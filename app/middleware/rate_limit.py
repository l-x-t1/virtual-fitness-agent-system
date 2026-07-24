"""
接口限流中间件 — 基于内存滑动窗口

使用方式（在 app/main.py 中注册）:
    from app.middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware, redis_url=settings.redis_url,
                       default_limit=60, default_window=60)
"""

from __future__ import annotations

import time
import threading
from collections import defaultdict
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class SlidingWindow:
    """滑动窗口计数器"""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max = max_requests
        self.window = window_seconds
        self.requests: list[float] = []
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.time()
        with self._lock:
            # 清理过期记录
            cutoff = now - self.window
            self.requests = [t for t in self.requests if t > cutoff]
            if len(self.requests) < self.max:
                self.requests.append(now)
                return True
            return False

    @property
    def remaining(self) -> int:
        return max(0, self.max - len(self.requests))


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    基于 IP 的内存限流中间件

    参数:
        redis_url: Redis 连接地址（保留，未来可升级为 Redis 分布式限流）
        default_limit: 默认每窗口最大请求数
        default_window: 默认窗口秒数
        exempt_paths: 不限流的路径列表
    """

    def __init__(
        self,
        app: ASGIApp,
        redis_url: str = "",
        default_limit: int = 60,
        default_window: int = 60,
        exempt_paths: list[str] | None = None,
    ):
        super().__init__(app)
        self.default_limit = default_limit
        self.default_window = default_window
        self.exempt_paths = exempt_paths or ["/health", "/openapi.json", "/docs", "/redoc"]
        self._windows: dict[str, SlidingWindow] = {}
        self._cleanup_interval = 120
        self._last_cleanup = time.time()

    async def dispatch(self, request: Request, call_next) -> Response:
        # 跳过白名单路径
        path = request.url.path
        if any(path.startswith(ep) for ep in self.exempt_paths):
            return await call_next(request)

        # 获取客户端 IP
        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.headers.get("X-Real-IP", "")
            or (request.client.host if request.client else "unknown")
        )

        # 获取或创建窗口
        key = f"rate:{client_ip}"
        window = self._get_window(key)

        if not window.allow():
            return Response(
                content='{"code":"RATE_LIMITED","message":"请求过于频繁，请稍后再试"}',
                status_code=429,
                media_type="application/json",
                headers={
                    "Retry-After": str(self.default_window),
                    "X-RateLimit-Limit": str(window.max),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(window.max)
        response.headers["X-RateLimit-Remaining"] = str(window.remaining)
        return response

    def _get_window(self, key: str) -> SlidingWindow:
        # 定期清理长时间未访问的 IP
        now = time.time()
        if now - self._last_cleanup > self._cleanup_interval:
            self._cleanup(now)

        if key not in self._windows:
            self._windows[key] = SlidingWindow(self.default_limit, self.default_window)
        return self._windows[key]

    def _cleanup(self, now: float):
        stale = [k for k, w in self._windows.items()
                 if not w.requests or now - max(w.requests) > 600]
        for k in stale:
            del self._windows[k]
        self._last_cleanup = now
