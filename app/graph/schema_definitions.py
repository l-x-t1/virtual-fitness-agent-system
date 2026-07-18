"""
Cypher 建表语句：约束、索引、节点与关系定义

在 Neo4j Browser 或 cypher-shell 中执行，或启动容器后自动执行：
  docker exec -i fitness-neo4j cypher-shell -u neo4j -p fitness123 < tools/init_graph.cypher
"""

# ============================================================
# 1. 约束（唯一性保证）
# ============================================================
CONSTRAINTS = [
    "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE;",
    "CREATE CONSTRAINT exercise_name IF NOT EXISTS FOR (e:Exercise) REQUIRE e.name IS UNIQUE;",
    "CREATE CONSTRAINT venue_id IF NOT EXISTS FOR (v:Venue) REQUIRE v.venue_id IS UNIQUE;",
    "CREATE CONSTRAINT equipment_id IF NOT EXISTS FOR (eq:Equipment) REQUIRE eq.equipment_id IS UNIQUE;",
    "CREATE CONSTRAINT muscle_name IF NOT EXISTS FOR (m:MuscleGroup) REQUIRE m.name IS UNIQUE;",
    "CREATE CONSTRAINT goal_name IF NOT EXISTS FOR (g:Goal) REQUIRE g.name IS UNIQUE;",
]

# ============================================================
# 2. 索引（加速查询）
# ============================================================
INDEXES = [
    "CREATE INDEX user_level IF NOT EXISTS FOR (u:User) ON (u.fitness_level);",
    "CREATE INDEX user_location IF NOT EXISTS FOR (u:User) ON (u.location);",
    "CREATE INDEX exercise_category IF NOT EXISTS FOR (e:Exercise) ON (e.category);",
    "CREATE INDEX exercise_difficulty IF NOT EXISTS FOR (e:Exercise) ON (e.difficulty);",
    "CREATE INDEX exercise_equipment IF NOT EXISTS FOR (e:Exercise) ON (e.equipment);",
    "CREATE INDEX venue_location IF NOT EXISTS FOR (v:Venue) ON (v.location);",
    "CREATE INDEX venue_crowd IF NOT EXISTS FOR (v:Venue) ON (v.crowd_index);",
    "CREATE INDEX equipment_category IF NOT EXISTS FOR (eq:Equipment) ON (eq.category);",
    "CREATE INDEX equipment_venue IF NOT EXISTS FOR (eq:Equipment) ON (eq.venue_id);",
]

# ============================================================
# 3. 节点属性定义（文档性质，实际在建节点时通过属性键隐式定义）
# ============================================================
NODE_SCHEMA = """
Node Labels & Properties:

User {
  user_id: Integer,        # 用户ID，来自 users 表
  nickname: String,        # 昵称
  age: Integer,            # 年龄
  fitness_level: String,   # beginner / intermediate / advanced
  injuries: String,        # 伤病史（可空）
  preference: String,      # 运动偏好
  location: String,        # 常驻位置
  points: Integer,         # 积分
  level: Integer           # 等级
}

Exercise {
  exercise_id: Integer,    # 动作ID
  name: String,            # 动作名称，如"深蹲"
  category: String,        # 类别：力量训练/有氧训练/核心训练/柔韧性训练
  difficulty: Integer,     # 难度 1-5
  target: String,          # 训练目标肌群/能力
  equipment: String,       # 所需器材
  standard_json: String    # 标准动作 JSON
}

Venue {
  venue_id: Integer,       # 场地ID
  name: String,            # 场地名称
  location: String,        # 所在区域
  latitude: Float,         # 纬度
  longitude: Float,        # 经度
  equipment: String,       # 场地器材（逗号分隔）
  capacity: Integer,       # 容量
  crowd_index: Integer,    # 拥挤指数 0-100
  air_quality: Integer,    # 空气质量指数
  rating: Float,           # 评分 1-5
  density_score: Float,    # 密度评分
  kind: String,            # indoor / outdoor
  open_hours: String       # 开放时间
}

Equipment {
  equipment_id: Integer,   # 器材ID
  name: String,            # 器材名称
  category: String,        # 器材类别
  is_smart: Boolean,       # 是否智能器材
  status: String,          # normal / maintenance / offline
  location: String,        # 所在位置
  latitude: Float,
  longitude: Float,
  venue_id: Integer        # 所属场地ID
}

MuscleGroup {
  name: String             # 肌群名称，如"下肢力量"/"核心稳定"/"心肺耐力"/"上肢力量"/"全身协调"
}

Goal {
  name: String             # 目标名称，如"增肌"/"减脂"/"耐力提升"/"柔韧性"/"协调性"/"综合训练"
}
"""

# ============================================================
# 4. 关系类型定义
# ============================================================
RELATIONSHIP_SCHEMA = """
Relationships:

(Exercise)-[:TARGETS {weight: Float}]->(MuscleGroup)
  动作 → 目标肌群

(Exercise)-[:REQUIRES {priority: String}]->(Equipment)
  动作 → 所需器材，priority: required/optional

(Exercise)-[:ACHIEVES {effectiveness: Float}]->(Goal)
  动作 → 达成的健身目标，effectiveness: 0-1

(Venue)-[:HAS_EQUIPMENT {quantity: Integer}]->(Equipment)
  场地 → 拥有的器材

(Venue)-[:SUITABLE_FOR {score: Float}]->(Exercise)
  场地 → 适合进行的动作，score 综合器材匹配 + 环境评分

(User)-[:PREFERS]->(Goal)
  用户偏好 → 训练目标

(User)-[:CAN_DO {match_score: Float, reason: String}]->(Exercise)
  用户 → 适合的动作，含匹配分数和原因

(User)-[:TRAINED_AT {session_count: Integer, avg_score: Float}]->(Venue)
  用户 → 曾训练的场地

(User)-[:COMPLETED {score: Integer, duration: Integer, at: DateTime}]->(Exercise)
  用户 → 已完成训练的动作（训练记录）
"""
