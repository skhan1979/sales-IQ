"""
Sales IQ - Workflow Schemas
Pydantic models for Dispute Management, Credit Limit Requests,
and Collection Activity tracking.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================
# Dispute Schemas
# =============================================

class DisputeCreate(BaseModel):
    customer_id: UUID
    invoice_id: Optional[UUID] = None
    reason: str = Field(..., description="pricing, quantity, quality, delivery, duplicate, wrong_product, damaged, not_received, terms, other")
    reason_detail: Optional[str] = None
    amount: Decimal = Field(..., gt=0)
    currency: str = "AED"
    priority: str = Field("medium", pattern="^(low|medium|high|critical)$")
    assigned_department: Optional[str] = None
    assigned_to_id: Optional[UUID] = None
    sla_due_date: Optional[date] = None
    attachments: Optional[List[dict]] = None


class DisputeUpdate(BaseModel):
    reason_detail: Optional[str] = None
    amount: Optional[Decimal] = None
    priority: Optional[str] = None
    assigned_department: Optional[str] = None
    assigned_to_id: Optional[UUID] = None
    sla_due_date: Optional[date] = None
    attachments: Optional[List[dict]] = None


class DisputeTransition(BaseModel):
    """Workflow state transition."""
    action: str = Field(..., description="review, escalate, resolve, reject, reopen")
    notes: Optional[str] = None
    # For resolution
    resolution_type: Optional[str] = Field(None, description="credit_note, adjustment, rejected")
    resolution_amount: Optional[Decimal] = None
    escalated_to_id: Optional[UUID] = None


class DisputeResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    customer_name: Optional[str] = None
    invoice_id: Optional[UUID] = None
    invoice_number: Optional[str] = None
    dispute_number: str
    reason: str
    reason_detail: Optional[str] = None
    status: str
    amount: Decimal
    currency: str
    priority: str
    assigned_department: Optional[str] = None
    assigned_to_id: Optional[UUID] = None
    escalated_to_id: Optional[UUID] = None
    resolution_type: Optional[str] = None
    resolution_amount: Optional[Decimal] = None
    resolution_notes: Optional[str] = None
    resolved_at: Optional[str] = None
    resolved_by_id: Optional[UUID] = None
    sla_due_date: Optional[date] = None
    sla_breached: bool = False
    attachments: Optional[List[dict]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DisputeListResponse(BaseModel):
    items: List[DisputeResponse]
    total: int
    page: int
    page_size: int


class DisputeSummary(BaseModel):
    total_disputes: int
    open_count: int
    in_review_count: int
    escalated_count: int
    resolved_count: int
    total_disputed_amount: Decimal
    sla_breached_count: int
    avg_resolution_days: Optional[float] = None
    by_reason: Dict[str, int]
    by_priority: Dict[str, int]


# =============================================
# Credit Limit Request Schemas
# =============================================

class CreditLimitRequestCreate(BaseModel):
    customer_id: UUID
    requested_limit: Decimal = Field(..., gt=0)
    currency: str = "AED"
    justification: Optional[str] = None


class CreditLimitApproval(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    approved_limit: Optional[Decimal] = None
    approval_notes: Optional[str] = None


class CreditLimitRequestResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    customer_name: Optional[str] = None
    requested_by_id: UUID
    current_limit: Decimal
    requested_limit: Decimal
    ai_recommended_limit: Optional[Decimal] = None
    currency: str
    justification: Optional[str] = None
    ai_risk_assessment: Optional[Dict[str, Any]] = None
    approval_status: str
    approved_by_id: Optional[UUID] = None
    approved_limit: Optional[Decimal] = None
    approval_notes: Optional[str] = None
    approved_at: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CreditLimitListResponse(BaseModel):
    items: List[CreditLimitRequestResponse]
    total: int
    page: int
    page_size: int


# =============================================
# Collection Activity Schemas
# =============================================

class CollectionActivityCreate(BaseModel):
    customer_id: UUID
    invoice_id: Optional[UUID] = None
    action_type: str = Field(..., description="email_reminder, sms_reminder, phone_call, escalation, promise_to_pay, legal_notice, write_off_request")
    action_date: date
    notes: Optional[str] = None
    ptp_date: Optional[date] = None
    ptp_amount: Optional[Decimal] = None


class CollectionActivityUpdate(BaseModel):
    notes: Optional[str] = None
    ptp_date: Optional[date] = None
    ptp_amount: Optional[Decimal] = None
    ptp_fulfilled: Optional[bool] = None


class CollectionActivityResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    customer_name: Optional[str] = None
    invoice_id: Optional[UUID] = None
    invoice_number: Optional[str] = None
    collector_id: Optional[UUID] = None
    action_type: str
    action_date: date
    notes: Optional[str] = None
    ptp_date: Optional[date] = None
    ptp_amount: Optional[Decimal] = None
    ptp_fulfilled: Optional[bool] = None
    is_ai_suggested: bool = False
    ai_priority_score: Optional[float] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CollectionActivityListResponse(BaseModel):
    items: List[CollectionActivityResponse]
    total: int
    page: int
    page_size: int


class CollectionSummary(BaseModel):
    total_activities: int
    activities_this_month: int
    promises_to_pay: int
    ptp_fulfilled: int
    ptp_broken: int
    by_action_type: Dict[str, int]
    ai_suggested_count: int
