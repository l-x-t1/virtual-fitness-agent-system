"""
图谱 API 路由 — /api/graph/*

挂载到 FastAPI，遵循项目现有 Controller 模式
"""

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool

from app.controllers.auth import envelope
from app.dependencies.auth import get_current_user
from app.models.graph import (
    GraphImportRequest,
    GraphQueryRequest,
    GraphRecommendRequest,
    GraphSearchRequest,
)
from app.services.graph_service import GraphService, get_graph_service

router = APIRouter(prefix="/api/graph", tags=["知识图谱"])


# ============================================================
# 推荐接口（核心 — 供 RecommendAgent 调用）
# ============================================================

@router.post("/recommend", summary="图谱推荐（供推荐Agent调用）")
async def graph_recommend(
    request: Request,
    body: GraphRecommendRequest,
    user: dict = Depends(get_current_user),
    service: GraphService = Depends(get_graph_service),
):
    """
    根据用户画像 + 可选动作 + 位置进行图谱推荐。
    返回适合该用户的动作列表和场地列表。
    供 RecommendAgent.recommend() 调用。
    """
    return envelope(
        request,
        await run_in_threadpool(
            service.recommend,
            user=user,
            exercise_name=body.exercise_name,
            lat=body.lat,
            lon=body.lon,
            max_distance_m=body.max_distance_m,
            use_llm=body.use_llm,
            top_k=body.top_k,
        ),
    )


# ============================================================
# 自然语言查询（GraphRAG LLM 模式）
# ============================================================

@router.post("/query", summary="自然语言图谱查询（GraphRAG）")
async def graph_query(
    request: Request,
    body: GraphQueryRequest,
    user: dict = Depends(get_current_user),
    service: GraphService = Depends(get_graph_service),
):
    """
    使用自然语言查询图谱（GraphCypherQAChain）。
    例: "什么动作能改善核心力量？附近哪里可以做？"
    """
    return envelope(
        request,
        await run_in_threadpool(service.query, body.question),
    )


@router.post("/search", summary="GraphRAG 健身知识检索")
async def graph_search(
    request: Request,
    body: GraphSearchRequest,
    user: dict = Depends(get_current_user),
    service: GraphService = Depends(get_graph_service),
):
    """检索知识图谱并返回 knowledge、relations 和 answer，供 AI Agent 调用。"""
    user_id = body.user_id or user.get("id") or user.get("user_id")
    return envelope(
        request,
        await run_in_threadpool(
            service.search,
            query=body.query,
            user_id=user_id,
            top_k=body.top_k,
            use_llm=body.use_llm,
        ),
    )


# ============================================================
# 管理接口
# ============================================================

@router.get("/status", summary="图谱状态")
async def graph_status(
    request: Request,
    service: GraphService = Depends(get_graph_service),
):
    """返回 Neo4j 连接状态和节点/关系统计"""
    return envelope(request, await run_in_threadpool(service.status))


@router.post("/import", summary="从数据库导入数据到图谱")
async def graph_import(
    request: Request,
    body: GraphImportRequest = None,
    user: dict = Depends(get_current_user),
    service: GraphService = Depends(get_graph_service),
):
    """触发全量数据导入（从现有 SQL 数据库同步到 Neo4j）"""
    if body is None:
        body = GraphImportRequest()
    return envelope(request, await run_in_threadpool(service.import_data))


# ============================================================
# 简化版推荐接口（GET，方便调试）
# ============================================================

@router.get("/exercises", summary="获取图谱动作推荐")
async def graph_exercises(
    request: Request,
    exercise_name: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    user: dict = Depends(get_current_user),
    service: GraphService = Depends(get_graph_service),
):
    """仅返回图谱推荐的动作列表"""
    exercises = await run_in_threadpool(
        service.recommend_exercises, user, lat, lon
    )
    return envelope(request, {"exercises": exercises})


@router.get("/venues", summary="获取图谱场地推荐")
async def graph_venues(
    request: Request,
    exercise_name: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    user: dict = Depends(get_current_user),
    service: GraphService = Depends(get_graph_service),
):
    """仅返回图谱推荐的场地列表"""
    venues = await run_in_threadpool(
        service.recommend_venues, user, exercise_name, lat, lon
    )
    return envelope(request, {"venues": venues})
