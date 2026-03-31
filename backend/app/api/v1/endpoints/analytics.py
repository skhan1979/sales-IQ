"""
Sales IQ - Analytics & Reporting Endpoints
Day 11: KPI dashboard, trend analysis, period comparisons, customer analytics, and reports.
"""

from datetime import date, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, RoleChecker
from app.models.core import User, UserRole, AuditLog
from app.services.analytics_engine import analytics_engine
from app.schemas.analytics import (
    KPIDashboard, KPIMetric,
    TrendResponse, TrendSeries, TrendDataPoint,
    ComparisonResponse, PeriodComparison,
    CustomerAnalyticsListResponse, CustomerAnalytics,
    ReportRequest, ReportResponse,
    AnalyticsPeriod,
)

router = APIRouter()


def _default_period() -> tuple:
    """Default to last 30 days."""
    today = date.today()
    return today - timedelta(days=30), today


# ── KPI Dashboard ──

@router.get("/kpis", response_model=KPIDashboard)
async def get_kpi_dashboard(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the core KPI dashboard with period-over-period comparison."""
    if not date_from or not date_to:
        date_from, date_to = _default_period()

    result = await analytics_engine.get_kpi_dashboard(db, current_user.tenant_id, date_from, date_to)

    return KPIDashboard(
        period=AnalyticsPeriod(date_from=date_from, date_to=date_to),
        kpis=[KPIMetric(**k) for k in result["kpis"]],
        generated_at=result["generated_at"],
    )


# ── Trend Analysis ──

@router.get("/trends", response_model=TrendResponse)
async def get_trends(
    metrics: str = Query("total_ar,dso,collection_rate", description="Comma-separated metric names"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    granularity: str = Query("weekly", description="daily, weekly, monthly"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get time-series trend data for specified metrics."""
    if not date_from or not date_to:
        date_from, date_to = _default_period()

    metric_list = [m.strip() for m in metrics.split(",") if m.strip()]
    if not metric_list:
        raise HTTPException(400, "At least one metric is required")

    valid_metrics = {"total_ar", "overdue_ar", "dso", "collection_rate",
                     "payment_total", "dispute_count_open", "invoice_count"}
    invalid = set(metric_list) - valid_metrics
    if invalid:
        raise HTTPException(400, f"Invalid metrics: {', '.join(invalid)}. Valid: {', '.join(valid_metrics)}")

    result = await analytics_engine.get_trends(
        db, current_user.tenant_id, metric_list, date_from, date_to, granularity,
    )

    return TrendResponse(
        period=AnalyticsPeriod(date_from=date_from, date_to=date_to),
        series=[TrendSeries(
            metric=s["metric"],
            display_name=s["display_name"],
            data=[TrendDataPoint(**dp) for dp in s["data"]],
            summary=s.get("summary"),
        ) for s in result["series"]],
    )


# ── Period Comparison ──

@router.get("/comparison", response_model=ComparisonResponse)
async def get_period_comparison(
    current_from: Optional[date] = None,
    current_to: Optional[date] = None,
    previous_from: Optional[date] = None,
    previous_to: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compare KPIs between two periods (defaults: current month vs previous month)."""
    today = date.today()
    if not current_from or not current_to:
        current_from = today.replace(day=1)
        current_to = today

    period_days = (current_to - current_from).days
    if not previous_from or not previous_to:
        previous_to = current_from - timedelta(days=1)
        previous_from = previous_to - timedelta(days=period_days)

    result = await analytics_engine.get_period_comparison(
        db, current_user.tenant_id,
        current_from, current_to, previous_from, previous_to,
    )

    return ComparisonResponse(
        current_period=AnalyticsPeriod(date_from=current_from, date_to=current_to),
        previous_period=AnalyticsPeriod(date_from=previous_from, date_to=previous_to),
        comparisons=[PeriodComparison(**c) for c in result["comparisons"]],
    )


# ── Customer Analytics ──

@router.get("/customers", response_model=CustomerAnalyticsListResponse)
async def get_customer_analytics(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sort_by: str = Query("overdue_amount", description="Sort field"),
    sort_desc: bool = Query(True, description="Sort descending"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get per-customer analytics with sorting and limit."""
    if not date_from or not date_to:
        date_from, date_to = _default_period()

    result = await analytics_engine.get_customer_analytics(
        db, current_user.tenant_id, date_from, date_to,
        sort_by=sort_by, sort_desc=sort_desc, limit=limit,
    )

    return CustomerAnalyticsListResponse(
        items=[CustomerAnalytics(**item) for item in result["items"]],
        total=result["total"],
        period=AnalyticsPeriod(date_from=date_from, date_to=date_to),
    )


# ── Reports ──

@router.post("/reports", response_model=ReportResponse)
async def generate_report(
    request: ReportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a structured report."""
    today = date.today()
    date_from = request.date_from or (today - timedelta(days=30))
    date_to = request.date_to or today

    valid_types = {"ar_aging", "dso_trend", "collection_performance", "customer_risk", "executive_summary"}
    if request.report_type not in valid_types:
        raise HTTPException(400, f"Invalid report_type. Valid: {', '.join(valid_types)}")

    result = await analytics_engine.generate_report(
        db, current_user.tenant_id, request.report_type, date_from, date_to,
        filters=request.filters,
    )

    # Audit
    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email, action="REPORT_GENERATE",
        entity_type="analytics",
        after_state={"report_type": request.report_type, "row_count": result["row_count"]},
    )
    db.add(audit)
    await db.commit()

    return ReportResponse(
        report_type=result["report_type"],
        title=result["title"],
        generated_at=result["generated_at"],
        period=AnalyticsPeriod(date_from=date_from, date_to=date_to),
        data=result["data"],
        summary=result["summary"],
        row_count=result["row_count"],
    )
