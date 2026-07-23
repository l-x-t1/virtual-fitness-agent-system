# 基于多智能体的虚拟游戏化全民健身智能辅助系统

这是根据项目申请材料生成的轻量可运行原型，面向“全民健身 + 虚拟游戏化 + 多智能体协同”的研究场景。

## 核心功能

- 用户注册、登录与画像录入：年龄、体能水平、伤病史、运动偏好、当前位置。
- 多智能体协同：画像智能体、动作评估智能体、推荐智能体、游戏激励智能体、报告智能体。
- 轻量知识图谱：维护“用户 - 动作 - 场地 - 环境 - 关卡”的关联规则。
- 游戏化健身训练：动作关卡、积分、等级、新关卡解锁。
- 动作评分与纠错：用滑块模拟 MediaPipe 关键点评分，生成反馈建议。
- 场馆推荐：结合用户画像、动作器材、位置、拥挤度、空气质量进行排序。
- 数据闭环：训练记录写入 SQLite，并驱动报告、推荐和激励更新。

## 运行方式

```bash
cd D:\dachuang\virtual-fitness-agent-system\virtual-fitness-agent-system
python app.py
```

启动后打开：

```text
http://127.0.0.1:8765
```

首次使用可以点击“注册”，默认输入框已填入 `demo / 123456 / 李同学`。

## 项目结构

```text
app.py                 后端 HTTP 服务与 API 路由
database.py            SQLite 初始化、样例数据和数据访问
agents.py              多智能体协同逻辑
knowledge_graph.py     轻量知识图谱和推荐规则
static/app.js          前端交互、游戏流程和 API 调用
static/styles.css      页面样式
templates/index.html   单页应用入口
data/fitness.db        运行后自动生成的数据库
```

## 后续扩展方向

- 将滑块评分替换为 MediaPipe Pose 真实关键点识别。
- 将轻量图谱迁移到 NetworkX 或 Neo4j。
- 接入天气、空气质量、场馆人流 API。
- 增加教师端或管理员端，用于查看试点数据与干预建议。
# FastAPI 版本启动说明

后端已迁移到 FastAPI，原生 `http.server` 启动方式已废弃。

```bash
python -m pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

启动后可访问：

- 系统页面：`http://127.0.0.1:8765/`
- Swagger 文档：`http://127.0.0.1:8765/docs`
- ReDoc 文档：`http://127.0.0.1:8765/redoc`
- OpenAPI：`http://127.0.0.1:8765/openapi.json`
- 训练 WebSocket：`ws://127.0.0.1:8765/ws/training?token=<JWT>`

生产部署前必须设置长度不少于 32 字节的 `JWT_SECRET`。登录和注册返回 Bearer access token；
受保护接口不再接受 `user_id` 或 `admin_user_id` 作为身份凭证。

## LLM Agent 调试

5 个智能体已支持 LangChain + DeepSeek / 阿里百炼兼容接口。复制 `.env.example` 为 `.env` 后，可按需配置：

```text
LLM_PROVIDER=deepseek
MODEL_NAME=deepseek-chat
DEEPSEEK_API_KEY=

# 或
LLM_PROVIDER=dashscope
MODEL_NAME=qwen-plus
DASHSCOPE_API_KEY=
```

本地快速查看 5 个 Agent 的结构化输出：

```bash
python test_agents.py
```

该脚本使用模拟用户、训练历史和 MediaPipe 姿态数据，不依赖真实数据库或线上 API Key。

## AI 对话教练（人员 C）

登录系统后访问 `http://127.0.0.1:8765/ai-coach`。该模块独立提供：

- DeepSeek 与阿里云百炼兼容接口，可在页面按会话切换供应商和模型。
- 多轮上下文、会话列表和会话状态；消息独立保存到 SQLite，默认保留 30 天。
- 基于身体数据和训练历史的画像，包含频率、时长、平均分、强弱动作和成绩趋势。
- 结构化个性化训练卡，以及按伤病风险选择低冲击替代动作。
- 24 条内置健身资料和独立 FAISS 检索；FAISS 不可用时自动使用关键词检索。
- 管理员可通过 `/api/ai/knowledge/import` 批量导入自定义 JSON 健身资料。
- Chrome/Edge 浏览器 Web Speech API 语音输入和语音播报。
- 没有任何 AI API Key 时自动进入降级演示模式。
- 页面可直接测试当前 DeepSeek／百炼模型连接并显示延迟或错误。

人员 C 使用独立配置，不依赖知识图谱服务：

```text
AI_LLM_PROVIDER=deepseek
AI_MODEL_NAME=deepseek-v4-flash
AI_DEEPSEEK_API_KEY=

# 或在页面选择阿里云百炼
AI_DASHSCOPE_API_KEY=
```

主要接口：`GET /api/ai/status`、`POST/GET /api/ai/sessions`、`POST /api/ai/chat`、
`GET /api/ai/profile`、`POST /api/ai/plans`、`POST /api/ai/corrections`、
`GET /api/ai/knowledge`、`POST /api/ai/knowledge/import`、`POST /api/ai/providers/test`。
