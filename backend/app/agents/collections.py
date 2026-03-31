"""
Sales IQ - Collections Agent
Real collections workflow engine with customer prioritization,
escalation detection, AI message drafting, and PTP monitoring.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent, PipelineStage, AgentContext
from app.models.business import (
    Customer, Invoice, Payment, CollectionActivity,
    InvoiceStatus, CollectionAction,
)


# ── Stage 1: Prioritize ─────────────────────────────────────────────

class PrioritizeStage(PipelineStage):
    """Rank overdue accounts by urgency, amount, and risk."""

    name = "prioritize"

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        today = date.today()

        # Load customers with overdue invoices
        result = await db.execute(
            select(Customer).where(
                Customer.tenant_id == ctx.tenant_id,
                Customer.status.in_(["active", "credit_hold"]),
            )
        )
        customers = result.scalars().all()

        work_queue = []

        for customer in customers:
            # Get overdue invoices
            inv_result = await db.execute(
                select(Invoice).where(
                    Invoice.tenant_id == ctx.tenant_id,
                    Invoice.customer_id == customer.id,
                    Invoice.status.in_(["overdue", "open", "partially_paid"]),
                )
            )
            invoices = inv_result.scalars().all()

            # Filter to truly overdue
            overdue_invoices = []
            for inv in invoices:
                if inv.due_date and today > inv.due_date:
                    overdue_invoices.append(inv)
                elif inv.status == "overdue":
                    overdue_invoices.append(inv)

            if not overdue_invoices:
                continue

            # Compute priority score
            total_overdue = sum(float(inv.amount_remaining or inv.amount or 0) for inv in overdue_invoices)
            max_days_overdue = max((inv.days_overdue or 0) for inv in overdue_invoices)
            risk_factor = (customer.risk_score or 50) / 100

            # Priority formula: amount * aging_multiplier * risk_multiplier
            aging_multiplier = 1.0
            if max_days_overdue > 90:
                aging_multiplier = 3.0
            elif max_days_overdue > 60:
                aging_multiplier = 2.5
            elif max_days_overdue > 30:
                aging_multiplier = 1.8
            elif max_days_overdue > 14:
                aging_multiplier = 1.3

            priority_score = total_overdue * aging_multiplier * (0.5 + risk_factor)

            # Determine urgency level
            if max_days_overdue > 90 or total_overdue > 500000:
                urgency = "critical"
            elif max_days_overdue > 60 or total_overdue > 200000:
                urgency = "high"
            elif max_days_overdue > 30 or total_overdue > 50000:
                urgency = "medium"
            else:
                urgency = "low"

            # Determine recommended action
            if max_days_overdue > 90:
                recommended_action = "legal_notice"
            elif max_days_overdue > 60:
                recommended_action = "escalation"
            elif max_days_overdue > 30:
                recommended_action = "phone_call"
            elif max_days_overdue > 14:
                recommended_action = "email_reminder"
            else:
                recommended_action = "sms_reminder"

            work_item = {
                "customer_id": str(customer.id),
                "customer_name": customer.name,
                "priority_score": round(priority_score, 2),
                "urgency": urgency,
                "total_overdue": round(total_overdue, 2),
                "overdue_count": len(overdue_invoices),
                "max_days_overdue": max_days_overdue,
                "risk_score": customer.risk_score or 50,
                "recommended_action": recommended_action,
                "currency": customer.currency or "AED",
            }
            work_queue.append(work_item)

            cid = str(customer.id)
            ctx.get_entity_result(cid)
            er = ctx.entity_results[cid]
            er["customer"] = customer
            er["overdue_invoices"] = overdue_invoices
            er["work_item"] = work_item

            ctx.records_processed += 1

        # Sort by priority (highest first)
        work_queue.sort(key=lambda x: x["priority_score"], reverse=True)

        # Assign rank
        for i, item in enumerate(work_queue):
            item["rank"] = i + 1

        ctx.extra["work_queue"] = work_queue
        ctx.extra["total_overdue_customers"] = len(work_queue)
        ctx.extra["total_overdue_amount"] = sum(w["total_overdue"] for w in work_queue)


# ── Stage 2: Escalation Check ───────────────────────────────────────

class EscalationCheckStage(PipelineStage):
    """Evaluate escalation triggers and detect accounts needing action."""

    name = "escalation_check"

    ESCALATION_THRESHOLDS = [
        {"days": 7, "action": "email_reminder", "label": "1st Reminder"},
        {"days": 14, "action": "sms_reminder", "label": "SMS Follow-up"},
        {"days": 21, "action": "phone_call", "label": "Phone Call"},
        {"days": 30, "action": "phone_call", "label": "2nd Phone Call"},
        {"days": 45, "action": "escalation", "label": "Manager Escalation"},
        {"days": 60, "action": "escalation", "label": "Senior Escalation"},
        {"days": 90, "action": "legal_notice", "label": "Legal Notice"},
    ]

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        today = date.today()
        escalations = []

        for entity_id, er in ctx.entity_results.items():
            customer = er.get("customer")
            overdue_invoices = er.get("overdue_invoices", [])
            if not customer or not overdue_invoices:
                continue

            # Load recent collection activities for this customer
            activity_result = await db.execute(
                select(CollectionActivity).where(
                    CollectionActivity.tenant_id == ctx.tenant_id,
                    CollectionActivity.customer_id == customer.id,
                ).order_by(CollectionActivity.action_date.desc()).limit(20)
            )
            activities = activity_result.scalars().all()

            # Find the last activity date
            last_activity_date = activities[0].action_date if activities else None
            days_since_last_action = (today - last_activity_date).days if last_activity_date else 999

            # Check what escalation level is appropriate
            max_overdue = max((inv.days_overdue or 0) for inv in overdue_invoices)

            appropriate_level = None
            for threshold in self.ESCALATION_THRESHOLDS:
                if max_overdue >= threshold["days"]:
                    appropriate_level = threshold

            if appropriate_level and days_since_last_action >= 7:
                escalation = {
                    "customer_id": str(customer.id),
                    "customer_name": customer.name,
                    "max_days_overdue": max_overdue,
                    "days_since_last_action": days_since_last_action,
                    "recommended_action": appropriate_level["action"],
                    "escalation_label": appropriate_level["label"],
                    "needs_escalation": True,
                    "total_activities": len(activities),
                }
                escalations.append(escalation)
                er["escalation"] = escalation

                if max_overdue > 60 and days_since_last_action > 14:
                    ctx.add_issue(
                        entity_id, "escalation_check", "critical",
                        "collection_gap",
                        f"Customer {customer.name} has {max_overdue} days overdue "
                        f"but no collection activity in {days_since_last_action} days",
                    )
                elif max_overdue > 30 and days_since_last_action > 7:
                    ctx.add_issue(
                        entity_id, "escalation_check", "warning",
                        "follow_up_due",
                        f"Customer {customer.name} needs follow-up "
                        f"({appropriate_level['label']})",
                    )

        ctx.extra["escalations"] = escalations
        ctx.extra["escalation_count"] = len(escalations)


# ── Stage 3: Message Draft ──────────────────────────────────────────

class MessageDraftStage(PipelineStage):
    """Generate collection message drafts based on escalation level."""

    name = "message_draft"

    TEMPLATES = {
        "email_reminder": {
            "subject": "Payment Reminder - Outstanding Invoice(s)",
            "body": (
                "Dear {contact_name},\n\n"
                "This is a friendly reminder that you have {overdue_count} outstanding invoice(s) "
                "totalling {currency} {total_amount:,.2f}. "
                "The oldest invoice is {max_days} days past due.\n\n"
                "We kindly request you to arrange payment at your earliest convenience.\n\n"
                "If you have already made payment, please disregard this message "
                "and share the payment confirmation with us.\n\n"
                "Best regards,\n"
                "Accounts Receivable Team"
            ),
        },
        "sms_reminder": {
            "body": (
                "Reminder: {company} has {overdue_count} overdue invoice(s) "
                "for {currency} {total_amount:,.2f}. "
                "Please arrange payment. Ref: {oldest_invoice}"
            ),
        },
        "phone_call": {
            "script": (
                "Call Script for {company}:\n"
                "- Overdue: {overdue_count} invoices, {currency} {total_amount:,.2f}\n"
                "- Oldest: {max_days} days overdue (Invoice {oldest_invoice})\n"
                "- Ask for: Payment date commitment (PTP)\n"
                "- Escalation: If no commitment, inform about potential credit hold"
            ),
        },
        "escalation": {
            "subject": "ESCALATION: Overdue Account - {company}",
            "body": (
                "ESCALATION NOTICE\n\n"
                "Customer: {company}\n"
                "Total Overdue: {currency} {total_amount:,.2f}\n"
                "Oldest Invoice: {max_days} days past due\n"
                "Previous Actions: {action_count} collection activities\n\n"
                "This account requires manager review and escalated action.\n"
                "Recommended: Direct senior contact or credit hold review."
            ),
        },
        "legal_notice": {
            "subject": "URGENT: Legal Notice Pending - {company}",
            "body": (
                "LEGAL ACTION NOTICE\n\n"
                "Customer: {company}\n"
                "Total Outstanding: {currency} {total_amount:,.2f}\n"
                "Maximum Days Overdue: {max_days}\n\n"
                "This account has exceeded 90 days overdue. "
                "Legal department notification is recommended.\n"
                "Recommend: Final demand letter before legal proceedings."
            ),
        },
    }

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        drafts = []

        for entity_id, er in ctx.entity_results.items():
            customer = er.get("customer")
            work_item = er.get("work_item", {})
            escalation = er.get("escalation", {})
            overdue_invoices = er.get("overdue_invoices", [])

            if not customer or not overdue_invoices:
                continue

            action = escalation.get("recommended_action") or work_item.get("recommended_action")
            if not action or action not in self.TEMPLATES:
                continue

            template = self.TEMPLATES[action]

            # Build template context
            oldest_inv = min(overdue_invoices, key=lambda i: i.due_date or date.today())
            tpl_ctx = {
                "contact_name": customer.name.split()[0] if customer.name else "Customer",
                "company": customer.name,
                "overdue_count": len(overdue_invoices),
                "total_amount": work_item.get("total_overdue", 0),
                "currency": customer.currency or "AED",
                "max_days": work_item.get("max_days_overdue", 0),
                "oldest_invoice": oldest_inv.invoice_number if oldest_inv else "N/A",
                "action_count": escalation.get("total_activities", 0),
            }

            draft = {
                "customer_id": str(customer.id),
                "customer_name": customer.name,
                "action_type": action,
                "channel": "email" if action in ("email_reminder", "escalation", "legal_notice") else "sms" if action == "sms_reminder" else "phone",
            }

            # Fill template
            if "subject" in template:
                draft["subject"] = template["subject"].format(**tpl_ctx)
            if "body" in template:
                draft["body"] = template["body"].format(**tpl_ctx)
            if "script" in template:
                draft["script"] = template["script"].format(**tpl_ctx)

            drafts.append(draft)
            er["draft"] = draft
            ctx.records_succeeded += 1

        ctx.extra["message_drafts"] = drafts
        ctx.extra["drafts_generated"] = len(drafts)


# ── Stage 4: PTP Monitor ────────────────────────────────────────────

class PTPMonitorStage(PipelineStage):
    """Track promise-to-pay commitments and flag broken ones."""

    name = "ptp_monitor"

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        today = date.today()

        # Find all PTPs
        ptp_result = await db.execute(
            select(CollectionActivity).where(
                CollectionActivity.tenant_id == ctx.tenant_id,
                CollectionActivity.action_type == CollectionAction.PROMISE_TO_PAY,
                CollectionActivity.ptp_date.isnot(None),
            )
        )
        ptps = ptp_result.scalars().all()

        active_ptps = 0
        broken_ptps = 0
        fulfilled_ptps = 0
        upcoming_ptps = 0
        ptp_details = []

        for ptp in ptps:
            if ptp.ptp_fulfilled is True:
                fulfilled_ptps += 1
                continue

            if ptp.ptp_date and ptp.ptp_date < today and not ptp.ptp_fulfilled:
                # Check if payment was made after PTP
                pay_result = await db.execute(
                    select(func.coalesce(func.sum(Payment.amount), 0)).where(
                        Payment.tenant_id == ctx.tenant_id,
                        Payment.customer_id == ptp.customer_id,
                        Payment.payment_date >= ptp.action_date,
                        Payment.payment_date <= ptp.ptp_date + timedelta(days=3),  # 3-day grace
                    )
                )
                paid_amount = float(pay_result.scalar() or 0)
                ptp_amount = float(ptp.ptp_amount or 0)

                if ptp_amount > 0 and paid_amount >= ptp_amount * 0.95:
                    # PTP fulfilled
                    ptp.ptp_fulfilled = True
                    fulfilled_ptps += 1
                else:
                    # PTP broken
                    broken_ptps += 1
                    ptp_details.append({
                        "customer_id": str(ptp.customer_id),
                        "ptp_date": str(ptp.ptp_date),
                        "ptp_amount": ptp_amount,
                        "paid_amount": paid_amount,
                        "status": "broken",
                        "days_past": (today - ptp.ptp_date).days,
                    })

                    # Add issue
                    ctx.add_issue(
                        str(ptp.customer_id), "ptp_monitor", "warning",
                        "broken_ptp",
                        f"Promise to pay on {ptp.ptp_date} for {ptp_amount:,.2f} "
                        f"was not fulfilled (paid {paid_amount:,.2f})",
                    )

            elif ptp.ptp_date and ptp.ptp_date >= today:
                upcoming_ptps += 1
                days_until = (ptp.ptp_date - today).days
                ptp_details.append({
                    "customer_id": str(ptp.customer_id),
                    "ptp_date": str(ptp.ptp_date),
                    "ptp_amount": float(ptp.ptp_amount or 0),
                    "status": "upcoming",
                    "days_until": days_until,
                })

            active_ptps += 1

        await db.flush()

        ctx.extra["ptp_summary"] = {
            "total_ptps": len(ptps),
            "active": active_ptps,
            "fulfilled": fulfilled_ptps,
            "broken": broken_ptps,
            "upcoming": upcoming_ptps,
            "details": ptp_details[:50],  # Limit detail list
        }


# ── Agent ─────────────────────────────────────────────────────────────

class CollectionsAgent(BaseAgent):
    """Automated collections workflow agent."""

    agent_name = "collections_agent"
    stages = [
        PrioritizeStage(),
        EscalationCheckStage(),
        MessageDraftStage(),
        PTPMonitorStage(),
    ]


# Singleton
collections_agent = CollectionsAgent()
