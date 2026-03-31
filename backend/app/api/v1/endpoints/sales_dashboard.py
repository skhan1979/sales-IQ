"""
Sales IQ - Sales Dashboard Endpoints
Day 16: Sales intelligence, pipeline, churn watchlist, reorder alerts, revenue segmentation.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.core import User
from app.services.sales_dashboard import sales_dashboard
from app.schemas.sales_dashboard import (
    PipelineSummaryResponse,
    ReorderAlertListResponse,
    ChurnWatchlistResponse,
    RevenueBySegmentResponse,
    GrowthOpportunityListResponse,
    SalesDashboardResponse,
)

router = APIRouter()


@router.get("/summary", response_model=SalesDashboardResponse)
async def get_sales_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sales VP dashboard summary with all key metrics."""
    result = await sales_dashboard.get_dashboard_summary(db, current_user.tenant_id)
    return SalesDashboardResponse(**result)


@router.get("/pipeline", response_model=PipelineSummaryResponse)
async def get_pipeline_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sales pipeline summary from invoice lifecycle stages."""
    result = await sales_dashboard.get_pipeline_summary(db, current_user.tenant_id)
    return PipelineSummaryResponse(**result)


@router.get("/reorder-alerts", response_model=ReorderAlertListResponse)
async def get_reorder_alerts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Customers overdue for reordering with alert levels."""
    result = await sales_dashboard.get_reorder_alerts(db, current_user.tenant_id)
    return ReorderAlertListResponse(**result)


@router.get("/churn-watchlist", response_model=ChurnWatchlistResponse)
async def get_churn_watchlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Customers ranked by churn probability with actionable insights."""
    result = await sales_dashboard.get_churn_watchlist(db, current_user.tenant_id)
    return ChurnWatchlistResponse(**result)


@router.get("/revenue-by-segment", response_model=RevenueBySegmentResponse)
async def get_revenue_by_segment(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revenue analytics broken down by customer segment."""
    result = await sales_dashboard.get_revenue_by_segment(db, current_user.tenant_id)
    return RevenueBySegmentResponse(**result)


@router.get("/growth-opportunities", response_model=GrowthOpportunityListResponse)
async def get_growth_opportunities(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Identify customers with upsell, reactivation, and expansion potential."""
    result = await sales_dashboard.get_growth_opportunities(db, current_user.tenant_id, limit)
    return GrowthOpportunityListResponse(**result)
