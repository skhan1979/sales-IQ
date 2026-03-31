"""
Sales IQ - API v1 Router
Aggregates all endpoint routers.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth, sso, users, customers, invoices, payments, dashboard,
    data_quality, demo_data, csv_import, disputes, credit_limits, collections,
    briefings, agent_hub, notifications, analytics, webhooks,
    collections_copilot, intelligence, cfo_dashboard, sales_dashboard,
    executive_dashboard, admin_panel, locale, performance, milestone,
)

api_router = APIRouter()


@api_router.get("/ping")
async def ping():
    """Simple ping endpoint."""
    return {"message": "pong", "service": "salesiq-api-v1"}


# Auth & SSO
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(sso.router, prefix="/auth/sso", tags=["SSO"])

# User Management
api_router.include_router(users.router, prefix="/users", tags=["Users"])

# Business Entities
api_router.include_router(customers.router, prefix="/customers", tags=["Customers"])
api_router.include_router(invoices.router, prefix="/invoices", tags=["Invoices"])
api_router.include_router(payments.router, prefix="/payments", tags=["Payments"])

# Dashboard
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])

# Data Quality Agent
api_router.include_router(data_quality.router, prefix="/data-quality", tags=["Data Quality"])

# Demo Data Manager
api_router.include_router(demo_data.router, prefix="/demo-data", tags=["Demo Data"])

# CSV Import
api_router.include_router(csv_import.router, prefix="/import", tags=["CSV Import"])

# Workflows
api_router.include_router(disputes.router, prefix="/disputes", tags=["Disputes"])
api_router.include_router(credit_limits.router, prefix="/credit-limits", tags=["Credit Limits"])
api_router.include_router(collections.router, prefix="/collections", tags=["Collections"])

# Briefings
api_router.include_router(briefings.router, prefix="/briefings", tags=["Briefings"])

# Agent Hub
api_router.include_router(agent_hub.router, prefix="/agent-hub", tags=["Agent Hub"])

# Notifications & Alerts
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])

# Analytics & Reporting
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])

# Webhooks & Integrations
api_router.include_router(webhooks.router, prefix="/integrations", tags=["Webhooks & Integrations"])

# Collections Copilot (Day 13)
api_router.include_router(collections_copilot.router, prefix="/collections-copilot", tags=["Collections Copilot"])

# Intelligence Layer (Day 14)
api_router.include_router(intelligence.router, prefix="/intelligence", tags=["Intelligence"])

# CFO Dashboard (Day 15)
api_router.include_router(cfo_dashboard.router, prefix="/cfo", tags=["CFO Dashboard"])

# Sales Dashboard (Day 16)
api_router.include_router(sales_dashboard.router, prefix="/sales", tags=["Sales Dashboard"])

# Executive Dashboard (Day 17)
api_router.include_router(executive_dashboard.router, prefix="/executive", tags=["Executive Dashboard"])

# Admin Panel (Day 18)
api_router.include_router(admin_panel.router, prefix="/admin", tags=["Admin Panel"])

# Locale / i18n (Day 19)
api_router.include_router(locale.router, prefix="/i18n", tags=["Locale & i18n"])

# Performance Monitoring (Day 20)
api_router.include_router(performance.router, prefix="/perf", tags=["Performance"])

# Milestone 1 Demo (Day 21)
api_router.include_router(milestone.router, prefix="/milestone", tags=["Milestone & Demo"])
