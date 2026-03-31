"""
Sales IQ - Sales Dashboard Service
Day 16: Pipeline analytics, reorder alerts, churn watchlist,
        revenue segmentation, growth opportunities.
"""

import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import (
    Customer, Invoice, Payment, CollectionActivity,
    CustomerStatus, InvoiceStatus, CollectionAction,
)


class SalesDashboardService:
    """Sales VP dashboard: pipeline, churn, reorder alerts, revenue intelligence."""

    # ═══════════════════════════════════════════
    # PIPELINE SUMMARY
    # ═══════════════════════════════════════════

    async def get_pipeline_summary(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """Simulated sales pipeline from invoice lifecycle stages."""
        invoices = (await db.execute(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id,
                Invoice.is_deleted == False,
            )
        )).scalars().all()

        # Map invoice statuses to pipeline stages
        stage_map = {
            "open": ("New / Open", 0.20),
            "partially_paid": ("In Progress", 0.50),
            "overdue": ("At Risk", 0.15),
            "paid": ("Won / Collected", 1.00),
            "disputed": ("Disputed", 0.10),
            "written_off": ("Lost / Written Off", 0.00),
            "credit_note": ("Credit Note", 0.00),
        }

        stages = defaultdict(lambda: {"count": 0, "amount": 0.0})
        total_value = 0.0

        for inv in invoices:
            status_key = inv.status.value if hasattr(inv.status, "value") else str(inv.status)
            stage_name, weight = stage_map.get(status_key, ("Other", 0.10))
            amount = float(inv.amount or 0)
            stages[stage_name]["count"] += 1
            stages[stage_name]["amount"] += amount
            total_value += amount

        stage_list = []
        weighted_total = 0.0
        for name, data in stages.items():
            pct = (data["amount"] / total_value * 100) if total_value > 0 else 0
            weight = stage_map.get(
                next((k for k, v in stage_map.items() if v[0] == name), ""), ("", 0.10)
            )[1] if isinstance(stage_map.get(next((k for k, v in stage_map.items() if v[0] == name), ""), 0), tuple) else 0.10

            # Get weight from map
            for k, (sname, w) in stage_map.items():
                if sname == name:
                    weight = w
                    break

            weighted_total += data["amount"] * weight
            stage_list.append({
                "stage": name,
                "count": data["count"],
                "amount": round(data["amount"], 2),
                "pct_of_total": round(pct, 1),
            })

        stage_list.sort(key=lambda x: x["amount"], reverse=True)

        won = stages.get("Won / Collected", {"count": 0})["count"]
        total_opps = sum(s["count"] for s in stages.values())
        conversion = (won / total_opps * 100) if total_opps > 0 else 0
        avg_deal = (total_value / total_opps) if total_opps > 0 else 0

        return {
            "stages": stage_list,
            "total_pipeline_value": round(total_value, 2),
            "total_opportunities": total_opps,
            "avg_deal_size": round(avg_deal, 2),
            "weighted_pipeline": round(weighted_total, 2),
            "conversion_rate": round(conversion, 1),
            "currency": "AED",
        }

    # ═══════════════════════════════════════════
    # REORDER ALERTS
    # ═══════════════════════════════════════════

    async def get_reorder_alerts(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """Identify customers who are overdue for reordering."""
        today = date.today()
        customers = (await db.execute(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                Customer.is_deleted == False,
                Customer.status.in_([CustomerStatus.ACTIVE, CustomerStatus.CREDIT_HOLD]),
            )
        )).scalars().all()

        alerts = []
        by_level = defaultdict(int)
        total_at_risk = 0.0

        for cust in customers:
            # Get invoice history for order frequency
            invoices = (await db.execute(
                select(Invoice).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.customer_id == cust.id,
                    Invoice.is_deleted == False,
                ).order_by(Invoice.invoice_date.desc())
            )).scalars().all()

            if not invoices:
                continue

            # Calculate order frequency
            dates = sorted([i.invoice_date for i in invoices if i.invoice_date], reverse=True)
            if not dates:
                continue

            last_order = dates[0]
            days_since = (today - last_order).days

            # Average frequency between orders
            avg_freq = None
            if len(dates) >= 2:
                gaps = [(dates[i] - dates[i + 1]).days for i in range(min(len(dates) - 1, 5))]
                avg_freq = sum(gaps) / len(gaps) if gaps else None

            avg_value = sum(float(i.amount or 0) for i in invoices) / len(invoices)

            # Determine alert level
            overdue_by = 0
            if avg_freq and avg_freq > 0:
                expected_next = last_order + timedelta(days=int(avg_freq))
                overdue_by = max(0, (today - expected_next).days)
                expected_str = str(expected_next)
            else:
                expected_str = None
                overdue_by = max(0, days_since - 60)  # Default: alert if no order in 60 days

            if days_since > 120 or overdue_by > 60:
                level = "dormant"
            elif overdue_by > 14 or days_since > 90:
                level = "critical"
            elif overdue_by > 0 or days_since > 45:
                level = "warning"
            else:
                continue  # No alert needed

            churn = float(cust.churn_probability or 0)
            from app.services.intelligence import _health_scores
            hs = _health_scores.get(str(cust.id), {}).get("composite_score")

            alerts.append({
                "customer_id": str(cust.id),
                "customer_name": cust.name,
                "segment": cust.segment,
                "last_order_date": str(last_order),
                "days_since_last_order": days_since,
                "avg_order_frequency_days": round(avg_freq, 1) if avg_freq else None,
                "avg_order_value": round(avg_value, 2),
                "expected_next_order": expected_str,
                "overdue_by_days": overdue_by if overdue_by > 0 else None,
                "alert_level": level,
                "churn_probability": round(churn, 3),
                "health_score": hs,
                "currency": cust.currency or "AED",
            })
            by_level[level] += 1
            total_at_risk += avg_value

        alerts.sort(key=lambda x: x["days_since_last_order"], reverse=True)

        return {
            "items": alerts,
            "total": len(alerts),
            "by_alert_level": dict(by_level),
            "total_at_risk_revenue": round(total_at_risk, 2),
            "currency": "AED",
        }

    # ═══════════════════════════════════════════
    # CHURN WATCHLIST
    # ═══════════════════════════════════════════

    async def get_churn_watchlist(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """Customers ranked by churn probability with actionable insights."""
        today = date.today()
        customers = (await db.execute(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                Customer.is_deleted == False,
            )
        )).scalars().all()

        entries = []
        high = medium = low = 0
        total_ar_at_risk = 0.0

        for cust in customers:
            churn = float(cust.churn_probability or 0)
            if churn < 0.1:
                continue  # Skip very low risk

            # Classify risk
            if churn >= 0.7:
                risk = "high"
                high += 1
            elif churn >= 0.3:
                risk = "medium"
                medium += 1
            else:
                risk = "low"
                low += 1

            # Get AR data
            ar_q = await db.execute(
                select(
                    func.coalesce(func.sum(Invoice.amount_remaining), 0),
                ).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.customer_id == cust.id,
                    Invoice.status.in_(["open", "partially_paid", "overdue"]),
                )
            )
            total_ar = float(ar_q.scalar() or 0)

            overdue_q = await db.execute(
                select(func.coalesce(func.sum(Invoice.amount_remaining), 0)).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.customer_id == cust.id,
                    Invoice.status == InvoiceStatus.OVERDUE,
                )
            )
            overdue_amt = float(overdue_q.scalar() or 0)

            # Last payment
            last_pay = (await db.execute(
                select(Payment.payment_date).where(
                    Payment.tenant_id == tenant_id,
                    Payment.customer_id == cust.id,
                ).order_by(Payment.payment_date.desc()).limit(1)
            )).scalar()
            days_since_pay = (today - last_pay).days if last_pay else None

            # Last collection action
            last_action = (await db.execute(
                select(CollectionActivity.action_type).where(
                    CollectionActivity.tenant_id == tenant_id,
                    CollectionActivity.customer_id == cust.id,
                ).order_by(CollectionActivity.action_date.desc()).limit(1)
            )).scalar()
            last_action_str = last_action.value if hasattr(last_action, "value") else str(last_action) if last_action else None

            # Health score
            from app.services.intelligence import _health_scores
            hs_data = _health_scores.get(str(cust.id), {})
            health = hs_data.get("composite_score")
            grade = hs_data.get("grade")

            # Determine trend (simulated from health score trend)
            trend = hs_data.get("trend", "stable")

            # Risk factors
            factors = []
            if days_since_pay and days_since_pay > 90:
                factors.append(f"No payment in {days_since_pay} days")
            if overdue_amt > 0:
                factors.append(f"Overdue: {overdue_amt:,.0f} AED")
            if cust.credit_hold:
                factors.append("On credit hold")
            if health and health < 40:
                factors.append(f"Low health score: {health:.0f}")
            if not factors:
                factors.append(f"Churn probability: {churn:.0%}")

            # Recommended action
            if risk == "high":
                action = "Schedule urgent retention meeting with account manager"
            elif risk == "medium" and overdue_amt > 0:
                action = "Address overdue invoices and propose payment plan"
            elif risk == "medium":
                action = "Proactive outreach to understand engagement decline"
            else:
                action = "Monitor and maintain regular contact cadence"

            total_ar_at_risk += total_ar

            entries.append({
                "customer_id": str(cust.id),
                "customer_name": cust.name,
                "segment": cust.segment,
                "churn_probability": round(churn, 3),
                "churn_risk": risk,
                "trend": trend,
                "health_score": health,
                "health_grade": grade,
                "total_ar": round(total_ar, 2),
                "overdue_amount": round(overdue_amt, 2),
                "days_since_last_payment": days_since_pay,
                "last_collection_action": last_action_str,
                "risk_factors": factors,
                "recommended_action": action,
                "currency": cust.currency or "AED",
            })

        entries.sort(key=lambda x: x["churn_probability"], reverse=True)

        return {
            "items": entries,
            "total": len(entries),
            "high_risk_count": high,
            "medium_risk_count": medium,
            "low_risk_count": low,
            "total_ar_at_risk": round(total_ar_at_risk, 2),
            "currency": "AED",
        }

    # ═══════════════════════════════════════════
    # REVENUE BY SEGMENT
    # ═══════════════════════════════════════════

    async def get_revenue_by_segment(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """Revenue analytics broken down by customer segment."""
        today = date.today()
        customers = (await db.execute(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                Customer.is_deleted == False,
            )
        )).scalars().all()

        seg_data = defaultdict(lambda: {
            "customer_count": 0, "total_invoiced": 0.0, "total_collected": 0.0,
            "total_outstanding": 0.0, "invoice_dates": [],
        })

        for cust in customers:
            segment = cust.segment or "unclassified"
            seg_data[segment]["customer_count"] += 1

            invoices = (await db.execute(
                select(Invoice).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.customer_id == cust.id,
                    Invoice.is_deleted == False,
                )
            )).scalars().all()

            for inv in invoices:
                amt = float(inv.amount or 0)
                remaining = float(inv.amount_remaining or 0)
                seg_data[segment]["total_invoiced"] += amt
                seg_data[segment]["total_collected"] += (amt - remaining)
                if inv.status in (InvoiceStatus.OPEN, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE):
                    seg_data[segment]["total_outstanding"] += remaining
                if inv.invoice_date:
                    seg_data[segment]["invoice_dates"].append(inv.invoice_date)

        segments = []
        total_revenue = 0.0
        top_segment = ""
        top_amount = 0.0

        for seg, data in seg_data.items():
            invoiced = data["total_invoiced"]
            collected = data["total_collected"]
            outstanding = data["total_outstanding"]
            rate = (collected / invoiced * 100) if invoiced > 0 else 0

            # Approximate DSO
            ninety_ago = today - timedelta(days=90)
            recent_invoiced = sum(1 for d in data["invoice_dates"] if d >= ninety_ago)
            dso = (outstanding / (invoiced / 365)) if invoiced > 0 else 0

            segments.append({
                "segment": seg,
                "customer_count": data["customer_count"],
                "total_invoiced": round(invoiced, 2),
                "total_collected": round(collected, 2),
                "total_outstanding": round(outstanding, 2),
                "collection_rate": round(rate, 1),
                "avg_dso": round(min(dso, 365), 1),
                "growth_pct": None,  # Would need historical comparison
                "currency": "AED",
            })

            total_revenue += invoiced
            if invoiced > top_amount:
                top_amount = invoiced
                top_segment = seg

        segments.sort(key=lambda x: x["total_invoiced"], reverse=True)

        return {
            "segments": segments,
            "total_revenue": round(total_revenue, 2),
            "top_segment": top_segment,
            "currency": "AED",
        }

    # ═══════════════════════════════════════════
    # GROWTH OPPORTUNITIES
    # ═══════════════════════════════════════════

    async def get_growth_opportunities(
        self, db: AsyncSession, tenant_id: UUID, limit: int = 20,
    ) -> dict:
        """Identify customers with upsell, reactivation, and expansion potential."""
        customers = (await db.execute(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                Customer.is_deleted == False,
            )
        )).scalars().all()

        opportunities = []
        by_type = defaultdict(int)

        for cust in customers:
            invoices = (await db.execute(
                select(Invoice).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.customer_id == cust.id,
                    Invoice.is_deleted == False,
                )
            )).scalars().all()

            total_rev = sum(float(i.amount or 0) for i in invoices)
            credit_limit = float(cust.credit_limit or 0)
            utilization = float(cust.credit_utilization or 0)
            util_pct = (utilization / credit_limit * 100) if credit_limit > 0 else 0
            health = 50.0
            from app.services.intelligence import _health_scores
            hs = _health_scores.get(str(cust.id), {})
            if hs:
                health = hs.get("composite_score", 50.0)

            reasoning = []
            opp_type = None
            potential = 0.0
            confidence = 0.5

            # High utilization + good health = credit expansion
            if util_pct > 80 and health >= 50 and not cust.credit_hold:
                potential = credit_limit * 0.25
                opp_type = "credit_expansion"
                reasoning.append(f"High utilization ({util_pct:.0f}%) with healthy account")
                reasoning.append(f"Health score: {health:.0f}")
                confidence = 0.70

            # Good health + declining orders = upsell
            elif health >= 60 and total_rev > 0:
                recent = [i for i in invoices if i.invoice_date and i.invoice_date >= (date.today() - timedelta(days=90))]
                recent_rev = sum(float(i.amount or 0) for i in recent)
                if recent_rev < total_rev * 0.2:
                    potential = total_rev * 0.15
                    opp_type = "upsell"
                    reasoning.append("Strong account health but declining recent orders")
                    reasoning.append(f"Recent revenue only {recent_rev / total_rev * 100:.0f}% of lifetime")
                    confidence = 0.60

            # Inactive with previous revenue = reactivation
            if not opp_type and total_rev > 0:
                last_inv = max((i.invoice_date for i in invoices if i.invoice_date), default=None)
                if last_inv and (date.today() - last_inv).days > 90:
                    potential = total_rev * 0.10
                    opp_type = "reactivation"
                    reasoning.append(f"No orders in {(date.today() - last_inv).days} days")
                    reasoning.append(f"Previous revenue: {total_rev:,.0f} AED")
                    confidence = 0.45

            if opp_type and potential > 0:
                potential_pct = (potential / total_rev * 100) if total_rev > 0 else 0
                opportunities.append({
                    "customer_id": str(cust.id),
                    "customer_name": cust.name,
                    "segment": cust.segment,
                    "current_revenue": round(total_rev, 2),
                    "potential_increase": round(potential, 2),
                    "potential_increase_pct": round(potential_pct, 1),
                    "opportunity_type": opp_type,
                    "reasoning": reasoning,
                    "confidence": confidence,
                    "health_score": health,
                    "currency": cust.currency or "AED",
                })
                by_type[opp_type] += 1

        opportunities.sort(key=lambda x: x["potential_increase"], reverse=True)
        top = opportunities[:limit]
        total_potential = sum(o["potential_increase"] for o in top)

        return {
            "items": top,
            "total": len(opportunities),
            "total_potential_revenue": round(total_potential, 2),
            "by_type": dict(by_type),
            "currency": "AED",
        }

    # ═══════════════════════════════════════════
    # SALES DASHBOARD SUMMARY
    # ═══════════════════════════════════════════

    async def get_dashboard_summary(self, db: AsyncSession, tenant_id: UUID) -> dict:
        """Aggregated sales dashboard overview."""
        pipeline = await self.get_pipeline_summary(db, tenant_id)
        reorder = await self.get_reorder_alerts(db, tenant_id)
        churn = await self.get_churn_watchlist(db, tenant_id)

        # Total AR and overdue
        ar_q = await db.execute(
            select(func.coalesce(func.sum(Invoice.amount_remaining), 0)).where(
                Invoice.tenant_id == tenant_id,
                Invoice.status.in_(["open", "partially_paid", "overdue"]),
            )
        )
        total_ar = float(ar_q.scalar() or 0)

        overdue_q = await db.execute(
            select(func.coalesce(func.sum(Invoice.amount_remaining), 0)).where(
                Invoice.tenant_id == tenant_id,
                Invoice.status.in_(["overdue"]),
            )
        )
        total_overdue = float(overdue_q.scalar() or 0)

        # Collection rate (30 days)
        today = date.today()
        thirty_ago = today - timedelta(days=30)
        pay_q = await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.tenant_id == tenant_id,
                Payment.payment_date >= thirty_ago,
            )
        )
        inv_q = await db.execute(
            select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                Invoice.tenant_id == tenant_id,
                Invoice.invoice_date >= thirty_ago,
            )
        )
        payments_30 = float(pay_q.scalar() or 0)
        invoiced_30 = float(inv_q.scalar() or 1)
        coll_rate = min(payments_30 / invoiced_30 * 100, 100) if invoiced_30 > 0 else 0

        # Customer count
        cust_count = (await db.execute(
            select(func.count()).where(
                Customer.tenant_id == tenant_id,
                Customer.is_deleted == False,
                Customer.status != CustomerStatus.INACTIVE,
            )
        )).scalar() or 0

        # Health distribution
        from app.services.intelligence import _health_scores
        health_dist = defaultdict(int)
        for s in _health_scores.values():
            health_dist[s.get("grade", "?")] += 1

        return {
            "pipeline": pipeline,
            "reorder_alerts_count": reorder["total"],
            "churn_high_risk_count": churn["high_risk_count"],
            "total_ar": round(total_ar, 2),
            "total_overdue": round(total_overdue, 2),
            "collection_rate": round(coll_rate, 1),
            "customer_count": cust_count,
            "health_distribution": dict(health_dist),
            "currency": "AED",
        }


# Singleton
sales_dashboard = SalesDashboardService()
