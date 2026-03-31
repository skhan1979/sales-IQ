"""
Sales IQ - Executive Dashboard Endpoints
Day 17: KPIs, AI summary, role-based home screen, widget system, cache management.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.core import User
from app.services.executive_dashboard import executive_dashboard
from app.schemas.executive_dashboard import (
    KPIDashboardResponse,
    ExecutiveSummaryResponse,
    ExecutiveDashboardResponse,
    HomeScreenResponse,
    AvailableWidgetsResponse,
    WidgetReorderRequest,
    WidgetConfigResponse,
    CacheStatusResponse,
)

router = APIRouter()


# ── KPI Cards ──

@router.get("/kpis", response_model=KPIDashboardResponse)
async def get_kpi_cards(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """KPI cards with trend sparklines for executive dashboard."""
    result = await executive_dashboard.get_kpi_cards(db, current_user.tenant_id)
    return KPIDashboardResponse(**result)


# ── AI Executive Summary ──

@router.get("/summary", response_model=ExecutiveSummaryResponse)
async def get_executive_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI-generated 3-sentence executive briefing."""
    result = await executive_dashboard.get_executive_summary(db, current_user.tenant_id)
    return ExecutiveSummaryResponse(**result)


# ── Full Executive Dashboard ──

@router.get("/dashboard")
async def get_executive_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unified executive dashboard: KPIs + AI summary + top overdue + pipeline + cash flow."""
    return await executive_dashboard.get_executive_dashboard(db, current_user.tenant_id)


# ── Role-Based Home Screen ──

@router.get("/home", response_model=HomeScreenResponse)
async def get_home_screen(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Role-based home screen with personalized widgets and quick stats."""
    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    result = await executive_dashboard.get_home_screen(
        db, current_user.tenant_id, current_user.id,
        role, current_user.full_name or "User",
    )
    return HomeScreenResponse(**result)


# ── Widget Configuration ──

@router.get("/widgets/available", response_model=AvailableWidgetsResponse)
async def get_available_widgets(
    current_user: User = Depends(get_current_user),
):
    """List all widgets available for the current user's role."""
    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    result = executive_dashboard.get_available_widgets(role)
    return AvailableWidgetsResponse(**result)


@router.get("/widgets/config", response_model=WidgetConfigResponse)
async def get_widget_config(
    current_user: User = Depends(get_current_user),
):
    """Get current widget layout configuration for the user."""
    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    result = executive_dashboard.get_widget_config(current_user.id, role)
    return WidgetConfigResponse(**result)


@router.put("/widgets/config", response_model=WidgetConfigResponse)
async def update_widget_layout(
    body: WidgetReorderRequest,
    current_user: User = Depends(get_current_user),
):
    """Update widget layout: reorder, hide, or pin widgets."""
    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    result = executive_dashboard.update_widget_layout(
        current_user.id, role,
        {
            "widget_ids": body.widget_ids,
            "hidden_widget_ids": body.hidden_widget_ids,
            "pinned_widget_ids": body.pinned_widget_ids,
        },
    )
    return WidgetConfigResponse(**result)


# ── Cache Management ──

@router.get("/cache/status", response_model=CacheStatusResponse)
async def get_cache_status(
    current_user: User = Depends(get_current_user),
):
    """Dashboard cache statistics and health."""
    result = executive_dashboard.get_cache_status()
    return CacheStatusResponse(**result)


@router.post("/cache/invalidate")
async def invalidate_cache(
    current_user: User = Depends(get_current_user),
):
    """Clear dashboard cache to force fresh data on next load."""
    cleared = executive_dashboard.invalidate_cache(current_user.tenant_id)
    return {"cleared": cleared, "message": f"Invalidated {cleared} cache entries"}
