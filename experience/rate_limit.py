"""Redis 优先、内存降级的固定窗口限流。"""
from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


class RateLimiter:
    def __init__(self, redis_client: Any = None, *, prefix: str = "experience:rate"):
        self._redis = redis_client
        self._prefix = prefix
        self._memory: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _safe_identifier(identifier: str) -> str:
        return hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:24]

    def _key(self, scope: str, identifier: str, window_seconds: int) -> str:
        window = int(time.time()) // window_seconds
        return (
            f"{self._prefix}:{scope}:{self._safe_identifier(identifier)}:"
            f"{window_seconds}:{window}"
        )

    def hit(
        self,
        scope: str,
        identifier: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        if limit < 1 or window_seconds < 1:
            raise ValueError("限流参数必须为正整数。")
        key = self._key(scope, identifier, window_seconds)
        if self._redis is not None:
            pipeline = self._redis.pipeline()
            pipeline.incr(key)
            pipeline.ttl(key)
            count, ttl = pipeline.execute()
            if count == 1 or ttl < 0:
                self._redis.expire(key, window_seconds)
                ttl = window_seconds
        else:
            now = time.monotonic()
            with self._lock:
                count, expires_at = self._memory.get(key, (0, now + window_seconds))
                if expires_at <= now:
                    count, expires_at = 0, now + window_seconds
                count += 1
                self._memory[key] = (count, expires_at)
                ttl = max(1, int(expires_at - now))
                if len(self._memory) > 4096:
                    self._memory = {
                        item_key: item
                        for item_key, item in self._memory.items()
                        if item[1] > now
                    }
        return RateLimitDecision(
            allowed=count <= limit,
            limit=limit,
            remaining=max(0, limit - count),
            retry_after=max(1, int(ttl)),
        )


def client_identifier(host: Optional[str], forwarded_for: Optional[str] = None) -> str:
    """只保留限流所需的网络标识，存储层仅保存其摘要。"""
    if forwarded_for:
        first = forwarded_for.split(",", 1)[0].strip()
        if first:
            return first
    return (host or "unknown").strip() or "unknown"
