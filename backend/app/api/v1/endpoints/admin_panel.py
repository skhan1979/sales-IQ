"""
Sales IQ - Admin Panel Endpoints
Day 18: User settings, user management, business rules, system monitor,
        audit log, agent hub enhancements, demo data manager presets.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, RoleChecker
from app.models.core import User, UserRole, AuditLog
from app.services.admin import admin_service
from app.schemas.admin import (
    UserProfileUpdate, PasswordChangeRequest, NotificationPreferences,
    UserSettingsResponse, UserInviteRequest, UserRoleUpdate,
    AdminUserResponse, AdminUserListResponse,
    BusinessRulesConfig, BusinessRulesResponse,
    SystemHealthResponse, AuditLogListResponse,
    AgentDependencyMap, AgentPerformanceHistory,
    DemoPresetListResponse, DemoDataSummary, DemoGenerateWithPresetRequest,
)

router = APIRouter()


# ═══════════════════════════════════════════════
# USER SETTINGS
# ═══════════════════════════════════════════════

@router.get("/settings/me", response_model=UserSettingsResponse)
async def get_my_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's profile and preferences."""
    result = await admin_service.get_user_settings(db, current_user)
    return UserSettingsResponse(**result)


@router.put("/settings/me", response_model=UserSettingsResponse)
async def update_my_profile(
    body: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's profile."""
    result = await admin_service.update_user_profile(db, current_user, body.model_dump(exclude_unset=True))
    return UserSettingsResponse(**result)


@router.put("/settings/me/notifications", response_model=NotificationPreferences)
async def update_notification_prefs(
    body: NotificationPreferences,
    current_user: User = Depends(get_current_user),
):
    """Update notification preferences."""
    result = admin_service.update_notification_preferences(current_user.id, body.model_dump())
    return NotificationPreferences(**result)


# ═══════════════════════════════════════════════
# USER MANAGEMENT (Admin)
# ═══════════════════════════════════════════════

@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all tenant users (admin view)."""
    result = await admin_service.list_users(db, current_user.tenant_id, page, page_size)
    return AdminUserListResponse(**result)


@router.post("/users/invite", response_model=AdminUserResponse, status_code=201)
async def invite_user(
    body: UserInviteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Invite (create) a new user."""
    result = await admin_service.invite_user(
        db, current_user.tenant_id, current_user.id, body.model_dump(),
    )
    if "error" in result:
        raise HTTPException(400, result["error"])

    # Audit
    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email, action="USER_INVITE",
        entity_type="user", after_state={"email": body.email, "role": body.role},
    )
    db.add(audit)
    await db.commit()

    return AdminUserResponse(**result)


@router.put("/users/{user_id}/role", response_model=AdminUserResponse)
async def update_user_role(
    user_id: UUID,
    body: UserRoleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a user's role and territory assignments."""
    result = await admin_service.update_user_role(
        db, current_user.tenant_id, user_id, body.model_dump(),
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return AdminUserResponse(**result)


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a user account."""
    result = await admin_service.deactivate_user(db, current_user.tenant_id, user_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


# ═══════════════════════════════════════════════
# BUSINESS RULES
# ═══════════════════════════════════════════════

@router.get("/business-rules", response_model=BusinessRulesResponse)
async def get_business_rules(
    current_user: User = Depends(get_current_user),
):
    """Get current business rules configuration."""
    result = admin_service.get_business_rules(current_user.tenant_id)
    return BusinessRulesResponse(**result)


@router.put("/business-rules", response_model=BusinessRulesResponse)
async def update_business_rules(
    body: BusinessRulesConfig,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update business rules (scoring weights, thresholds, etc.)."""
    result = admin_service.update_business_rules(
        current_user.tenant_id, body.model_dump(exclude_unset=True), current_user.email,
    )

    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email, action="BUSINESS_RULES_UPDATE",
        entity_type="business_rules", after_state=body.model_dump(exclude_unset=True),
    )
    db.add(audit)
    await db.commit()

    return BusinessRulesResponse(**result)


# ═══════════════════════════════════════════════
# SYSTEM MONITOR
# ═══════════════════════════════════════════════

@router.get("/system/health", response_model=SystemHealthResponse)
async def get_system_health(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """System health and monitoring overview."""
    result = await admin_service.get_system_health(db, current_user.tenant_id)
    return SystemHealthResponse(**result)


# ═══════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════

@router.get("/audit-logs", response_model=AuditLogListResponse)
async def get_audit_logs(
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    user_email: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Searchable, filterable audit log viewer."""
    result = await admin_service.get_audit_logs(
        db, current_user.tenant_id,
        action=action, entity_type=entity_type, user_email=user_email,
        page=page, page_size=page_size,
    )
    return AuditLogListResponse(**result)


# ═══════════════════════════════════════════════
# AGENT HUB ENHANCEMENTS
# ═══════════════════════════════════════════════

@router.get("/agents/dependency-map", response_model=AgentDependencyMap)
async def get_agent_dependency_map(
    current_user: User = Depends(get_current_user),
):
    """Agent dependency/interaction graph."""
    result = admin_service.get_agent_dependency_map()
    return AgentDependencyMap(**result)


@router.get("/agents/{agent_name}/performance", response_model=AgentPerformanceHistory)
async def get_agent_performance(
    agent_name: str,
    days: int = Query(7, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Historical performance chart for a specific agent."""
    result = await admin_service.get_agent_performance_history(
        db, current_user.tenant_id, agent_name, days,
    )
    return AgentPerformanceHistory(**result)


# ═══════════════════════════════════════════════
# DEMO DATA MANAGER ENHANCEMENTS
# ═══════════════════════════════════════════════

@router.get("/demo/presets", response_model=DemoPresetListResponse)
async def get_demo_presets(
    current_user: User = Depends(get_current_user),
):
    """List available demo data preset templates."""
    result = admin_service.get_demo_presets()
    return DemoPresetListResponse(**result)


@router.get("/demo/presets/{preset_id}")
async def get_demo_preset(
    preset_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get a specific demo preset with its parameters."""
    result = admin_service.get_preset_by_id(preset_id)
    if not result:
        raise HTTPException(404, f"Preset '{preset_id}' not found")
    return result


@router.get("/demo/summary", response_model=DemoDataSummary)
async def get_demo_data_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Summary of current demo data record counts per entity."""
    result = await admin_service.get_demo_data_summary(db, current_user.tenant_id)
    return DemoDataSummary(**result)


@router.post("/demo/generate-preset")
async def generate_from_preset(
    body: DemoGenerateWithPresetRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate demo data using a preset template or custom parameters."""
    # If preset_id provided, use its settings
    preset = None
    if body.preset_id:
        preset = admin_service.get_preset_by_id(body.preset_id)
        if not preset:
            raise HTTPException(404, f"Preset '{body.preset_id}' not found")

    # Use existing demo-data/generate endpoint logic
    from app.services.demo_data import DemoDataManager
    manager = DemoDataManager()

    erp = preset["erp_profile"] if preset else body.erp_profile
    size = preset["dataset_size"] if preset else body.dataset_size

    result = await manager.generate(
        db=db, tenant_id=current_user.tenant_id,
        user_id=current_user.id, dataset_size=size, erp_profile=erp,
    )

    # Audit
    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email, action="DEMO_GENERATE",
        entity_type="demo_data",
        after_state={
            "preset_id": body.preset_id, "erp_profile": erp,
            "size": size, "records": result.get("total_records"),
        },
    )
    db.add(audit)
    await db.commit()

    return {
        "preset_used": body.preset_id,
        "erp_profile": erp,
        "dataset_size": size,
        **result,
    }
