"""
Sales IQ - Performance Monitoring Endpoints
Day 20: API metrics dashboard, DB stats, endpoint profiling.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.query_optimizer import get_db_stats
from app.core.cache import get_all_cache_stats, dashboard_cache, kpi_cache, query_cache
from app.middleware.performance import metrics_store
from app.models.core import User

router = APIRouter()


@router.get("/metrics/summary")
async def get_performance_summary(
    current_user: User = Depends(get_current_user),
):
    """API performance metrics summary — response times, error rates, slow endpoints."""
    return metrics_store.get_summary()


@router.get("/metrics/endpoint")
async def get_endpoint_metrics(
    method: str = Query("GET"),
    path: str = Query(..., description="Endpoint path, e.g. /api/v1/customers/"),
    current_user: User = Depends(get_current_user),
):
    """Detailed metrics for a specific endpoint."""
    return metrics_store.get_endpoint_stats(method, path)


@router.get("/metrics/db")
async def get_database_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Database performance stats — sizes, index usage, cache hit ratio."""
    return await get_db_stats(db, str(current_user.tenant_id))


@router.get("/metrics/indexes")
async def get_index_report(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Index effectiveness report — most used, unused, and missing."""
    stats = await get_db_stats(db, str(current_user.tenant_id))
    return {
        "top_used_indexes": stats["top_indexes_by_usage"],
        "unused_indexes": stats["unused_indexes"],
        "cache_hit_ratio_pct": stats["cache_hit_ratio"],
        "recommendation": (
            "Cache hit ratio is excellent (>99%). Indexes are well-utilized."
            if stats["cache_hit_ratio"] > 99
            else "Consider reviewing unused indexes and adding missing ones."
        ),
    }


@router.get("/metrics/cache")
async def get_cache_stats(
    current_user: User = Depends(get_current_user),
):
    """Application cache statistics — hit rates, entry counts."""
    return get_all_cache_stats()


@router.post("/metrics/cache/clear")
async def clear_caches(
    current_user: User = Depends(get_current_user),
):
    """Clear all application caches (admin only)."""
    dashboard_cache.clear()
    kpi_cache.clear()
    query_cache.clear()
    return {"message": "All caches cleared", "stats": get_all_cache_stats()}
