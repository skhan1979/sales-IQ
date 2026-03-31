"""
Sales IQ - Core Domain Models
Tenant, User, Role, and foundational entities.
"""

from sqlalchemy import (
    Column, String, Boolean, Integer, Float, Text, ForeignKey,
    Enum as SQLEnum, UniqueConstraint, Index, text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
import enum

from app.models.base import BaseModel, TenantBaseModel, AuditableModel


# =============================================
# Enums
# =============================================

class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    TENANT_ADMIN = "tenant_admin"
    CFO = "cfo"
    FINANCE_MANAGER = "finance_manager"
    COLLECTOR = "collector"
    SALES_REP = "sales_rep"
    VIEWER = "viewer"


class TenantStatus(str, enum.Enum):
    ACTIVE = "active"
    TRIAL = "trial"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class ConnectorType(str, enum.Enum):
    D365_FO = "d365_fo"
    SAP_B1 = "sap_b1"
    AX_2012 = "ax_2012"
    SALESFORCE = "salesforce"
    CSV_IMPORT = "csv_import"
    DEMO = "demo"


class SyncStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


# =============================================
# Tenant (Platform-Level — NO RLS)
# =============================================

class Tenant(BaseModel):
    """
    Top-level tenant entity. NOT subject to RLS — managed by super admin.
    """
    __tablename__ = "tenants"

    name = Column(String(255), nullable=False)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    domain = Column(String(255), nullable=True)
    status = Column(SQLEnum(TenantStatus), default=TenantStatus.TRIAL, nullable=False)
    logo_url = Column(String(500), nullable=True)
    primary_color = Column(String(7), default="#1E40AF")
    timezone = Column(String(50), default="Asia/Dubai")
    default_currency = Column(String(3), default="AED")
    locale = Column(String(10), default="en")
    settings = Column(JSONB, default=dict)
    max_users = Column(Integer, default=25)
    subscription_tier = Column(String(50), default="trial")

    # Relationships
    users = relationship("User", back_populates="tenant", foreign_keys="[User.tenant_id]", lazy="selectin")
    connectors = relationship("ConnectorConfig", back_populates="tenant", foreign_keys="[ConnectorConfig.tenant_id]", lazy="selectin")


# =============================================
# User (Tenant-Scoped — RLS enforced)
# =============================================

class User(TenantBaseModel):
    """
    Platform user — scoped to a tenant via RLS.
    """
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),
        Index("ix_users_tenant_role", "tenant_id", "role"),
    )

    email = Column(String(255), nullable=False, index=True)
    hashed_password = Column(String(255), nullable=True)  # Null for SSO-only users
    full_name = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.VIEWER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, server_default=text("true"))
    is_sso = Column(Boolean, default=False, nullable=False, server_default=text("false"))
    sso_provider = Column(String(50), nullable=True)  # azure_ad, google, saml
    sso_subject_id = Column(String(255), nullable=True)  # External IdP user ID
    avatar_url = Column(String(500), nullable=True)
    phone = Column(String(20), nullable=True)
    territory_ids = Column(ARRAY(UUID(as_uuid=True)), default=list)
    last_login_at = Column(String(50), nullable=True)
    preferences = Column(JSONB, default=dict)  # Home screen widget config, language, etc.

    # Relationships — specify foreign_keys explicitly since tenant_id comes from mixin
    tenant = relationship("Tenant", back_populates="users", foreign_keys="[User.tenant_id]", lazy="joined")


# =============================================
# Connector Configuration (Tenant-Scoped)
# =============================================

class ConnectorConfig(TenantBaseModel):
    """
    ERP/CRM connector configuration per tenant.
    Stores encrypted credentials and sync settings.
    """
    __tablename__ = "connector_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "connector_type", name="uq_connector_tenant_type"),
    )

    connector_type = Column(SQLEnum(ConnectorType), nullable=False)
    display_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    config = Column(JSONB, default=dict)  # Encrypted connection parameters
    field_mapping = Column(JSONB, default=dict)  # Source → Sales IQ field mapping
    sync_schedule = Column(String(100), default="0 */4 * * *")  # Cron expression
    last_sync_at = Column(String(50), nullable=True)
    last_sync_status = Column(SQLEnum(SyncStatus), nullable=True)
    last_sync_records = Column(Integer, default=0)
    last_sync_errors = Column(JSONB, default=list)

    # Relationships
    tenant = relationship("Tenant", back_populates="connectors", foreign_keys="[ConnectorConfig.tenant_id]", lazy="joined")


# =============================================
# Audit Log (Tenant-Scoped — Append-Only)
# =============================================

class AuditLog(TenantBaseModel):
    """
    Immutable audit trail. Captures every CRUD operation.
    Populated automatically via SQLAlchemy event listeners.
    """
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_tenant_entity", "tenant_id", "entity_type", "entity_id"),
        Index("ix_audit_tenant_created", "tenant_id", "created_at"),
    )

    user_id = Column(UUID(as_uuid=True), nullable=True)  # Null for system actions
    user_email = Column(String(255), nullable=True)
    action = Column(String(50), nullable=False)  # CREATE, UPDATE, DELETE, READ, LOGIN, etc.
    entity_type = Column(String(100), nullable=False)  # Table name
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    before_state = Column(JSONB, nullable=True)  # Previous values (for UPDATE)
    after_state = Column(JSONB, nullable=True)  # New values
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    metadata_ = Column("metadata", JSONB, default=dict)
