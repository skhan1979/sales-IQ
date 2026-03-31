"""
Sales IQ - Agent Registry
Central registry for all AI agents with health monitoring,
run history aggregation, and execution controls.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import AgentRunLog


# ── Agent definitions ──

AGENT_REGISTRY = {
    "data_quality": {
        "display_name": "Data Quality Agent",
        "description": "5-stage pipeline for validating, deduplicating, normalizing, detecting anomalies, and enriching business entity data.",
        "category": "data_quality",
        "version": "1.0",
        "stages": [
            {"name": "validation", "description": "Checks completeness, format, and business rules"},
            {"name": "deduplication", "description": "Trigram-based fuzzy matching for duplicate detection"},
            {"name": "normalization", "description": "Standardizes phone numbers, names, and country codes"},
            {"name": "anomaly_detection", "description": "Z-score analysis for statistical outlier flagging"},
            {"name": "enrichment", "description": "Territory inference and segment classification"},
        ],
        "supported_entities": ["customers"],
        "default_config": {
            "dedup_threshold": 0.65,
            "anomaly_z_threshold": 2.5,
            "auto_apply_normalizations": False,
        },
    },
    "briefing_agent": {
        "display_name": "Briefing Agent",
        "description": "Generates AI-powered intelligence briefings with executive summaries, risk alerts, AR analysis, and collection priorities.",
        "category": "intelligence",
        "version": "1.0",
        "stages": [
            {"name": "data_collection", "description": "Gathers metrics from all business entities"},
            {"name": "insight_analysis", "description": "Detects patterns, trends, and anomalies"},
            {"name": "section_composer", "description": "Builds structured markdown briefing sections"},
            {"name": "html_renderer", "description": "Produces email-ready HTML output"},
        ],
        "supported_entities": ["briefing"],
        "default_config": {
            "default_type": "daily_flash",
            "default_delivery": "in_app",
            "analysis_window_days": 30,
        },
    },
    "prediction_agent": {
        "display_name": "Prediction Agent",
        "description": "ML-powered prediction engine for payment dates, churn probability, credit risk scoring, and DSO forecasting.",
        "category": "intelligence",
        "version": "1.0",
        "stages": [
            {"name": "feature_extraction", "description": "Builds feature vectors from customer and invoice data"},
            {"name": "model_inference", "description": "Runs XGBoost/regression models for predictions"},
            {"name": "score_update", "description": "Writes predicted values back to customer and invoice records"},
        ],
        "supported_entities": ["customers", "invoices"],
        "default_config": {
            "prediction_horizon_days": 90,
            "min_invoice_history": 3,
            "retrain_interval_days": 7,
        },
    },
    "collections_agent": {
        "display_name": "Collections Agent",
        "description": "Automated collections workflow engine handling prioritization, escalation, PTP tracking, and AI message generation.",
        "category": "collections",
        "version": "1.0",
        "stages": [
            {"name": "prioritize", "description": "Rank overdue accounts by urgency and amount"},
            {"name": "escalation_check", "description": "Evaluate escalation triggers and advance steps"},
            {"name": "message_draft", "description": "Generate collection messages per tone and channel"},
            {"name": "ptp_monitor", "description": "Track promise-to-pay commitments and flag broken ones"},
        ],
        "supported_entities": ["invoices", "customers"],
        "default_config": {
            "auto_escalate": True,
            "escalation_days": [7, 14, 30, 60],
            "default_tone": "friendly",
        },
    },
    "matching_agent": {
        "display_name": "Matching Agent",
        "description": "Intelligent payment-to-invoice matching using fuzzy logic, reference parsing, and confidence scoring.",
        "category": "finance",
        "version": "1.0",
        "stages": [
            {"name": "candidate_selection", "description": "Identify potential invoice matches for each payment"},
            {"name": "confidence_scoring", "description": "Score matches by amount, reference, date proximity"},
            {"name": "auto_match", "description": "Apply matches above confidence threshold"},
            {"name": "exception_queue", "description": "Flag ambiguous matches for manual review"},
        ],
        "supported_entities": ["payments", "invoices"],
        "default_config": {
            "auto_match_threshold": 0.85,
            "amount_tolerance_pct": 2.0,
            "date_window_days": 30,
        },
    },
    "ocr_agent": {
        "display_name": "OCR Agent",
        "description": "Document intelligence agent for extracting structured data from invoices, receipts, and credit notes via OCR.",
        "category": "data_quality",
        "version": "1.0",
        "stages": [
            {"name": "document_intake", "description": "Accept and classify uploaded documents"},
            {"name": "text_extraction", "description": "OCR processing with layout analysis"},
            {"name": "field_mapping", "description": "Map extracted text to invoice/payment fields"},
            {"name": "validation", "description": "Cross-check extracted values against business rules"},
        ],
        "supported_entities": ["documents"],
        "default_config": {
            "ocr_engine": "azure_di",
            "confidence_threshold": 0.80,
            "auto_create_invoice": False,
        },
    },
    "chat_agent": {
        "display_name": "Chat Agent",
        "description": "Natural language query engine for conversational access to AR data, risk insights, customer health, and collections status.",
        "category": "intelligence",
        "version": "1.0",
        "stages": [
            {"name": "intent_detection", "description": "Parse user message to identify query domain"},
            {"name": "data_retrieval", "description": "Fetch relevant data from services and DB"},
            {"name": "response_generation", "description": "Format data into natural language response"},
        ],
        "supported_entities": ["chat"],
        "default_config": {
            "max_results": 10,
            "conversation_memory": True,
            "supported_domains": ["ar", "risk", "credit", "health", "disputes", "collections"],
        },
    },
}

# In-memory agent state (production would persist to DB)
_agent_state: Dict[str, Dict[str, Any]] = {}


def _get_agent_state(agent_name: str) -> dict:
    if agent_name not in _agent_state:
        _agent_state[agent_name] = {
            "status": "active",
            "schedule_cron": None,
            "schedule_timezone": "Asia/Dubai",
            "config": AGENT_REGISTRY.get(agent_name, {}).get("default_config", {}),
        }
    return _agent_state[agent_name]


class AgentRegistry:
    """Central registry and health monitor for all AI agents."""

    async def get_all_agents(self, db: AsyncSession, tenant_id: UUID) -> List[dict]:
        """Get info for all registered agents with live metrics."""
        agents = []
        for name, defn in AGENT_REGISTRY.items():
            info = await self._build_agent_info(db, tenant_id, name, defn)
            agents.append(info)
        return agents

    async def get_agent(self, db: AsyncSession, tenant_id: UUID, agent_name: str) -> Optional[dict]:
        """Get detailed info for a single agent."""
        defn = AGENT_REGISTRY.get(agent_name)
        if not defn:
            return None
        return await self._build_agent_info(db, tenant_id, agent_name, defn)

    async def _build_agent_info(self, db: AsyncSession, tenant_id: UUID, name: str, defn: dict) -> dict:
        state = _get_agent_state(name)
        metrics = await self._get_agent_metrics(db, tenant_id, name)

        # Calculate health score
        health = 100.0
        if metrics["total_runs"] > 0:
            health = min(100, metrics["success_rate"] * 1.0)
            # Penalize for recent errors
            if metrics["errors_24h"] > 0:
                health = max(0, health - (metrics["errors_24h"] * 10))
            # Penalize for slow runs (>5s avg)
            if metrics["avg_duration_ms"] > 5000:
                health = max(0, health - 5)

        return {
            "agent_name": name,
            "display_name": defn["display_name"],
            "description": defn["description"],
            "category": defn["category"],
            "version": defn["version"],
            "stages": defn["stages"],
            "status": state["status"],
            "is_scheduled": state["schedule_cron"] is not None,
            "schedule_cron": state["schedule_cron"],
            "schedule_timezone": state["schedule_timezone"],
            "last_run_at": metrics.get("last_run_at"),
            "last_run_status": metrics.get("last_run_status"),
            "last_run_duration_ms": metrics.get("last_run_duration_ms"),
            "total_runs": metrics["total_runs"],
            "success_rate": metrics["success_rate"],
            "avg_duration_ms": metrics["avg_duration_ms"],
            "health_score": round(health, 1),
            "config": state["config"],
        }

    async def _get_agent_metrics(self, db: AsyncSession, tenant_id: UUID, agent_name: str) -> dict:
        """Compute agent metrics from AgentRunLog."""
        now = datetime.now(timezone.utc)
        day_ago = (now - timedelta(hours=24)).isoformat()
        week_ago = (now - timedelta(days=7)).isoformat()

        # Total runs
        total = (await db.execute(
            select(func.count()).select_from(AgentRunLog).where(
                AgentRunLog.tenant_id == tenant_id,
                AgentRunLog.agent_name == agent_name,
            )
        )).scalar() or 0

        # Successful runs
        completed = (await db.execute(
            select(func.count()).select_from(AgentRunLog).where(
                AgentRunLog.tenant_id == tenant_id,
                AgentRunLog.agent_name == agent_name,
                AgentRunLog.status == "completed",
            )
        )).scalar() or 0

        # Average duration
        avg_dur = (await db.execute(
            select(func.avg(AgentRunLog.duration_ms)).where(
                AgentRunLog.tenant_id == tenant_id,
                AgentRunLog.agent_name == agent_name,
                AgentRunLog.duration_ms.isnot(None),
            )
        )).scalar() or 0

        # Last run
        last_run_q = await db.execute(
            select(AgentRunLog).where(
                AgentRunLog.tenant_id == tenant_id,
                AgentRunLog.agent_name == agent_name,
            ).order_by(AgentRunLog.created_at.desc()).limit(1)
        )
        last_run = last_run_q.scalar_one_or_none()

        # 24h metrics
        runs_24h = (await db.execute(
            select(func.count()).select_from(AgentRunLog).where(
                AgentRunLog.tenant_id == tenant_id,
                AgentRunLog.agent_name == agent_name,
                AgentRunLog.started_at >= day_ago,
            )
        )).scalar() or 0

        errors_24h = (await db.execute(
            select(func.count()).select_from(AgentRunLog).where(
                AgentRunLog.tenant_id == tenant_id,
                AgentRunLog.agent_name == agent_name,
                AgentRunLog.started_at >= day_ago,
                AgentRunLog.status == "failed",
            )
        )).scalar() or 0

        # Records processed in 24h
        records_24h = (await db.execute(
            select(func.coalesce(func.sum(AgentRunLog.records_processed), 0)).where(
                AgentRunLog.tenant_id == tenant_id,
                AgentRunLog.agent_name == agent_name,
                AgentRunLog.started_at >= day_ago,
            )
        )).scalar() or 0

        return {
            "total_runs": total,
            "success_rate": round(completed / total * 100, 1) if total > 0 else 0,
            "avg_duration_ms": round(float(avg_dur), 1),
            "last_run_at": last_run.started_at if last_run else None,
            "last_run_status": last_run.status if last_run else None,
            "last_run_duration_ms": last_run.duration_ms if last_run else None,
            "runs_24h": runs_24h,
            "errors_24h": errors_24h,
            "records_24h": records_24h,
        }

    async def get_dashboard(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """Build the Agent Hub overview dashboard."""
        now = datetime.now(timezone.utc)
        day_ago = (now - timedelta(hours=24)).isoformat()
        week_ago = (now - timedelta(days=7)).isoformat()

        agents = await self.get_all_agents(db, tenant_id)

        # Aggregate 24h/7d metrics
        total_24h = (await db.execute(
            select(func.count()).select_from(AgentRunLog).where(
                AgentRunLog.tenant_id == tenant_id,
                AgentRunLog.started_at >= day_ago,
            )
        )).scalar() or 0

        total_7d = (await db.execute(
            select(func.count()).select_from(AgentRunLog).where(
                AgentRunLog.tenant_id == tenant_id,
                AgentRunLog.started_at >= week_ago,
            )
        )).scalar() or 0

        completed_24h = (await db.execute(
            select(func.count()).select_from(AgentRunLog).where(
                AgentRunLog.tenant_id == tenant_id,
                AgentRunLog.started_at >= day_ago,
                AgentRunLog.status == "completed",
            )
        )).scalar() or 0

        records_24h = (await db.execute(
            select(func.coalesce(func.sum(AgentRunLog.records_processed), 0)).where(
                AgentRunLog.tenant_id == tenant_id,
                AgentRunLog.started_at >= day_ago,
            )
        )).scalar() or 0

        # Recent errors (last 10)
        error_q = await db.execute(
            select(AgentRunLog).where(
                AgentRunLog.tenant_id == tenant_id,
                AgentRunLog.status == "failed",
            ).order_by(AgentRunLog.created_at.desc()).limit(10)
        )
        recent_errors = []
        for err in error_q.scalars().all():
            recent_errors.append({
                "agent_name": err.agent_name,
                "run_id": str(err.id),
                "started_at": err.started_at,
                "error": (err.error_message or "")[:200],
            })

        # Performance trend (last 7 days, per day)
        trend = []
        for days_back in range(6, -1, -1):
            day_start = (now - timedelta(days=days_back)).replace(hour=0, minute=0, second=0).isoformat()
            day_end = (now - timedelta(days=days_back)).replace(hour=23, minute=59, second=59).isoformat()

            day_total = (await db.execute(
                select(func.count()).select_from(AgentRunLog).where(
                    AgentRunLog.tenant_id == tenant_id,
                    AgentRunLog.started_at >= day_start,
                    AgentRunLog.started_at <= day_end,
                )
            )).scalar() or 0

            day_ok = (await db.execute(
                select(func.count()).select_from(AgentRunLog).where(
                    AgentRunLog.tenant_id == tenant_id,
                    AgentRunLog.started_at >= day_start,
                    AgentRunLog.started_at <= day_end,
                    AgentRunLog.status == "completed",
                )
            )).scalar() or 0

            trend.append({
                "date": (now - timedelta(days=days_back)).strftime("%Y-%m-%d"),
                "total_runs": day_total,
                "successful": day_ok,
                "failed": day_total - day_ok,
            })

        # Build agent health metrics
        agent_health = []
        for a in agents:
            metrics = await self._get_agent_metrics(db, tenant_id, a["agent_name"])
            agent_health.append({
                "agent_name": a["agent_name"],
                "display_name": a["display_name"],
                "status": a["status"],
                "health_score": a["health_score"],
                "last_run": metrics.get("last_run_at"),
                "runs_24h": metrics["runs_24h"],
                "success_rate_24h": round(
                    (metrics["runs_24h"] - metrics["errors_24h"]) / metrics["runs_24h"] * 100, 1
                ) if metrics["runs_24h"] > 0 else 100.0,
                "avg_duration_ms": metrics["avg_duration_ms"],
                "errors_24h": metrics["errors_24h"],
            })

        return {
            "total_agents": len(agents),
            "active_agents": sum(1 for a in agents if a["status"] == "active"),
            "total_runs_24h": total_24h,
            "total_runs_7d": total_7d,
            "overall_success_rate": round(completed_24h / total_24h * 100, 1) if total_24h > 0 else 100.0,
            "total_records_processed_24h": records_24h,
            "agents": agent_health,
            "recent_errors": recent_errors,
            "performance_trend": trend,
        }

    async def get_run_history(
        self, db: AsyncSession, tenant_id: UUID,
        agent_name: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1, page_size: int = 20,
    ) -> dict:
        """Get paginated run history with optional filtering."""
        query = select(AgentRunLog).where(AgentRunLog.tenant_id == tenant_id)

        if agent_name:
            query = query.where(AgentRunLog.agent_name == agent_name)
        if status:
            query = query.where(AgentRunLog.status == status)

        count_q = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_q)).scalar() or 0

        query = query.order_by(AgentRunLog.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        logs = result.scalars().all()

        return {
            "items": logs,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def update_agent_config(self, agent_name: str, updates: dict) -> Optional[dict]:
        """Update agent state/config."""
        if agent_name not in AGENT_REGISTRY:
            return None

        state = _get_agent_state(agent_name)
        if "status" in updates and updates["status"] is not None:
            state["status"] = updates["status"]
        if "schedule_cron" in updates and updates["schedule_cron"] is not None:
            state["schedule_cron"] = updates["schedule_cron"]
        if "schedule_timezone" in updates and updates["schedule_timezone"] is not None:
            state["schedule_timezone"] = updates["schedule_timezone"]
        if "config" in updates and updates["config"] is not None:
            state["config"].update(updates["config"])

        return state


# Singleton
agent_registry = AgentRegistry()
