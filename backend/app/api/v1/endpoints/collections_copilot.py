"""
Sales IQ - Collections Copilot Endpoints
Day 13: AI message drafting, escalation templates, PTP tracking, dispute aging.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, RoleChecker
from app.models.core import User, UserRole, AuditLog
from app.services.collections_copilot import collections_copilot
from app.schemas.collections_copilot import (
    MessageDraftRequest, MessageDraftResponse, MessageSendRequest, MessageSendResponse,
    MessageHistoryListResponse, MessageHistoryResponse,
    EscalationTemplateCreate, EscalationTemplateUpdate,
    EscalationTemplateResponse, EscalationTemplateListResponse, EscalationRunResponse,
    PTPCreateRequest, PTPUpdateRequest, PTPResponse, PTPListResponse, PTPDashboard,
    DisputeAgingReport,
)

router = APIRouter()


# ── AI Message Drafting ──

@router.post("/draft", response_model=MessageDraftResponse, status_code=status.HTTP_201_CREATED)
async def draft_message(
    request: MessageDraftRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate an AI-drafted collection message for a customer."""
    try:
        draft = await collections_copilot.draft_message(
            db=db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            customer_id=request.customer_id,
            channel=request.channel,
            tone=request.tone,
            language=request.language,
            invoice_ids=request.invoice_ids,
            include_payment_link=request.include_payment_link,
            custom_instructions=request.custom_instructions,
        )
        return MessageDraftResponse(
            draft_id=UUID(draft["id"]),
            customer_id=UUID(draft["customer_id"]),
            customer_name=draft["customer_name"],
            channel=draft["channel"],
            tone=draft["tone"],
            language=draft["language"],
            subject=draft.get("subject"),
            body=draft["body"],
            invoices_referenced=draft["invoices_referenced"],
            total_amount_due=draft["total_amount_due"],
            currency=draft["currency"],
            ai_confidence=draft["ai_confidence"],
            suggested_follow_up_days=draft["suggested_follow_up_days"],
            metadata={"status": draft["status"], "created_at": draft["created_at"]},
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/draft/{draft_id}/send", response_model=MessageSendResponse)
async def send_drafted_message(
    draft_id: UUID,
    request: MessageSendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send or schedule a drafted message (optionally with edits)."""
    result = collections_copilot.send_message(
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.id),
        draft_id=str(draft_id),
        edited_subject=request.edited_subject,
        edited_body=request.edited_body,
        send_now=request.send_now,
        schedule_at=request.schedule_at.isoformat() if request.schedule_at else None,
    )
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Draft not found")

    # Audit log
    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email, action="SEND_MESSAGE",
        entity_type="collection_messages",
        after_state={"message_id": result["message_id"], "channel": result["channel"]},
    )
    db.add(audit)
    await db.commit()

    return MessageSendResponse(
        message_id=UUID(result["message_id"]),
        draft_id=UUID(result["draft_id"]),
        status=result["status"],
        channel=result["channel"],
        sent_at=result.get("sent_at"),
        scheduled_at=result.get("scheduled_at"),
    )


@router.get("/messages", response_model=MessageHistoryListResponse)
async def list_messages(
    customer_id: Optional[UUID] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List sent collection message history."""
    result = collections_copilot.list_messages(
        tenant_id=str(current_user.tenant_id),
        customer_id=str(customer_id) if customer_id else None,
        page=page, page_size=page_size,
    )
    items = [MessageHistoryResponse(
        id=UUID(m["id"]),
        customer_id=UUID(m["customer_id"]),
        customer_name=m["customer_name"],
        channel=m["channel"],
        tone=m["tone"],
        subject=m.get("subject"),
        body=m["body"],
        status=m["status"],
        sent_at=m.get("sent_at"),
        opened_at=m.get("opened_at"),
        replied_at=m.get("replied_at"),
        invoices_referenced=m["invoices_referenced"],
        total_amount=m["total_amount"],
        currency=m["currency"],
    ) for m in result["items"]]
    return MessageHistoryListResponse(
        items=items, total=result["total"], page=result["page"], page_size=result["page_size"],
    )


# ── Escalation Templates ──

@router.get("/templates", response_model=EscalationTemplateListResponse)
async def list_escalation_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all escalation templates for the tenant."""
    templates = collections_copilot.list_templates(str(current_user.tenant_id))
    items = [EscalationTemplateResponse(
        id=UUID(t["id"]), name=t["name"], description=t.get("description"),
        trigger_type=t["trigger_type"], trigger_threshold=t["trigger_threshold"],
        steps=t["steps"], applies_to_segments=t.get("applies_to_segments"),
        is_active=t["is_active"], times_triggered=t.get("times_triggered", 0),
        last_triggered_at=t.get("last_triggered_at"),
        created_at=t.get("created_at"),
    ) for t in templates]
    return EscalationTemplateListResponse(items=items, total=len(items))


@router.post("/templates", response_model=EscalationTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_escalation_template(
    request: EscalationTemplateCreate,
    current_user: User = Depends(RoleChecker([UserRole.FINANCE_MANAGER], min_role=UserRole.FINANCE_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create an escalation template (finance_manager+ only)."""
    data = request.model_dump()
    # Convert EscalationStep models to dicts for storage
    data["steps"] = [s.model_dump() if hasattr(s, "model_dump") else s for s in data["steps"]]
    template = collections_copilot.create_template(str(current_user.tenant_id), data)

    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email, action="CREATE",
        entity_type="escalation_templates",
        after_state={"name": template["name"], "trigger_type": template["trigger_type"]},
    )
    db.add(audit)
    await db.commit()

    return EscalationTemplateResponse(
        id=UUID(template["id"]), name=template["name"], description=template.get("description"),
        trigger_type=template["trigger_type"], trigger_threshold=template["trigger_threshold"],
        steps=template["steps"], applies_to_segments=template.get("applies_to_segments"),
        is_active=template["is_active"], times_triggered=0,
        created_at=template.get("created_at"),
    )


@router.patch("/templates/{template_id}", response_model=EscalationTemplateResponse)
async def update_escalation_template(
    template_id: UUID,
    request: EscalationTemplateUpdate,
    current_user: User = Depends(RoleChecker([UserRole.FINANCE_MANAGER], min_role=UserRole.FINANCE_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Update an escalation template."""
    updates = request.model_dump(exclude_unset=True)
    if "steps" in updates and updates["steps"] is not None:
        updates["steps"] = [s.model_dump() if hasattr(s, "model_dump") else s for s in updates["steps"]]
    updated = collections_copilot.update_template(str(current_user.tenant_id), str(template_id), updates)
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    return EscalationTemplateResponse(
        id=UUID(updated["id"]), name=updated["name"], description=updated.get("description"),
        trigger_type=updated["trigger_type"], trigger_threshold=updated["trigger_threshold"],
        steps=updated["steps"], applies_to_segments=updated.get("applies_to_segments"),
        is_active=updated["is_active"], times_triggered=updated.get("times_triggered", 0),
        last_triggered_at=updated.get("last_triggered_at"),
        created_at=updated.get("created_at"),
    )


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_escalation_template(
    template_id: UUID,
    current_user: User = Depends(RoleChecker([UserRole.FINANCE_MANAGER], min_role=UserRole.FINANCE_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Delete an escalation template."""
    if not collections_copilot.delete_template(str(current_user.tenant_id), str(template_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")


# ── Escalation Scan ──

@router.post("/escalations/scan", response_model=EscalationRunResponse)
async def run_escalation_scan(
    current_user: User = Depends(RoleChecker([UserRole.FINANCE_MANAGER], min_role=UserRole.FINANCE_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate all active escalation templates and queue actions."""
    result = await collections_copilot.run_escalation_scan(db, current_user.tenant_id)
    return EscalationRunResponse(**result)


# ── Enhanced PTP Tracking ──

@router.post("/ptp", response_model=PTPResponse, status_code=status.HTTP_201_CREATED)
async def create_ptp(
    request: PTPCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Promise-to-Pay record."""
    try:
        ptp = await collections_copilot.create_ptp(
            db=db, tenant_id=current_user.tenant_id, user_id=current_user.id,
            data=request.model_dump(),
        )
        return PTPResponse(**{k: v for k, v in ptp.items() if k not in ("tenant_id", "user_id")})
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.patch("/ptp/{ptp_id}", response_model=PTPResponse)
async def update_ptp(
    ptp_id: UUID,
    request: PTPUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update PTP status, actual amount, or notes."""
    updates = request.model_dump(exclude_unset=True)
    updated = collections_copilot.update_ptp(str(current_user.tenant_id), str(ptp_id), updates)
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PTP record not found")
    return PTPResponse(**{k: v for k, v in updated.items() if k not in ("tenant_id", "user_id")})


@router.get("/ptp", response_model=PTPListResponse)
async def list_ptps(
    ptp_status: Optional[str] = Query(None, alias="status"),
    customer_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List PTP records with optional filters."""
    result = collections_copilot.list_ptps(
        tenant_id=str(current_user.tenant_id),
        status=ptp_status,
        customer_id=str(customer_id) if customer_id else None,
    )
    items = [PTPResponse(**{k: v for k, v in p.items() if k not in ("tenant_id", "user_id")})
             for p in result["items"]]
    return PTPListResponse(items=items, total=result["total"], summary=result["summary"])


@router.get("/ptp/dashboard", response_model=PTPDashboard)
async def get_ptp_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get PTP overview dashboard metrics."""
    dashboard = collections_copilot.get_ptp_dashboard(str(current_user.tenant_id))
    return PTPDashboard(**dashboard)


# ── Dispute Aging ──

@router.get("/disputes/aging", response_model=DisputeAgingReport)
async def get_dispute_aging(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate dispute aging report with resolution analytics."""
    report = await collections_copilot.get_dispute_aging(db, current_user.tenant_id)
    return DisputeAgingReport(**report)
