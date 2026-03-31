"""
Sales IQ - Intelligence Layer Service
Day 14: Health scores, AI credit recommendations, credit exposure,
        Customer 360 insights, chat engine.
"""

import math
import random
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import (
    Customer, Invoice, Payment, Dispute, CollectionActivity,
    CreditLimitRequest, Briefing,
    CustomerStatus, InvoiceStatus, DisputeStatus, CreditApprovalStatus,
    CollectionAction, ECLStage,
)


# ── In-memory stores ──

_health_scores: Dict[str, dict] = {}          # customer_id -> latest score
_health_history: Dict[str, List[dict]] = {}   # customer_id -> list of scores
_chat_conversations: Dict[str, dict] = {}     # conversation_id -> conversation


# ── Helpers ──

def _score_to_grade(score: float) -> str:
    if score >= 80:
        return "A"
    elif score >= 65:
        return "B"
    elif score >= 50:
        return "C"
    elif score >= 35:
        return "D"
    return "F"


def _determine_trend(current: float, previous: Optional[float]) -> str:
    if previous is None:
        return "stable"
    diff = current - previous
    if diff > 3:
        return "improving"
    elif diff < -3:
        return "declining"
    return "stable"


class IntelligenceEngine:
    """Unified intelligence service covering health scores, credit, 360 view, and chat."""

    # ═══════════════════════════════════════════
    # HEALTH SCORE ENGINE
    # ═══════════════════════════════════════════

    async def calculate_health_score(
        self, db: AsyncSession, tenant_id: UUID, customer_id: UUID,
        weights: Optional[dict] = None,
    ) -> dict:
        """Calculate composite health score for a customer."""
        w = weights or {"payment": 0.40, "engagement": 0.20, "order_trend": 0.30, "risk_flags": 0.10}

        customer = (await db.execute(
            select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

        # ── Payment Score (0-100) ──
        invoices = (await db.execute(
            select(Invoice).where(
                Invoice.customer_id == customer_id,
                Invoice.tenant_id == tenant_id,
                Invoice.is_deleted == False,
            )
        )).scalars().all()

        payment_score = 70.0
        payment_factors = []

        if invoices:
            total_inv = len(invoices)
            paid = sum(1 for i in invoices if i.status in (InvoiceStatus.PAID,))
            overdue = sum(1 for i in invoices if i.status == InvoiceStatus.OVERDUE)
            avg_days_overdue = 0
            overdue_invoices = [i for i in invoices if i.days_overdue and i.days_overdue > 0]
            if overdue_invoices:
                avg_days_overdue = sum(i.days_overdue for i in overdue_invoices) / len(overdue_invoices)

            pay_rate = paid / total_inv * 100 if total_inv > 0 else 0
            payment_score = min(100, max(0, pay_rate - avg_days_overdue * 0.5))

            if pay_rate >= 90:
                payment_factors.append(f"Excellent payment rate: {pay_rate:.0f}%")
            elif pay_rate >= 70:
                payment_factors.append(f"Good payment rate: {pay_rate:.0f}%")
            else:
                payment_factors.append(f"Low payment rate: {pay_rate:.0f}%")

            if overdue > 0:
                payment_factors.append(f"{overdue} overdue invoice(s), avg {avg_days_overdue:.0f} days late")
            if avg_days_overdue > 60:
                payment_score = max(0, payment_score - 20)
                payment_factors.append("Severely overdue: 60+ days average")

        # ── Engagement Score (0-100) ──
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        activities = (await db.execute(
            select(func.count()).select_from(CollectionActivity).where(
                CollectionActivity.customer_id == customer_id,
                CollectionActivity.tenant_id == tenant_id,
                CollectionActivity.action_date >= recent_cutoff.date(),
            )
        )).scalar() or 0

        engagement_score = 50.0
        engagement_factors = []

        recent_payments = (await db.execute(
            select(func.count()).select_from(Payment).where(
                Payment.customer_id == customer_id,
                Payment.tenant_id == tenant_id,
                Payment.payment_date >= recent_cutoff.date(),
            )
        )).scalar() or 0

        if recent_payments >= 3:
            engagement_score = 90.0
            engagement_factors.append(f"Active: {recent_payments} payments in last 90 days")
        elif recent_payments >= 1:
            engagement_score = 70.0
            engagement_factors.append(f"Moderate: {recent_payments} payment(s) in last 90 days")
        else:
            engagement_score = 30.0
            engagement_factors.append("No payments in last 90 days")

        if activities > 5:
            engagement_score = min(100, engagement_score + 10)
            engagement_factors.append(f"High interaction: {activities} collection activities")

        # ── Order Trend Score (0-100) ──
        total_amount = sum(float(i.amount or 0) for i in invoices)
        recent_invoices = [i for i in invoices if i.invoice_date and i.invoice_date >= recent_cutoff.date()]
        recent_amount = sum(float(i.amount or 0) for i in recent_invoices)

        order_trend_score = 50.0
        order_factors = []

        if invoices:
            if recent_amount > total_amount * 0.4:
                order_trend_score = 85.0
                order_factors.append(f"Strong recent activity: {len(recent_invoices)} invoices ({recent_amount:,.0f})")
            elif recent_amount > total_amount * 0.2:
                order_trend_score = 65.0
                order_factors.append("Moderate recent ordering activity")
            else:
                order_trend_score = 35.0
                order_factors.append("Declining order volume in recent period")
        else:
            order_factors.append("No invoice history available")

        # ── Risk Flag Score (0-100, higher = less risky) ──
        risk_flag_score = 80.0
        risk_factors = []

        if customer.credit_hold:
            risk_flag_score -= 30
            risk_factors.append("Customer on credit hold")

        ecl = str(customer.ecl_stage) if customer.ecl_stage else "stage_1"
        if "stage_3" in ecl:
            risk_flag_score -= 30
            risk_factors.append("ECL Stage 3 - credit impaired")
        elif "stage_2" in ecl:
            risk_flag_score -= 15
            risk_factors.append("ECL Stage 2 - significant risk increase")

        if customer.risk_score and float(customer.risk_score) > 70:
            risk_flag_score -= 20
            risk_factors.append(f"High risk score: {float(customer.risk_score):.0f}")

        open_disputes = (await db.execute(
            select(func.count()).select_from(Dispute).where(
                Dispute.customer_id == customer_id,
                Dispute.tenant_id == tenant_id,
                Dispute.status.in_([DisputeStatus.OPEN, DisputeStatus.IN_REVIEW, DisputeStatus.ESCALATED]),
            )
        )).scalar() or 0

        if open_disputes > 2:
            risk_flag_score -= 15
            risk_factors.append(f"{open_disputes} open disputes")
        elif open_disputes > 0:
            risk_flag_score -= 5
            risk_factors.append(f"{open_disputes} open dispute(s)")

        risk_flag_score = max(0, min(100, risk_flag_score))
        if not risk_factors:
            risk_factors.append("No significant risk flags")

        # ── Composite Score ──
        composite = (
            payment_score * w["payment"]
            + engagement_score * w["engagement"]
            + order_trend_score * w["order_trend"]
            + risk_flag_score * w["risk_flags"]
        )
        composite = round(min(100, max(0, composite)), 1)
        grade = _score_to_grade(composite)

        # Look up previous score
        cid = str(customer_id)
        previous = _health_scores.get(cid, {}).get("composite_score")
        trend = _determine_trend(composite, previous)

        # Store result
        now_iso = datetime.now(timezone.utc).isoformat()
        result = {
            "customer_id": cid,
            "customer_name": customer.name,
            "composite_score": composite,
            "grade": grade,
            "trend": trend,
            "breakdown": {
                "payment_score": round(payment_score, 1),
                "engagement_score": round(engagement_score, 1),
                "order_trend_score": round(order_trend_score, 1),
                "risk_flag_score": round(risk_flag_score, 1),
                "payment_factors": payment_factors,
                "engagement_factors": engagement_factors,
                "order_trend_factors": order_factors,
                "risk_factors": risk_factors,
            },
            "weights": w,
            "previous_score": previous,
            "score_change": round(composite - previous, 1) if previous is not None else None,
            "calculated_at": now_iso,
        }
        _health_scores[cid] = result

        # Append to history
        if cid not in _health_history:
            _health_history[cid] = []
        _health_history[cid].append({
            "date": now_iso,
            "composite_score": composite,
            "grade": grade,
        })

        # Update customer risk_score in DB
        customer.risk_score = Decimal(str(round(100 - composite, 1)))
        await db.commit()

        return result

    async def batch_health_scores(
        self, db: AsyncSession, tenant_id: UUID,
        customer_ids: Optional[List[UUID]] = None,
        weights: Optional[dict] = None,
    ) -> dict:
        """Calculate health scores for multiple customers."""
        start = time.time()

        query = select(Customer).where(Customer.tenant_id == tenant_id, Customer.is_deleted == False)
        if customer_ids:
            query = query.where(Customer.id.in_(customer_ids))
        customers = (await db.execute(query)).scalars().all()

        scores = []
        for cust in customers:
            try:
                score = await self.calculate_health_score(db, tenant_id, cust.id, weights)
                scores.append(score)
            except Exception:
                continue

        grade_dist = defaultdict(int)
        for s in scores:
            grade_dist[s["grade"]] += 1

        avg_score = sum(s["composite_score"] for s in scores) / len(scores) if scores else 0

        # Find top improvers / decliners
        with_change = [s for s in scores if s.get("score_change") is not None]
        improvers = sorted(with_change, key=lambda x: x["score_change"], reverse=True)[:5]
        decliners = sorted(with_change, key=lambda x: x["score_change"])[:5]

        duration_ms = int((time.time() - start) * 1000)
        return {
            "customers_processed": len(scores),
            "avg_score": round(avg_score, 1),
            "grade_distribution": dict(grade_dist),
            "top_improvers": [{"customer_name": s["customer_name"], "score": s["composite_score"],
                               "change": s["score_change"]} for s in improvers],
            "top_decliners": [{"customer_name": s["customer_name"], "score": s["composite_score"],
                               "change": s["score_change"]} for s in decliners],
            "duration_ms": duration_ms,
        }

    def get_health_history(self, customer_id: str) -> Optional[dict]:
        """Get health score history for a customer."""
        cid = str(customer_id)
        score = _health_scores.get(cid)
        history = _health_history.get(cid, [])
        if not score:
            return None
        return {
            "customer_id": cid,
            "customer_name": score["customer_name"],
            "history": history,
            "current_score": score["composite_score"],
            "current_grade": score["grade"],
            "trend": score["trend"],
        }

    # ═══════════════════════════════════════════
    # AI CREDIT RECOMMENDATIONS
    # ═══════════════════════════════════════════

    async def generate_credit_recommendations(
        self, db: AsyncSession, tenant_id: UUID, limit: int = 20,
    ) -> dict:
        """Generate AI credit limit recommendations for all customers."""
        customers = (await db.execute(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                Customer.is_deleted == False,
                Customer.status != CustomerStatus.INACTIVE,
            )
        )).scalars().all()

        recommendations = []
        for cust in customers:
            current_limit = float(cust.credit_limit or 0)
            if current_limit <= 0:
                continue

            utilization = float(cust.credit_utilization or 0)
            util_pct = (utilization / current_limit * 100) if current_limit > 0 else 0
            risk = float(cust.risk_score or 50)
            health = _health_scores.get(str(cust.id), {}).get("composite_score", 50.0)

            # Simulated XGBoost-style logic
            reasoning = []
            confidence = 0.70

            # Payment behaviour analysis
            invoices = (await db.execute(
                select(Invoice).where(
                    Invoice.customer_id == cust.id,
                    Invoice.tenant_id == tenant_id,
                    Invoice.is_deleted == False,
                )
            )).scalars().all()

            paid_on_time = sum(1 for i in invoices if i.status == InvoiceStatus.PAID and (i.days_overdue or 0) <= 0)
            total_inv = len(invoices) or 1
            on_time_rate = paid_on_time / total_inv * 100

            # Recommendation logic
            recommended = current_limit
            change_type = "hold"

            if health >= 75 and util_pct > 80 and on_time_rate > 70:
                increase = min(0.30, (util_pct - 70) / 100)
                recommended = round(current_limit * (1 + increase) / 10000) * 10000
                change_type = "increase"
                reasoning.append(f"High utilization ({util_pct:.0f}%) with good health score ({health:.0f})")
                reasoning.append(f"On-time payment rate: {on_time_rate:.0f}%")
                confidence = 0.80 + (health - 75) / 100

            elif health < 40 or risk > 75:
                decrease = min(0.30, risk / 200)
                recommended = max(utilization * 1.1, round(current_limit * (1 - decrease) / 10000) * 10000)
                change_type = "decrease"
                reasoning.append(f"Elevated risk score ({risk:.0f}) or low health ({health:.0f})")
                if on_time_rate < 50:
                    reasoning.append(f"Poor on-time rate: {on_time_rate:.0f}%")
                confidence = 0.65

            elif util_pct > 90 and health >= 50:
                increase = 0.15
                recommended = round(current_limit * (1 + increase) / 10000) * 10000
                change_type = "increase"
                reasoning.append(f"Very high utilization ({util_pct:.0f}%) with acceptable health")
                confidence = 0.70

            else:
                reasoning.append(f"Utilization ({util_pct:.0f}%) and health ({health:.0f}) within normal range")
                confidence = 0.85

            change_amount = recommended - current_limit
            change_pct = (change_amount / current_limit * 100) if current_limit > 0 else 0

            recommendations.append({
                "customer_id": str(cust.id),
                "customer_name": cust.name,
                "current_limit": current_limit,
                "recommended_limit": recommended,
                "change_type": change_type,
                "change_amount": round(change_amount, 2),
                "change_pct": round(change_pct, 1),
                "confidence": round(min(1.0, confidence), 2),
                "reasoning": reasoning,
                "risk_score": risk,
                "health_score": health,
                "utilization_pct": round(util_pct, 1),
                "model_version": "v1.0-simulated-xgboost",
            })

        recommendations.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
        top = recommendations[:limit]

        increases = [r for r in recommendations if r["change_type"] == "increase"]
        decreases = [r for r in recommendations if r["change_type"] == "decrease"]
        holds = [r for r in recommendations if r["change_type"] == "hold"]

        summary = {
            "total_customers": len(recommendations),
            "increases": len(increases),
            "decreases": len(decreases),
            "holds": len(holds),
            "total_increase_amount": sum(r["change_amount"] for r in increases),
            "total_decrease_amount": sum(r["change_amount"] for r in decreases),
            "avg_confidence": round(sum(r["confidence"] for r in recommendations) / len(recommendations), 2) if recommendations else 0,
        }

        return {"items": top, "total": len(recommendations), "summary": summary}

    # ═══════════════════════════════════════════
    # CREDIT HOLD / RELEASE AUTOMATION
    # ═══════════════════════════════════════════

    async def apply_credit_hold(
        self, db: AsyncSession, tenant_id: UUID, customer_id: UUID,
        reason: str = "Manual hold", user_id: Optional[UUID] = None,
    ) -> dict:
        """Apply credit hold to a customer."""
        customer = (await db.execute(
            select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if not customer:
            raise ValueError("Customer not found")

        previous = bool(customer.credit_hold)
        customer.credit_hold = True
        customer.status = CustomerStatus.CREDIT_HOLD

        util_pct = 0.0
        if customer.credit_limit and float(customer.credit_limit) > 0:
            util_pct = float(customer.credit_utilization or 0) / float(customer.credit_limit) * 100

        await db.commit()

        return {
            "customer_id": str(customer_id),
            "customer_name": customer.name,
            "action": "hold",
            "previous_status": previous,
            "new_status": True,
            "reason": reason,
            "utilization_pct": round(util_pct, 1),
            "threshold_pct": float(customer.credit_hold_threshold or 100),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def release_credit_hold(
        self, db: AsyncSession, tenant_id: UUID, customer_id: UUID,
        reason: str = "Manual release",
    ) -> dict:
        """Release credit hold from a customer."""
        customer = (await db.execute(
            select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if not customer:
            raise ValueError("Customer not found")

        previous = bool(customer.credit_hold)
        customer.credit_hold = False
        if customer.status == CustomerStatus.CREDIT_HOLD:
            customer.status = CustomerStatus.ACTIVE

        util_pct = 0.0
        if customer.credit_limit and float(customer.credit_limit) > 0:
            util_pct = float(customer.credit_utilization or 0) / float(customer.credit_limit) * 100

        await db.commit()

        return {
            "customer_id": str(customer_id),
            "customer_name": customer.name,
            "action": "release",
            "previous_status": previous,
            "new_status": False,
            "reason": reason,
            "utilization_pct": round(util_pct, 1),
            "threshold_pct": float(customer.credit_hold_threshold or 100),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def scan_credit_holds(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """Auto-scan for credit hold/release based on utilization thresholds."""
        start = time.time()
        customers = (await db.execute(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                Customer.is_deleted == False,
            )
        )).scalars().all()

        holds_applied = 0
        holds_released = 0
        already_held = 0
        details = []

        for cust in customers:
            limit = float(cust.credit_limit or 0)
            if limit <= 0:
                continue

            util = float(cust.credit_utilization or 0)
            util_pct = util / limit * 100
            threshold = float(cust.credit_hold_threshold or 100)

            if util_pct >= threshold and not cust.credit_hold:
                cust.credit_hold = True
                cust.status = CustomerStatus.CREDIT_HOLD
                holds_applied += 1
                details.append({
                    "customer": cust.name, "action": "hold_applied",
                    "utilization_pct": round(util_pct, 1), "threshold": threshold,
                })
            elif util_pct < threshold * 0.85 and cust.credit_hold:
                # Release when utilization drops below 85% of threshold
                cust.credit_hold = False
                if cust.status == CustomerStatus.CREDIT_HOLD:
                    cust.status = CustomerStatus.ACTIVE
                holds_released += 1
                details.append({
                    "customer": cust.name, "action": "hold_released",
                    "utilization_pct": round(util_pct, 1), "threshold": threshold,
                })
            elif cust.credit_hold:
                already_held += 1

        await db.commit()
        duration_ms = int((time.time() - start) * 1000)

        return {
            "customers_scanned": len(customers),
            "holds_applied": holds_applied,
            "holds_released": holds_released,
            "already_held": already_held,
            "details": details,
            "duration_ms": duration_ms,
        }

    # ═══════════════════════════════════════════
    # CREDIT EXPOSURE DASHBOARD
    # ═══════════════════════════════════════════

    async def get_credit_exposure(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """Portfolio-level credit exposure analytics."""
        customers = (await db.execute(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                Customer.is_deleted == False,
            )
        )).scalars().all()

        total_limit = 0.0
        total_util = 0.0
        entries = []

        for cust in customers:
            limit = float(cust.credit_limit or 0)
            util = float(cust.credit_utilization or 0)
            if limit <= 0:
                continue

            total_limit += limit
            total_util += util
            util_pct = util / limit * 100

            entries.append({
                "customer_id": str(cust.id),
                "customer_name": cust.name,
                "segment": cust.segment or "unclassified",
                "credit_limit": limit,
                "utilization": util,
                "utilization_pct": round(util_pct, 1),
                "credit_hold": bool(cust.credit_hold),
                "risk_score": float(cust.risk_score or 0),
                "health_score": _health_scores.get(str(cust.id), {}).get("composite_score", 0),
            })

        # Top utilization
        top_util = sorted(entries, key=lambda x: x["utilization_pct"], reverse=True)[:10]

        # Trending up (high util + no hold yet)
        trending_up = [e for e in entries if e["utilization_pct"] > 70 and not e["credit_hold"]]
        trending_up.sort(key=lambda x: x["utilization_pct"], reverse=True)

        # At risk (high util + high risk or low health)
        at_risk = [e for e in entries if e["utilization_pct"] > 60 and (e["risk_score"] > 60 or e["health_score"] < 40)]
        at_risk.sort(key=lambda x: x["risk_score"], reverse=True)

        # By segment
        by_segment = defaultdict(lambda: {"total_limit": 0, "total_utilization": 0, "count": 0})
        for e in entries:
            seg = e["segment"]
            by_segment[seg]["total_limit"] += e["credit_limit"]
            by_segment[seg]["total_utilization"] += e["utilization"]
            by_segment[seg]["count"] += 1
        for seg in by_segment:
            lim = by_segment[seg]["total_limit"]
            by_segment[seg]["utilization_pct"] = round(by_segment[seg]["total_utilization"] / lim * 100, 1) if lim else 0

        hold_count = sum(1 for e in entries if e["credit_hold"])
        portfolio_pct = round(total_util / total_limit * 100, 1) if total_limit > 0 else 0

        return {
            "total_credit_limit": round(total_limit, 2),
            "total_utilization": round(total_util, 2),
            "portfolio_utilization_pct": portfolio_pct,
            "currency": "AED",
            "top_utilization": top_util[:10],
            "trending_up": trending_up[:10],
            "at_risk": at_risk[:10],
            "by_segment": dict(by_segment),
            "hold_count": hold_count,
            "threshold_config": {"warning": 80.0, "critical": 95.0, "auto_hold": 100.0},
        }

    # ═══════════════════════════════════════════
    # CUSTOMER 360 AI INSIGHTS
    # ═══════════════════════════════════════════

    async def get_customer_360(
        self, db: AsyncSession, tenant_id: UUID, customer_id: UUID,
        include_sections: Optional[List[str]] = None,
    ) -> dict:
        """Aggregated AI-powered 360-degree view of a customer."""
        customer = (await db.execute(
            select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if not customer:
            raise ValueError("Customer not found")

        default_sections = [
            "health_score", "credit_status", "payment_analysis",
            "predictions", "latest_briefing", "recommended_actions",
            "collection_history", "disputes",
        ]
        sections = include_sections or default_sections

        result = {
            "customer_id": str(customer_id),
            "customer_name": customer.name,
            "status": customer.status.value if hasattr(customer.status, "value") else str(customer.status),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # ── Health Score ──
        if "health_score" in sections:
            hs = _health_scores.get(str(customer_id))
            if not hs:
                try:
                    hs = await self.calculate_health_score(db, tenant_id, customer_id)
                except Exception:
                    hs = None
            if hs:
                result["health_score"] = {
                    "composite_score": hs["composite_score"],
                    "grade": hs["grade"],
                    "trend": hs["trend"],
                    "breakdown": hs["breakdown"],
                    "previous_score": hs.get("previous_score"),
                    "change": hs.get("score_change"),
                }

        # ── Credit Status ──
        if "credit_status" in sections:
            limit = float(customer.credit_limit or 0)
            util = float(customer.credit_utilization or 0)
            available = max(0, limit - util)
            util_pct = (util / limit * 100) if limit > 0 else 0

            result["credit_status"] = {
                "credit_limit": limit,
                "utilized": util,
                "available": available,
                "utilization_pct": round(util_pct, 1),
                "on_hold": bool(customer.credit_hold),
                "hold_threshold": float(customer.credit_hold_threshold or 100),
                "currency": customer.currency or "AED",
                "ecl_stage": str(customer.ecl_stage) if customer.ecl_stage else "stage_1",
            }

        # ── Payment Analysis ──
        if "payment_analysis" in sections:
            invoices = (await db.execute(
                select(Invoice).where(
                    Invoice.customer_id == customer_id,
                    Invoice.tenant_id == tenant_id,
                    Invoice.is_deleted == False,
                )
            )).scalars().all()

            payments = (await db.execute(
                select(Payment).where(
                    Payment.customer_id == customer_id,
                    Payment.tenant_id == tenant_id,
                )
            )).scalars().all()

            total_invoiced = sum(float(i.amount or 0) for i in invoices)
            total_paid = sum(float(p.amount or 0) for p in payments)
            outstanding = sum(float(i.amount_remaining or 0) for i in invoices if i.status != InvoiceStatus.PAID)
            overdue_amt = sum(float(i.amount_remaining or 0) for i in invoices if i.status == InvoiceStatus.OVERDUE)

            avg_days_to_pay = 0
            paid_invoices = [i for i in invoices if i.status == InvoiceStatus.PAID]
            if paid_invoices:
                days_list = []
                for inv in paid_invoices:
                    matching = [p for p in payments if p.invoice_id == inv.id]
                    if matching and inv.invoice_date:
                        pay_date = matching[0].payment_date
                        if pay_date:
                            days_list.append((pay_date - inv.invoice_date).days)
                if days_list:
                    avg_days_to_pay = sum(days_list) / len(days_list)

            result["payment_analysis"] = {
                "total_invoiced": round(total_invoiced, 2),
                "total_paid": round(total_paid, 2),
                "outstanding": round(outstanding, 2),
                "overdue_amount": round(overdue_amt, 2),
                "invoice_count": len(invoices),
                "payment_count": len(payments),
                "avg_days_to_pay": round(avg_days_to_pay, 1),
                "currency": customer.currency or "AED",
            }

        # ── Predictions ──
        if "predictions" in sections:
            risk = float(customer.risk_score or 50)
            churn = float(customer.churn_probability or 0)

            result["predictions"] = {
                "risk_score": risk,
                "risk_level": "high" if risk > 70 else ("medium" if risk > 40 else "low"),
                "churn_probability": round(churn, 2),
                "churn_risk": "high" if churn > 0.7 else ("medium" if churn > 0.3 else "low"),
                "predicted_dso": customer.predicted_dso or None,
                "model_version": "v1.0-simulated",
            }

        # ── Latest Briefing ──
        if "latest_briefing" in sections:
            briefing = (await db.execute(
                select(Briefing).where(
                    Briefing.tenant_id == tenant_id,
                ).order_by(Briefing.created_at.desc()).limit(1)
            )).scalar_one_or_none()

            if briefing:
                result["latest_briefing"] = {
                    "briefing_id": str(briefing.id),
                    "title": briefing.title,
                    "date": str(briefing.briefing_date),
                    "executive_summary": briefing.executive_summary[:300] if briefing.executive_summary else None,
                    "section_count": len(briefing.sections) if briefing.sections else 0,
                }

        # ── Recommended Actions ──
        if "recommended_actions" in sections:
            actions = []
            hs_data = _health_scores.get(str(customer_id), {})
            health = hs_data.get("composite_score", 50)

            if customer.credit_hold:
                actions.append({
                    "priority": "high", "type": "credit",
                    "action": "Review credit hold status — check if recent payment allows release",
                    "reason": "Customer currently on credit hold",
                })

            overdue_inv = (await db.execute(
                select(func.count()).select_from(Invoice).where(
                    Invoice.customer_id == customer_id,
                    Invoice.tenant_id == tenant_id,
                    Invoice.status == InvoiceStatus.OVERDUE,
                )
            )).scalar() or 0

            if overdue_inv > 0:
                actions.append({
                    "priority": "high", "type": "collection",
                    "action": f"Follow up on {overdue_inv} overdue invoice(s)",
                    "reason": "Active overdue invoices need attention",
                })

            if health < 40:
                actions.append({
                    "priority": "medium", "type": "relationship",
                    "action": "Schedule account review meeting — health score declining",
                    "reason": f"Health score at {health:.0f} (grade {_score_to_grade(health)})",
                })

            open_disp = (await db.execute(
                select(func.count()).select_from(Dispute).where(
                    Dispute.customer_id == customer_id,
                    Dispute.tenant_id == tenant_id,
                    Dispute.status.in_([DisputeStatus.OPEN, DisputeStatus.IN_REVIEW]),
                )
            )).scalar() or 0

            if open_disp > 0:
                actions.append({
                    "priority": "medium", "type": "dispute",
                    "action": f"Resolve {open_disp} open dispute(s) to improve relationship",
                    "reason": "Open disputes affecting customer satisfaction",
                })

            if not actions:
                actions.append({
                    "priority": "low", "type": "maintenance",
                    "action": "Account in good standing — maintain regular contact schedule",
                    "reason": "No urgent issues identified",
                })

            result["recommended_actions"] = actions

        # ── Collection History ──
        if "collection_history" in sections:
            activities = (await db.execute(
                select(CollectionActivity).where(
                    CollectionActivity.customer_id == customer_id,
                    CollectionActivity.tenant_id == tenant_id,
                ).order_by(CollectionActivity.action_date.desc()).limit(10)
            )).scalars().all()

            activity_list = []
            for a in activities:
                activity_list.append({
                    "id": str(a.id),
                    "action_type": a.action_type.value if hasattr(a.action_type, "value") else str(a.action_type),
                    "action_date": str(a.action_date),
                    "notes": a.notes,
                    "is_ai_suggested": a.is_ai_suggested,
                })

            result["collection_history"] = {
                "recent_activities": activity_list,
                "total_activities": len(activities),
            }

        # ── Disputes ──
        if "disputes" in sections:
            disputes = (await db.execute(
                select(Dispute).where(
                    Dispute.customer_id == customer_id,
                    Dispute.tenant_id == tenant_id,
                    Dispute.is_deleted == False,
                )
            )).scalars().all()

            open_d = [d for d in disputes if d.status in (DisputeStatus.OPEN, DisputeStatus.IN_REVIEW, DisputeStatus.ESCALATED)]
            resolved_d = [d for d in disputes if d.status in (DisputeStatus.RESOLVED, DisputeStatus.CREDIT_ISSUED)]

            result["disputes"] = {
                "total": len(disputes),
                "open": len(open_d),
                "resolved": len(resolved_d),
                "open_amount": round(sum(float(d.amount or 0) for d in open_d), 2),
                "resolved_amount": round(sum(float(d.amount or 0) for d in resolved_d), 2),
                "recent": [{
                    "id": str(d.id),
                    "dispute_number": d.dispute_number,
                    "reason": d.reason.value if hasattr(d.reason, "value") else str(d.reason),
                    "status": d.status.value if hasattr(d.status, "value") else str(d.status),
                    "amount": float(d.amount or 0),
                } for d in disputes[:5]],
            }

        return result

    # ═══════════════════════════════════════════
    # CHAT ENGINE
    # ═══════════════════════════════════════════

    async def chat(
        self, db: AsyncSession, tenant_id: UUID, user_id: UUID,
        message: str, conversation_id: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> dict:
        """Process a chat message and return AI-generated response with data citations."""
        start = time.time()

        # Get or create conversation
        if conversation_id and conversation_id in _chat_conversations:
            conv = _chat_conversations[conversation_id]
        else:
            conversation_id = str(uuid4())
            conv = {
                "id": conversation_id,
                "tenant_id": str(tenant_id),
                "user_id": str(user_id),
                "messages": [],
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            _chat_conversations[conversation_id] = conv

        now_iso = datetime.now(timezone.utc).isoformat()
        conv["messages"].append({"role": "user", "content": message, "timestamp": now_iso})

        # Parse intent and generate response
        msg_lower = message.lower()
        response_text = ""
        citations = []
        entities = []
        suggestions = []

        # Use word-boundary aware matching for short keywords
        words = set(msg_lower.split())
        if any(kw in msg_lower for kw in ["overdue", "outstanding", "unpaid"]) or "ar" in words:
            # AR / overdue query
            overdue = (await db.execute(
                select(Invoice).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.is_deleted == False,
                    Invoice.status == InvoiceStatus.OVERDUE,
                )
            )).scalars().all()

            total_overdue = sum(float(i.amount_remaining or i.amount or 0) for i in overdue)
            response_text = (
                f"You currently have {len(overdue)} overdue invoice(s) totaling "
                f"{total_overdue:,.2f} AED. "
            )
            if overdue:
                worst = max(overdue, key=lambda x: x.days_overdue or 0)
                response_text += (
                    f"The most overdue is {worst.invoice_number} at {worst.days_overdue or 0} days "
                    f"({float(worst.amount_remaining or worst.amount or 0):,.2f} AED)."
                )
                citations.append({
                    "type": "invoice", "id": str(worst.id),
                    "label": worst.invoice_number,
                    "detail": f"{worst.days_overdue} days overdue",
                })
                entities.append({"type": "invoice", "id": str(worst.id), "name": worst.invoice_number})

            suggestions = [
                "Which customers have the highest overdue amounts?",
                "Show me the aging breakdown",
                "What collection actions were taken this week?",
            ]

        elif any(kw in msg_lower for kw in ["customer", "top", "risk", "risky"]):
            # Customer / risk query
            customers = (await db.execute(
                select(Customer).where(
                    Customer.tenant_id == tenant_id,
                    Customer.is_deleted == False,
                ).order_by(Customer.risk_score.desc().nullslast()).limit(5)
            )).scalars().all()

            response_text = "Here are the top 5 customers by risk score:\n\n"
            for i, c in enumerate(customers, 1):
                score = float(c.risk_score or 0)
                response_text += f"{i}. {c.name} — Risk: {score:.0f}, Credit limit: {float(c.credit_limit or 0):,.0f} AED\n"
                entities.append({"type": "customer", "id": str(c.id), "name": c.name})
                citations.append({
                    "type": "customer", "id": str(c.id),
                    "label": c.name, "detail": f"Risk score: {score:.0f}",
                })

            suggestions = [
                "Tell me more about the highest-risk customer",
                "What is the total credit exposure?",
                "Show health scores for these customers",
            ]

        elif any(kw in msg_lower for kw in ["credit", "exposure", "limit", "utilization"]):
            # Credit query
            customers = (await db.execute(
                select(Customer).where(
                    Customer.tenant_id == tenant_id,
                    Customer.is_deleted == False,
                )
            )).scalars().all()

            total_limit = sum(float(c.credit_limit or 0) for c in customers)
            total_util = sum(float(c.credit_utilization or 0) for c in customers)
            on_hold = sum(1 for c in customers if c.credit_hold)
            pct = (total_util / total_limit * 100) if total_limit > 0 else 0

            response_text = (
                f"Portfolio credit summary:\n\n"
                f"Total credit limit: {total_limit:,.0f} AED\n"
                f"Total utilization: {total_util:,.0f} AED ({pct:.1f}%)\n"
                f"Available credit: {(total_limit - total_util):,.0f} AED\n"
                f"Customers on hold: {on_hold}"
            )

            suggestions = [
                "Which customers are closest to their credit limit?",
                "Show AI credit recommendations",
                "Run a credit hold scan",
            ]

        elif any(kw in msg_lower for kw in ["health", "score", "grade"]):
            # Health score query
            scores = list(_health_scores.values())
            tenant_scores = [s for s in scores if True]  # all stored scores
            if tenant_scores:
                avg = sum(s["composite_score"] for s in tenant_scores) / len(tenant_scores)
                grade_dist = defaultdict(int)
                for s in tenant_scores:
                    grade_dist[s["grade"]] += 1

                response_text = (
                    f"Health score overview ({len(tenant_scores)} customers scored):\n\n"
                    f"Average score: {avg:.1f}\n"
                    f"Grade distribution: " +
                    ", ".join(f"{g}: {c}" for g, c in sorted(grade_dist.items())) +
                    "\n\nRun a batch health score calculation to update all customers."
                )
            else:
                response_text = "No health scores have been calculated yet. Would you like me to run a batch calculation?"

            suggestions = [
                "Calculate health scores for all customers",
                "Show me the lowest-scoring customers",
                "What factors affect health scores?",
            ]

        elif any(kw in msg_lower for kw in ["dispute", "resolution"]):
            disputes = (await db.execute(
                select(Dispute).where(
                    Dispute.tenant_id == tenant_id,
                    Dispute.is_deleted == False,
                )
            )).scalars().all()

            open_d = [d for d in disputes if d.status in (DisputeStatus.OPEN, DisputeStatus.IN_REVIEW, DisputeStatus.ESCALATED)]
            total_amt = sum(float(d.amount or 0) for d in open_d)

            response_text = (
                f"Dispute summary:\n\n"
                f"Total disputes: {len(disputes)}\n"
                f"Open/In review: {len(open_d)}\n"
                f"Open dispute value: {total_amt:,.2f} AED"
            )

            suggestions = [
                "Show dispute aging breakdown",
                "Which department has the most disputes?",
                "What are the common dispute reasons?",
            ]

        elif any(kw in msg_lower for kw in ["collection", "ptp", "promise"]):
            activities = (await db.execute(
                select(func.count()).select_from(CollectionActivity).where(
                    CollectionActivity.tenant_id == tenant_id,
                )
            )).scalar() or 0

            response_text = (
                f"Collection activity summary:\n\n"
                f"Total activities logged: {activities}\n\n"
                "I can help with drafting collection messages, tracking promises to pay, "
                "or running escalation scans."
            )

            suggestions = [
                "Draft a collection email for a customer",
                "Show PTP dashboard",
                "Run escalation scan",
            ]

        elif any(kw in msg_lower for kw in ["hello", "hi", "hey", "help"]):
            response_text = (
                "Hello! I'm your Sales IQ AI assistant. I can help you with:\n\n"
                "- Accounts receivable analysis and overdue tracking\n"
                "- Customer health scores and risk assessment\n"
                "- Credit limit management and recommendations\n"
                "- Collection activities and escalation\n"
                "- Dispute management and aging analysis\n"
                "- Payment predictions and DSO tracking\n\n"
                "What would you like to know about?"
            )

            suggestions = [
                "Show me overdue invoices",
                "What is the total credit exposure?",
                "Which customers are highest risk?",
                "Run health score calculations",
            ]

        else:
            response_text = (
                f"I understand you're asking about \"{message}\". "
                "Let me help you with that. I can provide insights on:\n\n"
                "- Accounts receivable and overdue invoices\n"
                "- Customer health scores and risk levels\n"
                "- Credit exposure and limit management\n"
                "- Disputes and resolutions\n"
                "- Collection activities and promises to pay\n\n"
                "Could you rephrase your question or pick one of the suggested topics?"
            )

            suggestions = [
                "Show overdue invoice summary",
                "Customer risk overview",
                "Credit exposure dashboard",
                "Dispute summary",
            ]

        # Add assistant message to conversation
        assistant_msg = {
            "role": "assistant",
            "content": response_text,
            "citations": citations,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        conv["messages"].append(assistant_msg)
        conv["last_message_at"] = assistant_msg["timestamp"]

        processing_ms = int((time.time() - start) * 1000)

        return {
            "conversation_id": conversation_id,
            "message": assistant_msg,
            "suggested_questions": suggestions,
            "data_citations": citations,
            "entities_referenced": entities,
            "processing_time_ms": processing_ms,
        }

    def get_chat_history(self, tenant_id: str, conversation_id: str) -> Optional[dict]:
        """Get chat conversation history."""
        conv = _chat_conversations.get(conversation_id)
        if not conv or conv["tenant_id"] != tenant_id:
            return None
        return {
            "conversation_id": conv["id"],
            "messages": conv["messages"],
            "started_at": conv["started_at"],
            "last_message_at": conv.get("last_message_at", conv["started_at"]),
            "message_count": len(conv["messages"]),
        }

    def list_conversations(self, tenant_id: str, user_id: str) -> List[dict]:
        """List all conversations for a user."""
        convs = [c for c in _chat_conversations.values()
                 if c["tenant_id"] == tenant_id and c["user_id"] == user_id]
        convs.sort(key=lambda x: x.get("last_message_at", ""), reverse=True)
        return [{
            "conversation_id": c["id"],
            "message_count": len(c["messages"]),
            "started_at": c["started_at"],
            "last_message_at": c.get("last_message_at"),
            "preview": c["messages"][-1]["content"][:100] if c["messages"] else "",
        } for c in convs]


# Singleton
intelligence_engine = IntelligenceEngine()
