"""
Sales IQ - SQLAlchemy Base Models
Multi-tenant base with automatic tenant_id injection and RLS support.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Boolean, text, event, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class TimestampMixin:
    """Adds created_at and updated_at timestamps to models."""

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class TenantMixin:
    """
    Multi-tenant mixin — adds tenant_id column.
    All tenant-scoped tables MUST inherit from this.
    PostgreSQL RLS policies will filter rows by app.current_tenant_id.
    """

    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Tenant isolation key -- enforced by PostgreSQL RLS",
    )


class SoftDeleteMixin:
    """Soft-delete support — marks records as deleted without removing them."""

    is_deleted = Column(Boolean, default=False, nullable=False, server_default=text("false"))
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(UUID(as_uuid=True), nullable=True)


class BaseModel(Base, TimestampMixin):
    """
    Abstract base for all Sales IQ models.
    Provides UUID primary key and timestamps.
    """

    __abstract__ = True

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )


class TenantBaseModel(BaseModel, TenantMixin):
    """
    Abstract base for all tenant-scoped models.
    Automatically includes tenant_id for RLS enforcement.
    """

    __abstract__ = True


class AuditableModel(TenantBaseModel, SoftDeleteMixin):
    """
    Abstract base for models that need full audit trail + soft delete.
    Use for critical business entities (invoices, customers, payments, etc.)
    """

    __abstract__ = True

    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)


# =============================================
# RLS Policy Generator
# =============================================

def generate_rls_policy_sql(table_name: str) -> str:
    """
    Generate SQL statements to enable RLS on a table.
    Call this during migrations for every tenant-scoped table.
    """
    return f"""
    -- Enable RLS on {table_name}
    ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;
    ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;

    -- Tenant isolation policy
    DROP POLICY IF EXISTS tenant_isolation_policy ON {table_name};
    CREATE POLICY tenant_isolation_policy ON {table_name}
        USING (tenant_id = current_tenant_id())
        WITH CHECK (tenant_id = current_tenant_id());

    -- Superuser bypass (for admin operations)
    DROP POLICY IF EXISTS superuser_bypass_policy ON {table_name};
    CREATE POLICY superuser_bypass_policy ON {table_name}
        USING (current_setting('app.current_tenant_id', true) = 'SUPERUSER')
        WITH CHECK (current_setting('app.current_tenant_id', true) = 'SUPERUSER');
    """
