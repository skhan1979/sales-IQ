"""
Sales IQ - Database Seed Script
Creates default tenant and admin user for development.
Run: python -m app.core.seed
"""

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.core import Tenant, User, UserRole, TenantStatus


# Default demo tenant
DEMO_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEMO_ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")


async def seed_database():
    """Seed the database with a default tenant and admin user."""
    async with AsyncSessionLocal() as db:
        async with db.begin():
            # Check if tenant already exists
            result = await db.execute(select(Tenant).where(Tenant.id == DEMO_TENANT_ID))
            existing_tenant = result.scalar_one_or_none()

            if existing_tenant:
                print("[SEED] Demo tenant already exists, skipping seed.")
                return

            # Create demo tenant
            tenant = Tenant(
                id=DEMO_TENANT_ID,
                name="Sales IQ Demo",
                slug="demo",
                domain="salesiq.ai",
                status=TenantStatus.ACTIVE,
                timezone="Asia/Dubai",
                default_currency="AED",
                locale="en",
                max_users=50,
                subscription_tier="enterprise",
                primary_color="#1E40AF",
                settings={
                    "briefing_time": "06:00",
                    "credit_hold_threshold": 90,
                    "auto_provision_sso": True,
                    "default_payment_terms": 30,
                },
            )
            db.add(tenant)
            print("[SEED] Created demo tenant: Sales IQ Demo (slug: demo)")

            # Create admin user
            admin = User(
                id=DEMO_ADMIN_ID,
                tenant_id=DEMO_TENANT_ID,
                email="admin@salesiq.ai",
                hashed_password=hash_password("Admin@2024"),
                full_name="System Administrator",
                role=UserRole.TENANT_ADMIN,
                is_active=True,
                is_sso=False,
                preferences={
                    "language": "en",
                    "theme": "light",
                    "home_widgets": ["ar_summary", "aging_chart", "top_overdue", "collection_tasks"],
                },
            )
            db.add(admin)
            print("[SEED] Created admin user: admin@salesiq.ai (password: Admin@2024)")

            # Create CFO user
            cfo = User(
                tenant_id=DEMO_TENANT_ID,
                email="cfo@salesiq.ai",
                hashed_password=hash_password("Cfo@2024!"),
                full_name="Mohammed Al-Rashid",
                role=UserRole.CFO,
                is_active=True,
                preferences={
                    "language": "en",
                    "home_widgets": ["executive_summary", "dso_trend", "risk_heatmap", "revenue_forecast"],
                },
            )
            db.add(cfo)
            print("[SEED] Created CFO user: cfo@salesiq.ai")

            # Create Collector user
            collector = User(
                tenant_id=DEMO_TENANT_ID,
                email="collector@salesiq.ai",
                hashed_password=hash_password("Collect@2024"),
                full_name="Sara Ahmed",
                role=UserRole.COLLECTOR,
                is_active=True,
                preferences={
                    "language": "en",
                    "home_widgets": ["my_tasks", "promises_due", "aging_buckets", "recent_payments"],
                },
            )
            db.add(collector)
            print("[SEED] Created Collector user: collector@salesiq.ai")

            # Create Sales Rep user
            sales_rep = User(
                tenant_id=DEMO_TENANT_ID,
                email="sales@salesiq.ai",
                hashed_password=hash_password("Sales@2024!"),
                full_name="Omar Hassan",
                role=UserRole.SALES_REP,
                is_active=True,
                preferences={
                    "language": "en",
                    "home_widgets": ["my_customers", "open_invoices", "credit_alerts", "disputes"],
                },
            )
            db.add(sales_rep)
            print("[SEED] Created Sales Rep user: sales@salesiq.ai")

        print("[SEED] Database seeded successfully!")
        print("")
        print("  Login credentials:")
        print("  ------------------------------------------")
        print("  Admin:     admin@salesiq.ai / Admin@2024")
        print("  CFO:       cfo@salesiq.ai / Cfo@2024!")
        print("  Collector: collector@salesiq.ai / Collect@2024")
        print("  Sales Rep: sales@salesiq.ai / Sales@2024!")
        print("  ------------------------------------------")
        print("  Tenant slug: demo")


if __name__ == "__main__":
    asyncio.run(seed_database())
