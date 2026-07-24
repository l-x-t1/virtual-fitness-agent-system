"""
FeatureFlag 中间件 — 拦截请求，根据 JWT + 百分比放量决定是否放行

工作流程:
  1. 检查请求路径是否在受保护的特性路由列表中
  2. 从 Authorization header 提取 JWT，解码出 user_id
  3. 调用 FeatureFlagService.is_enabled(feature_name, user_id)
  4. 放量 → 正常处理请求；未放量 → 返回 404（假装接口不存在）

配置方式（在 main.py 中注册）:
    FeatureFlagMiddleware(
        app,
        protected_routes={
            "/api/graph/search": "graph_search",
            "/api/ai/chat": "ai_coach",
        },
    )
"""

from __future__ import annotations

import logging
import re

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.feature_flags.service import get_feature_flag_service

logger = logging.getLogger("fitness.feature_flags")


class FeatureFlagMiddleware(BaseHTTPMiddleware):
    """
    特性开关中间件

    Args:
        app: FastAPI 实例
        protected_routes: {路径前缀: feature_name} 映射
            例如: {"/api/graph/search": "graph_search"}
        exclude_paths: 始终放行的路径列表
    """

    def __init__(
        self,
        app: ASGIApp,
        protected_routes: dict[str, str] | None = None,
        exclude_paths: list[str] | None = None,
    ):
        super().__init__(app)
        self.protected = protected_routes or {}
        self.exclude = exclude_paths or [
            "/api/login",
            "/api/register",
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/api/admin",
        ]

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # 白名单直接放行
        if any(path.startswith(ep) for ep in self.exclude):
            return await call_next(request)

        # 检查是否匹配受保护的路由
        feature_name = self._match(path)
        if feature_name is None:
            return await call_next(request)

        # 提取 user_id
        user_id = self._extract_user_id(request)
        if user_id is None:
            # 无法识别用户 → 放行（交给 JWT 中间件去拦截）
            return await call_next(request)

        # 判定是否放量
        ff = get_feature_flag_service()
        if ff.is_enabled(feature_name, user_id):
            logger.debug("FeatureFlag [%s] ENABLED for user %s", feature_name, user_id)
            return await call_next(request)

        logger.info("FeatureFlag [%s] BLOCKED for user %s", feature_name, user_id)
        return Response(
            content='{"code":"FEATURE_DISABLED","message":"该功能暂未对您开放"}',
            status_code=404,
            media_type="application/json",
        )

    def _match(self, path: str) -> str | None:
        """匹配路径，返回对应的 feature_name"""
        for prefix, name in self.protected.items():
            if path.startswith(prefix):
                return name
        return None

    def _extract_user_id(self, request: Request) -> int | None:
        """
        从请求中提取 user_id

        优先级:
          1. JWT Token (Authorization: Bearer xxx) → 解码 sub 字段
          2. 请求头 X-User-Id

        注意: 只解码不验证过期时间（鉴权由 get_current_user 负责）
        """
        # 方式 1: JWT
        auth = request.headers.get("Authorization", "")
        match = re.match(r'^[Bb]earer\s+(.+)$', auth)
        if match:
            try:
                from app.core.security import decode_access_token
                payload = decode_access_token(match.group(1))
                return int(payload["sub"])
            except Exception:
                pass

        # 方式 2: 显式 Header
        uid = request.headers.get("X-User-Id")
        if uid and uid.isdigit():
            return int(uid)

        return None
