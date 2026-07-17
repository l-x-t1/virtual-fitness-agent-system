from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool

from app.controllers.auth import envelope
from app.dependencies.auth import get_current_user
from app.models.user import ProfileUpdate
from app.dependencies.services import get_coordinator
from app.services.user_service import UserService

router = APIRouter(prefix="/api", tags=["用户"])


@router.get("/dashboard")
async def dashboard(request: Request, lat: float | None = None, lon: float | None = None, location: str | None = None,
                    user=Depends(get_current_user), coordinator=Depends(get_coordinator)):
    query = []
    if lat is not None and lon is not None:
        query.extend((f"lat={lat}", f"lon={lon}", f"location={location or '浏览器当前位置'}"))
    data = await run_in_threadpool(UserService(coordinator).dashboard, user, "&".join(query))
    return envelope(request, data)


@router.post("/profile")
async def update_profile(body: ProfileUpdate, request: Request, user=Depends(get_current_user),
                         coordinator=Depends(get_coordinator)):
    data = await run_in_threadpool(UserService(coordinator).update_profile, user, body.model_dump())
    return envelope(request, data)


@router.get("/sessions")
async def sessions(request: Request, user=Depends(get_current_user), coordinator=Depends(get_coordinator)):
    return envelope(request, await run_in_threadpool(UserService(coordinator).sessions, user["id"]))


@router.get("/badges")
async def badges(request: Request, user=Depends(get_current_user), coordinator=Depends(get_coordinator)):
    return envelope(request, await run_in_threadpool(UserService(coordinator).badges, user["id"]))


@router.get("/points/logs")
async def point_logs(request: Request, user=Depends(get_current_user), coordinator=Depends(get_coordinator)):
    return envelope(request, await run_in_threadpool(UserService(coordinator).point_logs, user["id"]))
