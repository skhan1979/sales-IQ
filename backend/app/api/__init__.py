"""
Sales IQ - API v1 Router
Aggregates all endpoint routers.
"""

from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/ping")
async def ping():
    """Simple ping endpoint."""
    return {"message": "pong", "service": "salesiq-api-v1"}


# Endpoint routers will be added here as we build each feature:
# from app.api.v1.endpoints import auth, customers, invoices, payments, ...
# api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
# api_router.include_router(customers.router, prefix="/customers", tags=["Customers"])
# etc.
