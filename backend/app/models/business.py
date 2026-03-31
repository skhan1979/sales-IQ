"""
Sales IQ - Business Domain Models
Customer, Invoice, Payment, Credit, Dispute, and related entities.
"""

from sqlalchemy import (
    Column, String, Boolean, Integer, Float, Text, Date, ForeignKey,
    Enum as SQLEnum, UniqueConstraint, Index, text, Numeric,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
import enum

from app.models.base import AuditableModel, TenantBaseModel


# =============================================
# Enums
# =============================================

class CustomerStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"
    CREDIT_HOLD = "credit_hold"
    PROSPECT = "prospect"


class InvoiceStatus(str, enum.Enum):
    OPEN = "open"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    DISPUTED = "disputed"
    WRITTEN_OFF = "written_off"
    CREDIT_NOTE = "credit_note"


class PaymentMethod(str, enum.Enum):
    BANK_TRANSFER = "bank_transfer"
    CHECK = "check"
    CASH = "cash"
    CREDIT_CARD = "credit_card"
    ONLINE = "online"
    OTHER = "other"


class DisputeStatus(str, enum.Enum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    REJECTED = "rejected"
    CREDIT_ISSUED = "credit_issued"


class DisputeReason(str, enum.Enum):
    PRICING = "pricing"
    QUANTITY = "quantity"
    QUALITY = "quality"
    DELIVERY = "delivery"
    DUPLICATE = "duplicate"
    WRONG_PRODUCT = "wrong_product"
    DAMAGED = "damaged"
    NOT_RECEIVED = "not_received"
    TERMS = "terms"
    OTHER = "other"


class CreditApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"


class ECLStage(str, enum.Enum):
    """IFRS 9 Expected Credit Loss stages."""
    STAGE_1 = "stage_1"  # Performing (12-month ECL)
    STAGE_2 = "stage_2"  # Underperforming (lifetime ECL)
    STAGE_3 = "stage_3"  # Non-performing (lifetime ECL, credit-impaired)


class CollectionAction(str, enum.Enum):
    EMAIL_REMINDER = "email_reminder"
    SMS_REMINDER = "sms_reminder"
    PHONE_CALL = "phone_call"
    ESCALATION = "escalation"
    PROMISE_TO_PAY = "promise_to_pay"
    LEGAL_NOTICE = "legal_notice"
    WRITE_OFF_REQUEST = "write_off_request"


class DataQualityStatus(str, enum.Enum):
    CLEAN = "clean"
    WARNING = "warning"
    QUARANTINED = "quarantined"
    ENRICHED = "enriched"


# =============================================
# Customer
# =============================================

class Customer(AuditableModel):
    """Master customer record — enriched from ERP/CRM."""
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_id", "source_system", name="uq_customer_external"),
        Index("ix_customer_tenant_status", "tenant_id", "status"),
        Index("ix_customer_tenant_name", "tenant_id", "name"),
    )

    external_id = Column(String(255), nullable=True)
    source_system = Column(String(50), nullable=True)
    name = Column(String(500), nullable=False)
    name_ar = Column(String(500), nullable=True)  # Arabic name
    trade_name = Column(String(500), nullable=True)
    tax_id = Column(String(50), nullable=True)
    status = Column(SQLEnum(CustomerStatus), default=CustomerStatus.ACTIVE, nullable=False)
    industry = Column(String(100), nullable=True)
    segment = Column(String(100), nullable=True)
    territory = Column(String(100), nullable=True)
    region = Column(String(100), nullable=True)
    country = Column(String(3), default="AE")
    city = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    website = Column(String(255), nullable=True)

    # Financial
    currency = Column(String(3), default="AED")
    payment_terms_days = Column(Integer, default=30)
    credit_limit = Column(Numeric(15, 2), default=0)
    credit_limit_currency = Column(String(3), default="AED")
    credit_utilization = Column(Numeric(15, 2), default=0)
    credit_hold = Column(Boolean, default=False)
    credit_hold_threshold = Column(Float, default=90.0)  # % utilization to auto-hold

    # Risk & Intelligence
    risk_score = Column(Float, nullable=True)  # 0-100
    churn_probability = Column(Float, nullable=True)  # 0-1
    predicted_dso = Column(Float, nullable=True)
    ecl_stage = Column(SQLEnum(ECLStage), default=ECLStage.STAGE_1)
    ecl_provision_amount = Column(Numeric(15, 2), default=0)

    # Sales rep assignment
    assigned_collector_id = Column(UUID(as_uuid=True), nullable=True)
    assigned_sales_rep_id = Column(UUID(as_uuid=True), nullable=True)

    # Data quality
    data_quality_score = Column(Float, default=100.0)
    data_quality_issues = Column(JSONB, default=list)

    # Metadata
    tags = Column(ARRAY(String), default=list)
    custom_fields = Column(JSONB, default=dict)
    last_synced_at = Column(String(50), nullable=True)

    # Relationships
    invoices = relationship("Invoice", back_populates="customer", lazy="selectin")
    payments = relationship("Payment", back_populates="customer", lazy="selectin")
    disputes = relationship("Dispute", back_populates="customer", lazy="selectin")
    credit_requests = relationship("CreditLimitRequest", back_populates="customer", lazy="selectin")
    collection_activities = relationship("CollectionActivity", back_populates="customer", lazy="selectin")


# =============================================
# Invoice
# =============================================

class Invoice(AuditableModel):
    """Accounts receivable invoice record."""
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_number", name="uq_invoice_number"),
        Index("ix_invoice_tenant_status", "tenant_id", "status"),
        Index("ix_invoice_tenant_due", "tenant_id", "due_date"),
        Index("ix_invoice_customer", "tenant_id", "customer_id"),
    )

    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    invoice_number = Column(String(100), nullable=False)
    external_id = Column(String(255), nullable=True)
    source_system = Column(String(50), nullable=True)
    po_number = Column(String(100), nullable=True)

    # Dates
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    posting_date = Column(Date, nullable=True)

    # Amounts
    currency = Column(String(3), default="AED")
    amount = Column(Numeric(15, 2), nullable=False)
    amount_paid = Column(Numeric(15, 2), default=0)
    amount_remaining = Column(Numeric(15, 2), nullable=False)
    tax_amount = Column(Numeric(15, 2), default=0)
    discount_amount = Column(Numeric(15, 2), default=0)

    # Status
    status = Column(SQLEnum(InvoiceStatus), default=InvoiceStatus.OPEN, nullable=False)
    days_overdue = Column(Integer, default=0)
    aging_bucket = Column(String(20), nullable=True)  # current, 1-30, 31-60, 61-90, 90+

    # Intelligence
    predicted_pay_date = Column(Date, nullable=True)
    payment_probability = Column(Float, nullable=True)

    # Line items stored as JSONB for flexibility across ERPs
    line_items = Column(JSONB, default=list)
    notes = Column(Text, nullable=True)

    # OCR source reference
    ocr_document_id = Column(UUID(as_uuid=True), nullable=True)
    ocr_confidence = Column(Float, nullable=True)

    # Relationships
    customer = relationship("Customer", back_populates="invoices")
    payments = relationship("Payment", back_populates="invoice", lazy="selectin")


# =============================================
# Payment
# =============================================

class Payment(AuditableModel):
    """Payment receipt / transaction record."""
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payment_tenant_date", "tenant_id", "payment_date"),
        Index("ix_payment_customer", "tenant_id", "customer_id"),
    )

    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True)
    external_id = Column(String(255), nullable=True)
    source_system = Column(String(50), nullable=True)

    payment_date = Column(Date, nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="AED")
    payment_method = Column(SQLEnum(PaymentMethod), nullable=True)
    reference_number = Column(String(100), nullable=True)
    bank_reference = Column(String(100), nullable=True)

    # Matching
    is_matched = Column(Boolean, default=False)
    matched_at = Column(String(50), nullable=True)
    match_confidence = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)

    # Relationships
    customer = relationship("Customer", back_populates="payments")
    invoice = relationship("Invoice", back_populates="payments")


# =============================================
# Dispute
# =============================================

class Dispute(AuditableModel):
    """Customer dispute / deduction workflow."""
    __tablename__ = "disputes"
    __table_args__ = (
        Index("ix_dispute_tenant_status", "tenant_id", "status"),
        Index("ix_dispute_customer", "tenant_id", "customer_id"),
    )

    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True)
    dispute_number = Column(String(100), nullable=False)
    reason = Column(SQLEnum(DisputeReason), nullable=False)
    reason_detail = Column(Text, nullable=True)
    status = Column(SQLEnum(DisputeStatus), default=DisputeStatus.OPEN, nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="AED")

    assigned_department = Column(String(100), nullable=True)
    assigned_to_id = Column(UUID(as_uuid=True), nullable=True)
    escalated_to_id = Column(UUID(as_uuid=True), nullable=True)
    priority = Column(String(20), default="medium")

    # Resolution
    resolution_type = Column(String(50), nullable=True)  # credit_note, adjustment, rejected
    resolution_amount = Column(Numeric(15, 2), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    resolved_at = Column(String(50), nullable=True)
    resolved_by_id = Column(UUID(as_uuid=True), nullable=True)

    # SLA
    sla_due_date = Column(Date, nullable=True)
    sla_breached = Column(Boolean, default=False)

    # Attachments stored as references to MinIO
    attachments = Column(JSONB, default=list)

    # Relationships
    customer = relationship("Customer", back_populates="disputes")


# =============================================
# Credit Limit Request
# =============================================

class CreditLimitRequest(AuditableModel):
    """Credit limit change request with approval workflow."""
    __tablename__ = "credit_limit_requests"
    __table_args__ = (
        Index("ix_credit_req_tenant_status", "tenant_id", "approval_status"),
    )

    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    requested_by_id = Column(UUID(as_uuid=True), nullable=False)

    current_limit = Column(Numeric(15, 2), nullable=False)
    requested_limit = Column(Numeric(15, 2), nullable=False)
    ai_recommended_limit = Column(Numeric(15, 2), nullable=True)
    currency = Column(String(3), default="AED")

    justification = Column(Text, nullable=True)
    ai_risk_assessment = Column(JSONB, default=dict)  # AI-generated risk factors

    approval_status = Column(SQLEnum(CreditApprovalStatus), default=CreditApprovalStatus.PENDING)
    approved_by_id = Column(UUID(as_uuid=True), nullable=True)
    approved_limit = Column(Numeric(15, 2), nullable=True)
    approval_notes = Column(Text, nullable=True)
    approved_at = Column(String(50), nullable=True)

    # Relationships
    customer = relationship("Customer", back_populates="credit_requests")


# =============================================
# Collection Activity
# =============================================

class CollectionActivity(AuditableModel):
    """Collection action log — calls, emails, promises to pay."""
    __tablename__ = "collection_activities"
    __table_args__ = (
        Index("ix_collection_tenant_customer", "tenant_id", "customer_id"),
    )

    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True)
    collector_id = Column(UUID(as_uuid=True), nullable=True)

    action_type = Column(SQLEnum(CollectionAction), nullable=False)
    action_date = Column(Date, nullable=False)
    notes = Column(Text, nullable=True)

    # Promise to Pay
    ptp_date = Column(Date, nullable=True)
    ptp_amount = Column(Numeric(15, 2), nullable=True)
    ptp_fulfilled = Column(Boolean, nullable=True)

    # AI-generated suggestion
    is_ai_suggested = Column(Boolean, default=False)
    ai_priority_score = Column(Float, nullable=True)

    # Relationships
    customer = relationship("Customer", back_populates="collection_activities")


# =============================================
# Briefing
# =============================================

class Briefing(TenantBaseModel):
    """AI-generated daily briefing for executives."""
    __tablename__ = "briefings"
    __table_args__ = (
        Index("ix_briefing_tenant_date", "tenant_id", "briefing_date"),
    )

    briefing_date = Column(Date, nullable=False)
    recipient_id = Column(UUID(as_uuid=True), nullable=False)
    recipient_role = Column(String(50), nullable=False)

    # Content
    title = Column(String(500), nullable=False)
    executive_summary = Column(Text, nullable=False)
    sections = Column(JSONB, nullable=False)  # Structured briefing sections
    html_content = Column(Text, nullable=True)  # Rendered HTML for email

    # Delivery
    delivered_via = Column(String(20), nullable=True)  # email, in_app, both
    delivered_at = Column(String(50), nullable=True)
    opened_at = Column(String(50), nullable=True)

    # AI metadata
    model_used = Column(String(50), nullable=True)
    generation_time_ms = Column(Integer, nullable=True)
    data_snapshot = Column(JSONB, default=dict)  # Key metrics at generation time


# =============================================
# Data Quality Record
# =============================================

class DataQualityRecord(TenantBaseModel):
    """Tracks data quality pipeline results per sync/import."""
    __tablename__ = "data_quality_records"
    __table_args__ = (
        Index("ix_dq_tenant_entity", "tenant_id", "entity_type"),
    )

    entity_type = Column(String(100), nullable=False)  # customers, invoices, etc.
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    source_system = Column(String(50), nullable=True)
    sync_batch_id = Column(UUID(as_uuid=True), nullable=True)

    status = Column(SQLEnum(DataQualityStatus), default=DataQualityStatus.CLEAN)
    quality_score = Column(Float, default=100.0)

    # Pipeline stage results
    validation_issues = Column(JSONB, default=list)
    dedup_matches = Column(JSONB, default=list)
    normalization_changes = Column(JSONB, default=list)
    anomalies_detected = Column(JSONB, default=list)
    enrichment_applied = Column(JSONB, default=list)

    # Quarantine
    is_quarantined = Column(Boolean, default=False)
    quarantine_reason = Column(Text, nullable=True)
    reviewed_by_id = Column(UUID(as_uuid=True), nullable=True)
    reviewed_at = Column(String(50), nullable=True)

    raw_data = Column(JSONB, default=dict)  # Original record before processing


# =============================================
# OCR Document
# =============================================

class OCRDocument(TenantBaseModel):
    """Processed document from OCR pipeline."""
    __tablename__ = "ocr_documents"
    __table_args__ = (
        Index("ix_ocr_tenant_type", "tenant_id", "document_type"),
    )

    document_type = Column(String(50), nullable=False)  # invoice, po, payment_advice, etc.
    file_name = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)  # MinIO path
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)

    # Extraction results
    extracted_fields = Column(JSONB, default=dict)
    confidence_scores = Column(JSONB, default=dict)
    overall_confidence = Column(Float, nullable=True)

    # Processing status
    processing_status = Column(String(50), default="pending")
    processed_at = Column(String(50), nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    # Review
    needs_review = Column(Boolean, default=False)
    reviewed_by_id = Column(UUID(as_uuid=True), nullable=True)
    reviewed_at = Column(String(50), nullable=True)
    review_corrections = Column(JSONB, default=dict)

    # Link to created entity
    linked_entity_type = Column(String(100), nullable=True)
    linked_entity_id = Column(UUID(as_uuid=True), nullable=True)


# =============================================
# Agent Run Log
# =============================================

class AgentRunLog(TenantBaseModel):
    """Tracks execution of AI agents for the Agent Hub dashboard."""
    __tablename__ = "agent_run_logs"
    __table_args__ = (
        Index("ix_agent_run_tenant_agent", "tenant_id", "agent_name"),
        Index("ix_agent_run_tenant_started", "tenant_id", "started_at"),
    )

    agent_name = Column(String(100), nullable=False)
    run_type = Column(String(50), default="scheduled")  # scheduled, manual, triggered
    started_at = Column(String(50), nullable=False)
    completed_at = Column(String(50), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    status = Column(String(50), default="running")  # running, completed, failed, cancelled
    records_processed = Column(Integer, default=0)
    records_succeeded = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)

    error_message = Column(Text, nullable=True)
    error_traceback = Column(Text, nullable=True)
    result_summary = Column(JSONB, default=dict)
    run_metadata = Column(JSONB, default=dict)


# =============================================
# Write-Off Record
# =============================================

class WriteOff(AuditableModel):
    """Write-off and IFRS 9 ECL provisioning record."""
    __tablename__ = "write_offs"
    __table_args__ = (
        Index("ix_writeoff_tenant_customer", "tenant_id", "customer_id"),
    )

    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True)

    write_off_type = Column(String(50), nullable=False)  # full, partial, provision
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="AED")

    ecl_stage = Column(SQLEnum(ECLStage), nullable=True)
    ecl_probability = Column(Float, nullable=True)
    provision_amount = Column(Numeric(15, 2), nullable=True)

    reason = Column(Text, nullable=True)
    approval_status = Column(SQLEnum(CreditApprovalStatus), default=CreditApprovalStatus.PENDING)
    approved_by_id = Column(UUID(as_uuid=True), nullable=True)
    approved_at = Column(String(50), nullable=True)

    # Reversal tracking
    is_reversed = Column(Boolean, default=False)
    reversed_at = Column(String(50), nullable=True)
    reversed_by_id = Column(UUID(as_uuid=True), nullable=True)
    reversal_reason = Column(Text, nullable=True)


# =============================================
# Product / Item Master
# =============================================

class Product(AuditableModel):
    """Product / Item master record — from D365, SAP, or CSV import."""
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "item_number", "source_system", name="uq_product_item_number"),
        Index("ix_product_tenant_group", "tenant_id", "item_group"),
    )

    item_number = Column(String(100), nullable=False)
    external_id = Column(String(255), nullable=True)
    source_system = Column(String(50), nullable=True)

    product_name = Column(String(500), nullable=False)
    product_type = Column(String(100), nullable=True)  # item, service, BOM, etc.
    item_group = Column(String(100), nullable=True)
    item_model_group = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True)

    # Pricing
    cost_price = Column(Numeric(15, 4), default=0)
    purchase_price = Column(Numeric(15, 4), default=0)
    sales_price = Column(Numeric(15, 4), default=0)
    currency = Column(String(3), default="AED")

    # Units
    inventory_unit = Column(String(20), nullable=True)  # EA, KG, M, etc.
    sales_unit = Column(String(20), nullable=True)
    purchase_unit = Column(String(20), nullable=True)

    # Tax
    tax_group = Column(String(50), nullable=True)

    # Status & metadata
    status = Column(String(50), default="active")  # active, discontinued, blocked
    tags = Column(ARRAY(String), default=list)
    custom_fields = Column(JSONB, default=dict)
