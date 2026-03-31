"""
Day 20 — Performance Indexes

Add composite indexes for the most common query patterns used by
dashboards, worklists, aging engines, and the agent hub.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "c3f7a1d20e01"
down_revision = "82bd4b8954e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Invoices: aging, date range, customer+status ──
    op.create_index(
        "ix_invoice_tenant_cust_status",
        "invoices", ["tenant_id", "customer_id", "status"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_invoice_tenant_inv_date",
        "invoices", ["tenant_id", "invoice_date"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_invoice_tenant_aging",
        "invoices", ["tenant_id", "aging_bucket", "amount_remaining"],
        if_not_exists=True,
    )

    # ── Payments: customer + date for payment history ──
    op.create_index(
        "ix_payment_tenant_cust_date",
        "payments", ["tenant_id", "customer_id", "payment_date"],
        if_not_exists=True,
    )

    # ── Customers: risk, territory, churn filters ──
    op.create_index(
        "ix_customer_tenant_risk",
        "customers", ["tenant_id", "risk_score"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_customer_tenant_territory",
        "customers", ["tenant_id", "territory"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_customer_tenant_churn",
        "customers", ["tenant_id", "churn_probability"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_customer_tenant_segment",
        "customers", ["tenant_id", "segment"],
        if_not_exists=True,
    )

    # ── Collection Activities: date range queries ──
    op.create_index(
        "ix_collection_tenant_date",
        "collection_activities", ["tenant_id", "action_date"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_collection_tenant_ptp",
        "collection_activities", ["tenant_id", "ptp_date"],
        if_not_exists=True,
    )

    # ── Disputes: date range for aging reports ──
    op.create_index(
        "ix_dispute_tenant_created",
        "disputes", ["tenant_id", "created_at"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_dispute_tenant_sla",
        "disputes", ["tenant_id", "sla_due_date", "sla_breached"],
        if_not_exists=True,
    )

    # ── Agent Run Logs: dashboard status queries ──
    op.create_index(
        "ix_agent_run_tenant_agent_status",
        "agent_run_logs", ["tenant_id", "agent_name", "status"],
        if_not_exists=True,
    )

    # ── Briefings: user lookup ──
    op.create_index(
        "ix_briefing_tenant_recipient",
        "briefings", ["tenant_id", "recipient_id"],
        if_not_exists=True,
    )

    # ── Write-offs: approval status ──
    op.create_index(
        "ix_writeoff_tenant_status",
        "write_offs", ["tenant_id", "approval_status"],
        if_not_exists=True,
    )

    # ── Credit Limit Requests: customer lookup ──
    op.create_index(
        "ix_credit_req_tenant_customer",
        "credit_limit_requests", ["tenant_id", "customer_id"],
        if_not_exists=True,
    )

    # ── Audit Logs: action filter ──
    op.create_index(
        "ix_audit_tenant_action",
        "audit_logs", ["tenant_id", "action"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_tenant_action", table_name="audit_logs")
    op.drop_index("ix_credit_req_tenant_customer", table_name="credit_limit_requests")
    op.drop_index("ix_writeoff_tenant_status", table_name="write_offs")
    op.drop_index("ix_briefing_tenant_recipient", table_name="briefings")
    op.drop_index("ix_agent_run_tenant_agent_status", table_name="agent_run_logs")
    op.drop_index("ix_dispute_tenant_sla", table_name="disputes")
    op.drop_index("ix_dispute_tenant_created", table_name="disputes")
    op.drop_index("ix_collection_tenant_ptp", table_name="collection_activities")
    op.drop_index("ix_collection_tenant_date", table_name="collection_activities")
    op.drop_index("ix_customer_tenant_segment", table_name="customers")
    op.drop_index("ix_customer_tenant_churn", table_name="customers")
    op.drop_index("ix_customer_tenant_territory", table_name="customers")
    op.drop_index("ix_customer_tenant_risk", table_name="customers")
    op.drop_index("ix_payment_tenant_cust_date", table_name="payments")
    op.drop_index("ix_invoice_tenant_aging", table_name="invoices")
    op.drop_index("ix_invoice_tenant_inv_date", table_name="invoices")
    op.drop_index("ix_invoice_tenant_cust_status", table_name="invoices")
