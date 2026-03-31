"""
Sales IQ - Audit Trail Middleware
Automatic capture of request context for audit logging.
"""

import time
from uuid import uuid4
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.security import decode_token_safe


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enriches the request state with audit context:
    - request_id: Unique ID for tracing
    - user_id: From JWT token (if authenticated)
    - tenant_id: From JWT token (if authenticated)
    - ip_address: Client IP
    - user_agent: Client user agent
    - start_time: For response time tracking
    """

    async def dispatch(self, request: Request, call_next):
        # Generate request ID
        request_id = str(uuid4())
        request.state.request_id = request_id
        request.state.start_time = time.time()

        # Extract auth context from Bearer token (non-blocking)
        request.state.user_id = None
        request.state.tenant_id = None
        request.state.user_email = None

        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = decode_token_safe(token)
            if payload:
                request.state.user_id = payload.get("sub")
                request.state.tenant_id = payload.get("tid")
                request.state.user_email = payload.get("email")

        # Client info
        request.state.ip_address = request.client.host if request.client else "unknown"
        request.state.user_agent = request.headers.get("user-agent", "")

        # Process request
        response = await call_next(request)

        # Add tracing headers
        duration_ms = int((time.time() - request.state.start_time) * 1000)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        return response


class TerritoryFilterMiddleware:
    """
    Utility to filter data by user's territory assignments.
    Not a true middleware — used as a helper in service layer.

    Usage in endpoints:
        territories = get_user_territories(current_user)
        query = query.where(Customer.territory.in_(territories))
    """

    @staticmethod
    def get_user_territories(user) -> Optional[list]:
        """
        Returns territory filter list for the user.
        Returns None for admin/CFO roles (no filtering = see everything).
        """
        from app.models.core import UserRole

        role = UserRole(user.role) if isinstance(user.role, str) else user.role

        # Admins, CFOs, and Finance Managers see all territories
        if role in (UserRole.SUPER_ADMIN, UserRole.TENANT_ADMIN, UserRole.CFO, UserRole.FINANCE_MANAGER):
            return None  # No territory filter

        # Collectors and Sales Reps only see their assigned territories
        if user.territory_ids:
            return user.territory_ids

        # No territories assigned = see nothing (safety default)
        return []
