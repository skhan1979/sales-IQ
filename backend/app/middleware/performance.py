"""
Sales IQ - Performance Monitoring Middleware & Metrics
Day 20: Response time tracking, slow endpoint detection, metrics collection.
"""

import time
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("salesiq.perf")


# ═══════════════════════════════════════════
# In-Memory Metrics Store (MVP — swap for
# Prometheus/StatsD in production)
# ═══════════════════════════════════════════

class MetricsStore:
    """Thread-safe in-memory metrics collection."""

    def __init__(self, max_history: int = 1000):
        self._lock = Lock()
        self._max_history = max_history

        # Per-endpoint stats
        self._endpoint_times: dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self._endpoint_counts: dict[str, int] = defaultdict(int)
        self._endpoint_errors: dict[str, int] = defaultdict(int)

        # Slow queries log
        self._slow_requests: deque = deque(maxlen=100)

        # Global counters
        self._total_requests = 0
        self._total_errors = 0
        self._start_time = time.time()

    def record(self, method: str, path: str, status_code: int, duration_ms: float):
        """Record a request metric."""
        key = f"{method} {path}"
        with self._lock:
            self._endpoint_times[key].append(duration_ms)
            self._endpoint_counts[key] += 1
            self._total_requests += 1

            if status_code >= 500:
                self._endpoint_errors[key] += 1
                self._total_errors += 1

            if duration_ms > 500:
                self._slow_requests.append({
                    "endpoint": key,
                    "duration_ms": round(duration_ms, 1),
                    "status": status_code,
                    "at": datetime.now(timezone.utc).isoformat(),
                })

    def get_summary(self) -> dict:
        """Return performance summary."""
        with self._lock:
            uptime = int(time.time() - self._start_time)
            endpoints = []

            for key in sorted(self._endpoint_counts, key=lambda k: self._endpoint_counts[k], reverse=True):
                times = list(self._endpoint_times[key])
                if not times:
                    continue

                avg_ms = sum(times) / len(times)
                p50 = sorted(times)[len(times) // 2]
                p95 = sorted(times)[int(len(times) * 0.95)] if len(times) > 1 else times[0]
                p99 = sorted(times)[int(len(times) * 0.99)] if len(times) > 1 else times[0]
                max_ms = max(times)

                endpoints.append({
                    "endpoint": key,
                    "count": self._endpoint_counts[key],
                    "errors": self._endpoint_errors.get(key, 0),
                    "avg_ms": round(avg_ms, 1),
                    "p50_ms": round(p50, 1),
                    "p95_ms": round(p95, 1),
                    "p99_ms": round(p99, 1),
                    "max_ms": round(max_ms, 1),
                })

            return {
                "uptime_seconds": uptime,
                "total_requests": self._total_requests,
                "total_errors": self._total_errors,
                "error_rate_pct": round(
                    (self._total_errors / self._total_requests * 100) if self._total_requests > 0 else 0, 2
                ),
                "endpoints": endpoints[:30],  # Top 30
                "slow_requests": list(self._slow_requests)[-20:],  # Last 20 slow
            }

    def get_endpoint_stats(self, method: str, path: str) -> dict:
        """Get stats for a specific endpoint."""
        key = f"{method} {path}"
        with self._lock:
            times = list(self._endpoint_times.get(key, []))
            if not times:
                return {"endpoint": key, "count": 0, "message": "No data"}

            return {
                "endpoint": key,
                "count": self._endpoint_counts[key],
                "errors": self._endpoint_errors.get(key, 0),
                "avg_ms": round(sum(times) / len(times), 1),
                "min_ms": round(min(times), 1),
                "max_ms": round(max(times), 1),
                "recent_10": [round(t, 1) for t in times[-10:]],
            }


# Singleton
metrics_store = MetricsStore()


# ═══════════════════════════════════════════
# Middleware
# ═══════════════════════════════════════════

class PerformanceMiddleware(BaseHTTPMiddleware):
    """
    Tracks response time per endpoint.
    Logs slow requests (>500ms).
    Records metrics in MetricsStore.
    """

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000

        # Normalize path (strip query params, collapse IDs)
        path = request.url.path
        method = request.method

        # Record metric
        metrics_store.record(method, path, response.status_code, duration_ms)

        # Log slow requests
        if duration_ms > 500:
            logger.warning(
                f"SLOW [{method} {path}] {duration_ms:.0f}ms "
                f"status={response.status_code}"
            )

        # Add header
        response.headers["X-Response-Time"] = f"{duration_ms:.0f}ms"

        return response
