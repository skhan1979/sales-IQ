"""
Sales IQ - Payment CRUD Endpoints
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
from app.models.business import Payment, Invoice, Customer, InvoiceStatus
from app.schemas.business import (
    PaymentCreate,
    PaymentUpdate,
    PaymentResponse,
    PaymentListResponse,
)

router = APIRouter()


@router.get("/", response_model=PaymentListResponse)
async def list_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[UUID] = None,
    invoice_id: Optional[UUID] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    is_matched: Optional[bool] = None,
    search: Optional[str] = None,
    sort_by: str = Query("payment_date", regex="^(payment_date|amount)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List payments with filtering and pagination."""
    query = select(Payment).where(Payment.tenant_id == current_user.tenant_id)

    if customer_id:
        query = query.where(Payment.customer_id == customer_id)
    if invoice_id:
        query = query.where(Payment.invoice_id == invoice_id)
    if from_date:
        query = query.where(Payment.payment_date >= from_date)
    if to_date:
        query = query.where(Payment.payment_date <= to_date)
    if is_matched is not None:
        query = query.where(Payment.is_matched == is_matched)
    if search:
        like = f"%{search}%"
        query = query.where(
            (Payment.reference_number.ilike(like))
            | (Payment.bank_reference.ilike(like))
        )

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    sort_col = getattr(Payment, sort_by, Payment.payment_date)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    payments = result.scalars().all()

    # Hydrate customer names and invoice numbers
    customer_ids = list({p.customer_id for p in payments})
    invoice_ids = list({p.invoice_id for p in payments if p.invoice_id})
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
    for p in payments:
        data = PaymentResponse.model_validate(p)
        data.customer_name = cust_map.get(p.customer_id)
        if p.invoice_id:
            data.invoice_number = inv_map.get(p.invoice_id)
        items.append(data)

    return PaymentListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create_payment(
    request: PaymentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a new payment and optionally match it to an invoice."""
    # Verify customer
    cust = await db.execute(
        select(Customer).where(
            Customer.id == request.customer_id,
            Customer.tenant_id == current_user.tenant_id,
        )
    )
    if not cust.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Customer not found")

    payment = Payment(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        **request.model_dump(),
    )

    # If invoice_id provided, auto-match and update invoice
    if request.invoice_id:
        inv_result = await db.execute(
            select(Invoice).where(
                Invoice.id == request.invoice_id,
                Invoice.tenant_id == current_user.tenant_id,
            )
        )
        invoice = inv_result.scalar_one_or_none()
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")

        # Apply payment to invoice
        invoice.amount_paid = (invoice.amount_paid or Decimal("0")) + request.amount
        invoice.amount_remaining = invoice.amount - invoice.amount_paid - invoice.discount_amount

        if invoice.amount_remaining <= 0:
            invoice.amount_remaining = Decimal("0")
            invoice.status = InvoiceStatus.PAID
        elif invoice.amount_paid > 0:
            invoice.status = InvoiceStatus.PARTIALLY_PAID

        payment.is_matched = True
        payment.matched_at = datetime.now(timezone.utc).isoformat()
        payment.match_confidence = 1.0  # Manual match = 100% confidence

    db.add(payment)

    # Update credit utilization
    from app.api.v1.endpoints.invoices import _update_credit_utilization
    await _update_credit_utilization(db, request.customer_id, current_user.tenant_id)

    audit = AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_email=current_user.email,
        action="CREATE",
        entity_type="payments",
        after_state={
            "amount": str(request.amount),
            "customer_id": str(request.customer_id),
            "invoice_id": str(request.invoice_id) if request.invoice_id else None,
        },
    )
    db.add(audit)
    await db.commit()
    await db.refresh(payment)

    return PaymentResponse.model_validate(payment)


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a payment by ID."""
    result = await db.execute(
        select(Payment).where(
            Payment.id == payment_id,
            Payment.tenant_id == current_user.tenant_id,
        )
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    data = PaymentResponse.model_validate(payment)
    # Hydrate customer name
    cust_result = await db.execute(
        select(Customer.name).where(Customer.id == payment.customer_id)
    )
    data.customer_name = cust_result.scalar_one_or_none()
    # Hydrate invoice number
    if payment.invoice_id:
        inv_result = await db.execute(
            select(Invoice.invoice_number).where(Invoice.id == payment.invoice_id)
        )
        data.invoice_number = inv_result.scalar_one_or_none()
    return data


@router.patch("/{payment_id}", response_model=PaymentResponse)
async def update_payment(
    payment_id: UUID,
    request: PaymentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a payment record."""
    result = await db.execute(
        select(Payment).where(
            Payment.id == payment_id,
            Payment.tenant_id == current_user.tenant_id,
        )
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(payment, field, value)

    payment.updated_by = current_user.id
    await db.commit()
    await db.refresh(payment)

    return PaymentResponse.model_validate(payment)
