"""
Sales IQ - Collections Copilot Service
Day 13: AI message drafting, escalation engine, PTP tracking, dispute aging analytics.
Simulated AI generation for MVP — production would use Claude/GPT-4o API.
"""

import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import (
    Customer, Invoice, Payment, Dispute, CollectionActivity,
    CustomerStatus, InvoiceStatus, DisputeStatus, DisputeReason, CollectionAction,
)


# ── In-memory stores (production: DB tables) ──

_message_drafts: Dict[str, dict] = {}
_sent_messages: Dict[str, dict] = {}
_escalation_templates: Dict[str, dict] = {}
_ptp_records: Dict[str, dict] = {}


# ── AI Message Templates ──

_EMAIL_TEMPLATES = {
    ("en", "friendly"): {
        "subject": "Payment Reminder - {invoice_list} ({total_amount} {currency})",
        "body": (
            "Dear {contact_name},\n\n"
            "I hope this message finds you well. This is a friendly reminder regarding "
            "the following outstanding invoice(s) with {company_name}:\n\n"
            "{invoice_details}\n\n"
            "The total amount due is {total_amount} {currency}. "
            "We would appreciate your earliest attention to this matter.\n\n"
            "If payment has already been made, please disregard this notice and accept "
            "our thanks.\n\n"
            "Should you have any questions or need to discuss payment arrangements, "
            "please don't hesitate to reach out.\n\n"
            "Best regards,\n{sender_name}\n{sender_title}\n{company_name}"
        ),
    },
    ("en", "firm"): {
        "subject": "Overdue Payment Notice - {invoice_list} ({total_amount} {currency})",
        "body": (
            "Dear {contact_name},\n\n"
            "We are writing to bring to your attention the following overdue invoice(s) "
            "that require immediate attention:\n\n"
            "{invoice_details}\n\n"
            "The total overdue amount is {total_amount} {currency}, "
            "which is now {max_days_overdue} days past due.\n\n"
            "We kindly request that you arrange payment within the next 7 business days. "
            "Please note that continued non-payment may affect your credit terms with us.\n\n"
            "If you are experiencing any difficulties, we encourage you to contact us to "
            "discuss a mutually agreeable payment plan.\n\n"
            "Regards,\n{sender_name}\n{sender_title}\n{company_name}"
        ),
    },
    ("en", "urgent"): {
        "subject": "URGENT: Overdue Payment - Immediate Action Required ({total_amount} {currency})",
        "body": (
            "Dear {contact_name},\n\n"
            "Despite our previous communications, the following invoice(s) remain "
            "significantly overdue:\n\n"
            "{invoice_details}\n\n"
            "Total outstanding: {total_amount} {currency} ({max_days_overdue} days overdue)\n\n"
            "This matter requires your immediate attention. We must receive payment or a "
            "confirmed payment arrangement within 3 business days to avoid further action, "
            "which may include:\n"
            "- Suspension of credit facilities\n"
            "- Referral to our collections department\n"
            "- Reporting to credit agencies\n\n"
            "Please contact us immediately at your earliest convenience to resolve this "
            "matter.\n\n"
            "Regards,\n{sender_name}\n{sender_title}\n{company_name}"
        ),
    },
    ("en", "legal"): {
        "subject": "Final Notice Before Legal Action - {invoice_list} ({total_amount} {currency})",
        "body": (
            "Dear {contact_name},\n\n"
            "NOTICE: This is a formal notification regarding the following severely overdue "
            "accounts:\n\n"
            "{invoice_details}\n\n"
            "Total outstanding: {total_amount} {currency}\n"
            "Days overdue: {max_days_overdue}\n\n"
            "All previous attempts to resolve this matter have been unsuccessful. Unless we "
            "receive full payment or a binding payment agreement within 5 calendar days from "
            "the date of this notice, we will have no alternative but to initiate formal "
            "legal proceedings to recover the outstanding amounts, plus applicable interest "
            "and legal costs.\n\n"
            "To avoid legal action, please arrange immediate payment or contact our office "
            "to discuss resolution.\n\n"
            "This notice is sent without prejudice to any rights or remedies available to us.\n\n"
            "Regards,\n{sender_name}\n{sender_title}\n{company_name}\nLegal Department"
        ),
    },
    ("en", "follow_up"): {
        "subject": "Follow-Up: Payment Status for {invoice_list}",
        "body": (
            "Dear {contact_name},\n\n"
            "I am following up on our previous communication regarding the outstanding "
            "balance of {total_amount} {currency}.\n\n"
            "{invoice_details}\n\n"
            "Could you please provide an update on the payment status? If payment has "
            "been processed, we would appreciate the remittance details for our records.\n\n"
            "Thank you for your continued partnership.\n\n"
            "Best regards,\n{sender_name}\n{sender_title}\n{company_name}"
        ),
    },
    ("ar", "friendly"): {
        "subject": "تذكير بالدفع - {invoice_list} ({total_amount} {currency})",
        "body": (
            "السادة {contact_name} المحترمين،\n\n"
            "تحية طيبة وبعد،\n\n"
            "نود تذكيركم بالفواتير المستحقة التالية:\n\n"
            "{invoice_details}\n\n"
            "إجمالي المبلغ المستحق: {total_amount} {currency}\n\n"
            "نرجو التكرم بترتيب الدفع في أقرب وقت ممكن.\n\n"
            "في حال تم الدفع مسبقاً، يرجى تجاهل هذا التنبيه مع خالص شكرنا.\n\n"
            "مع أطيب التحيات،\n{sender_name}\n{sender_title}\n{company_name}"
        ),
    },
}

_WHATSAPP_TEMPLATES = {
    ("en", "friendly"): (
        "Hi {contact_name}, this is a gentle reminder from {company_name} regarding "
        "your outstanding balance of {total_amount} {currency} "
        "({invoice_count} invoice(s)). Please let us know if you need any assistance "
        "with payment. Thank you!"
    ),
    ("en", "firm"): (
        "Dear {contact_name}, your account with {company_name} has an overdue balance "
        "of {total_amount} {currency} ({max_days_overdue} days past due). "
        "Kindly arrange payment within the next 7 days. Contact us for payment options."
    ),
    ("en", "urgent"): (
        "URGENT - {contact_name}, your overdue balance of {total_amount} {currency} "
        "with {company_name} requires immediate attention ({max_days_overdue} days overdue). "
        "Please contact us today to avoid credit restrictions."
    ),
    ("ar", "friendly"): (
        "مرحباً {contact_name}، نذكركم برصيدكم المستحق لدى {company_name} "
        "بمبلغ {total_amount} {currency}. "
        "يرجى التواصل معنا لأي استفسار. شكراً لكم."
    ),
}


class CollectionsCopilot:
    """AI-powered collections assistant for message drafting, escalation, and PTP management."""

    # ── AI Message Drafting ──

    async def draft_message(
        self, db: AsyncSession, tenant_id: UUID, user_id: UUID,
        customer_id: UUID, channel: str = "email", tone: str = "friendly",
        language: str = "en", invoice_ids: Optional[List[UUID]] = None,
        include_payment_link: bool = False, custom_instructions: Optional[str] = None,
    ) -> dict:
        """Generate an AI-drafted collection message for a customer."""

        # Fetch customer
        customer = (await db.execute(
            select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

        # Fetch relevant invoices
        inv_query = select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.customer_id == customer_id,
            Invoice.is_deleted == False,
            Invoice.status.in_(["open", "overdue", "partially_paid"]),
        )
        if invoice_ids:
            inv_query = inv_query.where(Invoice.id.in_(invoice_ids))
        invoices = (await db.execute(inv_query)).scalars().all()

        if not invoices:
            raise ValueError("No outstanding invoices found for this customer")

        # Build invoice details
        invoice_details = []
        total_amount = Decimal(0)
        max_days_overdue = 0
        for inv in invoices:
            remaining = inv.amount_remaining or inv.amount
            total_amount += remaining
            days = inv.days_overdue or 0
            max_days_overdue = max(max_days_overdue, days)
            invoice_details.append({
                "invoice_id": str(inv.id),
                "invoice_number": inv.invoice_number,
                "amount": float(remaining),
                "currency": inv.currency,
                "due_date": str(inv.due_date),
                "days_overdue": days,
                "status": inv.status.value if hasattr(inv.status, 'value') else str(inv.status),
            })

        invoice_list_str = ", ".join(d["invoice_number"] for d in invoice_details)
        detail_lines = []
        for d in invoice_details:
            line = f"  - {d['invoice_number']}: {d['amount']:,.2f} {d['currency']} (Due: {d['due_date']}"
            if d['days_overdue'] > 0:
                line += f", {d['days_overdue']} days overdue"
            line += ")"
            detail_lines.append(line)

        # Template context
        context = {
            "contact_name": customer.name,
            "company_name": "Sales IQ",
            "invoice_list": invoice_list_str,
            "invoice_details": "\n".join(detail_lines),
            "total_amount": f"{float(total_amount):,.2f}",
            "currency": customer.currency or "AED",
            "max_days_overdue": str(max_days_overdue),
            "invoice_count": str(len(invoices)),
            "sender_name": "Collections Team",
            "sender_title": "Accounts Receivable",
        }

        # Generate message based on channel
        subject = None
        if channel == "email":
            template = _EMAIL_TEMPLATES.get((language, tone), _EMAIL_TEMPLATES[("en", "friendly")])
            subject = template["subject"].format(**context)
            body = template["body"].format(**context)
        elif channel in ("whatsapp", "sms"):
            template = _WHATSAPP_TEMPLATES.get((language, tone), _WHATSAPP_TEMPLATES[("en", "friendly")])
            body = template.format(**context)
        else:
            template = _EMAIL_TEMPLATES.get((language, tone), _EMAIL_TEMPLATES[("en", "friendly")])
            subject = template["subject"].format(**context)
            body = template["body"].format(**context)

        if include_payment_link:
            body += "\n\nPayment Portal: https://pay.salesiq.ai/invoice/" + invoice_list_str.replace(", ", ",")

        if custom_instructions:
            body += f"\n\n[Note from AI: Custom instructions applied - {custom_instructions}]"

        # Determine follow-up suggestion based on tone escalation
        follow_up_days = {"friendly": 7, "follow_up": 5, "firm": 5, "urgent": 3, "legal": 5}.get(tone, 7)

        # Confidence based on data completeness
        confidence = 0.85
        if customer.email:
            confidence += 0.05
        if customer.phone:
            confidence += 0.05
        if len(invoices) > 0:
            confidence += 0.05

        # Store draft
        draft_id = str(uuid4())
        draft = {
            "id": draft_id,
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
            "customer_id": str(customer_id),
            "customer_name": customer.name,
            "channel": channel,
            "tone": tone,
            "language": language,
            "subject": subject,
            "body": body,
            "invoices_referenced": invoice_details,
            "total_amount_due": float(total_amount),
            "currency": customer.currency or "AED",
            "ai_confidence": min(confidence, 1.0),
            "suggested_follow_up_days": follow_up_days,
            "status": "draft",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _message_drafts[draft_id] = draft
        return draft

    def send_message(self, tenant_id: str, user_id: str, draft_id: str,
                     edited_subject: Optional[str] = None, edited_body: Optional[str] = None,
                     send_now: bool = True, schedule_at: Optional[str] = None) -> dict:
        """Send or schedule a drafted message."""
        draft = _message_drafts.get(draft_id)
        if not draft or draft["tenant_id"] != tenant_id:
            return None

        message_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()

        message = {
            "id": message_id,
            "draft_id": draft_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "customer_id": draft["customer_id"],
            "customer_name": draft["customer_name"],
            "channel": draft["channel"],
            "tone": draft["tone"],
            "subject": edited_subject or draft["subject"],
            "body": edited_body or draft["body"],
            "invoices_referenced": draft["invoices_referenced"],
            "total_amount": draft["total_amount_due"],
            "currency": draft["currency"],
            "status": "sent" if send_now else "scheduled",
            "sent_at": now if send_now else None,
            "scheduled_at": schedule_at,
            "opened_at": None,
            "replied_at": None,
            "created_at": now,
        }
        _sent_messages[message_id] = message
        draft["status"] = "sent"

        return {
            "message_id": message_id,
            "draft_id": draft_id,
            "status": message["status"],
            "channel": message["channel"],
            "sent_at": message["sent_at"],
            "scheduled_at": message["scheduled_at"],
        }

    def list_messages(self, tenant_id: str, customer_id: Optional[str] = None,
                      page: int = 1, page_size: int = 20) -> dict:
        """List sent message history."""
        messages = [m for m in _sent_messages.values() if m["tenant_id"] == tenant_id]
        if customer_id:
            messages = [m for m in messages if m["customer_id"] == customer_id]
        messages.sort(key=lambda x: x["created_at"], reverse=True)
        total = len(messages)
        start = (page - 1) * page_size
        items = messages[start:start + page_size]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    # ── Escalation Templates ──

    def create_template(self, tenant_id: str, data: dict) -> dict:
        tpl_id = str(uuid4())
        template = {
            "id": tpl_id,
            "tenant_id": tenant_id,
            **data,
            "times_triggered": 0,
            "last_triggered_at": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _escalation_templates[tpl_id] = template
        return template

    def list_templates(self, tenant_id: str) -> List[dict]:
        return [t for t in _escalation_templates.values() if t["tenant_id"] == tenant_id]

    def get_template(self, tenant_id: str, tpl_id: str) -> Optional[dict]:
        t = _escalation_templates.get(tpl_id)
        if t and t["tenant_id"] == tenant_id:
            return t
        return None

    def update_template(self, tenant_id: str, tpl_id: str, updates: dict) -> Optional[dict]:
        t = _escalation_templates.get(tpl_id)
        if not t or t["tenant_id"] != tenant_id:
            return None
        for k, v in updates.items():
            if v is not None:
                t[k] = v
        return t

    def delete_template(self, tenant_id: str, tpl_id: str) -> bool:
        t = _escalation_templates.get(tpl_id)
        if not t or t["tenant_id"] != tenant_id:
            return False
        del _escalation_templates[tpl_id]
        return True

    async def run_escalation_scan(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """Evaluate all active escalation templates and queue actions."""
        start = time.time()
        tid = str(tenant_id)
        templates = [t for t in _escalation_templates.values()
                     if t["tenant_id"] == tid and t.get("is_active", True)]

        customers_evaluated = set()
        escalations_triggered = 0
        actions_queued = 0
        by_template = defaultdict(int)
        by_action_type = defaultdict(int)

        for tpl in templates:
            trigger = tpl["trigger_type"]
            threshold = tpl["trigger_threshold"]

            if trigger == "overdue_days":
                # Find invoices overdue >= threshold days
                invoices = (await db.execute(
                    select(Invoice).where(
                        Invoice.tenant_id == tenant_id,
                        Invoice.is_deleted == False,
                        Invoice.status == InvoiceStatus.OVERDUE,
                        Invoice.days_overdue >= threshold,
                    )
                )).scalars().all()

                affected_customers = set(str(inv.customer_id) for inv in invoices)
                for cust_id in affected_customers:
                    customers_evaluated.add(cust_id)
                    escalations_triggered += 1
                    by_template[tpl["name"]] += 1

                    for step in tpl.get("steps", []):
                        actions_queued += 1
                        action_type = step.get("action_type", "email")
                        by_action_type[action_type] += 1

            elif trigger == "ptp_broken":
                # Find broken PTPs
                broken = [p for p in _ptp_records.values()
                          if p["tenant_id"] == tid and p["status"] == "broken"]
                for ptp in broken:
                    customers_evaluated.add(ptp["customer_id"])
                    escalations_triggered += 1
                    by_template[tpl["name"]] += 1
                    for step in tpl.get("steps", []):
                        actions_queued += 1
                        by_action_type[step.get("action_type", "email")] += 1

            if escalations_triggered > 0:
                tpl["times_triggered"] = tpl.get("times_triggered", 0) + 1
                tpl["last_triggered_at"] = datetime.now(timezone.utc).isoformat()

        duration_ms = int((time.time() - start) * 1000)
        return {
            "customers_evaluated": len(customers_evaluated),
            "escalations_triggered": escalations_triggered,
            "actions_queued": actions_queued,
            "by_template": dict(by_template),
            "by_action_type": dict(by_action_type),
            "duration_ms": duration_ms,
        }

    # ── Enhanced PTP Tracking ──

    async def create_ptp(self, db: AsyncSession, tenant_id: UUID, user_id: UUID,
                         data: dict) -> dict:
        """Create a new Promise-to-Pay record."""
        customer = (await db.execute(
            select(Customer).where(Customer.id == UUID(str(data["customer_id"])),
                                   Customer.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if not customer:
            raise ValueError("Customer not found")

        invoice_number = None
        if data.get("invoice_id"):
            invoice = (await db.execute(
                select(Invoice).where(Invoice.id == UUID(str(data["invoice_id"])),
                                      Invoice.tenant_id == tenant_id)
            )).scalar_one_or_none()
            if invoice:
                invoice_number = invoice.invoice_number

        ptp_id = str(uuid4())
        today = date.today()
        promised_date = data["promised_date"] if isinstance(data["promised_date"], date) else date.fromisoformat(str(data["promised_date"]))
        days_until = (promised_date - today).days

        ptp = {
            "id": ptp_id,
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
            "customer_id": str(data["customer_id"]),
            "customer_name": customer.name,
            "invoice_id": str(data["invoice_id"]) if data.get("invoice_id") else None,
            "invoice_number": invoice_number,
            "promised_date": str(promised_date),
            "promised_amount": float(data["promised_amount"]),
            "actual_amount": None,
            "actual_date": None,
            "currency": data.get("currency", "AED"),
            "status": "pending",
            "days_until_due": max(days_until, 0),
            "days_overdue": abs(min(days_until, 0)) if days_until < 0 else None,
            "contact_person": data.get("contact_person"),
            "contact_method": data.get("contact_method"),
            "notes": data.get("notes"),
            "follow_up_date": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _ptp_records[ptp_id] = ptp

        # Also create a CollectionActivity record for audit
        activity = CollectionActivity(
            tenant_id=tenant_id,
            customer_id=UUID(str(data["customer_id"])),
            invoice_id=UUID(str(data["invoice_id"])) if data.get("invoice_id") else None,
            collector_id=user_id,
            action_type=CollectionAction.PROMISE_TO_PAY,
            action_date=today,
            notes=f"PTP: {data['promised_amount']} {data.get('currency', 'AED')} by {promised_date}",
            ptp_date=promised_date,
            ptp_amount=Decimal(str(data["promised_amount"])),
            ptp_fulfilled=False,
        )
        db.add(activity)
        await db.commit()

        return ptp

    def update_ptp(self, tenant_id: str, ptp_id: str, updates: dict) -> Optional[dict]:
        ptp = _ptp_records.get(ptp_id)
        if not ptp or ptp["tenant_id"] != tenant_id:
            return None

        for k, v in updates.items():
            if v is not None:
                ptp[k] = v if not isinstance(v, (Decimal, date)) else str(v)

        # Auto-calculate status based on updates
        if updates.get("actual_amount") is not None:
            actual = float(updates["actual_amount"])
            promised = ptp["promised_amount"]
            if actual >= promised:
                ptp["status"] = "fulfilled"
            elif actual > 0:
                ptp["status"] = "partially_fulfilled"

        if updates.get("status"):
            ptp["status"] = updates["status"]

        return ptp

    def list_ptps(self, tenant_id: str, status: Optional[str] = None,
                  customer_id: Optional[str] = None) -> dict:
        """List PTPs with summary statistics."""
        ptps = [p for p in _ptp_records.values() if p["tenant_id"] == tenant_id]
        if status:
            ptps = [p for p in ptps if p["status"] == status]
        if customer_id:
            ptps = [p for p in ptps if p["customer_id"] == customer_id]

        # Refresh status for pending PTPs
        today = date.today()
        for p in ptps:
            pd = date.fromisoformat(p["promised_date"])
            if p["status"] == "pending" and pd < today:
                p["status"] = "broken"
                p["days_overdue"] = (today - pd).days

        ptps.sort(key=lambda x: x["promised_date"])

        total_promised = sum(p["promised_amount"] for p in ptps)
        fulfilled = [p for p in ptps if p["status"] == "fulfilled"]
        broken = [p for p in ptps if p["status"] == "broken"]
        pending = [p for p in ptps if p["status"] == "pending"]

        summary = {
            "total_promises": len(ptps),
            "total_promised_amount": total_promised,
            "fulfilled_count": len(fulfilled),
            "fulfilled_amount": sum(p["promised_amount"] for p in fulfilled),
            "broken_count": len(broken),
            "broken_amount": sum(p["promised_amount"] for p in broken),
            "pending_count": len(pending),
            "pending_amount": sum(p["promised_amount"] for p in pending),
            "fulfillment_rate": round(len(fulfilled) / len(ptps) * 100, 1) if ptps else 0,
        }

        return {"items": ptps, "total": len(ptps), "summary": summary}

    def get_ptp_dashboard(self, tenant_id: str) -> dict:
        """PTP overview dashboard."""
        ptps = [p for p in _ptp_records.values() if p["tenant_id"] == tenant_id]
        today = date.today()
        week_end = today + timedelta(days=7)

        # Refresh statuses
        for p in ptps:
            pd = date.fromisoformat(p["promised_date"])
            if p["status"] == "pending" and pd < today:
                p["status"] = "broken"
                p["days_overdue"] = (today - pd).days

        fulfilled = [p for p in ptps if p["status"] == "fulfilled"]
        broken = [p for p in ptps if p["status"] == "broken"]
        pending = [p for p in ptps if p["status"] == "pending"]

        due_today = sum(1 for p in pending if date.fromisoformat(p["promised_date"]) == today)
        due_this_week = sum(1 for p in pending
                           if today <= date.fromisoformat(p["promised_date"]) <= week_end)

        return {
            "total_promises": len(ptps),
            "total_promised_amount": sum(p["promised_amount"] for p in ptps),
            "fulfilled_count": len(fulfilled),
            "fulfilled_amount": sum(p["promised_amount"] for p in fulfilled),
            "broken_count": len(broken),
            "broken_amount": sum(p["promised_amount"] for p in broken),
            "pending_count": len(pending),
            "pending_amount": sum(p["promised_amount"] for p in pending),
            "fulfillment_rate": round(len(fulfilled) / len(ptps) * 100, 1) if ptps else 0,
            "due_today": due_today,
            "due_this_week": due_this_week,
            "overdue": len(broken),
            "currency": "AED",
        }

    # ── Dispute Aging Report ──

    async def get_dispute_aging(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """Generate dispute aging report with resolution analytics."""
        disputes = (await db.execute(
            select(Dispute).where(Dispute.tenant_id == tenant_id, Dispute.is_deleted == False)
        )).scalars().all()

        today = date.today()
        buckets_config = [
            ("0-7 days", 0, 7),
            ("8-14 days", 8, 14),
            ("15-30 days", 15, 30),
            ("31-60 days", 31, 60),
            ("60+ days", 61, 9999),
        ]

        open_statuses = {DisputeStatus.OPEN, DisputeStatus.IN_REVIEW, DisputeStatus.ESCALATED}
        resolved_statuses = {DisputeStatus.RESOLVED, DisputeStatus.CREDIT_ISSUED}

        open_disputes = [d for d in disputes if d.status in open_statuses]
        resolved_disputes = [d for d in disputes if d.status in resolved_statuses]

        # Build aging buckets for open disputes
        buckets = []
        for label, min_days, max_days in buckets_config:
            bucket_disputes = []
            for d in open_disputes:
                created = d.created_at
                if hasattr(created, 'date'):
                    days_open = (today - created.date()).days
                elif isinstance(created, str):
                    days_open = (today - datetime.fromisoformat(created).date()).days
                else:
                    days_open = 0

                if min_days <= days_open <= max_days:
                    bucket_disputes.append({
                        "dispute_id": str(d.id),
                        "dispute_number": d.dispute_number,
                        "customer_id": str(d.customer_id),
                        "amount": float(d.amount),
                        "reason": d.reason.value if hasattr(d.reason, 'value') else str(d.reason),
                        "status": d.status.value if hasattr(d.status, 'value') else str(d.status),
                        "days_open": days_open,
                        "sla_breached": d.sla_breached,
                    })

            total_amt = sum(bd["amount"] for bd in bucket_disputes)
            avg_days = (sum(bd["days_open"] for bd in bucket_disputes) / len(bucket_disputes)) if bucket_disputes else 0

            buckets.append({
                "bucket": label,
                "count": len(bucket_disputes),
                "total_amount": round(total_amt, 2),
                "avg_days_open": round(avg_days, 1),
                "disputes": bucket_disputes,
            })

        # Resolution analytics
        resolution_days = []
        for d in resolved_disputes:
            created = d.created_at
            resolved = d.resolved_at
            if created and resolved:
                if isinstance(created, str):
                    created = datetime.fromisoformat(created)
                if isinstance(resolved, str):
                    resolved = datetime.fromisoformat(resolved)
                if hasattr(created, 'date') and hasattr(resolved, 'date'):
                    resolution_days.append((resolved.date() - created.date()).days)

        avg_resolution = (sum(resolution_days) / len(resolution_days)) if resolution_days else 0
        resolution_rate = (len(resolved_disputes) / len(disputes) * 100) if disputes else 0

        # By reason
        by_reason = defaultdict(int)
        for d in open_disputes:
            reason = d.reason.value if hasattr(d.reason, 'value') else str(d.reason)
            by_reason[reason] += 1

        # By department
        by_department = defaultdict(int)
        for d in open_disputes:
            dept = d.assigned_department or "unassigned"
            by_department[dept] += 1

        sla_breach_count = sum(1 for d in open_disputes if d.sla_breached)

        return {
            "buckets": buckets,
            "total_open": len(open_disputes),
            "total_amount": round(sum(float(d.amount) for d in open_disputes), 2),
            "avg_resolution_days": round(avg_resolution, 1),
            "resolution_rate": round(resolution_rate, 1),
            "by_reason": dict(by_reason),
            "by_department": dict(by_department),
            "sla_breach_count": sla_breach_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


# Singleton
collections_copilot = CollectionsCopilot()
