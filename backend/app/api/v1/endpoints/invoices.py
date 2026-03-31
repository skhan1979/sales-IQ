"""
Sales IQ - Invoice CRUD Endpoints
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.core import User, AuditLog
from app.models.business import Invoice, Customer, InvoiceStatus
from app.schemas.business import (
    InvoiceCreate,
    InvoiceUpdate,
    InvoiceResponse,
    InvoiceListResponse,
)

router = APIRouter()


def _calculate_aging(due_date: date) -> tuple[int, str]:
    """Calculate days overdue and aging bucket."""
    today = date.today()
    if due_date >= today:
        return 0, "current"
    days = (today - due_date).days
    if days <= 30:
        return days, "1-30"
    elif days <= 60:
        return days, "31-60"
    elif days <= 90:
        return days, "61-90"
    else:
        return days, "90+"


@router.get("/", response_model=InvoiceListResponse)
async def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    aging_bucket: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    search: Optional[str] = None,
    sort_by: str = Query("due_date", regex="^(due_date|invoice_date|amount|amount_remaining|days_overdue)$"),
    sort_order: str = Query("asc", regex="^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List invoices with filtering and pagination."""
    query = select(Invoice).where(Invoice.tenant_id == current_user.tenant_id)

    if customer_id:
        query = query.where(Invoice.customer_id == customer_id)
    if status_filter:
        query = query.where(Invoice.status == status_filter)
    if aging_bucket:
        query = query.where(Invoice.aging_bucket == aging_bucket)
    if from_date:
        query = query.where(Invoice.invoice_date >= from_date)
    if to_date:
        query = query.where(Invoice.invoice_date <= to_date)
    if min_amount is not None:
        query = query.where(Invoice.amount >= min_amount)
    if max_amount is not None:
        query = query.where(Invoice.amount <= max_amount)
    if search:
        like = f"%{search}%"
        query = query.where(
            (Invoice.invoice_number.ilike(like))
            | (Invoice.po_number.ilike(like))
        )

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    sort_col = getattr(Invoice, sort_by, Invoice.due_date)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    invoices = result.scalars().all()

    # Hydrate customer names
    customer_ids = list({inv.customer_id for inv in invoices})
    cust_map = {}
    if customer_ids:
        cust_result = await db.execute(
            select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids))
        )
        cust_map = {row.id: row.name for row in cust_result.all()}

    items = []
    for inv in invoices:
        data = InvoiceResponse.model_validate(inv)
        data.customer_name = cust_map.get(inv.customer_id)
        items.append(data)

    return InvoiceListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    request: InvoiceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new invoice."""
    # Verify customer
    cust = await db.execute(
        select(Customer).where(
            Customer.id == request.customer_id,
            Customer.tenant_id == current_user.tenant_id,
        )
    )
    if not cust.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Customer not found")

    # Check duplicate invoice number
    dup = await db.execute(
        select(Invoice).where(
            Invoice.tenant_id == current_user.tenant_id,
            Invoice.invoice_number == request.invoice_number,
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Invoice '{request.invoice_number}' already exists")

    days_overdue, bucket = _calculate_aging(request.due_date)
    amount_remaining = request.amount - request.discount_amount

    invoice = Invoice(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        amount_remaining=amount_remaining,
        days_overdue=days_overdue,
        aging_bucket=bucket,
        amount_paid=Decimal("0"),
        **request.model_dump(),
    )

    # Update status based on dates
    if days_overdue > 0 and request.status == "open":
        invoice.status = InvoiceStatus.OVERDUE

    db.add(invoice)

    # Update customer credit utilization
    await _update_credit_utilization(db, request.customer_id, current_user.tenant_id)

    audit = AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_email=current_user.email,
        action="CREATE",
        entity_type="invoices",
        after_state={"invoice_number": request.invoice_number, "amount": str(request.amount)},
    )
    db.add(audit)
    await db.commit()
    await db.refresh(invoice)

    return InvoiceResponse.model_validate(invoice)


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get an invoice by ID."""
    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == current_user.tenant_id,
        )
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    data = InvoiceResponse.model_validate(invoice)
    # Hydrate customer name
    cust_result = await db.execute(
        select(Customer.name).where(Customer.id == invoice.customer_id)
    )
    cust_name = cust_result.scalar_one_or_none()
    data.customer_name = cust_name
    return data


@router.patch("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: UUID,
    request: InvoiceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an invoice."""
    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.tenant_id == current_user.tenant_id,
        )
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    before = {}
    after = {}
    for field, value in request.model_dump(exclude_unset=True).items():
        old = getattr(invoice, field, None)
        before[field] = str(old) if old is not None else None
        after[field] = str(value) if value is not None else None
        setattr(invoice, field, value)

    # Recalculate remaining and aging
    invoice.amount_remaining = invoice.amount - invoice.amount_paid - invoice.discount_amount
    if invoice.amount_remaining <= 0:
        invoice.amount_remaining = Decimal("0")
        invoice.status = InvoiceStatus.PAID

    days_overdue, bucket = _calculate_aging(invoice.due_date)
    invoice.days_overdue = days_overdue
    invoice.aging_bucket = bucket

    invoice.updated_by = current_user.id

    audit = AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_email=current_user.email,
        action="UPDATE",
        entity_type="invoices",
        entity_id=invoice_id,
        before_state=before,
        after_state=after,
    )
    db.add(audit)

    await _update_credit_utilization(db, invoice.customer_id, current_user.tenant_id)
    await db.commit()
    await db.refresh(invoice)

    return InvoiceResponse.model_validate(invoice)


async def _update_credit_utilization(db: AsyncSession, customer_id: UUID, tenant_id: UUID):
    """Recalculate and update customer credit utilization from open invoices."""
    result = await db.execute(
        select(func.coalesce(func.sum(Invoice.amount_remaining), 0)).where(
            Invoice.customer_id == customer_id,
            Invoice.tenant_id == tenant_id,
            Invoice.status.in_(["open", "partially_paid", "overdue"]),
        )
    )
    total_outstanding = result.scalar() or Decimal("0")

    cust_result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant_id)
    )
    customer = cust_result.scalar_one_or_none()
    if customer:
        customer.credit_utilization = total_outstanding
        # Auto credit hold check
        if customer.credit_limit > 0:
            utilization_pct = (float(total_outstanding) / float(customer.credit_limit)) * 100
            if utilization_pct >= customer.credit_hold_threshold:
                customer.credit_hold = True
            else:
                customer.credit_hold = False
