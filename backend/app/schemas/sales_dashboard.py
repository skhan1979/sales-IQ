"""
Sales IQ - Sales Dashboard Schemas
Day 16: Sales intelligence, pipeline, churn watchlist, reorder alerts, revenue segmentation.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Pipeline Summary ──

class PipelineStage(BaseModel):
    stage: str
    count: int
    amount: float
    pct_of_total: float


class PipelineSummaryResponse(BaseModel):
    stages: List[PipelineStage]
    total_pipeline_value: float
    total_opportunities: int
    avg_deal_size: float
    weighted_pipeline: float
    conversion_rate: float
    currency: str


# ── Reorder Alerts ──

class ReorderAlert(BaseModel):
    customer_id: UUID
    customer_name: str
    segment: Optional[str] = None
    last_order_date: Optional[str] = None
    days_since_last_order: int
    avg_order_frequency_days: Optional[float] = None
    avg_order_value: float
    expected_next_order: Optional[str] = None
    overdue_by_days: Optional[int] = None
    alert_level: str  # warning, critical, dormant
    churn_probability: float
    health_score: Optional[float] = None
    currency: str


class ReorderAlertListResponse(BaseModel):
    items: List[ReorderAlert]
    total: int
    by_alert_level: Dict[str, int]
    total_at_risk_revenue: float
    currency: str


# ── Churn Watchlist ──

class ChurnWatchlistEntry(BaseModel):
    customer_id: UUID
    customer_name: str
    segment: Optional[str] = None
    churn_probability: float
    churn_risk: str  # high, medium, low
    trend: str  # increasing, stable, decreasing
    health_score: Optional[float] = None
    health_grade: Optional[str] = None
    total_ar: float
    overdue_amount: float
    days_since_last_payment: Optional[int] = None
    last_collection_action: Optional[str] = None
    risk_factors: List[str]
    recommended_action: str
    currency: str


class ChurnWatchlistResponse(BaseModel):
    items: List[ChurnWatchlistEntry]
    total: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    total_ar_at_risk: float
    currency: str


# ── Revenue by Segment ──

class SegmentRevenue(BaseModel):
    segment: str
    customer_count: int
    total_invoiced: float
    total_collected: float
    total_outstanding: float
    collection_rate: float
    avg_dso: float
    growth_pct: Optional[float] = None
    currency: str


class RevenueBySegmentResponse(BaseModel):
    segments: List[SegmentRevenue]
    total_revenue: float
    top_segment: str
    currency: str


# ── Growth Opportunities ──

class GrowthOpportunity(BaseModel):
    customer_id: UUID
    customer_name: str
    segment: Optional[str] = None
    current_revenue: float
    potential_increase: float
    potential_increase_pct: float
    opportunity_type: str  # upsell, reactivation, cross_sell, credit_expansion
    reasoning: List[str]
    confidence: float
    health_score: Optional[float] = None
    currency: str


class GrowthOpportunityListResponse(BaseModel):
    items: List[GrowthOpportunity]
    total: int
    total_potential_revenue: float
    by_type: Dict[str, int]
    currency: str


# ── Sales Dashboard Summary ──

class SalesDashboardResponse(BaseModel):
    pipeline: PipelineSummaryResponse
    reorder_alerts_count: int
    churn_high_risk_count: int
    total_ar: float
    total_overdue: float
    collection_rate: float
    customer_count: int
    health_distribution: Dict[str, int]
    currency: str
