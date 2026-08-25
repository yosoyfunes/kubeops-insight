import json
from datetime import UTC, datetime, timedelta
from typing import Any


class AiResponseCache:
    def __init__(self) -> None:
        self._items: dict[str, tuple[datetime, dict[str, Any]]] = {}

    def get(self, key: str, ttl_seconds: int) -> dict[str, Any] | None:
        cached = self._items.get(key)
        if not cached:
            return None
        created_at, value = cached
        if datetime.now(UTC) - created_at > timedelta(seconds=ttl_seconds):
            self._items.pop(key, None)
            return None
        return {**value, "cached": True}

    def set(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        self._items[key] = (datetime.now(UTC), value)
        return {**value, "cached": False}

    def clear(self) -> None:
        self._items.clear()


def cache_key(kind: str, payload: dict[str, Any]) -> str:
    return f"{kind}:{json.dumps(payload, sort_keys=True, default=str)}"


ai_response_cache = AiResponseCache()
