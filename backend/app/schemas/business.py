"""
Sales IQ - Business Entity Schemas
Pydantic models for Customer, Invoice, Payment request/response.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Any
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================
# Customer Schemas
# =============================================

class CustomerCreate(BaseModel):
    external_id: Optional[str] = None
    source_system: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=500)
    name_ar: Optional[str] = None
    trade_name: Optional[str] = None
    tax_id: Optional[str] = None
    status: str = "active"
    industry: Optional[str] = None
    segment: Optional[str] = None
    territory: Optional[str] = None
    region: Optional[str] = None
    country: str = "AE"
    city: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    currency: str = "AED"
    payment_terms_days: int = 30
    credit_limit: Decimal = Decimal("0")
    credit_limit_currency: str = "AED"
    credit_hold_threshold: float = 90.0
    assigned_collector_id: Optional[UUID] = None
    assigned_sales_rep_id: Optional[UUID] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[dict] = None


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=500)
    name_ar: Optional[str] = None
    trade_name: Optional[str] = None
    tax_id: Optional[str] = None
    status: Optional[str] = None
    industry: Optional[str] = None
    segment: Optional[str] = None
    territory: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    currency: Optional[str] = None
    payment_terms_days: Optional[int] = None
    credit_limit: Optional[Decimal] = None
    credit_hold_threshold: Optional[float] = None
    assigned_collector_id: Optional[UUID] = None
    assigned_sales_rep_id: Optional[UUID] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[dict] = None


class CustomerResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    external_id: Optional[str] = None
    source_system: Optional[str] = None
    name: str
    name_ar: Optional[str] = None
    trade_name: Optional[str] = None
    tax_id: Optional[str] = None
    status: str
    industry: Optional[str] = None
    segment: Optional[str] = None
    territory: Optional[str] = None
    region: Optional[str] = None
    country: str
    city: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    currency: str
    payment_terms_days: int
    credit_limit: Decimal
    credit_limit_currency: str
    credit_utilization: Decimal
    credit_hold: bool
    credit_hold_threshold: float
    risk_score: Optional[float] = None
    churn_probability: Optional[float] = None
    predicted_dso: Optional[float] = None
    ecl_stage: Optional[str] = None
    data_quality_score: Optional[float] = None
    assigned_collector_id: Optional[UUID] = None
    assigned_sales_rep_id: Optional[UUID] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CustomerListResponse(BaseModel):
    items: List[CustomerResponse]
    total: int
    page: int
    page_size: int


class CustomerSummary(BaseModel):
    """Lightweight customer info for dropdowns and references."""
    id: UUID
    name: str
    status: str
    currency: str
    credit_limit: Decimal
    credit_utilization: Decimal
    credit_hold: bool

    model_config = {"from_attributes": True}


# =============================================
# Invoice Schemas
# =============================================

class InvoiceCreate(BaseModel):
    customer_id: UUID
    invoice_number: str = Field(..., min_length=1, max_length=100)
    external_id: Optional[str] = None
    source_system: Optional[str] = None
    po_number: Optional[str] = None
    invoice_date: date
    due_date: date
    posting_date: Optional[date] = None
    currency: str = "AED"
    amount: Decimal = Field(..., gt=0)
    tax_amount: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    status: str = "open"
    line_items: Optional[List[dict]] = None
    notes: Optional[str] = None


class InvoiceUpdate(BaseModel):
    po_number: Optional[str] = None
    due_date: Optional[date] = None
    amount_paid: Optional[Decimal] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    line_items: Optional[List[dict]] = None


class InvoiceResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    customer_name: Optional[str] = None
    invoice_number: str
    external_id: Optional[str] = None
    source_system: Optional[str] = None
    po_number: Optional[str] = None
    invoice_date: date
    due_date: date
    posting_date: Optional[date] = None
    currency: str
    amount: Decimal
    amount_paid: Decimal
    amount_remaining: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    status: str
    days_overdue: int
    aging_bucket: Optional[str] = None
    predicted_pay_date: Optional[date] = None
    payment_probability: Optional[float] = None
    line_items: Optional[List[dict]] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class InvoiceListResponse(BaseModel):
    items: List[InvoiceResponse]
    total: int
    page: int
    page_size: int


# =============================================
# Payment Schemas
# =============================================

class PaymentCreate(BaseModel):
    customer_id: UUID
    invoice_id: Optional[UUID] = None
    external_id: Optional[str] = None
    source_system: Optional[str] = None
    payment_date: date
    amount: Decimal = Field(..., gt=0)
    currency: str = "AED"
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    bank_reference: Optional[str] = None
    notes: Optional[str] = None


class PaymentUpdate(BaseModel):
    invoice_id: Optional[UUID] = None
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    bank_reference: Optional[str] = None
    is_matched: Optional[bool] = None
    notes: Optional[str] = None


class PaymentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    customer_name: Optional[str] = None
    invoice_id: Optional[UUID] = None
    invoice_number: Optional[str] = None
    external_id: Optional[str] = None
    source_system: Optional[str] = None
    payment_date: date
    amount: Decimal
    currency: str
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    bank_reference: Optional[str] = None
    is_matched: bool
    matched_at: Optional[str] = None
    match_confidence: Optional[float] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PaymentListResponse(BaseModel):
    items: List[PaymentResponse]
    total: int
    page: int
    page_size: int


# =============================================
# Dashboard / AR Summary Schemas
# =============================================

class AgingBucket(BaseModel):
    bucket: str  # current, 1-30, 31-60, 61-90, 90+
    count: int
    amount: Decimal
    percentage: float


class ARSummary(BaseModel):
    total_receivables: Decimal
    total_overdue: Decimal
    total_customers: int
    customers_on_credit_hold: int
    average_dso: float
    collection_rate: float
    aging_buckets: List[AgingBucket]
    currency: str


class RecentActivity(BaseModel):
    type: str  # payment, invoice, dispute
    description: str
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    timestamp: datetime
    entity_id: UUID
