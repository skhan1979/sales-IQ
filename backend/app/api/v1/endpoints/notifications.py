"""
Sales IQ - Notification & Alert Endpoints
Day 10: Alert rules, notification inbox, and scan triggers.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, RoleChecker
from app.models.core import User, UserRole, AuditLog
from app.services.alert_engine import alert_engine
from app.schemas.notifications import (
    AlertRuleCreate, AlertRuleUpdate, AlertRuleResponse, AlertRuleListResponse,
    NotificationResponse, NotificationListResponse, NotificationMarkRead,
    AlertScanResponse,
)

router = APIRouter()


# ── Alert Rules ──

@router.get("/rules", response_model=AlertRuleListResponse)
async def list_alert_rules(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all alert rules for the tenant."""
    rules = alert_engine.list_rules(str(current_user.tenant_id))
    items = [AlertRuleResponse(
        id=UUID(r["id"]), name=r["name"], description=r.get("description"),
        category=r["category"], severity=r["severity"], condition=r["condition"],
        channels=r["channels"], recipient_roles=r.get("recipient_roles"),
        recipient_user_ids=r.get("recipient_user_ids"),
        is_active=r["is_active"], cooldown_minutes=r["cooldown_minutes"],
        times_triggered=r["times_triggered"], last_triggered_at=r.get("last_triggered_at"),
    ) for r in rules]
    return AlertRuleListResponse(items=items, total=len(items))


@router.post("/rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    request: AlertRuleCreate,
    current_user: User = Depends(RoleChecker([UserRole.FINANCE_MANAGER], min_role=UserRole.FINANCE_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a custom alert rule."""
    rule = alert_engine.create_rule(str(current_user.tenant_id), request.model_dump())
    return AlertRuleResponse(
        id=UUID(rule["id"]), name=rule["name"], description=rule.get("description"),
        category=rule["category"], severity=rule["severity"], condition=rule["condition"],
        channels=rule["channels"], is_active=rule["is_active"],
        cooldown_minutes=rule["cooldown_minutes"], times_triggered=0,
    )


@router.patch("/rules/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: UUID,
    request: AlertRuleUpdate,
    current_user: User = Depends(RoleChecker([UserRole.FINANCE_MANAGER], min_role=UserRole.FINANCE_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Update an alert rule."""
    updated = alert_engine.update_rule(str(current_user.tenant_id), str(rule_id), request.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(404, "Rule not found")
    return AlertRuleResponse(
        id=UUID(updated["id"]), name=updated["name"], description=updated.get("description"),
        category=updated["category"], severity=updated["severity"], condition=updated["condition"],
        channels=updated["channels"], is_active=updated["is_active"],
        cooldown_minutes=updated["cooldown_minutes"], times_triggered=updated["times_triggered"],
        last_triggered_at=updated.get("last_triggered_at"),
    )


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: UUID,
    current_user: User = Depends(RoleChecker([UserRole.FINANCE_MANAGER], min_role=UserRole.FINANCE_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Delete an alert rule."""
    if not alert_engine.delete_rule(str(current_user.tenant_id), str(rule_id)):
        raise HTTPException(404, "Rule not found")


# ── Alert Scan ──

@router.post("/scan", response_model=AlertScanResponse)
async def run_alert_scan(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate all active rules and generate notifications."""
    result = await alert_engine.scan(db, current_user.tenant_id, current_user.id)
    return AlertScanResponse(**result)


# ── Notifications ──

@router.get("/inbox", response_model=NotificationListResponse)
async def get_notifications(
    is_read: Optional[bool] = None,
    category: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user notification inbox."""
    result = alert_engine.list_notifications(
        str(current_user.tenant_id), str(current_user.id),
        is_read=is_read, category=category, page=page, page_size=page_size,
    )
    items = [NotificationResponse(
        id=UUID(n["id"]), alert_rule_id=UUID(n["alert_rule_id"]) if n.get("alert_rule_id") else None,
        category=n["category"], severity=n["severity"], title=n["title"], message=n["message"],
        entity_type=n.get("entity_type"), entity_id=n.get("entity_id"),
        channel=n["channel"], is_read=n["is_read"], read_at=n.get("read_at"),
        action_url=n.get("action_url"), metadata=n.get("metadata"),
    ) for n in result["items"]]
    return NotificationListResponse(
        items=items, total=result["total"], unread_count=result["unread_count"],
        page=result["page"], page_size=result["page_size"],
    )


@router.post("/inbox/mark-read")
async def mark_notifications_read(
    request: NotificationMarkRead,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark specific notifications as read."""
    count = alert_engine.mark_read(
        str(current_user.tenant_id), str(current_user.id),
        [str(nid) for nid in request.notification_ids],
    )
    return {"marked_read": count}


@router.post("/inbox/mark-all-read")
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all notifications as read."""
    count = alert_engine.mark_all_read(str(current_user.tenant_id), str(current_user.id))
    return {"marked_read": count}
