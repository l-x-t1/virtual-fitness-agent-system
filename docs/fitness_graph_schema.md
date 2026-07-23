# 健身知识图谱 Schema

本文档定义“人员 B：知识图谱 + GraphRAG 知识库建设”模块的核心图谱结构。Schema 以 Neo4j Community 为目标，代码定义位于 `app/graph/graph_schema.py`。

## 设计目标

核心链路：

```text
User
  -HAS_RECORD->
TrainingRecord
  -CONTAINS->
Exercise
  -HAS_ERROR->
ErrorPoint
  -CORRECT_BY->
Correction
```

GraphRAG 使用该链路完成：

```text
用户问题 -> 图谱实体检索 -> 关系扩展 -> 纠错方案 Context -> LLM 答案
```

## 节点定义

### User

用户节点，同步自业务数据库 `users`。

主键：`user_id`

属性：

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| user_id | Integer | 业务用户 ID |
| nickname | String | 昵称 |
| age | Integer | 年龄 |
| fitness_level | String | beginner/intermediate/advanced |
| injuries | String | 伤病史 |
| preference | String | 运动偏好 |
| location | String | 常用训练位置 |
| points | Integer | 积分 |
| level | Integer | 游戏化等级 |

### TrainingRecord

训练记录节点，对应一次训练或动作评估。

主键：`record_id`

属性：

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| record_id | String | 图谱稳定 ID，例如 `session:12` |
| session_id | Integer | 业务训练记录 ID |
| user_id | Integer | 用户 ID |
| exercise_name | String | 动作名称 |
| score | Integer | 动作评分 |
| duration | Integer | 训练时长，单位秒 |
| feedback | String | 训练反馈 |
| created_at | DateTime | 创建时间 |

### Exercise

训练动作节点。

主键：`name`

属性：

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| exercise_id | Integer | 业务动作 ID |
| name | String | 动作名称 |
| category | String | 力量/有氧/核心/柔韧等 |
| difficulty | Integer | 难度 1-5 |
| target | String | 训练目标描述 |
| standard_action | String | 标准动作文本 |
| standard_json | String | 结构化动作标准 |
| precautions | String | 注意事项 |

### BodyPart

身体部位节点。

主键：`name`

属性：`name`、`alias`、`description`

示例：`膝关节`、`髋部`、`核心`、`肩部`

### Muscle

肌肉或肌群节点。

主键：`name`

属性：`name`、`body_part`、`function`、`alias`

示例：`股四头肌`、`臀大肌`、`臀中肌`、`腘绳肌`、`腹横肌`

### ErrorPoint

动作错误点节点。

主键：`code`

属性：

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| code | String | 错误编码 |
| name | String | 错误名称 |
| description | String | 可观察表现 |
| reason | String | 常见原因 |
| risk_level | String | low/medium/high |

示例：`膝盖内扣`、`腰背塌陷`、`重心前移`

### Correction

纠正方案节点。

主键：`code`

属性：

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| code | String | 纠正方案编码 |
| title | String | 方案标题 |
| solution | String | 纠正方法 |
| drills | String | 辅助训练 |
| frequency | String | 建议频率 |
| safety_note | String | 安全提示 |

### Equipment

训练器械节点。

主键：`equipment_id`

属性：`equipment_id`、`name`、`category`、`is_smart`、`status`、`location`、`venue_id`

### Goal

训练目标节点。

主键：`name`

属性：`name`、`description`、`priority`

示例：`增肌`、`减脂`、`康复`、`柔韧性`、`综合训练`

### Level

训练等级节点。

主键：`name`

属性：`name`、`rank`、`description`

示例：`beginner`、`intermediate`、`advanced`

## 关系定义

| 关系 | 起点 | 终点 | 说明 |
| --- | --- | --- | --- |
| HAS_RECORD | User | TrainingRecord | 用户拥有训练记录 |
| CONTAINS | TrainingRecord | Exercise | 训练记录包含动作 |
| TARGETS | Exercise | Muscle | 动作训练肌肉 |
| LOCATED_IN | Muscle | BodyPart | 肌肉归属身体部位 |
| USES | Exercise | Equipment | 动作使用器械 |
| HAS_ERROR | Exercise | ErrorPoint | 动作存在常见错误 |
| CORRECT_BY | ErrorPoint | Correction | 错误可由方案纠正 |
| HAS_GOAL | User | Goal | 用户训练目标 |
| HAS_LEVEL | User | Level | 用户训练等级 |
| OBSERVED_ERROR | TrainingRecord | ErrorPoint | 某次训练观测到错误 |
| RECOMMENDED_CORRECTION | TrainingRecord | Correction | 某次训练推荐纠正方案 |

## 核心查询链路

### 查询用户最近训练错误

```cypher
MATCH (u:User {user_id: $user_id})-[:HAS_RECORD]->(r:TrainingRecord)
MATCH (r)-[:CONTAINS]->(e:Exercise)
MATCH (r)-[:OBSERVED_ERROR]->(ep:ErrorPoint)
MATCH (ep)-[:CORRECT_BY]->(c:Correction)
RETURN u.nickname AS user,
       e.name AS exercise,
       ep.name AS error,
       ep.reason AS reason,
       c.solution AS correction,
       r.created_at AS created_at
ORDER BY r.created_at DESC
LIMIT $limit
```

### 查询动作常见错误与纠正

```cypher
MATCH (e:Exercise {name: $exercise_name})-[:HAS_ERROR]->(ep:ErrorPoint)
OPTIONAL MATCH (ep)-[:CORRECT_BY]->(c:Correction)
RETURN e.name AS exercise,
       ep.name AS error,
       ep.reason AS reason,
       c.title AS correction_title,
       c.solution AS correction
ORDER BY ep.risk_level DESC
```

## 兼容现有模块

当前项目已有推荐图谱链路，仍保留：

| 关系 | 用途 |
| --- | --- |
| REQUIRES | 旧版 `Exercise -> Equipment` |
| ACHIEVES | 旧版 `Exercise -> Goal` |
| PREFERS | 旧版 `User -> Goal` |
| COMPLETED | 旧版 `User -> Exercise` |
| HAS_EQUIPMENT | 旧版 `Venue -> Equipment` |
| SUITABLE_FOR | 旧版 `Venue -> Exercise` |
| TRAINED_AT | 旧版 `User -> Venue` |

后续实现时，新 GraphRAG 查询优先使用 `HAS_RECORD / CONTAINS / HAS_ERROR / CORRECT_BY`；推荐模块继续兼容旧关系，避免影响已有 Agent。

## 初始化方式

在代码中调用：

```python
from app.graph.graph_schema import initialize_graph_schema

result = initialize_graph_schema()
print(result)
```

Neo4j 离线时会返回 `errors`，不会影响主服务启动。

## 数据导入

结构化知识库位置：

```text
app/graph/knowledge_base/fitness_knowledge.json
```

当前知识库包含：

| 类型 | 内容 |
| --- | --- |
| 动作知识 | 深蹲、平板支撑、弓步蹲、开合跳 |
| 错误知识 | 膝盖内扣、脚跟离地、腰背塌陷、躯干晃动、落地过重 |
| 纠正方案 | 髋外展控制、踝活动度、核心支撑、单腿稳定、低冲击落地 |
| 训练方案 | 增肌、减脂、康复 |
| 用户经验 | 深蹲膝盖疼、平板支撑腰酸等经验知识 |

导入入口：

```bash
python -m app.graph.data_import --full
```

也可以只导入知识库：

```bash
python -m app.graph.data_import --knowledge
```

代码调用：

```python
from app.graph.data_import import import_all, import_knowledge_base, load_knowledge_base

knowledge = load_knowledge_base()
stats = import_all()
```

`import_all()` 会执行：

1. 初始化 Neo4j 约束、索引和基础参考数据
2. 导入 `fitness_knowledge.json`
3. 从业务库同步 User、Exercise、Venue、Equipment
4. 从 `sessions` 同步 TrainingRecord
5. 为低分训练记录建立 `OBSERVED_ERROR` 和 `RECOMMENDED_CORRECTION` 关系

## Cypher 查询接口

查询封装位于：

```text
app/graph/cypher_query.py
```

所有查询都使用固定 Cypher 模板和参数绑定，不拼接用户输入。

### find_user_training_history

用途：查询某用户最近训练记录、动作错误和纠正方案。

```python
from app.graph.cypher_query import find_user_training_history

result = find_user_training_history(user_id=1, limit=10)
```

返回结构：

```json
{
  "user_id": 1,
  "records": [
    {
      "user": "demo",
      "exercise": "深蹲",
      "error": "膝盖内扣",
      "reason": "臀中肌和髋外旋控制不足",
      "correction": "加强髋外展与膝盖力线控制"
    }
  ]
}
```

### find_exercise_errors

用途：查询动作常见错误和对应纠正方案。

```python
from app.graph.cypher_query import find_exercise_errors

result = find_exercise_errors("深蹲")
```

### find_correction_plan

用途：按动作、错误编码或错误名称查询纠正方案。

```python
from app.graph.cypher_query import find_correction_plan

result = find_correction_plan(exercise_name="深蹲", error_name="膝盖内扣")
```

### find_related_exercises

用途：按共享肌肉、目标、身体部位或错误点查询相关动作。

```python
from app.graph.cypher_query import find_related_exercises

result = find_related_exercises("深蹲")
```

### search_training_knowledge

用途：GraphRAG 入口级关键词搜索，覆盖 Exercise、ErrorPoint、Correction、Muscle、Goal。

```python
from app.graph.cypher_query import search_training_knowledge

result = search_training_knowledge("深蹲膝盖疼")
```

## GraphRAG 调用方式

GraphRAG 独立模块位于：

```text
app/graphrag/
  graph_retriever.py
  graph_chain.py
  graph_prompt.py
```

流程：

```text
用户问题
  -> GraphRetriever.extract_keywords()
  -> CypherQueryService 查询 Neo4j
  -> GraphRetriever.build_context()
  -> GraphRAGChain 调用 LLMClient
  -> 返回 answer / knowledge / relations
```

代码调用：

```python
from app.graphrag import GraphRAGChain

chain = GraphRAGChain()
result = chain.invoke("我的深蹲膝盖疼是什么原因？", user_id=1)
```

返回结构：

```json
{
  "query": "我的深蹲膝盖疼是什么原因？",
  "knowledge": [],
  "relations": [],
  "answer": "",
  "context": "",
  "keywords": ["深蹲", "膝盖"],
  "used_llm": true
}
```

当 LLM API Key 未配置或 Neo4j 离线时，模块会返回结构化降级结果，不影响后端服务启动。

## API 接口

新增 GraphRAG 检索接口：

```http
POST /api/graph/search
Authorization: Bearer <JWT>
Content-Type: application/json
```

请求体：

```json
{
  "query": "我的深蹲膝盖疼是什么原因？",
  "top_k": 8,
  "use_llm": true
}
```

可选传入 `user_id`；不传时使用当前登录用户。

响应体位于项目统一 envelope 的 `data` 字段：

```json
{
  "knowledge": [],
  "relations": [],
  "answer": "",
  "context": "",
  "keywords": [],
  "used_llm": false
}
```

该接口面向 AI Agent 和后端服务集成，旧 `/api/graph/query`、`/api/graph/recommend` 保持不变。
