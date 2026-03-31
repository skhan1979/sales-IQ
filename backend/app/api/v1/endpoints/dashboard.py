"""
Sales IQ - AR Dashboard Endpoints
Summary KPIs, aging analysis, and recent activity.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.core import User
from app.models.business import Customer, Invoice, Payment
from app.schemas.business import ARSummary, AgingBucket

router = APIRouter()


@router.get("/ar-summary", response_model=ARSummary)
async def get_ar_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get Accounts Receivable summary with aging buckets and KPIs.
    This powers the main dashboard for CFOs and Finance Managers.
    """
    tid = current_user.tenant_id
    today = date.today()

    # Total receivables
    total_q = await db.execute(
        select(func.coalesce(func.sum(Invoice.amount_remaining), 0)).where(
            Invoice.tenant_id == tid,
            Invoice.status.in_(["open", "partially_paid", "overdue"]),
        )
    )
    total_receivables = total_q.scalar() or Decimal("0")

    # Total overdue
    overdue_q = await db.execute(
        select(func.coalesce(func.sum(Invoice.amount_remaining), 0)).where(
            Invoice.tenant_id == tid,
            Invoice.status.in_(["open", "partially_paid", "overdue"]),
            Invoice.due_date < today,
        )
    )
    total_overdue = overdue_q.scalar() or Decimal("0")

    # Customer counts
    total_customers_q = await db.execute(
        select(func.count()).where(
            Customer.tenant_id == tid,
            Customer.is_deleted == False,
            Customer.status == "active",
        )
    )
    total_customers = total_customers_q.scalar() or 0

    hold_q = await db.execute(
        select(func.count()).where(
            Customer.tenant_id == tid,
            Customer.is_deleted == False,
            Customer.credit_hold == True,
        )
    )
    customers_on_hold = hold_q.scalar() or 0

    # Average DSO (Days Sales Outstanding)
    # DSO = (Total Receivables / Total Credit Sales in last 90 days) * 90
    ninety_days_ago = today - timedelta(days=90)
    credit_sales_q = await db.execute(
        select(func.coalesce(func.sum(Invoice.amount), 0)).where(
            Invoice.tenant_id == tid,
            Invoice.invoice_date >= ninety_days_ago,
        )
    )
    credit_sales_90d = credit_sales_q.scalar() or Decimal("1")
    if credit_sales_90d > 0:
        avg_dso = (float(total_receivables) / float(credit_sales_90d)) * 90
    else:
        avg_dso = 0.0

    # Collection rate (payments last 30 days vs invoiced last 30 days)
    thirty_days_ago = today - timedelta(days=30)
    payments_30d_q = await db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.tenant_id == tid,
            Payment.payment_date >= thirty_days_ago,
        )
    )
    payments_30d = payments_30d_q.scalar() or Decimal("0")

    invoiced_30d_q = await db.execute(
        select(func.coalesce(func.sum(Invoice.amount), 0)).where(
            Invoice.tenant_id == tid,
            Invoice.invoice_date >= thirty_days_ago,
        )
    )
    invoiced_30d = invoiced_30d_q.scalar() or Decimal("1")
    collection_rate = min(float(payments_30d) / float(invoiced_30d) * 100, 100.0) if invoiced_30d > 0 else 0.0

    # Aging buckets
    aging_data = []
    buckets = [
        ("current", Invoice.due_date >= today),
        ("1-30", and_(Invoice.due_date < today, Invoice.due_date >= today - timedelta(days=30))),
        ("31-60", and_(Invoice.due_date < today - timedelta(days=30), Invoice.due_date >= today - timedelta(days=60))),
        ("61-90", and_(Invoice.due_date < today - timedelta(days=60), Invoice.due_date >= today - timedelta(days=90))),
        ("90+", Invoice.due_date < today - timedelta(days=90)),
    ]

    for bucket_name, condition in buckets:
        bq = await db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(Invoice.amount_remaining), 0),
            ).where(
                Invoice.tenant_id == tid,
                Invoice.status.in_(["open", "partially_paid", "overdue"]),
                condition,
            )
        )
        row = bq.one()
        count = row[0] or 0
        amount = row[1] or Decimal("0")
        pct = float(amount) / float(total_receivables) * 100 if total_receivables > 0 else 0.0

        aging_data.append(AgingBucket(
            bucket=bucket_name,
            count=count,
            amount=amount,
            percentage=round(pct, 1),
        ))

    # Get tenant currency
    tenant_result = await db.execute(
        select(Customer.currency).where(Customer.tenant_id == tid).limit(1)
    )
    currency = tenant_result.scalar() or "AED"

    return ARSummary(
        total_receivables=total_receivables,
        total_overdue=total_overdue,
        total_customers=total_customers,
        customers_on_credit_hold=customers_on_hold,
        average_dso=round(avg_dso, 1),
        collection_rate=round(collection_rate, 1),
        aging_buckets=aging_data,
        currency=currency,
    )


@router.get("/top-overdue")
async def get_top_overdue(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get top overdue invoices sorted by amount remaining."""
    result = await db.execute(
        select(Invoice)
        .where(
            Invoice.tenant_id == current_user.tenant_id,
            Invoice.status.in_(["overdue", "open"]),
            Invoice.due_date < date.today(),
        )
        .order_by(Invoice.amount_remaining.desc())
        .limit(limit)
    )
    invoices = result.scalars().all()

    from app.schemas.business import InvoiceResponse
    return [InvoiceResponse.model_validate(inv).model_dump() for inv in invoices]


@router.get("/collection-effectiveness")
async def get_collection_effectiveness(
    months: int = Query(6, ge=1, le=24),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Monthly collection effectiveness trend for charts."""
    today = date.today()
    tid = current_user.tenant_id
    trends = []

    for i in range(months - 1, -1, -1):
        month_start = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)

        inv_q = await db.execute(
            select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                Invoice.tenant_id == tid,
                Invoice.invoice_date >= month_start,
                Invoice.invoice_date <= month_end,
            )
        )
        invoiced = inv_q.scalar() or Decimal("0")

        pay_q = await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.tenant_id == tid,
                Payment.payment_date >= month_start,
                Payment.payment_date <= month_end,
            )
        )
        collected = pay_q.scalar() or Decimal("0")

        rate = float(collected) / float(invoiced) * 100 if invoiced > 0 else 0.0

        trends.append({
            "month": month_start.strftime("%Y-%m"),
            "invoiced": float(invoiced),
            "collected": float(collected),
            "rate": round(rate, 1),
        })

    return trends
