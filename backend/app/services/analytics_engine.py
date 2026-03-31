"""
Sales IQ - Analytics & Reporting Engine
Day 11: KPI computation, trend analysis, period comparisons, and report generation.
Operates against live DB data via SQLAlchemy async queries.
"""

import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, func, case, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import (
    Customer, Invoice, Payment, Dispute, CollectionActivity, CreditLimitRequest,
    CustomerStatus, InvoiceStatus, DisputeStatus,
)


class AnalyticsEngine:
    """Computes financial KPIs, trends, and reports from tenant data."""

    # ── KPI Dashboard ──

    async def get_kpi_dashboard(
        self, db: AsyncSession, tenant_id: UUID,
        date_from: date, date_to: date,
        previous_from: Optional[date] = None, previous_to: Optional[date] = None,
    ) -> dict:
        """Compute core AR/collection KPIs for the given period."""
        start = time.time()

        # Default previous period = same length, immediately prior
        period_days = (date_to - date_from).days
        if not previous_from:
            previous_to = date_from - timedelta(days=1)
            previous_from = previous_to - timedelta(days=period_days)

        current = await self._compute_period_kpis(db, tenant_id, date_from, date_to)
        previous = await self._compute_period_kpis(db, tenant_id, previous_from, previous_to)

        kpis = []
        for key, meta in self._KPI_META.items():
            curr_val = current.get(key, 0)
            prev_val = previous.get(key, 0)
            change_pct = self._pct_change(curr_val, prev_val)
            trend = "up" if change_pct > 1 else ("down" if change_pct < -1 else "flat")

            kpis.append({
                "name": key,
                "value": round(curr_val, 2),
                "previous_value": round(prev_val, 2),
                "change_pct": round(change_pct, 2),
                "trend": trend,
                "unit": meta["unit"],
                "target": meta.get("target"),
                "target_met": curr_val <= meta["target"] if meta.get("target") and meta.get("lower_better")
                              else (curr_val >= meta["target"] if meta.get("target") else None),
            })

        return {
            "period": {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
            "kpis": kpis,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    _KPI_META = {
        "total_ar": {"unit": "currency", "target": None},
        "overdue_ar": {"unit": "currency", "target": None},
        "overdue_pct": {"unit": "percent", "target": 15.0, "lower_better": True},
        "dso": {"unit": "days", "target": 45.0, "lower_better": True},
        "collection_rate": {"unit": "percent", "target": 85.0},
        "dispute_count_open": {"unit": "count", "target": None},
        "dispute_resolution_rate": {"unit": "percent", "target": 90.0},
        "avg_days_to_pay": {"unit": "days", "target": 30.0, "lower_better": True},
        "payment_count": {"unit": "count", "target": None},
        "payment_total": {"unit": "currency", "target": None},
        "customer_count_active": {"unit": "count", "target": None},
        "credit_hold_count": {"unit": "count", "target": None},
    }

    async def _compute_period_kpis(
        self, db: AsyncSession, tenant_id: UUID, date_from: date, date_to: date,
    ) -> dict:
        """Compute raw KPI values for a single period."""
        kpis: Dict[str, float] = {}

        # ── Invoice-based KPIs ──
        inv_q = select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.is_deleted == False,
        )
        invoices = (await db.execute(inv_q)).scalars().all()

        total_ar = sum(float(i.amount_remaining or 0) for i in invoices if i.status != InvoiceStatus.PAID)
        overdue_invoices = [i for i in invoices if i.status == InvoiceStatus.OVERDUE]
        overdue_ar = sum(float(i.amount_remaining or 0) for i in overdue_invoices)

        kpis["total_ar"] = total_ar
        kpis["overdue_ar"] = overdue_ar
        kpis["overdue_pct"] = (overdue_ar / total_ar * 100) if total_ar > 0 else 0

        # DSO = (Total AR / Total Credit Sales in Period) * Days in Period
        period_days = max((date_to - date_from).days, 1)
        period_invoices = [i for i in invoices if i.invoice_date and date_from <= i.invoice_date <= date_to]
        credit_sales = sum(float(i.amount or 0) for i in period_invoices)
        kpis["dso"] = (total_ar / credit_sales * period_days) if credit_sales > 0 else 0

        # ── Payment-based KPIs ──
        pay_q = select(Payment).where(
            Payment.tenant_id == tenant_id,
            Payment.is_deleted == False,
            Payment.payment_date >= date_from,
            Payment.payment_date <= date_to,
        )
        payments = (await db.execute(pay_q)).scalars().all()
        payment_total = sum(float(p.amount or 0) for p in payments)
        kpis["payment_count"] = len(payments)
        kpis["payment_total"] = payment_total
        kpis["collection_rate"] = (payment_total / (total_ar + payment_total) * 100) if (total_ar + payment_total) > 0 else 0

        # Average days to pay (for matched payments with invoice)
        days_to_pay_list = []
        for p in payments:
            if p.invoice_id:
                inv_result = await db.execute(select(Invoice).where(Invoice.id == p.invoice_id))
                inv = inv_result.scalar_one_or_none()
                if inv and inv.invoice_date and p.payment_date:
                    delta = (p.payment_date - inv.invoice_date).days
                    if delta >= 0:
                        days_to_pay_list.append(delta)
        kpis["avg_days_to_pay"] = (sum(days_to_pay_list) / len(days_to_pay_list)) if days_to_pay_list else 0

        # ── Dispute KPIs ──
        disp_q = select(Dispute).where(Dispute.tenant_id == tenant_id, Dispute.is_deleted == False)
        disputes = (await db.execute(disp_q)).scalars().all()
        open_disputes = [d for d in disputes if d.status in (DisputeStatus.OPEN, DisputeStatus.IN_REVIEW, DisputeStatus.ESCALATED)]
        resolved_disputes = [d for d in disputes if d.status in (DisputeStatus.RESOLVED, DisputeStatus.CREDIT_ISSUED)]
        kpis["dispute_count_open"] = len(open_disputes)
        kpis["dispute_resolution_rate"] = (len(resolved_disputes) / len(disputes) * 100) if disputes else 0

        # ── Customer KPIs ──
        cust_q = select(Customer).where(Customer.tenant_id == tenant_id, Customer.is_deleted == False)
        customers = (await db.execute(cust_q)).scalars().all()
        kpis["customer_count_active"] = sum(1 for c in customers if c.status == CustomerStatus.ACTIVE)
        kpis["credit_hold_count"] = sum(1 for c in customers if c.credit_hold)

        return kpis

    # ── Trend Analysis ──

    async def get_trends(
        self, db: AsyncSession, tenant_id: UUID,
        metrics: List[str], date_from: date, date_to: date,
        granularity: str = "weekly",
    ) -> dict:
        """Compute time-series trends for specified metrics."""
        intervals = self._build_intervals(date_from, date_to, granularity)
        series = []

        for metric in metrics:
            data_points = []
            for interval_start, interval_end in intervals:
                value = await self._compute_trend_point(db, tenant_id, metric, interval_start, interval_end)
                data_points.append({
                    "date": interval_start.isoformat(),
                    "value": round(value, 2),
                    "label": f"{interval_start.strftime('%b %d')}",
                })

            values = [dp["value"] for dp in data_points]
            summary = {
                "min": min(values) if values else 0,
                "max": max(values) if values else 0,
                "avg": round(sum(values) / len(values), 2) if values else 0,
            }

            display_names = {
                "total_ar": "Total Accounts Receivable",
                "overdue_ar": "Overdue AR",
                "dso": "Days Sales Outstanding",
                "collection_rate": "Collection Rate",
                "payment_total": "Payments Collected",
                "dispute_count_open": "Open Disputes",
                "invoice_count": "Invoices Raised",
            }

            series.append({
                "metric": metric,
                "display_name": display_names.get(metric, metric.replace("_", " ").title()),
                "data": data_points,
                "summary": summary,
            })

        return {
            "period": {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
            "series": series,
        }

    async def _compute_trend_point(
        self, db: AsyncSession, tenant_id: UUID,
        metric: str, d_from: date, d_to: date,
    ) -> float:
        """Compute a single data point for a trend metric."""
        if metric == "total_ar":
            invoices = (await db.execute(
                select(Invoice).where(
                    Invoice.tenant_id == tenant_id, Invoice.is_deleted == False,
                    Invoice.invoice_date <= d_to,
                )
            )).scalars().all()
            return sum(float(i.amount_remaining or 0) for i in invoices if i.status != InvoiceStatus.PAID)

        elif metric == "overdue_ar":
            invoices = (await db.execute(
                select(Invoice).where(
                    Invoice.tenant_id == tenant_id, Invoice.is_deleted == False,
                    Invoice.status == InvoiceStatus.OVERDUE,
                    Invoice.due_date <= d_to,
                )
            )).scalars().all()
            return sum(float(i.amount_remaining or 0) for i in invoices)

        elif metric == "payment_total":
            result = await db.execute(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.tenant_id == tenant_id, Payment.is_deleted == False,
                    Payment.payment_date >= d_from, Payment.payment_date <= d_to,
                )
            )
            return float(result.scalar() or 0)

        elif metric == "invoice_count":
            result = await db.execute(
                select(func.count()).where(
                    Invoice.tenant_id == tenant_id, Invoice.is_deleted == False,
                    Invoice.invoice_date >= d_from, Invoice.invoice_date <= d_to,
                )
            )
            return float(result.scalar() or 0)

        elif metric == "dispute_count_open":
            result = await db.execute(
                select(func.count()).where(
                    Dispute.tenant_id == tenant_id, Dispute.is_deleted == False,
                    Dispute.status.in_(["open", "in_review", "escalated"]),
                )
            )
            return float(result.scalar() or 0)

        elif metric == "dso":
            kpis = await self._compute_period_kpis(db, tenant_id, d_from, d_to)
            return kpis.get("dso", 0)

        elif metric == "collection_rate":
            kpis = await self._compute_period_kpis(db, tenant_id, d_from, d_to)
            return kpis.get("collection_rate", 0)

        return 0

    # ── Period Comparison ──

    async def get_period_comparison(
        self, db: AsyncSession, tenant_id: UUID,
        current_from: date, current_to: date,
        previous_from: date, previous_to: date,
    ) -> dict:
        """Compare KPIs between two periods."""
        current = await self._compute_period_kpis(db, tenant_id, current_from, current_to)
        previous = await self._compute_period_kpis(db, tenant_id, previous_from, previous_to)

        comparisons = []
        display_names = {
            "total_ar": "Total AR", "overdue_ar": "Overdue AR",
            "overdue_pct": "Overdue %", "dso": "DSO",
            "collection_rate": "Collection Rate", "payment_total": "Payments",
            "payment_count": "Payment Count", "dispute_count_open": "Open Disputes",
            "dispute_resolution_rate": "Dispute Resolution %",
            "avg_days_to_pay": "Avg Days to Pay",
            "customer_count_active": "Active Customers",
            "credit_hold_count": "Credit Holds",
        }

        for key in self._KPI_META:
            curr_val = current.get(key, 0)
            prev_val = previous.get(key, 0)
            change = curr_val - prev_val
            change_pct = self._pct_change(curr_val, prev_val)
            trend = "up" if change_pct > 1 else ("down" if change_pct < -1 else "flat")

            comparisons.append({
                "metric": key,
                "display_name": display_names.get(key, key.replace("_", " ").title()),
                "current_value": round(curr_val, 2),
                "previous_value": round(prev_val, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "trend": trend,
            })

        return {
            "current_period": {"date_from": current_from.isoformat(), "date_to": current_to.isoformat()},
            "previous_period": {"date_from": previous_from.isoformat(), "date_to": previous_to.isoformat()},
            "comparisons": comparisons,
        }

    # ── Customer Analytics ──

    async def get_customer_analytics(
        self, db: AsyncSession, tenant_id: UUID,
        date_from: date, date_to: date,
        sort_by: str = "overdue_amount", sort_desc: bool = True,
        limit: int = 50,
    ) -> dict:
        """Per-customer analytics breakdown."""
        customers = (await db.execute(
            select(Customer).where(
                Customer.tenant_id == tenant_id, Customer.is_deleted == False,
                Customer.status != CustomerStatus.INACTIVE,
            )
        )).scalars().all()

        items = []
        for c in customers:
            invoices = (await db.execute(
                select(Invoice).where(
                    Invoice.tenant_id == tenant_id, Invoice.customer_id == c.id,
                    Invoice.is_deleted == False,
                )
            )).scalars().all()

            payments = (await db.execute(
                select(Payment).where(
                    Payment.tenant_id == tenant_id, Payment.customer_id == c.id,
                    Payment.is_deleted == False,
                    Payment.payment_date >= date_from, Payment.payment_date <= date_to,
                )
            )).scalars().all()

            disputes = (await db.execute(
                select(Dispute).where(
                    Dispute.tenant_id == tenant_id, Dispute.customer_id == c.id,
                    Dispute.is_deleted == False,
                )
            )).scalars().all()

            total_ar = sum(float(i.amount_remaining or 0) for i in invoices if i.status != InvoiceStatus.PAID)
            overdue_amount = sum(float(i.amount_remaining or 0) for i in invoices if i.status == InvoiceStatus.OVERDUE)
            overdue_count = sum(1 for i in invoices if i.status == InvoiceStatus.OVERDUE)
            payment_total = sum(float(p.amount or 0) for p in payments)
            credit_limit = float(c.credit_limit or 0)
            utilization = (total_ar / credit_limit * 100) if credit_limit > 0 else 0

            # Average days to pay
            day_list = []
            for p in payments:
                if p.invoice_id:
                    for inv in invoices:
                        if inv.id == p.invoice_id and inv.invoice_date and p.payment_date:
                            day_list.append((p.payment_date - inv.invoice_date).days)
            avg_dtp = (sum(day_list) / len(day_list)) if day_list else 0

            # Collection effectiveness
            billed = sum(float(i.amount or 0) for i in invoices if i.invoice_date and date_from <= i.invoice_date <= date_to)
            coll_eff = (payment_total / billed * 100) if billed > 0 else 0

            items.append({
                "customer_id": str(c.id),
                "customer_name": c.name,
                "total_ar": round(total_ar, 2),
                "overdue_amount": round(overdue_amount, 2),
                "total_invoices": len(invoices),
                "overdue_invoices": overdue_count,
                "avg_days_to_pay": round(avg_dtp, 1),
                "risk_score": c.risk_score,
                "credit_utilization_pct": round(utilization, 1),
                "collection_effectiveness": round(coll_eff, 1),
                "dispute_count": len(disputes),
                "payment_count": len(payments),
            })

        # Sort
        reverse = sort_desc
        items.sort(key=lambda x: x.get(sort_by, 0) or 0, reverse=reverse)
        items = items[:limit]

        return {
            "items": items,
            "total": len(items),
            "period": {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
        }

    # ── Reports ──

    async def generate_report(
        self, db: AsyncSession, tenant_id: UUID,
        report_type: str, date_from: date, date_to: date,
        filters: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """Generate a structured report."""
        start = time.time()

        if report_type == "ar_aging":
            data, summary = await self._report_ar_aging(db, tenant_id)
        elif report_type == "dso_trend":
            data, summary = await self._report_dso_trend(db, tenant_id, date_from, date_to)
        elif report_type == "collection_performance":
            data, summary = await self._report_collection_performance(db, tenant_id, date_from, date_to)
        elif report_type == "customer_risk":
            data, summary = await self._report_customer_risk(db, tenant_id)
        elif report_type == "executive_summary":
            data, summary = await self._report_executive_summary(db, tenant_id, date_from, date_to)
        else:
            data, summary = [], {"error": f"Unknown report type: {report_type}"}

        titles = {
            "ar_aging": "Accounts Receivable Aging Report",
            "dso_trend": "DSO Trend Analysis",
            "collection_performance": "Collection Performance Report",
            "customer_risk": "Customer Risk Assessment",
            "executive_summary": "Executive Summary Report",
        }

        return {
            "report_type": report_type,
            "title": titles.get(report_type, report_type.replace("_", " ").title()),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period": {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
            "data": data,
            "summary": summary,
            "row_count": len(data) if isinstance(data, list) else 1,
        }

    async def _report_ar_aging(self, db: AsyncSession, tenant_id: UUID):
        """AR Aging report grouped by bucket."""
        invoices = (await db.execute(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id, Invoice.is_deleted == False,
                Invoice.status != InvoiceStatus.PAID,
            )
        )).scalars().all()

        buckets = {"current": 0, "1-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
        rows = []
        today = date.today()

        for inv in invoices:
            days = (today - inv.due_date).days if inv.due_date else 0
            if days <= 0:
                bucket = "current"
            elif days <= 30:
                bucket = "1-30"
            elif days <= 60:
                bucket = "31-60"
            elif days <= 90:
                bucket = "61-90"
            else:
                bucket = "90+"

            amt = float(inv.amount_remaining or 0)
            buckets[bucket] += amt
            rows.append({
                "invoice_number": inv.invoice_number,
                "customer_id": str(inv.customer_id),
                "amount": amt,
                "due_date": str(inv.due_date),
                "days_overdue": max(days, 0),
                "bucket": bucket,
                "currency": inv.currency,
            })

        total = sum(buckets.values())
        summary = {
            "total_ar": round(total, 2),
            "buckets": {k: round(v, 2) for k, v in buckets.items()},
            "bucket_pct": {k: round(v / total * 100, 1) if total > 0 else 0 for k, v in buckets.items()},
            "invoice_count": len(rows),
        }
        return rows, summary

    async def _report_dso_trend(self, db: AsyncSession, tenant_id: UUID, date_from: date, date_to: date):
        """DSO trend over weekly intervals."""
        intervals = self._build_intervals(date_from, date_to, "weekly")
        data = []
        for start, end in intervals:
            kpis = await self._compute_period_kpis(db, tenant_id, start, end)
            data.append({
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "dso": round(kpis.get("dso", 0), 1),
                "total_ar": round(kpis.get("total_ar", 0), 2),
            })

        dso_values = [d["dso"] for d in data]
        summary = {
            "avg_dso": round(sum(dso_values) / len(dso_values), 1) if dso_values else 0,
            "min_dso": min(dso_values) if dso_values else 0,
            "max_dso": max(dso_values) if dso_values else 0,
            "trend": "improving" if len(dso_values) > 1 and dso_values[-1] < dso_values[0] else "worsening",
            "data_points": len(data),
        }
        return data, summary

    async def _report_collection_performance(self, db: AsyncSession, tenant_id: UUID, date_from: date, date_to: date):
        """Collection performance breakdown."""
        payments = (await db.execute(
            select(Payment).where(
                Payment.tenant_id == tenant_id, Payment.is_deleted == False,
                Payment.payment_date >= date_from, Payment.payment_date <= date_to,
            )
        )).scalars().all()

        activities = (await db.execute(
            select(CollectionActivity).where(
                CollectionActivity.tenant_id == tenant_id,
                CollectionActivity.action_date >= date_from,
                CollectionActivity.action_date <= date_to,
            )
        )).scalars().all()

        action_breakdown = defaultdict(int)
        ptp_total = 0
        ptp_fulfilled = 0
        for a in activities:
            action_type = a.action_type.value if hasattr(a.action_type, 'value') else str(a.action_type)
            action_breakdown[action_type] += 1
            if a.ptp_date:
                ptp_total += 1
                if a.ptp_fulfilled:
                    ptp_fulfilled += 1

        payment_total = sum(float(p.amount or 0) for p in payments)

        data = [{
            "total_collected": round(payment_total, 2),
            "payment_count": len(payments),
            "collection_activities": len(activities),
            "action_breakdown": dict(action_breakdown),
            "ptp_total": ptp_total,
            "ptp_fulfilled": ptp_fulfilled,
            "ptp_fulfillment_rate": round(ptp_fulfilled / ptp_total * 100, 1) if ptp_total > 0 else 0,
        }]

        summary = {
            "total_collected": round(payment_total, 2),
            "avg_payment": round(payment_total / len(payments), 2) if payments else 0,
            "activities_per_payment": round(len(activities) / len(payments), 1) if payments else 0,
            "ptp_effectiveness": round(ptp_fulfilled / ptp_total * 100, 1) if ptp_total > 0 else 0,
        }
        return data, summary

    async def _report_customer_risk(self, db: AsyncSession, tenant_id: UUID):
        """Customer risk matrix."""
        customers = (await db.execute(
            select(Customer).where(
                Customer.tenant_id == tenant_id, Customer.is_deleted == False,
            )
        )).scalars().all()

        data = []
        risk_dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for c in customers:
            score = c.risk_score or 0
            if score >= 80:
                level = "critical"
            elif score >= 60:
                level = "high"
            elif score >= 40:
                level = "medium"
            else:
                level = "low"

            risk_dist[level] += 1
            data.append({
                "customer_id": str(c.id),
                "customer_name": c.name,
                "risk_score": score,
                "risk_level": level,
                "credit_limit": float(c.credit_limit or 0),
                "credit_utilization": float(c.credit_utilization or 0),
                "credit_hold": c.credit_hold,
                "ecl_stage": c.ecl_stage.value if hasattr(c.ecl_stage, 'value') else str(c.ecl_stage),
                "status": c.status.value if hasattr(c.status, 'value') else str(c.status),
            })

        data.sort(key=lambda x: x["risk_score"], reverse=True)
        summary = {
            "total_customers": len(data),
            "risk_distribution": risk_dist,
            "avg_risk_score": round(sum(d["risk_score"] for d in data) / len(data), 1) if data else 0,
            "credit_holds": sum(1 for d in data if d["credit_hold"]),
        }
        return data, summary

    async def _report_executive_summary(self, db: AsyncSession, tenant_id: UUID, date_from: date, date_to: date):
        """High-level executive summary combining key metrics."""
        kpis = await self._compute_period_kpis(db, tenant_id, date_from, date_to)

        period_days = max((date_to - date_from).days, 1)
        prev_to = date_from - timedelta(days=1)
        prev_from = prev_to - timedelta(days=period_days)
        prev_kpis = await self._compute_period_kpis(db, tenant_id, prev_from, prev_to)

        data = {
            "current_period": {k: round(v, 2) for k, v in kpis.items()},
            "previous_period": {k: round(v, 2) for k, v in prev_kpis.items()},
            "changes": {},
        }
        for key in kpis:
            data["changes"][key] = round(self._pct_change(kpis.get(key, 0), prev_kpis.get(key, 0)), 2)

        # Top concerns
        concerns = []
        if kpis.get("overdue_pct", 0) > 20:
            concerns.append(f"High overdue percentage: {kpis['overdue_pct']:.1f}%")
        if kpis.get("dso", 0) > 60:
            concerns.append(f"Elevated DSO: {kpis['dso']:.0f} days")
        if kpis.get("credit_hold_count", 0) > 0:
            concerns.append(f"{int(kpis['credit_hold_count'])} customer(s) on credit hold")
        if kpis.get("dispute_count_open", 0) > 5:
            concerns.append(f"{int(kpis['dispute_count_open'])} open disputes")

        summary = {
            "health_score": self._compute_health_score(kpis),
            "top_concerns": concerns,
            "total_ar": round(kpis.get("total_ar", 0), 2),
            "dso": round(kpis.get("dso", 0), 1),
            "collection_rate": round(kpis.get("collection_rate", 0), 1),
        }
        return data, summary

    # ── Helpers ──

    @staticmethod
    def _pct_change(current: float, previous: float) -> float:
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return ((current - previous) / abs(previous)) * 100

    @staticmethod
    def _build_intervals(date_from: date, date_to: date, granularity: str) -> List[tuple]:
        intervals = []
        if granularity == "daily":
            step = timedelta(days=1)
        elif granularity == "weekly":
            step = timedelta(days=7)
        elif granularity == "monthly":
            step = timedelta(days=30)
        else:
            step = timedelta(days=7)

        current = date_from
        while current < date_to:
            end = min(current + step - timedelta(days=1), date_to)
            intervals.append((current, end))
            current = current + step
        return intervals

    @staticmethod
    def _compute_health_score(kpis: dict) -> float:
        """Compute a composite AR health score (0-100, higher = healthier)."""
        score = 100.0

        # Penalize high overdue %
        overdue_pct = kpis.get("overdue_pct", 0)
        if overdue_pct > 10:
            score -= min(overdue_pct - 10, 30)

        # Penalize high DSO
        dso = kpis.get("dso", 0)
        if dso > 45:
            score -= min((dso - 45) * 0.5, 20)

        # Reward collection rate
        coll_rate = kpis.get("collection_rate", 0)
        if coll_rate < 80:
            score -= min((80 - coll_rate) * 0.5, 15)

        # Penalize credit holds
        holds = kpis.get("credit_hold_count", 0)
        score -= min(holds * 3, 15)

        # Penalize open disputes
        disputes = kpis.get("dispute_count_open", 0)
        score -= min(disputes * 2, 10)

        return max(round(score, 1), 0)


# Singleton
analytics_engine = AnalyticsEngine()
