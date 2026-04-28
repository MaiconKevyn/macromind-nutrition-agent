from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from src.core.config import get_settings
from src.core.exceptions import RateLimitError


@dataclass
class _Bucket:
    hits: deque[datetime] = field(default_factory=deque)


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[int, _Bucket] = {}

    def check(self, user_id: int) -> None:
        now = datetime.now(UTC)
        window_start = now - timedelta(minutes=1)
        limit = get_settings().rate_limit_per_minute

        bucket = self._buckets.setdefault(user_id, _Bucket())
        while bucket.hits and bucket.hits[0] < window_start:
            bucket.hits.popleft()

        if len(bucket.hits) >= limit:
            raise RateLimitError(f"Limite de {limit} requisições por minuto excedido")

        bucket.hits.append(now)


_limiter = InMemoryRateLimiter()


def enforce_rate_limit(user_id: int) -> None:
    _limiter.check(user_id)
