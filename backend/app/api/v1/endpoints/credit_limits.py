"""
Sales IQ - Credit Limit Request Endpoints
Approval workflow with AI risk assessment stub.
"""

import random
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, RoleChecker
from app.models.core import User, UserRole, AuditLog
from app.models.business import CreditLimitRequest, Customer, CreditApprovalStatus
from app.schemas.workflows import (
    CreditLimitRequestCreate, CreditLimitApproval,
    CreditLimitRequestResponse, CreditLimitListResponse,
)

router = APIRouter()

require_finance = RoleChecker(min_role=UserRole.FINANCE_MANAGER, allowed_roles=[UserRole.FINANCE_MANAGER])


def _generate_risk_assessment(customer: Customer, requested_limit: Decimal) -> dict:
    """
    Generate a simulated AI risk assessment for the credit limit request.
    In production, this would call the ML risk model.
    """
    current = float(customer.credit_limit or 0)
    requested = float(requested_limit)
    increase_pct = ((requested - current) / current * 100) if current > 0 else 100

    risk_factors = []
    risk_score = customer.risk_score or 50.0

    if increase_pct > 100:
        risk_factors.append({"factor": "Large increase requested", "detail": f"{increase_pct:.0f}% above current limit", "impact": "high"})
        risk_score = min(100, risk_score + 15)
    elif increase_pct > 50:
        risk_factors.append({"factor": "Significant increase", "detail": f"{increase_pct:.0f}% above current limit", "impact": "medium"})
        risk_score = min(100, risk_score + 8)

    utilization = float(customer.credit_utilization or 0)
    if current > 0:
        util_pct = utilization / current * 100
        if util_pct > 80:
            risk_factors.append({"factor": "High current utilization", "detail": f"{util_pct:.0f}% utilized", "impact": "medium"})
        else:
            risk_factors.append({"factor": "Healthy utilization", "detail": f"{util_pct:.0f}% utilized", "impact": "low"})

    if customer.ecl_stage and str(customer.ecl_stage) != "stage_1":
        risk_factors.append({"factor": "Elevated ECL stage", "detail": str(customer.ecl_stage), "impact": "high"})
        risk_score = min(100, risk_score + 20)

    if customer.credit_hold:
        risk_factors.append({"factor": "Customer on credit hold", "detail": "Active credit hold", "impact": "critical"})
        risk_score = min(100, risk_score + 25)

    # AI recommendation: conservative approach
    if risk_score < 40:
        recommended = requested
        recommendation = "approve"
    elif risk_score < 60:
        recommended = Decimal(str(round(float(requested) * 0.8 / 10000) * 10000))
        recommendation = "approve_reduced"
    elif risk_score < 80:
        recommended = Decimal(str(round(float(requested) * 0.5 / 10000) * 10000))
        recommendation = "review_carefully"
    else:
        recommended = customer.credit_limit
        recommendation = "reject"

    return {
        "risk_score": round(risk_score, 1),
        "risk_factors": risk_factors,
        "recommendation": recommendation,
        "recommended_limit": str(recommended),
        "model_version": "v1.0-stub",
    }


@router.get("/", response_model=CreditLimitListResponse)
async def list_credit_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(CreditLimitRequest).where(CreditLimitRequest.tenant_id == current_user.tenant_id)
    if customer_id:
        query = query.where(CreditLimitRequest.customer_id == customer_id)
    if status_filter:
        query = query.where(CreditLimitRequest.approval_status == status_filter)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(CreditLimitRequest.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    requests = result.scalars().all()

    # Hydrate customer names
    customer_ids = list({r.customer_id for r in requests})
    cust_map = {}
    if customer_ids:
        cust_result = await db.execute(
            select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids))
        )
        cust_map = {row.id: row.name for row in cust_result.all()}

    items = []
    for r in requests:
        data = CreditLimitRequestResponse.model_validate(r)
        data.customer_name = cust_map.get(r.customer_id)
        items.append(data)

    return CreditLimitListResponse(
        items=items,
        total=total, page=page, page_size=page_size,
    )


@router.post("/", response_model=CreditLimitRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_credit_request(
    request: CreditLimitRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a credit limit increase/decrease request with AI risk assessment."""
    cust_result = await db.execute(
        select(Customer).where(Customer.id == request.customer_id, Customer.tenant_id == current_user.tenant_id)
    )
    customer = cust_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(404, "Customer not found")

    # Check for existing pending request
    existing = await db.execute(
        select(CreditLimitRequest).where(
            CreditLimitRequest.tenant_id == current_user.tenant_id,
            CreditLimitRequest.customer_id == request.customer_id,
            CreditLimitRequest.approval_status == CreditApprovalStatus.PENDING,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "A pending credit limit request already exists for this customer")

    # Generate AI risk assessment
    risk_assessment = _generate_risk_assessment(customer, request.requested_limit)
    ai_recommended = Decimal(risk_assessment["recommended_limit"])

    # Auto-approve small increases with low risk
    auto_approved = False
    current_limit = customer.credit_limit or Decimal("0")
    increase_pct = ((float(request.requested_limit) - float(current_limit)) / float(current_limit) * 100) if current_limit > 0 else 100

    if increase_pct <= 20 and risk_assessment["risk_score"] < 30:
        auto_approved = True

    credit_req = CreditLimitRequest(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        customer_id=request.customer_id,
        requested_by_id=current_user.id,
        current_limit=current_limit,
        requested_limit=request.requested_limit,
        ai_recommended_limit=ai_recommended,
        currency=request.currency,
        justification=request.justification,
        ai_risk_assessment=risk_assessment,
        approval_status=CreditApprovalStatus.AUTO_APPROVED if auto_approved else CreditApprovalStatus.PENDING,
    )

    if auto_approved:
        credit_req.approved_limit = request.requested_limit
        credit_req.approved_at = datetime.now(timezone.utc).isoformat()
        credit_req.approval_notes = "Auto-approved: small increase with low risk score"
        # Apply the new limit
        customer.credit_limit = request.requested_limit

    db.add(credit_req)

    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email, action="CREATE",
        entity_type="credit_limit_requests",
        after_state={
            "customer_id": str(request.customer_id),
            "current": str(current_limit), "requested": str(request.requested_limit),
            "ai_recommended": str(ai_recommended), "auto_approved": auto_approved,
        },
    )
    db.add(audit)
    await db.commit()
    await db.refresh(credit_req)

    return CreditLimitRequestResponse.model_validate(credit_req)


@router.post("/{request_id}/decide", response_model=CreditLimitRequestResponse)
async def decide_credit_request(
    request_id: UUID,
    decision: CreditLimitApproval,
    current_user: User = Depends(require_finance),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a pending credit limit request (finance manager+)."""
    result = await db.execute(
        select(CreditLimitRequest).where(
            CreditLimitRequest.id == request_id,
            CreditLimitRequest.tenant_id == current_user.tenant_id,
        )
    )
    credit_req = result.scalar_one_or_none()
    if not credit_req:
        raise HTTPException(404, "Credit limit request not found")

    if credit_req.approval_status not in (CreditApprovalStatus.PENDING, "pending"):
        raise HTTPException(400, f"Request already processed: {credit_req.approval_status}")

    if decision.action == "approve":
        approved_limit = decision.approved_limit or credit_req.requested_limit
        credit_req.approval_status = CreditApprovalStatus.APPROVED
        credit_req.approved_limit = approved_limit
        credit_req.approved_by_id = current_user.id
        credit_req.approved_at = datetime.now(timezone.utc).isoformat()
        credit_req.approval_notes = decision.approval_notes

        # Apply new credit limit to customer
        cust_result = await db.execute(
            select(Customer).where(Customer.id == credit_req.customer_id, Customer.tenant_id == current_user.tenant_id)
        )
        customer = cust_result.scalar_one_or_none()
        if customer:
            customer.credit_limit = approved_limit
            # Release credit hold if utilization now below threshold
            if customer.credit_utilization and approved_limit > 0:
                pct = float(customer.credit_utilization) / float(approved_limit) * 100
                if pct < float(customer.credit_hold_threshold or 90):
                    customer.credit_hold = False

    elif decision.action == "reject":
        credit_req.approval_status = CreditApprovalStatus.REJECTED
        credit_req.approved_by_id = current_user.id
        credit_req.approved_at = datetime.now(timezone.utc).isoformat()
        credit_req.approval_notes = decision.approval_notes or "Rejected by finance"

    credit_req.updated_by = current_user.id

    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email,
        action=f"CREDIT_{decision.action.upper()}",
        entity_type="credit_limit_requests", entity_id=request_id,
        after_state={
            "action": decision.action,
            "approved_limit": str(credit_req.approved_limit) if credit_req.approved_limit else None,
        },
    )
    db.add(audit)
    await db.commit()
    await db.refresh(credit_req)

    return CreditLimitRequestResponse.model_validate(credit_req)
