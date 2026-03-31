"""
Sales IQ - Models Package
Import all models here so Alembic can discover them.
"""

from app.models.base import Base, BaseModel, TenantBaseModel, AuditableModel
from app.models.core import (
    Tenant,
    User,
    ConnectorConfig,
    AuditLog,
    UserRole,
    TenantStatus,
    ConnectorType,
    SyncStatus,
)
from app.models.business import (
    Customer,
    Invoice,
    Payment,
    Dispute,
    CreditLimitRequest,
    CollectionActivity,
    Briefing,
    DataQualityRecord,
    OCRDocument,
    AgentRunLog,
    WriteOff,
    Product,
    CustomerStatus,
    InvoiceStatus,
    PaymentMethod,
    DisputeStatus,
    DisputeReason,
    CreditApprovalStatus,
    ECLStage,
    CollectionAction,
    DataQualityStatus,
)

__all__ = [
    # Base
    "Base",
    "BaseModel",
    "TenantBaseModel",
    "AuditableModel",
    # Core
    "Tenant",
    "User",
    "ConnectorConfig",
    "AuditLog",
    # Business
    "Customer",
    "Invoice",
    "Payment",
    "Dispute",
    "CreditLimitRequest",
    "CollectionActivity",
    "Briefing",
    "DataQualityRecord",
    "OCRDocument",
    "AgentRunLog",
    "WriteOff",
    "Product",
    # Enums
    "UserRole",
    "TenantStatus",
    "ConnectorType",
    "SyncStatus",
    "CustomerStatus",
    "InvoiceStatus",
    "PaymentMethod",
    "DisputeStatus",
    "DisputeReason",
    "CreditApprovalStatus",
    "ECLStage",
    "CollectionAction",
    "DataQualityStatus",
]
