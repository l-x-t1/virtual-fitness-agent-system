from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse

from app.ai import AICoach
from app.ai.sse import AIStreamOrchestrator
from app.controllers.auth import envelope
from app.dependencies.auth import get_current_user
from app.models.ai import (
    AICorrectionRequest,
    AIChatRequest,
    AIKnowledgeImportRequest,
    AIPlanRequest,
    AIProviderTestRequest,
    AISessionCreate,
)
from app.repositories import FitnessRepository, session_scope

router = APIRouter(tags=["AI 教练"])
coach = AICoach()
stream_orchestrator = AIStreamOrchestrator(coach)
PAGE = Path(__file__).resolve().parents[2] / "templates" / "ai-coach.html"


def recent_history(user_id: int) -> list[dict]:
    with session_scope() as session:
        return FitnessRepository(session).recent_sessions(user_id, 20)


@router.get("/ai-coach", include_in_schema=False)
async def ai_coach_page():
    return FileResponse(PAGE)


@router.get("/api/ai/status")
async def ai_status(request: Request, user=Depends(get_current_user)):
    return envelope(request, coach.status())


@router.post("/api/ai/sessions")
async def create_session(body: AISessionCreate, request: Request, user=Depends(get_current_user)):
    return envelope(request, coach.create_session(user["id"], body.title))


@router.get("/api/ai/sessions")
async def list_sessions(request: Request, user=Depends(get_current_user)):
    return envelope(request, {"sessions": coach.sessions(user["id"])})


@router.get("/api/ai/sessions/{session_id}")
async def get_session(session_id: str, request: Request, user=Depends(get_current_user)):
    data = coach.session(user["id"], session_id)
    if not data:
        raise HTTPException(status_code=404, detail="AI 会话不存在")
    return envelope(request, data)


@router.delete("/api/ai/sessions/{session_id}")
async def delete_session(session_id: str, request: Request, user=Depends(get_current_user)):
    if not coach.delete_session(user["id"], session_id):
        raise HTTPException(status_code=404, detail="AI 会话不存在")
    return envelope(request, {"deleted": True})


@router.post("/api/ai/chat")
async def ai_chat(body: AIChatRequest, request: Request, user=Depends(get_current_user)):
    history = await run_in_threadpool(recent_history, user["id"])
    try:
        data = await run_in_threadpool(coach.chat, user, history, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope(request, data)


@router.post("/api/ai/chat/stream")
async def ai_chat_stream(body: AIChatRequest, request: Request, user=Depends(get_current_user)):
    history = await run_in_threadpool(recent_history, user["id"])
    events = stream_orchestrator.stream(
        user,
        history,
        body.model_dump(),
        is_disconnected=request.is_disconnected,
    )
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/ai/profile")
async def ai_profile(
    request: Request,
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None, max_length=100),
    user=Depends(get_current_user),
):
    history = await run_in_threadpool(recent_history, user["id"])
    data = await run_in_threadpool(coach.profile, user, history, True, provider, model)
    return envelope(request, data)


@router.post("/api/ai/plans")
async def ai_plan(body: AIPlanRequest, request: Request, user=Depends(get_current_user)):
    history = await run_in_threadpool(recent_history, user["id"])
    data = await run_in_threadpool(coach.plan, user, history, body.model_dump())
    return envelope(request, data)


@router.post("/api/ai/corrections")
async def ai_correction(body: AICorrectionRequest, request: Request, user=Depends(get_current_user)):
    data = await run_in_threadpool(coach.correct, user, body.model_dump())
    return envelope(request, data)


@router.get("/api/ai/knowledge")
async def ai_knowledge_status(request: Request, user=Depends(get_current_user)):
    return envelope(request, coach.knowledge.stats())


@router.post("/api/ai/knowledge/import")
async def ai_knowledge_import(
    body: AIKnowledgeImportRequest,
    request: Request,
    user=Depends(get_current_user),
):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可导入 AI 知识资料")
    documents = [item.model_dump() for item in body.documents]
    data = await run_in_threadpool(coach.knowledge.import_documents, documents)
    return envelope(request, data)


@router.post("/api/ai/providers/test")
async def ai_provider_test(
    body: AIProviderTestRequest,
    request: Request,
    user=Depends(get_current_user),
):
    data = await run_in_threadpool(coach.test_provider, body.provider, body.model)
    return envelope(request, data)
