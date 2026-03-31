"""
Sales IQ - SSO Provider Implementations
Azure AD OIDC, Google Workspace OAuth 2.0, SAML 2.0 scaffolding.
"""

from typing import Optional
from dataclasses import dataclass

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db, set_tenant_context
from app.core.security import create_access_token, create_refresh_token
from app.models.core import User, Tenant, UserRole, AuditLog
from app.schemas.auth import TokenResponse

settings = get_settings()
router = APIRouter()


# =============================================
# SSO User Info Data Class
# =============================================

@dataclass
class SSOUserInfo:
    """Normalized user info from any SSO provider."""
    email: str
    full_name: str
    subject_id: str  # Provider-specific unique ID
    provider: str  # azure_ad, google, saml
    avatar_url: Optional[str] = None
    groups: Optional[list[str]] = None


# =============================================
# Azure AD OIDC
# =============================================

@router.get("/azure-ad/authorize")
async def azure_ad_authorize(tenant_slug: Optional[str] = None):
    """Generate Azure AD authorization URL."""
    if not settings.AZURE_AD_CLIENT_ID or not settings.AZURE_AD_TENANT_ID:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Azure AD SSO is not configured",
        )

    authorize_url = (
        f"https://login.microsoftonline.com/{settings.AZURE_AD_TENANT_ID}/oauth2/v2.0/authorize"
        f"?client_id={settings.AZURE_AD_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={settings.AZURE_AD_REDIRECT_URI}"
        f"&response_mode=query"
        f"&scope=openid+profile+email+User.Read"
        f"&state={tenant_slug or 'default'}"
    )

    return {"authorize_url": authorize_url}


@router.post("/azure-ad/callback", response_model=TokenResponse)
async def azure_ad_callback(
    code: str,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle Azure AD OAuth2 callback.
    Exchange code for tokens, extract user info, provision or login user.
    """
    if not settings.AZURE_AD_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Azure AD not configured")

    # Exchange authorization code for tokens
    token_url = f"https://login.microsoftonline.com/{settings.AZURE_AD_TENANT_ID}/oauth2/v2.0/token"

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            token_url,
            data={
                "client_id": settings.AZURE_AD_CLIENT_ID,
                "client_secret": settings.AZURE_AD_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.AZURE_AD_REDIRECT_URI,
                "grant_type": "authorization_code",
                "scope": "openid profile email User.Read",
            },
        )

        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to exchange authorization code",
            )

        tokens = token_response.json()
        access_token_ad = tokens.get("access_token")

        # Get user info from Microsoft Graph
        graph_response = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token_ad}"},
        )

        if graph_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to fetch user profile from Microsoft Graph",
            )

        profile = graph_response.json()

    user_info = SSOUserInfo(
        email=profile.get("mail") or profile.get("userPrincipalName", ""),
        full_name=profile.get("displayName", ""),
        subject_id=profile.get("id", ""),
        provider="azure_ad",
        avatar_url=None,
    )

    return await _sso_login_or_provision(user_info, state, db)


# =============================================
# Google Workspace OAuth 2.0
# =============================================

@router.get("/google/authorize")
async def google_authorize(tenant_slug: Optional[str] = None):
    """Generate Google OAuth2 authorization URL."""
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google Workspace SSO is not configured",
        )

    authorize_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.GOOGLE_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={settings.GOOGLE_REDIRECT_URI}"
        f"&scope=openid+email+profile"
        f"&access_type=offline"
        f"&state={tenant_slug or 'default'}"
    )

    return {"authorize_url": authorize_url}


@router.post("/google/callback", response_model=TokenResponse)
async def google_callback(
    code: str,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth2 callback."""
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google SSO not configured")

    async with httpx.AsyncClient() as client:
        # Exchange code for tokens
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )

        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to exchange Google authorization code",
            )

        tokens = token_response.json()
        google_access_token = tokens.get("access_token")

        # Get user info
        userinfo_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {google_access_token}"},
        )

        if userinfo_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to fetch Google user profile",
            )

        profile = userinfo_response.json()

    user_info = SSOUserInfo(
        email=profile.get("email", ""),
        full_name=profile.get("name", ""),
        subject_id=profile.get("id", ""),
        provider="google",
        avatar_url=profile.get("picture"),
    )

    return await _sso_login_or_provision(user_info, state, db)


# =============================================
# SAML 2.0 (Scaffolding)
# =============================================

@router.post("/saml/acs")
async def saml_assertion_consumer(request: Request, db: AsyncSession = Depends(get_db)):
    """
    SAML 2.0 Assertion Consumer Service endpoint.
    Receives SAML response from enterprise IdP.

    NOTE: Full SAML implementation requires python3-saml library
    and IdP metadata configuration per tenant.
    This is scaffolded for Day 2 — full implementation when design partner
    provides their IdP metadata.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="SAML 2.0 SSO is scaffolded. Configure IdP metadata in tenant settings to enable.",
    )


@router.get("/saml/metadata")
async def saml_metadata(tenant_slug: str):
    """
    Return SAML SP metadata XML for tenant.
    Enterprise IdPs need this to configure the trust relationship.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="SAML metadata generation requires tenant IdP configuration.",
    )


# =============================================
# Shared SSO Login / Auto-Provisioning
# =============================================

async def _sso_login_or_provision(
    user_info: SSOUserInfo,
    tenant_slug: Optional[str],
    db: AsyncSession,
) -> TokenResponse:
    """
    Common SSO flow:
    1. Resolve tenant from state/slug or email domain
    2. Find existing user by sso_subject_id or email
    3. Auto-provision if user doesn't exist (JIT provisioning)
    4. Issue JWT tokens
    """
    # Resolve tenant
    tenant = None

    if tenant_slug and tenant_slug != "default":
        result = await db.execute(
            select(Tenant).where(Tenant.slug == tenant_slug)
        )
        tenant = result.scalar_one_or_none()

    if not tenant:
        # Try email domain matching
        domain = user_info.email.split("@")[1] if "@" in user_info.email else ""
        result = await db.execute(
            select(Tenant).where(Tenant.domain == domain)
        )
        tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenant found for this SSO account. Contact your administrator.",
        )

    # Set tenant context
    await set_tenant_context(db, str(tenant.id))

    # Look for existing user by SSO subject ID
    result = await db.execute(
        select(User).where(
            User.tenant_id == tenant.id,
            User.sso_provider == user_info.provider,
            User.sso_subject_id == user_info.subject_id,
        )
    )
    user = result.scalar_one_or_none()

    # Fallback: try by email
    if not user:
        result = await db.execute(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == user_info.email,
            )
        )
        user = result.scalar_one_or_none()

        # Link SSO to existing email-matched user
        if user:
            user.is_sso = True
            user.sso_provider = user_info.provider
            user.sso_subject_id = user_info.subject_id
            if user_info.avatar_url:
                user.avatar_url = user_info.avatar_url

    # Auto-provision new user (JIT)
    if not user:
        user = User(
            tenant_id=tenant.id,
            email=user_info.email,
            full_name=user_info.full_name,
            role=UserRole.VIEWER,  # Default role for auto-provisioned users
            is_active=True,
            is_sso=True,
            sso_provider=user_info.provider,
            sso_subject_id=user_info.subject_id,
            avatar_url=user_info.avatar_url,
        )
        db.add(user)
        await db.flush()

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Contact your administrator.",
        )

    # Update last login
    from datetime import datetime, timezone
    user.last_login_at = datetime.now(timezone.utc).isoformat()
    await db.commit()

    # Audit log
    audit = AuditLog(
        tenant_id=tenant.id,
        user_id=user.id,
        user_email=user.email,
        action="SSO_LOGIN",
        entity_type="users",
        entity_id=user.id,
        metadata_={"provider": user_info.provider},
    )
    db.add(audit)
    await db.commit()

    # Generate JWT tokens
    role_val = user.role.value if isinstance(user.role, UserRole) else user.role
    access_token = create_access_token(
        subject=str(user.id),
        tenant_id=str(tenant.id),
        role=role_val,
        extra_claims={"email": user.email, "name": user.full_name},
    )
    refresh_token = create_refresh_token(
        subject=str(user.id),
        tenant_id=str(tenant.id),
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
