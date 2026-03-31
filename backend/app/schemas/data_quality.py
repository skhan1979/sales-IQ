"""
Sales IQ - Data Quality Schemas
Request/Response models for the Data Quality Agent API.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================
# Request Models
# =============================================

class DQScanRequest(BaseModel):
    """Trigger a data quality scan."""
    entity_type: str = Field(
        ...,
        description="Entity to scan: customers, invoices, or payments",
        pattern="^(customers|invoices|payments)$",
    )
    stages: Optional[List[str]] = Field(
        None,
        description="Specific stages to run. Omit for all 5 stages.",
    )


class DQApplyFixRequest(BaseModel):
    """Apply a suggested normalization/enrichment fix."""
    entity_id: UUID
    entity_type: str = Field(..., pattern="^(customers|invoices|payments)$")
    field: str
    new_value: str


class DQBulkApplyRequest(BaseModel):
    """Apply multiple fixes at once."""
    fixes: List[DQApplyFixRequest]


class DQQuarantineAction(BaseModel):
    """Release or confirm quarantine on an entity."""
    entity_id: UUID
    action: str = Field(..., pattern="^(release|confirm)$")
    notes: Optional[str] = None


# =============================================
# Response Models
# =============================================

class DQIssue(BaseModel):
    entity_id: str
    stage: str
    severity: str  # critical, warning, info
    field: str
    message: str


class DQChange(BaseModel):
    entity_id: str
    stage: str
    field: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None


class DQDedupMatch(BaseModel):
    entity_a: str
    entity_b: str
    confidence: float
    reasons: List[str]


class DQEntityResult(BaseModel):
    entity_id: str
    quality_score: float
    issues: List[DQIssue]
    changes: List[DQChange]
    is_quarantined: bool


class DQStageTiming(BaseModel):
    stage: str
    duration_ms: float


class DQScanResponse(BaseModel):
    """Result of a data quality scan run."""
    run_id: str
    status: str  # completed, failed
    batch_id: str
    entity_type: str
    records_processed: int
    records_succeeded: int
    records_failed: int
    total_issues: int
    quarantined_count: int
    average_quality_score: float
    stage_timings: Dict[str, float]
    duration_ms: int
    error: Optional[str] = None

    # Detailed results
    entity_results: Optional[List[DQEntityResult]] = None
    dedup_matches: Optional[List[DQDedupMatch]] = None
    normalization_changes: Optional[List[DQChange]] = None
    anomalies: Optional[List[Dict[str, Any]]] = None
    enrichments: Optional[List[Dict[str, Any]]] = None


class DQRecordResponse(BaseModel):
    """Stored data quality record for an entity."""
    id: UUID
    entity_type: str
    entity_id: Optional[UUID] = None
    status: str
    quality_score: float
    validation_issues: List[Any]
    dedup_matches: List[Any]
    normalization_changes: List[Any]
    anomalies_detected: List[Any]
    enrichment_applied: List[Any]
    is_quarantined: bool
    quarantine_reason: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DQRecordListResponse(BaseModel):
    items: List[DQRecordResponse]
    total: int
    page: int
    page_size: int


class DQDashboard(BaseModel):
    """Data quality dashboard overview."""
    overall_score: float
    total_entities: int
    clean_count: int
    warning_count: int
    quarantined_count: int
    enriched_count: int
    issues_by_severity: Dict[str, int]
    issues_by_stage: Dict[str, int]
    top_issues: List[DQIssue]
    recent_scans: List[Dict[str, Any]]
