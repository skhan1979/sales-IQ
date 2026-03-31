"""
Sales IQ - CFO Dashboard Schemas
Day 15: AR Dashboard enhancements, Write-Off management, IFRS 9 ECL provisioning.
"""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Enhanced AR Dashboard ──

class DSOTrendPoint(BaseModel):
    month: str
    dso: float
    total_receivables: float
    credit_sales: float


class DSOTrendResponse(BaseModel):
    trend: List[DSOTrendPoint]
    current_dso: float
    avg_dso: float
    best_dso: float
    worst_dso: float
    trend_direction: str  # improving, stable, worsening


class OverdueTrendPoint(BaseModel):
    month: str
    overdue_amount: float
    overdue_count: int
    overdue_pct: float  # % of total receivables


class OverdueTrendResponse(BaseModel):
    trend: List[OverdueTrendPoint]
    current_overdue: float
    current_overdue_count: int
    currency: str


class CashFlowForecastBucket(BaseModel):
    period: str  # "30_days", "60_days", "90_days"
    label: str
    predicted_inflow: float
    high_confidence: float  # amount where payment_probability > 0.7
    medium_confidence: float  # 0.3-0.7
    low_confidence: float  # < 0.3
    invoice_count: int


class CashFlowForecastResponse(BaseModel):
    buckets: List[CashFlowForecastBucket]
    total_predicted: float
    total_high_confidence: float
    total_medium_confidence: float
    total_low_confidence: float
    currency: str
    generated_at: str


class TopOverdueCustomer(BaseModel):
    customer_id: UUID
    customer_name: str
    total_overdue: float
    invoice_count: int
    max_days_overdue: int
    credit_limit: float
    utilization_pct: float
    health_score: Optional[float] = None
    risk_score: float
    currency: str


class TopOverdueCustomerListResponse(BaseModel):
    items: List[TopOverdueCustomer]
    total_overdue_amount: float
    currency: str


# ── Write-Off Management ──

class WriteOffType(str, enum.Enum):
    FULL = "full"
    PARTIAL = "partial"
    PROVISION = "provision"


class WriteOffCreateRequest(BaseModel):
    customer_id: UUID
    invoice_id: Optional[UUID] = None
    write_off_type: str = Field("full", description="full, partial, provision")
    amount: Decimal = Field(..., gt=0)
    currency: str = "AED"
    reason: Optional[str] = None


class WriteOffApprovalRequest(BaseModel):
    action: str = Field(..., description="approve or reject")
    approval_notes: Optional[str] = None
    approved_amount: Optional[Decimal] = Field(None, description="Override amount (for partial adjustments)")


class WriteOffResponse(BaseModel):
    id: UUID
    customer_id: UUID
    customer_name: Optional[str] = None
    invoice_id: Optional[UUID] = None
    invoice_number: Optional[str] = None
    write_off_type: str
    amount: float
    currency: str
    ecl_stage: Optional[str] = None
    ecl_probability: Optional[float] = None
    provision_amount: Optional[float] = None
    reason: Optional[str] = None
    approval_status: str
    approved_by_id: Optional[UUID] = None
    approved_at: Optional[str] = None
    is_reversed: bool = False
    created_at: Optional[str] = None


class WriteOffListResponse(BaseModel):
    items: List[WriteOffResponse]
    total: int
    page: int
    page_size: int
    summary: Dict[str, Any]


class WriteOffReversalRequest(BaseModel):
    reason: str


class WriteOffSummary(BaseModel):
    total_written_off: float
    total_pending: float
    total_approved: float
    total_reversed: float
    by_type: Dict[str, float]
    by_ecl_stage: Dict[str, float]
    write_off_count: int
    currency: str


# ── IFRS 9 ECL Provisioning ──

class ECLStageInfo(str, enum.Enum):
    STAGE_1 = "stage_1"  # Performing, 12-month ECL
    STAGE_2 = "stage_2"  # Significant credit deterioration, lifetime ECL
    STAGE_3 = "stage_3"  # Credit-impaired, lifetime ECL


class ECLCustomerResult(BaseModel):
    customer_id: UUID
    customer_name: str
    ecl_stage: str
    ecl_probability: float
    total_exposure: float  # Total outstanding receivables
    provision_required: float  # ML-calculated provision
    traditional_provision: float  # Aging-based provision
    provision_difference: float  # ML - traditional (positive = under-provisioned)
    provision_status: str  # under_provisioned, over_provisioned, adequate
    risk_score: float
    health_score: Optional[float] = None
    key_factors: List[str]
    currency: str


class ECLBatchResponse(BaseModel):
    customers_analyzed: int
    total_exposure: float
    total_ml_provision: float
    total_traditional_provision: float
    provision_gap: float  # ML - Traditional
    by_stage: Dict[str, dict]
    under_provisioned_count: int
    over_provisioned_count: int
    adequate_count: int
    recommendations: List[dict]
    model_version: str
    currency: str
    duration_ms: int


class ProvisioningDashboard(BaseModel):
    total_provision_required: float
    total_current_provision: float
    provision_adequacy_ratio: float
    movement_analysis: Dict[str, float]  # new_provisions, releases, write_offs, net_change
    by_stage: Dict[str, dict]  # per-stage totals
    by_segment: Dict[str, dict]  # per-segment totals
    top_under_provisioned: List[dict]
    ai_vs_traditional: Dict[str, float]
    currency: str
    generated_at: str
