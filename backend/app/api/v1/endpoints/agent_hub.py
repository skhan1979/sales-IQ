"""
Sales IQ - Agent Hub Endpoints
Unified dashboard, agent details, run history, and execution controls.
"""

from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, RoleChecker
from app.models.core import User, UserRole, AuditLog
from app.services.agent_registry import agent_registry, AGENT_REGISTRY
from app.schemas.agent_hub import (
    AgentInfo, AgentHubDashboard, AgentHealthMetric,
    AgentRunLogResponse, AgentRunLogListResponse,
    AgentTriggerRequest, AgentTriggerResponse,
    AgentConfigUpdate,
)

router = APIRouter()


@router.get("/dashboard", response_model=AgentHubDashboard)
async def get_agent_hub_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the Agent Hub overview dashboard with health metrics for all agents."""
    dashboard = await agent_registry.get_dashboard(db, current_user.tenant_id)
    return AgentHubDashboard(**dashboard)


@router.get("/agents", response_model=list[AgentInfo])
async def list_agents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all registered agents with their status and metrics."""
    agents = await agent_registry.get_all_agents(db, current_user.tenant_id)
    return [AgentInfo(**a) for a in agents]


@router.get("/agents/{agent_name}", response_model=AgentInfo)
async def get_agent_detail(
    agent_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed info for a specific agent."""
    agent = await agent_registry.get_agent(db, current_user.tenant_id, agent_name)
    if not agent:
        raise HTTPException(404, f"Agent '{agent_name}' not found")
    return AgentInfo(**agent)


@router.get("/runs", response_model=AgentRunLogListResponse)
async def get_run_history(
    agent_name: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated agent run history with optional filtering."""
    result = await agent_registry.get_run_history(
        db, current_user.tenant_id,
        agent_name=agent_name,
        status=status_filter,
        page=page, page_size=page_size,
    )
    return AgentRunLogListResponse(
        items=[AgentRunLogResponse.model_validate(log) for log in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/runs/{run_id}", response_model=AgentRunLogResponse)
async def get_run_detail(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed info for a specific agent run."""
    from sqlalchemy import select
    from app.models.business import AgentRunLog

    result = await db.execute(
        select(AgentRunLog).where(
            AgentRunLog.id == run_id,
            AgentRunLog.tenant_id == current_user.tenant_id,
        )
    )
    run_log = result.scalar_one_or_none()
    if not run_log:
        raise HTTPException(404, "Run not found")
    return AgentRunLogResponse.model_validate(run_log)


@router.post("/agents/{agent_name}/trigger", response_model=AgentTriggerResponse)
async def trigger_agent(
    agent_name: str,
    request: AgentTriggerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger an agent run."""
    if agent_name not in AGENT_REGISTRY:
        raise HTTPException(404, f"Agent '{agent_name}' not found")

    # Check agent is not paused/disabled
    agent_info = await agent_registry.get_agent(db, current_user.tenant_id, agent_name)
    if agent_info["status"] in ("paused", "disabled"):
        raise HTTPException(400, f"Agent '{agent_name}' is {agent_info['status']}. Enable it first.")

    # Execute the agent
    result = {}
    try:
        if agent_name == "data_quality":
            from app.agents.data_quality import data_quality_agent
            result = await data_quality_agent.run(
                db=db,
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                entity_type=request.entity_type or "customers",
                run_type="manual",
            )
            response = AgentTriggerResponse(
                run_id=result.get("run_id", ""),
                agent_name=agent_name,
                status=result.get("status", "completed"),
                message=f"Data quality scan completed. Processed {result.get('records_processed', 0)} records.",
                result=result,
            )

        elif agent_name == "briefing_agent":
            from app.agents.briefing import BriefingAgent
            agent = BriefingAgent()
            params = request.run_params or {}
            briefing = await agent.generate_briefing(
                db=db,
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                recipient_id=current_user.id,
                briefing_type=params.get("briefing_type", "daily_flash"),
                delivery=params.get("delivery", "in_app"),
            )
            response = AgentTriggerResponse(
                run_id=str(briefing.id),
                agent_name=agent_name,
                status="completed",
                message=f"Briefing generated: {briefing.title}",
                result={"briefing_id": str(briefing.id), "title": briefing.title},
            )

        elif agent_name == "prediction_agent":
            from app.agents.prediction import prediction_agent
            result = await prediction_agent.run(
                db=db,
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                entity_type=request.entity_type or "customers",
                run_type="manual",
            )
            response = AgentTriggerResponse(
                run_id=result.get("run_id", str(uuid4())),
                agent_name=agent_name,
                status=result.get("status", "completed"),
                message=f"Prediction agent completed. Scored {result.get('records_processed', 0)} customers for risk, churn, and DSO. {result.get('total_predictions', 0)} invoice payment dates predicted.",
                result=result,
            )

        elif agent_name == "collections_agent":
            from app.agents.collections import collections_agent
            result = await collections_agent.run(
                db=db,
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                entity_type=request.entity_type or "invoices",
                run_type="manual",
            )
            response = AgentTriggerResponse(
                run_id=result.get("run_id", str(uuid4())),
                agent_name=agent_name,
                status=result.get("status", "completed"),
                message=(
                    f"Collections agent completed. "
                    f"Prioritized {result.get('total_overdue_customers', 0)} overdue accounts, "
                    f"found {result.get('escalation_count', 0)} needing escalation, "
                    f"drafted {result.get('drafts_generated', 0)} collection messages."
                ),
                result=result,
            )

        elif agent_name == "matching_agent":
            from app.agents.matching import matching_agent
            result = await matching_agent.run(
                db=db,
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                entity_type=request.entity_type or "payments",
                run_type="manual",
            )
            response = AgentTriggerResponse(
                run_id=result.get("run_id", str(uuid4())),
                agent_name=agent_name,
                status=result.get("status", "completed"),
                message=(
                    f"Matching agent completed. Processed {result.get('records_processed', 0)} unmatched payments. "
                    f"Auto-matched {result.get('auto_matched', 0)} "
                    f"({result.get('matched_amount', 0):,.2f} total). "
                    f"{result.get('exceptions_count', 0)} sent to exception queue for review."
                ),
                result=result,
            )

        elif agent_name == "ocr_agent":
            from app.agents.ocr import ocr_agent
            result = await ocr_agent.run(
                db=db,
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                entity_type=request.entity_type or "invoices",
                run_type="manual",
            )
            no_docs = result.get("no_documents", False)
            if no_docs:
                msg = "OCR agent ready. No pending documents to process. Upload invoice PDFs or images to extract data automatically."
            else:
                msg = (
                    f"OCR agent completed. Processed {result.get('documents_queued', 0)} documents, "
                    f"extracted text from {result.get('texts_extracted', 0)}, "
                    f"mapped fields in {result.get('fields_mapped', 0)}. "
                    f"Engine: {result.get('ocr_engine', 'pdf_text_only')}."
                )
            response = AgentTriggerResponse(
                run_id=result.get("run_id", str(uuid4())),
                agent_name=agent_name,
                status=result.get("status", "completed"),
                message=msg,
                result=result,
            )

        elif agent_name == "chat_agent":
            response = AgentTriggerResponse(
                run_id=str(uuid4()),
                agent_name=agent_name,
                status="completed",
                message="Chat agent is active. Use the AI Chat page to interact with your data.",
                result={"status": "active"},
            )

        else:
            raise HTTPException(400, f"Agent '{agent_name}' does not support manual triggering")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Agent execution failed: {str(e)}")

    # Audit log (outside try/except so it doesn't mask errors)
    try:
        audit = AuditLog(
            tenant_id=current_user.tenant_id, user_id=current_user.id,
            user_email=current_user.email,
            action="AGENT_TRIGGER",
            entity_type="agent_hub",
            after_state={"agent": agent_name, "entity_type": request.entity_type},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        pass  # Don't let audit failure mask the agent result

    return response


@router.patch("/agents/{agent_name}/config", response_model=AgentInfo)
async def update_agent_config(
    agent_name: str,
    request: AgentConfigUpdate,
    current_user: User = Depends(RoleChecker([UserRole.FINANCE_MANAGER], min_role=UserRole.FINANCE_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Update agent configuration (finance_manager+)."""
    updated = agent_registry.update_agent_config(agent_name, request.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(404, f"Agent '{agent_name}' not found")

    # Audit
    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email,
        action="AGENT_CONFIG_UPDATE",
        entity_type="agent_hub",
        after_state={"agent": agent_name, "updates": request.model_dump(exclude_unset=True)},
    )
    db.add(audit)
    await db.commit()

    # Return refreshed agent info
    agent = await agent_registry.get_agent(db, current_user.tenant_id, agent_name)
    return AgentInfo(**agent)


@router.post("/agents/{agent_name}/pause", response_model=AgentInfo)
async def pause_agent(
    agent_name: str,
    current_user: User = Depends(RoleChecker([UserRole.FINANCE_MANAGER], min_role=UserRole.FINANCE_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Pause an agent (stops scheduled runs)."""
    updated = agent_registry.update_agent_config(agent_name, {"status": "paused"})
    if not updated:
        raise HTTPException(404, f"Agent '{agent_name}' not found")

    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email,
        action="AGENT_PAUSE", entity_type="agent_hub",
        after_state={"agent": agent_name},
    )
    db.add(audit)
    await db.commit()

    agent = await agent_registry.get_agent(db, current_user.tenant_id, agent_name)
    return AgentInfo(**agent)


@router.post("/agents/{agent_name}/resume", response_model=AgentInfo)
async def resume_agent(
    agent_name: str,
    current_user: User = Depends(RoleChecker([UserRole.FINANCE_MANAGER], min_role=UserRole.FINANCE_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Resume a paused agent."""
    current = await agent_registry.get_agent(db, current_user.tenant_id, agent_name)
    if not current:
        raise HTTPException(404, f"Agent '{agent_name}' not found")
    if current["status"] != "paused":
        raise HTTPException(400, f"Agent is not paused (current: {current['status']})")

    agent_registry.update_agent_config(agent_name, {"status": "active"})

    audit = AuditLog(
        tenant_id=current_user.tenant_id, user_id=current_user.id,
        user_email=current_user.email,
        action="AGENT_RESUME", entity_type="agent_hub",
        after_state={"agent": agent_name},
    )
    db.add(audit)
    await db.commit()

    agent = await agent_registry.get_agent(db, current_user.tenant_id, agent_name)
    return AgentInfo(**agent)
