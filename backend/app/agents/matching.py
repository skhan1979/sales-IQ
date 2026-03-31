"""
Sales IQ - Matching Agent
Intelligent payment-to-invoice matching using fuzzy logic,
reference parsing, amount comparison, and confidence scoring.
"""

import re
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent, PipelineStage, AgentContext
from app.models.business import Customer, Invoice, Payment, InvoiceStatus


# ── Stage 1: Candidate Selection ─────────────────────────────────────

class CandidateSelectionStage(PipelineStage):
    """Identify potential invoice matches for each unmatched payment."""

    name = "candidate_selection"

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        # Load all unmatched payments
        pay_result = await db.execute(
            select(Payment).where(
                Payment.tenant_id == ctx.tenant_id,
                Payment.invoice_id.is_(None),
                Payment.is_matched == False,
            )
        )
        unmatched_payments = pay_result.scalars().all()
        ctx.records_processed = len(unmatched_payments)

        if not unmatched_payments:
            ctx.extra["no_unmatched"] = True
            return

        # Load all open invoices
        inv_result = await db.execute(
            select(Invoice).where(
                Invoice.tenant_id == ctx.tenant_id,
                Invoice.status.in_(["open", "overdue", "partially_paid"]),
            )
        )
        all_open_invoices = inv_result.scalars().all()

        # Index invoices by customer_id for fast lookup
        inv_by_customer: Dict[str, List] = {}
        for inv in all_open_invoices:
            cust_key = str(inv.customer_id)
            if cust_key not in inv_by_customer:
                inv_by_customer[cust_key] = []
            inv_by_customer[cust_key].append(inv)

        # Index invoices by invoice_number for reference matching
        inv_by_number: Dict[str, Invoice] = {}
        for inv in all_open_invoices:
            if inv.invoice_number:
                inv_by_number[inv.invoice_number.strip().upper()] = inv

        # For each unmatched payment, find candidates
        for payment in unmatched_payments:
            pid = str(payment.id)
            ctx.get_entity_result(pid)

            candidates = []
            cust_key = str(payment.customer_id)

            # Primary: same-customer invoices
            customer_invoices = inv_by_customer.get(cust_key, [])

            for inv in customer_invoices:
                candidate = {
                    "invoice_id": str(inv.id),
                    "invoice_number": inv.invoice_number,
                    "invoice_amount": float(inv.amount or 0),
                    "amount_remaining": float(inv.amount_remaining or inv.amount or 0),
                    "invoice_date": str(inv.invoice_date) if inv.invoice_date else None,
                    "due_date": str(inv.due_date) if inv.due_date else None,
                    "status": str(inv.status.value) if inv.status else "open",
                    "match_signals": [],
                }
                candidates.append(candidate)

            # Secondary: reference-based matching (cross-customer)
            ref_text = (payment.reference_number or "") + " " + (payment.bank_reference or "") + " " + (payment.notes or "")
            if ref_text.strip():
                extracted_refs = self._extract_invoice_refs(ref_text)
                for ref in extracted_refs:
                    ref_upper = ref.strip().upper()
                    if ref_upper in inv_by_number:
                        inv = inv_by_number[ref_upper]
                        # Check if already in candidates
                        existing = [c for c in candidates if c["invoice_id"] == str(inv.id)]
                        if not existing:
                            candidates.append({
                                "invoice_id": str(inv.id),
                                "invoice_number": inv.invoice_number,
                                "invoice_amount": float(inv.amount or 0),
                                "amount_remaining": float(inv.amount_remaining or inv.amount or 0),
                                "invoice_date": str(inv.invoice_date) if inv.invoice_date else None,
                                "due_date": str(inv.due_date) if inv.due_date else None,
                                "status": str(inv.status.value) if inv.status else "open",
                                "match_signals": ["reference_cross_customer"],
                            })

            er = ctx.entity_results[pid]
            er["payment"] = payment
            er["candidates"] = candidates
            er["ref_text"] = ref_text

    @staticmethod
    def _extract_invoice_refs(text: str) -> List[str]:
        """Extract potential invoice number references from payment text."""
        refs = []
        # Common patterns: INV-XXXX, SI-XXXX, #XXXX, SINV/XXXX
        patterns = [
            r'(?:INV|SI|SINV|SO|SIV|PI)[/-]?\s*(\d{3,})',
            r'#\s*(\d{4,})',
            r'\b(\d{6,})\b',  # Long numbers likely are invoice refs
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                refs.append(m)
        # Also try the full text segments that look like invoice numbers
        segments = re.findall(r'[A-Z]{2,4}[-/]\d{3,}', text, re.IGNORECASE)
        refs.extend(segments)
        return list(set(refs))


# ── Stage 2: Confidence Scoring ──────────────────────────────────────

class ConfidenceScoringStage(PipelineStage):
    """Score each candidate match by amount, reference, and date proximity."""

    name = "confidence_scoring"

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        amount_tolerance_pct = ctx.extra.get("config", {}).get("amount_tolerance_pct", 2.0)
        date_window_days = ctx.extra.get("config", {}).get("date_window_days", 30)

        for entity_id, er in ctx.entity_results.items():
            payment = er.get("payment")
            candidates = er.get("candidates", [])
            ref_text = er.get("ref_text", "")

            if not payment or not candidates:
                continue

            pay_amount = float(payment.amount or 0)
            pay_date = payment.payment_date

            for candidate in candidates:
                confidence = 0.0
                signals = candidate.get("match_signals", [])

                inv_amount = candidate["amount_remaining"]
                inv_number = candidate.get("invoice_number", "")

                # ── Amount Match (max 0.40) ──
                if pay_amount > 0 and inv_amount > 0:
                    amount_diff_pct = abs(pay_amount - inv_amount) / inv_amount * 100

                    if amount_diff_pct == 0:
                        confidence += 0.40
                        signals.append("exact_amount_match")
                    elif amount_diff_pct <= amount_tolerance_pct:
                        confidence += 0.35
                        signals.append(f"amount_within_{amount_tolerance_pct}%")
                    elif amount_diff_pct <= 5:
                        confidence += 0.20
                        signals.append("amount_within_5%")
                    elif pay_amount < inv_amount:
                        # Partial payment
                        ratio = pay_amount / inv_amount
                        if ratio > 0.5:
                            confidence += 0.15
                            signals.append("partial_payment_likely")
                        elif ratio > 0.1:
                            confidence += 0.05
                            signals.append("partial_payment_possible")

                # ── Reference Match (max 0.35) ──
                if inv_number and ref_text:
                    ref_upper = ref_text.upper()
                    inv_upper = inv_number.upper()

                    if inv_upper in ref_upper:
                        confidence += 0.35
                        signals.append("invoice_number_in_reference")
                    else:
                        # Check numeric portion
                        inv_nums = re.findall(r'\d{3,}', inv_upper)
                        for num in inv_nums:
                            if num in ref_upper:
                                confidence += 0.25
                                signals.append("invoice_digits_in_reference")
                                break

                # Cross-customer reference match bonus
                if "reference_cross_customer" in signals:
                    confidence += 0.30
                    signals.append("cross_customer_ref_match")

                # ── Date Proximity (max 0.15) ──
                if pay_date and candidate.get("due_date"):
                    try:
                        due = date.fromisoformat(candidate["due_date"])
                        days_diff = abs((pay_date - due).days)
                        if days_diff <= 3:
                            confidence += 0.15
                            signals.append("payment_near_due_date")
                        elif days_diff <= 14:
                            confidence += 0.10
                            signals.append("payment_within_2_weeks")
                        elif days_diff <= date_window_days:
                            confidence += 0.05
                            signals.append("payment_within_window")
                    except (ValueError, TypeError):
                        pass

                # ── Single-invoice customer bonus (max 0.10) ──
                if len(candidates) == 1:
                    confidence += 0.10
                    signals.append("only_open_invoice")

                candidate["confidence"] = round(min(1.0, confidence), 3)
                candidate["match_signals"] = signals

            # Sort candidates by confidence
            candidates.sort(key=lambda c: c["confidence"], reverse=True)
            er["candidates"] = candidates


# ── Stage 3: Auto Match ──────────────────────────────────────────────

class AutoMatchStage(PipelineStage):
    """Apply matches above the confidence threshold."""

    name = "auto_match"

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        threshold = ctx.extra.get("config", {}).get("auto_match_threshold", 0.70)
        auto_matched = 0
        matched_amount = 0.0

        for entity_id, er in ctx.entity_results.items():
            payment = er.get("payment")
            candidates = er.get("candidates", [])

            if not payment or not candidates:
                continue

            top_candidate = candidates[0] if candidates else None
            if not top_candidate or top_candidate["confidence"] < threshold:
                continue

            # Check there's a clear winner (top confidence significantly higher than 2nd)
            if len(candidates) > 1:
                second_conf = candidates[1]["confidence"]
                if second_conf > 0.5 and (top_candidate["confidence"] - second_conf) < 0.15:
                    # Ambiguous — skip auto-match, send to exception queue
                    er["match_status"] = "ambiguous"
                    continue

            # Apply the match
            from uuid import UUID as UUIDType
            invoice_id = UUIDType(top_candidate["invoice_id"])

            # Load the actual invoice
            inv_result = await db.execute(
                select(Invoice).where(Invoice.id == invoice_id)
            )
            invoice = inv_result.scalar_one_or_none()

            if not invoice:
                continue

            payment.invoice_id = invoice_id
            payment.is_matched = True
            payment.match_confidence = top_candidate["confidence"]
            payment.matched_at = date.today().isoformat()

            # Update invoice payment tracking
            pay_amount = float(payment.amount or 0)
            current_paid = float(invoice.amount_paid or 0)
            invoice.amount_paid = current_paid + pay_amount
            invoice.amount_remaining = max(0, float(invoice.amount or 0) - float(invoice.amount_paid))

            if invoice.amount_remaining <= 0.01:
                invoice.status = InvoiceStatus.PAID
            elif invoice.amount_paid > 0:
                invoice.status = InvoiceStatus.PARTIALLY_PAID

            auto_matched += 1
            matched_amount += pay_amount
            er["match_status"] = "auto_matched"
            er["matched_invoice"] = top_candidate["invoice_number"]
            er["match_confidence"] = top_candidate["confidence"]

            ctx.records_succeeded += 1
            ctx.add_change(
                entity_id, "auto_match", "invoice_id",
                None, top_candidate["invoice_number"],
                confidence=top_candidate["confidence"],
                signals=top_candidate["match_signals"],
            )

        await db.flush()

        ctx.extra["auto_matched"] = auto_matched
        ctx.extra["matched_amount"] = round(matched_amount, 2)


# ── Stage 4: Exception Queue ────────────────────────────────────────

class ExceptionQueueStage(PipelineStage):
    """Flag ambiguous or low-confidence matches for manual review."""

    name = "exception_queue"

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        exceptions = []

        for entity_id, er in ctx.entity_results.items():
            payment = er.get("payment")
            candidates = er.get("candidates", [])
            match_status = er.get("match_status")

            if not payment or match_status == "auto_matched":
                continue

            if not candidates:
                # No candidates at all
                exceptions.append({
                    "payment_id": str(payment.id),
                    "payment_amount": float(payment.amount or 0),
                    "payment_date": str(payment.payment_date) if payment.payment_date else None,
                    "customer_id": str(payment.customer_id),
                    "reason": "no_candidates",
                    "description": "No open invoices found for this customer",
                    "top_candidates": [],
                })
                ctx.add_issue(
                    entity_id, "exception_queue", "info",
                    "no_match_candidates",
                    f"Payment of {payment.amount} has no matching invoice candidates",
                )
            elif match_status == "ambiguous":
                # Multiple close candidates
                top_3 = candidates[:3]
                exceptions.append({
                    "payment_id": str(payment.id),
                    "payment_amount": float(payment.amount or 0),
                    "payment_date": str(payment.payment_date) if payment.payment_date else None,
                    "customer_id": str(payment.customer_id),
                    "reason": "ambiguous",
                    "description": f"Multiple invoices match with similar confidence ({top_3[0]['confidence']:.0%} vs {top_3[1]['confidence']:.0%})",
                    "top_candidates": top_3,
                })
                ctx.add_issue(
                    entity_id, "exception_queue", "warning",
                    "ambiguous_match",
                    f"Payment of {payment.amount} has multiple possible matches",
                )
            else:
                # Low confidence
                top_3 = candidates[:3]
                best_conf = top_3[0]["confidence"] if top_3 else 0
                exceptions.append({
                    "payment_id": str(payment.id),
                    "payment_amount": float(payment.amount or 0),
                    "payment_date": str(payment.payment_date) if payment.payment_date else None,
                    "customer_id": str(payment.customer_id),
                    "reason": "low_confidence",
                    "description": f"Best match confidence ({best_conf:.0%}) below threshold",
                    "top_candidates": top_3,
                })
                if best_conf > 0.3:
                    ctx.add_issue(
                        entity_id, "exception_queue", "info",
                        "low_confidence_match",
                        f"Payment of {payment.amount} has a possible but uncertain match "
                        f"({best_conf:.0%} confidence)",
                    )

            ctx.records_failed += 1

        ctx.extra["exception_queue"] = exceptions
        ctx.extra["exceptions_count"] = len(exceptions)


# ── Agent ─────────────────────────────────────────────────────────────

class MatchingAgent(BaseAgent):
    """Intelligent payment-to-invoice matching agent."""

    agent_name = "matching_agent"
    stages = [
        CandidateSelectionStage(),
        ConfidenceScoringStage(),
        AutoMatchStage(),
        ExceptionQueueStage(),
    ]


# Singleton
matching_agent = MatchingAgent()
