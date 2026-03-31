"""
Sales IQ - Webhook & Integration Schemas
Day 12: Event types, webhook subscriptions, delivery logs, and connector configs.
"""

import enum
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


# ── Enums ──

class EventType(str, enum.Enum):
    # Customer events
    CUSTOMER_CREATED = "customer.created"
    CUSTOMER_UPDATED = "customer.updated"
    CUSTOMER_CREDIT_HOLD = "customer.credit_hold"
    CUSTOMER_RISK_CHANGE = "customer.risk_change"

    # Invoice events
    INVOICE_CREATED = "invoice.created"
    INVOICE_OVERDUE = "invoice.overdue"
    INVOICE_PAID = "invoice.paid"

    # Payment events
    PAYMENT_RECEIVED = "payment.received"
    PAYMENT_MATCHED = "payment.matched"

    # Dispute events
    DISPUTE_OPENED = "dispute.opened"
    DISPUTE_ESCALATED = "dispute.escalated"
    DISPUTE_RESOLVED = "dispute.resolved"

    # Credit limit events
    CREDIT_LIMIT_REQUESTED = "credit_limit.requested"
    CREDIT_LIMIT_APPROVED = "credit_limit.approved"
    CREDIT_LIMIT_REJECTED = "credit_limit.rejected"

    # Collection events
    COLLECTION_ACTION = "collection.action"
    PTP_BROKEN = "collection.ptp_broken"

    # Alert events
    ALERT_TRIGGERED = "alert.triggered"

    # System events
    DATA_IMPORT_COMPLETED = "system.import_completed"
    DQ_SCAN_COMPLETED = "system.dq_scan_completed"
    BRIEFING_GENERATED = "system.briefing_generated"


class WebhookStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    FAILED = "failed"  # Automatically disabled after too many failures


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


# ── Webhook Subscription ──

class WebhookCreate(BaseModel):
    name: str = Field(..., max_length=200)
    url: str = Field(..., description="Target URL for webhook delivery")
    events: List[str] = Field(..., description="Event types to subscribe to", min_length=1)
    secret: Optional[str] = Field(None, description="HMAC secret for payload signing")
    headers: Optional[Dict[str, str]] = Field(None, description="Custom headers to include")
    is_active: bool = True
    retry_count: int = Field(3, ge=0, le=10, description="Max delivery retries")
    timeout_seconds: int = Field(30, ge=5, le=120)
    description: Optional[str] = None


class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    events: Optional[List[str]] = None
    secret: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    is_active: Optional[bool] = None
    retry_count: Optional[int] = None
    timeout_seconds: Optional[int] = None


class WebhookResponse(BaseModel):
    id: UUID
    name: str
    url: str
    events: List[str]
    headers: Optional[Dict[str, str]] = None
    is_active: bool
    status: str
    retry_count: int
    timeout_seconds: int
    description: Optional[str] = None
    total_deliveries: int = 0
    successful_deliveries: int = 0
    failed_deliveries: int = 0
    last_delivery_at: Optional[str] = None
    last_delivery_status: Optional[str] = None
    created_at: Optional[datetime] = None


class WebhookListResponse(BaseModel):
    items: List[WebhookResponse]
    total: int


# ── Delivery Log ──

class DeliveryLogResponse(BaseModel):
    id: UUID
    webhook_id: UUID
    event_type: str
    event_id: UUID
    status: str
    attempt: int
    response_code: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: Optional[int] = None
    payload_size: int = 0
    created_at: Optional[str] = None


class DeliveryLogListResponse(BaseModel):
    items: List[DeliveryLogResponse]
    total: int
    page: int
    page_size: int


# ── Event Log ──

class EventLogResponse(BaseModel):
    id: UUID
    event_type: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    payload: Dict[str, Any]
    webhooks_triggered: int = 0
    created_at: Optional[str] = None


class EventLogListResponse(BaseModel):
    items: List[EventLogResponse]
    total: int
    page: int
    page_size: int


# ── Event Publish ──

class EventPublish(BaseModel):
    event_type: str = Field(..., description="Event type (from EventType enum)")
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class EventPublishResponse(BaseModel):
    event_id: UUID
    event_type: str
    webhooks_matched: int
    deliveries_queued: int


# ── Webhook Test ──

class WebhookTestResponse(BaseModel):
    webhook_id: UUID
    success: bool
    response_code: Optional[int] = None
    response_body: Optional[str] = None
    error: Optional[str] = None
    duration_ms: int
