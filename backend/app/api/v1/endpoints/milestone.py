"""
Sales IQ - Demo & Milestone 1 Endpoints
Day 21: Demo validation walkthrough, readiness check, design partner onboarding.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.core import User, Tenant, AuditLog, ConnectorConfig
from app.models.business import (
    Customer, Invoice, Payment, Dispute, CollectionActivity,
    CreditLimitRequest, Briefing, AgentRunLog, DataQualityRecord,
    WriteOff, CustomerStatus,
)

router = APIRouter()


# ═══════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════

class DemoReadinessResponse(BaseModel):
    overall_ready: bool
    score: float  # 0-100
    checks: list
    timestamp: str


class DesignPartnerOnboardRequest(BaseModel):
    company_name: str
    contact_name: str
    contact_email: str
    erp_system: str = Field(default="d365_fo", description="d365_fo, sap_b1, ax_2012")
    crm_system: Optional[str] = Field(default=None, description="salesforce, d365_sales")
    estimated_customers: int = Field(default=100, ge=10, le=1000)
    industry: str = Field(default="trading")
    region: str = Field(default="GCC")


class DemoWalkthroughStep(BaseModel):
    step: int
    name: str
    endpoint: str
    method: str
    status: str  # pass, fail, skip
    response_time_ms: float
    notes: str


class DemoWalkthroughResponse(BaseModel):
    total_steps: int
    passed: int
    failed: int
    duration_ms: float
    steps: list[DemoWalkthroughStep]
    milestone_1_ready: bool


# ═══════════════════════════════════════════
# Demo Readiness Check
# ═══════════════════════════════════════════

@router.get("/readiness", response_model=DemoReadinessResponse)
async def check_demo_readiness(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Comprehensive readiness check for Milestone 1 demo.
    Validates data quality, feature completeness, and system health.
    """
    tid = current_user.tenant_id
    checks = []
    total_weight = 0
    weighted_score = 0

    # ── 1. Data Volume Checks ──
    async def count_check(model, label, min_count, weight=1):
        nonlocal total_weight, weighted_score
        total_weight += weight
        q = await db.execute(select(func.count()).where(model.tenant_id == tid))
        count = q.scalar() or 0
        ok = count >= min_count
        if ok:
            weighted_score += weight
        checks.append({
            "category": "data",
            "check": label,
            "status": "pass" if ok else "fail",
            "detail": f"{count} records (min: {min_count})",
        })

    await count_check(Customer, "Customers exist", 10, weight=2)
    await count_check(Invoice, "Invoices exist", 20, weight=2)
    await count_check(Payment, "Payments exist", 10, weight=1)
    await count_check(Dispute, "Disputes exist", 3, weight=1)
    await count_check(CollectionActivity, "Collection activities exist", 5, weight=1)
    await count_check(CreditLimitRequest, "Credit limit requests exist", 2, weight=1)
    await count_check(AgentRunLog, "Agent run logs exist", 3, weight=1)
    await count_check(AuditLog, "Audit log entries exist", 10, weight=1)

    # ── 2. Customer Archetype Diversity ──
    total_weight += 2
    segments_q = await db.execute(
        select(Customer.segment, func.count())
        .where(Customer.tenant_id == tid)
        .group_by(Customer.segment)
    )
    segments = {row[0]: row[1] for row in segments_q.fetchall() if row[0]}
    seg_count = len(segments)
    seg_ok = seg_count >= 3
    if seg_ok:
        weighted_score += 2
    checks.append({
        "category": "data_quality",
        "check": "Customer segment diversity",
        "status": "pass" if seg_ok else "fail",
        "detail": f"{seg_count} segments: {list(segments.keys())[:5]}",
    })

    # ── 3. Risk Score Distribution ──
    total_weight += 1
    risk_q = await db.execute(
        select(func.count()).where(
            Customer.tenant_id == tid,
            Customer.risk_score.isnot(None),
        )
    )
    risk_count = risk_q.scalar() or 0
    risk_ok = risk_count > 0
    if risk_ok:
        weighted_score += 1
    checks.append({
        "category": "intelligence",
        "check": "Risk scores populated",
        "status": "pass" if risk_ok else "fail",
        "detail": f"{risk_count} customers with risk scores",
    })

    # ── 4. Overdue Invoices (demo needs some) ──
    total_weight += 1
    overdue_q = await db.execute(
        select(func.count()).where(
            Invoice.tenant_id == tid,
            Invoice.days_overdue > 0,
        )
    )
    overdue = overdue_q.scalar() or 0
    overdue_ok = overdue >= 5
    if overdue_ok:
        weighted_score += 1
    checks.append({
        "category": "data_quality",
        "check": "Overdue invoices for demo",
        "status": "pass" if overdue_ok else "fail",
        "detail": f"{overdue} overdue invoices (need >= 5 for realistic demo)",
    })

    # ── 5. Aging Buckets Populated ──
    total_weight += 1
    aging_q = await db.execute(
        select(Invoice.aging_bucket, func.count())
        .where(Invoice.tenant_id == tid, Invoice.aging_bucket.isnot(None))
        .group_by(Invoice.aging_bucket)
    )
    buckets = {row[0]: row[1] for row in aging_q.fetchall()}
    bucket_ok = len(buckets) >= 2
    if bucket_ok:
        weighted_score += 1
    checks.append({
        "category": "data_quality",
        "check": "Aging bucket distribution",
        "status": "pass" if bucket_ok else "fail",
        "detail": f"Buckets: {buckets}",
    })

    # ── 6. Agent Hub Functional ──
    total_weight += 1
    from app.services.agent_registry import AGENT_REGISTRY
    agent_count = len(AGENT_REGISTRY)
    agent_ok = agent_count >= 7
    if agent_ok:
        weighted_score += 1
    checks.append({
        "category": "features",
        "check": "Agent Hub (all 7 agents registered)",
        "status": "pass" if agent_ok else "fail",
        "detail": f"{agent_count} agents registered",
    })

    # ── 7. Locale / i18n ──
    total_weight += 1
    from app.middleware.i18n import SUPPORTED_LOCALES
    locale_ok = "ar" in SUPPORTED_LOCALES and "en" in SUPPORTED_LOCALES
    if locale_ok:
        weighted_score += 1
    checks.append({
        "category": "features",
        "check": "Arabic + English i18n support",
        "status": "pass" if locale_ok else "fail",
        "detail": f"Locales: {list(SUPPORTED_LOCALES.keys())}",
    })

    # ── 8. Multi-currency Data ──
    total_weight += 1
    curr_q = await db.execute(
        select(Invoice.currency, func.count())
        .where(Invoice.tenant_id == tid)
        .group_by(Invoice.currency)
    )
    currencies = {row[0]: row[1] for row in curr_q.fetchall()}
    curr_ok = len(currencies) >= 1
    if curr_ok:
        weighted_score += 1
    checks.append({
        "category": "data_quality",
        "check": "Multi-currency data",
        "status": "pass" if curr_ok else "warn",
        "detail": f"Currencies: {currencies}",
    })

    score = round((weighted_score / total_weight * 100) if total_weight > 0 else 0, 1)

    return DemoReadinessResponse(
        overall_ready=score >= 80,
        score=score,
        checks=checks,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ═══════════════════════════════════════════
# Design Partner Onboarding
# ═══════════════════════════════════════════

@router.get("/onboarding/checklist")
async def get_onboarding_checklist(
    current_user: User = Depends(get_current_user),
):
    """Design partner onboarding checklist — what they need to provide."""
    return {
        "title": "Design Partner Onboarding Checklist",
        "description": "Items needed from the design partner to set up their Sales IQ environment",
        "sections": [
            {
                "name": "ERP Access",
                "items": [
                    {"item": "ERP system type", "options": ["D365 F&O", "SAP B1", "AX 2012"], "required": True},
                    {"item": "ERP environment URL", "required": True},
                    {"item": "API credentials (OAuth client ID/secret or service account)", "required": True},
                    {"item": "Entity access: Customers, Invoices, Payments, Orders", "required": True},
                    {"item": "Test/sandbox environment preferred", "required": False},
                ],
            },
            {
                "name": "CRM Access (Optional)",
                "items": [
                    {"item": "CRM system type", "options": ["Salesforce", "D365 Sales"], "required": False},
                    {"item": "CRM instance URL", "required": False},
                    {"item": "API credentials", "required": False},
                    {"item": "Object access: Accounts, Contacts, Opportunities", "required": False},
                ],
            },
            {
                "name": "Users & Roles",
                "items": [
                    {"item": "Admin user email", "required": True},
                    {"item": "Number of pilot users (2-10 recommended)", "required": True},
                    {"item": "User roles needed", "options": ["CFO", "Finance Manager", "Collector", "Sales Rep"], "required": True},
                    {"item": "SSO provider (if applicable)", "options": ["Azure AD", "Google Workspace", "SAML"], "required": False},
                ],
            },
            {
                "name": "Business Context",
                "items": [
                    {"item": "Industry vertical", "required": True},
                    {"item": "Primary currency", "required": True},
                    {"item": "Average customer count", "required": True},
                    {"item": "Typical payment terms (days)", "required": True},
                    {"item": "Key pain points to address", "required": True},
                    {"item": "Current DSO target", "required": False},
                ],
            },
            {
                "name": "Demo Scenarios",
                "items": [
                    {"item": "Use demo data or connect live ERP?", "options": ["Demo data", "Live connection", "Both"], "required": True},
                    {"item": "Priority features to showcase", "required": True},
                    {"item": "Preferred demo date/time", "required": True},
                    {"item": "Attendee list (names, roles)", "required": False},
                ],
            },
        ],
    }


@router.post("/onboarding/register")
async def register_design_partner(
    body: DesignPartnerOnboardRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a new design partner and prepare their demo environment."""
    # Log the registration
    audit = AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_email=current_user.email,
        action="PARTNER_ONBOARD",
        entity_type="design_partner",
        after_state={
            "company": body.company_name,
            "contact": body.contact_name,
            "email": body.contact_email,
            "erp": body.erp_system,
            "crm": body.crm_system,
            "industry": body.industry,
            "region": body.region,
        },
    )
    db.add(audit)
    await db.commit()

    return {
        "status": "registered",
        "company": body.company_name,
        "contact_email": body.contact_email,
        "next_steps": [
            "Admin will create a dedicated tenant for the partner",
            f"Demo data will be generated with {body.erp_system} profile",
            f"Estimated {body.estimated_customers} customers in {body.industry} / {body.region}",
            "Onboarding call to be scheduled within 48 hours",
        ],
        "demo_config": {
            "erp_profile": body.erp_system,
            "crm_profile": body.crm_system,
            "dataset_size": "medium" if body.estimated_customers <= 100 else "large",
            "industry": body.industry,
            "region": body.region,
        },
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════
# Demo Script (API Walkthrough)
# ═══════════════════════════════════════════

@router.get("/demo-script")
async def get_demo_script(
    current_user: User = Depends(get_current_user),
):
    """
    20-minute guided demo script with API endpoints for each step.
    Used by sales team to deliver consistent demos.
    """
    return {
        "title": "Sales IQ — 20-Minute Demo Script",
        "version": "Milestone 1 (Day 21)",
        "duration_minutes": 20,
        "audience": "Design Partners, Early Customers",
        "sections": [
            {
                "name": "1. Login & Role-Based Home Screen",
                "duration": "2 min",
                "talking_points": [
                    "Multi-tenant platform — each customer gets isolated environment",
                    "Role-based dashboards — CFO, Collector, Sales Rep each see different home screen",
                    "Arabic RTL support built in from day one",
                ],
                "api_calls": [
                    {"method": "POST", "path": "/api/v1/auth/login", "description": "Authenticate and get JWT token"},
                    {"method": "GET", "path": "/api/v1/executive/kpis", "description": "Executive KPI cards with sparklines"},
                    {"method": "GET", "path": "/api/v1/i18n/locales/ar/config", "description": "Arabic RTL configuration"},
                ],
            },
            {
                "name": "2. Executive Dashboard",
                "duration": "3 min",
                "talking_points": [
                    "Total AR outstanding, average DSO, collection rate at a glance",
                    "AI-generated executive summary updated daily",
                    "Click any KPI card to drill down",
                ],
                "api_calls": [
                    {"method": "GET", "path": "/api/v1/executive/kpis", "description": "7 KPI cards with trends"},
                    {"method": "GET", "path": "/api/v1/executive/summary", "description": "AI executive briefing"},
                    {"method": "GET", "path": "/api/v1/cfo/dso-trend", "description": "DSO trend chart"},
                    {"method": "GET", "path": "/api/v1/dashboard/ar-summary", "description": "Aging bucket breakdown"},
                ],
            },
            {
                "name": "3. Customer 360° Profile",
                "duration": "3 min",
                "talking_points": [
                    "Complete customer view — financials, risk, health score, activity timeline",
                    "AI health score combining payment behavior, engagement, order trends",
                    "Credit limit management with AI recommendations",
                ],
                "api_calls": [
                    {"method": "GET", "path": "/api/v1/customers/", "description": "Customer list with health badges"},
                    {"method": "GET", "path": "/api/v1/customers/{id}", "description": "Full 360 profile"},
                    {"method": "GET", "path": "/api/v1/intelligence/health-score/{id}", "description": "Composite health score"},
                    {"method": "GET", "path": "/api/v1/intelligence/credit/recommendations", "description": "AI credit limit suggestions"},
                ],
            },
            {
                "name": "4. AI Briefings",
                "duration": "2 min",
                "talking_points": [
                    "Claude-powered daily briefings for each role",
                    "Scheduled email delivery — CFO gets AR intelligence, collectors get worklist",
                    "Available in both English and Arabic",
                ],
                "api_calls": [
                    {"method": "GET", "path": "/api/v1/briefings/", "description": "Briefing list"},
                    {"method": "GET", "path": "/api/v1/briefings/latest", "description": "Today's briefing"},
                ],
            },
            {
                "name": "5. Collections Copilot",
                "duration": "3 min",
                "talking_points": [
                    "AI-prioritized worklist — scores every case by amount, risk, and prediction",
                    "One-click AI message drafting for collection emails/WhatsApp",
                    "Promise-to-pay tracking with auto-escalation",
                    "Full dispute management lifecycle",
                ],
                "api_calls": [
                    {"method": "GET", "path": "/api/v1/collections/", "description": "AI-prioritized collection activities"},
                    {"method": "POST", "path": "/api/v1/collections-copilot/draft", "description": "AI draft message"},
                    {"method": "GET", "path": "/api/v1/collections-copilot/ptp/dashboard", "description": "PTP tracking"},
                    {"method": "GET", "path": "/api/v1/collections-copilot/disputes/aging", "description": "Dispute aging"},
                ],
            },
            {
                "name": "6. AI Chat",
                "duration": "2 min",
                "talking_points": [
                    "Natural language questions — 'Who are my top overdue customers?'",
                    "Text-to-SQL with role-based data scoping",
                    "Streaming responses with data citations",
                ],
                "api_calls": [
                    {"method": "POST", "path": "/api/v1/intelligence/chat", "description": "Ask a question"},
                ],
            },
            {
                "name": "7. Sales Dashboard & Predictions",
                "duration": "2 min",
                "talking_points": [
                    "Churn risk watchlist — catch at-risk customers before they leave",
                    "Reorder prediction alerts — proactive sales motions",
                    "Revenue by segment with growth opportunities",
                ],
                "api_calls": [
                    {"method": "GET", "path": "/api/v1/sales/summary", "description": "Sales dashboard"},
                    {"method": "GET", "path": "/api/v1/sales/churn-watchlist", "description": "Churn risk list"},
                    {"method": "GET", "path": "/api/v1/sales/reorder-alerts", "description": "Reorder predictions"},
                ],
            },
            {
                "name": "8. Agent Hub & Admin",
                "duration": "2 min",
                "talking_points": [
                    "7 autonomous AI agents — visible, controllable, monitored",
                    "Agent dependency map showing data flow",
                    "Business rules configuration — scoring weights, thresholds",
                    "Full audit trail of every action",
                ],
                "api_calls": [
                    {"method": "GET", "path": "/api/v1/agent-hub/dashboard", "description": "Agent Hub overview"},
                    {"method": "GET", "path": "/api/v1/admin/agents/dependency-map", "description": "Agent graph"},
                    {"method": "GET", "path": "/api/v1/admin/business-rules", "description": "Business rules"},
                    {"method": "GET", "path": "/api/v1/admin/audit-logs", "description": "Audit trail"},
                ],
            },
            {
                "name": "9. Wrap-up & Next Steps",
                "duration": "1 min",
                "talking_points": [
                    "Phase 2: Live ERP/CRM connectors (D365 F&O, Salesforce)",
                    "Phase 2: Workflow builder, report builder, customer statement portal",
                    "Design partner program — early access, direct feedback loop",
                ],
                "api_calls": [],
            },
        ],
    }
