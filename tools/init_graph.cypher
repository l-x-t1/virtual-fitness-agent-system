-- ============================================================
-- Neo4j 初始化脚本: tools/init_graph.cypher
-- 执行方式:
--   docker exec -i fitness-neo4j cypher-shell -u neo4j -p fitness123 < tools/init_graph.cypher
-- 或在 Neo4j Browser 中逐段执行
-- ============================================================

-- 1. 约束
CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE;
CREATE CONSTRAINT exercise_name IF NOT EXISTS FOR (e:Exercise) REQUIRE e.name IS UNIQUE;
CREATE CONSTRAINT venue_id IF NOT EXISTS FOR (v:Venue) REQUIRE v.venue_id IS UNIQUE;
CREATE CONSTRAINT equipment_id IF NOT EXISTS FOR (eq:Equipment) REQUIRE eq.equipment_id IS UNIQUE;
CREATE CONSTRAINT muscle_name IF NOT EXISTS FOR (m:MuscleGroup) REQUIRE m.name IS UNIQUE;
CREATE CONSTRAINT goal_name IF NOT EXISTS FOR (g:Goal) REQUIRE g.name IS UNIQUE;

-- 2. 索引
CREATE INDEX user_level IF NOT EXISTS FOR (u:User) ON (u.fitness_level);
CREATE INDEX user_location IF NOT EXISTS FOR (u:User) ON (u.location);
CREATE INDEX exercise_category IF NOT EXISTS FOR (e:Exercise) ON (e.category);
CREATE INDEX exercise_difficulty IF NOT EXISTS FOR (e:Exercise) ON (e.difficulty);
CREATE INDEX venue_location IF NOT EXISTS FOR (v:Venue) ON (v.location);
CREATE INDEX venue_crowd IF NOT EXISTS FOR (v:Venue) ON (v.crowd_index);
CREATE INDEX equipment_category IF NOT EXISTS FOR (eq:Equipment) ON (eq.category);

-- 3. 预置 MuscleGroup 节点
MERGE (m1:MuscleGroup {name: '下肢力量'});
MERGE (m2:MuscleGroup {name: '核心稳定'});
MERGE (m3:MuscleGroup {name: '心肺耐力'});
MERGE (m4:MuscleGroup {name: '上肢力量'});
MERGE (m5:MuscleGroup {name: '全身协调'});
MERGE (m6:MuscleGroup {name: '下肢协调'});
MERGE (m7:MuscleGroup {name: '爆发力'});

-- 4. 预置 Goal 节点
MERGE (g1:Goal {name: '增肌'});
MERGE (g2:Goal {name: '减脂'});
MERGE (g3:Goal {name: '耐力提升'});
MERGE (g4:Goal {name: '柔韧性'});
MERGE (g5:Goal {name: '协调性'});
MERGE (g6:Goal {name: '综合训练'});
MERGE (g7:Goal {name: '爆发力'});

RETURN 'Neo4j graph schema initialized successfully.' AS result;
