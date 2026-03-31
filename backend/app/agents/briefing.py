"""
Sales IQ - Briefing Agent
AI-powered briefing generation with 4-stage pipeline:
  1. Data Collection  - Gather metrics from all entities
  2. Insight Analysis  - Detect patterns, trends, anomalies
  3. Section Composer  - Build structured markdown sections
  4. HTML Renderer     - Produce email-ready HTML output
"""

import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, func, case, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentContext, PipelineStage, BaseAgent
from app.models.business import (
    Customer, Invoice, Payment, Dispute, CollectionActivity,
    CreditLimitRequest, Briefing,
    CustomerStatus, InvoiceStatus, DisputeStatus, CreditApprovalStatus,
    CollectionAction, ECLStage,
)
from app.models.core import User


# ── Helper constants ──

AGING_BUCKETS = [
    ("current", 0, 0),
    ("1_30", 1, 30),
    ("31_60", 31, 60),
    ("61_90", 61, 90),
    ("91_plus", 91, 9999),
]

BRIEFING_SECTIONS = {
    "daily_flash": [
        "executive_summary", "ar_overview", "risk_alerts", "collection_priorities",
    ],
    "weekly_digest": [
        "executive_summary", "ar_overview", "risk_alerts",
        "collection_priorities", "dispute_update", "credit_alerts",
    ],
    "monthly_review": [
        "executive_summary", "ar_overview", "risk_alerts",
        "collection_priorities", "dispute_update", "credit_alerts", "data_quality",
    ],
}


# ═══════════════════════════════════════════════
# Stage 1: Data Collection
# ═══════════════════════════════════════════════

class DataCollectionStage(PipelineStage):
    """Gathers raw metrics from all business entities."""
    name = "data_collection"

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        tid = ctx.tenant_id
        today = date.today()
        date_from = ctx.extra.get("date_from", today - timedelta(days=30))
        date_to = ctx.extra.get("date_to", today)
        customer_ids = ctx.extra.get("customer_ids")

        snapshot = {}

        # ── Customer metrics ──
        cust_q = select(Customer).where(Customer.tenant_id == tid, Customer.is_deleted == False)
        if customer_ids:
            cust_q = cust_q.where(Customer.id.in_(customer_ids))
        customers = (await db.execute(cust_q)).scalars().all()

        total_credit = sum(float(c.credit_limit or 0) for c in customers)
        total_utilization = sum(float(c.credit_utilization or 0) for c in customers)
        on_hold = [c for c in customers if c.credit_hold]
        high_risk = [c for c in customers if (c.risk_score or 0) >= 70]

        snapshot["customers"] = {
            "total": len(customers),
            "active": sum(1 for c in customers if c.status == CustomerStatus.ACTIVE),
            "on_credit_hold": len(on_hold),
            "high_risk_count": len(high_risk),
            "total_credit_limit": total_credit,
            "total_utilization": total_utilization,
            "avg_utilization_pct": round(total_utilization / total_credit * 100, 1) if total_credit > 0 else 0,
            "hold_names": [c.name for c in on_hold[:5]],
            "high_risk_names": [{"name": c.name, "score": c.risk_score} for c in sorted(high_risk, key=lambda x: x.risk_score or 0, reverse=True)[:5]],
        }

        # ── AR / Invoice metrics ──
        inv_q = select(Invoice).where(
            Invoice.tenant_id == tid, Invoice.is_deleted == False,
        )
        if customer_ids:
            inv_q = inv_q.where(Invoice.customer_id.in_(customer_ids))
        invoices = (await db.execute(inv_q)).scalars().all()

        open_invoices = [i for i in invoices if i.status in (InvoiceStatus.OPEN, InvoiceStatus.OVERDUE, InvoiceStatus.PARTIALLY_PAID)]
        total_ar = sum(float(i.amount_remaining or i.amount or 0) for i in open_invoices)
        overdue = [i for i in open_invoices if i.status == InvoiceStatus.OVERDUE or (i.due_date and i.due_date < today)]

        # Aging buckets
        aging = {}
        for label, lo, hi in AGING_BUCKETS:
            bucket_inv = [i for i in open_invoices if lo <= (i.days_overdue or 0) <= hi]
            aging[label] = {
                "count": len(bucket_inv),
                "amount": round(sum(float(i.amount_remaining or i.amount or 0) for i in bucket_inv), 2),
            }

        # DSO calculation (last 90 days)
        period_start = today - timedelta(days=90)
        period_revenue = sum(
            float(i.amount or 0) for i in invoices
            if i.invoice_date and i.invoice_date >= period_start
        )
        dso = round(total_ar / (period_revenue / 90), 1) if period_revenue > 0 else 0

        # Recent payments (in analysis window)
        pay_q = select(Payment).where(
            Payment.tenant_id == tid,
            Payment.payment_date >= date_from,
        )
        if customer_ids:
            pay_q = pay_q.where(Payment.customer_id.in_(customer_ids))
        payments = (await db.execute(pay_q)).scalars().all()
        total_collected = sum(float(p.amount or 0) for p in payments)

        snapshot["ar"] = {
            "total_ar": round(total_ar, 2),
            "total_invoices_open": len(open_invoices),
            "total_overdue": len(overdue),
            "total_overdue_amount": round(sum(float(i.amount_remaining or i.amount or 0) for i in overdue), 2),
            "aging": aging,
            "dso": dso,
            "collected_period": round(total_collected, 2),
            "payment_count_period": len(payments),
            "collection_rate": round(total_collected / total_ar * 100, 1) if total_ar > 0 else 0,
        }

        # Top overdue accounts
        overdue_by_customer = defaultdict(float)
        for i in overdue:
            overdue_by_customer[str(i.customer_id)] += float(i.amount_remaining or i.amount or 0)
        cust_map = {str(c.id): c.name for c in customers}
        top_overdue = sorted(overdue_by_customer.items(), key=lambda x: x[1], reverse=True)[:10]
        snapshot["ar"]["top_overdue"] = [
            {"customer": cust_map.get(cid, "Unknown"), "amount": round(amt, 2)}
            for cid, amt in top_overdue
        ]

        # ── Dispute metrics ──
        dsp_q = select(Dispute).where(Dispute.tenant_id == tid, Dispute.is_deleted == False)
        if customer_ids:
            dsp_q = dsp_q.where(Dispute.customer_id.in_(customer_ids))
        disputes = (await db.execute(dsp_q)).scalars().all()

        open_disputes = [d for d in disputes if d.status in (DisputeStatus.OPEN, DisputeStatus.IN_REVIEW, DisputeStatus.ESCALATED)]
        sla_breached = [d for d in open_disputes if d.sla_breached]

        snapshot["disputes"] = {
            "total": len(disputes),
            "open": len(open_disputes),
            "escalated": sum(1 for d in open_disputes if d.status == DisputeStatus.ESCALATED),
            "sla_breached": len(sla_breached),
            "total_disputed_amount": round(sum(float(d.amount or 0) for d in open_disputes), 2),
            "breached_details": [
                {"number": d.dispute_number, "amount": float(d.amount or 0), "days_past_sla": (today - d.sla_due_date).days if d.sla_due_date else 0}
                for d in sla_breached[:5]
            ],
            "by_reason": dict(defaultdict(int, {
                str(d.reason.value if hasattr(d.reason, 'value') else d.reason): 1
                for d in open_disputes
            })),
        }
        # Fix by_reason to actually count
        reason_counts = defaultdict(int)
        for d in open_disputes:
            r = str(d.reason.value if hasattr(d.reason, 'value') else d.reason)
            reason_counts[r] += 1
        snapshot["disputes"]["by_reason"] = dict(reason_counts)

        # ── Collection activity metrics ──
        coll_q = select(CollectionActivity).where(
            CollectionActivity.tenant_id == tid,
        )
        if customer_ids:
            coll_q = coll_q.where(CollectionActivity.customer_id.in_(customer_ids))
        activities = (await db.execute(coll_q)).scalars().all()

        recent_activities = [a for a in activities if a.action_date and a.action_date >= date_from]
        ptp_all = [a for a in activities if a.action_type == CollectionAction.PROMISE_TO_PAY or str(a.action_type) == "promise_to_pay"]
        ptp_upcoming = [a for a in ptp_all if a.ptp_date and a.ptp_date >= today and not a.ptp_fulfilled]
        ptp_broken = [a for a in ptp_all if a.ptp_date and a.ptp_date < today and not a.ptp_fulfilled]

        snapshot["collections"] = {
            "total_period": len(recent_activities),
            "ptp_upcoming": len(ptp_upcoming),
            "ptp_broken": len(ptp_broken),
            "ptp_upcoming_amount": round(sum(float(a.ptp_amount or 0) for a in ptp_upcoming), 2),
            "ptp_broken_amount": round(sum(float(a.ptp_amount or 0) for a in ptp_broken), 2),
            "broken_details": [
                {"customer_id": str(a.customer_id), "amount": float(a.ptp_amount or 0), "date": str(a.ptp_date)}
                for a in ptp_broken[:5]
            ],
        }

        # ── Credit limit requests ──
        clr_q = select(CreditLimitRequest).where(
            CreditLimitRequest.tenant_id == tid,
            CreditLimitRequest.approval_status == CreditApprovalStatus.PENDING,
        )
        pending_requests = (await db.execute(clr_q)).scalars().all()

        snapshot["credit"] = {
            "pending_requests": len(pending_requests),
            "pending_details": [
                {
                    "customer_id": str(r.customer_id),
                    "current": float(r.current_limit or 0),
                    "requested": float(r.requested_limit or 0),
                    "ai_recommendation": (r.ai_risk_assessment or {}).get("recommendation", "unknown"),
                }
                for r in pending_requests[:5]
            ],
        }

        # Store snapshot in context
        ctx.extra["data_snapshot"] = snapshot
        ctx.extra["customers_map"] = cust_map
        ctx.records_processed = len(customers) + len(invoices) + len(payments)


# ═══════════════════════════════════════════════
# Stage 2: Insight Analysis
# ═══════════════════════════════════════════════

class InsightAnalysisStage(PipelineStage):
    """Analyzes data patterns and generates actionable insights."""
    name = "insight_analysis"

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        snapshot = ctx.extra["data_snapshot"]
        insights = []

        ar = snapshot.get("ar", {})
        custs = snapshot.get("customers", {})
        disputes = snapshot.get("disputes", {})
        collections = snapshot.get("collections", {})
        credit = snapshot.get("credit", {})

        # ── AR Health Insights ──
        if ar.get("dso", 0) > 60:
            insights.append({
                "category": "ar",
                "severity": "critical",
                "title": "DSO Exceeds 60 Days",
                "detail": f"Current DSO is {ar['dso']} days, indicating collection challenges.",
                "action": "Review collection strategy and escalate top overdue accounts.",
            })
        elif ar.get("dso", 0) > 45:
            insights.append({
                "category": "ar",
                "severity": "warning",
                "title": "DSO Trending High",
                "detail": f"Current DSO is {ar['dso']} days, above the 45-day target.",
                "action": "Increase collection follow-up frequency for 60+ day buckets.",
            })

        overdue_pct = (ar.get("total_overdue", 0) / ar.get("total_invoices_open", 1)) * 100
        if overdue_pct > 40:
            insights.append({
                "category": "ar",
                "severity": "critical",
                "title": f"{overdue_pct:.0f}% of Open Invoices Are Overdue",
                "detail": f"{ar['total_overdue']} of {ar['total_invoices_open']} open invoices are past due.",
                "action": "Prioritize overdue accounts for immediate collection action.",
            })

        # 91+ bucket concentration
        aging_91 = ar.get("aging", {}).get("91_plus", {})
        if aging_91.get("amount", 0) > 0 and ar.get("total_ar", 0) > 0:
            pct_91 = aging_91["amount"] / ar["total_ar"] * 100
            if pct_91 > 20:
                insights.append({
                    "category": "ar",
                    "severity": "critical",
                    "title": f"High 91+ Day Concentration ({pct_91:.0f}%)",
                    "detail": f"{aging_91['amount']:,.0f} in severely aged receivables.",
                    "action": "Initiate escalation procedures for 91+ accounts.",
                })

        # ── Credit Risk Insights ──
        if custs.get("on_credit_hold", 0) > 0:
            insights.append({
                "category": "credit",
                "severity": "warning",
                "title": f"{custs['on_credit_hold']} Customer(s) on Credit Hold",
                "detail": f"Customers on hold: {', '.join(custs.get('hold_names', []))}",
                "action": "Review credit hold status and pending orders impact.",
            })

        if custs.get("avg_utilization_pct", 0) > 80:
            insights.append({
                "category": "credit",
                "severity": "warning",
                "title": f"Portfolio Credit Utilization at {custs['avg_utilization_pct']}%",
                "detail": "High aggregate utilization increases portfolio risk.",
                "action": "Consider proactive credit limit reviews for high-utilization accounts.",
            })

        if credit.get("pending_requests", 0) > 0:
            insights.append({
                "category": "credit",
                "severity": "attention",
                "title": f"{credit['pending_requests']} Pending Credit Limit Request(s)",
                "detail": "Unprocessed credit limit requests require attention.",
                "action": "Review pending requests in the Credit Limits dashboard.",
            })

        # ── Dispute Insights ──
        if disputes.get("sla_breached", 0) > 0:
            insights.append({
                "category": "disputes",
                "severity": "critical",
                "title": f"{disputes['sla_breached']} Dispute(s) Breached SLA",
                "detail": "Dispute resolution has exceeded the agreed service level.",
                "action": "Escalate SLA-breached disputes immediately.",
            })

        if disputes.get("escalated", 0) > 0:
            insights.append({
                "category": "disputes",
                "severity": "warning",
                "title": f"{disputes['escalated']} Escalated Dispute(s)",
                "detail": f"Total disputed amount: {disputes.get('total_disputed_amount', 0):,.0f}",
                "action": "Schedule review meeting with dispute resolution team.",
            })

        # ── Collection Insights ──
        if collections.get("ptp_broken", 0) > 0:
            insights.append({
                "category": "collections",
                "severity": "warning",
                "title": f"{collections['ptp_broken']} Broken Promise(s) to Pay",
                "detail": f"Total broken PTP amount: {collections.get('ptp_broken_amount', 0):,.0f}",
                "action": "Re-engage customers with broken promises and consider escalation.",
            })

        if collections.get("ptp_upcoming", 0) > 0:
            insights.append({
                "category": "collections",
                "severity": "attention",
                "title": f"{collections['ptp_upcoming']} Upcoming PTP Due",
                "detail": f"Expected collections: {collections.get('ptp_upcoming_amount', 0):,.0f}",
                "action": "Send proactive reminders before PTP dates.",
            })

        # ── High risk customers ──
        if custs.get("high_risk_count", 0) > 0:
            insights.append({
                "category": "risk",
                "severity": "warning",
                "title": f"{custs['high_risk_count']} High-Risk Customer(s)",
                "detail": "Customers with risk score >= 70 require monitoring.",
                "action": "Review risk profiles and consider tightening credit terms.",
            })

        # Sort by severity
        severity_order = {"critical": 0, "warning": 1, "attention": 2, "info": 3}
        insights.sort(key=lambda x: severity_order.get(x["severity"], 99))

        ctx.extra["insights"] = insights
        ctx.records_succeeded = len(insights)


# ═══════════════════════════════════════════════
# Stage 3: Section Composer
# ═══════════════════════════════════════════════

class SectionComposerStage(PipelineStage):
    """Composes markdown-formatted briefing sections."""
    name = "section_composer"

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        snapshot = ctx.extra["data_snapshot"]
        insights = ctx.extra["insights"]
        briefing_type = ctx.extra.get("briefing_type", "daily_flash")
        sections_to_include = ctx.extra.get("sections") or BRIEFING_SECTIONS.get(briefing_type, BRIEFING_SECTIONS["daily_flash"])

        sections = []

        for section_type in sections_to_include:
            composer = getattr(self, f"_compose_{section_type}", None)
            if composer:
                section = composer(snapshot, insights)
                if section:
                    sections.append(section)

        ctx.extra["composed_sections"] = sections

        # Generate executive summary title
        today = date.today()
        type_labels = {
            "daily_flash": "Daily Flash",
            "weekly_digest": "Weekly Digest",
            "monthly_review": "Monthly Review",
            "custom": "Custom Briefing",
        }
        ctx.extra["title"] = f"SalesIQ {type_labels.get(briefing_type, 'Briefing')} - {today.strftime('%B %d, %Y')}"

    def _compose_executive_summary(self, snapshot: dict, insights: list) -> dict:
        ar = snapshot.get("ar", {})
        custs = snapshot.get("customers", {})
        disputes = snapshot.get("disputes", {})

        critical = [i for i in insights if i["severity"] == "critical"]
        warnings = [i for i in insights if i["severity"] == "warning"]

        lines = []
        lines.append(f"**Total AR Outstanding:** {ar.get('total_ar', 0):,.0f} | "
                      f"**DSO:** {ar.get('dso', 0)} days | "
                      f"**Overdue:** {ar.get('total_overdue', 0)} invoices ({ar.get('total_overdue_amount', 0):,.0f})")
        lines.append(f"**Active Customers:** {custs.get('active', 0)} | "
                      f"**Credit Holds:** {custs.get('on_credit_hold', 0)} | "
                      f"**Open Disputes:** {disputes.get('open', 0)}")
        lines.append(f"**Period Collections:** {ar.get('collected_period', 0):,.0f} from {ar.get('payment_count_period', 0)} payments")

        if critical:
            lines.append("")
            lines.append("**Alerts Requiring Immediate Attention:**")
            for alert in critical[:3]:
                lines.append(f"- {alert['title']}: {alert['detail']}")

        if warnings:
            lines.append("")
            lines.append("**Warnings:**")
            for w in warnings[:3]:
                lines.append(f"- {w['title']}")

        priority = 2 if critical else (1 if warnings else 0)

        return {
            "section_type": "executive_summary",
            "title": "Executive Summary",
            "priority": priority,
            "content": "\n".join(lines),
            "metrics": {
                "total_ar": ar.get("total_ar", 0),
                "dso": ar.get("dso", 0),
                "overdue_count": ar.get("total_overdue", 0),
                "critical_alerts": len(critical),
                "warnings": len(warnings),
            },
        }

    def _compose_ar_overview(self, snapshot: dict, insights: list) -> dict:
        ar = snapshot.get("ar", {})
        aging = ar.get("aging", {})

        lines = []
        lines.append("### Aging Analysis\n")
        lines.append("| Bucket | Count | Amount |")
        lines.append("|--------|------:|-------:|")
        for label, _, _ in AGING_BUCKETS:
            b = aging.get(label, {})
            display = label.replace("_", "-").replace("plus", "+").title()
            lines.append(f"| {display} | {b.get('count', 0)} | {b.get('amount', 0):,.0f} |")

        lines.append(f"\n**Total Open AR:** {ar.get('total_ar', 0):,.0f}")
        lines.append(f"**DSO (90-day):** {ar.get('dso', 0)} days")
        lines.append(f"**Collection Rate:** {ar.get('collection_rate', 0):.1f}%")

        if ar.get("top_overdue"):
            lines.append("\n### Top Overdue Accounts\n")
            lines.append("| Customer | Overdue Amount |")
            lines.append("|----------|---------------:|")
            for entry in ar["top_overdue"][:7]:
                lines.append(f"| {entry['customer']} | {entry['amount']:,.0f} |")

        return {
            "section_type": "ar_overview",
            "title": "Accounts Receivable Overview",
            "priority": 1 if ar.get("total_overdue", 0) > 0 else 0,
            "content": "\n".join(lines),
            "metrics": {
                "total_ar": ar.get("total_ar", 0),
                "dso": ar.get("dso", 0),
                "overdue_amount": ar.get("total_overdue_amount", 0),
            },
        }

    def _compose_risk_alerts(self, snapshot: dict, insights: list) -> dict:
        risk_insights = [i for i in insights if i["severity"] in ("critical", "warning")]
        if not risk_insights:
            return {
                "section_type": "risk_alerts",
                "title": "Risk Alerts",
                "priority": 0,
                "content": "No critical or warning-level alerts at this time.",
                "action_items": [],
            }

        lines = []
        action_items = []
        for ins in risk_insights:
            icon = "!!!" if ins["severity"] == "critical" else "!!"
            lines.append(f"**[{icon}] {ins['title']}**")
            lines.append(f"{ins['detail']}")
            lines.append(f"*Recommended:* {ins['action']}\n")
            action_items.append({
                "priority": ins["severity"],
                "action": ins["action"],
                "category": ins["category"],
            })

        return {
            "section_type": "risk_alerts",
            "title": "Risk Alerts",
            "priority": 2 if any(i["severity"] == "critical" for i in risk_insights) else 1,
            "content": "\n".join(lines),
            "action_items": action_items,
        }

    def _compose_collection_priorities(self, snapshot: dict, insights: list) -> dict:
        ar = snapshot.get("ar", {})
        coll = snapshot.get("collections", {})

        lines = []
        lines.append(f"**Collection Actions (Period):** {coll.get('total_period', 0)}")
        lines.append(f"**Upcoming PTP:** {coll.get('ptp_upcoming', 0)} ({coll.get('ptp_upcoming_amount', 0):,.0f})")
        lines.append(f"**Broken PTP:** {coll.get('ptp_broken', 0)} ({coll.get('ptp_broken_amount', 0):,.0f})")

        action_items = []

        if ar.get("top_overdue"):
            lines.append("\n### Priority Collection Targets\n")
            for i, entry in enumerate(ar["top_overdue"][:5], 1):
                lines.append(f"{i}. **{entry['customer']}** - {entry['amount']:,.0f} overdue")
                action_items.append({
                    "priority": "high",
                    "action": f"Follow up with {entry['customer']} on {entry['amount']:,.0f} overdue",
                    "category": "collections",
                })

        if coll.get("broken_details"):
            lines.append("\n### Broken Promises to Pay\n")
            cust_map = snapshot.get("customers_map", {})
            for bp in coll["broken_details"]:
                cname = cust_map if isinstance(cust_map, str) else "Customer"
                lines.append(f"- PTP of {bp['amount']:,.0f} due {bp['date']} (unfulfilled)")

        return {
            "section_type": "collection_priorities",
            "title": "Collection Priorities",
            "priority": 1 if ar.get("total_overdue", 0) > 0 else 0,
            "content": "\n".join(lines),
            "action_items": action_items,
        }

    def _compose_dispute_update(self, snapshot: dict, insights: list) -> dict:
        disp = snapshot.get("disputes", {})

        lines = []
        lines.append(f"**Open Disputes:** {disp.get('open', 0)} | "
                      f"**Escalated:** {disp.get('escalated', 0)} | "
                      f"**SLA Breached:** {disp.get('sla_breached', 0)}")
        lines.append(f"**Total Disputed Amount:** {disp.get('total_disputed_amount', 0):,.0f}")

        if disp.get("by_reason"):
            lines.append("\n### Disputes by Reason\n")
            lines.append("| Reason | Count |")
            lines.append("|--------|------:|")
            for reason, count in disp["by_reason"].items():
                lines.append(f"| {reason.replace('_', ' ').title()} | {count} |")

        if disp.get("breached_details"):
            lines.append("\n### SLA Breached Disputes\n")
            for bd in disp["breached_details"]:
                lines.append(f"- **{bd['number']}**: {bd['amount']:,.0f} ({bd['days_past_sla']} days past SLA)")

        return {
            "section_type": "dispute_update",
            "title": "Dispute Status Update",
            "priority": 2 if disp.get("sla_breached", 0) > 0 else (1 if disp.get("open", 0) > 0 else 0),
            "content": "\n".join(lines),
            "metrics": {
                "open": disp.get("open", 0),
                "sla_breached": disp.get("sla_breached", 0),
                "total_amount": disp.get("total_disputed_amount", 0),
            },
        }

    def _compose_credit_alerts(self, snapshot: dict, insights: list) -> dict:
        custs = snapshot.get("customers", {})
        credit = snapshot.get("credit", {})

        lines = []
        lines.append(f"**Total Credit Limit:** {custs.get('total_credit_limit', 0):,.0f}")
        lines.append(f"**Portfolio Utilization:** {custs.get('avg_utilization_pct', 0):.1f}%")
        lines.append(f"**Customers on Hold:** {custs.get('on_credit_hold', 0)}")
        lines.append(f"**Pending Requests:** {credit.get('pending_requests', 0)}")

        if credit.get("pending_details"):
            lines.append("\n### Pending Credit Limit Requests\n")
            lines.append("| Current | Requested | AI Recommendation |")
            lines.append("|--------:|----------:|-------------------|")
            for pd in credit["pending_details"]:
                lines.append(f"| {pd['current']:,.0f} | {pd['requested']:,.0f} | {pd['ai_recommendation']} |")

        if custs.get("high_risk_names"):
            lines.append("\n### High-Risk Customers\n")
            for hr in custs["high_risk_names"]:
                lines.append(f"- **{hr['name']}** (risk score: {hr['score']})")

        return {
            "section_type": "credit_alerts",
            "title": "Credit & Risk Alerts",
            "priority": 1 if custs.get("on_credit_hold", 0) > 0 else 0,
            "content": "\n".join(lines),
            "metrics": {
                "utilization_pct": custs.get("avg_utilization_pct", 0),
                "on_hold": custs.get("on_credit_hold", 0),
                "pending_requests": credit.get("pending_requests", 0),
            },
        }

    def _compose_data_quality(self, snapshot: dict, insights: list) -> dict:
        custs = snapshot.get("customers", {})
        lines = []
        lines.append(f"**Total Customers Monitored:** {custs.get('total', 0)}")
        lines.append("Data quality monitoring is active across all entities.")
        lines.append("Run a DQ scan from the Data Quality dashboard for detailed analysis.")

        return {
            "section_type": "data_quality",
            "title": "Data Quality",
            "priority": 0,
            "content": "\n".join(lines),
        }


# ═══════════════════════════════════════════════
# Stage 4: HTML Renderer
# ═══════════════════════════════════════════════

class HTMLRendererStage(PipelineStage):
    """Renders briefing sections into email-ready HTML."""
    name = "html_renderer"

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        sections = ctx.extra.get("composed_sections", [])
        title = ctx.extra.get("title", "SalesIQ Briefing")

        html_parts = [self._html_header(title)]

        for section in sections:
            html_parts.append(self._render_section(section))

        html_parts.append(self._html_footer())
        ctx.extra["html_content"] = "\n".join(html_parts)

    def _html_header(self, title: str) -> str:
        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 720px; margin: 0 auto; padding: 20px; color: #1a1a2e; background: #f8f9fa; }}
.header {{ background: linear-gradient(135deg, #0f3460, #16213e); color: white; padding: 24px; border-radius: 12px 12px 0 0; }}
.header h1 {{ margin: 0; font-size: 22px; font-weight: 600; }}
.header .date {{ opacity: 0.8; margin-top: 4px; font-size: 14px; }}
.section {{ background: white; padding: 20px 24px; margin-bottom: 2px; border-left: 4px solid #e0e0e0; }}
.section.priority-2 {{ border-left-color: #e74c3c; }}
.section.priority-1 {{ border-left-color: #f39c12; }}
.section.priority-0 {{ border-left-color: #27ae60; }}
.section h2 {{ margin: 0 0 12px 0; font-size: 16px; color: #0f3460; }}
.section p {{ margin: 6px 0; line-height: 1.6; font-size: 14px; }}
.metric {{ display: inline-block; background: #f0f4f8; padding: 6px 12px; border-radius: 6px; margin: 4px 4px 4px 0; font-size: 13px; }}
.metric strong {{ color: #0f3460; }}
table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13px; }}
th {{ background: #f0f4f8; text-align: left; padding: 8px 12px; border-bottom: 2px solid #ddd; }}
td {{ padding: 8px 12px; border-bottom: 1px solid #eee; }}
.alert-critical {{ background: #fef2f2; padding: 8px 12px; border-radius: 6px; margin: 6px 0; border-left: 3px solid #e74c3c; font-size: 13px; }}
.alert-warning {{ background: #fffbeb; padding: 8px 12px; border-radius: 6px; margin: 6px 0; border-left: 3px solid #f39c12; font-size: 13px; }}
.footer {{ background: #f0f4f8; padding: 16px 24px; border-radius: 0 0 12px 12px; font-size: 12px; color: #666; text-align: center; }}
</style>
</head>
<body>
<div class="header">
  <h1>{title}</h1>
  <div class="date">Generated {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}</div>
</div>"""

    def _render_section(self, section: dict) -> str:
        priority = section.get("priority", 0)
        title = section.get("title", "")
        content = section.get("content", "")

        # Convert markdown-like content to basic HTML
        html_content = self._md_to_html(content)

        return f"""<div class="section priority-{priority}">
  <h2>{title}</h2>
  {html_content}
</div>"""

    def _md_to_html(self, md: str) -> str:
        """Simple markdown to HTML conversion for briefing content."""
        import re
        lines = md.split("\n")
        html_lines = []
        in_table = False

        for line in lines:
            stripped = line.strip()

            # Skip table separator lines
            if stripped.startswith("|") and set(stripped.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
                continue

            # Table rows
            if stripped.startswith("|") and stripped.endswith("|"):
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                if not in_table:
                    html_lines.append("<table>")
                    html_lines.append("<tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr>")
                    in_table = True
                else:
                    html_lines.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
                continue
            elif in_table:
                html_lines.append("</table>")
                in_table = False

            # Headers
            if stripped.startswith("### "):
                html_lines.append(f"<h3>{stripped[4:]}</h3>")
            elif stripped.startswith("## "):
                html_lines.append(f"<h2>{stripped[3:]}</h2>")
            # List items
            elif stripped.startswith("- "):
                item = stripped[2:]
                item = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', item)
                html_lines.append(f"<p style='margin:2px 0 2px 16px;'>&#8226; {item}</p>")
            elif re.match(r'^\d+\.\s', stripped):
                item = re.sub(r'^\d+\.\s', '', stripped)
                item = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', item)
                html_lines.append(f"<p style='margin:2px 0 2px 16px;'>{stripped[:2]} {item}</p>")
            # Bold text
            elif stripped:
                processed = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
                processed = re.sub(r'\*(.+?)\*', r'<em>\1</em>', processed)
                # Alert boxes
                if "[!!!]" in processed:
                    processed = processed.replace("[!!!]", "").strip()
                    html_lines.append(f'<div class="alert-critical">{processed}</div>')
                elif "[!!]" in processed:
                    processed = processed.replace("[!!]", "").strip()
                    html_lines.append(f'<div class="alert-warning">{processed}</div>')
                else:
                    html_lines.append(f"<p>{processed}</p>")
            else:
                html_lines.append("")

        if in_table:
            html_lines.append("</table>")

        return "\n".join(html_lines)

    def _html_footer(self) -> str:
        return """<div class="footer">
  <p>SalesIQ Revenue Intelligence Platform | Powered by AI</p>
  <p>This briefing was automatically generated. Data reflects the latest available snapshot.</p>
</div>
</body></html>"""


# ═══════════════════════════════════════════════
# Briefing Agent (orchestrator)
# ═══════════════════════════════════════════════

class BriefingAgent(BaseAgent):
    agent_name = "briefing_agent"
    stages = [
        DataCollectionStage(),
        InsightAnalysisStage(),
        SectionComposerStage(),
        HTMLRendererStage(),
    ]

    async def generate_briefing(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        recipient_id: UUID,
        recipient_role: str = "finance_manager",
        briefing_type: str = "daily_flash",
        sections: list = None,
        date_from: date = None,
        date_to: date = None,
        delivery: str = "in_app",
        customer_ids: list = None,
    ) -> Briefing:
        """Generate a complete briefing and persist it."""
        start_ms = time.time()

        # Run the pipeline
        result = await self.run(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            entity_type="briefing",
            run_type="briefing_generation",
            briefing_type=briefing_type,
            sections=sections,
            date_from=date_from or date.today() - timedelta(days=30),
            date_to=date_to or date.today(),
            customer_ids=customer_ids,
        )

        # Extract context results (stored in the last run's context)
        ctx = self._last_context
        generation_ms = int((time.time() - start_ms) * 1000)

        # Build executive summary from first section
        exec_summary = ""
        composed = ctx.extra.get("composed_sections", [])
        for s in composed:
            if s["section_type"] == "executive_summary":
                exec_summary = s["content"]
                break

        briefing = Briefing(
            tenant_id=tenant_id,
            briefing_date=date.today(),
            recipient_id=recipient_id,
            recipient_role=recipient_role,
            title=ctx.extra.get("title", f"SalesIQ Briefing - {date.today()}"),
            executive_summary=exec_summary,
            sections=composed,
            html_content=ctx.extra.get("html_content", ""),
            delivered_via=delivery,
            model_used="salesiq-briefing-v1",
            generation_time_ms=generation_ms,
            data_snapshot=ctx.extra.get("data_snapshot", {}),
        )
        db.add(briefing)
        await db.commit()
        await db.refresh(briefing)

        return briefing

    async def run(self, db, tenant_id, user_id, entity_type, run_type="manual", **kwargs):
        """Override to capture context for briefing extraction."""
        # Create context manually so we can capture it
        from uuid import uuid4
        ctx = AgentContext(tenant_id, user_id, entity_type, uuid4())
        ctx.extra.update(kwargs)
        self._last_context = ctx

        from app.models.business import AgentRunLog

        run_log = AgentRunLog(
            tenant_id=tenant_id,
            agent_name=self.agent_name,
            run_type=run_type,
            started_at=datetime.now(timezone.utc).isoformat(),
            status="running",
            run_metadata={"entity_type": entity_type},
        )
        db.add(run_log)
        await db.flush()

        stage_timings = {}
        error_msg = None

        for stage in self.stages:
            t0 = time.time()
            try:
                await stage.process(db, ctx)
                stage_timings[stage.name] = round((time.time() - t0) * 1000, 1)
            except Exception as e:
                stage_timings[stage.name] = round((time.time() - t0) * 1000, 1)
                error_msg = f"Stage '{stage.name}' failed: {str(e)}"
                import traceback
                run_log.error_traceback = traceback.format_exc()
                break

        ctx.extra["stage_timings"] = stage_timings
        run_log.completed_at = datetime.now(timezone.utc).isoformat()
        run_log.duration_ms = sum(stage_timings.values())
        run_log.status = "failed" if error_msg else "completed"
        run_log.error_message = error_msg
        run_log.records_processed = ctx.records_processed
        run_log.records_succeeded = ctx.records_succeeded
        run_log.result_summary = {
            "insights_count": len(ctx.extra.get("insights", [])),
            "sections_count": len(ctx.extra.get("composed_sections", [])),
        }

        await db.flush()
        return ctx.summary
