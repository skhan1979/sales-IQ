"""
Sales IQ - CFO Dashboard Service
Day 15: Enhanced AR analytics, write-off management, IFRS 9 ECL provisioning engine.
"""

import math
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import (
    Customer, Invoice, Payment, WriteOff, Dispute,
    CustomerStatus, InvoiceStatus, CreditApprovalStatus, ECLStage,
)


class CFODashboardService:
    """CFO-oriented dashboard: enhanced AR, write-offs, IFRS 9 provisioning."""

    # ═══════════════════════════════════════════
    # ENHANCED AR DASHBOARD
    # ═══════════════════════════════════════════

    async def get_dso_trend(self, db: AsyncSession, tenant_id: UUID, months: int = 6) -> dict:
        """Monthly DSO trend for chart rendering."""
        today = date.today()
        points = []

        for i in range(months - 1, -1, -1):
            # Calculate month boundaries
            ref = today.replace(day=1) - timedelta(days=i * 28)
            month_start = ref.replace(day=1)
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)

            # Total receivables at month end
            recv_q = await db.execute(
                select(func.coalesce(func.sum(Invoice.amount_remaining), 0)).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.status.in_(["open", "partially_paid", "overdue"]),
                    Invoice.invoice_date <= month_end,
                )
            )
            receivables = float(recv_q.scalar() or 0)

            # Credit sales during the 90-day window ending at month_end
            window_start = month_end - timedelta(days=90)
            sales_q = await db.execute(
                select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.invoice_date >= window_start,
                    Invoice.invoice_date <= month_end,
                )
            )
            credit_sales = float(sales_q.scalar() or 1)

            dso = (receivables / credit_sales) * 90 if credit_sales > 0 else 0
            points.append({
                "month": month_start.strftime("%Y-%m"),
                "dso": round(dso, 1),
                "total_receivables": round(receivables, 2),
                "credit_sales": round(credit_sales, 2),
            })

        dso_values = [p["dso"] for p in points if p["dso"] > 0]
        current = dso_values[-1] if dso_values else 0
        avg = sum(dso_values) / len(dso_values) if dso_values else 0

        # Trend direction
        if len(dso_values) >= 2:
            recent_avg = sum(dso_values[-2:]) / 2
            older_avg = sum(dso_values[:2]) / 2
            if recent_avg < older_avg - 3:
                direction = "improving"
            elif recent_avg > older_avg + 3:
                direction = "worsening"
            else:
                direction = "stable"
        else:
            direction = "stable"

        return {
            "trend": points,
            "current_dso": current,
            "avg_dso": round(avg, 1),
            "best_dso": round(min(dso_values), 1) if dso_values else 0,
            "worst_dso": round(max(dso_values), 1) if dso_values else 0,
            "trend_direction": direction,
        }

    async def get_overdue_trend(self, db: AsyncSession, tenant_id: UUID, months: int = 6) -> dict:
        """Monthly overdue amount trends."""
        today = date.today()
        points = []

        for i in range(months - 1, -1, -1):
            ref = today.replace(day=1) - timedelta(days=i * 28)
            month_start = ref.replace(day=1)
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)

            overdue_q = await db.execute(
                select(
                    func.coalesce(func.sum(Invoice.amount_remaining), 0),
                    func.count(),
                ).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.status.in_(["open", "partially_paid", "overdue"]),
                    Invoice.due_date < month_end,
                    Invoice.invoice_date <= month_end,
                )
            )
            row = overdue_q.one()
            overdue_amt = float(row[0] or 0)
            overdue_cnt = row[1] or 0

            recv_q = await db.execute(
                select(func.coalesce(func.sum(Invoice.amount_remaining), 0)).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.status.in_(["open", "partially_paid", "overdue"]),
                    Invoice.invoice_date <= month_end,
                )
            )
            total_recv = float(recv_q.scalar() or 1)
            overdue_pct = (overdue_amt / total_recv * 100) if total_recv > 0 else 0

            points.append({
                "month": month_start.strftime("%Y-%m"),
                "overdue_amount": round(overdue_amt, 2),
                "overdue_count": overdue_cnt,
                "overdue_pct": round(overdue_pct, 1),
            })

        current = points[-1] if points else {"overdue_amount": 0, "overdue_count": 0}
        currency_q = await db.execute(
            select(Customer.currency).where(Customer.tenant_id == tenant_id).limit(1)
        )
        currency = currency_q.scalar() or "AED"

        return {
            "trend": points,
            "current_overdue": current["overdue_amount"],
            "current_overdue_count": current["overdue_count"],
            "currency": currency,
        }

    async def get_cash_flow_forecast(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """Predict cash inflows for next 30/60/90 days based on payment probability."""
        today = date.today()
        invoices = (await db.execute(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id,
                Invoice.is_deleted == False,
                Invoice.status.in_(["open", "partially_paid", "overdue"]),
            )
        )).scalars().all()

        buckets = []
        for period, label, days_from, days_to in [
            ("30_days", "Next 30 days", 0, 30),
            ("60_days", "31-60 days", 31, 60),
            ("90_days", "61-90 days", 61, 90),
        ]:
            high = 0.0
            medium = 0.0
            low = 0.0
            total = 0.0
            count = 0

            for inv in invoices:
                remaining = float(inv.amount_remaining or inv.amount or 0)
                if remaining <= 0:
                    continue

                prob = float(inv.payment_probability or 0.5)
                predicted = inv.predicted_pay_date
                due = inv.due_date

                # Estimate when payment will arrive
                if predicted:
                    days_until = (predicted - today).days
                elif due:
                    days_until = (due - today).days
                else:
                    days_until = 30

                if days_from <= days_until <= days_to:
                    weighted = remaining * prob
                    total += weighted
                    count += 1

                    if prob > 0.7:
                        high += weighted
                    elif prob > 0.3:
                        medium += weighted
                    else:
                        low += weighted

            buckets.append({
                "period": period,
                "label": label,
                "predicted_inflow": round(total, 2),
                "high_confidence": round(high, 2),
                "medium_confidence": round(medium, 2),
                "low_confidence": round(low, 2),
                "invoice_count": count,
            })

        total_predicted = sum(b["predicted_inflow"] for b in buckets)
        total_high = sum(b["high_confidence"] for b in buckets)
        total_med = sum(b["medium_confidence"] for b in buckets)
        total_low = sum(b["low_confidence"] for b in buckets)

        currency_q = await db.execute(
            select(Customer.currency).where(Customer.tenant_id == tenant_id).limit(1)
        )
        currency = currency_q.scalar() or "AED"

        return {
            "buckets": buckets,
            "total_predicted": round(total_predicted, 2),
            "total_high_confidence": round(total_high, 2),
            "total_medium_confidence": round(total_med, 2),
            "total_low_confidence": round(total_low, 2),
            "currency": currency,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_top_overdue_customers(
        self, db: AsyncSession, tenant_id: UUID, limit: int = 10,
    ) -> dict:
        """Top overdue customers with details for 360 click-through."""
        today = date.today()
        customers = (await db.execute(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                Customer.is_deleted == False,
            )
        )).scalars().all()

        results = []
        for cust in customers:
            overdue_q = await db.execute(
                select(
                    func.coalesce(func.sum(Invoice.amount_remaining), 0),
                    func.count(),
                    func.coalesce(func.max(Invoice.days_overdue), 0),
                ).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.customer_id == cust.id,
                    Invoice.status.in_(["overdue"]),
                    Invoice.due_date < today,
                )
            )
            row = overdue_q.one()
            total_overdue = float(row[0] or 0)
            inv_count = row[1] or 0
            max_days = row[2] or 0

            if total_overdue <= 0:
                continue

            credit_limit = float(cust.credit_limit or 0)
            utilization = float(cust.credit_utilization or 0)
            util_pct = (utilization / credit_limit * 100) if credit_limit > 0 else 0

            # Import health scores if available
            from app.services.intelligence import _health_scores
            hs = _health_scores.get(str(cust.id), {}).get("composite_score")

            results.append({
                "customer_id": str(cust.id),
                "customer_name": cust.name,
                "total_overdue": round(total_overdue, 2),
                "invoice_count": inv_count,
                "max_days_overdue": max_days,
                "credit_limit": credit_limit,
                "utilization_pct": round(util_pct, 1),
                "health_score": hs,
                "risk_score": float(cust.risk_score or 0),
                "currency": cust.currency or "AED",
            })

        results.sort(key=lambda x: x["total_overdue"], reverse=True)
        top = results[:limit]
        total_overdue_amt = sum(r["total_overdue"] for r in top)

        return {
            "items": top,
            "total_overdue_amount": round(total_overdue_amt, 2),
            "currency": "AED",
        }

    # ═══════════════════════════════════════════
    # WRITE-OFF MANAGEMENT
    # ═══════════════════════════════════════════

    async def create_write_off(
        self, db: AsyncSession, tenant_id: UUID, user_id: UUID, data: dict,
    ) -> dict:
        """Create a write-off request with pending approval."""
        customer = (await db.execute(
            select(Customer).where(Customer.id == data["customer_id"], Customer.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if not customer:
            raise ValueError("Customer not found")

        invoice_number = None
        if data.get("invoice_id"):
            invoice = (await db.execute(
                select(Invoice).where(Invoice.id == data["invoice_id"], Invoice.tenant_id == tenant_id)
            )).scalar_one_or_none()
            if not invoice:
                raise ValueError("Invoice not found")
            invoice_number = invoice.invoice_number

        # Determine ECL stage from customer
        ecl_stage = customer.ecl_stage or ECLStage.STAGE_1
        ecl_prob = self._calculate_ecl_probability(customer)

        wo = WriteOff(
            tenant_id=tenant_id,
            created_by=user_id,
            customer_id=data["customer_id"],
            invoice_id=data.get("invoice_id"),
            write_off_type=data.get("write_off_type", "full"),
            amount=Decimal(str(data["amount"])),
            currency=data.get("currency", "AED"),
            ecl_stage=ecl_stage,
            ecl_probability=ecl_prob,
            provision_amount=Decimal(str(float(data["amount"]) * ecl_prob)),
            reason=data.get("reason"),
            approval_status=CreditApprovalStatus.PENDING,
        )
        db.add(wo)
        await db.commit()
        await db.refresh(wo)

        return {
            "id": str(wo.id),
            "customer_id": str(wo.customer_id),
            "customer_name": customer.name,
            "invoice_id": str(wo.invoice_id) if wo.invoice_id else None,
            "invoice_number": invoice_number,
            "write_off_type": wo.write_off_type,
            "amount": float(wo.amount),
            "currency": wo.currency,
            "ecl_stage": wo.ecl_stage.value if wo.ecl_stage else None,
            "ecl_probability": wo.ecl_probability,
            "provision_amount": float(wo.provision_amount) if wo.provision_amount else None,
            "reason": wo.reason,
            "approval_status": wo.approval_status.value if hasattr(wo.approval_status, 'value') else str(wo.approval_status),
            "approved_by_id": None,
            "approved_at": None,
            "is_reversed": False,
            "created_at": str(wo.created_at) if wo.created_at else None,
        }

    async def approve_write_off(
        self, db: AsyncSession, tenant_id: UUID, user_id: UUID,
        write_off_id: UUID, action: str, notes: Optional[str] = None,
        approved_amount: Optional[Decimal] = None,
    ) -> dict:
        """Approve or reject a write-off request."""
        wo = (await db.execute(
            select(WriteOff).where(WriteOff.id == write_off_id, WriteOff.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if not wo:
            raise ValueError("Write-off not found")

        curr_status = wo.approval_status.value if hasattr(wo.approval_status, 'value') else str(wo.approval_status)
        if curr_status != "pending":
            raise ValueError(f"Write-off already processed: {curr_status}")

        now_iso = datetime.now(timezone.utc).isoformat()

        if action == "approve":
            wo.approval_status = CreditApprovalStatus.APPROVED
            wo.approved_by_id = user_id
            wo.approved_at = now_iso
            if approved_amount is not None:
                wo.amount = approved_amount

            # Update invoice status if linked
            if wo.invoice_id:
                invoice = (await db.execute(
                    select(Invoice).where(Invoice.id == wo.invoice_id)
                )).scalar_one_or_none()
                if invoice and wo.write_off_type == "full":
                    invoice.status = InvoiceStatus.WRITTEN_OFF
        else:
            wo.approval_status = CreditApprovalStatus.REJECTED
            wo.approved_by_id = user_id
            wo.approved_at = now_iso

        wo.updated_by = user_id
        await db.commit()
        await db.refresh(wo)

        customer = (await db.execute(
            select(Customer).where(Customer.id == wo.customer_id)
        )).scalar_one_or_none()

        return {
            "id": str(wo.id),
            "customer_id": str(wo.customer_id),
            "customer_name": customer.name if customer else None,
            "invoice_id": str(wo.invoice_id) if wo.invoice_id else None,
            "write_off_type": wo.write_off_type,
            "amount": float(wo.amount),
            "currency": wo.currency,
            "ecl_stage": wo.ecl_stage.value if wo.ecl_stage else None,
            "ecl_probability": wo.ecl_probability,
            "provision_amount": float(wo.provision_amount) if wo.provision_amount else None,
            "reason": wo.reason,
            "approval_status": wo.approval_status.value if hasattr(wo.approval_status, 'value') else str(wo.approval_status),
            "approved_by_id": str(wo.approved_by_id) if wo.approved_by_id else None,
            "approved_at": wo.approved_at,
            "is_reversed": wo.is_reversed,
            "created_at": str(wo.created_at) if wo.created_at else None,
        }

    async def reverse_write_off(
        self, db: AsyncSession, tenant_id: UUID, user_id: UUID,
        write_off_id: UUID, reason: str,
    ) -> dict:
        """Reverse a previously approved write-off."""
        wo = (await db.execute(
            select(WriteOff).where(WriteOff.id == write_off_id, WriteOff.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if not wo:
            raise ValueError("Write-off not found")

        curr_status = wo.approval_status.value if hasattr(wo.approval_status, 'value') else str(wo.approval_status)
        if curr_status != "approved":
            raise ValueError("Can only reverse approved write-offs")
        if wo.is_reversed:
            raise ValueError("Write-off already reversed")

        wo.is_reversed = True
        wo.reversed_at = datetime.now(timezone.utc).isoformat()
        wo.reversed_by_id = user_id
        wo.reversal_reason = reason

        # Restore invoice status if applicable
        if wo.invoice_id:
            invoice = (await db.execute(
                select(Invoice).where(Invoice.id == wo.invoice_id)
            )).scalar_one_or_none()
            if invoice and invoice.status == InvoiceStatus.WRITTEN_OFF:
                invoice.status = InvoiceStatus.OVERDUE

        await db.commit()
        await db.refresh(wo)

        customer = (await db.execute(
            select(Customer).where(Customer.id == wo.customer_id)
        )).scalar_one_or_none()

        return {
            "id": str(wo.id),
            "customer_id": str(wo.customer_id),
            "customer_name": customer.name if customer else None,
            "write_off_type": wo.write_off_type,
            "amount": float(wo.amount),
            "currency": wo.currency,
            "approval_status": wo.approval_status.value if hasattr(wo.approval_status, 'value') else str(wo.approval_status),
            "is_reversed": True,
            "reversed_at": wo.reversed_at,
            "reversal_reason": reason,
            "created_at": str(wo.created_at) if wo.created_at else None,
        }

    async def list_write_offs(
        self, db: AsyncSession, tenant_id: UUID,
        status: Optional[str] = None, customer_id: Optional[UUID] = None,
        page: int = 1, page_size: int = 20,
    ) -> dict:
        """List write-offs with filtering and summary."""
        query = select(WriteOff).where(WriteOff.tenant_id == tenant_id)
        if status:
            query = query.where(WriteOff.approval_status == status)
        if customer_id:
            query = query.where(WriteOff.customer_id == customer_id)

        count_q = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_q)).scalar() or 0

        query = query.order_by(WriteOff.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        items = (await db.execute(query)).scalars().all()

        # Summary of ALL write-offs (not just paginated)
        all_q = select(WriteOff).where(WriteOff.tenant_id == tenant_id)
        all_wos = (await db.execute(all_q)).scalars().all()

        approved = [w for w in all_wos if (w.approval_status.value if hasattr(w.approval_status, 'value') else str(w.approval_status)) == "approved" and not w.is_reversed]
        pending = [w for w in all_wos if (w.approval_status.value if hasattr(w.approval_status, 'value') else str(w.approval_status)) == "pending"]
        reversed_wos = [w for w in all_wos if w.is_reversed]

        by_type = defaultdict(float)
        by_stage = defaultdict(float)
        for w in approved:
            by_type[w.write_off_type] += float(w.amount or 0)
            stage = w.ecl_stage.value if w.ecl_stage else "unknown"
            by_stage[stage] += float(w.amount or 0)

        summary = {
            "total_written_off": round(sum(float(w.amount or 0) for w in approved), 2),
            "total_pending": round(sum(float(w.amount or 0) for w in pending), 2),
            "total_approved": round(sum(float(w.amount or 0) for w in approved), 2),
            "total_reversed": round(sum(float(w.amount or 0) for w in reversed_wos), 2),
            "by_type": dict(by_type),
            "by_ecl_stage": dict(by_stage),
            "write_off_count": len(all_wos),
            "currency": "AED",
        }

        # Build response items
        response_items = []
        for w in items:
            cust = (await db.execute(
                select(Customer.name).where(Customer.id == w.customer_id)
            )).scalar()
            inv_num = None
            if w.invoice_id:
                inv_num = (await db.execute(
                    select(Invoice.invoice_number).where(Invoice.id == w.invoice_id)
                )).scalar()

            response_items.append({
                "id": str(w.id),
                "customer_id": str(w.customer_id),
                "customer_name": cust,
                "invoice_id": str(w.invoice_id) if w.invoice_id else None,
                "invoice_number": inv_num,
                "write_off_type": w.write_off_type,
                "amount": float(w.amount),
                "currency": w.currency,
                "ecl_stage": w.ecl_stage.value if w.ecl_stage else None,
                "ecl_probability": w.ecl_probability,
                "provision_amount": float(w.provision_amount) if w.provision_amount else None,
                "reason": w.reason,
                "approval_status": w.approval_status.value if hasattr(w.approval_status, 'value') else str(w.approval_status),
                "approved_by_id": str(w.approved_by_id) if w.approved_by_id else None,
                "approved_at": w.approved_at,
                "is_reversed": w.is_reversed,
                "created_at": str(w.created_at) if w.created_at else None,
            })

        return {"items": response_items, "total": total, "page": page, "page_size": page_size, "summary": summary}

    # ═══════════════════════════════════════════
    # IFRS 9 ECL PROVISIONING ENGINE
    # ═══════════════════════════════════════════

    def _calculate_ecl_probability(self, customer) -> float:
        """Calculate Expected Credit Loss probability based on customer data."""
        risk = float(customer.risk_score or 50)
        ecl_stage = str(customer.ecl_stage) if customer.ecl_stage else "stage_1"

        # Base probability by ECL stage
        if "stage_3" in ecl_stage:
            base_prob = 0.60  # Credit-impaired
        elif "stage_2" in ecl_stage:
            base_prob = 0.25  # Significant deterioration
        else:
            base_prob = 0.05  # Performing

        # Adjust by risk score
        risk_adj = (risk - 50) / 200  # -0.25 to +0.25
        prob = base_prob + risk_adj

        # Adjust for credit hold
        if customer.credit_hold:
            prob += 0.10

        return round(max(0.01, min(0.95, prob)), 4)

    def _traditional_aging_provision(self, invoices: list) -> float:
        """Calculate provision using traditional aging percentage method."""
        today = date.today()
        total = 0.0
        # Standard aging percentages
        rates = {
            "current": 0.01,
            "1-30": 0.03,
            "31-60": 0.10,
            "61-90": 0.25,
            "90+": 0.50,
        }

        for inv in invoices:
            remaining = float(inv.amount_remaining or inv.amount or 0)
            if remaining <= 0:
                continue

            due = inv.due_date
            if not due:
                total += remaining * 0.05
                continue

            days = (today - due).days
            if days <= 0:
                total += remaining * rates["current"]
            elif days <= 30:
                total += remaining * rates["1-30"]
            elif days <= 60:
                total += remaining * rates["31-60"]
            elif days <= 90:
                total += remaining * rates["61-90"]
            else:
                total += remaining * rates["90+"]

        return round(total, 2)

    async def run_ecl_provisioning(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """Run IFRS 9 ECL provisioning engine across all customers."""
        start = time.time()

        customers = (await db.execute(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                Customer.is_deleted == False,
            )
        )).scalars().all()

        results = []
        total_exposure = 0.0
        total_ml = 0.0
        total_trad = 0.0
        by_stage = defaultdict(lambda: {"count": 0, "exposure": 0, "ml_provision": 0, "trad_provision": 0})

        for cust in customers:
            invoices = (await db.execute(
                select(Invoice).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.customer_id == cust.id,
                    Invoice.is_deleted == False,
                    Invoice.status.in_(["open", "partially_paid", "overdue"]),
                )
            )).scalars().all()

            if not invoices:
                continue

            exposure = sum(float(i.amount_remaining or i.amount or 0) for i in invoices)
            if exposure <= 0:
                continue

            ecl_prob = self._calculate_ecl_probability(cust)
            ecl_stage = str(cust.ecl_stage.value) if cust.ecl_stage else "stage_1"

            # ML-based provision (ECL probability * exposure, adjusted by stage)
            if "stage_3" in ecl_stage:
                ml_provision = exposure * ecl_prob * 1.2  # Lifetime ECL with impairment markup
            elif "stage_2" in ecl_stage:
                ml_provision = exposure * ecl_prob * 1.0  # Lifetime ECL
            else:
                # 12-month ECL: probability * exposure * (12-month fraction)
                ml_provision = exposure * ecl_prob * 0.8

            trad_provision = self._traditional_aging_provision(invoices)

            diff = ml_provision - trad_provision
            if diff > trad_provision * 0.1:
                prov_status = "under_provisioned"
            elif diff < -trad_provision * 0.1:
                prov_status = "over_provisioned"
            else:
                prov_status = "adequate"

            # Key factors
            factors = []
            risk = float(cust.risk_score or 50)
            if risk > 70:
                factors.append(f"High risk score ({risk:.0f})")
            overdue_count = sum(1 for i in invoices if i.status == InvoiceStatus.OVERDUE)
            if overdue_count > 0:
                factors.append(f"{overdue_count} overdue invoices")
            if cust.credit_hold:
                factors.append("Credit hold active")
            if "stage_2" in ecl_stage or "stage_3" in ecl_stage:
                factors.append(f"ECL {ecl_stage.replace('_', ' ').title()}")
            if not factors:
                factors.append("Standard performing account")

            from app.services.intelligence import _health_scores
            hs = _health_scores.get(str(cust.id), {}).get("composite_score")

            results.append({
                "customer_id": str(cust.id),
                "customer_name": cust.name,
                "ecl_stage": ecl_stage,
                "ecl_probability": ecl_prob,
                "total_exposure": round(exposure, 2),
                "provision_required": round(ml_provision, 2),
                "traditional_provision": round(trad_provision, 2),
                "provision_difference": round(diff, 2),
                "provision_status": prov_status,
                "risk_score": risk,
                "health_score": hs,
                "key_factors": factors,
                "currency": cust.currency or "AED",
            })

            total_exposure += exposure
            total_ml += ml_provision
            total_trad += trad_provision
            by_stage[ecl_stage]["count"] += 1
            by_stage[ecl_stage]["exposure"] += exposure
            by_stage[ecl_stage]["ml_provision"] += ml_provision
            by_stage[ecl_stage]["trad_provision"] += trad_provision

            # Update customer ECL data
            cust.ecl_stage = ECLStage(ecl_stage) if ecl_stage in [e.value for e in ECLStage] else cust.ecl_stage

        await db.commit()

        # Round stage values
        for stage in by_stage:
            by_stage[stage] = {k: round(v, 2) if isinstance(v, float) else v for k, v in by_stage[stage].items()}

        under = sum(1 for r in results if r["provision_status"] == "under_provisioned")
        over = sum(1 for r in results if r["provision_status"] == "over_provisioned")
        adequate = sum(1 for r in results if r["provision_status"] == "adequate")

        # Generate recommendations
        recommendations = []
        under_prov = [r for r in results if r["provision_status"] == "under_provisioned"]
        under_prov.sort(key=lambda x: x["provision_difference"], reverse=True)
        for up in under_prov[:5]:
            recommendations.append({
                "type": "increase_provision",
                "customer": up["customer_name"],
                "current_traditional": up["traditional_provision"],
                "recommended_ml": up["provision_required"],
                "gap": up["provision_difference"],
                "reason": f"ML model suggests {up['provision_difference']:,.0f} additional provision based on {', '.join(up['key_factors'][:2])}",
            })

        duration_ms = int((time.time() - start) * 1000)

        return {
            "customers_analyzed": len(results),
            "total_exposure": round(total_exposure, 2),
            "total_ml_provision": round(total_ml, 2),
            "total_traditional_provision": round(total_trad, 2),
            "provision_gap": round(total_ml - total_trad, 2),
            "by_stage": dict(by_stage),
            "under_provisioned_count": under,
            "over_provisioned_count": over,
            "adequate_count": adequate,
            "recommendations": recommendations,
            "model_version": "v1.0-ecl-simulated",
            "currency": "AED",
            "duration_ms": duration_ms,
        }

    async def get_provisioning_dashboard(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """Provisioning dashboard with movement analysis and adequacy metrics."""
        # Get all write-offs for movement analysis
        write_offs = (await db.execute(
            select(WriteOff).where(WriteOff.tenant_id == tenant_id)
        )).scalars().all()

        approved_wos = [w for w in write_offs
                        if (w.approval_status.value if hasattr(w.approval_status, 'value') else str(w.approval_status)) == "approved"
                        and not w.is_reversed]

        total_current = sum(float(w.provision_amount or 0) for w in approved_wos)
        new_provisions = sum(float(w.provision_amount or 0) for w in approved_wos if w.write_off_type == "provision")
        written_off = sum(float(w.amount or 0) for w in approved_wos if w.write_off_type in ("full", "partial"))
        released = sum(float(w.amount or 0) for w in write_offs if w.is_reversed)

        # Run ECL to get required provision
        ecl_result = await self.run_ecl_provisioning(db, tenant_id)
        total_required = ecl_result["total_ml_provision"]

        adequacy = (total_current / total_required * 100) if total_required > 0 else 100

        # By stage
        by_stage = {}
        for stage, data in ecl_result["by_stage"].items():
            by_stage[stage] = {
                "exposure": data["exposure"],
                "ml_provision": data["ml_provision"],
                "traditional_provision": data["trad_provision"],
                "count": data["count"],
            }

        # By segment
        customers = (await db.execute(
            select(Customer).where(Customer.tenant_id == tenant_id, Customer.is_deleted == False)
        )).scalars().all()

        seg_map = {str(c.id): c.segment or "unclassified" for c in customers}
        by_segment = defaultdict(lambda: {"exposure": 0, "provision": 0, "count": 0})
        for r in ecl_result.get("recommendations", []):
            pass  # recommendations don't have customer_id readily accessible

        # Build from ECL internal data (re-query simpler approach)
        invoices = (await db.execute(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id,
                Invoice.is_deleted == False,
                Invoice.status.in_(["open", "partially_paid", "overdue"]),
            )
        )).scalars().all()

        for inv in invoices:
            seg = seg_map.get(str(inv.customer_id), "unclassified")
            remaining = float(inv.amount_remaining or inv.amount or 0)
            by_segment[seg]["exposure"] += remaining
            by_segment[seg]["count"] += 1

        for seg in by_segment:
            by_segment[seg]["exposure"] = round(by_segment[seg]["exposure"], 2)

        # Top under-provisioned
        top_under = ecl_result["recommendations"][:5]

        return {
            "total_provision_required": round(total_required, 2),
            "total_current_provision": round(total_current, 2),
            "provision_adequacy_ratio": round(adequacy, 1),
            "movement_analysis": {
                "new_provisions": round(new_provisions, 2),
                "releases": round(released, 2),
                "write_offs": round(written_off, 2),
                "net_change": round(new_provisions - released - written_off, 2),
            },
            "by_stage": by_stage,
            "by_segment": dict(by_segment),
            "top_under_provisioned": top_under,
            "ai_vs_traditional": {
                "ai_total": round(ecl_result["total_ml_provision"], 2),
                "traditional_total": round(ecl_result["total_traditional_provision"], 2),
                "difference": round(ecl_result["provision_gap"], 2),
                "pct_difference": round(
                    (ecl_result["provision_gap"] / ecl_result["total_traditional_provision"] * 100)
                    if ecl_result["total_traditional_provision"] > 0 else 0, 1
                ),
            },
            "currency": "AED",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


# Singleton
cfo_dashboard = CFODashboardService()
