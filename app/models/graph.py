"""
图谱请求/响应 Pydantic 模型 — 注册到 app/models/graph.py

这些模型用于:
  1. FastAPI 路由的请求体验证
  2. 与推荐 Agent (Person C) 的接口格式约定
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ============================================================
# 请求模型
# ============================================================

class GraphQueryRequest(BaseModel):
    """自然语言图谱查询请求"""
    question: str = Field(..., min_length=1, max_length=500, description="自然语言查询，如'推荐适合新手的核心训练动作'")


class GraphSearchRequest(BaseModel):
    """GraphRAG 知识检索请求"""
    query: str = Field(..., min_length=1, max_length=500, description="用户问题或知识检索文本")
    user_id: int | None = Field(None, ge=1, description="可选用户 ID；默认使用当前登录用户")
    top_k: int = Field(8, ge=1, le=20, description="返回和检索的最大条数")
    use_llm: bool = Field(True, description="是否调用 LLM 生成最终答案")


class GraphRecommendRequest(BaseModel):
    """结构化推荐请求 — 供推荐 Agent 调用"""
    user_id: int = Field(..., description="用户ID")
    exercise_name: str | None = Field(None, max_length=100, description="当前动作名，用于场地器材匹配")
    lat: float | None = Field(None, ge=-90, le=90, description="用户当前纬度")
    lon: float | None = Field(None, ge=-180, le=180, description="用户当前经度")
    max_distance_m: int = Field(80_000, ge=100, le=500_000, description="场地搜索半径（米）")
    use_llm: bool = Field(False, description="是否使用LLM重排序")
    top_k: int = Field(5, ge=1, le=10, description="返回结果数量")


class GraphImportRequest(BaseModel):
    """数据导入请求"""
    users: bool = Field(True, description="导入用户")
    exercises: bool = Field(True, description="导入动作")
    venues: bool = Field(True, description="导入场地")


# ============================================================
# 响应模型
# ============================================================

class ExerciseRecommendItem(BaseModel):
    """动作推荐条目 — 与 RecommendAgent 的 RecommendationItem 兼容"""
    name: str = Field(..., description="动作名称")
    category: str = Field("", description="动作类别")
    difficulty: int = Field(1, ge=1, le=5, description="难度 1-5")
    target: str = Field("", description="训练目标")
    equipment: str = Field("", description="所需器材")
    match_score: float = Field(0.0, description="匹配分数 0-100")
    reason: str = Field("", description="推荐原因")


class VenueRecommendItem(BaseModel):
    """场地推荐条目"""
    name: str = Field(..., description="场地名称")
    location: str = Field("", description="所在区域")
    latitude: float | None = Field(None, description="纬度")
    longitude: float | None = Field(None, description="经度")
    crowd_index: int = Field(50, description="拥挤指数")
    air_quality: int = Field(50, description="空气质量")
    rating: float = Field(4.0, description="评分")
    density_score: float = Field(0.0, description="密度评分")
    equipment: str = Field("", description="场地器材")
    capacity: int = Field(0, description="容量")
    kind: str = Field("outdoor", description="indoor/outdoor")
    open_hours: str = Field("", description="开放时间")
    distance_km: float | None = Field(None, description="距离（公里）")
    match_score: float = Field(0.0, description="匹配分数")


class GraphRecommendResponse(BaseModel):
    """图谱推荐响应 — 供推荐 Agent 消费"""
    exercises: list[ExerciseRecommendItem] = Field(default_factory=list, description="推荐动作列表")
    venues: list[VenueRecommendItem] = Field(default_factory=list, description="推荐场地列表")


class GraphQueryResponse(BaseModel):
    """自然语言查询响应"""
    question: str = ""
    answer: str = ""
    cypher: str = Field("", description="生成的 Cypher 语句（调试用）")
    exercises: list[ExerciseRecommendItem] = Field(default_factory=list)
    venues: list[VenueRecommendItem] = Field(default_factory=list)


class GraphSearchResponse(BaseModel):
    """GraphRAG 检索响应，供 API 和 Agent 消费"""
    query: str = ""
    knowledge: list[dict] = Field(default_factory=list)
    relations: list[dict] = Field(default_factory=list)
    answer: str = ""
    context: str = ""
    keywords: list[str] = Field(default_factory=list)
    used_llm: bool = False


class GraphStatusResponse(BaseModel):
    """图谱状态"""
    available: bool = False
    node_count: dict[str, int] = Field(default_factory=dict)
    relationship_count: int = 0


class GraphImportResponse(BaseModel):
    """导入结果"""
    users: int = 0
    exercises: int = 0
    venues: int = 0
    equipment: int = 0
    relationships: int = 0
    errors: list[str] = Field(default_factory=list)
