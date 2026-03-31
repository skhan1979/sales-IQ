"""
Sales IQ - Admin & Agent Hub Enhanced Schemas
Day 18: Admin screens, Agent Hub dashboard enhancements, Demo Data Manager presets.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── User Settings ──

class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


class NotificationPreferences(BaseModel):
    email_enabled: bool = True
    in_app_enabled: bool = True
    daily_briefing: bool = True
    overdue_alerts: bool = True
    dispute_updates: bool = True
    credit_hold_alerts: bool = True
    agent_failure_alerts: bool = False


class UserSettingsResponse(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    role: str
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    timezone: str
    language: str
    notification_preferences: NotificationPreferences
    updated_at: str


# ── Admin Users & Roles ──

class UserInviteRequest(BaseModel):
    email: str
    full_name: str
    role: str = "viewer"
    territory_ids: Optional[List[str]] = None


class UserRoleUpdate(BaseModel):
    role: str
    territory_ids: Optional[List[str]] = None


class AdminUserResponse(BaseModel):
    id: UUID
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    last_login_at: Optional[str] = None
    territory_ids: Optional[List[str]] = None
    created_at: str


class AdminUserListResponse(BaseModel):
    items: List[AdminUserResponse]
    total: int
    page: int
    page_size: int


# ── Business Rules ──

class BusinessRulesConfig(BaseModel):
    # AI model preferences
    ai_scoring_model: str = "xgboost_v1"
    ai_prediction_enabled: bool = True
    # Alert thresholds
    overdue_alert_days: int = 7
    credit_hold_threshold_pct: float = 90.0
    churn_alert_threshold: float = 0.3
    health_score_alert_grade: str = "D"
    # Scoring weights
    payment_weight: float = 0.40
    engagement_weight: float = 0.20
    order_trend_weight: float = 0.30
    risk_flag_weight: float = 0.10
    # Notification rules
    auto_escalation_enabled: bool = True
    ptp_reminder_days_before: int = 1
    collection_frequency_days: int = 7


class BusinessRulesResponse(BaseModel):
    config: BusinessRulesConfig
    updated_at: str
    updated_by: Optional[str] = None


# ── System Monitor ──

class SystemHealthResponse(BaseModel):
    api_status: str  # healthy, degraded, down
    database_status: str
    cache_status: str
    uptime_seconds: int
    api_calls_24h: int
    avg_response_ms: float
    error_rate_24h: float
    active_connections: int
    background_jobs: List[Dict[str, Any]]
    recent_errors: List[Dict[str, Any]]


# ── Audit Log ──

class AuditLogEntry(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    user_email: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[UUID] = None
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    created_at: str


class AuditLogListResponse(BaseModel):
    items: List[AuditLogEntry]
    total: int
    page: int
    page_size: int


# ── Agent Hub Enhanced ──

class AgentDependencyLink(BaseModel):
    source_agent: str
    target_agent: str
    relationship: str  # feeds_data, triggers, enriches


class AgentDependencyMap(BaseModel):
    agents: List[str]
    links: List[AgentDependencyLink]
    description: str


class AgentPerformancePoint(BaseModel):
    date: str
    total_runs: int
    successful: int
    failed: int
    avg_duration_ms: float


class AgentPerformanceHistory(BaseModel):
    agent_name: str
    display_name: str
    period_days: int
    data_points: List[AgentPerformancePoint]
    overall_success_rate: float
    total_records_processed: int


# ── Demo Data Manager Enhanced ──

class DemoPreset(BaseModel):
    preset_id: str
    name: str
    description: str
    erp_profile: str
    dataset_size: str
    parameters: Dict[str, Any]


class DemoPresetListResponse(BaseModel):
    presets: List[DemoPreset]
    total: int


class DemoGenerateWithPresetRequest(BaseModel):
    preset_id: Optional[str] = None
    erp_profile: str = "d365_fo"
    crm_profile: Optional[str] = None
    dataset_size: str = "medium"
    customer_count: Optional[int] = None
    industry: Optional[str] = None
    revenue_range: Optional[str] = None
    overdue_pct: Optional[float] = None
    target_dso: Optional[int] = None


class DemoDataSummary(BaseModel):
    customers: int
    invoices: int
    payments: int
    disputes: int
    collection_activities: int
    credit_requests: int
    agent_runs: int
    audit_logs: int
    total_records: int
    erp_profile: str
    last_generated_at: Optional[str] = None
