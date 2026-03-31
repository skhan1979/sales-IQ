"""
Sales IQ - Collection Activity Endpoints
Track collection actions (calls, emails, PTP) with AI prioritization.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.core import User, AuditLog
from app.models.business import (
    CollectionActivity, Customer, Invoice,
    CollectionAction,
)
from app.schemas.workflows import (
    CollectionActivityCreate, CollectionActivityUpdate,
    CollectionActivityResponse, CollectionActivityListResponse,
    CollectionSummary,
)

router = APIRouter()


@router.get("/", response_model=CollectionActivityListResponse)
async def list_activities(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[UUID] = None,
    invoice_id: Optional[UUID] = None,
    action_type: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(CollectionActivity).where(CollectionActivity.tenant_id == current_user.tenant_id)

    if customer_id:
        query = query.where(CollectionActivity.customer_id == customer_id)
    if invoice_id:
        query = query.where(CollectionActivity.invoice_id == invoice_id)
    if action_type:
        query = query.where(CollectionActivity.action_type == action_type)
    if from_date:
        query = query.where(CollectionActivity.action_date >= from_date)
    if to_date:
        query = query.where(CollectionActivity.action_date <= to_date)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(CollectionActivity.action_date.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    activities = result.scalars().all()

    # Hydrate customer names and invoice numbers
    customer_ids = list({a.customer_id for a in activities})
    invoice_ids = list({a.invoice_id for a in activities if a.invoice_id})
    cust_map = {}
    inv_map = {}
    if customer_ids:
        cust_result = await db.execute(
            select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids))
        )
        cust_map = {row.id: row.name for row in cust_result.all()}
    if invoice_ids:
        inv_result = await db.execute(
            select(Invoice.id, Invoice.invoice_number).where(Invoice.id.in_(invoice_ids))
        )
        inv_map = {row.id: row.invoice_number for row in inv_result.all()}

    items = []
    for a in activities:
        data = CollectionActivityResponse.model_validate(a)
        data.customer_name = cust_map.get(a.customer_id)
        if a.invoice_id:
            data.invoice_number = inv_map.get(a.invoice_id)
        items.append(data)

    return CollectionActivityListResponse(
        items=items,
        total=total, page=page, page_size=page_size,
    )


@router.post("/", response_model=CollectionActivityResponse, status_code=status.HTTP_201_CREATED)
async def create_activity(
    request: CollectionActivityCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Log a collection activity (call, email, PTP, escalation)."""
    # Verify customer
    cust = await db.execute(
        select(Customer).where(Customer.id == request.customer_id, Customer.tenant_id == current_user.tenant_id)
    )
    if not cust.scalar_one_or_none():
        raise HTTPException(404, "Customer not found")

    # Verify invoice if provided
    if request.invoice_id:
        inv = await db.execute(
            select(Invoice).where(Invoice.id == request.invoice_id, Invoice.tenant_id == current_user.tenant_id)
        )
        if not inv.scalar_one_or_none():
            raise HTTPException(404, "Invoice not found")

    try:
        action_enum = CollectionAction(request.action_type)
    except ValueError:
        raise HTTPException(400, f"Invalid action_type. Valid: {[a.value for a in CollectionAction]}")

    activity = CollectionActivity(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        customer_id=request.customer_id,
        invoice_id=request.invoice_id,
        collector_id=current_user.id,
        action_type=action_enum,
        action_date=request.action_date,
        notes=request.notes,
        ptp_date=request.ptp_date,
        ptp_amount=request.ptp_amount,
    )
    db.add(activity)

    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email, action="CREATE",
        entity_type="collection_activities",
        after_state={"action_type": request.action_type, "customer_id": str(request.customer_id)},
    )
    db.add(audit)
    await db.commit()
    await db.refresh(activity)

    return CollectionActivityResponse.model_validate(activity)


@router.patch("/{activity_id}", response_model=CollectionActivityResponse)
async def update_activity(
    activity_id: UUID,
    request: CollectionActivityUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a collection activity (e.g., mark PTP as fulfilled)."""
    result = await db.execute(
        select(CollectionActivity).where(
            CollectionActivity.id == activity_id,
            CollectionActivity.tenant_id == current_user.tenant_id,
        )
    )
    activity = result.scalar_one_or_none()
    if not activity:
        raise HTTPException(404, "Activity not found")

    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(activity, field, value)

    activity.updated_by = current_user.id
    await db.commit()
    await db.refresh(activity)

    return CollectionActivityResponse.model_validate(activity)


@router.get("/summary", response_model=CollectionSummary)
async def get_collection_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Collection activity analytics dashboard."""
    tid = current_user.tenant_id

    total = (await db.execute(
        select(func.count()).select_from(CollectionActivity).where(CollectionActivity.tenant_id == tid)
    )).scalar() or 0

    # This month
    today = date.today()
    first_of_month = today.replace(day=1)
    this_month = (await db.execute(
        select(func.count()).select_from(CollectionActivity).where(
            CollectionActivity.tenant_id == tid,
            CollectionActivity.action_date >= first_of_month,
        )
    )).scalar() or 0

    # PTP stats
    ptp_total = (await db.execute(
        select(func.count()).select_from(CollectionActivity).where(
            CollectionActivity.tenant_id == tid,
            CollectionActivity.action_type == CollectionAction.PROMISE_TO_PAY,
        )
    )).scalar() or 0

    ptp_fulfilled = (await db.execute(
        select(func.count()).select_from(CollectionActivity).where(
            CollectionActivity.tenant_id == tid,
            CollectionActivity.action_type == CollectionAction.PROMISE_TO_PAY,
            CollectionActivity.ptp_fulfilled == True,
        )
    )).scalar() or 0

    ptp_broken = (await db.execute(
        select(func.count()).select_from(CollectionActivity).where(
            CollectionActivity.tenant_id == tid,
            CollectionActivity.action_type == CollectionAction.PROMISE_TO_PAY,
            CollectionActivity.ptp_fulfilled == False,
        )
    )).scalar() or 0

    # By action type
    by_action = {}
    for a in CollectionAction:
        cnt = (await db.execute(
            select(func.count()).select_from(CollectionActivity).where(
                CollectionActivity.tenant_id == tid, CollectionActivity.action_type == a
            )
        )).scalar() or 0
        if cnt > 0:
            by_action[a.value] = cnt

    # AI suggested
    ai_count = (await db.execute(
        select(func.count()).select_from(CollectionActivity).where(
            CollectionActivity.tenant_id == tid, CollectionActivity.is_ai_suggested == True
        )
    )).scalar() or 0

    return CollectionSummary(
        total_activities=total,
        activities_this_month=this_month,
        promises_to_pay=ptp_total,
        ptp_fulfilled=ptp_fulfilled,
        ptp_broken=ptp_broken,
        by_action_type=by_action,
        ai_suggested_count=ai_count,
    )
