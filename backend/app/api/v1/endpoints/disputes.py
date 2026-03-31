"""
Sales IQ - Dispute Management Endpoints
Full CRUD with workflow state machine, SLA tracking, and analytics.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, RoleChecker
from app.models.core import User, UserRole, AuditLog
from app.models.business import (
    Dispute, Customer, Invoice,
    DisputeStatus, DisputeReason, InvoiceStatus,
)
from app.schemas.workflows import (
    DisputeCreate, DisputeUpdate, DisputeTransition,
    DisputeResponse, DisputeListResponse, DisputeSummary,
)

router = APIRouter()

# Workflow: valid state transitions
VALID_TRANSITIONS = {
    "review":   (DisputeStatus.OPEN,       DisputeStatus.IN_REVIEW),
    "escalate": (DisputeStatus.IN_REVIEW,  DisputeStatus.ESCALATED),
    "resolve":  (None,                     DisputeStatus.RESOLVED),     # from any non-resolved
    "reject":   (None,                     DisputeStatus.REJECTED),     # from any non-resolved
    "reopen":   (None,                     DisputeStatus.OPEN),         # from resolved/rejected
}

# Auto-increment dispute number per tenant
async def _next_dispute_number(db: AsyncSession, tenant_id: UUID) -> str:
    result = await db.execute(
        select(func.count()).select_from(Dispute).where(Dispute.tenant_id == tenant_id)
    )
    count = (result.scalar() or 0) + 1
    return f"DSP-{count:05d}"


@router.get("/", response_model=DisputeListResponse)
async def list_disputes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    priority: Optional[str] = None,
    reason: Optional[str] = None,
    sla_breached: Optional[bool] = None,
    sort_by: str = Query("created_at", pattern="^(created_at|amount|sla_due_date|priority)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List disputes with filtering, sorting, and pagination."""
    query = select(Dispute).where(Dispute.tenant_id == current_user.tenant_id)

    if customer_id:
        query = query.where(Dispute.customer_id == customer_id)
    if status_filter:
        query = query.where(Dispute.status == status_filter)
    if priority:
        query = query.where(Dispute.priority == priority)
    if reason:
        query = query.where(Dispute.reason == reason)
    if sla_breached is not None:
        query = query.where(Dispute.sla_breached == sla_breached)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    sort_col = getattr(Dispute, sort_by, Dispute.created_at)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    disputes = result.scalars().all()

    # Hydrate customer names and invoice numbers
    customer_ids = list({d.customer_id for d in disputes})
    invoice_ids = list({d.invoice_id for d in disputes if d.invoice_id})
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
    for d in disputes:
        data = DisputeResponse.model_validate(d)
        data.customer_name = cust_map.get(d.customer_id)
        if d.invoice_id:
            data.invoice_number = inv_map.get(d.invoice_id)
        items.append(data)

    return DisputeListResponse(
        items=items,
        total=total, page=page, page_size=page_size,
    )


@router.post("/", response_model=DisputeResponse, status_code=status.HTTP_201_CREATED)
async def create_dispute(
    request: DisputeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new dispute against a customer/invoice."""
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
        invoice = inv.scalar_one_or_none()
        if not invoice:
            raise HTTPException(404, "Invoice not found")
        # Mark invoice as disputed
        invoice.status = InvoiceStatus.DISPUTED

    # Validate reason enum
    try:
        reason_enum = DisputeReason(request.reason)
    except ValueError:
        raise HTTPException(400, f"Invalid reason. Valid: {[r.value for r in DisputeReason]}")

    dispute_number = await _next_dispute_number(db, current_user.tenant_id)

    # Default SLA: 15 business days if not specified
    sla_date = request.sla_due_date or (date.today() + __import__("datetime").timedelta(days=21))

    dispute = Dispute(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        customer_id=request.customer_id,
        invoice_id=request.invoice_id,
        dispute_number=dispute_number,
        reason=reason_enum,
        reason_detail=request.reason_detail,
        status=DisputeStatus.OPEN,
        amount=request.amount,
        currency=request.currency,
        priority=request.priority,
        assigned_department=request.assigned_department,
        assigned_to_id=request.assigned_to_id,
        sla_due_date=sla_date,
        attachments=request.attachments or [],
    )
    db.add(dispute)

    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email, action="CREATE",
        entity_type="disputes",
        after_state={"dispute_number": dispute_number, "amount": str(request.amount), "reason": request.reason},
    )
    db.add(audit)
    await db.commit()
    await db.refresh(dispute)

    return DisputeResponse.model_validate(dispute)


@router.get("/{dispute_id}", response_model=DisputeResponse)
async def get_dispute(
    dispute_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Dispute).where(Dispute.id == dispute_id, Dispute.tenant_id == current_user.tenant_id)
    )
    dispute = result.scalar_one_or_none()
    if not dispute:
        raise HTTPException(404, "Dispute not found")
    data = DisputeResponse.model_validate(dispute)
    # Hydrate customer name
    cust_result = await db.execute(
        select(Customer.name).where(Customer.id == dispute.customer_id)
    )
    data.customer_name = cust_result.scalar_one_or_none()
    # Hydrate invoice number
    if dispute.invoice_id:
        inv_result = await db.execute(
            select(Invoice.invoice_number).where(Invoice.id == dispute.invoice_id)
        )
        data.invoice_number = inv_result.scalar_one_or_none()
    return data


@router.patch("/{dispute_id}", response_model=DisputeResponse)
async def update_dispute(
    dispute_id: UUID,
    request: DisputeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Dispute).where(Dispute.id == dispute_id, Dispute.tenant_id == current_user.tenant_id)
    )
    dispute = result.scalar_one_or_none()
    if not dispute:
        raise HTTPException(404, "Dispute not found")

    before = {}
    after = {}
    for field, value in request.model_dump(exclude_unset=True).items():
        old = getattr(dispute, field, None)
        before[field] = str(old) if old is not None else None
        after[field] = str(value) if value is not None else None
        setattr(dispute, field, value)

    dispute.updated_by = current_user.id

    # Check SLA breach
    if dispute.sla_due_date and dispute.sla_due_date < date.today() and dispute.status not in (DisputeStatus.RESOLVED, DisputeStatus.REJECTED):
        dispute.sla_breached = True

    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email, action="UPDATE",
        entity_type="disputes", entity_id=dispute_id,
        before_state=before, after_state=after,
    )
    db.add(audit)
    await db.commit()
    await db.refresh(dispute)

    return DisputeResponse.model_validate(dispute)


@router.post("/{dispute_id}/transition", response_model=DisputeResponse)
async def transition_dispute(
    dispute_id: UUID,
    request: DisputeTransition,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Transition a dispute through its workflow.
    Actions: review, escalate, resolve, reject, reopen
    """
    result = await db.execute(
        select(Dispute).where(Dispute.id == dispute_id, Dispute.tenant_id == current_user.tenant_id)
    )
    dispute = result.scalar_one_or_none()
    if not dispute:
        raise HTTPException(404, "Dispute not found")

    transition = VALID_TRANSITIONS.get(request.action)
    if not transition:
        raise HTTPException(400, f"Invalid action: {request.action}. Valid: {list(VALID_TRANSITIONS.keys())}")

    from_status, to_status = transition
    current_status = DisputeStatus(dispute.status) if isinstance(dispute.status, str) else dispute.status

    # Validate from_status (None means any non-terminal)
    if from_status is not None and current_status != from_status:
        raise HTTPException(
            400,
            f"Cannot '{request.action}' from status '{current_status.value}'. Expected '{from_status.value}'.",
        )

    # Reopen only from resolved/rejected
    if request.action == "reopen" and current_status not in (DisputeStatus.RESOLVED, DisputeStatus.REJECTED, DisputeStatus.CREDIT_ISSUED):
        raise HTTPException(400, f"Cannot reopen from status '{current_status.value}'")

    # Resolve/reject from any non-terminal state
    terminal_statuses = (DisputeStatus.RESOLVED, DisputeStatus.REJECTED, DisputeStatus.CREDIT_ISSUED)
    if request.action in ("resolve", "reject") and current_status in terminal_statuses:
        raise HTTPException(400, f"Dispute already '{current_status.value}'")

    before_status = current_status.value
    dispute.status = to_status

    if request.action == "resolve":
        dispute.resolution_type = request.resolution_type or "adjustment"
        dispute.resolution_amount = request.resolution_amount or dispute.amount
        dispute.resolution_notes = request.notes
        dispute.resolved_at = datetime.now(timezone.utc).isoformat()
        dispute.resolved_by_id = current_user.id

        # If resolved with credit note, update to CREDIT_ISSUED
        if request.resolution_type == "credit_note":
            dispute.status = DisputeStatus.CREDIT_ISSUED

    elif request.action == "reject":
        dispute.resolution_type = "rejected"
        dispute.resolution_notes = request.notes
        dispute.resolved_at = datetime.now(timezone.utc).isoformat()
        dispute.resolved_by_id = current_user.id

    elif request.action == "escalate":
        dispute.escalated_to_id = request.escalated_to_id
        if request.notes:
            dispute.reason_detail = (dispute.reason_detail or "") + f"\n[Escalation] {request.notes}"

    elif request.action == "reopen":
        dispute.resolved_at = None
        dispute.resolved_by_id = None
        dispute.resolution_type = None
        dispute.resolution_amount = None

    dispute.updated_by = current_user.id

    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email,
        action=f"DISPUTE_{request.action.upper()}",
        entity_type="disputes", entity_id=dispute_id,
        before_state={"status": before_status},
        after_state={"status": dispute.status.value if hasattr(dispute.status, 'value') else str(dispute.status)},
    )
    db.add(audit)
    await db.commit()
    await db.refresh(dispute)

    return DisputeResponse.model_validate(dispute)


@router.get("/summary/overview", response_model=DisputeSummary)
async def get_dispute_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dispute analytics dashboard."""
    tid = current_user.tenant_id
    base = select(Dispute).where(Dispute.tenant_id == tid)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0

    # Count by status
    status_counts = {}
    for s in DisputeStatus:
        cnt = (await db.execute(
            select(func.count()).select_from(Dispute).where(Dispute.tenant_id == tid, Dispute.status == s)
        )).scalar() or 0
        status_counts[s.value] = cnt

    # Total disputed amount (non-resolved)
    total_amount = (await db.execute(
        select(func.coalesce(func.sum(Dispute.amount), 0)).where(
            Dispute.tenant_id == tid,
            Dispute.status.notin_([DisputeStatus.RESOLVED, DisputeStatus.REJECTED, DisputeStatus.CREDIT_ISSUED]),
        )
    )).scalar() or Decimal("0")

    # SLA breached
    sla_breached = (await db.execute(
        select(func.count()).select_from(Dispute).where(
            Dispute.tenant_id == tid, Dispute.sla_breached == True
        )
    )).scalar() or 0

    # By reason
    by_reason = {}
    for r in DisputeReason:
        cnt = (await db.execute(
            select(func.count()).select_from(Dispute).where(Dispute.tenant_id == tid, Dispute.reason == r)
        )).scalar() or 0
        if cnt > 0:
            by_reason[r.value] = cnt

    # By priority
    by_priority = {}
    for p in ["low", "medium", "high", "critical"]:
        cnt = (await db.execute(
            select(func.count()).select_from(Dispute).where(Dispute.tenant_id == tid, Dispute.priority == p)
        )).scalar() or 0
        if cnt > 0:
            by_priority[p] = cnt

    return DisputeSummary(
        total_disputes=total,
        open_count=status_counts.get("open", 0),
        in_review_count=status_counts.get("in_review", 0),
        escalated_count=status_counts.get("escalated", 0),
        resolved_count=status_counts.get("resolved", 0) + status_counts.get("credit_issued", 0),
        total_disputed_amount=total_amount,
        sla_breached_count=sla_breached,
        by_reason=by_reason,
        by_priority=by_priority,
    )
