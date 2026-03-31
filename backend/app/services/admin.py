"""
Sales IQ - Admin Service
Day 18: User settings, role management, business rules, system monitor,
        audit log viewer, enhanced Agent Hub, Demo Data Manager presets.
"""

import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import AuditLog, User, UserRole
from app.models.business import (
    Customer, Invoice, Payment, Dispute, CollectionActivity,
    AgentRunLog, CreditLimitRequest,
)


def _safe_isoformat(value) -> str:
    """Return ISO format string whether value is datetime or already a string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)

# ═══════════════════════════════════════════════
# In-memory stores (MVP)
# ═══════════════════════════════════════════════

# user_id -> notification prefs
_notification_prefs: Dict[str, dict] = {}

# tenant_id -> business rules
_business_rules: Dict[str, dict] = {}

# Server start time for uptime
_server_start_time = time.time()

# Default business rules
DEFAULT_BUSINESS_RULES = {
    "ai_scoring_model": "xgboost_v1",
    "ai_prediction_enabled": True,
    "overdue_alert_days": 7,
    "credit_hold_threshold_pct": 90.0,
    "churn_alert_threshold": 0.3,
    "health_score_alert_grade": "D",
    "payment_weight": 0.40,
    "engagement_weight": 0.20,
    "order_trend_weight": 0.30,
    "risk_flag_weight": 0.10,
    "auto_escalation_enabled": True,
    "ptp_reminder_days_before": 1,
    "collection_frequency_days": 7,
}


# ═══════════════════════════════════════════════
# Demo Data Presets
# ═══════════════════════════════════════════════

DEMO_PRESETS = [
    {
        "preset_id": "gcc_fmcg",
        "name": "GCC FMCG Distributor",
        "description": "Fast-moving consumer goods distributor in the GCC region with high order frequency, moderate overdue, and diverse customer segments.",
        "erp_profile": "d365_fo",
        "dataset_size": "medium",
        "parameters": {
            "customer_count": 25,
            "industry": "FMCG",
            "revenue_range": "500K-5M AED",
            "overdue_pct": 35,
            "target_dso": 45,
            "regions": ["UAE", "KSA", "Qatar", "Bahrain"],
        },
    },
    {
        "preset_id": "manufacturing",
        "name": "Manufacturing Enterprise",
        "description": "Large manufacturing firm with fewer but bigger accounts, long payment terms, and higher credit exposure.",
        "erp_profile": "sap_b1",
        "dataset_size": "large",
        "parameters": {
            "customer_count": 15,
            "industry": "Manufacturing",
            "revenue_range": "2M-20M AED",
            "overdue_pct": 50,
            "target_dso": 75,
            "regions": ["UAE", "Oman", "KSA"],
        },
    },
    {
        "preset_id": "multi_entity",
        "name": "Multi-Entity Trading Group",
        "description": "Trading conglomerate with multiple entities, cross-company invoicing, and complex reconciliation needs.",
        "erp_profile": "d365_fo",
        "dataset_size": "large",
        "parameters": {
            "customer_count": 40,
            "industry": "Trading",
            "revenue_range": "100K-10M AED",
            "overdue_pct": 40,
            "target_dso": 60,
            "regions": ["UAE", "KSA", "Kuwait", "Jordan", "Egypt"],
        },
    },
]


# ═══════════════════════════════════════════════
# Agent Dependency Map
# ═══════════════════════════════════════════════

AGENT_DEPENDENCY_MAP = {
    "agents": [
        "data_quality", "briefing_agent", "prediction_agent",
        "collections_agent", "matching_agent", "ocr_agent", "chat_agent",
    ],
    "links": [
        {"source_agent": "data_quality", "target_agent": "prediction_agent", "relationship": "feeds_data"},
        {"source_agent": "data_quality", "target_agent": "matching_agent", "relationship": "feeds_data"},
        {"source_agent": "ocr_agent", "target_agent": "data_quality", "relationship": "feeds_data"},
        {"source_agent": "prediction_agent", "target_agent": "briefing_agent", "relationship": "enriches"},
        {"source_agent": "prediction_agent", "target_agent": "collections_agent", "relationship": "triggers"},
        {"source_agent": "matching_agent", "target_agent": "collections_agent", "relationship": "feeds_data"},
        {"source_agent": "briefing_agent", "target_agent": "chat_agent", "relationship": "enriches"},
        {"source_agent": "collections_agent", "target_agent": "briefing_agent", "relationship": "enriches"},
    ],
    "description": "Agent dependency graph showing data flow: OCR feeds Data Quality, which feeds Prediction and Matching. Prediction triggers Collections and enriches Briefing. Matching feeds Collections. Briefing and Collections enrich the Chat Agent for context-aware responses.",
}


class AdminService:
    """Admin panel: user settings, roles, business rules, system health, audit log."""

    # ═══════════════════════════════════════════
    # USER SETTINGS
    # ═══════════════════════════════════════════

    async def get_user_settings(self, db: AsyncSession, user: Any) -> dict:
        """Get current user's profile and preferences."""
        prefs = _notification_prefs.get(str(user.id), {
            "email_enabled": True, "in_app_enabled": True,
            "daily_briefing": True, "overdue_alerts": True,
            "dispute_updates": True, "credit_hold_alerts": True,
            "agent_failure_alerts": False,
        })

        user_prefs = user.preferences or {} if hasattr(user, "preferences") else {}

        return {
            "user_id": str(user.id),
            "full_name": user.full_name or "",
            "email": user.email,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "phone": user.phone,
            "avatar_url": user.avatar_url,
            "timezone": user_prefs.get("timezone", "Asia/Dubai"),
            "language": user_prefs.get("language", "en"),
            "notification_preferences": prefs,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def update_user_profile(self, db: AsyncSession, user: Any, updates: dict) -> dict:
        """Update user profile fields."""
        if updates.get("full_name"):
            user.full_name = updates["full_name"]
        if updates.get("phone") is not None:
            user.phone = updates["phone"]
        if updates.get("avatar_url") is not None:
            user.avatar_url = updates["avatar_url"]

        # Store timezone/language in preferences
        prefs = user.preferences or {}
        if updates.get("timezone"):
            prefs["timezone"] = updates["timezone"]
        if updates.get("language"):
            prefs["language"] = updates["language"]
        user.preferences = prefs

        await db.commit()
        return await self.get_user_settings(db, user)

    def update_notification_preferences(self, user_id: UUID, prefs: dict) -> dict:
        """Save notification preferences."""
        _notification_prefs[str(user_id)] = prefs
        return prefs

    # ═══════════════════════════════════════════
    # ADMIN USER MANAGEMENT
    # ═══════════════════════════════════════════

    async def list_users(
        self, db: AsyncSession, tenant_id: UUID, page: int = 1, page_size: int = 20,
    ) -> dict:
        """List all users for the tenant."""
        total_q = await db.execute(
            select(func.count()).where(User.tenant_id == tenant_id)
        )
        total = total_q.scalar() or 0

        users_q = await db.execute(
            select(User).where(User.tenant_id == tenant_id)
            .order_by(User.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )
        users = users_q.scalars().all()

        items = []
        for u in users:
            items.append({
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role.value if hasattr(u.role, "value") else str(u.role),
                "is_active": u.is_active,
                "last_login_at": _safe_isoformat(u.last_login_at) or None,
                "territory_ids": u.territory_ids or [],
                "created_at": _safe_isoformat(u.created_at),
            })

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    async def invite_user(self, db: AsyncSession, tenant_id: UUID, admin_id: UUID, data: dict) -> dict:
        """Create (invite) a new user."""
        from app.core.security import hash_password

        existing = await db.execute(
            select(User).where(User.email == data["email"], User.tenant_id == tenant_id)
        )
        if existing.scalar():
            return {"error": "User with this email already exists"}

        role_value = data.get("role", "viewer")
        try:
            role = UserRole(role_value)
        except ValueError:
            role = UserRole.VIEWER

        new_user = User(
            tenant_id=tenant_id,
            email=data["email"],
            full_name=data["full_name"],
            hashed_password=hash_password("Welcome@2024"),  # temp password
            role=role,
            is_active=True,
            territory_ids=data.get("territory_ids"),
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        return {
            "id": str(new_user.id),
            "email": new_user.email,
            "full_name": new_user.full_name,
            "role": role_value,
            "is_active": True,
            "last_login_at": None,
            "territory_ids": data.get("territory_ids"),
            "created_at": _safe_isoformat(new_user.created_at),
        }

    async def update_user_role(self, db: AsyncSession, tenant_id: UUID, user_id: UUID, data: dict) -> dict:
        """Update a user's role and territory assignments."""
        user = (await db.execute(
            select(User).where(User.id == user_id, User.tenant_id == tenant_id)
        )).scalar()
        if not user:
            return {"error": "User not found"}

        try:
            user.role = UserRole(data["role"])
        except ValueError:
            return {"error": f"Invalid role: {data['role']}"}

        if "territory_ids" in data and data["territory_ids"] is not None:
            # territory_ids column is UUID[]; validate and convert
            valid_ids = []
            for tid in data["territory_ids"]:
                try:
                    valid_ids.append(UUID(str(tid)) if not isinstance(tid, UUID) else tid)
                except (ValueError, AttributeError):
                    pass  # skip non-UUID territory ids
            user.territory_ids = valid_ids if valid_ids else None

        await db.commit()
        return {
            "id": str(user.id), "email": user.email, "full_name": user.full_name,
            "role": data["role"], "is_active": user.is_active,
            "last_login_at": _safe_isoformat(user.last_login_at) or None,
            "territory_ids": [str(t) for t in user.territory_ids] if user.territory_ids else [],
            "created_at": _safe_isoformat(user.created_at),
        }

    async def deactivate_user(self, db: AsyncSession, tenant_id: UUID, user_id: UUID) -> dict:
        """Deactivate a user account."""
        user = (await db.execute(
            select(User).where(User.id == user_id, User.tenant_id == tenant_id)
        )).scalar()
        if not user:
            return {"error": "User not found"}

        user.is_active = False
        await db.commit()
        return {"id": str(user.id), "is_active": False, "message": "User deactivated"}

    # ═══════════════════════════════════════════
    # BUSINESS RULES
    # ═══════════════════════════════════════════

    def get_business_rules(self, tenant_id: UUID) -> dict:
        """Get current business rules configuration."""
        config = _business_rules.get(str(tenant_id), DEFAULT_BUSINESS_RULES.copy())
        return {
            "config": config,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": None,
        }

    def update_business_rules(self, tenant_id: UUID, updates: dict, user_email: str) -> dict:
        """Update business rules."""
        key = str(tenant_id)
        if key not in _business_rules:
            _business_rules[key] = DEFAULT_BUSINESS_RULES.copy()

        for k, v in updates.items():
            if k in DEFAULT_BUSINESS_RULES and v is not None:
                _business_rules[key][k] = v

        return {
            "config": _business_rules[key],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": user_email,
        }

    # ═══════════════════════════════════════════
    # SYSTEM MONITOR
    # ═══════════════════════════════════════════

    async def get_system_health(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """System health and monitoring overview."""
        now = datetime.now(timezone.utc)
        day_ago = now - timedelta(hours=24)

        uptime = int(time.time() - _server_start_time)

        # API call proxy: count audit log entries in 24h
        api_calls_q = await db.execute(
            select(func.count()).where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.created_at >= day_ago,
            )
        )
        api_calls = api_calls_q.scalar() or 0

        # Agent run errors in 24h
        errors_q = await db.execute(
            select(func.count()).select_from(AgentRunLog).where(
                AgentRunLog.tenant_id == tenant_id,
                AgentRunLog.started_at >= day_ago.isoformat(),
                AgentRunLog.status == "failed",
            )
        )
        errors_24h = errors_q.scalar() or 0

        total_runs_q = await db.execute(
            select(func.count()).select_from(AgentRunLog).where(
                AgentRunLog.tenant_id == tenant_id,
                AgentRunLog.started_at >= day_ago.isoformat(),
            )
        )
        total_runs = total_runs_q.scalar() or 0
        error_rate = (errors_24h / total_runs * 100) if total_runs > 0 else 0

        # Recent errors
        recent_errors_q = await db.execute(
            select(AgentRunLog).where(
                AgentRunLog.tenant_id == tenant_id,
                AgentRunLog.status == "failed",
            ).order_by(AgentRunLog.created_at.desc()).limit(5)
        )
        recent_errors = [
            {"agent": e.agent_name, "error": (e.error_message or "")[:150], "at": e.started_at}
            for e in recent_errors_q.scalars().all()
        ]

        # Background jobs (agent run status summary)
        from app.services.agent_registry import AGENT_REGISTRY, _agent_state, _get_agent_state
        bg_jobs = []
        for name in AGENT_REGISTRY:
            state = _get_agent_state(name)
            bg_jobs.append({
                "name": name,
                "status": state["status"],
                "scheduled": state["schedule_cron"] is not None,
            })

        return {
            "api_status": "healthy" if error_rate < 10 else "degraded" if error_rate < 50 else "down",
            "database_status": "healthy",
            "cache_status": "healthy",
            "uptime_seconds": uptime,
            "api_calls_24h": api_calls,
            "avg_response_ms": 45.0,  # Would need real metrics middleware
            "error_rate_24h": round(error_rate, 1),
            "active_connections": 1,
            "background_jobs": bg_jobs,
            "recent_errors": recent_errors,
        }

    # ═══════════════════════════════════════════
    # AUDIT LOG VIEWER
    # ═══════════════════════════════════════════

    async def get_audit_logs(
        self, db: AsyncSession, tenant_id: UUID,
        action: Optional[str] = None,
        entity_type: Optional[str] = None,
        user_email: Optional[str] = None,
        page: int = 1, page_size: int = 20,
    ) -> dict:
        """Searchable, filterable audit log viewer."""
        query = select(AuditLog).where(AuditLog.tenant_id == tenant_id)

        if action:
            query = query.where(AuditLog.action == action)
        if entity_type:
            query = query.where(AuditLog.entity_type == entity_type)
        if user_email:
            query = query.where(AuditLog.user_email.ilike(f"%{user_email}%"))

        count_q = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_q)).scalar() or 0

        query = query.order_by(AuditLog.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        logs = result.scalars().all()

        items = []
        for log in logs:
            items.append({
                "id": str(log.id),
                "user_id": str(log.user_id) if log.user_id else None,
                "user_email": log.user_email,
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": str(log.entity_id) if log.entity_id else None,
                "before_state": log.before_state,
                "after_state": log.after_state,
                "ip_address": log.ip_address,
                "created_at": _safe_isoformat(log.created_at),
            })

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    # ═══════════════════════════════════════════
    # AGENT HUB ENHANCEMENTS
    # ═══════════════════════════════════════════

    def get_agent_dependency_map(self) -> dict:
        """Return the agent dependency/interaction graph."""
        return AGENT_DEPENDENCY_MAP

    async def get_agent_performance_history(
        self, db: AsyncSession, tenant_id: UUID, agent_name: str, days: int = 30,
    ) -> dict:
        """Historical performance chart data for a specific agent."""
        from app.services.agent_registry import AGENT_REGISTRY
        defn = AGENT_REGISTRY.get(agent_name, {})
        now = datetime.now(timezone.utc)

        data_points = []
        total_records = 0

        for d in range(days - 1, -1, -1):
            day_date = (now - timedelta(days=d)).strftime("%Y-%m-%d")
            day_start = (now - timedelta(days=d)).replace(hour=0, minute=0, second=0).isoformat()
            day_end = (now - timedelta(days=d)).replace(hour=23, minute=59, second=59).isoformat()

            total_q = await db.execute(
                select(func.count()).select_from(AgentRunLog).where(
                    AgentRunLog.tenant_id == tenant_id,
                    AgentRunLog.agent_name == agent_name,
                    AgentRunLog.started_at >= day_start,
                    AgentRunLog.started_at <= day_end,
                )
            )
            total = total_q.scalar() or 0

            ok_q = await db.execute(
                select(func.count()).select_from(AgentRunLog).where(
                    AgentRunLog.tenant_id == tenant_id,
                    AgentRunLog.agent_name == agent_name,
                    AgentRunLog.started_at >= day_start,
                    AgentRunLog.started_at <= day_end,
                    AgentRunLog.status == "completed",
                )
            )
            ok = ok_q.scalar() or 0

            avg_dur_q = await db.execute(
                select(func.coalesce(func.avg(AgentRunLog.duration_ms), 0)).where(
                    AgentRunLog.tenant_id == tenant_id,
                    AgentRunLog.agent_name == agent_name,
                    AgentRunLog.started_at >= day_start,
                    AgentRunLog.started_at <= day_end,
                )
            )
            avg_dur = float(avg_dur_q.scalar() or 0)

            rec_q = await db.execute(
                select(func.coalesce(func.sum(AgentRunLog.records_processed), 0)).where(
                    AgentRunLog.tenant_id == tenant_id,
                    AgentRunLog.agent_name == agent_name,
                    AgentRunLog.started_at >= day_start,
                    AgentRunLog.started_at <= day_end,
                )
            )
            records = int(rec_q.scalar() or 0)
            total_records += records

            data_points.append({
                "date": day_date,
                "total_runs": total,
                "successful": ok,
                "failed": total - ok,
                "avg_duration_ms": round(avg_dur, 1),
            })

        # Overall success rate
        all_total = sum(p["total_runs"] for p in data_points)
        all_ok = sum(p["successful"] for p in data_points)
        overall_rate = (all_ok / all_total * 100) if all_total > 0 else 100.0

        return {
            "agent_name": agent_name,
            "display_name": defn.get("display_name", agent_name),
            "period_days": days,
            "data_points": data_points,
            "overall_success_rate": round(overall_rate, 1),
            "total_records_processed": total_records,
        }

    # ═══════════════════════════════════════════
    # DEMO DATA MANAGER ENHANCEMENTS
    # ═══════════════════════════════════════════

    def get_demo_presets(self) -> dict:
        """Return available demo data preset templates."""
        return {"presets": DEMO_PRESETS, "total": len(DEMO_PRESETS)}

    def get_preset_by_id(self, preset_id: str) -> Optional[dict]:
        """Get a specific preset."""
        for p in DEMO_PRESETS:
            if p["preset_id"] == preset_id:
                return p
        return None

    async def get_demo_data_summary(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """Summary of current demo data record counts."""
        customers = (await db.execute(
            select(func.count()).where(Customer.tenant_id == tenant_id)
        )).scalar() or 0

        invoices = (await db.execute(
            select(func.count()).where(Invoice.tenant_id == tenant_id)
        )).scalar() or 0

        payments = (await db.execute(
            select(func.count()).where(Payment.tenant_id == tenant_id)
        )).scalar() or 0

        disputes = (await db.execute(
            select(func.count()).where(Dispute.tenant_id == tenant_id)
        )).scalar() or 0

        collections = (await db.execute(
            select(func.count()).where(CollectionActivity.tenant_id == tenant_id)
        )).scalar() or 0

        credits = (await db.execute(
            select(func.count()).where(CreditLimitRequest.tenant_id == tenant_id)
        )).scalar() or 0

        agent_runs = (await db.execute(
            select(func.count()).select_from(AgentRunLog).where(AgentRunLog.tenant_id == tenant_id)
        )).scalar() or 0

        audits = (await db.execute(
            select(func.count()).where(AuditLog.tenant_id == tenant_id)
        )).scalar() or 0

        total = customers + invoices + payments + disputes + collections + credits + agent_runs + audits

        return {
            "customers": customers,
            "invoices": invoices,
            "payments": payments,
            "disputes": disputes,
            "collection_activities": collections,
            "credit_requests": credits,
            "agent_runs": agent_runs,
            "audit_logs": audits,
            "total_records": total,
            "erp_profile": "d365_fo",
            "last_generated_at": None,
        }


# Singleton
admin_service = AdminService()
