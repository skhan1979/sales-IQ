"""
Sales IQ - Query Optimization Utilities
Day 20: Column selection helpers, pagination optimizer, query timing,
        eager/lazy loading guidance, and EXPLAIN ANALYZE wrapper.
"""

import time
import logging
from math import ceil
from typing import Any, Optional, Sequence

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

logger = logging.getLogger("salesiq.query")


# ═══════════════════════════════════════════
# Pagination Helper
# ═══════════════════════════════════════════

class PaginatedResult:
    """Standardized paginated query result."""

    __slots__ = ("items", "total", "page", "page_size", "total_pages", "has_next", "has_previous")

    def __init__(self, items: list, total: int, page: int, page_size: int):
        self.items = items
        self.total = total
        self.page = page
        self.page_size = page_size
        self.total_pages = ceil(total / page_size) if page_size > 0 else 0
        self.has_next = page < self.total_pages
        self.has_previous = page > 1

    def to_dict(self) -> dict:
        return {
            "items": self.items,
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages,
            "has_next": self.has_next,
            "has_previous": self.has_previous,
        }


async def paginated_query(
    db: AsyncSession,
    query,
    page: int = 1,
    page_size: int = 20,
    count_query=None,
) -> PaginatedResult:
    """
    Execute a paginated query efficiently.

    Uses separate count query for total, then fetches the page.
    Optionally accepts a pre-built count query for complex filters.
    """
    # Count total
    if count_query is not None:
        total = (await db.execute(count_query)).scalar() or 0
    else:
        count_q = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_q)).scalar() or 0

    # Fetch page
    offset = (page - 1) * page_size
    paged_query = query.offset(offset).limit(page_size)
    result = await db.execute(paged_query)
    items = list(result.scalars().all())

    return PaginatedResult(items=items, total=total, page=page, page_size=page_size)


# ═══════════════════════════════════════════
# Column Selection (Lightweight Queries)
# ═══════════════════════════════════════════

def select_columns(model, columns: Sequence[str]):
    """
    Build a SELECT with only the specified columns — avoids loading
    heavy JSONB/Text fields when they aren't needed.

    Usage:
        query = select_columns(Customer, ["id", "name", "risk_score", "status"])
    """
    col_objs = [getattr(model, c) for c in columns if hasattr(model, c)]
    return select(model).options(load_only(*[getattr(model, c) for c in columns if hasattr(model, c)]))


# ═══════════════════════════════════════════
# Query Timing Decorator
# ═══════════════════════════════════════════

class QueryTimer:
    """
    Context manager that logs slow queries.

    Usage:
        async with QueryTimer("customer_list"):
            result = await db.execute(query)
    """

    def __init__(self, label: str, slow_threshold_ms: int = 200):
        self.label = label
        self.slow_threshold_ms = slow_threshold_ms
        self._start: float = 0

    async def __aenter__(self):
        self._start = time.perf_counter()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        elapsed_ms = (time.perf_counter() - self._start) * 1000
        if elapsed_ms > self.slow_threshold_ms:
            logger.warning(f"SLOW QUERY [{self.label}]: {elapsed_ms:.1f}ms (threshold: {self.slow_threshold_ms}ms)")
        else:
            logger.debug(f"Query [{self.label}]: {elapsed_ms:.1f}ms")
        return False

    @property
    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000


# ═══════════════════════════════════════════
# EXPLAIN ANALYZE Wrapper (Dev/Debug Only)
# ═══════════════════════════════════════════

async def explain_query(db: AsyncSession, query_text: str, params: dict = None) -> list[str]:
    """
    Run EXPLAIN ANALYZE on a raw SQL query. Returns the plan lines.
    Use only in development/debugging — never in production endpoints.
    """
    explain_sql = f"EXPLAIN ANALYZE {query_text}"
    result = await db.execute(text(explain_sql), params or {})
    return [row[0] for row in result.fetchall()]


# ═══════════════════════════════════════════
# Database Stats Snapshot
# ═══════════════════════════════════════════

async def get_db_stats(db: AsyncSession, tenant_id: str) -> dict:
    """
    Collect database size and table statistics for performance monitoring.
    """
    # Total database size
    db_size_q = await db.execute(text(
        "SELECT pg_size_pretty(pg_database_size(current_database()))"
    ))
    db_size = db_size_q.scalar() or "unknown"

    # Table row counts (approximate from pg_stat)
    table_stats_q = await db.execute(text("""
        SELECT relname AS table_name,
               n_live_tup AS row_estimate,
               pg_size_pretty(pg_total_relation_size(quote_ident(relname))) AS total_size
        FROM pg_stat_user_tables
        WHERE schemaname = 'public'
        ORDER BY n_live_tup DESC
        LIMIT 20
    """))
    tables = [
        {"table": row[0], "rows_estimate": row[1], "size": row[2]}
        for row in table_stats_q.fetchall()
    ]

    # Index usage stats
    idx_stats_q = await db.execute(text("""
        SELECT indexrelname AS index_name,
               relname AS table_name,
               idx_scan AS scans,
               idx_tup_read AS tuples_read,
               pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
        FROM pg_stat_user_indexes
        WHERE schemaname = 'public'
        ORDER BY idx_scan DESC
        LIMIT 20
    """))
    indexes = [
        {
            "index": row[0], "table": row[1],
            "scans": row[2], "tuples_read": row[3], "size": row[4],
        }
        for row in idx_stats_q.fetchall()
    ]

    # Unused indexes (0 scans = wasted space)
    unused_q = await db.execute(text("""
        SELECT indexrelname, relname,
               pg_size_pretty(pg_relation_size(indexrelid))
        FROM pg_stat_user_indexes
        WHERE idx_scan = 0 AND schemaname = 'public'
        ORDER BY pg_relation_size(indexrelid) DESC
        LIMIT 10
    """))
    unused_indexes = [
        {"index": row[0], "table": row[1], "size": row[2]}
        for row in unused_q.fetchall()
    ]

    # Cache hit ratio
    cache_q = await db.execute(text("""
        SELECT
            sum(heap_blks_hit) / NULLIF(sum(heap_blks_hit) + sum(heap_blks_read), 0) AS ratio
        FROM pg_statio_user_tables
    """))
    cache_hit_ratio = float(cache_q.scalar() or 0)

    return {
        "database_size": db_size,
        "tables": tables,
        "top_indexes_by_usage": indexes,
        "unused_indexes": unused_indexes,
        "cache_hit_ratio": round(cache_hit_ratio * 100, 2),
    }
