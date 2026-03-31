"""
Sales IQ - Agent Hub Schemas
Pydantic models for the Agent Hub dashboard, registry, and controls.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Agent definition ──

class AgentStageInfo(BaseModel):
    """Info about a single pipeline stage."""
    name: str
    description: str
    avg_duration_ms: Optional[float] = None


class AgentInfo(BaseModel):
    """Full info about a registered agent."""
    agent_name: str
    display_name: str
    description: str
    category: str = Field(..., description="data_quality, intelligence, automation")
    version: str = "1.0"
    stages: List[AgentStageInfo]
    status: str = Field("active", description="active, paused, error, disabled")
    is_scheduled: bool = False
    schedule_cron: Optional[str] = None
    schedule_timezone: Optional[str] = None
    last_run_at: Optional[str] = None
    last_run_status: Optional[str] = None
    last_run_duration_ms: Optional[int] = None
    total_runs: int = 0
    success_rate: float = 0.0
    avg_duration_ms: float = 0.0
    health_score: float = 100.0
    config: Optional[Dict[str, Any]] = None


class AgentRunLogResponse(BaseModel):
    """Response for a single agent run log entry."""
    id: UUID
    agent_name: str
    run_type: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    status: str
    records_processed: int = 0
    records_succeeded: int = 0
    records_failed: int = 0
    error_message: Optional[str] = None
    result_summary: Optional[Dict[str, Any]] = None
    run_metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AgentRunLogListResponse(BaseModel):
    items: List[AgentRunLogResponse]
    total: int
    page: int
    page_size: int


# ── Agent Hub dashboard ──

class AgentHealthMetric(BaseModel):
    """Health metric for a single agent."""
    agent_name: str
    display_name: str
    status: str
    health_score: float
    last_run: Optional[str] = None
    runs_24h: int = 0
    success_rate_24h: float = 0.0
    avg_duration_ms: float = 0.0
    errors_24h: int = 0


class AgentHubDashboard(BaseModel):
    """Overview dashboard for all agents."""
    total_agents: int
    active_agents: int
    total_runs_24h: int
    total_runs_7d: int
    overall_success_rate: float
    total_records_processed_24h: int
    agents: List[AgentHealthMetric]
    recent_errors: List[Dict[str, Any]]
    performance_trend: List[Dict[str, Any]]


# ── Agent controls ──

class AgentTriggerRequest(BaseModel):
    """Request to manually trigger an agent run."""
    entity_type: Optional[str] = Field("customers", description="Target entity type")
    run_params: Optional[Dict[str, Any]] = Field(None, description="Extra parameters for the run")


class AgentConfigUpdate(BaseModel):
    """Update agent configuration."""
    status: Optional[str] = Field(None, description="active, paused, disabled")
    schedule_cron: Optional[str] = None
    schedule_timezone: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class AgentTriggerResponse(BaseModel):
    """Response after triggering an agent."""
    run_id: str
    agent_name: str
    status: str
    message: str
    result: Optional[Dict[str, Any]] = None
