"""
Sales IQ - Data Quality Agent
5-stage pipeline: Validate → Deduplicate → Normalize → Anomaly Detect → Enrich

Runs against customer, invoice, and payment entities to ensure data integrity
before AI models consume the data for predictions and recommendations.
"""

import re
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent, PipelineStage, AgentContext
from app.models.business import (
    Customer, Invoice, Payment, DataQualityRecord, DataQualityStatus,
)


# =============================================
# Stage 1: Validation
# =============================================

# GCC country codes and phone formats
GCC_COUNTRY_CODES = {"AE", "SA", "QA", "KW", "BH", "OM"}
PHONE_PATTERNS = {
    "AE": r"^(\+971|00971|971)?[- ]?(0)?[2-9]\d{7,8}$",
    "SA": r"^(\+966|00966|966)?[- ]?(0)?[1-9]\d{7,8}$",
    "QA": r"^(\+974|00974|974)?[- ]?[3-7]\d{6,7}$",
    "KW": r"^(\+965|00965|965)?[- ]?[1-9]\d{6,7}$",
    "BH": r"^(\+973|00973|973)?[- ]?[1-9]\d{6,7}$",
    "OM": r"^(\+968|00968|968)?[- ]?[2-9]\d{6,7}$",
}
EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
TAX_ID_RE = re.compile(r"^\d{15}$")  # UAE TRN: 15 digits


class ValidationStage(PipelineStage):
    """
    Stage 1 — Checks completeness, format validity, and business rules.
    Flags critical issues that may block downstream processing.
    """

    name = "validation"

    # Required fields per entity type
    REQUIRED_FIELDS = {
        "customers": ["name", "country", "currency", "payment_terms_days"],
        "invoices": ["customer_id", "invoice_number", "invoice_date", "due_date", "amount", "currency"],
        "payments": ["customer_id", "payment_date", "amount", "currency"],
    }

    # Recommended fields (warning, not critical)
    RECOMMENDED_FIELDS = {
        "customers": ["email", "phone", "industry", "territory", "credit_limit", "tax_id"],
        "invoices": ["po_number", "line_items"],
        "payments": ["payment_method", "reference_number"],
    }

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        if ctx.entity_type == "customers":
            await self._validate_customers(db, ctx)
        elif ctx.entity_type == "invoices":
            await self._validate_invoices(db, ctx)
        elif ctx.entity_type == "payments":
            await self._validate_payments(db, ctx)

    async def _validate_customers(self, db: AsyncSession, ctx: AgentContext) -> None:
        result = await db.execute(
            select(Customer).where(Customer.tenant_id == ctx.tenant_id)
        )
        customers = result.scalars().all()
        ctx.records_processed = len(customers)

        for cust in customers:
            eid = str(cust.id)

            # --- Completeness: required fields ---
            for field in self.REQUIRED_FIELDS["customers"]:
                val = getattr(cust, field, None)
                if val is None or (isinstance(val, str) and not val.strip()):
                    ctx.add_issue(eid, self.name, "critical", field,
                                 f"Required field '{field}' is missing or empty")

            # --- Completeness: recommended fields ---
            for field in self.RECOMMENDED_FIELDS["customers"]:
                val = getattr(cust, field, None)
                if val is None or (isinstance(val, str) and not val.strip()):
                    ctx.add_issue(eid, self.name, "info", field,
                                 f"Recommended field '{field}' is empty")

            # --- Format: Email ---
            if cust.email and not EMAIL_RE.match(cust.email):
                ctx.add_issue(eid, self.name, "warning", "email",
                              f"Invalid email format: '{cust.email}'")

            # --- Format: Phone ---
            if cust.phone:
                country = cust.country or "AE"
                pattern = PHONE_PATTERNS.get(country)
                cleaned = re.sub(r"[\s\-\(\)]", "", cust.phone)
                if pattern and not re.match(pattern, cleaned):
                    ctx.add_issue(eid, self.name, "warning", "phone",
                                  f"Phone '{cust.phone}' may not match {country} format")

            # --- Format: Tax ID (UAE TRN) ---
            if cust.tax_id and cust.country == "AE":
                if not TAX_ID_RE.match(cust.tax_id.strip()):
                    ctx.add_issue(eid, self.name, "warning", "tax_id",
                                  f"UAE TRN should be 15 digits, got '{cust.tax_id}'")

            # --- Business Rule: Credit limit ---
            if cust.credit_limit and cust.credit_limit < 0:
                ctx.add_issue(eid, self.name, "critical", "credit_limit",
                              "Credit limit cannot be negative")

            if cust.credit_limit == 0 and cust.status == "active":
                ctx.add_issue(eid, self.name, "warning", "credit_limit",
                              "Active customer has zero credit limit")

            # --- Business Rule: Payment terms ---
            if cust.payment_terms_days and cust.payment_terms_days > 180:
                ctx.add_issue(eid, self.name, "warning", "payment_terms_days",
                              f"Unusually long payment terms: {cust.payment_terms_days} days")

            ctx.records_succeeded += 1

    async def _validate_invoices(self, db: AsyncSession, ctx: AgentContext) -> None:
        result = await db.execute(
            select(Invoice).where(Invoice.tenant_id == ctx.tenant_id)
        )
        invoices = result.scalars().all()
        ctx.records_processed = len(invoices)

        for inv in invoices:
            eid = str(inv.id)

            # Required fields
            for field in self.REQUIRED_FIELDS["invoices"]:
                val = getattr(inv, field, None)
                if val is None or (isinstance(val, str) and not val.strip()):
                    ctx.add_issue(eid, self.name, "critical", field,
                                 f"Required field '{field}' is missing")

            # Business rules
            if inv.amount is not None and inv.amount <= 0:
                ctx.add_issue(eid, self.name, "critical", "amount",
                              f"Invoice amount must be positive, got {inv.amount}")

            if inv.due_date and inv.invoice_date and inv.due_date < inv.invoice_date:
                ctx.add_issue(eid, self.name, "critical", "due_date",
                              "Due date is before invoice date")

            if inv.invoice_date and inv.invoice_date > date.today():
                ctx.add_issue(eid, self.name, "warning", "invoice_date",
                              f"Invoice date is in the future: {inv.invoice_date}")

            if inv.amount_paid and inv.amount and inv.amount_paid > inv.amount:
                ctx.add_issue(eid, self.name, "warning", "amount_paid",
                              "Amount paid exceeds invoice amount (possible overpayment)")

            if inv.tax_amount and inv.amount:
                tax_pct = float(inv.tax_amount) / float(inv.amount) * 100
                if tax_pct > 20:
                    ctx.add_issue(eid, self.name, "warning", "tax_amount",
                                  f"Tax is {tax_pct:.1f}% of amount — unusually high")

            ctx.records_succeeded += 1

    async def _validate_payments(self, db: AsyncSession, ctx: AgentContext) -> None:
        result = await db.execute(
            select(Payment).where(Payment.tenant_id == ctx.tenant_id)
        )
        payments = result.scalars().all()
        ctx.records_processed = len(payments)

        for pmt in payments:
            eid = str(pmt.id)

            for field in self.REQUIRED_FIELDS["payments"]:
                val = getattr(pmt, field, None)
                if val is None or (isinstance(val, str) and not val.strip()):
                    ctx.add_issue(eid, self.name, "critical", field,
                                 f"Required field '{field}' is missing")

            if pmt.amount is not None and pmt.amount <= 0:
                ctx.add_issue(eid, self.name, "critical", "amount",
                              f"Payment amount must be positive, got {pmt.amount}")

            if pmt.payment_date and pmt.payment_date > date.today():
                ctx.add_issue(eid, self.name, "warning", "payment_date",
                              f"Payment date is in the future: {pmt.payment_date}")

            if not pmt.is_matched:
                ctx.add_issue(eid, self.name, "info", "is_matched",
                              "Payment is unmatched — no invoice linked")

            ctx.records_succeeded += 1


# =============================================
# Stage 2: Deduplication
# =============================================

def _normalize_for_compare(s: str) -> str:
    """Lowercase, strip whitespace and common suffixes for fuzzy compare."""
    if not s:
        return ""
    s = s.lower().strip()
    # Remove common company suffixes
    for suffix in [" llc", " ltd", " inc", " fzco", " fze", " fzc", " l.l.c",
                   " co.", " corp", " pvt", " gmbh", " sarl", " wll", " est"]:
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    # Remove punctuation
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _trigrams(s: str) -> Set[str]:
    """Generate character trigrams for similarity scoring."""
    if len(s) < 3:
        return {s}
    return {s[i: i + 3] for i in range(len(s) - 2)}


def _trigram_similarity(a: str, b: str) -> float:
    """Trigram-based similarity between 0.0 and 1.0."""
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return 0.0
    intersection = ta & tb
    union = ta | tb
    return len(intersection) / len(union)


class DeduplicationStage(PipelineStage):
    """
    Stage 2 — Detects potential duplicate records using fuzzy name matching
    and secondary field comparison (phone, email, tax_id).
    """

    name = "deduplication"
    SIMILARITY_THRESHOLD = 0.65  # Trigram similarity threshold

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        if ctx.entity_type != "customers":
            return  # Dedup primarily applies to customers

        result = await db.execute(
            select(Customer).where(Customer.tenant_id == ctx.tenant_id)
        )
        customers = result.scalars().all()

        # Build normalized lookup
        normalized = []
        for c in customers:
            normalized.append({
                "id": str(c.id),
                "name_norm": _normalize_for_compare(c.name),
                "name_ar": c.name_ar or "",
                "email": (c.email or "").lower().strip(),
                "phone": re.sub(r"[\s\-\(\)+]", "", c.phone or ""),
                "tax_id": (c.tax_id or "").strip(),
            })

        seen_pairs: Set[Tuple[str, str]] = set()

        for i, a in enumerate(normalized):
            for j, b in enumerate(normalized):
                if i >= j:
                    continue
                pair_key = tuple(sorted([a["id"], b["id"]]))
                if pair_key in seen_pairs:
                    continue

                confidence = 0.0
                match_reasons = []

                # Name similarity
                name_sim = _trigram_similarity(a["name_norm"], b["name_norm"])
                if name_sim >= self.SIMILARITY_THRESHOLD:
                    confidence = max(confidence, name_sim)
                    match_reasons.append(f"name similarity {name_sim:.0%}")

                # Exact secondary matches boost confidence
                if a["email"] and a["email"] == b["email"]:
                    confidence = max(confidence, 0.9)
                    match_reasons.append("same email")

                if a["phone"] and a["phone"] == b["phone"]:
                    confidence = max(confidence, 0.85)
                    match_reasons.append("same phone")

                if a["tax_id"] and a["tax_id"] == b["tax_id"]:
                    confidence = max(confidence, 0.95)
                    match_reasons.append("same tax ID")

                if confidence >= self.SIMILARITY_THRESHOLD:
                    seen_pairs.add(pair_key)
                    match = {
                        "entity_a": a["id"],
                        "entity_b": b["id"],
                        "confidence": round(confidence, 3),
                        "reasons": match_reasons,
                    }
                    ctx.dedup_matches.append(match)

                    severity = "warning" if confidence < 0.85 else "critical"
                    ctx.add_issue(
                        a["id"], self.name, severity, "name",
                        f"Potential duplicate: confidence {confidence:.0%} ({', '.join(match_reasons)})",
                        duplicate_of=b["id"],
                    )
                    ctx.add_issue(
                        b["id"], self.name, severity, "name",
                        f"Potential duplicate: confidence {confidence:.0%} ({', '.join(match_reasons)})",
                        duplicate_of=a["id"],
                    )


# =============================================
# Stage 3: Normalization
# =============================================

COUNTRY_PHONE_PREFIX = {
    "AE": "+971", "SA": "+966", "QA": "+974",
    "KW": "+965", "BH": "+973", "OM": "+968",
}


def _normalize_phone(phone: str, country: str = "AE") -> Optional[str]:
    """Normalize phone to E.164-like format (+971-X-XXXXXXX)."""
    if not phone:
        return None
    cleaned = re.sub(r"[\s\-\(\)]", "", phone)

    prefix = COUNTRY_PHONE_PREFIX.get(country, "+971")
    digits_prefix = prefix.replace("+", "")

    # Remove leading 00 or +
    if cleaned.startswith("00"):
        cleaned = cleaned[2:]
    elif cleaned.startswith("+"):
        cleaned = cleaned[1:]

    # Add country code if missing
    if not cleaned.startswith(digits_prefix):
        if cleaned.startswith("0"):
            cleaned = digits_prefix + cleaned[1:]
        else:
            cleaned = digits_prefix + cleaned

    # Format: +971-X-XXXXXXX
    if country == "AE" and len(cleaned) >= 11:
        return f"+{cleaned[:3]}-{cleaned[3]}-{cleaned[4:]}"
    return f"+{cleaned}"


def _normalize_name(name: str) -> str:
    """Standardize company name casing and common abbreviations."""
    if not name:
        return name

    # Title case with exceptions
    small_words = {"and", "or", "of", "the", "for", "in", "at", "to", "al", "el"}
    # Known abbreviations to keep uppercase
    abbreviations = {"llc", "ltd", "fzco", "fze", "fzc", "inc", "plc", "est",
                     "wll", "co", "uae", "gcc", "mena", "fmcg"}

    words = name.split()
    result = []
    for i, word in enumerate(words):
        lower = word.lower().rstrip(".,")
        if lower in abbreviations:
            result.append(word.upper())
        elif i > 0 and lower in small_words:
            result.append(lower)
        else:
            result.append(word.capitalize())

    return " ".join(result)


class NormalizationStage(PipelineStage):
    """
    Stage 3 — Standardizes phone numbers, company names, and country codes.
    Records all changes for audit trail without modifying records in-place
    (changes are applied only when user confirms via the API).
    """

    name = "normalization"

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        if ctx.entity_type == "customers":
            await self._normalize_customers(db, ctx)
        elif ctx.entity_type == "invoices":
            await self._normalize_invoices(db, ctx)

    async def _normalize_customers(self, db: AsyncSession, ctx: AgentContext) -> None:
        result = await db.execute(
            select(Customer).where(Customer.tenant_id == ctx.tenant_id)
        )
        customers = result.scalars().all()

        for cust in customers:
            eid = str(cust.id)

            # Name normalization
            normalized_name = _normalize_name(cust.name)
            if normalized_name != cust.name:
                ctx.add_change(eid, self.name, "name", cust.name, normalized_name)
                ctx.normalization_changes.append({
                    "entity_id": eid, "field": "name",
                    "old": cust.name, "new": normalized_name,
                })

            # Phone normalization
            if cust.phone:
                normalized_phone = _normalize_phone(cust.phone, cust.country or "AE")
                if normalized_phone and normalized_phone != cust.phone:
                    ctx.add_change(eid, self.name, "phone", cust.phone, normalized_phone)
                    ctx.normalization_changes.append({
                        "entity_id": eid, "field": "phone",
                        "old": cust.phone, "new": normalized_phone,
                    })

            # Email lowercase
            if cust.email:
                lower_email = cust.email.strip().lower()
                if lower_email != cust.email:
                    ctx.add_change(eid, self.name, "email", cust.email, lower_email)
                    ctx.normalization_changes.append({
                        "entity_id": eid, "field": "email",
                        "old": cust.email, "new": lower_email,
                    })

            # Country code standardization
            if cust.country:
                upper_country = cust.country.upper().strip()
                country_map = {"UAE": "AE", "KSA": "SA", "QATAR": "QA", "OMAN": "OM",
                               "BAHRAIN": "BH", "KUWAIT": "KW"}
                std_country = country_map.get(upper_country, upper_country)
                if std_country != cust.country:
                    ctx.add_change(eid, self.name, "country", cust.country, std_country)
                    ctx.normalization_changes.append({
                        "entity_id": eid, "field": "country",
                        "old": cust.country, "new": std_country,
                    })

    async def _normalize_invoices(self, db: AsyncSession, ctx: AgentContext) -> None:
        result = await db.execute(
            select(Invoice).where(Invoice.tenant_id == ctx.tenant_id)
        )
        invoices = result.scalars().all()

        for inv in invoices:
            eid = str(inv.id)

            # Currency code uppercase
            if inv.currency and inv.currency != inv.currency.upper():
                ctx.add_change(eid, self.name, "currency", inv.currency, inv.currency.upper())
                ctx.normalization_changes.append({
                    "entity_id": eid, "field": "currency",
                    "old": inv.currency, "new": inv.currency.upper(),
                })


# =============================================
# Stage 4: Anomaly Detection
# =============================================

class AnomalyDetectionStage(PipelineStage):
    """
    Stage 4 — Statistical anomaly detection using z-score analysis.
    Flags outliers in invoice amounts, payment patterns, and timing.
    """

    name = "anomaly_detection"
    Z_SCORE_THRESHOLD = 2.5  # Flag values > 2.5 standard deviations from mean

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        if ctx.entity_type == "invoices":
            await self._detect_invoice_anomalies(db, ctx)
        elif ctx.entity_type == "payments":
            await self._detect_payment_anomalies(db, ctx)
        elif ctx.entity_type == "customers":
            await self._detect_customer_anomalies(db, ctx)

    def _z_score(self, value: float, mean: float, std: float) -> float:
        if std == 0:
            return 0.0
        return abs(value - mean) / std

    async def _detect_invoice_anomalies(self, db: AsyncSession, ctx: AgentContext) -> None:
        result = await db.execute(
            select(Invoice).where(Invoice.tenant_id == ctx.tenant_id)
        )
        invoices = result.scalars().all()
        if len(invoices) < 5:
            return  # Not enough data for statistical analysis

        amounts = [float(inv.amount) for inv in invoices if inv.amount]
        mean_amt = sum(amounts) / len(amounts) if amounts else 0
        std_amt = math.sqrt(sum((a - mean_amt) ** 2 for a in amounts) / len(amounts)) if len(amounts) > 1 else 0

        for inv in invoices:
            eid = str(inv.id)

            # Amount outlier
            if inv.amount and std_amt > 0:
                z = self._z_score(float(inv.amount), mean_amt, std_amt)
                if z > self.Z_SCORE_THRESHOLD:
                    anomaly = {
                        "entity_id": eid, "type": "amount_outlier",
                        "z_score": round(z, 2),
                        "value": str(inv.amount), "mean": round(mean_amt, 2),
                        "message": f"Invoice amount {inv.amount} is {z:.1f}σ from mean ({mean_amt:,.0f})",
                    }
                    ctx.anomalies_detected.append(anomaly)
                    ctx.add_issue(eid, self.name, "warning", "amount",
                                  anomaly["message"], z_score=round(z, 2))

            # Round-number check (potential manual entry / estimation)
            if inv.amount and float(inv.amount) >= 1000:
                amt_str = f"{float(inv.amount):.2f}"
                if amt_str.endswith("000.00") or amt_str.endswith("500.00"):
                    ctx.add_issue(eid, self.name, "info", "amount",
                                  f"Suspiciously round amount: {inv.amount} (may be estimated)")

            # Same-day duplicate check (same customer, same amount, same date)
            for other in invoices:
                if other.id == inv.id:
                    continue
                if (other.customer_id == inv.customer_id
                        and other.amount == inv.amount
                        and other.invoice_date == inv.invoice_date
                        and other.invoice_number != inv.invoice_number):
                    ctx.add_issue(eid, self.name, "warning", "invoice_number",
                                  f"Same customer, amount, and date as invoice {other.invoice_number} — possible duplicate",
                                  related_invoice=str(other.id))

    async def _detect_payment_anomalies(self, db: AsyncSession, ctx: AgentContext) -> None:
        result = await db.execute(
            select(Payment).where(Payment.tenant_id == ctx.tenant_id)
        )
        payments = result.scalars().all()
        if len(payments) < 3:
            return

        amounts = [float(p.amount) for p in payments if p.amount]
        mean_amt = sum(amounts) / len(amounts) if amounts else 0
        std_amt = math.sqrt(sum((a - mean_amt) ** 2 for a in amounts) / len(amounts)) if len(amounts) > 1 else 0

        for pmt in payments:
            eid = str(pmt.id)

            if pmt.amount and std_amt > 0:
                z = self._z_score(float(pmt.amount), mean_amt, std_amt)
                if z > self.Z_SCORE_THRESHOLD:
                    ctx.anomalies_detected.append({
                        "entity_id": eid, "type": "payment_amount_outlier",
                        "z_score": round(z, 2), "value": str(pmt.amount),
                    })
                    ctx.add_issue(eid, self.name, "warning", "amount",
                                  f"Payment amount {pmt.amount} is {z:.1f}σ from mean ({mean_amt:,.0f})")

    async def _detect_customer_anomalies(self, db: AsyncSession, ctx: AgentContext) -> None:
        result = await db.execute(
            select(Customer).where(Customer.tenant_id == ctx.tenant_id)
        )
        customers = result.scalars().all()
        if len(customers) < 3:
            return

        credit_limits = [float(c.credit_limit) for c in customers if c.credit_limit and c.credit_limit > 0]
        if not credit_limits:
            return
        mean_cl = sum(credit_limits) / len(credit_limits)
        std_cl = math.sqrt(sum((c - mean_cl) ** 2 for c in credit_limits) / len(credit_limits)) if len(credit_limits) > 1 else 0

        for cust in customers:
            eid = str(cust.id)
            if cust.credit_limit and cust.credit_limit > 0 and std_cl > 0:
                z = self._z_score(float(cust.credit_limit), mean_cl, std_cl)
                if z > self.Z_SCORE_THRESHOLD:
                    ctx.anomalies_detected.append({
                        "entity_id": eid, "type": "credit_limit_outlier",
                        "z_score": round(z, 2), "value": str(cust.credit_limit),
                    })
                    ctx.add_issue(eid, self.name, "warning", "credit_limit",
                                  f"Credit limit {cust.credit_limit:,.0f} is {z:.1f}σ from mean ({mean_cl:,.0f})")


# =============================================
# Stage 5: Enrichment
# =============================================

class EnrichmentStage(PipelineStage):
    """
    Stage 5 — Fills gaps using cross-reference and inference.
    - Infer territory from city/region
    - Infer segment from credit limit brackets
    - Fill missing payment_terms from customer defaults
    - Calculate data_quality_score per entity
    """

    name = "enrichment"

    # Territory inference map for GCC
    CITY_TERRITORY_MAP = {
        # UAE
        "dubai": "Dubai", "abu dhabi": "Abu Dhabi", "sharjah": "Sharjah",
        "ajman": "Ajman", "ras al khaimah": "RAK", "fujairah": "Fujairah",
        "umm al quwain": "UAQ", "al ain": "Abu Dhabi",
        # KSA
        "riyadh": "Central", "jeddah": "Western", "dammam": "Eastern",
        "khobar": "Eastern", "makkah": "Western", "madinah": "Western",
        # QA
        "doha": "Qatar",
    }

    SEGMENT_BRACKETS = [
        (0, 50_000, "micro"),
        (50_000, 250_000, "sme"),
        (250_000, 1_000_000, "mid_market"),
        (1_000_000, 5_000_000, "enterprise"),
        (5_000_000, float("inf"), "key_account"),
    ]

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        if ctx.entity_type == "customers":
            await self._enrich_customers(db, ctx)
        elif ctx.entity_type == "invoices":
            await self._enrich_invoices(db, ctx)

    async def _enrich_customers(self, db: AsyncSession, ctx: AgentContext) -> None:
        result = await db.execute(
            select(Customer).where(Customer.tenant_id == ctx.tenant_id)
        )
        customers = result.scalars().all()

        for cust in customers:
            eid = str(cust.id)

            # Infer territory from city
            if not cust.territory and cust.city:
                city_lower = cust.city.lower().strip()
                inferred_territory = self.CITY_TERRITORY_MAP.get(city_lower)
                if inferred_territory:
                    ctx.add_change(eid, self.name, "territory", None, inferred_territory)
                    ctx.enrichments_applied.append({
                        "entity_id": eid, "field": "territory",
                        "value": inferred_territory, "source": "city_inference",
                    })

            # Infer segment from credit limit
            if not cust.segment and cust.credit_limit:
                cl = float(cust.credit_limit)
                for low, high, segment in self.SEGMENT_BRACKETS:
                    if low <= cl < high:
                        ctx.add_change(eid, self.name, "segment", None, segment)
                        ctx.enrichments_applied.append({
                            "entity_id": eid, "field": "segment",
                            "value": segment, "source": "credit_limit_bracket",
                        })
                        break

            # Infer region from country
            if not cust.region and cust.country:
                region_map = {
                    "AE": "UAE", "SA": "KSA", "QA": "Qatar",
                    "KW": "Kuwait", "BH": "Bahrain", "OM": "Oman",
                }
                inferred_region = region_map.get(cust.country)
                if inferred_region:
                    ctx.add_change(eid, self.name, "region", None, inferred_region)
                    ctx.enrichments_applied.append({
                        "entity_id": eid, "field": "region",
                        "value": inferred_region, "source": "country_mapping",
                    })

            # Calculate and store final quality score for this entity
            entity_result = ctx.get_entity_result(eid)
            score = entity_result["quality_score"]
            # Boost score if enrichments were applied
            enrichments_for_entity = [
                e for e in ctx.enrichments_applied if e["entity_id"] == eid
            ]
            if enrichments_for_entity:
                score = min(100, score + len(enrichments_for_entity) * 3)
                entity_result["quality_score"] = score

    async def _enrich_invoices(self, db: AsyncSession, ctx: AgentContext) -> None:
        # Recalculate aging for all invoices (in case stale)
        result = await db.execute(
            select(Invoice).where(Invoice.tenant_id == ctx.tenant_id)
        )
        invoices = result.scalars().all()

        for inv in invoices:
            eid = str(inv.id)
            if inv.due_date:
                today = date.today()
                if inv.due_date < today:
                    days = (today - inv.due_date).days
                    if days <= 30:
                        expected_bucket = "1-30"
                    elif days <= 60:
                        expected_bucket = "31-60"
                    elif days <= 90:
                        expected_bucket = "61-90"
                    else:
                        expected_bucket = "90+"
                else:
                    days = 0
                    expected_bucket = "current"

                if inv.aging_bucket != expected_bucket:
                    ctx.add_change(eid, self.name, "aging_bucket", inv.aging_bucket, expected_bucket)
                    ctx.enrichments_applied.append({
                        "entity_id": eid, "field": "aging_bucket",
                        "value": expected_bucket, "source": "recalculated",
                    })

                if inv.days_overdue != days:
                    ctx.add_change(eid, self.name, "days_overdue", inv.days_overdue, days)


# =============================================
# Assemble the Agent
# =============================================

class DataQualityAgent(BaseAgent):
    """
    5-stage Data Quality Agent for Sales IQ.
    Pipeline: Validate → Deduplicate → Normalize → Anomaly Detect → Enrich
    """

    agent_name = "data_quality"
    stages = [
        ValidationStage(),
        DeduplicationStage(),
        NormalizationStage(),
        AnomalyDetectionStage(),
        EnrichmentStage(),
    ]


# Singleton for import convenience
data_quality_agent = DataQualityAgent()
