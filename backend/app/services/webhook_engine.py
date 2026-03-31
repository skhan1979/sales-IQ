"""
Sales IQ - Webhook & Integration Engine
Day 12: Event bus, webhook subscription management, simulated delivery, and delivery logging.
In-memory implementation for MVP — production would use a message queue (Redis Streams / RabbitMQ).
"""

import hashlib
import hmac
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4


# ── In-memory stores ──

_webhooks: Dict[str, dict] = {}           # webhook_id -> webhook config
_events: Dict[str, dict] = {}             # event_id -> event record
_delivery_logs: Dict[str, dict] = {}      # delivery_id -> delivery log
_event_handlers: Dict[str, List] = defaultdict(list)  # event_type -> [handler_fn]


class WebhookEngine:
    """Manages webhook subscriptions, event publishing, and simulated delivery."""

    MAX_FAILURES_BEFORE_DISABLE = 10

    # ── Webhook CRUD ──

    def create_webhook(self, tenant_id: str, data: dict) -> dict:
        wh_id = str(uuid4())
        webhook = {
            "id": wh_id,
            "tenant_id": tenant_id,
            "name": data["name"],
            "url": data["url"],
            "events": data["events"],
            "secret": data.get("secret"),
            "headers": data.get("headers"),
            "is_active": data.get("is_active", True),
            "status": "active" if data.get("is_active", True) else "paused",
            "retry_count": data.get("retry_count", 3),
            "timeout_seconds": data.get("timeout_seconds", 30),
            "description": data.get("description"),
            "total_deliveries": 0,
            "successful_deliveries": 0,
            "failed_deliveries": 0,
            "last_delivery_at": None,
            "last_delivery_status": None,
            "consecutive_failures": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _webhooks[wh_id] = webhook
        return webhook

    def list_webhooks(self, tenant_id: str) -> List[dict]:
        return [w for w in _webhooks.values() if w["tenant_id"] == tenant_id]

    def get_webhook(self, tenant_id: str, webhook_id: str) -> Optional[dict]:
        wh = _webhooks.get(webhook_id)
        if wh and wh["tenant_id"] == tenant_id:
            return wh
        return None

    def update_webhook(self, tenant_id: str, webhook_id: str, updates: dict) -> Optional[dict]:
        wh = _webhooks.get(webhook_id)
        if not wh or wh["tenant_id"] != tenant_id:
            return None
        for k, v in updates.items():
            if v is not None:
                wh[k] = v
        if "is_active" in updates:
            wh["status"] = "active" if updates["is_active"] else "paused"
            if updates["is_active"]:
                wh["consecutive_failures"] = 0
        return wh

    def delete_webhook(self, tenant_id: str, webhook_id: str) -> bool:
        wh = _webhooks.get(webhook_id)
        if not wh or wh["tenant_id"] != tenant_id:
            return False
        del _webhooks[webhook_id]
        return True

    # ── Event Publishing ──

    def publish_event(self, tenant_id: str, event_type: str,
                      entity_type: Optional[str] = None,
                      entity_id: Optional[str] = None,
                      payload: Optional[dict] = None,
                      user_id: Optional[str] = None) -> dict:
        """Publish an event and trigger matching webhooks."""
        event_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()

        event = {
            "id": event_id,
            "tenant_id": tenant_id,
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload or {},
            "user_id": user_id,
            "webhooks_triggered": 0,
            "created_at": now,
        }

        # Find matching webhooks
        matching = [
            w for w in _webhooks.values()
            if w["tenant_id"] == tenant_id
            and w["is_active"]
            and w["status"] == "active"
            and event_type in w["events"]
        ]

        deliveries_queued = 0
        for wh in matching:
            delivery = self._deliver(wh, event)
            deliveries_queued += 1

        event["webhooks_triggered"] = len(matching)
        _events[event_id] = event

        # Call registered internal handlers
        for handler in _event_handlers.get(event_type, []):
            try:
                handler(event)
            except Exception:
                pass

        return {
            "event_id": event_id,
            "event_type": event_type,
            "webhooks_matched": len(matching),
            "deliveries_queued": deliveries_queued,
        }

    def _deliver(self, webhook: dict, event: dict) -> dict:
        """Simulate webhook delivery (in production, this would be async HTTP POST)."""
        start = time.time()
        delivery_id = str(uuid4())

        # Build payload
        payload = {
            "event_id": event["id"],
            "event_type": event["event_type"],
            "timestamp": event["created_at"],
            "tenant_id": event["tenant_id"],
            "data": {
                "entity_type": event.get("entity_type"),
                "entity_id": event.get("entity_id"),
                **event.get("payload", {}),
            },
        }
        payload_json = json.dumps(payload, default=str)

        # Compute HMAC signature if secret is configured
        signature = None
        if webhook.get("secret"):
            signature = hmac.new(
                webhook["secret"].encode(),
                payload_json.encode(),
                hashlib.sha256,
            ).hexdigest()

        # Simulate delivery (always succeeds in MVP)
        # In production: async HTTP POST with retry queue
        duration_ms = int((time.time() - start) * 1000) + 1  # min 1ms
        success = True  # Simulated success

        delivery = {
            "id": delivery_id,
            "webhook_id": webhook["id"],
            "event_type": event["event_type"],
            "event_id": event["id"],
            "status": "success" if success else "failed",
            "attempt": 1,
            "response_code": 200 if success else None,
            "response_body": '{"ok": true}' if success else None,
            "error_message": None,
            "duration_ms": duration_ms,
            "payload_size": len(payload_json),
            "signature": signature,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _delivery_logs[delivery_id] = delivery

        # Update webhook stats
        webhook["total_deliveries"] += 1
        if success:
            webhook["successful_deliveries"] += 1
            webhook["consecutive_failures"] = 0
        else:
            webhook["failed_deliveries"] += 1
            webhook["consecutive_failures"] += 1
            if webhook["consecutive_failures"] >= self.MAX_FAILURES_BEFORE_DISABLE:
                webhook["status"] = "failed"
                webhook["is_active"] = False

        webhook["last_delivery_at"] = datetime.now(timezone.utc).isoformat()
        webhook["last_delivery_status"] = "success" if success else "failed"

        return delivery

    # ── Test Webhook ──

    def test_webhook(self, tenant_id: str, webhook_id: str) -> dict:
        """Send a test event to a webhook."""
        wh = _webhooks.get(webhook_id)
        if not wh or wh["tenant_id"] != tenant_id:
            return {"success": False, "error": "Webhook not found"}

        start = time.time()
        test_event = {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "event_type": "webhook.test",
            "entity_type": None,
            "entity_id": None,
            "payload": {"message": "This is a test webhook delivery from Sales IQ"},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        delivery = self._deliver(wh, test_event)
        duration_ms = int((time.time() - start) * 1000) + 1

        return {
            "webhook_id": webhook_id,
            "success": delivery["status"] == "success",
            "response_code": delivery.get("response_code"),
            "response_body": delivery.get("response_body"),
            "error": delivery.get("error_message"),
            "duration_ms": duration_ms,
        }

    # ── Delivery Logs ──

    def list_delivery_logs(self, tenant_id: str, webhook_id: Optional[str] = None,
                            status: Optional[str] = None,
                            page: int = 1, page_size: int = 20) -> dict:
        """List delivery logs with optional filtering."""
        # Get all webhooks for this tenant
        tenant_wh_ids = {w["id"] for w in _webhooks.values() if w["tenant_id"] == tenant_id}

        logs = [
            dl for dl in _delivery_logs.values()
            if dl["webhook_id"] in tenant_wh_ids
        ]

        if webhook_id:
            logs = [dl for dl in logs if dl["webhook_id"] == webhook_id]
        if status:
            logs = [dl for dl in logs if dl["status"] == status]

        logs.sort(key=lambda x: x["created_at"], reverse=True)
        total = len(logs)
        start_idx = (page - 1) * page_size
        items = logs[start_idx:start_idx + page_size]

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    # ── Event Logs ──

    def list_events(self, tenant_id: str, event_type: Optional[str] = None,
                    page: int = 1, page_size: int = 20) -> dict:
        """List published events."""
        events = [e for e in _events.values() if e["tenant_id"] == tenant_id]

        if event_type:
            events = [e for e in events if e["event_type"] == event_type]

        events.sort(key=lambda x: x["created_at"], reverse=True)
        total = len(events)
        start_idx = (page - 1) * page_size
        items = events[start_idx:start_idx + page_size]

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    # ── Event Handlers (Internal) ──

    def register_handler(self, event_type: str, handler):
        """Register an internal event handler."""
        _event_handlers[event_type].append(handler)

    # ── Supported Events ──

    @staticmethod
    def list_event_types() -> List[dict]:
        """Return all supported event types with descriptions."""
        from app.schemas.webhooks import EventType
        return [
            {"event_type": et.value, "category": et.value.split(".")[0],
             "name": et.name.replace("_", " ").title()}
            for et in EventType
        ]


# Singleton
webhook_engine = WebhookEngine()
