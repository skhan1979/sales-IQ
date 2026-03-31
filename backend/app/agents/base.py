"""
Sales IQ - Base Agent Infrastructure
Abstract base class for all AI agents and pipeline orchestrator.
"""

import asyncio
import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import AgentRunLog


class AgentContext:
    """
    Shared context passed through all pipeline stages.
    Collects results, issues, and metrics as data flows through.
    """

    def __init__(
        self,
        tenant_id: UUID,
        user_id: UUID,
        entity_type: str,
        batch_id: Optional[UUID] = None,
    ):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.entity_type = entity_type
        self.batch_id = batch_id or uuid4()
        self.started_at = datetime.now(timezone.utc)

        # Accumulate results from each stage
        self.records_processed: int = 0
        self.records_succeeded: int = 0
        self.records_failed: int = 0

        # Per-entity results keyed by entity_id
        self.entity_results: Dict[str, Dict[str, Any]] = {}

        # Aggregate issues across all stages
        self.validation_issues: List[Dict] = []
        self.dedup_matches: List[Dict] = []
        self.normalization_changes: List[Dict] = []
        self.anomalies_detected: List[Dict] = []
        self.enrichments_applied: List[Dict] = []

        # Stage timing
        self.stage_timings: Dict[str, float] = {}

        # Extra data for agent-specific use (e.g., briefing snapshots)
        self.extra: Dict[str, Any] = {}

    def get_entity_result(self, entity_id: str) -> Dict[str, Any]:
        if entity_id not in self.entity_results:
            self.entity_results[entity_id] = {
                "quality_score": 100.0,
                "issues": [],
                "changes": [],
                "is_quarantined": False,
            }
        return self.entity_results[entity_id]

    def add_issue(self, entity_id: str, stage: str, severity: str, field: str, message: str, **extra):
        issue = {
            "entity_id": entity_id,
            "stage": stage,
            "severity": severity,  # critical, warning, info
            "field": field,
            "message": message,
            **extra,
        }
        self.get_entity_result(entity_id)["issues"].append(issue)

        # Deduct from quality score based on severity
        result = self.entity_results[entity_id]
        deduction = {"critical": 25, "warning": 10, "info": 2}.get(severity, 5)
        result["quality_score"] = max(0, result["quality_score"] - deduction)

        # Auto-quarantine on critical issues
        if severity == "critical":
            result["is_quarantined"] = True

        return issue

    def add_change(self, entity_id: str, stage: str, field: str, old_value: Any, new_value: Any, **extra):
        change = {
            "entity_id": entity_id,
            "stage": stage,
            "field": field,
            "old_value": str(old_value) if old_value is not None else None,
            "new_value": str(new_value) if new_value is not None else None,
            **extra,
        }
        self.get_entity_result(entity_id)["changes"].append(change)
        return change

    @property
    def summary(self) -> Dict[str, Any]:
        total_issues = sum(len(r["issues"]) for r in self.entity_results.values())
        quarantined = sum(1 for r in self.entity_results.values() if r["is_quarantined"])
        avg_score = (
            sum(r["quality_score"] for r in self.entity_results.values()) / len(self.entity_results)
            if self.entity_results
            else 100.0
        )
        return {
            "batch_id": str(self.batch_id),
            "entity_type": self.entity_type,
            "records_processed": self.records_processed,
            "records_succeeded": self.records_succeeded,
            "records_failed": self.records_failed,
            "total_issues": total_issues,
            "quarantined_count": quarantined,
            "average_quality_score": round(avg_score, 1),
            "stage_timings": self.stage_timings,
            "duration_ms": int(
                (datetime.now(timezone.utc) - self.started_at).total_seconds() * 1000
            ),
        }


class PipelineStage(ABC):
    """Abstract base for a single stage in the DQ pipeline."""

    name: str = "base"

    @abstractmethod
    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        """Run this stage against all entities in the current batch."""
        ...


class BaseAgent(ABC):
    """
    Abstract agent that orchestrates a sequence of pipeline stages.
    Handles logging, error capture, and run tracking.
    """

    agent_name: str = "base_agent"
    stages: List[PipelineStage] = []

    async def run(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        entity_type: str,
        run_type: str = "manual",
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute all stages sequentially and record the run."""

        ctx = AgentContext(
            tenant_id=tenant_id,
            user_id=user_id,
            entity_type=entity_type,
        )

        # Create run log entry
        run_log = AgentRunLog(
            tenant_id=tenant_id,
            agent_name=self.agent_name,
            run_type=run_type,
            started_at=datetime.now(timezone.utc).isoformat(),
            status="running",
        )
        db.add(run_log)
        await db.flush()

        error_msg = None
        error_tb = None

        try:
            # Run each stage
            for stage in self.stages:
                stage_start = datetime.now(timezone.utc)
                try:
                    await stage.process(db, ctx)
                except Exception as e:
                    error_msg = f"Stage '{stage.name}' failed: {str(e)}"
                    error_tb = traceback.format_exc()
                    break
                finally:
                    elapsed = (datetime.now(timezone.utc) - stage_start).total_seconds() * 1000
                    ctx.stage_timings[stage.name] = round(elapsed, 1)

        except Exception as e:
            error_msg = str(e)
            error_tb = traceback.format_exc()

        # Finalize run log
        run_log.completed_at = datetime.now(timezone.utc).isoformat()
        run_log.duration_ms = int(
            (datetime.now(timezone.utc) - ctx.started_at).total_seconds() * 1000
        )
        run_log.records_processed = ctx.records_processed
        run_log.records_succeeded = ctx.records_succeeded
        run_log.records_failed = ctx.records_failed
        run_log.status = "failed" if error_msg else "completed"
        run_log.error_message = error_msg
        run_log.error_traceback = error_tb
        run_log.result_summary = ctx.summary

        await db.commit()

        result = ctx.summary
        result["run_id"] = str(run_log.id)
        result["status"] = run_log.status
        if error_msg:
            result["error"] = error_msg

        return result
