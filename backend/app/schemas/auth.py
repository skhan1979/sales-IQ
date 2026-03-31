"""
Sales IQ - Pydantic Schemas for Authentication
Request/response models for auth endpoints.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# =============================================
# Auth Request Schemas
# =============================================

class LoginRequest(BaseModel):
    """Email + password login."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    tenant_slug: Optional[str] = None  # Optional — auto-detected from email domain if not provided


class RegisterRequest(BaseModel):
    """New user registration (tenant admin creates users)."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=2, max_length=255)
    role: str = Field(default="viewer")
    phone: Optional[str] = None
    territory_ids: Optional[List[UUID]] = None

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        has_upper = any(c.isupper() for c in v)
        has_lower = any(c.islower() for c in v)
        has_digit = any(c.isdigit() for c in v)
        if not (has_upper and has_lower and has_digit):
            raise ValueError("Password must contain uppercase, lowercase, and a digit")
        return v


class RefreshTokenRequest(BaseModel):
    """Refresh token exchange."""
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    """Change password for current user."""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


# =============================================
# SSO Request Schemas
# =============================================

class SSOCallbackRequest(BaseModel):
    """OAuth2 callback from SSO provider."""
    code: str
    state: Optional[str] = None
    redirect_uri: Optional[str] = None


# =============================================
# Auth Response Schemas
# =============================================

class TokenResponse(BaseModel):
    """JWT token pair response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserResponse(BaseModel):
    """User profile response."""
    id: UUID
    tenant_id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    is_sso: bool
    sso_provider: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    territory_ids: Optional[List[UUID]] = None
    last_login_at: Optional[str] = None
    preferences: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MeResponse(BaseModel):
    """Current user with tenant context."""
    user: UserResponse
    tenant: "TenantBriefResponse"


class TenantBriefResponse(BaseModel):
    """Minimal tenant info returned with auth."""
    id: UUID
    name: str
    slug: str
    logo_url: Optional[str] = None
    primary_color: str = "#1E40AF"
    timezone: str = "Asia/Dubai"
    default_currency: str = "AED"
    locale: str = "en"

    model_config = {"from_attributes": True}


# =============================================
# User Management Schemas
# =============================================

class UserCreateRequest(BaseModel):
    """Admin creates a new user in their tenant."""
    email: EmailStr
    password: Optional[str] = Field(None, min_length=8, max_length=128)
    full_name: str = Field(..., min_length=2, max_length=255)
    role: str = Field(default="viewer")
    phone: Optional[str] = None
    territory_ids: Optional[List[UUID]] = None
    is_sso: bool = False
    sso_provider: Optional[str] = None


class UserUpdateRequest(BaseModel):
    """Update user fields."""
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    role: Optional[str] = None
    phone: Optional[str] = None
    territory_ids: Optional[List[UUID]] = None
    is_active: Optional[bool] = None
    preferences: Optional[dict] = None


class UserListResponse(BaseModel):
    """Paginated user list."""
    items: List[UserResponse]
    total: int
    page: int
    page_size: int
