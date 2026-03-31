"""
Sales IQ - CFO Dashboard Endpoints
Day 15: Enhanced AR dashboard, write-off management, IFRS 9 ECL provisioning.
"""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, RoleChecker
from app.models.core import User, UserRole, AuditLog
from app.services.cfo_dashboard import cfo_dashboard
from app.schemas.cfo_dashboard import (
    DSOTrendResponse, OverdueTrendResponse,
    CashFlowForecastResponse, TopOverdueCustomerListResponse,
    WriteOffCreateRequest, WriteOffApprovalRequest, WriteOffResponse,
    WriteOffListResponse, WriteOffReversalRequest, WriteOffSummary,
    ECLBatchResponse, ProvisioningDashboard,
)

router = APIRouter()

require_finance = RoleChecker(min_role=UserRole.FINANCE_MANAGER, allowed_roles=[UserRole.FINANCE_MANAGER])


# ═══════════════════════════════════════════
# ENHANCED AR DASHBOARD
# ═══════════════════════════════════════════

@router.get("/dso-trend", response_model=DSOTrendResponse)
async def get_dso_trend(
    months: int = Query(6, ge=1, le=24),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get monthly DSO trend for charts."""
    result = await cfo_dashboard.get_dso_trend(db, current_user.tenant_id, months)
    return DSOTrendResponse(**result)


@router.get("/overdue-trend", response_model=OverdueTrendResponse)
async def get_overdue_trend(
    months: int = Query(6, ge=1, le=24),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get monthly overdue amount trends."""
    result = await cfo_dashboard.get_overdue_trend(db, current_user.tenant_id, months)
    return OverdueTrendResponse(**result)


@router.get("/cash-flow-forecast", response_model=CashFlowForecastResponse)
async def get_cash_flow_forecast(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Predict cash inflows for next 30/60/90 days."""
    result = await cfo_dashboard.get_cash_flow_forecast(db, current_user.tenant_id)
    return CashFlowForecastResponse(**result)


@router.get("/top-overdue-customers", response_model=TopOverdueCustomerListResponse)
async def get_top_overdue_customers(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Top overdue customers with click-through details."""
    result = await cfo_dashboard.get_top_overdue_customers(db, current_user.tenant_id, limit)
    return TopOverdueCustomerListResponse(**result)


# ═══════════════════════════════════════════
# WRITE-OFF MANAGEMENT
# ═══════════════════════════════════════════

@router.post("/write-offs", response_model=WriteOffResponse, status_code=status.HTTP_201_CREATED)
async def create_write_off(
    request: WriteOffCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Request a write-off (requires manager approval)."""
    try:
        result = await cfo_dashboard.create_write_off(
            db, current_user.tenant_id, current_user.id, request.model_dump(),
        )

        audit = AuditLog(
            tenant_id=current_user.tenant_id, user_id=current_user.id,
            user_email=current_user.email, action="WRITE_OFF_REQUEST",
            entity_type="write_offs",
            after_state={"amount": float(request.amount), "type": request.write_off_type},
        )
        db.add(audit)
        await db.commit()

        return WriteOffResponse(**result)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/write-offs/{write_off_id}/decide", response_model=WriteOffResponse)
async def decide_write_off(
    write_off_id: UUID,
    request: WriteOffApprovalRequest,
    current_user: User = Depends(require_finance),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a write-off (finance_manager+)."""
    try:
        result = await cfo_dashboard.approve_write_off(
            db, current_user.tenant_id, current_user.id,
            write_off_id, request.action, request.approval_notes,
            request.approved_amount,
        )

        audit = AuditLog(
            tenant_id=current_user.tenant_id, user_id=current_user.id,
            user_email=current_user.email,
            action=f"WRITE_OFF_{request.action.upper()}",
            entity_type="write_offs", entity_id=write_off_id,
            after_state={"action": request.action},
        )
        db.add(audit)
        await db.commit()

        return WriteOffResponse(**result)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/write-offs/{write_off_id}/reverse", response_model=WriteOffResponse)
async def reverse_write_off(
    write_off_id: UUID,
    request: WriteOffReversalRequest,
    current_user: User = Depends(require_finance),
    db: AsyncSession = Depends(get_db),
):
    """Reverse a previously approved write-off."""
    try:
        result = await cfo_dashboard.reverse_write_off(
            db, current_user.tenant_id, current_user.id,
            write_off_id, request.reason,
        )

        audit = AuditLog(
            tenant_id=current_user.tenant_id, user_id=current_user.id,
            user_email=current_user.email, action="WRITE_OFF_REVERSAL",
            entity_type="write_offs", entity_id=write_off_id,
            after_state={"reason": request.reason},
        )
        db.add(audit)
        await db.commit()

        return WriteOffResponse(**result)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.get("/write-offs", response_model=WriteOffListResponse)
async def list_write_offs(
    wo_status: Optional[str] = Query(None, alias="status"),
    customer_id: Optional[UUID] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List write-offs with filtering and summary."""
    result = await cfo_dashboard.list_write_offs(
        db, current_user.tenant_id, wo_status, customer_id, page, page_size,
    )
    return WriteOffListResponse(**result)


# ═══════════════════════════════════════════
# IFRS 9 ECL PROVISIONING
# ═══════════════════════════════════════════

@router.post("/ecl/run", response_model=ECLBatchResponse)
async def run_ecl_provisioning(
    current_user: User = Depends(require_finance),
    db: AsyncSession = Depends(get_db),
):
    """Run IFRS 9 ECL provisioning engine across all customers."""
    result = await cfo_dashboard.run_ecl_provisioning(db, current_user.tenant_id)
    return ECLBatchResponse(**result)


@router.get("/ecl/dashboard", response_model=ProvisioningDashboard)
async def get_provisioning_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Provisioning dashboard with movement analysis and AI vs traditional comparison."""
    result = await cfo_dashboard.get_provisioning_dashboard(db, current_user.tenant_id)
    return ProvisioningDashboard(**result)
