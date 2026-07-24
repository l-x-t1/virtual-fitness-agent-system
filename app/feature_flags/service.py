"""
FeatureFlag 服务 — 基于百分比取模的特性开关

核心接口:
    is_enabled(feature_name: str, user_id: int) -> bool

存储:
    优先 Redis，不可用时自动降级到内存字典

配置方式:
    1. .env 文件:  FEATURE_前缀的变量
       FEATURE_NEW_RECOMMEND=30   # 30% 用户放量
       FEATURE_AI_COACH=0         # 全量关闭
       FEATURE_GRAPH_SEARCH=100   # 全量开放

    2. 运行时动态修改:  POST /api/admin/features
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.core.config import settings

logger = logging.getLogger("fitness.feature_flags")

# ============================================================
# 内存存储（Redis 不可用时的降级方案）
# ============================================================

class _MemoryStore:
    def __init__(self):
        self._data: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def set(self, key: str, value: str):
        with self._lock:
            self._data[key] = value

    def get_all(self, prefix: str) -> dict[str, str]:
        return {k: v for k, v in self._data.items() if k.startswith(prefix)}


# ============================================================
# FeatureFlag 服务
# ============================================================

class FeatureFlagService:
    """
    特性开关服务

    判定逻辑:
        user_id % 100 < percentage  →  放量
        例: percentage=30, user_id=1007
            1007 % 100 = 7 < 30  →  True (放量)
    """

    KEY_PREFIX = "feature:"

    def __init__(self):
        self._redis = self._connect_redis()
        self._memory = _MemoryStore()

    # ---- Redis 连接 ----

    def _connect_redis(self):
        try:
            from redis import Redis
            client = Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
            return client
        except Exception:
            logger.info("FeatureFlag: Redis unavailable, using in-memory storage")
            return None

    # ---- 核心接口 ----

    def is_enabled(self, feature_name: str, user_id: int) -> bool:
        """
        检查特性是否对指定用户开放

        Args:
            feature_name: 特性名称，如 "new_recommend"
            user_id: 用户 ID

        Returns:
            True = 放量给该用户, False = 不放量
        """
        percentage = self.get_percentage(feature_name)
        return user_id % 100 < percentage

    def get_percentage(self, feature_name: str) -> int:
        """
        获取特性放量百分比 (0-100)

        读取优先级: Redis > 内存 > .env > 默认值 0
        """
        key = self.KEY_PREFIX + feature_name

        # 1. Redis
        if self._redis:
            try:
                value = self._redis.get(key)
                if value is not None:
                    return int(value)
            except Exception:
                pass

        # 2. 内存
        mem_value = self._memory.get(key)
        if mem_value is not None:
            return int(mem_value)

        # 3. .env  (FEATURE_NEW_RECOMMEND=30)
        env_value = self._env_percentage(feature_name)
        if env_value is not None:
            # 缓存到内存
            self._memory.set(key, str(env_value))
            return env_value

        # 4. 默认关闭
        return 0

    def set_percentage(self, feature_name: str, percentage: int):
        """
        运行时修改放量百分比

        Args:
            feature_name: 特性名称
            percentage: 0-100 的百分比
        """
        key = self.KEY_PREFIX + feature_name
        val = str(max(0, min(100, percentage)))

        if self._redis:
            try:
                self._redis.set(key, val)
            except Exception:
                pass

        self._memory.set(key, val)
        logger.info("FeatureFlag [%s] set to %s%%", feature_name, val)

    def list_all(self) -> dict[str, dict]:
        """列出所有特性开关及其配置"""
        result: dict[str, dict] = {}

        # 从 .env 加载所有 FEATURE_ 开头的变量作为基础
        env_features = self._env_all()
        for name, pct in env_features.items():
            result[name] = {
                "percentage": pct,
                "source": "env",
                "enabled_for_user_25": self.is_enabled(name, 25),
                "enabled_for_user_50": self.is_enabled(name, 50),
                "enabled_for_user_75": self.is_enabled(name, 75),
            }

        # 从内存/Redis 覆盖
        if self._redis:
            try:
                keys = self._redis.keys(self.KEY_PREFIX + "*")
                for key in keys:
                    name = key.replace(self.KEY_PREFIX, "")
                    result[name] = {
                        "percentage": int(self._redis.get(key)),
                        "source": "redis",
                        "enabled_for_user_25": self.is_enabled(name, 25),
                        "enabled_for_user_50": self.is_enabled(name, 50),
                        "enabled_for_user_75": self.is_enabled(name, 75),
                    }
            except Exception:
                pass

        return result

    # ---- 环境变量 ----

    def _env_percentage(self, feature_name: str) -> int | None:
        import os
        env_key = f"FEATURE_{feature_name.upper()}"
        val = os.getenv(env_key)
        if val is not None and val.strip():
            try:
                return int(val.strip())
            except ValueError:
                return None
        return None

    def _env_all(self) -> dict[str, int]:
        import os
        result = {}
        for k, v in os.environ.items():
            if k.startswith("FEATURE_") and v.strip():
                try:
                    name = k.replace("FEATURE_", "").lower()
                    result[name] = int(v.strip())
                except ValueError:
                    pass
        return result


# ============================================================
# 全局单例
# ============================================================

_service: FeatureFlagService | None = None


def get_feature_flag_service() -> FeatureFlagService:
    global _service
    if _service is None:
        _service = FeatureFlagService()
    return _service
