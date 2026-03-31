"""
Sales IQ - Authentication Endpoints
Login, register, refresh token, current user profile.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db, set_tenant_context
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.deps import get_current_user
from app.models.core import User, Tenant, UserRole, AuditLog
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    ChangePasswordRequest,
    TokenResponse,
    UserResponse,
    MeResponse,
    TenantBriefResponse,
)

settings = get_settings()
router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Authenticate with email + password.
    Resolves tenant from slug or email domain.
    """
    # Resolve tenant
    tenant = None
    if request.tenant_slug:
        result = await db.execute(
            select(Tenant).where(Tenant.slug == request.tenant_slug)
        )
        tenant = result.scalar_one_or_none()
    else:
        # Try to resolve from email domain
        domain = request.email.split("@")[1]
        result = await db.execute(
            select(Tenant).where(Tenant.domain == domain)
        )
        tenant = result.scalar_one_or_none()

    if not tenant:
        # Fall back: find any tenant with this user
        result = await db.execute(
            select(User).where(User.email == request.email, User.is_active == True)
        )
        user = result.scalar_one_or_none()
        if user:
            t_result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
            tenant = t_result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Set tenant context for RLS
    await set_tenant_context(db, str(tenant.id))

    # Find user within tenant
    result = await db.execute(
        select(User).where(
            User.email == request.email,
            User.tenant_id == tenant.id,
            User.is_active == True,
        )
    )
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Update last login
    user.last_login_at = datetime.now(timezone.utc).isoformat()
    await db.commit()

    # Generate tokens
    access_token = create_access_token(
        subject=str(user.id),
        tenant_id=str(tenant.id),
        role=user.role.value if isinstance(user.role, UserRole) else user.role,
        extra_claims={"email": user.email, "name": user.full_name},
    )
    refresh_token = create_refresh_token(
        subject=str(user.id),
        tenant_id=str(tenant.id),
    )

    # Audit log
    audit = AuditLog(
        tenant_id=tenant.id,
        user_id=user.id,
        user_email=user.email,
        action="LOGIN",
        entity_type="users",
        entity_id=user.id,
    )
    db.add(audit)
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a refresh token for a new access token."""
    try:
        payload = decode_token(request.refresh_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    tenant_id = payload.get("tid")

    # Set tenant context
    await set_tenant_context(db, tenant_id)

    # Verify user still exists and is active
    from uuid import UUID
    result = await db.execute(
        select(User).where(User.id == UUID(user_id), User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Issue new tokens
    access_token = create_access_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
        role=user.role.value if isinstance(user.role, UserRole) else user.role,
        extra_claims={"email": user.email, "name": user.full_name},
    )
    new_refresh = create_refresh_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=MeResponse)
async def get_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current authenticated user profile with tenant context."""
    # Load tenant
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()

    return MeResponse(
        user=UserResponse.model_validate(user),
        tenant=TenantBriefResponse.model_validate(tenant),
    )


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change password for the current user."""
    if not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSO users cannot change password here",
        )

    if not verify_password(request.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    user.hashed_password = hash_password(request.new_password)
    await db.commit()

    # Audit
    audit = AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        user_email=user.email,
        action="UPDATE",
        entity_type="users",
        entity_id=user.id,
        after_state={"field": "password", "changed": True},
    )
    db.add(audit)
    await db.commit()

    return {"message": "Password changed successfully"}
