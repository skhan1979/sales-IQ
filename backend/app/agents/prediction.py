"""
Sales IQ - Prediction Agent
Real ML-style prediction pipeline for payment dates, churn probability,
risk scoring, and DSO forecasting using statistical heuristics.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Dict, List
from uuid import UUID
import math
import statistics

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent, PipelineStage, AgentContext
from app.models.business import Customer, Invoice, Payment, InvoiceStatus


# ── Stage 1: Feature Extraction ──────────────────────────────────────

class FeatureExtractionStage(PipelineStage):
    """Build feature vectors from customer payment history."""

    name = "feature_extraction"

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        # Load all active customers
        result = await db.execute(
            select(Customer).where(
                Customer.tenant_id == ctx.tenant_id,
                Customer.status.in_(["active", "credit_hold"]),
            )
        )
        customers = result.scalars().all()
        ctx.records_processed = len(customers)

        today = date.today()

        for customer in customers:
            cid = str(customer.id)
            ctx.get_entity_result(cid)

            # Load invoices for this customer
            inv_result = await db.execute(
                select(Invoice).where(
                    Invoice.tenant_id == ctx.tenant_id,
                    Invoice.customer_id == customer.id,
                )
            )
            invoices = inv_result.scalars().all()

            # Load payments for this customer
            pay_result = await db.execute(
                select(Payment).where(
                    Payment.tenant_id == ctx.tenant_id,
                    Payment.customer_id == customer.id,
                )
            )
            payments = pay_result.scalars().all()

            # ── Compute features ──
            features = {}

            # Payment history features
            if payments:
                pay_amounts = [float(p.amount or 0) for p in payments]
                features["avg_payment_amount"] = statistics.mean(pay_amounts)
                features["total_payments"] = len(payments)
                features["total_paid_amount"] = sum(pay_amounts)

                # Days-to-pay: for matched payments, compute invoice_date -> payment_date
                days_to_pay = []
                for p in payments:
                    if p.invoice_id:
                        # Find the matching invoice
                        for inv in invoices:
                            if inv.id == p.invoice_id and inv.invoice_date and p.payment_date:
                                delta = (p.payment_date - inv.invoice_date).days
                                if 0 < delta < 365:
                                    days_to_pay.append(delta)
                                break

                if days_to_pay:
                    features["avg_days_to_pay"] = statistics.mean(days_to_pay)
                    features["median_days_to_pay"] = statistics.median(days_to_pay)
                    features["stddev_days_to_pay"] = (
                        statistics.stdev(days_to_pay) if len(days_to_pay) > 1 else 0
                    )
                    features["max_days_to_pay"] = max(days_to_pay)
                    features["min_days_to_pay"] = min(days_to_pay)
                else:
                    features["avg_days_to_pay"] = float(customer.payment_terms_days or 30)
                    features["median_days_to_pay"] = features["avg_days_to_pay"]
                    features["stddev_days_to_pay"] = 15.0
                    features["max_days_to_pay"] = features["avg_days_to_pay"] * 2
                    features["min_days_to_pay"] = features["avg_days_to_pay"] * 0.5
            else:
                features["avg_payment_amount"] = 0
                features["total_payments"] = 0
                features["total_paid_amount"] = 0
                features["avg_days_to_pay"] = float(customer.payment_terms_days or 30)
                features["median_days_to_pay"] = features["avg_days_to_pay"]
                features["stddev_days_to_pay"] = 15.0
                features["max_days_to_pay"] = features["avg_days_to_pay"] * 2
                features["min_days_to_pay"] = features["avg_days_to_pay"] * 0.5

            # Invoice features
            if invoices:
                inv_amounts = [float(inv.amount or 0) for inv in invoices]
                features["total_invoices"] = len(invoices)
                features["avg_invoice_amount"] = statistics.mean(inv_amounts)
                features["total_invoiced_amount"] = sum(inv_amounts)

                overdue = [i for i in invoices if i.status in ("overdue",) and i.days_overdue and i.days_overdue > 0]
                features["overdue_count"] = len(overdue)
                features["overdue_ratio"] = len(overdue) / len(invoices)
                features["avg_days_overdue"] = (
                    statistics.mean([i.days_overdue for i in overdue]) if overdue else 0
                )

                # Open AR
                open_invs = [i for i in invoices if i.status in ("open", "overdue", "partially_paid")]
                features["open_ar_amount"] = sum(float(i.amount_remaining or i.amount or 0) for i in open_invs)
                features["open_ar_count"] = len(open_invs)

                # Recent activity (last 90 days)
                cutoff_90 = today - timedelta(days=90)
                recent_invs = [i for i in invoices if i.invoice_date and i.invoice_date >= cutoff_90]
                features["recent_invoice_count"] = len(recent_invs)
                features["recent_invoice_amount"] = sum(float(i.amount or 0) for i in recent_invs)

                # Order trend (comparing last 90d vs previous 90d)
                cutoff_180 = today - timedelta(days=180)
                prev_invs = [i for i in invoices if i.invoice_date and cutoff_180 <= i.invoice_date < cutoff_90]
                recent_total = features["recent_invoice_amount"]
                prev_total = sum(float(i.amount or 0) for i in prev_invs)
                if prev_total > 0:
                    features["order_trend"] = (recent_total - prev_total) / prev_total
                else:
                    features["order_trend"] = 1.0 if recent_total > 0 else 0.0
            else:
                features["total_invoices"] = 0
                features["avg_invoice_amount"] = 0
                features["total_invoiced_amount"] = 0
                features["overdue_count"] = 0
                features["overdue_ratio"] = 0
                features["avg_days_overdue"] = 0
                features["open_ar_amount"] = 0
                features["open_ar_count"] = 0
                features["recent_invoice_count"] = 0
                features["recent_invoice_amount"] = 0
                features["order_trend"] = 0

            # Credit features
            features["credit_limit"] = float(customer.credit_limit or 0)
            features["credit_utilization"] = float(customer.credit_utilization or 0)
            features["credit_hold"] = 1 if customer.credit_hold else 0

            # Store features in context
            er = ctx.get_entity_result(cid)
            er["features"] = features
            er["customer"] = customer
            er["invoices"] = invoices
            er["payments"] = payments

            ctx.records_succeeded += 1


# ── Stage 2: Model Inference ─────────────────────────────────────────

class ModelInferenceStage(PipelineStage):
    """
    Run heuristic scoring models for:
    - Payment date prediction (per open invoice)
    - Churn probability
    - Risk scoring
    - DSO forecasting
    """

    name = "model_inference"

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        predictions_count = 0

        for entity_id, er in ctx.entity_results.items():
            features = er.get("features", {})
            customer = er.get("customer")
            invoices = er.get("invoices", [])
            if not customer:
                continue

            # ── Risk Score (0-100, higher = riskier) ──
            risk_score = 20.0  # Baseline

            # Overdue ratio impact
            overdue_ratio = features.get("overdue_ratio", 0)
            risk_score += overdue_ratio * 40  # up to +40

            # Average days overdue impact
            avg_overdue = features.get("avg_days_overdue", 0)
            if avg_overdue > 90:
                risk_score += 20
            elif avg_overdue > 60:
                risk_score += 15
            elif avg_overdue > 30:
                risk_score += 10
            elif avg_overdue > 0:
                risk_score += 5

            # Credit hold penalty
            if features.get("credit_hold"):
                risk_score += 10

            # Credit utilization
            credit_limit = features.get("credit_limit", 0)
            if credit_limit > 0:
                util_pct = features.get("credit_utilization", 0) / credit_limit * 100
                if util_pct > 90:
                    risk_score += 10
                elif util_pct > 75:
                    risk_score += 5

            # Order trend (declining = riskier)
            trend = features.get("order_trend", 0)
            if trend < -0.5:
                risk_score += 10
            elif trend < -0.2:
                risk_score += 5

            # Payment regularity bonus (lower risk)
            if features.get("total_payments", 0) > 5 and overdue_ratio < 0.2:
                risk_score -= 10

            risk_score = max(0, min(100, risk_score))

            # ── Churn Probability (0-1) ──
            churn_prob = 0.1  # Baseline

            # No recent invoices = higher churn
            if features.get("recent_invoice_count", 0) == 0:
                churn_prob += 0.3
            elif features.get("recent_invoice_count", 0) < 2:
                churn_prob += 0.15

            # Declining trend
            if trend < -0.5:
                churn_prob += 0.25
            elif trend < -0.2:
                churn_prob += 0.1

            # High overdue = may stop ordering
            if overdue_ratio > 0.5:
                churn_prob += 0.15

            # Credit hold = blocked, might churn
            if features.get("credit_hold"):
                churn_prob += 0.1

            churn_prob = max(0, min(1, churn_prob))

            # ── DSO Prediction ──
            avg_dtp = features.get("avg_days_to_pay", float(customer.payment_terms_days or 30))
            stddev_dtp = features.get("stddev_days_to_pay", 10)
            # Predicted DSO = weighted avg with trend adjustment
            trend_adjustment = 0
            if trend < -0.3:
                trend_adjustment = 5  # Declining business = slower pay
            elif trend > 0.3:
                trend_adjustment = -3  # Growing business = slightly faster pay
            predicted_dso = max(1, avg_dtp + trend_adjustment)

            # ── Per-invoice payment date prediction ──
            today = date.today()
            for inv in invoices:
                if inv.status in ("open", "overdue", "partially_paid"):
                    # Predict when this specific invoice will be paid
                    base_days = avg_dtp
                    # Adjust for overdue: if already overdue, predict based on pattern
                    if inv.due_date and today > inv.due_date:
                        overdue_days = (today - inv.due_date).days
                        # Probability of payment decreases with overdue duration
                        extra_wait = max(0, base_days - (inv.due_date - inv.invoice_date).days) if inv.invoice_date else 7
                        extra_wait = max(extra_wait, 7)  # At least 7 more days
                        predicted_date = today + timedelta(days=int(extra_wait))
                    elif inv.invoice_date:
                        predicted_date = inv.invoice_date + timedelta(days=int(base_days))
                        if predicted_date < today:
                            predicted_date = today + timedelta(days=7)
                    else:
                        predicted_date = today + timedelta(days=int(base_days))

                    # Payment probability (higher for non-overdue)
                    if inv.status == "overdue":
                        pay_prob = max(0.2, 0.9 - (avg_overdue / 200))
                    elif inv.status == "partially_paid":
                        pay_prob = 0.85
                    else:
                        pay_prob = max(0.5, 0.95 - overdue_ratio * 0.3)

                    inv._predicted_pay_date = predicted_date
                    inv._payment_probability = round(pay_prob, 3)
                    predictions_count += 1

            # Store predictions
            er["predictions"] = {
                "risk_score": round(risk_score, 1),
                "churn_probability": round(churn_prob, 3),
                "predicted_dso": round(predicted_dso, 1),
            }

        ctx.extra["total_predictions"] = predictions_count


# ── Stage 3: Score Update ────────────────────────────────────────────

class ScoreUpdateStage(PipelineStage):
    """Write predicted values back to customer and invoice records in the DB."""

    name = "score_update"

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        updates_applied = 0

        for entity_id, er in ctx.entity_results.items():
            customer = er.get("customer")
            predictions = er.get("predictions", {})
            invoices = er.get("invoices", [])

            if not customer or not predictions:
                continue

            # Update customer scores
            old_risk = customer.risk_score
            new_risk = predictions["risk_score"]
            customer.risk_score = new_risk
            customer.churn_probability = predictions["churn_probability"]
            customer.predicted_dso = predictions["predicted_dso"]

            if old_risk != new_risk:
                ctx.add_change(
                    entity_id, "score_update", "risk_score",
                    old_risk, new_risk,
                    detail=f"Risk score updated from {old_risk} to {new_risk}"
                )

            # Update invoice predictions
            for inv in invoices:
                predicted_date = getattr(inv, "_predicted_pay_date", None)
                pay_prob = getattr(inv, "_payment_probability", None)
                if predicted_date:
                    inv.predicted_pay_date = predicted_date
                if pay_prob is not None:
                    inv.payment_probability = pay_prob

            updates_applied += 1

        ctx.extra["updates_applied"] = updates_applied
        await db.flush()


# ── Agent ─────────────────────────────────────────────────────────────

class PredictionAgent(BaseAgent):
    """ML-style prediction agent using statistical heuristics."""

    agent_name = "prediction_agent"
    stages = [
        FeatureExtractionStage(),
        ModelInferenceStage(),
        ScoreUpdateStage(),
    ]


# Singleton
prediction_agent = PredictionAgent()
