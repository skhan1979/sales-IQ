"""
Sales IQ - Auth Dependencies
FastAPI dependencies for authentication, tenant resolution, and RBAC.
"""

from typing import Optional, List
from uuid import UUID

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db, set_tenant_context
from app.core.security import decode_token
from app.models.core import User, Tenant, UserRole

settings = get_settings()

# Bearer token extraction
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extract and validate JWT, load user from database, set tenant context.
    This is the primary auth dependency — use on all protected endpoints.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    tenant_id = payload.get("tid")

    if not user_id or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token",
        )

    # Set tenant context for RLS BEFORE querying
    await set_tenant_context(db, tenant_id)

    # Load user
    result = await db.execute(
        select(User).where(User.id == UUID(user_id), User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Optional auth — returns None instead of raising if no token provided."""
    if not credentials:
        return None
    return await get_current_user(credentials, db)


# =============================================
# Role-Based Access Control
# =============================================

# Role hierarchy: higher index = more permissions
ROLE_HIERARCHY = {
    UserRole.VIEWER: 0,
    UserRole.SALES_REP: 1,
    UserRole.COLLECTOR: 2,
    UserRole.FINANCE_MANAGER: 3,
    UserRole.CFO: 4,
    UserRole.TENANT_ADMIN: 5,
    UserRole.SUPER_ADMIN: 6,
}


class RoleChecker:
    """
    Dependency factory for role-based access control.

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(user: User = Depends(RoleChecker(UserRole.TENANT_ADMIN))):
            ...

        @router.get("/finance-team")
        async def finance_endpoint(user: User = Depends(RoleChecker([UserRole.COLLECTOR, UserRole.FINANCE_MANAGER]))):
            ...
    """

    def __init__(self, allowed_roles: UserRole | List[UserRole], min_role: Optional[UserRole] = None):
        """
        Args:
            allowed_roles: Specific role(s) allowed, OR
            min_role: Minimum role level in hierarchy (all roles >= this are allowed)
        """
        if isinstance(allowed_roles, list):
            self.allowed_roles = allowed_roles
        else:
            self.allowed_roles = [allowed_roles]
        self.min_role = min_role

    async def __call__(self, user: User = Depends(get_current_user)) -> User:
        user_role = UserRole(user.role) if isinstance(user.role, str) else user.role

        # Super admin always passes
        if user_role == UserRole.SUPER_ADMIN:
            return user

        # Check minimum role level
        if self.min_role:
            user_level = ROLE_HIERARCHY.get(user_role, 0)
            min_level = ROLE_HIERARCHY.get(self.min_role, 0)
            if user_level >= min_level:
                return user

        # Check specific allowed roles
        if user_role in self.allowed_roles:
            return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required: {[r.value for r in self.allowed_roles]}",
        )


# Convenience dependency factories
require_admin = RoleChecker(UserRole.TENANT_ADMIN)
require_finance = RoleChecker(min_role=UserRole.FINANCE_MANAGER, allowed_roles=[UserRole.FINANCE_MANAGER])
require_collector_or_above = RoleChecker(min_role=UserRole.COLLECTOR, allowed_roles=[UserRole.COLLECTOR])
require_cfo = RoleChecker(UserRole.CFO)


# =============================================
# Tenant Resolution
# =============================================

async def get_tenant_from_slug(
    tenant_slug: str,
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """Resolve a tenant from its URL slug."""
    result = await db.execute(
        select(Tenant).where(Tenant.slug == tenant_slug, Tenant.status != "cancelled")
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_slug}' not found",
        )
    return tenant


async def get_current_tenant(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """Get the tenant of the currently authenticated user."""
    result = await db.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tenant not found for current user",
        )
    return tenant
