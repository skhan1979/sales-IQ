"""
Sales IQ - Intelligence Layer Endpoints
Day 14: Health scores, AI credit recommendations, credit exposure,
        Customer 360 insights, chat engine.
"""

from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, RoleChecker
from app.models.core import User, UserRole, AuditLog
from app.services.intelligence import intelligence_engine
from app.schemas.intelligence import (
    HealthScoreResponse, HealthScoreBreakdown, HealthScoreWeights,
    HealthScoreHistoryResponse, HealthScoreBatchRequest, HealthScoreBatchResponse,
    CreditRecommendationListResponse,
    CreditHoldRequest, CreditReleaseRequest, CreditHoldResponse, CreditHoldScanResponse,
    CreditExposureResponse,
    Customer360Request, Customer360Response,
    ChatRequest, ChatResponse, ChatHistoryResponse, ChatMessage,
)

router = APIRouter()

require_finance = RoleChecker(min_role=UserRole.FINANCE_MANAGER, allowed_roles=[UserRole.FINANCE_MANAGER])


# ═══════════════════════════════════════════
# HEALTH SCORE ENGINE
# ═══════════════════════════════════════════

@router.get("/health-score/{customer_id}", response_model=HealthScoreResponse)
async def get_health_score(
    customer_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Calculate and return the composite health score for a customer."""
    try:
        score = await intelligence_engine.calculate_health_score(
            db, current_user.tenant_id, customer_id,
        )
        return HealthScoreResponse(
            customer_id=UUID(score["customer_id"]),
            customer_name=score["customer_name"],
            composite_score=score["composite_score"],
            grade=score["grade"],
            trend=score["trend"],
            breakdown=HealthScoreBreakdown(**score["breakdown"]),
            weights=HealthScoreWeights(**score["weights"]),
            previous_score=score.get("previous_score"),
            score_change=score.get("score_change"),
            calculated_at=score["calculated_at"],
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))


@router.get("/health-score/{customer_id}/history", response_model=HealthScoreHistoryResponse)
async def get_health_score_history(
    customer_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get health score history for trend analysis."""
    history = intelligence_engine.get_health_history(str(customer_id))
    if not history:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No health score history found. Calculate score first.")
    return HealthScoreHistoryResponse(
        customer_id=UUID(history["customer_id"]),
        customer_name=history["customer_name"],
        history=history["history"],
        current_score=history["current_score"],
        current_grade=history["current_grade"],
        trend=history["trend"],
    )


@router.post("/health-score/batch", response_model=HealthScoreBatchResponse)
async def batch_health_scores(
    request: HealthScoreBatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Calculate health scores for multiple customers (or all)."""
    weights = request.weights.model_dump() if request.weights else None
    result = await intelligence_engine.batch_health_scores(
        db, current_user.tenant_id, request.customer_ids, weights,
    )
    return HealthScoreBatchResponse(**result)


# ═══════════════════════════════════════════
# AI CREDIT RECOMMENDATIONS
# ═══════════════════════════════════════════

@router.get("/credit/recommendations", response_model=CreditRecommendationListResponse)
async def get_credit_recommendations(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_finance),
    db: AsyncSession = Depends(get_db),
):
    """Generate AI credit limit recommendations for all customers."""
    result = await intelligence_engine.generate_credit_recommendations(
        db, current_user.tenant_id, limit,
    )
    return CreditRecommendationListResponse(**result)


# ═══════════════════════════════════════════
# CREDIT HOLD / RELEASE
# ═══════════════════════════════════════════

@router.post("/credit/hold", response_model=CreditHoldResponse)
async def apply_credit_hold(
    request: CreditHoldRequest,
    current_user: User = Depends(require_finance),
    db: AsyncSession = Depends(get_db),
):
    """Manually apply credit hold to a customer."""
    try:
        result = await intelligence_engine.apply_credit_hold(
            db, current_user.tenant_id, request.customer_id,
            reason=request.reason or "Manual hold",
            user_id=current_user.id,
        )

        audit = AuditLog(
            tenant_id=current_user.tenant_id, user_id=current_user.id,
            user_email=current_user.email, action="CREDIT_HOLD",
            entity_type="customers", entity_id=request.customer_id,
            after_state={"reason": request.reason, "action": "hold"},
        )
        db.add(audit)
        await db.commit()

        return CreditHoldResponse(**result)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))


@router.post("/credit/release", response_model=CreditHoldResponse)
async def release_credit_hold(
    request: CreditReleaseRequest,
    current_user: User = Depends(require_finance),
    db: AsyncSession = Depends(get_db),
):
    """Manually release credit hold from a customer."""
    try:
        result = await intelligence_engine.release_credit_hold(
            db, current_user.tenant_id, request.customer_id,
            reason=request.reason or "Manual release",
        )

        audit = AuditLog(
            tenant_id=current_user.tenant_id, user_id=current_user.id,
            user_email=current_user.email, action="CREDIT_RELEASE",
            entity_type="customers", entity_id=request.customer_id,
            after_state={"reason": request.reason, "action": "release"},
        )
        db.add(audit)
        await db.commit()

        return CreditHoldResponse(**result)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))


@router.post("/credit/hold-scan", response_model=CreditHoldScanResponse)
async def scan_credit_holds(
    current_user: User = Depends(require_finance),
    db: AsyncSession = Depends(get_db),
):
    """Auto-scan all customers for credit hold/release based on utilization thresholds."""
    result = await intelligence_engine.scan_credit_holds(db, current_user.tenant_id)
    return CreditHoldScanResponse(**result)


# ═══════════════════════════════════════════
# CREDIT EXPOSURE DASHBOARD
# ═══════════════════════════════════════════

@router.get("/credit/exposure", response_model=CreditExposureResponse)
async def get_credit_exposure(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get portfolio-level credit exposure analytics."""
    result = await intelligence_engine.get_credit_exposure(db, current_user.tenant_id)
    return CreditExposureResponse(**result)


# ═══════════════════════════════════════════
# CUSTOMER 360 AI INSIGHTS
# ═══════════════════════════════════════════

@router.get("/customer-360/{customer_id}", response_model=Customer360Response)
async def get_customer_360(
    customer_id: UUID,
    sections: Optional[str] = Query(
        None,
        description="Comma-separated sections: health_score,credit_status,payment_analysis,"
                    "predictions,latest_briefing,recommended_actions,collection_history,disputes"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated AI-powered 360-degree view of a customer."""
    include_sections = sections.split(",") if sections else None
    try:
        result = await intelligence_engine.get_customer_360(
            db, current_user.tenant_id, customer_id, include_sections,
        )
        return Customer360Response(**result)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))


# ═══════════════════════════════════════════
# CHAT ENGINE
# ═══════════════════════════════════════════

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to the AI chat assistant."""
    result = await intelligence_engine.chat(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        message=request.message,
        conversation_id=str(request.conversation_id) if request.conversation_id else None,
        context=request.context,
    )
    return ChatResponse(
        conversation_id=UUID(result["conversation_id"]),
        message=ChatMessage(**result["message"]),
        suggested_questions=result["suggested_questions"],
        data_citations=result["data_citations"],
        entities_referenced=result["entities_referenced"],
        processing_time_ms=result["processing_time_ms"],
    )


@router.get("/chat/{conversation_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get chat conversation history."""
    result = intelligence_engine.get_chat_history(
        str(current_user.tenant_id), str(conversation_id),
    )
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return ChatHistoryResponse(
        conversation_id=UUID(result["conversation_id"]),
        messages=[ChatMessage(**m) for m in result["messages"]],
        started_at=result["started_at"],
        last_message_at=result["last_message_at"],
        message_count=result["message_count"],
    )


@router.get("/chat", response_model=list)
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all chat conversations for the current user."""
    return intelligence_engine.list_conversations(
        str(current_user.tenant_id), str(current_user.id),
    )
