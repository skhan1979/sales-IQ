"""
Sales IQ - Demo Data Manager
Generates realistic GCC-market ERP/CRM sample data for demos and testing.

Supports multiple ERP profiles (D365 F&O, SAP B1, Generic) with configurable
dataset sizes (small/medium/large). All data is tenant-scoped and can be
generated or wiped without affecting production records.
"""

import random
import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import AuditLog
from app.models.business import (
    Customer, Invoice, Payment, Dispute, CollectionActivity,
    CreditLimitRequest, WriteOff,
    CustomerStatus, InvoiceStatus, PaymentMethod,
    DisputeStatus, DisputeReason, CollectionAction, ECLStage,
)


# =============================================
# GCC Seed Data Corpus
# =============================================

# Realistic GCC company names with Arabic equivalents
GCC_COMPANIES = [
    # UAE
    {"name": "Al Futtaim Group", "name_ar": "مجموعة الفطيم", "country": "AE", "city": "Dubai", "industry": "Retail & Distribution", "territory": "Dubai"},
    {"name": "Emirates Steel Industries", "name_ar": "حديد الإمارات", "country": "AE", "city": "Abu Dhabi", "industry": "Manufacturing", "territory": "Abu Dhabi"},
    {"name": "Majid Al Futtaim Holdings", "name_ar": "مجيد الفطيم القابضة", "country": "AE", "city": "Dubai", "industry": "Real Estate & Retail", "territory": "Dubai"},
    {"name": "Gulf Petrochemicals FZE", "name_ar": "الخليج للبتروكيماويات", "country": "AE", "city": "Sharjah", "industry": "Petrochemicals", "territory": "Sharjah"},
    {"name": "Al Ghurair Foods LLC", "name_ar": "الغرير للأغذية", "country": "AE", "city": "Dubai", "industry": "FMCG", "territory": "Dubai"},
    {"name": "National Food Products Co", "name_ar": "الوطنية للمنتجات الغذائية", "country": "AE", "city": "Abu Dhabi", "industry": "FMCG", "territory": "Abu Dhabi"},
    {"name": "RAK Ceramics PJSC", "name_ar": "سيراميك رأس الخيمة", "country": "AE", "city": "Ras Al Khaimah", "industry": "Manufacturing", "territory": "RAK"},
    {"name": "Emaar Properties PJSC", "name_ar": "إعمار العقارية", "country": "AE", "city": "Dubai", "industry": "Real Estate", "territory": "Dubai"},
    {"name": "Dubai Refreshments PJSC", "name_ar": "دبي للمرطبات", "country": "AE", "city": "Dubai", "industry": "FMCG", "territory": "Dubai"},
    {"name": "Agthia Group PJSC", "name_ar": "أغذية القابضة", "country": "AE", "city": "Abu Dhabi", "industry": "FMCG", "territory": "Abu Dhabi"},
    {"name": "Al Masah Capital Limited", "name_ar": "المسة كابيتال", "country": "AE", "city": "Dubai", "industry": "Financial Services", "territory": "Dubai"},
    {"name": "Julphar Pharmaceuticals", "name_ar": "جلفار للصناعات الدوائية", "country": "AE", "city": "Ras Al Khaimah", "industry": "Pharmaceuticals", "territory": "RAK"},
    {"name": "Al Ain Farms PJSC", "name_ar": "مزارع العين", "country": "AE", "city": "Al Ain", "industry": "FMCG", "territory": "Abu Dhabi"},
    {"name": "Dubai Cable Company", "name_ar": "دبي للكابلات", "country": "AE", "city": "Dubai", "industry": "Manufacturing", "territory": "Dubai"},
    {"name": "Sharjah Cement & Industrial", "name_ar": "الشارقة للاسمنت", "country": "AE", "city": "Sharjah", "industry": "Construction Materials", "territory": "Sharjah"},
    {"name": "Union Properties PJSC", "name_ar": "الاتحاد العقارية", "country": "AE", "city": "Dubai", "industry": "Real Estate", "territory": "Dubai"},
    {"name": "Gulf Pharmaceutical Industries", "name_ar": "الخليج للصناعات الدوائية", "country": "AE", "city": "Ajman", "industry": "Pharmaceuticals", "territory": "Ajman"},
    {"name": "Al Rawabi Dairy Company", "name_ar": "الروابي للألبان", "country": "AE", "city": "Dubai", "industry": "FMCG", "territory": "Dubai"},
    # KSA
    {"name": "Saudi Aramco Base Oil Co", "name_ar": "أرامكو للزيوت الأساسية", "country": "SA", "city": "Jeddah", "industry": "Oil & Gas", "territory": "Western"},
    {"name": "SABIC Agri-Nutrients", "name_ar": "سابك للمغذيات الزراعية", "country": "SA", "city": "Riyadh", "industry": "Petrochemicals", "territory": "Central"},
    {"name": "Almarai Company", "name_ar": "المراعي", "country": "SA", "city": "Riyadh", "industry": "FMCG", "territory": "Central"},
    {"name": "Saudi Ceramic Company", "name_ar": "الخزف السعودي", "country": "SA", "city": "Riyadh", "industry": "Manufacturing", "territory": "Central"},
    {"name": "Jarir Marketing Company", "name_ar": "مكتبة جرير", "country": "SA", "city": "Riyadh", "industry": "Retail", "territory": "Central"},
    {"name": "Al Rajhi Steel Industries", "name_ar": "الراجحي للصناعات الحديدية", "country": "SA", "city": "Dammam", "industry": "Manufacturing", "territory": "Eastern"},
    {"name": "Savola Group Company", "name_ar": "مجموعة صافولا", "country": "SA", "city": "Jeddah", "industry": "FMCG", "territory": "Western"},
    {"name": "Halwani Brothers Company", "name_ar": "شركة حلواني إخوان", "country": "SA", "city": "Jeddah", "industry": "FMCG", "territory": "Western"},
    # Qatar / Kuwait / Bahrain / Oman
    {"name": "Industries Qatar QSC", "name_ar": "صناعات قطر", "country": "QA", "city": "Doha", "industry": "Petrochemicals", "territory": "Qatar"},
    {"name": "Qatar National Cement Co", "name_ar": "قطر الوطنية للإسمنت", "country": "QA", "city": "Doha", "industry": "Construction Materials", "territory": "Qatar"},
    {"name": "Americana Restaurants", "name_ar": "أمريكانا للمطاعم", "country": "KW", "city": "Kuwait City", "industry": "Food & Beverage", "territory": "Kuwait"},
    {"name": "Gulf Petrochemical Industries", "name_ar": "صناعات البتروكيماويات الخليجية", "country": "BH", "city": "Manama", "industry": "Petrochemicals", "territory": "Bahrain"},
    {"name": "Oman Cement Company", "name_ar": "أسمنت عمان", "country": "OM", "city": "Muscat", "industry": "Construction Materials", "territory": "Oman"},
    {"name": "Al Jazeera Services", "name_ar": "خدمات الجزيرة", "country": "OM", "city": "Muscat", "industry": "Services", "territory": "Oman"},
]

# Contact name corpus
FIRST_NAMES = [
    "Mohammed", "Ahmed", "Ali", "Omar", "Khalid", "Saeed", "Hassan", "Yousuf",
    "Fatima", "Aisha", "Maryam", "Noura", "Sara", "Huda", "Layla", "Dana",
    "Rashid", "Hamad", "Sultan", "Faisal", "Nasser", "Tariq", "Majid", "Salim",
]
LAST_NAMES = [
    "Al Maktoum", "Al Nahyan", "Al Thani", "Al Sabah", "Al Khalifa",
    "Al Hashimi", "Al Mansouri", "Al Mazrouei", "Al Nuaimi", "Al Shamsi",
    "Khan", "Patel", "Sharma", "Singh", "Ahmed", "Ibrahim", "Abbas",
    "Al Suwaidi", "Al Dhaheri", "Al Zaabi", "Al Muhairi", "Al Ketbi",
]

# Invoice line item descriptions per industry
LINE_ITEMS = {
    "FMCG": [
        "Bottled water 500ml x24 cases", "Yogurt multi-pack x48 units",
        "Cooking oil 5L x20 cartons", "Rice 25kg sacks x50",
        "Juice assorted flavors x36 cases", "Flour 50kg bags x30",
        "Snack assortment box x60", "Dairy fresh milk 1L x100",
    ],
    "Manufacturing": [
        "Steel reinforcement bars 12mm x10T", "Aluminium profiles custom",
        "PVC pipes 110mm x500m", "Copper wire 2.5mm² x1000m",
        "Concrete blocks 200mm x5000", "Glass panels tempered 6mm",
        "Welding electrodes E7018 x50kg", "Industrial bolts M16 x2000",
    ],
    "Construction Materials": [
        "Portland cement Type I x200 bags", "Ready-mix concrete Grade 40 x50m³",
        "Sand washed x100T", "Aggregate 20mm x80T",
        "Ceramic tiles 60x60cm x500m²", "Waterproofing membrane x200m²",
    ],
    "Petrochemicals": [
        "Polyethylene granules HDPE x20T", "Polypropylene homopolymer x15T",
        "Industrial solvents MEK x500L", "Lubricant base oil Group II x10KL",
        "Methanol technical grade x5KL", "Urea fertilizer x30T",
    ],
    "default": [
        "Professional services - consulting", "Equipment maintenance contract",
        "Office supplies quarterly order", "IT infrastructure support",
        "Logistics and transportation", "Raw materials bulk order",
    ],
}

CURRENCIES = {"AE": "AED", "SA": "SAR", "QA": "QAR", "KW": "KWD", "BH": "BHD", "OM": "OMR"}
PHONE_PREFIXES = {"AE": "+971", "SA": "+966", "QA": "+974", "KW": "+965", "BH": "+973", "OM": "+968"}

# ERP source system profiles
ERP_PROFILES = {
    "d365_fo": {
        "display_name": "Dynamics 365 Finance & Operations",
        "source_system": "D365_FO",
        "invoice_prefix": "SI-",
        "external_id_prefix": "CUST-",
        "payment_ref_prefix": "PMT-",
    },
    "sap_b1": {
        "display_name": "SAP Business One",
        "source_system": "SAP_B1",
        "invoice_prefix": "INV",
        "external_id_prefix": "BP",
        "payment_ref_prefix": "RCT",
    },
    "generic": {
        "display_name": "Generic CSV Import",
        "source_system": "CSV_IMPORT",
        "invoice_prefix": "INV-",
        "external_id_prefix": "C-",
        "payment_ref_prefix": "PAY-",
    },
}

# Dataset size configurations
DATASET_SIZES = {
    "small": {"customers": 10, "invoices_per_customer": (2, 5), "payment_probability": 0.6},
    "medium": {"customers": 20, "invoices_per_customer": (3, 8), "payment_probability": 0.65},
    "large": {"customers": 30, "invoices_per_customer": (5, 15), "payment_probability": 0.7},
}


# =============================================
# Generator Helpers
# =============================================

def _random_phone(country: str) -> str:
    prefix = PHONE_PREFIXES.get(country, "+971")
    area = random.choice(["2", "3", "4", "6", "7"])
    number = "".join([str(random.randint(0, 9)) for _ in range(7)])
    return f"{prefix}-{area}-{number}"


def _random_email(company_name: str) -> str:
    domain = company_name.lower().replace(" ", "").replace(".", "")[:15]
    dept = random.choice(["finance", "accounts", "ar", "billing", "treasury", "admin"])
    tld = random.choice(["ae", "com", "sa", "qa"])
    return f"{dept}@{domain}.{tld}"


def _random_contact() -> str:
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def _random_amount(industry: str) -> Decimal:
    """Generate realistic invoice amounts by industry."""
    ranges = {
        "FMCG": (5_000, 250_000),
        "Manufacturing": (20_000, 800_000),
        "Construction Materials": (15_000, 500_000),
        "Petrochemicals": (50_000, 2_000_000),
        "Real Estate": (100_000, 5_000_000),
        "Oil & Gas": (100_000, 3_000_000),
        "Retail": (3_000, 150_000),
        "Pharmaceuticals": (10_000, 400_000),
    }
    low, high = ranges.get(industry, (5_000, 300_000))
    amount = random.uniform(low, high)
    # Round to nearest 50 for realism
    amount = round(amount / 50) * 50
    return Decimal(str(amount))


def _random_credit_limit(industry: str) -> Decimal:
    multipliers = {
        "FMCG": (3, 8),
        "Manufacturing": (5, 15),
        "Petrochemicals": (10, 30),
        "Real Estate": (15, 50),
        "Oil & Gas": (10, 40),
    }
    low_mult, high_mult = multipliers.get(industry, (3, 10))
    base = random.randint(50_000, 200_000)
    limit = base * random.uniform(low_mult, high_mult) / 10
    return Decimal(str(round(limit / 10_000) * 10_000))


def _random_line_items(industry: str, amount: Decimal) -> List[Dict]:
    items_pool = LINE_ITEMS.get(industry, LINE_ITEMS["default"])
    num_items = random.randint(1, min(4, len(items_pool)))
    selected = random.sample(items_pool, num_items)

    # Distribute amount across items
    weights = [random.random() for _ in range(num_items)]
    total_w = sum(weights)
    result = []
    for i, desc in enumerate(selected):
        item_amount = float(amount) * weights[i] / total_w
        qty = random.randint(1, 100)
        unit_price = round(item_amount / qty, 2)
        result.append({
            "description": desc,
            "quantity": qty,
            "unit_price": unit_price,
            "total": round(unit_price * qty, 2),
        })
    return result


# =============================================
# Demo Data Manager
# =============================================

class DemoDataManager:
    """
    Generates and manages demo datasets for Sales IQ.
    All generated records are tagged with source_system='DEMO' for easy cleanup.
    """

    DEMO_TAG = "DEMO"

    async def generate(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        size: str = "medium",
        erp_profile: str = "d365_fo",
    ) -> Dict:
        """
        Generate a full demo dataset for the given tenant.
        Returns summary statistics.
        """
        if size not in DATASET_SIZES:
            raise ValueError(f"Invalid size '{size}'. Choose from: {list(DATASET_SIZES.keys())}")
        if erp_profile not in ERP_PROFILES:
            raise ValueError(f"Invalid profile '{erp_profile}'. Choose from: {list(ERP_PROFILES.keys())}")

        config = DATASET_SIZES[size]
        profile = ERP_PROFILES[erp_profile]
        today = date.today()

        stats = {
            "customers": 0, "invoices": 0, "payments": 0,
            "disputes": 0, "collection_activities": 0,
            "erp_profile": profile["display_name"],
            "size": size,
        }

        # Select a subset of companies
        num_customers = min(config["customers"], len(GCC_COMPANIES))
        selected_companies = random.sample(GCC_COMPANIES, num_customers)

        all_customers = []
        all_invoices = []
        all_payments = []

        # --- Generate Customers ---
        for idx, company in enumerate(selected_companies):
            currency = CURRENCIES.get(company["country"], "AED")
            credit_limit = _random_credit_limit(company["industry"])

            # Assign ECL stage with weighted distribution
            ecl_stage = random.choices(
                [ECLStage.STAGE_1, ECLStage.STAGE_2, ECLStage.STAGE_3],
                weights=[70, 20, 10],
            )[0]

            # Some customers have quality issues for DQ agent to find
            status = random.choices(
                [CustomerStatus.ACTIVE, CustomerStatus.INACTIVE, CustomerStatus.CREDIT_HOLD],
                weights=[80, 10, 10],
            )[0]

            customer = Customer(
                tenant_id=tenant_id,
                created_by=user_id,
                external_id=f"{profile['external_id_prefix']}{1000 + idx}",
                source_system=self.DEMO_TAG,
                name=company["name"],
                name_ar=company.get("name_ar"),
                industry=company["industry"],
                segment=random.choice(["sme", "mid_market", "enterprise", "key_account"]),
                territory=company["territory"],
                region=company["country"],
                country=company["country"],
                city=company["city"],
                phone=_random_phone(company["country"]),
                email=_random_email(company["name"]),
                currency=currency,
                payment_terms_days=random.choice([15, 30, 45, 60, 90]),
                credit_limit=credit_limit,
                credit_limit_currency=currency,
                credit_hold_threshold=random.choice([80.0, 85.0, 90.0, 95.0]),
                status=status,
                ecl_stage=ecl_stage,
                risk_score=round(random.uniform(10, 90), 1),
                data_quality_score=round(random.uniform(60, 100), 1),
                tags=[company["industry"].lower().replace(" & ", "_").replace(" ", "_"), "demo"],
                custom_fields={
                    "contact_person": _random_contact(),
                    "erp_source": profile["source_system"],
                },
            )
            db.add(customer)
            all_customers.append(customer)
            stats["customers"] += 1

        await db.flush()  # Get customer IDs

        # --- Generate Invoices ---
        inv_counter = 1
        for customer in all_customers:
            min_inv, max_inv = config["invoices_per_customer"]
            num_invoices = random.randint(min_inv, max_inv)

            for _ in range(num_invoices):
                # Spread invoices across the last 6 months
                days_ago = random.randint(1, 180)
                invoice_date = today - timedelta(days=days_ago)
                payment_terms = customer.payment_terms_days or 30
                due_date = invoice_date + timedelta(days=payment_terms)

                amount = _random_amount(customer.industry or "default")
                tax_rate = random.choice([0, 5, 15])  # UAE 5% VAT, KSA 15% VAT
                tax_amount = Decimal(str(round(float(amount) * tax_rate / 100, 2)))
                total = amount + tax_amount

                # Calculate aging
                if due_date >= today:
                    days_overdue = 0
                    aging_bucket = "current"
                else:
                    days_overdue = (today - due_date).days
                    if days_overdue <= 30:
                        aging_bucket = "1-30"
                    elif days_overdue <= 60:
                        aging_bucket = "31-60"
                    elif days_overdue <= 90:
                        aging_bucket = "61-90"
                    else:
                        aging_bucket = "90+"

                # Determine status
                inv_status = InvoiceStatus.OPEN
                if days_overdue > 0:
                    inv_status = InvoiceStatus.OVERDUE

                currency = str(customer.currency) if customer.currency else "AED"
                industry = customer.industry or "default"

                invoice = Invoice(
                    tenant_id=tenant_id,
                    created_by=user_id,
                    customer_id=customer.id,
                    invoice_number=f"{profile['invoice_prefix']}{inv_counter:06d}",
                    external_id=f"{profile['invoice_prefix']}{inv_counter:06d}",
                    source_system=self.DEMO_TAG,
                    invoice_date=invoice_date,
                    due_date=due_date,
                    posting_date=invoice_date,
                    currency=currency,
                    amount=total,
                    tax_amount=tax_amount,
                    amount_paid=Decimal("0"),
                    amount_remaining=total,
                    status=inv_status,
                    days_overdue=days_overdue,
                    aging_bucket=aging_bucket,
                    line_items=_random_line_items(industry, amount),
                )
                db.add(invoice)
                all_invoices.append(invoice)
                stats["invoices"] += 1
                inv_counter += 1

        await db.flush()  # Get invoice IDs

        # --- Generate Payments ---
        pmt_counter = 1
        for invoice in all_invoices:
            if random.random() > config["payment_probability"]:
                continue  # Skip — this invoice remains unpaid

            # Decide payment pattern
            pattern = random.choices(
                ["full", "partial", "overpay"],
                weights=[50, 40, 10],
            )[0]

            inv_amount = float(invoice.amount)
            if pattern == "full":
                pay_amount = inv_amount
            elif pattern == "partial":
                pay_amount = round(inv_amount * random.uniform(0.2, 0.8), 2)
            else:  # overpay (rare)
                pay_amount = round(inv_amount * random.uniform(1.01, 1.05), 2)

            # Payment date: between invoice date and today
            invoice_date = invoice.invoice_date
            max_delay = (today - invoice_date).days
            if max_delay <= 0:
                max_delay = 1
            pay_delay = random.randint(1, max_delay)
            payment_date = invoice_date + timedelta(days=pay_delay)
            if payment_date > today:
                payment_date = today

            method = random.choice(list(PaymentMethod))
            currency = str(invoice.currency) if invoice.currency else "AED"

            payment = Payment(
                tenant_id=tenant_id,
                created_by=user_id,
                customer_id=invoice.customer_id,
                invoice_id=invoice.id,
                external_id=f"{profile['payment_ref_prefix']}{pmt_counter:06d}",
                source_system=self.DEMO_TAG,
                payment_date=payment_date,
                amount=Decimal(str(pay_amount)),
                currency=currency,
                payment_method=method,
                reference_number=f"REF-{random.randint(100000, 999999)}",
                bank_reference=f"BNK-{random.randint(100000, 999999)}",
                is_matched=True,
                matched_at=datetime.now(timezone.utc).isoformat(),
                match_confidence=random.choice([0.85, 0.90, 0.95, 1.0]),
            )
            db.add(payment)
            all_payments.append(payment)
            stats["payments"] += 1
            pmt_counter += 1

            # Update invoice status
            paid = Decimal(str(pay_amount))
            invoice.amount_paid = paid
            invoice.amount_remaining = invoice.amount - paid
            if invoice.amount_remaining <= 0:
                invoice.amount_remaining = Decimal("0")
                invoice.status = InvoiceStatus.PAID
            else:
                invoice.status = InvoiceStatus.PARTIALLY_PAID

        # --- Generate Disputes (on ~10% of unpaid/partially paid invoices) ---
        dispute_counter = 1
        unpaid_invoices = [i for i in all_invoices if i.status in (InvoiceStatus.OPEN, InvoiceStatus.OVERDUE, InvoiceStatus.PARTIALLY_PAID)]
        dispute_candidates = random.sample(unpaid_invoices, min(len(unpaid_invoices), max(1, len(unpaid_invoices) // 10)))

        for inv in dispute_candidates:
            reason = random.choice(list(DisputeReason))
            dispute_amount = float(inv.amount_remaining) * random.uniform(0.1, 0.5)
            status = random.choices(
                [DisputeStatus.OPEN, DisputeStatus.IN_REVIEW, DisputeStatus.RESOLVED],
                weights=[40, 35, 25],
            )[0]
            currency = str(inv.currency) if inv.currency else "AED"

            dispute = Dispute(
                tenant_id=tenant_id,
                created_by=user_id,
                customer_id=inv.customer_id,
                invoice_id=inv.id,
                dispute_number=f"DSP-{dispute_counter:04d}",
                reason=reason,
                reason_detail=f"Customer reported {reason.value} issue on invoice {inv.invoice_number}",
                status=status,
                amount=Decimal(str(round(dispute_amount, 2))),
                currency=currency,
                priority=random.choice(["low", "medium", "high", "critical"]),
                sla_due_date=today + timedelta(days=random.choice([5, 10, 15, 30])),
                sla_breached=random.random() < 0.15,
            )
            if status == DisputeStatus.RESOLVED:
                dispute.resolution_type = random.choice(["credit_note", "adjustment", "rejected"])
                dispute.resolution_amount = dispute.amount
                dispute.resolved_at = datetime.now(timezone.utc).isoformat()

            inv.status = InvoiceStatus.DISPUTED
            db.add(dispute)
            stats["disputes"] += 1
            dispute_counter += 1

        # --- Generate Collection Activities ---
        overdue_invoices = [i for i in all_invoices if i.days_overdue and i.days_overdue > 0 and i.status != InvoiceStatus.PAID]
        for inv in overdue_invoices:
            # 1-3 collection actions per overdue invoice
            num_actions = random.randint(1, 3)
            for action_idx in range(num_actions):
                action_type = random.choices(
                    [CollectionAction.EMAIL_REMINDER, CollectionAction.PHONE_CALL,
                     CollectionAction.SMS_REMINDER, CollectionAction.PROMISE_TO_PAY,
                     CollectionAction.ESCALATION],
                    weights=[35, 25, 15, 15, 10],
                )[0]

                action_date = inv.due_date + timedelta(days=random.randint(1, max(1, inv.days_overdue)))
                if action_date > today:
                    action_date = today

                activity = CollectionActivity(
                    tenant_id=tenant_id,
                    created_by=user_id,
                    customer_id=inv.customer_id,
                    invoice_id=inv.id,
                    action_type=action_type,
                    action_date=action_date,
                    notes=f"Follow-up #{action_idx + 1} for {inv.invoice_number}",
                    is_ai_suggested=random.random() < 0.3,
                    ai_priority_score=round(random.uniform(0.3, 1.0), 2) if random.random() < 0.3 else None,
                )

                if action_type == CollectionAction.PROMISE_TO_PAY:
                    activity.ptp_date = today + timedelta(days=random.randint(3, 30))
                    activity.ptp_amount = inv.amount_remaining
                    activity.ptp_fulfilled = random.random() < 0.4

                db.add(activity)
                stats["collection_activities"] += 1

        # --- Update credit utilization for each customer ---
        for customer in all_customers:
            cust_invoices = [i for i in all_invoices if i.customer_id == customer.id]
            outstanding = sum(
                float(i.amount_remaining) for i in cust_invoices
                if i.status in (InvoiceStatus.OPEN, InvoiceStatus.OVERDUE, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.DISPUTED)
            )
            customer.credit_utilization = Decimal(str(round(outstanding, 2)))
            if customer.credit_limit and customer.credit_limit > 0:
                pct = outstanding / float(customer.credit_limit) * 100
                customer.credit_hold = pct >= float(customer.credit_hold_threshold or 90)

        # --- Audit log ---
        audit = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="DEMO_DATA_GENERATE",
            entity_type="demo_data",
            after_state=stats,
        )
        db.add(audit)

        await db.commit()
        return stats

    async def clear(self, db: AsyncSession, tenant_id: UUID, user_id: UUID, clear_all: bool = False) -> Dict:
        """
        Remove demo records for the given tenant.
        By default only deletes records where source_system = 'DEMO'.
        If clear_all=True, removes ALL business data for the tenant
        (use when records exist from before the DEMO tagging was implemented).
        """
        counts = {}

        # Delete in dependency order (children before parents)
        for model, name in [
            (WriteOff, "write_offs"),
            (CreditLimitRequest, "credit_limit_requests"),
            (CollectionActivity, "collection_activities"),
            (Payment, "payments"),
            (Dispute, "disputes"),
            (Invoice, "invoices"),
            (Customer, "customers"),
        ]:
            if clear_all:
                # Delete ALL records for this tenant
                result = await db.execute(
                    delete(model).where(model.tenant_id == tenant_id)
                )
                counts[name] = result.rowcount
            elif hasattr(model, "source_system"):
                # Delete DEMO-tagged + NULL source_system (legacy untagged records)
                result = await db.execute(
                    delete(model).where(
                        model.tenant_id == tenant_id,
                        (model.source_system == self.DEMO_TAG) | (model.source_system.is_(None)),
                    )
                )
                counts[name] = result.rowcount
            else:
                # CollectionActivity doesn't have source_system — delete by customer linkage
                demo_customer_ids = (
                    select(Customer.id).where(
                        Customer.tenant_id == tenant_id,
                        (Customer.source_system == self.DEMO_TAG) | (Customer.source_system.is_(None)),
                    )
                )
                result = await db.execute(
                    delete(model).where(
                        model.tenant_id == tenant_id,
                        model.customer_id.in_(demo_customer_ids),
                    )
                )
                counts[name] = result.rowcount

        audit = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="DEMO_DATA_CLEAR",
            entity_type="demo_data",
            after_state=counts,
        )
        db.add(audit)
        await db.commit()

        return counts

    async def get_stats(self, db: AsyncSession, tenant_id: UUID) -> Dict:
        """Get current demo data statistics for the tenant."""
        stats = {}
        for model, name in [
            (Customer, "customers"),
            (Invoice, "invoices"),
            (Payment, "payments"),
        ]:
            total = (await db.execute(
                select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
            )).scalar() or 0
            demo = (await db.execute(
                select(func.count()).select_from(model).where(
                    model.tenant_id == tenant_id,
                    model.source_system == self.DEMO_TAG,
                )
            )).scalar() or 0
            stats[name] = {"total": total, "demo": demo, "real": total - demo}

        # Disputes and collection activities via customer linkage
        demo_cust_ids = select(Customer.id).where(
            Customer.tenant_id == tenant_id,
            Customer.source_system == self.DEMO_TAG,
        )
        for model, name in [(Dispute, "disputes"), (CollectionActivity, "collection_activities")]:
            total = (await db.execute(
                select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
            )).scalar() or 0
            demo = (await db.execute(
                select(func.count()).select_from(model).where(
                    model.tenant_id == tenant_id,
                    model.customer_id.in_(demo_cust_ids),
                )
            )).scalar() or 0
            stats[name] = {"total": total, "demo": demo, "real": total - demo}

        return stats


# Singleton
demo_data_manager = DemoDataManager()
