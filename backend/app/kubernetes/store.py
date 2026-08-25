from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

from app.config.settings import get_settings

_cache: dict[str, tuple[float, Any]] = {}


async def get_cached[T](key: str, loader: Callable[[], Awaitable[T]]) -> T:
    ttl = get_settings().cache_ttl_seconds
    now = monotonic()
    cached = _cache.get(key)
    if cached and now - cached[0] < ttl:
        return cached[1]

    value = await loader()
    _cache[key] = (now, value)
    return value


def clear_cache() -> None:
    _cache.clear()


class ClusterStateStore:
    async def get[T](self, key: str, loader: Callable[[], Awaitable[T]]) -> T:
        return await get_cached(key, loader)

    def clear(self) -> None:
        clear_cache()


cluster_state_store = ClusterStateStore()
