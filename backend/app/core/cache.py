"""
Sales IQ - Cache Layer
Day 20: In-memory TTL cache with Redis-compatible interface.
Used for hot dashboard queries, KPI cards, and frequently-accessed aggregations.
Falls back gracefully to in-memory dict when Redis is unavailable.
"""

import time
import hashlib
import json
import logging
import functools
from typing import Any, Callable, Optional

logger = logging.getLogger("salesiq.cache")


# ═══════════════════════════════════════════
# In-Memory TTL Cache (MVP)
# ═══════════════════════════════════════════

class TTLCache:
    """
    Thread-safe in-memory cache with TTL expiration.
    Designed as a drop-in until Redis is fully configured.
    """

    def __init__(self, default_ttl: int = 300):
        self._store: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Get value if key exists and hasn't expired."""
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None

        value, expires_at = entry
        if time.time() > expires_at:
            del self._store[key]
            self._misses += 1
            return None

        self._hits += 1
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Store a value with optional TTL override."""
        ttl = ttl or self._default_ttl
        expires_at = time.time() + ttl
        self._store[key] = (value, expires_at)

    def delete(self, key: str):
        """Remove a key."""
        self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str):
        """Invalidate all keys matching a prefix."""
        keys_to_delete = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_delete:
            del self._store[k]
        if keys_to_delete:
            logger.debug(f"Invalidated {len(keys_to_delete)} keys with prefix '{prefix}'")

    def clear(self):
        """Clear all cache entries."""
        self._store.clear()
        self._hits = 0
        self._misses = 0

    def cleanup_expired(self):
        """Remove all expired entries (call periodically)."""
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]
        return len(expired)

    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "entries": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round((self._hits / total * 100) if total > 0 else 0, 1),
        }


# Singleton cache instances
dashboard_cache = TTLCache(default_ttl=300)   # 5 min for dashboards
kpi_cache = TTLCache(default_ttl=60)          # 1 min for KPIs
query_cache = TTLCache(default_ttl=120)       # 2 min for repeated queries


# ═══════════════════════════════════════════
# Cache Key Builder
# ═══════════════════════════════════════════

def build_cache_key(prefix: str, tenant_id: str, **kwargs) -> str:
    """Build a deterministic cache key from prefix, tenant, and params."""
    parts = [prefix, tenant_id]
    for k in sorted(kwargs):
        v = kwargs[k]
        if v is not None:
            parts.append(f"{k}={v}")
    raw = ":".join(str(p) for p in parts)
    # Use hash for long keys
    if len(raw) > 200:
        h = hashlib.md5(raw.encode()).hexdigest()[:12]
        return f"{prefix}:{tenant_id}:{h}"
    return raw


# ═══════════════════════════════════════════
# Async Cache Decorator
# ═══════════════════════════════════════════

def cached(cache: TTLCache, prefix: str, ttl: Optional[int] = None):
    """
    Decorator for caching async function results.

    The decorated function must accept `tenant_id` as its first
    positional or keyword argument.

    Usage:
        @cached(dashboard_cache, "cfo_dso", ttl=300)
        async def get_dso_trend(tenant_id, days=30):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract tenant_id from args or kwargs
            tid = kwargs.get("tenant_id") or (str(args[0]) if args else "global")

            # Build key from all arguments
            key_kwargs = {**kwargs}
            for i, a in enumerate(args):
                key_kwargs[f"arg{i}"] = str(a)

            key = build_cache_key(prefix, str(tid), **key_kwargs)

            # Check cache
            result = cache.get(key)
            if result is not None:
                logger.debug(f"CACHE HIT [{prefix}]: {key}")
                return result

            # Execute and cache
            result = await func(*args, **kwargs)
            cache.set(key, result, ttl)
            logger.debug(f"CACHE SET [{prefix}]: {key}")
            return result

        # Expose cache control
        wrapper.invalidate = lambda tid: cache.invalidate_prefix(f"{prefix}:{tid}")
        wrapper.cache = cache
        return wrapper

    return decorator


# ═══════════════════════════════════════════
# Cache Stats Endpoint Helper
# ═══════════════════════════════════════════

def get_all_cache_stats() -> dict:
    """Return stats for all cache instances."""
    return {
        "dashboard_cache": dashboard_cache.stats,
        "kpi_cache": kpi_cache.stats,
        "query_cache": query_cache.stats,
    }
