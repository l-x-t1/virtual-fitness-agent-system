"""
核心 Cypher 查询模板

包含三类查询：
  1. 按用户目标推荐动作
  2. 按场地/器材筛选动作
  3. 混合查询（用户画像 + 场地 + 器材联合推荐）
"""

# ============================================================
# 1. 按用户目标推荐动作
# ============================================================

RECOMMEND_BY_GOAL = """
// 输入: $user_id, $limit (默认5)
// 根据用户的健身目标，找到最匹配的动作
MATCH (u:User {user_id: $user_id})
MATCH (u)-[:PREFERS]->(g:Goal)
MATCH (e:Exercise)-[:ACHIEVES]->(g)
OPTIONAL MATCH (u)-[r:CAN_DO]->(e)
WITH e, g, u, r
// 难度匹配：新手只能做难度<=1，中级<=2
WHERE u.fitness_level = 'advanced'
   OR (u.fitness_level = 'intermediate' AND e.difficulty <= 2)
   OR (u.fitness_level = 'beginner' AND e.difficulty <= 1)
// 计算匹配分数
WITH e, g,
     CASE
       WHEN u.preference CONTAINS e.category THEN 30
       ELSE 10
     END AS category_bonus,
     CASE
       WHEN u.injuries CONTAINS '膝' AND e.name IN ['深蹲', '弓步蹲', '开合跳', '节奏冲刺'] THEN -40
       WHEN u.injuries CONTAINS '腰' AND e.name IN ['平板支撑'] THEN -30
       ELSE 0
     END AS injury_penalty
WITH e, g.name AS goal_name,
     60 + category_bonus + injury_penalty +
     (5 - e.difficulty) * 5 AS match_score
WHERE match_score > 0
RETURN e.name AS name, e.category AS category, e.difficulty AS difficulty,
       e.target AS target, e.equipment AS equipment,
       match_score, goal_name,
       '匹配目标: ' + goal_name AS reason
ORDER BY match_score DESC
LIMIT $limit
"""

# ============================================================
# 2. 按场地/器材筛选动作
# ============================================================

RECOMMEND_BY_VENUE = """
// 输入: $venue_id, $limit (默认5)
// 在指定场地根据可用器材推荐能做的动作
MATCH (v:Venue {venue_id: $venue_id})
MATCH (v)-[:HAS_EQUIPMENT]->(eq:Equipment)
MATCH (e:Exercise)-[:REQUIRES]->(eq)
// 综合场地环境评分
WITH e, v, COUNT(DISTINCT eq) AS matched_equipment,
     (100 - v.crowd_index * 0.3 - v.air_quality * 0.15 + v.rating * 8) AS venue_score
RETURN e.name AS name, e.category AS category, e.difficulty AS difficulty,
       e.target AS target, e.equipment AS equipment,
       venue_score + matched_equipment * 10 AS match_score,
       v.name AS venue_name,
       '场地 ' + v.name + ' 器材匹配' AS reason
ORDER BY match_score DESC
LIMIT $limit
"""

# ============================================================
# 3. 混合查询：用户 + 目标 + 场地 + 器材联合推荐
# ============================================================

RECOMMEND_HYBRID = """
// 输入: $user_id, $lat, $lon, $max_distance_m (默认80000), $limit (默认5)
// 综合用户画像、距离、场地器材、环境进行推荐
MATCH (u:User {user_id: $user_id})
MATCH (u)-[:PREFERS]->(g:Goal)

// 找附近场地
MATCH (v:Venue)
WHERE v.latitude IS NOT NULL AND v.longitude IS NOT NULL
WITH u, g, v,
     point.distance(
       point({latitude: $lat, longitude: $lon}),
       point({latitude: v.latitude, longitude: v.longitude})
     ) AS distance_m
WHERE distance_m <= $max_distance_m

// 场地器材 → 匹配动作
MATCH (v)-[:HAS_EQUIPMENT]->(eq:Equipment)
MATCH (e:Exercise)-[:REQUIRES]->(eq)
MATCH (e)-[:ACHIEVES]->(g)

// 难度过滤
WHERE u.fitness_level = 'advanced'
   OR (u.fitness_level = 'intermediate' AND e.difficulty <= 2)
   OR (u.fitness_level = 'beginner' AND e.difficulty <= 1)

// 伤病惩罚
WITH u, v, e, distance_m, g,
     CASE
       WHEN u.injuries CONTAINS '膝' AND e.name IN ['深蹲', '弓步蹲', '开合跳', '节奏冲刺'] THEN -40
       WHEN u.injuries CONTAINS '腰' AND e.name IN ['平板支撑'] THEN -30
       ELSE 0
     END AS injury_penalty

// 综合评分
WITH e, v, distance_m, g,
     // 距离分数：越近越高
     (1.0 - distance_m / $max_distance_m) * 40 +
     // 环境分数
     (100 - v.crowd_index * 0.35 - v.air_quality * 0.15 + v.rating * 8) * 0.4 +
     // 偏好匹配
     CASE WHEN v.kind = 'indoor' THEN 5 ELSE 0 END +
     injury_penalty AS composite_score
WHERE composite_score > 0

RETURN e.name AS name, e.category AS category, e.difficulty AS difficulty,
       e.target AS target, e.equipment AS equipment,
       ROUND(composite_score, 1) AS match_score,
       g.name AS goal_name,
       v.name AS venue_name,
       ROUND(distance_m / 1000.0, 2) AS distance_km,
       v.crowd_index AS crowd_index,
       v.air_quality AS air_quality,
       v.rating AS rating,
       '距 ' + v.name + ' ' + ROUND(distance_m / 1000.0, 1) + 'km，匹配目标: ' + g.name AS reason
ORDER BY composite_score DESC
LIMIT $limit
"""

# ============================================================
# 4. 场地推荐（按用户位置 + 动作器材需求）
# ============================================================

RECOMMEND_VENUES = """
// 输入: $user_id, $exercise_name (可选), $lat, $lon, $max_distance_m (默认80000), $limit (默认5)
// 综合距离、器材匹配、拥挤度、空气质量推荐场地
MATCH (u:User {user_id: $user_id})
MATCH (v:Venue)
WHERE v.latitude IS NOT NULL AND v.longitude IS NOT NULL
WITH u, v,
     point.distance(
       point({latitude: $lat, longitude: $lon}),
       point({latitude: v.latitude, longitude: v.longitude})
     ) AS distance_m
WHERE distance_m <= $max_distance_m

// 如果指定了动作，检查该动作所需器材是否与场地匹配
OPTIONAL MATCH (e:Exercise {name: $exercise_name})
OPTIONAL MATCH (e)-[:REQUIRES]->(req_eq:Equipment)
OPTIONAL MATCH (v)-[:HAS_EQUIPMENT]->(ven_eq:Equipment)
WITH u, v, distance_m, e,
     COUNT(DISTINCT req_eq) AS total_required,
     COUNT(DISTINCT ven_eq) AS venue_has,
     COLLECT(DISTINCT req_eq.name) AS required_names,
     COLLECT(DISTINCT ven_eq.name) AS available_names

// 器材匹配率
WITH u, v, distance_m,
     CASE WHEN total_required = 0 THEN 1.0
          ELSE venue_has * 1.0 / total_required
     END AS equipment_match_ratio,
     required_names, available_names

// 综合评分
WITH v, distance_m, equipment_match_ratio,
     // Haversine 积分公式（沿用原 knowledge_graph.py 的算法）
     112
     - v.crowd_index * 0.55
     - v.air_quality * 0.14
     - (distance_m / 1000.0) * 1.8
     - v.density_score * 0.18
     + CASE WHEN distance_m / 1000.0 < 3 THEN 15 ELSE 0 END
     + CASE WHEN distance_m / 1000.0 < 10 THEN 10 ELSE 0 END
     + equipment_match_ratio * 20 AS match_score

RETURN v.name AS name, v.location AS location,
       v.latitude AS latitude, v.longitude AS longitude,
       v.crowd_index AS crowd_index, v.air_quality AS air_quality,
       v.rating AS rating, v.density_score AS density_score,
       v.equipment AS equipment, v.capacity AS capacity,
       v.kind AS kind, v.open_hours AS open_hours,
       ROUND(distance_m / 1000.0, 2) AS distance_km,
       ROUND(match_score, 1) AS match_score,
       ROUND(equipment_match_ratio * 100, 0) AS equipment_match_pct
ORDER BY match_score DESC
LIMIT $limit
"""

# ============================================================
# 5. 图谱统计信息查询
# ============================================================

GRAPH_STATS = """
MATCH (u:User)
WITH COUNT(u) AS user_count
MATCH (e:Exercise)
WITH user_count, COUNT(e) AS exercise_count
MATCH (v:Venue)
WITH user_count, exercise_count, COUNT(v) AS venue_count
MATCH (eq:Equipment)
WITH user_count, exercise_count, venue_count, COUNT(eq) AS equipment_count
MATCH ()-[r]->()
RETURN user_count, exercise_count, venue_count, equipment_count,
       COUNT(r) AS relationship_count
"""

# ============================================================
# 6. 创建/更新节点用的 MERGE 模板
# ============================================================

MERGE_USER = """
MERGE (u:User {user_id: $user_id})
SET u.nickname = $nickname, u.age = $age,
    u.fitness_level = $fitness_level, u.injuries = $injuries,
    u.preference = $preference, u.location = $location,
    u.points = $points, u.level = $level
RETURN u
"""

MERGE_EXERCISE = """
MERGE (e:Exercise {name: $name})
SET e.exercise_id = $exercise_id, e.category = $category,
    e.difficulty = $difficulty, e.target = $target,
    e.equipment = $equipment, e.standard_json = $standard_json
RETURN e
"""

MERGE_VENUE = """
MERGE (v:Venue {venue_id: $venue_id})
SET v.name = $name, v.location = $location,
    v.latitude = $latitude, v.longitude = $longitude,
    v.equipment = $equipment, v.capacity = $capacity,
    v.crowd_index = $crowd_index, v.air_quality = $air_quality,
    v.rating = $rating, v.density_score = $density_score,
    v.kind = $kind, v.open_hours = $open_hours
RETURN v
"""

MERGE_EQUIPMENT = """
MERGE (eq:Equipment {equipment_id: $equipment_id})
SET eq.name = $name, eq.category = $category,
    eq.is_smart = $is_smart, eq.status = $status,
    eq.location = $location, eq.latitude = $latitude,
    eq.longitude = $longitude, eq.venue_id = $venue_id
RETURN eq
"""

# ============================================================
# 7. 关系创建模板
# ============================================================

LINK_EXERCISE_TARGETS_MUSCLE = """
MATCH (e:Exercise {name: $exercise_name})
MATCH (m:MuscleGroup {name: $muscle_name})
MERGE (e)-[:TARGETS {weight: $weight}]->(m)
"""

LINK_EXERCISE_REQUIRES_EQUIPMENT = """
MATCH (e:Exercise {name: $exercise_name})
MATCH (eq:Equipment {name: $equipment_name})
MERGE (e)-[:REQUIRES {priority: $priority}]->(eq)
"""

LINK_EXERCISE_ACHIEVES_GOAL = """
MATCH (e:Exercise {name: $exercise_name})
MATCH (g:Goal {name: $goal_name})
MERGE (e)-[:ACHIEVES {effectiveness: $effectiveness}]->(g)
"""

LINK_VENUE_HAS_EQUIPMENT = """
MATCH (v:Venue {venue_id: $venue_id})
MATCH (eq:Equipment {equipment_id: $equipment_id})
MERGE (v)-[:HAS_EQUIPMENT {quantity: $quantity}]->(eq)
"""

LINK_USER_PREFERS_GOAL = """
MATCH (u:User {user_id: $user_id})
MATCH (g:Goal {name: $goal_name})
MERGE (u)-[:PREFERS]->(g)
"""

# 查询模板字典，方便按名称调用
QUERY_REGISTRY = {
    "recommend_by_goal": RECOMMEND_BY_GOAL,
    "recommend_by_venue": RECOMMEND_BY_VENUE,
    "recommend_hybrid": RECOMMEND_HYBRID,
    "recommend_venues": RECOMMEND_VENUES,
    "graph_stats": GRAPH_STATS,
}
