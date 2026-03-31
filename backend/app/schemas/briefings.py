"""
Sales IQ - Briefing Schemas
Pydantic models for AI-generated briefing requests, responses, and scheduling.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Enums as string literals ──

BRIEFING_TYPES = ["daily_flash", "weekly_digest", "monthly_review", "custom"]
SECTION_TYPES = [
    "executive_summary",
    "ar_overview",
    "risk_alerts",
    "collection_priorities",
    "dispute_update",
    "credit_alerts",
    "data_quality",
]
DELIVERY_CHANNELS = ["in_app", "email", "both"]


# ── Request models ──

class BriefingGenerateRequest(BaseModel):
    """Request to generate a new briefing."""
    briefing_type: str = Field("daily_flash", description="daily_flash, weekly_digest, monthly_review, custom")
    recipient_id: Optional[UUID] = Field(None, description="Target user. Defaults to current user.")
    sections: Optional[List[str]] = Field(None, description="Section types to include (for custom type)")
    date_from: Optional[date] = Field(None, description="Analysis period start")
    date_to: Optional[date] = Field(None, description="Analysis period end. Defaults to today")
    delivery: str = Field("in_app", description="in_app, email, both")
    customer_ids: Optional[List[UUID]] = Field(None, description="Limit to specific customers")


class BriefingScheduleRequest(BaseModel):
    """Configure automated briefing schedule."""
    briefing_type: str = Field(..., description="daily_flash, weekly_digest, monthly_review")
    schedule_cron: str = Field(..., description="Cron expression (e.g. '0 7 * * 1-5' for weekday 7am)")
    recipient_ids: List[UUID] = Field(..., min_length=1, description="Users to receive the briefing")
    delivery: str = Field("email", description="in_app, email, both")
    sections: Optional[List[str]] = Field(None, description="Custom section selection")
    is_active: bool = True
    timezone: str = Field("Asia/Dubai", description="Schedule timezone")


class BriefingScheduleUpdate(BaseModel):
    is_active: Optional[bool] = None
    schedule_cron: Optional[str] = None
    recipient_ids: Optional[List[UUID]] = None
    delivery: Optional[str] = None
    sections: Optional[List[str]] = None


# ── Section model ──

class BriefingSection(BaseModel):
    """A single section within a briefing."""
    section_type: str
    title: str
    priority: int = Field(0, description="0=normal, 1=attention, 2=critical")
    content: str = Field(..., description="Markdown content")
    metrics: Optional[Dict[str, Any]] = None
    action_items: Optional[List[Dict[str, str]]] = None
    charts: Optional[List[Dict[str, Any]]] = None


# ── Response models ──

class BriefingResponse(BaseModel):
    id: UUID
    briefing_date: Optional[date] = None
    recipient_id: Optional[UUID] = None
    recipient_role: Optional[str] = None
    title: Optional[str] = None
    executive_summary: Optional[str] = None
    sections: Optional[List[Dict[str, Any]]] = None
    html_content: Optional[str] = None
    delivered_via: Optional[str] = None
    delivered_at: Optional[str] = None
    opened_at: Optional[str] = None
    model_used: Optional[str] = None
    generation_time_ms: Optional[int] = None
    data_snapshot: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BriefingListResponse(BaseModel):
    items: List[BriefingResponse]
    total: int
    page: int
    page_size: int


class BriefingScheduleResponse(BaseModel):
    id: UUID
    briefing_type: str
    schedule_cron: str
    recipient_ids: List[UUID]
    delivery: str
    sections: Optional[List[str]] = None
    is_active: bool
    timezone: str
    next_run: Optional[str] = None
    last_run: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BriefingScheduleListResponse(BaseModel):
    items: List[BriefingScheduleResponse]
    total: int
