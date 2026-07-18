import json
import random
import time
from collections.abc import Callable
from contextlib import suppress
from typing import TypeVar

from app.core.config import settings

T = TypeVar("T")
_client = None


def redis_client():
    global _client
    if _client is not None:
        return _client
    try:
        from redis import Redis

        _client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _client.ping()
    except Exception:
        _client = False
    return _client or None


def _ttl(ttl: int | None = None) -> int:
    base = ttl or settings.cache_default_ttl
    return max(1, base + random.randint(0, max(1, base // 10)))


def cache_set(key: str, value, ttl: int | None = None) -> None:
    client = redis_client()
    if not client:
        return
    with suppress(Exception):
        client.setex(key, _ttl(ttl), json.dumps(value, ensure_ascii=False, default=str))


def cache_get(key: str):
    client = redis_client()
    if not client:
        return None
    with suppress(Exception):
        raw = client.get(key)
        return json.loads(raw) if raw else None
    return None


def cache_delete(*keys: str) -> None:
    client = redis_client()
    if not client or not keys:
        return
    with suppress(Exception):
        client.delete(*keys)


def cache_get_or_set(key: str, loader: Callable[[], T], ttl: int | None = None) -> T:
    cached = cache_get(key)
    if cached is not None:
        return cached

    client = redis_client()
    lock_key = f"{key}:lock"
    if client:
        with suppress(Exception):
            if client.set(lock_key, "1", nx=True, ex=settings.cache_lock_ttl):
                value = loader()
                cache_set(key, value, ttl)
                client.delete(lock_key)
                return value
            for _ in range(5):
                time.sleep(0.05)
                cached = cache_get(key)
                if cached is not None:
                    return cached

    value = loader()
    cache_set(key, value, ttl)
    return value
