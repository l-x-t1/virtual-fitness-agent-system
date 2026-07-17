from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool

from app.models.auth import LoginRequest, RegisterRequest
from app.services import auth_service

router = APIRouter(prefix="/api", tags=["认证"])


def envelope(request: Request, data, message: str = "success"):
    return {"code": "OK", "message": message, "data": data, "request_id": request.state.request_id}


@router.post("/login")
async def login(body: LoginRequest, request: Request):
    data = await run_in_threadpool(auth_service.login, body.username, body.password)
    return envelope(request, data)


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, request: Request):
    data = await run_in_threadpool(auth_service.register, body.username, body.password, body.nickname)
    return envelope(request, data, "注册成功")
