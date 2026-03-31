"""
Sales IQ - Customer CRUD Endpoints
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.middleware.audit import TerritoryFilterMiddleware
from app.models.core import User, AuditLog
from app.models.business import Customer, Invoice, InvoiceStatus
from app.schemas.business import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerListResponse,
)

router = APIRouter()


@router.get("/", response_model=CustomerListResponse)
async def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    industry: Optional[str] = None,
    territory: Optional[str] = None,
    segment: Optional[str] = None,
    search: Optional[str] = None,
    credit_hold: Optional[bool] = None,
    sort_by: str = Query("name", regex="^(name|credit_limit|risk_score|created_at)$"),
    sort_order: str = Query("asc", regex="^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List customers with filtering, territory scoping, and pagination."""
    query = select(Customer).where(
        Customer.tenant_id == current_user.tenant_id,
        Customer.is_deleted == False,
    )

    # Territory scoping
    territories = TerritoryFilterMiddleware.get_user_territories(current_user)
    if territories is not None:
        if not territories:
            return CustomerListResponse(items=[], total=0, page=page, page_size=page_size)
        query = query.where(Customer.assigned_sales_rep_id.in_(
            select(User.id).where(User.territory_ids.overlap(territories))
        ))

    # Filters
    if status_filter:
        query = query.where(Customer.status == status_filter)
    if industry:
        query = query.where(Customer.industry == industry)
    if territory:
        query = query.where(Customer.territory == territory)
    if segment:
        query = query.where(Customer.segment == segment)
    if credit_hold is not None:
        query = query.where(Customer.credit_hold == credit_hold)
    if search:
        like = f"%{search}%"
        query = query.where(
            (Customer.name.ilike(like))
            | (Customer.name_ar.ilike(like))
            | (Customer.email.ilike(like))
            | (Customer.external_id.ilike(like))
        )

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Sort
    sort_col = getattr(Customer, sort_by, Customer.name)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    customers = result.scalars().all()

    return CustomerListResponse(
        items=[CustomerResponse.model_validate(c) for c in customers],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    request: CustomerCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new customer."""
    # Check duplicate within tenant
    if request.external_id and request.source_system:
        existing = await db.execute(
            select(Customer).where(
                Customer.tenant_id == current_user.tenant_id,
                Customer.external_id == request.external_id,
                Customer.source_system == request.source_system,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Customer with external_id '{request.external_id}' already exists",
            )

    customer = Customer(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        **request.model_dump(exclude_none=True),
    )
    db.add(customer)

    audit = AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_email=current_user.email,
        action="CREATE",
        entity_type="customers",
        after_state={"name": request.name},
    )
    db.add(audit)
    await db.commit()
    await db.refresh(customer)

    return CustomerResponse.model_validate(customer)


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a customer by ID."""
    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.tenant_id == current_user.tenant_id,
            Customer.is_deleted == False,
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return CustomerResponse.model_validate(customer)


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: UUID,
    request: CustomerUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a customer."""
    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.tenant_id == current_user.tenant_id,
            Customer.is_deleted == False,
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    before = {}
    after = {}
    for field, value in request.model_dump(exclude_unset=True).items():
        old = getattr(customer, field, None)
        before[field] = str(old) if old is not None else None
        after[field] = str(value) if value is not None else None
        setattr(customer, field, value)

    customer.updated_by = current_user.id

    audit = AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_email=current_user.email,
        action="UPDATE",
        entity_type="customers",
        entity_id=customer_id,
        before_state=before,
        after_state=after,
    )
    db.add(audit)
    await db.commit()
    await db.refresh(customer)

    return CustomerResponse.model_validate(customer)


@router.delete("/{customer_id}", status_code=status.HTTP_200_OK)
async def delete_customer(
    customer_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a customer."""
    from datetime import datetime, timezone

    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.tenant_id == current_user.tenant_id,
            Customer.is_deleted == False,
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer.is_deleted = True
    customer.deleted_at = datetime.now(timezone.utc)
    customer.deleted_by = current_user.id

    audit = AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_email=current_user.email,
        action="DELETE",
        entity_type="customers",
        entity_id=customer_id,
        before_state={"name": customer.name},
    )
    db.add(audit)
    await db.commit()

    return {"message": f"Customer '{customer.name}' deleted"}


@router.get("/{customer_id}/statement")
async def get_customer_statement(
    customer_id: UUID,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get customer account statement with open invoices and recent payments."""
    # Verify customer exists
    cust_result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.tenant_id == current_user.tenant_id,
            Customer.is_deleted == False,
        )
    )
    customer = cust_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Open invoices
    inv_query = select(Invoice).where(
        Invoice.tenant_id == current_user.tenant_id,
        Invoice.customer_id == customer_id,
        Invoice.status.in_(["open", "partially_paid", "overdue"]),
    )
    if from_date:
        inv_query = inv_query.where(Invoice.invoice_date >= from_date)
    if to_date:
        inv_query = inv_query.where(Invoice.invoice_date <= to_date)

    inv_result = await db.execute(inv_query.order_by(Invoice.due_date))
    invoices = inv_result.scalars().all()

    from app.schemas.business import InvoiceResponse

    return {
        "customer": {
            "id": str(customer.id),
            "name": customer.name,
            "currency": customer.currency,
            "credit_limit": float(customer.credit_limit),
            "credit_utilization": float(customer.credit_utilization),
            "payment_terms_days": customer.payment_terms_days,
        },
        "open_invoices": [InvoiceResponse.model_validate(i).model_dump() for i in invoices],
        "total_outstanding": float(sum(i.amount_remaining for i in invoices)),
        "invoice_count": len(invoices),
    }
