"""
Sales IQ - Day 14 Schemas
Health Scores, AI Credit Recommendations, Credit Exposure, Customer 360, Chat Engine.
"""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Health Score Engine ──

class HealthScoreWeights(BaseModel):
    payment: float = Field(0.40, ge=0, le=1, description="Payment behaviour weight")
    engagement: float = Field(0.20, ge=0, le=1, description="Engagement / responsiveness weight")
    order_trend: float = Field(0.30, ge=0, le=1, description="Order/revenue trend weight")
    risk_flags: float = Field(0.10, ge=0, le=1, description="Risk flag penalty weight")


class HealthScoreBreakdown(BaseModel):
    payment_score: float = Field(..., description="0-100 score for payment behaviour")
    engagement_score: float = Field(..., description="0-100 score for engagement")
    order_trend_score: float = Field(..., description="0-100 score for order trends")
    risk_flag_score: float = Field(..., description="0-100 score for risk (higher = less risky)")
    payment_factors: List[str] = []
    engagement_factors: List[str] = []
    order_trend_factors: List[str] = []
    risk_factors: List[str] = []


class HealthScoreResponse(BaseModel):
    customer_id: UUID
    customer_name: str
    composite_score: float = Field(..., description="Weighted composite 0-100")
    grade: str = Field(..., description="A/B/C/D/F grade")
    trend: str = Field(..., description="improving, stable, declining")
    breakdown: HealthScoreBreakdown
    weights: HealthScoreWeights
    previous_score: Optional[float] = None
    score_change: Optional[float] = None
    calculated_at: str


class HealthScoreHistoryPoint(BaseModel):
    date: str
    composite_score: float
    grade: str


class HealthScoreHistoryResponse(BaseModel):
    customer_id: UUID
    customer_name: str
    history: List[HealthScoreHistoryPoint]
    current_score: float
    current_grade: str
    trend: str


class HealthScoreBatchRequest(BaseModel):
    customer_ids: Optional[List[UUID]] = Field(None, description="Specific customers (null = all)")
    weights: Optional[HealthScoreWeights] = None


class HealthScoreBatchResponse(BaseModel):
    customers_processed: int
    avg_score: float
    grade_distribution: Dict[str, int]
    top_improvers: List[dict]
    top_decliners: List[dict]
    duration_ms: int


# ── AI Credit Recommendations ──

class CreditRecommendation(BaseModel):
    customer_id: UUID
    customer_name: str
    current_limit: float
    recommended_limit: float
    change_type: str = Field(..., description="increase, decrease, hold")
    change_amount: float
    change_pct: float
    confidence: float = Field(..., ge=0, le=1)
    reasoning: List[str]
    risk_score: float
    health_score: float
    utilization_pct: float
    model_version: str


class CreditRecommendationListResponse(BaseModel):
    items: List[CreditRecommendation]
    total: int
    summary: Dict[str, Any]


# ── Credit Hold/Release ──

class CreditHoldRequest(BaseModel):
    customer_id: UUID
    reason: Optional[str] = "Manual hold"
    threshold_override: Optional[float] = Field(None, description="Override utilization threshold %")


class CreditReleaseRequest(BaseModel):
    customer_id: UUID
    reason: Optional[str] = "Manual release"


class CreditHoldResponse(BaseModel):
    customer_id: UUID
    customer_name: str
    action: str  # hold, release
    previous_status: bool
    new_status: bool
    reason: str
    utilization_pct: float
    threshold_pct: float
    timestamp: str


class CreditHoldScanResponse(BaseModel):
    customers_scanned: int
    holds_applied: int
    holds_released: int
    already_held: int
    details: List[dict]
    duration_ms: int


# ── Credit Exposure Dashboard ──

class CreditExposureResponse(BaseModel):
    total_credit_limit: float
    total_utilization: float
    portfolio_utilization_pct: float
    currency: str
    top_utilization: List[dict]
    trending_up: List[dict]
    at_risk: List[dict]
    by_segment: Dict[str, dict]
    hold_count: int
    threshold_config: Dict[str, float]


# ── Customer 360 AI Insights ──

class Customer360Request(BaseModel):
    customer_id: UUID
    include_sections: Optional[List[str]] = Field(
        None,
        description="Sections to include: health_score, credit_status, payment_analysis, "
                    "predictions, latest_briefing, recommended_actions, collection_history, disputes"
    )


class Customer360Response(BaseModel):
    customer_id: UUID
    customer_name: str
    status: str
    health_score: Optional[dict] = None
    credit_status: Optional[dict] = None
    payment_analysis: Optional[dict] = None
    predictions: Optional[dict] = None
    latest_briefing: Optional[dict] = None
    recommended_actions: Optional[List[dict]] = None
    collection_history: Optional[dict] = None
    disputes: Optional[dict] = None
    generated_at: str


# ── Chat Engine ──

class ChatMessage(BaseModel):
    role: str = Field(..., description="user or assistant")
    content: str
    citations: Optional[List[dict]] = None
    timestamp: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[UUID] = Field(None, description="Existing conversation to continue")
    context: Optional[Dict[str, Any]] = Field(None, description="Extra context (current page, customer, etc.)")


class ChatResponse(BaseModel):
    conversation_id: UUID
    message: ChatMessage
    suggested_questions: List[str] = []
    data_citations: List[dict] = []
    entities_referenced: List[dict] = []
    processing_time_ms: int


class ChatHistoryResponse(BaseModel):
    conversation_id: UUID
    messages: List[ChatMessage]
    started_at: str
    last_message_at: str
    message_count: int
