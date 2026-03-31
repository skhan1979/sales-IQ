"""Day 16 End-to-End Tests: Sales Dashboard - Pipeline, Churn, Reorder, Revenue, Growth"""
import asyncio, httpx, json, sys, io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:8000/api/v1"


async def main():
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(f"{BASE}/auth/login", json={"email": "admin@salesiq.ai", "password": "Admin@2024", "tenant_slug": "demo"})
        tok = r.json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        print("=== Login OK ===")

        # Generate demo data
        print("\n--- Generating demo data ---")
        demo = await c.post(f"{BASE}/demo-data/generate", json={"dataset_size": "medium", "erp_profile": "d365_fo"}, headers=h)
        if demo.status_code in (200, 201):
            dd = demo.json()
            print(f"    Demo data: {dd.get('customers_created', '?')} customers, {dd.get('invoices_created', '?')} invoices")
        else:
            print(f"    Demo data: {demo.status_code} (may already exist)")

        # Pre-calculate health scores for enriched results
        print("\n--- Pre-calculating health scores ---")
        batch_hs = await c.post(f"{BASE}/intelligence/health-score/batch", headers=h, json={})
        if batch_hs.status_code == 200:
            print(f"    Scored {batch_hs.json()['customers_processed']} customers")

        # ==============================
        # DAY 16: SALES DASHBOARD
        # ==============================
        print("\n" + "=" * 60)
        print("DAY 16: SALES DASHBOARD (VP SALES VIEW)")
        print("=" * 60)

        # ── Sales Dashboard Summary ──
        print("\n--- Sales Dashboard Summary ---")

        # 1. Full dashboard summary
        summary = await c.get(f"{BASE}/sales/summary", headers=h)
        print(f"\n1. Dashboard summary: {summary.status_code}")
        if summary.status_code == 200:
            sd = summary.json()
            print(f"   Customers: {sd['customer_count']}")
            print(f"   Total AR: {sd['total_ar']:,.0f} {sd['currency']}")
            print(f"   Total overdue: {sd['total_overdue']:,.0f}")
            print(f"   Collection rate: {sd['collection_rate']}%")
            print(f"   Reorder alerts: {sd['reorder_alerts_count']}")
            print(f"   Churn high risk: {sd['churn_high_risk_count']}")
            print(f"   Health distribution: {sd['health_distribution']}")
            print(f"   Pipeline value: {sd['pipeline']['total_pipeline_value']:,.0f}")
            print(f"   Pipeline stages: {len(sd['pipeline']['stages'])}")

        # ── Pipeline ──
        print("\n--- Pipeline ---")

        # 2. Pipeline summary
        pipeline = await c.get(f"{BASE}/sales/pipeline", headers=h)
        print(f"\n2. Pipeline summary: {pipeline.status_code}")
        if pipeline.status_code == 200:
            pd = pipeline.json()
            print(f"   Total value: {pd['total_pipeline_value']:,.0f} {pd['currency']}")
            print(f"   Opportunities: {pd['total_opportunities']}")
            print(f"   Avg deal size: {pd['avg_deal_size']:,.0f}")
            print(f"   Weighted pipeline: {pd['weighted_pipeline']:,.0f}")
            print(f"   Conversion rate: {pd['conversion_rate']}%")
            print(f"   Stages:")
            for s in pd["stages"]:
                print(f"     - {s['stage']}: {s['count']} deals, {s['amount']:,.0f} ({s['pct_of_total']}%)")

        # ── Reorder Alerts ──
        print("\n--- Reorder Alerts ---")

        # 3. Reorder alerts
        reorder = await c.get(f"{BASE}/sales/reorder-alerts", headers=h)
        print(f"\n3. Reorder alerts: {reorder.status_code}")
        if reorder.status_code == 200:
            ra = reorder.json()
            print(f"   Total alerts: {ra['total']}")
            print(f"   By level: {ra['by_alert_level']}")
            print(f"   At-risk revenue: {ra['total_at_risk_revenue']:,.0f} {ra['currency']}")
            for a in ra["items"][:5]:
                hs_str = f" HS={a['health_score']:.0f}" if a.get('health_score') else ""
                print(f"     [{a['alert_level']}] {a['customer_name']}: {a['days_since_last_order']}d since last order, avg value={a['avg_order_value']:,.0f}{hs_str}")

        # ── Churn Watchlist ──
        print("\n--- Churn Watchlist ---")

        # 4. Churn watchlist
        churn = await c.get(f"{BASE}/sales/churn-watchlist", headers=h)
        print(f"\n4. Churn watchlist: {churn.status_code}")
        if churn.status_code == 200:
            cw = churn.json()
            print(f"   Total on watchlist: {cw['total']}")
            print(f"   High risk: {cw['high_risk_count']} | Medium: {cw['medium_risk_count']} | Low: {cw['low_risk_count']}")
            print(f"   Total AR at risk: {cw['total_ar_at_risk']:,.0f} {cw['currency']}")
            for e in cw["items"][:5]:
                grade = f" ({e['health_grade']})" if e.get('health_grade') else ""
                days_pay = f" {e['days_since_last_payment']}d since pay" if e.get('days_since_last_payment') else ""
                print(f"     [{e['churn_risk']}] {e['customer_name']}: churn={e['churn_probability']:.1%} trend={e['trend']}{grade}{days_pay}")
                print(f"       Factors: {e['risk_factors'][:2]}")
                print(f"       Action: {e['recommended_action'][:80]}")

        # ── Revenue by Segment ──
        print("\n--- Revenue by Segment ---")

        # 5. Revenue by segment
        revenue = await c.get(f"{BASE}/sales/revenue-by-segment", headers=h)
        print(f"\n5. Revenue by segment: {revenue.status_code}")
        if revenue.status_code == 200:
            rv = revenue.json()
            print(f"   Total revenue: {rv['total_revenue']:,.0f} {rv['currency']}")
            print(f"   Top segment: {rv['top_segment']}")
            print(f"   Segments:")
            for s in rv["segments"]:
                print(f"     - {s['segment']}: {s['customer_count']} customers, invoiced={s['total_invoiced']:,.0f}, collected={s['total_collected']:,.0f} ({s['collection_rate']}%)")

        # ── Growth Opportunities ──
        print("\n--- Growth Opportunities ---")

        # 6. Growth opportunities
        growth = await c.get(f"{BASE}/sales/growth-opportunities?limit=10", headers=h)
        print(f"\n6. Growth opportunities: {growth.status_code}")
        if growth.status_code == 200:
            gd = growth.json()
            print(f"   Total opportunities: {gd['total']}")
            print(f"   Total potential: {gd['total_potential_revenue']:,.0f} {gd['currency']}")
            print(f"   By type: {gd['by_type']}")
            for o in gd["items"][:5]:
                hs_str = f" HS={o['health_score']:.0f}" if o.get('health_score') else ""
                print(f"     [{o['opportunity_type']}] {o['customer_name']}: +{o['potential_increase']:,.0f} ({o['potential_increase_pct']}%) conf={o['confidence']}{hs_str}")
                if o['reasoning']:
                    print(f"       Reason: {o['reasoning'][0][:80]}")

        # ── Cross-feature verification ──
        print("\n--- Cross-Feature Verification ---")

        # 7. Customer 360 still works (click-through target)
        custs = await c.get(f"{BASE}/customers/?page_size=1", headers=h)
        if custs.status_code == 200 and custs.json()["items"]:
            cust_id = custs.json()["items"][0]["id"]
            c360 = await c.get(f"{BASE}/intelligence/customer-360/{cust_id}?sections=health_score,credit_status,predictions", headers=h)
            print(f"\n7. Customer 360 cross-link: {c360.status_code}")
            if c360.status_code == 200:
                cd = c360.json()
                print(f"   Customer: {cd['customer_name']}")
                if cd.get('health_score'):
                    print(f"   Health: {cd['health_score']['composite_score']} ({cd['health_score']['grade']})")

        # 8. CFO dashboard still works
        ar = await c.get(f"{BASE}/dashboard/ar-summary", headers=h)
        print(f"\n8. CFO AR summary: {ar.status_code}")
        if ar.status_code == 200:
            print(f"   Total receivables: {float(ar.json()['total_receivables']):,.0f}")

        # 9. Intelligence credit exposure
        exp = await c.get(f"{BASE}/intelligence/credit/exposure", headers=h)
        print(f"\n9. Credit exposure: {exp.status_code}")
        if exp.status_code == 200:
            print(f"   Portfolio utilization: {exp.json()['portfolio_utilization_pct']}%")

        # 10. Chat about sales
        chat = await c.post(f"{BASE}/intelligence/chat", headers=h, json={
            "message": "What are the top risky customers I should watch?",
        })
        print(f"\n10. Chat (sales context): {chat.status_code}")
        if chat.status_code == 200:
            print(f"    Response: {chat.json()['message']['content'][:120]}...")

        print("\n" + "=" * 60)
        print("ALL DAY 16 TESTS COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
