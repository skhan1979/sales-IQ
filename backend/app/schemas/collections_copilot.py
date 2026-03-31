"""
Sales IQ - Collections Copilot Schemas
Day 13: AI message drafting, escalation templates, PTP tracking, dispute aging.
"""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Enums ──

class MessageChannel(str, enum.Enum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    LETTER = "letter"


class MessageTone(str, enum.Enum):
    FRIENDLY = "friendly"
    FIRM = "firm"
    URGENT = "urgent"
    LEGAL = "legal"
    FOLLOW_UP = "follow_up"


class EscalationStepType(str, enum.Enum):
    EMAIL = "email"
    PHONE_CALL = "phone_call"
    WHATSAPP = "whatsapp"
    MANAGER_ESCALATION = "manager_escalation"
    LEGAL_NOTICE = "legal_notice"
    CREDIT_HOLD = "credit_hold"


class PTPStatus(str, enum.Enum):
    PENDING = "pending"
    FULFILLED = "fulfilled"
    PARTIALLY_FULFILLED = "partially_fulfilled"
    BROKEN = "broken"
    EXPIRED = "expired"


# ── AI Message Drafting ──

class MessageDraftRequest(BaseModel):
    customer_id: UUID
    invoice_ids: Optional[List[UUID]] = Field(None, description="Specific invoices to reference (null=all overdue)")
    channel: str = Field("email", description="email, whatsapp, sms, letter")
    tone: str = Field("friendly", description="friendly, firm, urgent, legal, follow_up")
    language: str = Field("en", description="en or ar")
    include_payment_link: bool = False
    custom_instructions: Optional[str] = Field(None, description="Extra instructions for AI")


class MessageDraftResponse(BaseModel):
    draft_id: UUID
    customer_id: UUID
    customer_name: str
    channel: str
    tone: str
    language: str
    subject: Optional[str] = None  # For email
    body: str
    invoices_referenced: List[dict]
    total_amount_due: float
    currency: str
    ai_confidence: float
    suggested_follow_up_days: int
    metadata: Optional[Dict[str, Any]] = None


class MessageSendRequest(BaseModel):
    draft_id: UUID
    edited_subject: Optional[str] = None
    edited_body: Optional[str] = None
    send_now: bool = True
    schedule_at: Optional[datetime] = None


class MessageSendResponse(BaseModel):
    message_id: UUID
    draft_id: UUID
    status: str  # sent, scheduled, queued
    channel: str
    sent_at: Optional[str] = None
    scheduled_at: Optional[str] = None


class MessageHistoryResponse(BaseModel):
    id: UUID
    customer_id: UUID
    customer_name: str
    channel: str
    tone: str
    subject: Optional[str] = None
    body: str
    status: str
    sent_at: Optional[str] = None
    opened_at: Optional[str] = None
    replied_at: Optional[str] = None
    invoices_referenced: List[dict]
    total_amount: float
    currency: str


class MessageHistoryListResponse(BaseModel):
    items: List[MessageHistoryResponse]
    total: int
    page: int
    page_size: int


# ── Escalation Templates ──

class EscalationStep(BaseModel):
    day_offset: int = Field(..., ge=0, description="Days after trigger to execute this step")
    action_type: str = Field(..., description="email, phone_call, whatsapp, manager_escalation, legal_notice, credit_hold")
    message_tone: str = Field("friendly", description="Tone for AI-generated message")
    message_channel: Optional[str] = Field(None, description="Override channel for this step")
    assignee_role: Optional[str] = Field(None, description="Role to assign (e.g. collector, finance_manager)")
    auto_execute: bool = Field(True, description="Auto-execute or require manual approval")
    description: Optional[str] = None


class EscalationTemplateCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    trigger_type: str = Field(..., description="overdue_days, ptp_broken, dispute_unresolved")
    trigger_threshold: int = Field(..., description="Days overdue / days since PTP broken / etc.")
    steps: List[EscalationStep] = Field(..., min_length=1)
    applies_to_segments: Optional[List[str]] = Field(None, description="Customer segments (null=all)")
    is_active: bool = True


class EscalationTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[List[EscalationStep]] = None
    is_active: Optional[bool] = None
    trigger_threshold: Optional[int] = None


class EscalationTemplateResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    trigger_type: str
    trigger_threshold: int
    steps: List[EscalationStep]
    applies_to_segments: Optional[List[str]] = None
    is_active: bool
    times_triggered: int = 0
    last_triggered_at: Optional[str] = None
    created_at: Optional[str] = None


class EscalationTemplateListResponse(BaseModel):
    items: List[EscalationTemplateResponse]
    total: int


class EscalationRunResponse(BaseModel):
    customers_evaluated: int
    escalations_triggered: int
    actions_queued: int
    by_template: Dict[str, int]
    by_action_type: Dict[str, int]
    duration_ms: int


# ── Enhanced PTP Tracking ──

class PTPCreateRequest(BaseModel):
    customer_id: UUID
    invoice_id: Optional[UUID] = None
    promised_date: date
    promised_amount: Decimal = Field(..., gt=0)
    currency: str = "AED"
    notes: Optional[str] = None
    contact_person: Optional[str] = None
    contact_method: Optional[str] = Field(None, description="phone, email, in_person")


class PTPUpdateRequest(BaseModel):
    status: Optional[str] = None
    actual_amount: Optional[Decimal] = None
    actual_date: Optional[date] = None
    notes: Optional[str] = None
    follow_up_date: Optional[date] = None


class PTPResponse(BaseModel):
    id: UUID
    customer_id: UUID
    customer_name: str
    invoice_id: Optional[UUID] = None
    invoice_number: Optional[str] = None
    promised_date: date
    promised_amount: float
    actual_amount: Optional[float] = None
    actual_date: Optional[date] = None
    currency: str
    status: str
    days_until_due: Optional[int] = None
    days_overdue: Optional[int] = None
    contact_person: Optional[str] = None
    contact_method: Optional[str] = None
    notes: Optional[str] = None
    follow_up_date: Optional[date] = None
    created_at: Optional[str] = None


class PTPListResponse(BaseModel):
    items: List[PTPResponse]
    total: int
    summary: Dict[str, Any]


class PTPDashboard(BaseModel):
    total_promises: int
    total_promised_amount: float
    fulfilled_count: int
    fulfilled_amount: float
    broken_count: int
    broken_amount: float
    pending_count: int
    pending_amount: float
    fulfillment_rate: float
    due_today: int
    due_this_week: int
    overdue: int
    currency: str


# ── Dispute Aging ──

class DisputeAgingBucket(BaseModel):
    bucket: str
    count: int
    total_amount: float
    avg_days_open: float
    disputes: List[dict]


class DisputeAgingReport(BaseModel):
    buckets: List[DisputeAgingBucket]
    total_open: int
    total_amount: float
    avg_resolution_days: float
    resolution_rate: float
    by_reason: Dict[str, int]
    by_department: Dict[str, int]
    sla_breach_count: int
    generated_at: str
