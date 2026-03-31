"""
Sales IQ - Analytics & Reporting Schemas
Day 11: KPIs, trend analysis, period comparisons, and exportable reports.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AnalyticsPeriod(BaseModel):
    date_from: date
    date_to: date
    label: Optional[str] = None


class KPIMetric(BaseModel):
    name: str
    value: float
    previous_value: Optional[float] = None
    change_pct: Optional[float] = None
    trend: Optional[str] = Field(None, description="up, down, flat")
    unit: Optional[str] = None
    target: Optional[float] = None
    target_met: Optional[bool] = None


class KPIDashboard(BaseModel):
    period: AnalyticsPeriod
    kpis: List[KPIMetric]
    generated_at: str


class TrendDataPoint(BaseModel):
    date: str
    value: float
    label: Optional[str] = None


class TrendSeries(BaseModel):
    metric: str
    display_name: str
    data: List[TrendDataPoint]
    summary: Optional[Dict[str, float]] = None


class TrendResponse(BaseModel):
    period: AnalyticsPeriod
    series: List[TrendSeries]


class PeriodComparison(BaseModel):
    metric: str
    display_name: str
    current_value: float
    previous_value: float
    change: float
    change_pct: float
    trend: str


class ComparisonResponse(BaseModel):
    current_period: AnalyticsPeriod
    previous_period: AnalyticsPeriod
    comparisons: List[PeriodComparison]


class CustomerAnalytics(BaseModel):
    customer_id: UUID
    customer_name: str
    total_ar: float
    overdue_amount: float
    total_invoices: int
    overdue_invoices: int
    avg_days_to_pay: float
    risk_score: Optional[float] = None
    credit_utilization_pct: float
    collection_effectiveness: float
    dispute_count: int
    payment_count: int


class CustomerAnalyticsListResponse(BaseModel):
    items: List[CustomerAnalytics]
    total: int
    period: AnalyticsPeriod


class ReportRequest(BaseModel):
    report_type: str = Field(..., description="ar_aging, dso_trend, collection_performance, customer_risk, executive_summary")
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    format: str = Field("json", description="json, csv")
    filters: Optional[Dict[str, Any]] = None


class ReportResponse(BaseModel):
    report_type: str
    title: str
    generated_at: str
    period: AnalyticsPeriod
    data: Any
    summary: Dict[str, Any]
    row_count: int
