"""
Sales IQ - Notification & Alert Engine
Rule-based alert evaluation, notification creation, and delivery management.
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
    Customer, Invoice, Dispute, CollectionActivity, CreditLimitRequest,
    CustomerStatus, InvoiceStatus, DisputeStatus, CreditApprovalStatus,
)


# ── In-memory stores (production: DB tables) ──

_alert_rules: Dict[str, dict] = {}
_notifications: Dict[str, dict] = {}
_user_preferences: Dict[str, dict] = {}

# Seed default rules
DEFAULT_RULES = [
    {
        "name": "SLA Breach Alert",
        "description": "Fires when a dispute exceeds its SLA due date",
        "category": "sla_breach",
        "severity": "critical",
        "condition": {"entity": "disputes", "field": "sla_breached", "operator": "==", "value": True, "status_in": ["open", "in_review", "escalated"]},
        "channels": ["in_app", "email"],
        "cooldown_minutes": 240,
    },
    {
        "name": "Credit Hold Notification",
        "description": "Fires when a customer is placed on credit hold",
        "category": "credit_hold",
        "severity": "warning",
        "condition": {"entity": "customers", "field": "credit_hold", "operator": "==", "value": True},
        "channels": ["in_app"],
        "cooldown_minutes": 1440,
    },
    {
        "name": "90+ Days Overdue",
        "description": "Fires for invoices overdue more than 90 days",
        "category": "overdue_threshold",
        "severity": "critical",
        "condition": {"entity": "invoices", "field": "days_overdue", "operator": ">", "value": 90, "status_in": ["overdue"]},
        "channels": ["in_app", "email"],
        "cooldown_minutes": 1440,
    },
    {
        "name": "Broken Promise to Pay",
        "description": "Fires when a PTP date passes without fulfillment",
        "category": "ptp_broken",
        "severity": "warning",
        "condition": {"entity": "collection_activities", "field": "ptp_fulfilled", "operator": "==", "value": False, "ptp_past_due": True},
        "channels": ["in_app"],
        "cooldown_minutes": 480,
    },
    {
        "name": "Pending Credit Limit Request",
        "description": "Fires for unprocessed credit limit requests older than 24h",
        "category": "credit_limit_request",
        "severity": "info",
        "condition": {"entity": "credit_limit_requests", "field": "approval_status", "operator": "==", "value": "pending"},
        "channels": ["in_app"],
        "cooldown_minutes": 1440,
    },
    {
        "name": "High Risk Customer",
        "description": "Fires when customer risk score exceeds 80",
        "category": "high_risk_customer",
        "severity": "warning",
        "condition": {"entity": "customers", "field": "risk_score", "operator": ">=", "value": 80},
        "channels": ["in_app"],
        "cooldown_minutes": 1440,
    },
]


def _init_default_rules(tenant_id: str):
    """Seed default alert rules for a tenant if not already present."""
    existing = [r for r in _alert_rules.values() if r.get("tenant_id") == tenant_id]
    if existing:
        return
    for defn in DEFAULT_RULES:
        rule_id = str(uuid4())
        _alert_rules[rule_id] = {
            "id": rule_id,
            "tenant_id": tenant_id,
            **defn,
            "recipient_roles": None,
            "recipient_user_ids": None,
            "is_active": True,
            "times_triggered": 0,
            "last_triggered_at": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }


class AlertEngine:
    """Evaluates alert rules against current data and generates notifications."""

    async def scan(self, db: AsyncSession, tenant_id: UUID, user_id: UUID) -> dict:
        """Scan all active rules and generate notifications for matches."""
        start = time.time()
        tid = str(tenant_id)
        _init_default_rules(tid)

        active_rules = [r for r in _alert_rules.values() if r["tenant_id"] == tid and r["is_active"]]
        alerts_generated = 0
        by_category = defaultdict(int)
        by_severity = defaultdict(int)

        for rule in active_rules:
            # Check cooldown
            if rule["last_triggered_at"]:
                last = datetime.fromisoformat(rule["last_triggered_at"])
                if datetime.now(timezone.utc) - last < timedelta(minutes=rule["cooldown_minutes"]):
                    continue

            matches = await self._evaluate_rule(db, tenant_id, rule)
            for match in matches:
                notif_id = str(uuid4())
                _notifications[notif_id] = {
                    "id": notif_id,
                    "tenant_id": tid,
                    "user_id": str(user_id),
                    "alert_rule_id": rule["id"],
                    "category": rule["category"],
                    "severity": rule["severity"],
                    "title": match["title"],
                    "message": match["message"],
                    "entity_type": match.get("entity_type"),
                    "entity_id": match.get("entity_id"),
                    "channel": "in_app",
                    "is_read": False,
                    "read_at": None,
                    "action_url": match.get("action_url"),
                    "metadata": match.get("metadata"),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                alerts_generated += 1
                by_category[rule["category"]] += 1
                by_severity[rule["severity"]] += 1

            if matches:
                rule["times_triggered"] += 1
                rule["last_triggered_at"] = datetime.now(timezone.utc).isoformat()

        duration_ms = int((time.time() - start) * 1000)
        return {
            "alerts_generated": alerts_generated,
            "by_category": dict(by_category),
            "by_severity": dict(by_severity),
            "scan_duration_ms": duration_ms,
        }

    async def _evaluate_rule(self, db: AsyncSession, tenant_id: UUID, rule: dict) -> List[dict]:
        """Evaluate a single rule and return matching alert details."""
        condition = rule["condition"]
        entity = condition.get("entity")
        matches = []

        if entity == "disputes":
            matches = await self._eval_disputes(db, tenant_id, rule)
        elif entity == "customers":
            matches = await self._eval_customers(db, tenant_id, rule)
        elif entity == "invoices":
            matches = await self._eval_invoices(db, tenant_id, rule)
        elif entity == "collection_activities":
            matches = await self._eval_collections(db, tenant_id, rule)
        elif entity == "credit_limit_requests":
            matches = await self._eval_credit_requests(db, tenant_id, rule)

        return matches

    async def _eval_disputes(self, db: AsyncSession, tenant_id: UUID, rule: dict) -> List[dict]:
        cond = rule["condition"]
        q = select(Dispute).where(Dispute.tenant_id == tenant_id, Dispute.is_deleted == False)
        if "status_in" in cond:
            q = q.where(Dispute.status.in_(cond["status_in"]))
        disputes = (await db.execute(q)).scalars().all()

        matches = []
        for d in disputes:
            val = getattr(d, cond["field"], None)
            if self._compare(val, cond["operator"], cond["value"]):
                matches.append({
                    "title": f"{rule['name']}: {d.dispute_number}",
                    "message": f"Dispute {d.dispute_number} ({d.amount} {d.currency}) - {d.reason.value if hasattr(d.reason, 'value') else d.reason}",
                    "entity_type": "disputes",
                    "entity_id": str(d.id),
                    "action_url": f"/disputes/{d.id}",
                    "metadata": {"dispute_number": d.dispute_number, "amount": str(d.amount)},
                })
        return matches

    async def _eval_customers(self, db: AsyncSession, tenant_id: UUID, rule: dict) -> List[dict]:
        cond = rule["condition"]
        customers = (await db.execute(
            select(Customer).where(Customer.tenant_id == tenant_id, Customer.is_deleted == False)
        )).scalars().all()

        matches = []
        for c in customers:
            val = getattr(c, cond["field"], None)
            if self._compare(val, cond["operator"], cond["value"]):
                matches.append({
                    "title": f"{rule['name']}: {c.name}",
                    "message": f"Customer {c.name} - {cond['field']}={val}",
                    "entity_type": "customers",
                    "entity_id": str(c.id),
                    "action_url": f"/customers/{c.id}",
                    "metadata": {"customer_name": c.name},
                })
        return matches

    async def _eval_invoices(self, db: AsyncSession, tenant_id: UUID, rule: dict) -> List[dict]:
        cond = rule["condition"]
        q = select(Invoice).where(Invoice.tenant_id == tenant_id, Invoice.is_deleted == False)
        if "status_in" in cond:
            q = q.where(Invoice.status.in_(cond["status_in"]))
        invoices = (await db.execute(q)).scalars().all()

        matches = []
        for i in invoices:
            val = getattr(i, cond["field"], None)
            if self._compare(val, cond["operator"], cond["value"]):
                matches.append({
                    "title": f"{rule['name']}: {i.invoice_number}",
                    "message": f"Invoice {i.invoice_number} is {i.days_overdue} days overdue ({i.amount_remaining or i.amount} {i.currency})",
                    "entity_type": "invoices",
                    "entity_id": str(i.id),
                    "action_url": f"/invoices/{i.id}",
                    "metadata": {"invoice_number": i.invoice_number, "days_overdue": i.days_overdue},
                })
        return matches

    async def _eval_collections(self, db: AsyncSession, tenant_id: UUID, rule: dict) -> List[dict]:
        cond = rule["condition"]
        activities = (await db.execute(
            select(CollectionActivity).where(CollectionActivity.tenant_id == tenant_id)
        )).scalars().all()

        today = date.today()
        matches = []
        for a in activities:
            if cond.get("ptp_past_due") and a.ptp_date and a.ptp_date < today and not a.ptp_fulfilled:
                matches.append({
                    "title": f"{rule['name']}",
                    "message": f"Promise to pay of {a.ptp_amount} was due {a.ptp_date} but unfulfilled",
                    "entity_type": "collection_activities",
                    "entity_id": str(a.id),
                    "action_url": f"/collections/{a.id}",
                    "metadata": {"ptp_amount": str(a.ptp_amount), "ptp_date": str(a.ptp_date)},
                })
        return matches

    async def _eval_credit_requests(self, db: AsyncSession, tenant_id: UUID, rule: dict) -> List[dict]:
        cond = rule["condition"]
        requests = (await db.execute(
            select(CreditLimitRequest).where(
                CreditLimitRequest.tenant_id == tenant_id,
                CreditLimitRequest.approval_status == CreditApprovalStatus.PENDING,
            )
        )).scalars().all()

        matches = []
        for r in requests:
            matches.append({
                "title": f"{rule['name']}",
                "message": f"Credit limit request: {r.current_limit} -> {r.requested_limit} (pending)",
                "entity_type": "credit_limit_requests",
                "entity_id": str(r.id),
                "action_url": f"/credit-limits/{r.id}",
                "metadata": {"current": str(r.current_limit), "requested": str(r.requested_limit)},
            })
        return matches

    @staticmethod
    def _compare(val, operator: str, target) -> bool:
        if val is None:
            return False
        try:
            if isinstance(val, Decimal):
                val = float(val)
            if isinstance(target, (int, float)) and isinstance(val, (int, float, Decimal)):
                val = float(val)
            if operator == "==":
                return val == target
            elif operator == "!=":
                return val != target
            elif operator == ">":
                return val > target
            elif operator == ">=":
                return val >= target
            elif operator == "<":
                return val < target
            elif operator == "<=":
                return val <= target
        except (TypeError, ValueError):
            return False
        return False

    # ── Rule CRUD ──

    def list_rules(self, tenant_id: str) -> List[dict]:
        _init_default_rules(tenant_id)
        return [r for r in _alert_rules.values() if r["tenant_id"] == tenant_id]

    def get_rule(self, tenant_id: str, rule_id: str) -> Optional[dict]:
        rule = _alert_rules.get(rule_id)
        if rule and rule["tenant_id"] == tenant_id:
            return rule
        return None

    def create_rule(self, tenant_id: str, data: dict) -> dict:
        rule_id = str(uuid4())
        rule = {
            "id": rule_id,
            "tenant_id": tenant_id,
            **data,
            "times_triggered": 0,
            "last_triggered_at": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _alert_rules[rule_id] = rule
        return rule

    def update_rule(self, tenant_id: str, rule_id: str, updates: dict) -> Optional[dict]:
        rule = _alert_rules.get(rule_id)
        if not rule or rule["tenant_id"] != tenant_id:
            return None
        for k, v in updates.items():
            if v is not None:
                rule[k] = v
        return rule

    def delete_rule(self, tenant_id: str, rule_id: str) -> bool:
        rule = _alert_rules.get(rule_id)
        if not rule or rule["tenant_id"] != tenant_id:
            return False
        del _alert_rules[rule_id]
        return True

    # ── Notification CRUD ──

    def list_notifications(self, tenant_id: str, user_id: str, is_read: Optional[bool] = None,
                           category: Optional[str] = None, page: int = 1, page_size: int = 20) -> dict:
        all_notifs = [n for n in _notifications.values()
                      if n["tenant_id"] == tenant_id and n["user_id"] == user_id]
        if is_read is not None:
            all_notifs = [n for n in all_notifs if n["is_read"] == is_read]
        if category:
            all_notifs = [n for n in all_notifs if n["category"] == category]

        all_notifs.sort(key=lambda x: x["created_at"], reverse=True)
        unread_count = sum(1 for n in _notifications.values()
                          if n["tenant_id"] == tenant_id and n["user_id"] == user_id and not n["is_read"])
        total = len(all_notifs)
        start = (page - 1) * page_size
        items = all_notifs[start:start + page_size]

        return {"items": items, "total": total, "unread_count": unread_count, "page": page, "page_size": page_size}

    def mark_read(self, tenant_id: str, user_id: str, notification_ids: List[str]) -> int:
        count = 0
        for nid in notification_ids:
            n = _notifications.get(nid)
            if n and n["tenant_id"] == tenant_id and n["user_id"] == user_id:
                n["is_read"] = True
                n["read_at"] = datetime.now(timezone.utc).isoformat()
                count += 1
        return count

    def mark_all_read(self, tenant_id: str, user_id: str) -> int:
        count = 0
        for n in _notifications.values():
            if n["tenant_id"] == tenant_id and n["user_id"] == user_id and not n["is_read"]:
                n["is_read"] = True
                n["read_at"] = datetime.now(timezone.utc).isoformat()
                count += 1
        return count


# Singleton
alert_engine = AlertEngine()
