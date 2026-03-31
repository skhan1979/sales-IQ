"""
Sales IQ - Database Session Management
Async SQLAlchemy engine and session with multi-tenant RLS support.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

from app.core.config import get_settings

settings = get_settings()

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session.
    Tenant context must be set separately via set_tenant_context().
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def set_tenant_context(session: AsyncSession, tenant_id: str) -> None:
    """
    Set the current tenant context for Row-Level Security.
    This MUST be called at the start of every request that accesses tenant data.

    NOTE: SET LOCAL cannot use parameterized queries with asyncpg,
    so we validate the UUID format first to prevent injection.
    """
    import uuid
    # Validate UUID format to prevent SQL injection
    validated = str(uuid.UUID(str(tenant_id)))
    await session.execute(
        text(f"SET LOCAL app.current_tenant_id = '{validated}'")
    )


@asynccontextmanager
async def get_tenant_session(tenant_id: str) -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager that provides a database session with tenant context already set.
    Use this for background tasks (Celery workers, agents) that need tenant isolation.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await set_tenant_context(session, tenant_id)
            yield session
