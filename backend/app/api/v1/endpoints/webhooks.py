"""
Sales IQ - Webhook & Integration Endpoints
Day 12: Webhook CRUD, event publishing, delivery logs, and test endpoints.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, RoleChecker
from app.models.core import User, UserRole, AuditLog
from app.services.webhook_engine import webhook_engine
from app.schemas.webhooks import (
    WebhookCreate, WebhookUpdate, WebhookResponse, WebhookListResponse,
    DeliveryLogResponse, DeliveryLogListResponse,
    EventLogResponse, EventLogListResponse,
    EventPublish, EventPublishResponse,
    WebhookTestResponse,
)

router = APIRouter()


# ── Webhook Subscriptions ──

@router.get("/webhooks", response_model=WebhookListResponse)
async def list_webhooks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all webhook subscriptions for the tenant."""
    webhooks = webhook_engine.list_webhooks(str(current_user.tenant_id))
    items = [WebhookResponse(
        id=UUID(w["id"]), name=w["name"], url=w["url"], events=w["events"],
        headers=w.get("headers"), is_active=w["is_active"], status=w["status"],
        retry_count=w["retry_count"], timeout_seconds=w["timeout_seconds"],
        description=w.get("description"),
        total_deliveries=w["total_deliveries"],
        successful_deliveries=w["successful_deliveries"],
        failed_deliveries=w["failed_deliveries"],
        last_delivery_at=w.get("last_delivery_at"),
        last_delivery_status=w.get("last_delivery_status"),
    ) for w in webhooks]
    return WebhookListResponse(items=items, total=len(items))


@router.post("/webhooks", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    request: WebhookCreate,
    current_user: User = Depends(RoleChecker([UserRole.FINANCE_MANAGER], min_role=UserRole.FINANCE_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new webhook subscription (finance_manager+)."""
    # Validate event types
    valid_types = {et["event_type"] for et in webhook_engine.list_event_types()}
    invalid = set(request.events) - valid_types
    if invalid:
        raise HTTPException(400, f"Invalid event types: {', '.join(invalid)}")

    wh = webhook_engine.create_webhook(str(current_user.tenant_id), request.model_dump())

    # Audit
    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email, action="WEBHOOK_CREATE",
        entity_type="webhooks",
        after_state={"name": wh["name"], "url": wh["url"], "events": wh["events"]},
    )
    db.add(audit)
    await db.commit()

    return WebhookResponse(
        id=UUID(wh["id"]), name=wh["name"], url=wh["url"], events=wh["events"],
        headers=wh.get("headers"), is_active=wh["is_active"], status=wh["status"],
        retry_count=wh["retry_count"], timeout_seconds=wh["timeout_seconds"],
        description=wh.get("description"), total_deliveries=0,
        successful_deliveries=0, failed_deliveries=0,
    )


@router.patch("/webhooks/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: UUID,
    request: WebhookUpdate,
    current_user: User = Depends(RoleChecker([UserRole.FINANCE_MANAGER], min_role=UserRole.FINANCE_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Update a webhook subscription."""
    updated = webhook_engine.update_webhook(
        str(current_user.tenant_id), str(webhook_id),
        request.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(404, "Webhook not found")

    return WebhookResponse(
        id=UUID(updated["id"]), name=updated["name"], url=updated["url"],
        events=updated["events"], headers=updated.get("headers"),
        is_active=updated["is_active"], status=updated["status"],
        retry_count=updated["retry_count"], timeout_seconds=updated["timeout_seconds"],
        description=updated.get("description"),
        total_deliveries=updated["total_deliveries"],
        successful_deliveries=updated["successful_deliveries"],
        failed_deliveries=updated["failed_deliveries"],
        last_delivery_at=updated.get("last_delivery_at"),
        last_delivery_status=updated.get("last_delivery_status"),
    )


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: UUID,
    current_user: User = Depends(RoleChecker([UserRole.FINANCE_MANAGER], min_role=UserRole.FINANCE_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a webhook subscription."""
    if not webhook_engine.delete_webhook(str(current_user.tenant_id), str(webhook_id)):
        raise HTTPException(404, "Webhook not found")

    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email, action="WEBHOOK_DELETE",
        entity_type="webhooks", entity_id=webhook_id,
    )
    db.add(audit)
    await db.commit()


# ── Webhook Test ──

@router.post("/webhooks/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook(
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a test event to a webhook endpoint."""
    result = webhook_engine.test_webhook(str(current_user.tenant_id), str(webhook_id))
    if result.get("error") == "Webhook not found":
        raise HTTPException(404, "Webhook not found")
    return WebhookTestResponse(**{**result, "webhook_id": webhook_id})


# ── Event Publishing ──

@router.post("/events", response_model=EventPublishResponse, status_code=status.HTTP_201_CREATED)
async def publish_event(
    request: EventPublish,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Publish an event to trigger matching webhooks."""
    valid_types = {et["event_type"] for et in webhook_engine.list_event_types()}
    if request.event_type not in valid_types:
        raise HTTPException(400, f"Invalid event_type: {request.event_type}")

    result = webhook_engine.publish_event(
        tenant_id=str(current_user.tenant_id),
        event_type=request.event_type,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        payload=request.payload,
        user_id=str(current_user.id),
    )

    return EventPublishResponse(
        event_id=UUID(result["event_id"]),
        event_type=result["event_type"],
        webhooks_matched=result["webhooks_matched"],
        deliveries_queued=result["deliveries_queued"],
    )


# ── Event Types ──

@router.get("/event-types")
async def list_event_types(
    current_user: User = Depends(get_current_user),
):
    """List all supported event types."""
    return {"event_types": webhook_engine.list_event_types()}


# ── Event Log ──

@router.get("/events", response_model=EventLogListResponse)
async def list_events(
    event_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List published events."""
    result = webhook_engine.list_events(
        str(current_user.tenant_id), event_type=event_type,
        page=page, page_size=page_size,
    )
    items = [EventLogResponse(
        id=UUID(e["id"]), event_type=e["event_type"],
        entity_type=e.get("entity_type"), entity_id=e.get("entity_id"),
        payload=e["payload"], webhooks_triggered=e["webhooks_triggered"],
        created_at=e.get("created_at"),
    ) for e in result["items"]]
    return EventLogListResponse(
        items=items, total=result["total"], page=result["page"], page_size=result["page_size"],
    )


# ── Delivery Logs ──

@router.get("/deliveries", response_model=DeliveryLogListResponse)
async def list_delivery_logs(
    webhook_id: Optional[UUID] = None,
    delivery_status: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List webhook delivery logs."""
    result = webhook_engine.list_delivery_logs(
        str(current_user.tenant_id),
        webhook_id=str(webhook_id) if webhook_id else None,
        status=delivery_status,
        page=page, page_size=page_size,
    )
    items = [DeliveryLogResponse(
        id=UUID(dl["id"]), webhook_id=UUID(dl["webhook_id"]),
        event_type=dl["event_type"], event_id=UUID(dl["event_id"]),
        status=dl["status"], attempt=dl["attempt"],
        response_code=dl.get("response_code"),
        response_body=dl.get("response_body"),
        error_message=dl.get("error_message"),
        duration_ms=dl.get("duration_ms"),
        payload_size=dl.get("payload_size", 0),
        created_at=dl.get("created_at"),
    ) for dl in result["items"]]
    return DeliveryLogListResponse(
        items=items, total=result["total"], page=result["page"], page_size=result["page_size"],
    )
