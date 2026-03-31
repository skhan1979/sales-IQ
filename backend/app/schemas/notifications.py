"""
Sales IQ - Notification & Alert Models + Schemas
Day 10: Rule-based alert engine, notification delivery, and user preferences.
"""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Enums ──

class AlertSeverity(str, enum.Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertCategory(str, enum.Enum):
    SLA_BREACH = "sla_breach"
    CREDIT_HOLD = "credit_hold"
    OVERDUE_THRESHOLD = "overdue_threshold"
    PAYMENT_RECEIVED = "payment_received"
    DISPUTE_ESCALATED = "dispute_escalated"
    CREDIT_LIMIT_REQUEST = "credit_limit_request"
    DSO_THRESHOLD = "dso_threshold"
    HIGH_RISK_CUSTOMER = "high_risk_customer"
    PTP_BROKEN = "ptp_broken"
    DQ_QUARANTINE = "dq_quarantine"
    CUSTOM = "custom"


class NotificationChannel(str, enum.Enum):
    IN_APP = "in_app"
    EMAIL = "email"
    WEBHOOK = "webhook"


# ── Alert Rule schemas ──

class AlertRuleCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    category: str = Field(..., description="Alert category from AlertCategory enum")
    severity: str = Field("warning", description="critical, warning, info")
    condition: Dict[str, Any] = Field(..., description="Rule condition (e.g. {'field': 'days_overdue', 'operator': '>', 'value': 90})")
    channels: List[str] = Field(["in_app"], description="Delivery channels: in_app, email, webhook")
    recipient_roles: Optional[List[str]] = Field(None, description="Target roles (null = all)")
    recipient_user_ids: Optional[List[UUID]] = None
    is_active: bool = True
    cooldown_minutes: int = Field(60, description="Minimum minutes between repeat alerts")


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    severity: Optional[str] = None
    condition: Optional[Dict[str, Any]] = None
    channels: Optional[List[str]] = None
    is_active: Optional[bool] = None
    cooldown_minutes: Optional[int] = None


class AlertRuleResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    category: str
    severity: str
    condition: Dict[str, Any]
    channels: List[str]
    recipient_roles: Optional[List[str]] = None
    recipient_user_ids: Optional[List[str]] = None
    is_active: bool
    cooldown_minutes: int
    times_triggered: int = 0
    last_triggered_at: Optional[str] = None
    created_at: Optional[datetime] = None


class AlertRuleListResponse(BaseModel):
    items: List[AlertRuleResponse]
    total: int


# ── Notification schemas ──

class NotificationResponse(BaseModel):
    id: UUID
    alert_rule_id: Optional[UUID] = None
    category: str
    severity: str
    title: str
    message: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    channel: str
    is_read: bool = False
    read_at: Optional[str] = None
    action_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    total: int
    unread_count: int
    page: int
    page_size: int


class NotificationMarkRead(BaseModel):
    notification_ids: List[UUID]


class NotificationPreferences(BaseModel):
    email_enabled: bool = True
    in_app_enabled: bool = True
    quiet_hours_start: Optional[str] = Field(None, description="HH:MM format")
    quiet_hours_end: Optional[str] = Field(None, description="HH:MM format")
    muted_categories: Optional[List[str]] = None
    min_severity: str = Field("info", description="Minimum severity to receive")


# ── Alert Engine Scan ──

class AlertScanResponse(BaseModel):
    alerts_generated: int
    by_category: Dict[str, int]
    by_severity: Dict[str, int]
    scan_duration_ms: int
