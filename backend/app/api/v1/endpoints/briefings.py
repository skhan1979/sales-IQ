"""
Sales IQ - Briefing Endpoints
Generate, list, view, and schedule AI-powered briefings.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, RoleChecker
from app.models.core import User, UserRole, AuditLog
from app.models.business import Briefing
from app.agents.briefing import BriefingAgent
from app.schemas.briefings import (
    BriefingGenerateRequest, BriefingResponse,
    BriefingListResponse, BriefingScheduleRequest,
    BriefingScheduleResponse, BriefingScheduleListResponse,
    BriefingScheduleUpdate,
)

router = APIRouter()

# In-memory schedule store (production would use DB table or APScheduler)
_schedules: dict = {}


@router.post("/generate", response_model=BriefingResponse, status_code=status.HTTP_201_CREATED)
async def generate_briefing(
    request: BriefingGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new AI-powered briefing on demand."""
    recipient_id = request.recipient_id or current_user.id
    recipient_role = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)

    agent = BriefingAgent()

    try:
        briefing = await agent.generate_briefing(
            db=db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            recipient_id=recipient_id,
            recipient_role=recipient_role,
            briefing_type=request.briefing_type,
            sections=request.sections,
            date_from=request.date_from,
            date_to=request.date_to,
            delivery=request.delivery,
            customer_ids=request.customer_ids,
        )
    except Exception as e:
        raise HTTPException(500, f"Briefing generation failed: {str(e)}")

    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email, action="BRIEFING_GENERATE",
        entity_type="briefings", entity_id=briefing.id,
        after_state={
            "type": request.briefing_type,
            "generation_time_ms": briefing.generation_time_ms,
            "sections": len(briefing.sections) if briefing.sections else 0,
        },
    )
    db.add(audit)
    await db.commit()

    return BriefingResponse.model_validate(briefing)


@router.get("/", response_model=BriefingListResponse)
async def list_briefings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    recipient_id: Optional[UUID] = None,
    briefing_type: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List briefings with filtering and pagination."""
    query = select(Briefing).where(Briefing.tenant_id == current_user.tenant_id)

    if recipient_id:
        query = query.where(Briefing.recipient_id == recipient_id)
    if date_from:
        query = query.where(Briefing.briefing_date >= date_from)
    if date_to:
        query = query.where(Briefing.briefing_date <= date_to)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(Briefing.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    briefings = result.scalars().all()

    return BriefingListResponse(
        items=[BriefingResponse.model_validate(b) for b in briefings],
        total=total, page=page, page_size=page_size,
    )


@router.get("/latest", response_model=BriefingResponse)
async def get_latest_briefing(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the most recent briefing for the current user."""
    result = await db.execute(
        select(Briefing).where(
            Briefing.tenant_id == current_user.tenant_id,
            Briefing.recipient_id == current_user.id,
        ).order_by(Briefing.created_at.desc()).limit(1)
    )
    briefing = result.scalar_one_or_none()
    if not briefing:
        raise HTTPException(404, "No briefings found")
    return BriefingResponse.model_validate(briefing)


@router.get("/{briefing_id}", response_model=BriefingResponse)
async def get_briefing(
    briefing_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific briefing by ID."""
    result = await db.execute(
        select(Briefing).where(
            Briefing.id == briefing_id,
            Briefing.tenant_id == current_user.tenant_id,
        )
    )
    briefing = result.scalar_one_or_none()
    if not briefing:
        raise HTTPException(404, "Briefing not found")

    # Mark as opened if not already
    if not briefing.opened_at:
        briefing.opened_at = datetime.now(timezone.utc).isoformat()
        await db.commit()
        await db.refresh(briefing)

    return BriefingResponse.model_validate(briefing)


@router.get("/{briefing_id}/html")
async def get_briefing_html(
    briefing_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get briefing as rendered HTML (for email preview or iframe display)."""
    result = await db.execute(
        select(Briefing).where(
            Briefing.id == briefing_id,
            Briefing.tenant_id == current_user.tenant_id,
        )
    )
    briefing = result.scalar_one_or_none()
    if not briefing:
        raise HTTPException(404, "Briefing not found")

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=briefing.html_content or "<p>No HTML content available.</p>")


# ── Scheduling endpoints ──

@router.post("/schedules", response_model=BriefingScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    request: BriefingScheduleRequest,
    current_user: User = Depends(RoleChecker([UserRole.FINANCE_MANAGER], min_role=UserRole.FINANCE_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create an automated briefing schedule (finance_manager+)."""
    schedule_id = uuid4()

    schedule = {
        "id": schedule_id,
        "tenant_id": str(current_user.tenant_id),
        "briefing_type": request.briefing_type,
        "schedule_cron": request.schedule_cron,
        "recipient_ids": [str(r) for r in request.recipient_ids],
        "delivery": request.delivery,
        "sections": request.sections,
        "is_active": request.is_active,
        "timezone": request.timezone,
        "created_by": str(current_user.id),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "next_run": _calculate_next_run(request.schedule_cron, request.timezone),
        "last_run": None,
    }
    _schedules[str(schedule_id)] = schedule

    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email, action="SCHEDULE_CREATE",
        entity_type="briefing_schedules",
        after_state={"type": request.briefing_type, "cron": request.schedule_cron},
    )
    db.add(audit)
    await db.commit()

    return BriefingScheduleResponse(
        id=schedule_id,
        briefing_type=request.briefing_type,
        schedule_cron=request.schedule_cron,
        recipient_ids=request.recipient_ids,
        delivery=request.delivery,
        sections=request.sections,
        is_active=request.is_active,
        timezone=request.timezone,
        next_run=schedule["next_run"],
        created_at=datetime.now(timezone.utc),
    )


@router.get("/schedules/list", response_model=BriefingScheduleListResponse)
async def list_schedules(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all briefing schedules for the tenant."""
    tenant_schedules = [
        s for s in _schedules.values()
        if s["tenant_id"] == str(current_user.tenant_id)
    ]

    items = []
    for s in tenant_schedules:
        items.append(BriefingScheduleResponse(
            id=s["id"],
            briefing_type=s["briefing_type"],
            schedule_cron=s["schedule_cron"],
            recipient_ids=[UUID(r) for r in s["recipient_ids"]],
            delivery=s["delivery"],
            sections=s.get("sections"),
            is_active=s["is_active"],
            timezone=s["timezone"],
            next_run=s.get("next_run"),
            last_run=s.get("last_run"),
            created_at=datetime.fromisoformat(s["created_at"]) if s.get("created_at") else None,
        ))

    return BriefingScheduleListResponse(items=items, total=len(items))


@router.patch("/schedules/{schedule_id}", response_model=BriefingScheduleResponse)
async def update_schedule(
    schedule_id: UUID,
    request: BriefingScheduleUpdate,
    current_user: User = Depends(RoleChecker([UserRole.FINANCE_MANAGER], min_role=UserRole.FINANCE_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Update a briefing schedule."""
    schedule = _schedules.get(str(schedule_id))
    if not schedule or schedule["tenant_id"] != str(current_user.tenant_id):
        raise HTTPException(404, "Schedule not found")

    if request.is_active is not None:
        schedule["is_active"] = request.is_active
    if request.schedule_cron is not None:
        schedule["schedule_cron"] = request.schedule_cron
        schedule["next_run"] = _calculate_next_run(request.schedule_cron, schedule["timezone"])
    if request.recipient_ids is not None:
        schedule["recipient_ids"] = [str(r) for r in request.recipient_ids]
    if request.delivery is not None:
        schedule["delivery"] = request.delivery
    if request.sections is not None:
        schedule["sections"] = request.sections

    await db.commit()

    return BriefingScheduleResponse(
        id=schedule["id"],
        briefing_type=schedule["briefing_type"],
        schedule_cron=schedule["schedule_cron"],
        recipient_ids=[UUID(r) for r in schedule["recipient_ids"]],
        delivery=schedule["delivery"],
        sections=schedule.get("sections"),
        is_active=schedule["is_active"],
        timezone=schedule["timezone"],
        next_run=schedule.get("next_run"),
        last_run=schedule.get("last_run"),
        created_at=datetime.fromisoformat(schedule["created_at"]) if schedule.get("created_at") else None,
    )


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: UUID,
    current_user: User = Depends(RoleChecker([UserRole.FINANCE_MANAGER], min_role=UserRole.FINANCE_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a briefing schedule."""
    schedule = _schedules.get(str(schedule_id))
    if not schedule or schedule["tenant_id"] != str(current_user.tenant_id):
        raise HTTPException(404, "Schedule not found")

    del _schedules[str(schedule_id)]

    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email, action="SCHEDULE_DELETE",
        entity_type="briefing_schedules", entity_id=schedule_id,
    )
    db.add(audit)
    await db.commit()


def _calculate_next_run(cron_expression: str, tz: str) -> str:
    """
    Simple next-run estimator from cron expression.
    Production would use croniter library for precise calculation.
    """
    parts = cron_expression.split()
    if len(parts) < 5:
        return None

    now = datetime.now(timezone.utc)
    minute = parts[0]
    hour = parts[1]

    try:
        target_hour = int(hour) if hour != "*" else now.hour
        target_minute = int(minute) if minute != "*" else 0

        next_dt = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        if next_dt <= now:
            next_dt += timedelta(days=1)

        return next_dt.isoformat()
    except (ValueError, TypeError):
        return (now + timedelta(days=1)).isoformat()
