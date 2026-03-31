"""
Sales IQ - Executive Dashboard Schemas
Day 17: Executive Dashboard, KPI Engine, Role-Based Home Screen & Widget System.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── KPI Cards ──

class TrendPoint(BaseModel):
    """Single point in a sparkline trend."""
    date: str
    value: float


class KPICard(BaseModel):
    """A single KPI metric card with trend sparklines."""
    key: str  # identifier: total_ar, avg_dso, collection_rate, etc.
    label: str
    value: float
    formatted_value: str  # human-readable, e.g. "12.9M AED"
    unit: Optional[str] = None
    change_pct: Optional[float] = None  # vs prior period
    change_direction: Optional[str] = None  # up, down, flat
    trend_7d: List[TrendPoint] = []
    trend_30d: List[TrendPoint] = []
    status: str = "normal"  # normal, warning, critical


class KPIDashboardResponse(BaseModel):
    cards: List[KPICard]
    currency: str
    generated_at: str


# ── AI Executive Summary ──

class ExecutiveSummaryResponse(BaseModel):
    summary: str  # 3-sentence AI briefing
    highlights: List[str]  # Key bullet points
    alerts: List[str]  # Urgent items needing attention
    data_as_of: str
    generated_at: str


# ── Executive Dashboard (unified) ──

class ExecutiveDashboardResponse(BaseModel):
    kpis: List[KPICard]
    executive_summary: ExecutiveSummaryResponse
    top_overdue_customers: List[Dict[str, Any]]
    pipeline_snapshot: Dict[str, Any]
    cash_flow_forecast: Dict[str, Any]
    health_distribution: Dict[str, int]  # grade -> count
    currency: str
    generated_at: str


# ── Role-Based Home Screen ──

class HomeScreenWidget(BaseModel):
    """A single widget in the home screen layout."""
    widget_id: str  # e.g. my_tasks, top_overdue, todays_briefing
    widget_type: str  # tasks, chart, list, summary, metric
    title: str
    position: int  # Order on screen (0-indexed)
    size: str = "medium"  # small, medium, large, full_width
    is_visible: bool = True
    is_pinned: bool = False
    data: Optional[Dict[str, Any]] = None  # Pre-loaded widget data
    endpoint: Optional[str] = None  # API endpoint for lazy loading


class HomeScreenLayout(BaseModel):
    """Widget layout for a specific role."""
    role: str
    widgets: List[HomeScreenWidget]
    last_customized_at: Optional[str] = None


class HomeScreenResponse(BaseModel):
    """Complete home screen data for current user."""
    role: str
    role_label: str
    greeting: str  # Personalized greeting
    widgets: List[HomeScreenWidget]
    quick_stats: Dict[str, Any]  # Role-specific quick numbers
    generated_at: str


# ── Widget Configuration ──

class WidgetDefinition(BaseModel):
    """Available widget definition for the configuration panel."""
    widget_id: str
    title: str
    description: str
    widget_type: str
    default_size: str
    available_for_roles: List[str]  # Which roles can use this widget


class AvailableWidgetsResponse(BaseModel):
    widgets: List[WidgetDefinition]
    total: int


class WidgetReorderRequest(BaseModel):
    """Request to reorder or toggle widgets."""
    widget_ids: List[str]  # Ordered list of widget IDs
    hidden_widget_ids: List[str] = []  # Widgets to hide
    pinned_widget_ids: List[str] = []  # Widgets to pin at top


class WidgetConfigResponse(BaseModel):
    """Current widget configuration for user."""
    user_id: UUID
    role: str
    layout: List[HomeScreenWidget]
    updated_at: str


# ── Dashboard Cache ──

class CacheStatusResponse(BaseModel):
    cached_keys: int
    oldest_entry: Optional[str] = None
    newest_entry: Optional[str] = None
    ttl_seconds: int
    hit_rate: Optional[float] = None
