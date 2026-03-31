"""
Sales IQ - Executive Dashboard Service
Day 17: KPI Engine, trend sparklines, AI-generated executive summary,
        role-based home screens, and configurable widget system.
"""

import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import (
    Customer, Invoice, Payment, CollectionActivity, Dispute,
    CustomerStatus, InvoiceStatus,
)
from app.models.core import UserRole


# ═══════════════════════════════════════════════
# In-memory stores (MVP)
# ═══════════════════════════════════════════════

# user_id -> widget layout
_user_widget_configs: Dict[str, dict] = {}

# Simple cache: key -> {"data": ..., "expires": timestamp}
_dashboard_cache: Dict[str, dict] = {}

CACHE_TTL_SECONDS = 300  # 5 minutes


def _cache_get(key: str) -> Optional[Any]:
    entry = _dashboard_cache.get(key)
    if entry and entry["expires"] > time.time():
        return entry["data"]
    if entry:
        del _dashboard_cache[key]
    return None


def _cache_set(key: str, data: Any):
    _dashboard_cache[key] = {
        "data": data,
        "expires": time.time() + CACHE_TTL_SECONDS,
    }


# ═══════════════════════════════════════════════
# Widget Definitions
# ═══════════════════════════════════════════════

WIDGET_DEFINITIONS = [
    {
        "widget_id": "my_tasks",
        "title": "My Tasks",
        "description": "Your prioritized action items for today",
        "widget_type": "tasks",
        "default_size": "medium",
        "available_for_roles": ["cfo", "finance_manager", "collector", "sales_rep", "tenant_admin"],
    },
    {
        "widget_id": "top_overdue",
        "title": "Top Overdue",
        "description": "Largest overdue invoices requiring attention",
        "widget_type": "list",
        "default_size": "medium",
        "available_for_roles": ["cfo", "finance_manager", "collector", "tenant_admin"],
    },
    {
        "widget_id": "todays_briefing",
        "title": "Today's Briefing",
        "description": "AI-generated daily executive summary",
        "widget_type": "summary",
        "default_size": "large",
        "available_for_roles": ["cfo", "finance_manager", "tenant_admin"],
    },
    {
        "widget_id": "cash_flow_forecast",
        "title": "Cash Flow Forecast",
        "description": "30/60/90-day predicted cash inflows",
        "widget_type": "chart",
        "default_size": "large",
        "available_for_roles": ["cfo", "finance_manager", "tenant_admin"],
    },
    {
        "widget_id": "churn_alerts",
        "title": "Churn Alerts",
        "description": "Customers at risk of churning with recommended actions",
        "widget_type": "list",
        "default_size": "medium",
        "available_for_roles": ["cfo", "sales_rep", "finance_manager", "tenant_admin"],
    },
    {
        "widget_id": "ptp_due_today",
        "title": "PTP Due Today",
        "description": "Promise-to-pay commitments expiring today",
        "widget_type": "list",
        "default_size": "small",
        "available_for_roles": ["collector", "finance_manager", "tenant_admin"],
    },
    {
        "widget_id": "credit_holds",
        "title": "Credit Holds",
        "description": "Customers currently on credit hold",
        "widget_type": "list",
        "default_size": "small",
        "available_for_roles": ["cfo", "finance_manager", "collector", "tenant_admin"],
    },
    {
        "widget_id": "dispute_queue",
        "title": "Dispute Queue",
        "description": "Open disputes requiring resolution",
        "widget_type": "list",
        "default_size": "medium",
        "available_for_roles": ["cfo", "finance_manager", "collector", "tenant_admin"],
    },
    {
        "widget_id": "kpi_cards",
        "title": "KPI Cards",
        "description": "Key performance indicators with trend sparklines",
        "widget_type": "metric",
        "default_size": "full_width",
        "available_for_roles": ["cfo", "finance_manager", "tenant_admin"],
    },
    {
        "widget_id": "pipeline_snapshot",
        "title": "Sales Pipeline",
        "description": "Pipeline funnel from invoice lifecycle stages",
        "widget_type": "chart",
        "default_size": "medium",
        "available_for_roles": ["cfo", "sales_rep", "finance_manager", "tenant_admin"],
    },
    {
        "widget_id": "reorder_alerts",
        "title": "Reorder Alerts",
        "description": "Customers overdue for reordering",
        "widget_type": "list",
        "default_size": "medium",
        "available_for_roles": ["sales_rep", "finance_manager", "tenant_admin"],
    },
    {
        "widget_id": "team_performance",
        "title": "Team Performance",
        "description": "Collector and sales team productivity metrics",
        "widget_type": "chart",
        "default_size": "large",
        "available_for_roles": ["finance_manager", "tenant_admin"],
    },
    {
        "widget_id": "system_health",
        "title": "System Health",
        "description": "Sync status, error counts, and connector health",
        "widget_type": "summary",
        "default_size": "medium",
        "available_for_roles": ["tenant_admin", "super_admin"],
    },
    {
        "widget_id": "health_distribution",
        "title": "Health Distribution",
        "description": "Customer health grade distribution chart",
        "widget_type": "chart",
        "default_size": "small",
        "available_for_roles": ["cfo", "finance_manager", "sales_rep", "tenant_admin"],
    },
]

# Default widget layouts per role
ROLE_DEFAULT_WIDGETS = {
    "cfo": [
        "kpi_cards", "todays_briefing", "top_overdue", "cash_flow_forecast",
        "health_distribution", "credit_holds", "dispute_queue", "churn_alerts",
    ],
    "collector": [
        "my_tasks", "ptp_due_today", "top_overdue", "credit_holds",
        "dispute_queue",
    ],
    "sales_rep": [
        "my_tasks", "reorder_alerts", "churn_alerts", "pipeline_snapshot",
        "health_distribution",
    ],
    "finance_manager": [
        "kpi_cards", "todays_briefing", "team_performance", "top_overdue",
        "cash_flow_forecast", "dispute_queue", "credit_holds",
    ],
    "tenant_admin": [
        "system_health", "kpi_cards", "todays_briefing", "top_overdue",
        "team_performance",
    ],
    "super_admin": [
        "system_health",
    ],
    "viewer": [
        "kpi_cards", "health_distribution",
    ],
}


class ExecutiveDashboardService:
    """Executive dashboard: KPI engine, AI summaries, role-based home screens."""

    # ═══════════════════════════════════════════
    # KPI ENGINE
    # ═══════════════════════════════════════════

    async def get_kpi_cards(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """Build KPI cards with trend sparklines."""
        cache_key = f"kpi:{tenant_id}"
        cached = _cache_get(cache_key)
        if cached:
            return cached

        today = date.today()
        now_str = datetime.now(timezone.utc).isoformat()

        # ── Total AR ──
        ar_q = await db.execute(
            select(func.coalesce(func.sum(Invoice.amount_remaining), 0)).where(
                Invoice.tenant_id == tenant_id,
                Invoice.status.in_([InvoiceStatus.OPEN, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE]),
            )
        )
        total_ar = float(ar_q.scalar() or 0)

        # Prior period AR (30d ago snapshot approximation)
        thirty_ago = today - timedelta(days=30)
        prior_ar_q = await db.execute(
            select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                Invoice.tenant_id == tenant_id,
                Invoice.invoice_date <= thirty_ago,
                Invoice.status.in_([InvoiceStatus.OPEN, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE]),
            )
        )
        prior_ar = float(prior_ar_q.scalar() or 0)
        ar_change = ((total_ar - prior_ar) / prior_ar * 100) if prior_ar > 0 else 0

        # AR sparkline (7-day and 30-day)
        ar_7d = await self._build_trend(db, tenant_id, "ar", 7)
        ar_30d = await self._build_trend(db, tenant_id, "ar", 30)

        # ── Average DSO ──
        # DSO = (total receivables / total credit sales) * days
        credit_sales_q = await db.execute(
            select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                Invoice.tenant_id == tenant_id,
                Invoice.invoice_date >= today - timedelta(days=90),
            )
        )
        credit_sales_90 = float(credit_sales_q.scalar() or 1)
        avg_dso = (total_ar / (credit_sales_90 / 90)) if credit_sales_90 > 0 else 0
        avg_dso = min(avg_dso, 365)

        dso_7d = await self._build_trend(db, tenant_id, "dso", 7)
        dso_30d = await self._build_trend(db, tenant_id, "dso", 30)

        # ── Collection Rate (30d) ──
        pay_q = await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.tenant_id == tenant_id,
                Payment.payment_date >= thirty_ago,
            )
        )
        inv_q = await db.execute(
            select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                Invoice.tenant_id == tenant_id,
                Invoice.invoice_date >= thirty_ago,
            )
        )
        collected = float(pay_q.scalar() or 0)
        invoiced = float(inv_q.scalar() or 1)
        coll_rate = min(collected / invoiced * 100, 100) if invoiced > 0 else 0

        # Prior period collection rate
        sixty_ago = today - timedelta(days=60)
        prior_pay_q = await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.tenant_id == tenant_id,
                Payment.payment_date >= sixty_ago,
                Payment.payment_date < thirty_ago,
            )
        )
        prior_inv_q = await db.execute(
            select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                Invoice.tenant_id == tenant_id,
                Invoice.invoice_date >= sixty_ago,
                Invoice.invoice_date < thirty_ago,
            )
        )
        prior_collected = float(prior_pay_q.scalar() or 0)
        prior_invoiced = float(prior_inv_q.scalar() or 1)
        prior_coll = min(prior_collected / prior_invoiced * 100, 100) if prior_invoiced > 0 else 0
        coll_change = coll_rate - prior_coll

        coll_7d = await self._build_trend(db, tenant_id, "collection_rate", 7)
        coll_30d = await self._build_trend(db, tenant_id, "collection_rate", 30)

        # ── Churn Risk Count ──
        churn_q = await db.execute(
            select(func.count()).where(
                Customer.tenant_id == tenant_id,
                Customer.is_deleted == False,
                Customer.churn_probability >= 0.3,
            )
        )
        churn_count = churn_q.scalar() or 0

        # ── Pipeline Value ──
        pipeline_q = await db.execute(
            select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                Invoice.tenant_id == tenant_id,
                Invoice.is_deleted == False,
            )
        )
        pipeline_value = float(pipeline_q.scalar() or 0)

        # ── Credit Exposure ──
        credit_q = await db.execute(
            select(
                func.coalesce(func.sum(Customer.credit_utilization), 0),
                func.coalesce(func.sum(Customer.credit_limit), 0),
            ).where(
                Customer.tenant_id == tenant_id,
                Customer.is_deleted == False,
            )
        )
        row = credit_q.one()
        total_util = float(row[0] or 0)
        total_limit = float(row[1] or 1)
        credit_exposure_pct = (total_util / total_limit * 100) if total_limit > 0 else 0

        # ── Overdue Amount ──
        overdue_q = await db.execute(
            select(func.coalesce(func.sum(Invoice.amount_remaining), 0)).where(
                Invoice.tenant_id == tenant_id,
                Invoice.status == InvoiceStatus.OVERDUE,
            )
        )
        total_overdue = float(overdue_q.scalar() or 0)

        def _fmt_amount(v):
            if v >= 1_000_000:
                return f"{v / 1_000_000:.1f}M AED"
            elif v >= 1_000:
                return f"{v / 1_000:.0f}K AED"
            return f"{v:,.0f} AED"

        def _direction(pct):
            if pct > 1:
                return "up"
            elif pct < -1:
                return "down"
            return "flat"

        cards = [
            {
                "key": "total_ar",
                "label": "Total AR Outstanding",
                "value": round(total_ar, 2),
                "formatted_value": _fmt_amount(total_ar),
                "unit": "AED",
                "change_pct": round(ar_change, 1),
                "change_direction": _direction(ar_change),
                "trend_7d": ar_7d,
                "trend_30d": ar_30d,
                "status": "warning" if total_ar > 10_000_000 else "normal",
            },
            {
                "key": "avg_dso",
                "label": "Average DSO",
                "value": round(avg_dso, 1),
                "formatted_value": f"{avg_dso:.0f} days",
                "unit": "days",
                "change_pct": None,
                "change_direction": "flat",
                "trend_7d": dso_7d,
                "trend_30d": dso_30d,
                "status": "critical" if avg_dso > 90 else "warning" if avg_dso > 60 else "normal",
            },
            {
                "key": "collection_rate",
                "label": "Collection Rate (30d)",
                "value": round(coll_rate, 1),
                "formatted_value": f"{coll_rate:.1f}%",
                "unit": "%",
                "change_pct": round(coll_change, 1),
                "change_direction": _direction(coll_change),
                "trend_7d": coll_7d,
                "trend_30d": coll_30d,
                "status": "critical" if coll_rate < 30 else "warning" if coll_rate < 60 else "normal",
            },
            {
                "key": "churn_risk_count",
                "label": "Churn Risk Customers",
                "value": churn_count,
                "formatted_value": str(churn_count),
                "unit": "customers",
                "change_pct": None,
                "change_direction": "flat",
                "trend_7d": [],
                "trend_30d": [],
                "status": "critical" if churn_count > 5 else "warning" if churn_count > 0 else "normal",
            },
            {
                "key": "pipeline_value",
                "label": "Pipeline Value",
                "value": round(pipeline_value, 2),
                "formatted_value": _fmt_amount(pipeline_value),
                "unit": "AED",
                "change_pct": None,
                "change_direction": "flat",
                "trend_7d": [],
                "trend_30d": [],
                "status": "normal",
            },
            {
                "key": "credit_exposure",
                "label": "Credit Exposure",
                "value": round(credit_exposure_pct, 1),
                "formatted_value": f"{credit_exposure_pct:.1f}%",
                "unit": "%",
                "change_pct": None,
                "change_direction": "flat",
                "trend_7d": [],
                "trend_30d": [],
                "status": "critical" if credit_exposure_pct > 90 else "warning" if credit_exposure_pct > 70 else "normal",
            },
            {
                "key": "total_overdue",
                "label": "Total Overdue",
                "value": round(total_overdue, 2),
                "formatted_value": _fmt_amount(total_overdue),
                "unit": "AED",
                "change_pct": None,
                "change_direction": "flat",
                "trend_7d": [],
                "trend_30d": [],
                "status": "critical" if total_overdue > 5_000_000 else "warning" if total_overdue > 1_000_000 else "normal",
            },
        ]

        result = {
            "cards": cards,
            "currency": "AED",
            "generated_at": now_str,
        }
        _cache_set(cache_key, result)
        return result

    async def _build_trend(
        self, db: AsyncSession, tenant_id: UUID, metric: str, days: int,
    ) -> List[dict]:
        """Build sparkline trend data for a metric over N days."""
        today = date.today()
        points = []

        # Sample at intervals for efficiency
        step = max(1, days // 7)

        for i in range(0, days, step):
            ref_date = today - timedelta(days=days - i - 1)

            if metric == "ar":
                q = await db.execute(
                    select(func.coalesce(func.sum(Invoice.amount_remaining), 0)).where(
                        Invoice.tenant_id == tenant_id,
                        Invoice.invoice_date <= ref_date,
                        Invoice.status.in_([InvoiceStatus.OPEN, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE]),
                    )
                )
                value = float(q.scalar() or 0)
            elif metric == "dso":
                recv_q = await db.execute(
                    select(func.coalesce(func.sum(Invoice.amount_remaining), 0)).where(
                        Invoice.tenant_id == tenant_id,
                        Invoice.invoice_date <= ref_date,
                        Invoice.status.in_([InvoiceStatus.OPEN, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE]),
                    )
                )
                sales_q = await db.execute(
                    select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                        Invoice.tenant_id == tenant_id,
                        Invoice.invoice_date >= ref_date - timedelta(days=90),
                        Invoice.invoice_date <= ref_date,
                    )
                )
                recv = float(recv_q.scalar() or 0)
                sales = float(sales_q.scalar() or 1)
                value = min((recv / (sales / 90)) if sales > 0 else 0, 365)
            elif metric == "collection_rate":
                week_start = ref_date - timedelta(days=7)
                pay = await db.execute(
                    select(func.coalesce(func.sum(Payment.amount), 0)).where(
                        Payment.tenant_id == tenant_id,
                        Payment.payment_date >= week_start,
                        Payment.payment_date <= ref_date,
                    )
                )
                inv = await db.execute(
                    select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                        Invoice.tenant_id == tenant_id,
                        Invoice.invoice_date >= week_start,
                        Invoice.invoice_date <= ref_date,
                    )
                )
                p = float(pay.scalar() or 0)
                iv = float(inv.scalar() or 1)
                value = min(p / iv * 100, 100) if iv > 0 else 0
            else:
                value = 0

            points.append({
                "date": str(ref_date),
                "value": round(value, 2),
            })

        return points

    # ═══════════════════════════════════════════
    # AI EXECUTIVE SUMMARY
    # ═══════════════════════════════════════════

    async def get_executive_summary(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """Generate AI executive summary - 3-sentence briefing."""
        cache_key = f"exec_summary:{tenant_id}"
        cached = _cache_get(cache_key)
        if cached:
            return cached

        now_str = datetime.now(timezone.utc).isoformat()
        today = date.today()

        # Gather metrics for summary
        ar_q = await db.execute(
            select(func.coalesce(func.sum(Invoice.amount_remaining), 0)).where(
                Invoice.tenant_id == tenant_id,
                Invoice.status.in_([InvoiceStatus.OPEN, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE]),
            )
        )
        total_ar = float(ar_q.scalar() or 0)

        overdue_q = await db.execute(
            select(
                func.coalesce(func.sum(Invoice.amount_remaining), 0),
                func.count(),
            ).where(
                Invoice.tenant_id == tenant_id,
                Invoice.status == InvoiceStatus.OVERDUE,
            )
        )
        overdue_row = overdue_q.one()
        overdue_amount = float(overdue_row[0] or 0)
        overdue_count = int(overdue_row[1] or 0)

        # Collection in last 7 days
        week_ago = today - timedelta(days=7)
        recent_pay_q = await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.tenant_id == tenant_id,
                Payment.payment_date >= week_ago,
            )
        )
        recent_collections = float(recent_pay_q.scalar() or 0)

        # Credit holds
        holds_q = await db.execute(
            select(func.count()).where(
                Customer.tenant_id == tenant_id,
                Customer.is_deleted == False,
                Customer.credit_hold == True,
            )
        )
        credit_holds = holds_q.scalar() or 0

        # Open disputes
        dispute_q = await db.execute(
            select(func.count()).where(
                Dispute.tenant_id == tenant_id,
                Dispute.status.in_(["open", "in_review", "escalated"]),
            )
        )
        open_disputes = dispute_q.scalar() or 0

        # Customer count
        cust_q = await db.execute(
            select(func.count()).where(
                Customer.tenant_id == tenant_id,
                Customer.is_deleted == False,
                Customer.status == CustomerStatus.ACTIVE,
            )
        )
        active_customers = cust_q.scalar() or 0

        # Health distribution
        from app.services.intelligence import _health_scores
        health_dist = defaultdict(int)
        for s in _health_scores.values():
            health_dist[s.get("grade", "?")] += 1

        at_risk = health_dist.get("D", 0) + health_dist.get("F", 0)

        # Build AI summary (template-based for MVP)
        overdue_pct = (overdue_amount / total_ar * 100) if total_ar > 0 else 0

        sentence1 = (
            f"Your portfolio stands at {total_ar / 1_000_000:.1f}M AED across "
            f"{active_customers} active accounts, with {overdue_pct:.0f}% "
            f"({overdue_amount / 1_000_000:.1f}M) overdue across {overdue_count} invoices."
        )

        if recent_collections > 0:
            sentence2 = (
                f"Collections activity brought in {recent_collections / 1_000:.0f}K AED "
                f"over the past 7 days"
            )
            if credit_holds > 0:
                sentence2 += f", while {credit_holds} customer(s) remain on credit hold."
            else:
                sentence2 += "."
        else:
            sentence2 = (
                f"No collections recorded in the past 7 days — review collection "
                f"priorities and consider escalating stale receivables."
            )

        if at_risk > 0:
            sentence3 = (
                f"Health monitoring flags {at_risk} account(s) in D/F grade range; "
                f"recommend proactive outreach to prevent further deterioration."
            )
        elif open_disputes > 0:
            sentence3 = (
                f"There are {open_disputes} open dispute(s) in the queue — "
                f"prioritize resolution to unblock payment flows."
            )
        else:
            sentence3 = (
                f"Portfolio health is generally stable. Focus on improving DSO "
                f"and maintaining the current collection momentum."
            )

        summary = f"{sentence1} {sentence2} {sentence3}"

        highlights = []
        if total_ar > 0:
            highlights.append(f"Total AR: {total_ar / 1_000_000:.1f}M AED")
        if recent_collections > 0:
            highlights.append(f"Collected {recent_collections / 1_000:.0f}K AED this week")
        if overdue_count > 0:
            highlights.append(f"{overdue_count} overdue invoices ({overdue_amount / 1_000_000:.1f}M)")
        highlights.append(f"{active_customers} active accounts")

        alerts = []
        if overdue_pct > 50:
            alerts.append(f"CRITICAL: {overdue_pct:.0f}% of AR is overdue")
        if credit_holds > 3:
            alerts.append(f"WARNING: {credit_holds} customers on credit hold")
        if at_risk > 5:
            alerts.append(f"ALERT: {at_risk} accounts at D/F health grade")
        if open_disputes > 5:
            alerts.append(f"ATTENTION: {open_disputes} unresolved disputes")

        result = {
            "summary": summary,
            "highlights": highlights,
            "alerts": alerts,
            "data_as_of": str(today),
            "generated_at": now_str,
        }
        _cache_set(cache_key, result)
        return result

    # ═══════════════════════════════════════════
    # EXECUTIVE DASHBOARD (UNIFIED)
    # ═══════════════════════════════════════════

    async def get_executive_dashboard(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """Full executive dashboard combining all sections."""
        cache_key = f"exec_dash:{tenant_id}"
        cached = _cache_get(cache_key)
        if cached:
            return cached

        now_str = datetime.now(timezone.utc).isoformat()

        kpis = await self.get_kpi_cards(db, tenant_id)
        summary = await self.get_executive_summary(db, tenant_id)

        # Top overdue customers (top 5)
        overdue_invoices = (await db.execute(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id,
                Invoice.status == InvoiceStatus.OVERDUE,
            ).order_by(Invoice.amount_remaining.desc()).limit(5)
        )).scalars().all()

        top_overdue = []
        for inv in overdue_invoices:
            cust = (await db.execute(
                select(Customer).where(Customer.id == inv.customer_id)
            )).scalar()
            top_overdue.append({
                "customer_name": cust.name if cust else "Unknown",
                "customer_id": str(inv.customer_id),
                "invoice_number": inv.invoice_number,
                "amount_remaining": float(inv.amount_remaining or 0),
                "days_overdue": inv.days_overdue or 0,
                "currency": inv.currency or "AED",
            })

        # Pipeline snapshot
        from app.services.sales_dashboard import sales_dashboard
        pipeline = await sales_dashboard.get_pipeline_summary(db, tenant_id)

        # Cash flow forecast
        from app.services.cfo_dashboard import cfo_dashboard
        cash_flow = await cfo_dashboard.get_cash_flow_forecast(db, tenant_id)

        # Health distribution
        from app.services.intelligence import _health_scores
        health_dist = defaultdict(int)
        for s in _health_scores.values():
            health_dist[s.get("grade", "?")] += 1

        result = {
            "kpis": kpis["cards"],
            "executive_summary": summary,
            "top_overdue_customers": top_overdue,
            "pipeline_snapshot": pipeline,
            "cash_flow_forecast": cash_flow,
            "health_distribution": dict(health_dist),
            "currency": "AED",
            "generated_at": now_str,
        }
        _cache_set(cache_key, result)
        return result

    # ═══════════════════════════════════════════
    # ROLE-BASED HOME SCREEN
    # ═══════════════════════════════════════════

    async def get_home_screen(
        self, db: AsyncSession, tenant_id: UUID, user_id: UUID, role: str, full_name: str,
    ) -> dict:
        """Build role-specific home screen with widgets and quick stats."""
        now_str = datetime.now(timezone.utc).isoformat()
        today = date.today()

        # Greeting
        hour = datetime.now().hour
        if hour < 12:
            time_greeting = "Good morning"
        elif hour < 17:
            time_greeting = "Good afternoon"
        else:
            time_greeting = "Good evening"

        first_name = full_name.split()[0] if full_name else "there"
        greeting = f"{time_greeting}, {first_name}"

        role_labels = {
            "cfo": "Chief Financial Officer",
            "finance_manager": "Finance Manager",
            "collector": "Collection Specialist",
            "sales_rep": "Sales Representative",
            "tenant_admin": "System Administrator",
            "super_admin": "Super Administrator",
            "viewer": "Viewer",
        }
        role_label = role_labels.get(role, role.replace("_", " ").title())

        # Get user's widget config or use role defaults
        user_key = str(user_id)
        custom_config = _user_widget_configs.get(user_key)

        if custom_config:
            widget_ids = custom_config.get("widget_ids", [])
            hidden = set(custom_config.get("hidden_widget_ids", []))
            pinned = set(custom_config.get("pinned_widget_ids", []))
        else:
            widget_ids = ROLE_DEFAULT_WIDGETS.get(role, ["kpi_cards"])
            hidden = set()
            pinned = set()

        widget_defs = {w["widget_id"]: w for w in WIDGET_DEFINITIONS}

        widgets = []
        for pos, wid in enumerate(widget_ids):
            defn = widget_defs.get(wid)
            if not defn:
                continue

            widget_data = await self._load_widget_data(db, tenant_id, user_id, wid)

            widgets.append({
                "widget_id": wid,
                "widget_type": defn["widget_type"],
                "title": defn["title"],
                "position": pos,
                "size": defn["default_size"],
                "is_visible": wid not in hidden,
                "is_pinned": wid in pinned,
                "data": widget_data,
                "endpoint": f"/api/v1/executive/widgets/{wid}",
            })

        # Role-specific quick stats
        quick_stats = await self._get_quick_stats(db, tenant_id, role)

        return {
            "role": role,
            "role_label": role_label,
            "greeting": greeting,
            "widgets": widgets,
            "quick_stats": quick_stats,
            "generated_at": now_str,
        }

    async def _get_quick_stats(self, db: AsyncSession, tenant_id: UUID, role: str) -> dict:
        """Role-specific quick numbers for the top of the home screen."""
        today = date.today()
        stats: Dict[str, Any] = {}

        if role in ("cfo", "finance_manager", "tenant_admin"):
            # AR overview
            ar_q = await db.execute(
                select(func.coalesce(func.sum(Invoice.amount_remaining), 0)).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.status.in_([InvoiceStatus.OPEN, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE]),
                )
            )
            stats["total_ar"] = float(ar_q.scalar() or 0)

            overdue_q = await db.execute(
                select(func.count()).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.status == InvoiceStatus.OVERDUE,
                )
            )
            stats["overdue_invoices"] = overdue_q.scalar() or 0

            holds_q = await db.execute(
                select(func.count()).where(
                    Customer.tenant_id == tenant_id,
                    Customer.credit_hold == True,
                )
            )
            stats["credit_holds"] = holds_q.scalar() or 0

        elif role == "collector":
            # Worklist numbers
            overdue_q = await db.execute(
                select(func.count()).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.status == InvoiceStatus.OVERDUE,
                )
            )
            stats["overdue_invoices"] = overdue_q.scalar() or 0

            # PTP due today (from in-memory store)
            from app.services.collections_copilot import _ptp_store
            ptp_today = sum(
                1 for p in _ptp_store.values()
                if p.get("status") == "pending" and str(p.get("promised_date")) == str(today)
            )
            stats["ptp_due_today"] = ptp_today

            dispute_q = await db.execute(
                select(func.count()).where(
                    Dispute.tenant_id == tenant_id,
                    Dispute.status.in_(["open", "in_review"]),
                )
            )
            stats["open_disputes"] = dispute_q.scalar() or 0

        elif role == "sales_rep":
            # Territory health
            cust_q = await db.execute(
                select(func.count()).where(
                    Customer.tenant_id == tenant_id,
                    Customer.is_deleted == False,
                    Customer.status == CustomerStatus.ACTIVE,
                )
            )
            stats["active_customers"] = cust_q.scalar() or 0

            from app.services.intelligence import _health_scores
            at_risk = sum(1 for s in _health_scores.values() if s.get("grade") in ("D", "F"))
            stats["at_risk_accounts"] = at_risk

            churn_q = await db.execute(
                select(func.count()).where(
                    Customer.tenant_id == tenant_id,
                    Customer.churn_probability >= 0.3,
                )
            )
            stats["churn_alerts"] = churn_q.scalar() or 0

        elif role in ("tenant_admin", "super_admin"):
            # System health
            cust_q = await db.execute(
                select(func.count()).where(
                    Customer.tenant_id == tenant_id,
                    Customer.is_deleted == False,
                )
            )
            stats["total_customers"] = cust_q.scalar() or 0

            inv_q = await db.execute(
                select(func.count()).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.is_deleted == False,
                )
            )
            stats["total_invoices"] = inv_q.scalar() or 0

            stats["cache_entries"] = len(_dashboard_cache)

        return stats

    async def _load_widget_data(
        self, db: AsyncSession, tenant_id: UUID, user_id: UUID, widget_id: str,
    ) -> Optional[dict]:
        """Load data for a specific widget. Returns summary data for inline display."""
        try:
            if widget_id == "top_overdue":
                invoices = (await db.execute(
                    select(Invoice).where(
                        Invoice.tenant_id == tenant_id,
                        Invoice.status == InvoiceStatus.OVERDUE,
                    ).order_by(Invoice.amount_remaining.desc()).limit(5)
                )).scalars().all()
                return {
                    "count": len(invoices),
                    "total_amount": sum(float(i.amount_remaining or 0) for i in invoices),
                }

            elif widget_id == "credit_holds":
                q = await db.execute(
                    select(func.count()).where(
                        Customer.tenant_id == tenant_id,
                        Customer.credit_hold == True,
                    )
                )
                return {"count": q.scalar() or 0}

            elif widget_id == "dispute_queue":
                q = await db.execute(
                    select(func.count()).where(
                        Dispute.tenant_id == tenant_id,
                        Dispute.status.in_(["open", "in_review", "escalated"]),
                    )
                )
                return {"open_count": q.scalar() or 0}

            elif widget_id == "ptp_due_today":
                from app.services.collections_copilot import _ptp_store
                today_str = str(date.today())
                due = [p for p in _ptp_store.values() if str(p.get("promised_date")) == today_str]
                return {"count": len(due), "total_amount": sum(float(p.get("promised_amount", 0)) for p in due)}

            elif widget_id == "health_distribution":
                from app.services.intelligence import _health_scores
                dist = defaultdict(int)
                for s in _health_scores.values():
                    dist[s.get("grade", "?")] += 1
                return {"distribution": dict(dist), "total": len(_health_scores)}

            elif widget_id == "my_tasks":
                overdue_q = await db.execute(
                    select(func.count()).where(
                        Invoice.tenant_id == tenant_id,
                        Invoice.status == InvoiceStatus.OVERDUE,
                    )
                )
                return {"pending_tasks": overdue_q.scalar() or 0}

            elif widget_id == "system_health":
                return {
                    "cache_entries": len(_dashboard_cache),
                    "status": "healthy",
                }

        except Exception:
            return None

        return None

    # ═══════════════════════════════════════════
    # WIDGET CONFIGURATION
    # ═══════════════════════════════════════════

    def get_available_widgets(self, role: str) -> dict:
        """Return widget definitions available for a role."""
        available = [
            w for w in WIDGET_DEFINITIONS
            if role in w["available_for_roles"]
        ]
        return {
            "widgets": available,
            "total": len(available),
        }

    def update_widget_layout(self, user_id: UUID, role: str, data: dict) -> dict:
        """Save user's custom widget layout."""
        now_str = datetime.now(timezone.utc).isoformat()
        user_key = str(user_id)

        _user_widget_configs[user_key] = {
            "widget_ids": data.get("widget_ids", ROLE_DEFAULT_WIDGETS.get(role, [])),
            "hidden_widget_ids": data.get("hidden_widget_ids", []),
            "pinned_widget_ids": data.get("pinned_widget_ids", []),
            "updated_at": now_str,
        }

        widget_defs = {w["widget_id"]: w for w in WIDGET_DEFINITIONS}
        layout = []
        for pos, wid in enumerate(data.get("widget_ids", [])):
            defn = widget_defs.get(wid, {})
            layout.append({
                "widget_id": wid,
                "widget_type": defn.get("widget_type", "unknown"),
                "title": defn.get("title", wid),
                "position": pos,
                "size": defn.get("default_size", "medium"),
                "is_visible": wid not in data.get("hidden_widget_ids", []),
                "is_pinned": wid in data.get("pinned_widget_ids", []),
                "data": None,
                "endpoint": f"/api/v1/executive/widgets/{wid}",
            })

        return {
            "user_id": str(user_id),
            "role": role,
            "layout": layout,
            "updated_at": now_str,
        }

    def get_widget_config(self, user_id: UUID, role: str) -> dict:
        """Get current widget configuration for user."""
        now_str = datetime.now(timezone.utc).isoformat()
        user_key = str(user_id)
        config = _user_widget_configs.get(user_key)

        if config:
            widget_ids = config["widget_ids"]
            hidden = set(config.get("hidden_widget_ids", []))
            pinned = set(config.get("pinned_widget_ids", []))
        else:
            widget_ids = ROLE_DEFAULT_WIDGETS.get(role, ["kpi_cards"])
            hidden = set()
            pinned = set()

        widget_defs = {w["widget_id"]: w for w in WIDGET_DEFINITIONS}
        layout = []
        for pos, wid in enumerate(widget_ids):
            defn = widget_defs.get(wid, {})
            layout.append({
                "widget_id": wid,
                "widget_type": defn.get("widget_type", "unknown"),
                "title": defn.get("title", wid),
                "position": pos,
                "size": defn.get("default_size", "medium"),
                "is_visible": wid not in hidden,
                "is_pinned": wid in pinned,
                "data": None,
                "endpoint": f"/api/v1/executive/widgets/{wid}",
            })

        return {
            "user_id": str(user_id),
            "role": role,
            "layout": layout,
            "updated_at": config.get("updated_at", now_str) if config else now_str,
        }

    # ═══════════════════════════════════════════
    # CACHE MANAGEMENT
    # ═══════════════════════════════════════════

    def get_cache_status(self) -> dict:
        """Return dashboard cache statistics."""
        now = time.time()
        # Clean expired entries
        expired = [k for k, v in _dashboard_cache.items() if v["expires"] <= now]
        for k in expired:
            del _dashboard_cache[k]

        entries = _dashboard_cache.values()
        oldest = min((e["expires"] - CACHE_TTL_SECONDS for e in entries), default=None)
        newest = max((e["expires"] - CACHE_TTL_SECONDS for e in entries), default=None)

        return {
            "cached_keys": len(_dashboard_cache),
            "oldest_entry": datetime.fromtimestamp(oldest, tz=timezone.utc).isoformat() if oldest else None,
            "newest_entry": datetime.fromtimestamp(newest, tz=timezone.utc).isoformat() if newest else None,
            "ttl_seconds": CACHE_TTL_SECONDS,
            "hit_rate": None,  # Would need hit/miss counters for real implementation
        }

    def invalidate_cache(self, tenant_id: UUID = None) -> int:
        """Invalidate cache entries. Returns count of cleared entries."""
        if tenant_id:
            prefix = str(tenant_id)
            keys = [k for k in _dashboard_cache if prefix in k]
        else:
            keys = list(_dashboard_cache.keys())

        for k in keys:
            del _dashboard_cache[k]
        return len(keys)


# Singleton
executive_dashboard = ExecutiveDashboardService()
