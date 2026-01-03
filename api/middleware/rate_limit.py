"""Rate limiting middleware for FastAPI."""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from typing import Final

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from config.settings import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token bucket rate limiter per IP address."""

    def __init__(
        self,
        app: Callable,
        *,
        requests_per_minute: int | None = None,
        burst: int = 10,
    ) -> None:
        super().__init__(app)
        self.rate: Final[int] = requests_per_minute or settings.rate_limit_per_minute
        self.burst: Final[int] = burst
        self._buckets: dict[str, tuple[float, int]] = defaultdict(
            lambda: (time.monotonic(), self.burst)
        )

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP, respecting X-Forwarded-For behind proxy."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take first IP (original client)
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in {"/health", "/healthz", "/ready"}:
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        now = time.monotonic()

        # Token bucket algorithm
        last_time, tokens = self._buckets[client_ip]
        elapsed = now - last_time

        # Refill tokens based on elapsed time
        tokens = min(self.burst, tokens + int(elapsed * self.rate / 60))

        if tokens < 1:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Slow down."},
                headers={"Retry-After": str(60 // self.rate)},
            )

        # Consume a token
        self._buckets[client_ip] = (now, tokens - 1)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.rate)
        response.headers["X-RateLimit-Remaining"] = str(tokens - 1)

        return response

