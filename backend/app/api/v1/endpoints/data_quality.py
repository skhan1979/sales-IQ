"""
Sales IQ - Data Quality API Endpoints
Run scans, view reports, apply fixes, manage quarantine.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, RoleChecker
from app.models.core import User, UserRole, AuditLog
from app.models.business import (
    Customer, Invoice, Payment,
    DataQualityRecord, DataQualityStatus,
    AgentRunLog,
)
from app.agents.data_quality import data_quality_agent
from app.schemas.data_quality import (
    DQScanRequest,
    DQScanResponse,
    DQEntityResult,
    DQIssue,
    DQChange,
    DQDedupMatch,
    DQApplyFixRequest,
    DQBulkApplyRequest,
    DQQuarantineAction,
    DQRecordResponse,
    DQRecordListResponse,
    DQDashboard,
)

router = APIRouter()

# Finance manager+ can run scans; collectors can view reports
require_finance = RoleChecker(min_role=UserRole.FINANCE_MANAGER, allowed_roles=[UserRole.FINANCE_MANAGER])


# =============================================
# Run a DQ Scan
# =============================================

@router.post("/scan", response_model=DQScanResponse, status_code=status.HTTP_200_OK)
async def run_dq_scan(
    request: DQScanRequest,
    current_user: User = Depends(require_finance),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger a full data quality scan on the specified entity type.
    Runs the 5-stage pipeline: Validate → Deduplicate → Normalize → Anomaly Detect → Enrich.
    """
    # Run the agent pipeline
    result = await data_quality_agent.run(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        entity_type=request.entity_type,
        run_type="manual",
    )

    # Retrieve the agent context's detailed data from the pipeline run
    # The agent returns a summary; we augment it with entity-level details
    # by re-reading the context stored during the run
    response = DQScanResponse(
        run_id=result.get("run_id", ""),
        status=result.get("status", "completed"),
        batch_id=result.get("batch_id", ""),
        entity_type=result.get("entity_type", request.entity_type),
        records_processed=result.get("records_processed", 0),
        records_succeeded=result.get("records_succeeded", 0),
        records_failed=result.get("records_failed", 0),
        total_issues=result.get("total_issues", 0),
        quarantined_count=result.get("quarantined_count", 0),
        average_quality_score=result.get("average_quality_score", 100.0),
        stage_timings=result.get("stage_timings", {}),
        duration_ms=result.get("duration_ms", 0),
        error=result.get("error"),
    )

    # Audit
    audit = AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_email=current_user.email,
        action="DQ_SCAN",
        entity_type=request.entity_type,
        after_state={
            "run_id": response.run_id,
            "records_processed": response.records_processed,
            "total_issues": response.total_issues,
            "average_score": response.average_quality_score,
        },
    )
    db.add(audit)
    await db.commit()

    return response


# =============================================
# Run scan with full details (entity-level)
# =============================================

@router.post("/scan/detailed", response_model=DQScanResponse, status_code=status.HTTP_200_OK)
async def run_dq_scan_detailed(
    request: DQScanRequest,
    current_user: User = Depends(require_finance),
    db: AsyncSession = Depends(get_db),
):
    """
    Run a full DQ scan and return entity-level details (issues, changes, matches).
    Heavier response — use for investigation, not routine monitoring.
    """
    agent = data_quality_agent

    # We need access to the context after the run, so we run stages manually
    from app.agents.base import AgentContext
    ctx = AgentContext(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        entity_type=request.entity_type,
    )

    run_log = AgentRunLog(
        tenant_id=current_user.tenant_id,
        agent_name=agent.agent_name,
        run_type="manual_detailed",
        started_at=datetime.now(timezone.utc).isoformat(),
        status="running",
    )
    db.add(run_log)
    await db.flush()

    error_msg = None
    try:
        for stage in agent.stages:
            stage_start = datetime.now(timezone.utc)
            await stage.process(db, ctx)
            elapsed = (datetime.now(timezone.utc) - stage_start).total_seconds() * 1000
            ctx.stage_timings[stage.name] = round(elapsed, 1)
    except Exception as e:
        error_msg = str(e)

    run_log.completed_at = datetime.now(timezone.utc).isoformat()
    run_log.duration_ms = int(
        (datetime.now(timezone.utc) - ctx.started_at).total_seconds() * 1000
    )
    run_log.records_processed = ctx.records_processed
    run_log.records_succeeded = ctx.records_succeeded
    run_log.records_failed = ctx.records_failed
    run_log.status = "failed" if error_msg else "completed"
    run_log.error_message = error_msg
    run_log.result_summary = ctx.summary
    await db.commit()

    # Build entity-level detail
    entity_results = []
    for eid, er in ctx.entity_results.items():
        entity_results.append(DQEntityResult(
            entity_id=eid,
            quality_score=er["quality_score"],
            issues=[DQIssue(**{k: v for k, v in i.items()
                               if k in DQIssue.model_fields}) for i in er["issues"]],
            changes=[DQChange(**{k: v for k, v in c.items()
                                 if k in DQChange.model_fields}) for c in er["changes"]],
            is_quarantined=er["is_quarantined"],
        ))

    dedup_matches = [DQDedupMatch(**m) for m in ctx.dedup_matches]
    norm_changes = []
    for c in ctx.normalization_changes:
        norm_changes.append(DQChange(
            entity_id=c.get("entity_id", ""),
            stage="normalization",
            field=c.get("field", ""),
            old_value=c.get("old"),
            new_value=c.get("new"),
        ))

    return DQScanResponse(
        run_id=str(run_log.id),
        status=run_log.status,
        batch_id=str(ctx.batch_id),
        entity_type=request.entity_type,
        records_processed=ctx.records_processed,
        records_succeeded=ctx.records_succeeded,
        records_failed=ctx.records_failed,
        total_issues=ctx.summary["total_issues"],
        quarantined_count=ctx.summary["quarantined_count"],
        average_quality_score=ctx.summary["average_quality_score"],
        stage_timings=ctx.stage_timings,
        duration_ms=ctx.summary["duration_ms"],
        error=error_msg,
        entity_results=entity_results,
        dedup_matches=dedup_matches,
        normalization_changes=norm_changes,
        anomalies=ctx.anomalies_detected,
        enrichments=ctx.enrichments_applied,
    )


# =============================================
# Apply Fixes
# =============================================

ENTITY_MODEL_MAP = {
    "customers": Customer,
    "invoices": Invoice,
    "payments": Payment,
}


@router.post("/apply-fix", status_code=status.HTTP_200_OK)
async def apply_dq_fix(
    request: DQApplyFixRequest,
    current_user: User = Depends(require_finance),
    db: AsyncSession = Depends(get_db),
):
    """Apply a single normalization or enrichment fix to an entity."""
    model = ENTITY_MODEL_MAP.get(request.entity_type)
    if not model:
        raise HTTPException(400, f"Unknown entity type: {request.entity_type}")

    result = await db.execute(
        select(model).where(
            model.id == request.entity_id,
            model.tenant_id == current_user.tenant_id,
        )
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Entity not found")

    if not hasattr(entity, request.field):
        raise HTTPException(400, f"Field '{request.field}' does not exist on {request.entity_type}")

    old_value = getattr(entity, request.field)
    setattr(entity, request.field, request.new_value)

    audit = AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_email=current_user.email,
        action="DQ_FIX",
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        before_state={request.field: str(old_value) if old_value else None},
        after_state={request.field: request.new_value},
    )
    db.add(audit)
    await db.commit()

    return {
        "message": f"Fixed {request.entity_type}.{request.field}",
        "entity_id": str(request.entity_id),
        "field": request.field,
        "old_value": str(old_value) if old_value else None,
        "new_value": request.new_value,
    }


@router.post("/apply-fixes/bulk", status_code=status.HTTP_200_OK)
async def apply_dq_fixes_bulk(
    request: DQBulkApplyRequest,
    current_user: User = Depends(require_finance),
    db: AsyncSession = Depends(get_db),
):
    """Apply multiple normalization/enrichment fixes at once."""
    results = []

    for fix in request.fixes:
        model = ENTITY_MODEL_MAP.get(fix.entity_type)
        if not model:
            results.append({"entity_id": str(fix.entity_id), "status": "error", "message": f"Unknown type: {fix.entity_type}"})
            continue

        result = await db.execute(
            select(model).where(
                model.id == fix.entity_id,
                model.tenant_id == current_user.tenant_id,
            )
        )
        entity = result.scalar_one_or_none()
        if not entity:
            results.append({"entity_id": str(fix.entity_id), "status": "error", "message": "Not found"})
            continue

        if not hasattr(entity, fix.field):
            results.append({"entity_id": str(fix.entity_id), "status": "error", "message": f"Unknown field: {fix.field}"})
            continue

        old_value = getattr(entity, fix.field)
        setattr(entity, fix.field, fix.new_value)
        results.append({
            "entity_id": str(fix.entity_id), "status": "applied",
            "field": fix.field, "old": str(old_value) if old_value else None, "new": fix.new_value,
        })

    audit = AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_email=current_user.email,
        action="DQ_BULK_FIX",
        entity_type="mixed",
        after_state={"fixes_count": len(request.fixes), "applied": sum(1 for r in results if r["status"] == "applied")},
    )
    db.add(audit)
    await db.commit()

    return {
        "total": len(request.fixes),
        "applied": sum(1 for r in results if r["status"] == "applied"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "results": results,
    }


# =============================================
# Scan History
# =============================================

@router.get("/history", status_code=status.HTTP_200_OK)
async def get_scan_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    entity_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List previous DQ scan runs."""
    query = select(AgentRunLog).where(
        AgentRunLog.tenant_id == current_user.tenant_id,
        AgentRunLog.agent_name == "data_quality",
    )

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(AgentRunLog.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    runs = result.scalars().all()

    items = []
    for run in runs:
        items.append({
            "id": str(run.id),
            "run_type": run.run_type,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "duration_ms": run.duration_ms,
            "status": run.status,
            "records_processed": run.records_processed,
            "records_succeeded": run.records_succeeded,
            "records_failed": run.records_failed,
            "result_summary": run.result_summary,
            "error_message": run.error_message,
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


# =============================================
# DQ Dashboard Overview
# =============================================

@router.get("/overview", response_model=DQDashboard)
async def get_dq_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Data quality dashboard: overall health score, issue distribution,
    quarantine status, and recent scan results.
    """
    tid = current_user.tenant_id

    # Count entities
    cust_count = (await db.execute(
        select(func.count()).select_from(Customer).where(Customer.tenant_id == tid)
    )).scalar() or 0
    inv_count = (await db.execute(
        select(func.count()).select_from(Invoice).where(Invoice.tenant_id == tid)
    )).scalar() or 0
    pmt_count = (await db.execute(
        select(func.count()).select_from(Payment).where(Payment.tenant_id == tid)
    )).scalar() or 0
    total_entities = cust_count + inv_count + pmt_count

    # Get latest scan results
    latest_runs = await db.execute(
        select(AgentRunLog).where(
            AgentRunLog.tenant_id == tid,
            AgentRunLog.agent_name == "data_quality",
        ).order_by(AgentRunLog.created_at.desc()).limit(5)
    )
    recent_scans = []
    overall_scores = []
    all_issues_severity = defaultdict(int)
    all_issues_stage = defaultdict(int)
    top_issues = []

    for run in latest_runs.scalars().all():
        summary = run.result_summary or {}
        recent_scans.append({
            "run_id": str(run.id),
            "entity_type": summary.get("entity_type", "unknown"),
            "status": run.status,
            "records_processed": run.records_processed,
            "average_score": summary.get("average_quality_score", 100),
            "total_issues": summary.get("total_issues", 0),
            "started_at": run.started_at,
            "duration_ms": run.duration_ms,
        })
        if summary.get("average_quality_score") is not None:
            overall_scores.append(summary["average_quality_score"])

    overall_score = sum(overall_scores) / len(overall_scores) if overall_scores else 100.0

    # Placeholder counts based on latest scan data
    return DQDashboard(
        overall_score=round(overall_score, 1),
        total_entities=total_entities,
        clean_count=total_entities,  # Will be refined after DQ records are stored
        warning_count=0,
        quarantined_count=0,
        enriched_count=0,
        issues_by_severity=dict(all_issues_severity),
        issues_by_stage=dict(all_issues_stage),
        top_issues=[],
        recent_scans=recent_scans,
    )
