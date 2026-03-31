"""Day 14 End-to-End Tests: Health Scores, AI Credit, Credit Exposure, Customer 360, Chat Engine"""
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

        # Get a customer for testing
        custs = await c.get(f"{BASE}/customers/?page_size=5", headers=h)
        cust_id = None
        cust_name = None
        if custs.status_code == 200 and custs.json()["items"]:
            cust_id = custs.json()["items"][0]["id"]
            cust_name = custs.json()["items"][0]["name"]
            print(f"\n    Test customer: {cust_name} ({cust_id[:8]}...)")

        if not cust_id:
            print("\nERROR: No customers found. Cannot proceed.")
            return

        # ==============================
        # DAY 14: INTELLIGENCE LAYER
        # ==============================
        print("\n" + "=" * 60)
        print("DAY 14: INTELLIGENCE LAYER")
        print("=" * 60)

        # ── Health Score Engine ──
        print("\n--- Health Score Engine ---")

        # 1. Calculate health score for a customer
        hs1 = await c.get(f"{BASE}/intelligence/health-score/{cust_id}", headers=h)
        print(f"\n1. Health score for {cust_name}: {hs1.status_code}")
        if hs1.status_code == 200:
            s = hs1.json()
            print(f"   Composite: {s['composite_score']} (Grade: {s['grade']}, Trend: {s['trend']})")
            b = s['breakdown']
            print(f"   Payment: {b['payment_score']} | Engagement: {b['engagement_score']} | Order Trend: {b['order_trend_score']} | Risk Flags: {b['risk_flag_score']}")
            print(f"   Payment factors: {b['payment_factors'][:2]}")
            print(f"   Risk factors: {b['risk_factors'][:2]}")
            print(f"   Weights: payment={s['weights']['payment']} engagement={s['weights']['engagement']}")
        else:
            print(f"   Response: {hs1.text[:200]}")

        # 2. Calculate again (should show previous score and change)
        hs2 = await c.get(f"{BASE}/intelligence/health-score/{cust_id}", headers=h)
        print(f"\n2. Recalculate (with history): {hs2.status_code}")
        if hs2.status_code == 200:
            s2 = hs2.json()
            print(f"   Score: {s2['composite_score']} | Previous: {s2.get('previous_score')} | Change: {s2.get('score_change')}")

        # 3. Get health score history
        hist = await c.get(f"{BASE}/intelligence/health-score/{cust_id}/history", headers=h)
        print(f"\n3. Health score history: {hist.status_code}")
        if hist.status_code == 200:
            hd = hist.json()
            print(f"   Customer: {hd['customer_name']} | Current: {hd['current_score']} ({hd['current_grade']})")
            print(f"   History points: {len(hd['history'])}")
            print(f"   Trend: {hd['trend']}")

        # 4. Batch health scores (all customers)
        batch = await c.post(f"{BASE}/intelligence/health-score/batch", headers=h, json={})
        print(f"\n4. Batch health scores: {batch.status_code}")
        if batch.status_code == 200:
            bd = batch.json()
            print(f"   Customers processed: {bd['customers_processed']}")
            print(f"   Average score: {bd['avg_score']}")
            print(f"   Grade distribution: {bd['grade_distribution']}")
            print(f"   Top improvers: {[t['customer_name'] for t in bd['top_improvers'][:3]]}")
            print(f"   Duration: {bd['duration_ms']}ms")

        # 5. Health score for non-existent customer
        bad_hs = await c.get(f"{BASE}/intelligence/health-score/00000000-0000-0000-0000-000000000000", headers=h)
        print(f"\n5. Invalid customer health score: {bad_hs.status_code} (expected 404)")

        # ── AI Credit Recommendations ──
        print("\n--- AI Credit Recommendations ---")

        # 6. Get recommendations
        recs = await c.get(f"{BASE}/intelligence/credit/recommendations?limit=10", headers=h)
        print(f"\n6. Credit recommendations: {recs.status_code}")
        if recs.status_code == 200:
            rd = recs.json()
            print(f"   Total customers: {rd['total']}")
            print(f"   Summary: increases={rd['summary']['increases']} decreases={rd['summary']['decreases']} holds={rd['summary']['holds']}")
            print(f"   Avg confidence: {rd['summary']['avg_confidence']}")
            for item in rd["items"][:5]:
                arrow = "+" if item["change_type"] == "increase" else ("-" if item["change_type"] == "decrease" else "=")
                print(f"   {arrow} {item['customer_name']}: {item['current_limit']:,.0f} -> {item['recommended_limit']:,.0f} ({item['change_pct']:+.1f}%) confidence={item['confidence']}")
                if item['reasoning']:
                    print(f"     Reason: {item['reasoning'][0]}")

        # ── Credit Hold / Release ──
        print("\n--- Credit Hold / Release ---")

        # 7. Apply credit hold
        hold = await c.post(f"{BASE}/intelligence/credit/hold", headers=h, json={
            "customer_id": cust_id,
            "reason": "Test: Manual credit hold for review",
        })
        print(f"\n7. Apply credit hold: {hold.status_code}")
        if hold.status_code == 200:
            hd = hold.json()
            print(f"   Customer: {hd['customer_name']}")
            print(f"   Action: {hd['action']} | Previous: {hd['previous_status']} -> New: {hd['new_status']}")
            print(f"   Utilization: {hd['utilization_pct']}% | Threshold: {hd['threshold_pct']}%")

        # 8. Release credit hold
        release = await c.post(f"{BASE}/intelligence/credit/release", headers=h, json={
            "customer_id": cust_id,
            "reason": "Test: Payment received, releasing hold",
        })
        print(f"\n8. Release credit hold: {release.status_code}")
        if release.status_code == 200:
            rd = release.json()
            print(f"   Action: {rd['action']} | Previous: {rd['previous_status']} -> New: {rd['new_status']}")

        # 9. Auto-scan credit holds
        scan = await c.post(f"{BASE}/intelligence/credit/hold-scan", headers=h)
        print(f"\n9. Credit hold scan: {scan.status_code}")
        if scan.status_code == 200:
            sd = scan.json()
            print(f"   Customers scanned: {sd['customers_scanned']}")
            print(f"   Holds applied: {sd['holds_applied']} | Released: {sd['holds_released']} | Already held: {sd['already_held']}")
            if sd['details']:
                for d in sd['details'][:3]:
                    print(f"     - {d['customer']}: {d['action']} (util={d['utilization_pct']}%)")
            print(f"   Duration: {sd['duration_ms']}ms")

        # 10. Hold for invalid customer
        bad_hold = await c.post(f"{BASE}/intelligence/credit/hold", headers=h, json={
            "customer_id": "00000000-0000-0000-0000-000000000000",
        })
        print(f"\n10. Hold invalid customer: {bad_hold.status_code} (expected 404)")

        # ── Credit Exposure Dashboard ──
        print("\n--- Credit Exposure Dashboard ---")

        # 11. Get credit exposure
        exp = await c.get(f"{BASE}/intelligence/credit/exposure", headers=h)
        print(f"\n11. Credit exposure: {exp.status_code}")
        if exp.status_code == 200:
            ed = exp.json()
            print(f"    Total limit: {ed['total_credit_limit']:,.0f} {ed['currency']}")
            print(f"    Total utilization: {ed['total_utilization']:,.0f} {ed['currency']}")
            print(f"    Portfolio utilization: {ed['portfolio_utilization_pct']}%")
            print(f"    Customers on hold: {ed['hold_count']}")
            print(f"    Segments: {list(ed['by_segment'].keys())}")
            print(f"    Top utilization ({len(ed['top_utilization'])} customers):")
            for t in ed['top_utilization'][:3]:
                print(f"      - {t['customer_name']}: {t['utilization_pct']}% ({t['utilization']:,.0f}/{t['credit_limit']:,.0f})")
            print(f"    At risk: {len(ed['at_risk'])} customers")
            print(f"    Trending up: {len(ed['trending_up'])} customers")

        # ── Customer 360 AI Insights ──
        print("\n--- Customer 360 AI Insights ---")

        # 12. Full 360 view
        c360 = await c.get(f"{BASE}/intelligence/customer-360/{cust_id}", headers=h)
        print(f"\n12. Customer 360: {c360.status_code}")
        if c360.status_code == 200:
            cd = c360.json()
            print(f"    Customer: {cd['customer_name']} (Status: {cd['status']})")

            if cd.get('health_score'):
                hs = cd['health_score']
                print(f"    Health: {hs['composite_score']} ({hs['grade']}) trend={hs['trend']}")

            if cd.get('credit_status'):
                cs = cd['credit_status']
                print(f"    Credit: limit={cs['credit_limit']:,.0f} util={cs['utilization_pct']}% available={cs['available']:,.0f} hold={cs['on_hold']}")

            if cd.get('payment_analysis'):
                pa = cd['payment_analysis']
                print(f"    Payments: invoiced={pa['total_invoiced']:,.0f} paid={pa['total_paid']:,.0f} outstanding={pa['outstanding']:,.0f}")
                print(f"    Avg days to pay: {pa['avg_days_to_pay']}")

            if cd.get('predictions'):
                pr = cd['predictions']
                print(f"    Predictions: risk={pr['risk_score']} ({pr['risk_level']}) churn={pr['churn_probability']} ({pr['churn_risk']})")

            if cd.get('recommended_actions'):
                actions = cd['recommended_actions']
                print(f"    Recommended actions ({len(actions)}):")
                for a in actions[:3]:
                    print(f"      [{a['priority']}] {a['action'][:80]}")

            if cd.get('collection_history'):
                ch = cd['collection_history']
                print(f"    Collection history: {ch['total_activities']} activities")

            if cd.get('disputes'):
                dp = cd['disputes']
                print(f"    Disputes: {dp['total']} total, {dp['open']} open ({dp['open_amount']:,.0f} AED)")

        # 13. 360 with specific sections only
        c360_partial = await c.get(f"{BASE}/intelligence/customer-360/{cust_id}?sections=health_score,credit_status,recommended_actions", headers=h)
        print(f"\n13. Customer 360 (partial): {c360_partial.status_code}")
        if c360_partial.status_code == 200:
            pd = c360_partial.json()
            has_hs = pd.get('health_score') is not None
            has_cs = pd.get('credit_status') is not None
            has_pa = pd.get('payment_analysis') is not None  # should be None
            print(f"    Has health_score: {has_hs} | credit_status: {has_cs} | payment_analysis: {has_pa}")

        # 14. 360 for invalid customer
        bad_360 = await c.get(f"{BASE}/intelligence/customer-360/00000000-0000-0000-0000-000000000000", headers=h)
        print(f"\n14. 360 invalid customer: {bad_360.status_code} (expected 404)")

        # ── Chat Engine ──
        print("\n--- Chat Engine ---")

        # 15. Chat: greeting
        chat1 = await c.post(f"{BASE}/intelligence/chat", headers=h, json={
            "message": "Hello, I need help with our accounts receivable",
        })
        print(f"\n15. Chat (greeting): {chat1.status_code}")
        conv_id = None
        if chat1.status_code == 200:
            cd = chat1.json()
            conv_id = cd["conversation_id"]
            print(f"    Conversation ID: {conv_id[:8]}...")
            print(f"    Response: {cd['message']['content'][:150]}...")
            print(f"    Suggested questions: {cd['suggested_questions'][:2]}")
            print(f"    Processing: {cd['processing_time_ms']}ms")

        # 16. Chat: overdue query
        chat2 = await c.post(f"{BASE}/intelligence/chat", headers=h, json={
            "message": "Show me overdue invoices",
            "conversation_id": conv_id,
        })
        print(f"\n16. Chat (overdue query): {chat2.status_code}")
        if chat2.status_code == 200:
            cd2 = chat2.json()
            print(f"    Response: {cd2['message']['content'][:150]}...")
            print(f"    Citations: {len(cd2['data_citations'])}")
            print(f"    Entities: {len(cd2['entities_referenced'])}")
            if cd2['data_citations']:
                print(f"    First citation: {cd2['data_citations'][0]}")

        # 17. Chat: risk query
        chat3 = await c.post(f"{BASE}/intelligence/chat", headers=h, json={
            "message": "Which customers are highest risk?",
            "conversation_id": conv_id,
        })
        print(f"\n17. Chat (risk query): {chat3.status_code}")
        if chat3.status_code == 200:
            cd3 = chat3.json()
            print(f"    Response preview: {cd3['message']['content'][:150]}...")
            print(f"    Entities referenced: {len(cd3['entities_referenced'])}")

        # 18. Chat: credit query
        chat4 = await c.post(f"{BASE}/intelligence/chat", headers=h, json={
            "message": "What is our total credit exposure?",
        })
        print(f"\n18. Chat (credit query): {chat4.status_code}")
        if chat4.status_code == 200:
            cd4 = chat4.json()
            print(f"    New conversation: {cd4['conversation_id'][:8]}...")
            print(f"    Response: {cd4['message']['content'][:150]}...")

        # 19. Chat: dispute query
        chat5 = await c.post(f"{BASE}/intelligence/chat", headers=h, json={
            "message": "Give me a dispute summary",
        })
        print(f"\n19. Chat (disputes): {chat5.status_code}")
        if chat5.status_code == 200:
            print(f"    Response: {chat5.json()['message']['content'][:150]}...")

        # 20. Chat: health score query
        chat6 = await c.post(f"{BASE}/intelligence/chat", headers=h, json={
            "message": "Show health score overview",
        })
        print(f"\n20. Chat (health scores): {chat6.status_code}")
        if chat6.status_code == 200:
            print(f"    Response: {chat6.json()['message']['content'][:150]}...")

        # 21. Chat: collection query
        chat7 = await c.post(f"{BASE}/intelligence/chat", headers=h, json={
            "message": "What about collection activities and PTP?",
        })
        print(f"\n21. Chat (collections): {chat7.status_code}")
        if chat7.status_code == 200:
            print(f"    Response: {chat7.json()['message']['content'][:150]}...")

        # 22. Get conversation history
        if conv_id:
            history = await c.get(f"{BASE}/intelligence/chat/{conv_id}", headers=h)
            print(f"\n22. Chat history: {history.status_code}")
            if history.status_code == 200:
                hd = history.json()
                print(f"    Messages: {hd['message_count']}")
                print(f"    Started: {hd['started_at']}")
                for m in hd['messages'][:4]:
                    print(f"    [{m['role']}] {m['content'][:80]}...")

        # 23. List conversations
        convs = await c.get(f"{BASE}/intelligence/chat", headers=h)
        print(f"\n23. List conversations: {convs.status_code}")
        if convs.status_code == 200:
            cl = convs.json()
            print(f"    Total conversations: {len(cl)}")
            for cv in cl[:3]:
                print(f"    - {cv['conversation_id'][:8]}... ({cv['message_count']} msgs)")

        # 24. Get non-existent conversation
        bad_conv = await c.get(f"{BASE}/intelligence/chat/00000000-0000-0000-0000-000000000000", headers=h)
        print(f"\n24. Invalid conversation: {bad_conv.status_code} (expected 404)")

        # 25. Chat with unknown query (fallback)
        chat_fallback = await c.post(f"{BASE}/intelligence/chat", headers=h, json={
            "message": "What is the meaning of life?",
        })
        print(f"\n25. Chat (fallback): {chat_fallback.status_code}")
        if chat_fallback.status_code == 200:
            print(f"    Response: {chat_fallback.json()['message']['content'][:150]}...")

        print("\n" + "=" * 60)
        print("ALL DAY 14 TESTS COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
