import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from agents import AgentCoordinator
from app.controllers import admin, auth, training, users, venues, websocket
from app.core.config import settings
from app.core.exceptions import AppError
from app.services import fitness_service
from database import init_db

logger = logging.getLogger("fitness.api")
BASE_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(application: FastAPI):
    init_db()
    application.state.coordinator = AgentCoordinator()
    fitness_service.coordinator = application.state.coordinator
    yield


app = FastAPI(
    title="虚拟游戏化全民健身智能辅助系统 API",
    version="2.0.0",
    description="FastAPI、Pydantic、JWT 与实时训练 WebSocket 接口。",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or str(uuid4())
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Process-Time"] = f"{time.perf_counter() - started:.6f}"
    logger.info("%s %s %s %.3fms", request.method, request.url.path, response.status_code,
                (time.perf_counter() - started) * 1000)
    return response


def error_body(request: Request, code: str, message: str, details=None):
    return {
        "code": code,
        "message": message,
        "details": details or [],
        "request_id": getattr(request.state, "request_id", str(uuid4())),
    }


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(error_body(request, exc.code, exc.message, exc.details), exc.status_code, headers=headers)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    details = [
        {"field": ".".join(str(part) for part in item["loc"]), "message": item["msg"], "type": item["type"]}
        for item in exc.errors()
    ]
    return JSONResponse(error_body(request, "VALIDATION_ERROR", "请求参数不合法", details), 422)


@app.exception_handler(Exception)
async def unknown_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled request error", exc_info=exc)
    return JSONResponse(error_body(request, "INTERNAL_ERROR", "服务器内部错误"), 500)


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(training.router)
app.include_router(venues.router)
app.include_router(admin.router)
app.include_router(websocket.router)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(BASE_DIR / "templates" / "index.html")
