"""Day 7 - Dispute, Credit Limit, Collection Workflow Tests"""
import asyncio, httpx, json

BASE = "http://localhost:8000/api/v1"


async def main():
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{BASE}/auth/login", json={"email": "admin@salesiq.ai", "password": "Admin@2024", "tenant_slug": "demo"})
        tok = r.json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        print("=== Login OK ===")

        # Clean slate: clear demo data then regenerate
        await c.request("DELETE", f"{BASE}/demo-data/clear", headers=h, json={"confirm": True})

        # Check if we already have customers (from CSV import or previous runs)
        custs = await c.get(f"{BASE}/customers/?page_size=1", headers=h)
        if not custs.json()["items"]:
            # No customers exist - generate demo data
            gen = await c.post(f"{BASE}/demo-data/generate", headers=h, json={"size": "small", "erp_profile": "d365_fo"})
            print(f"Demo data: {gen.status_code} ({gen.json().get('customers', 0)} customers)")
            custs = await c.get(f"{BASE}/customers/?page_size=1", headers=h)

        cust_id = custs.json()["items"][0]["id"]
        cust_name = custs.json()["items"][0]["name"]
        cust_credit = custs.json()["items"][0]["credit_limit"]
        print(f"Test customer: {cust_name} (credit={cust_credit})")

        invs = await c.get(f"{BASE}/invoices/?customer_id={cust_id}&page_size=1", headers=h)
        inv_id = None
        if invs.json()["items"]:
            inv_id = invs.json()["items"][0]["id"]
            inv_num = invs.json()["items"][0]["invoice_number"]
            print(f"Test invoice: {inv_num}")

        # Clean up any pending credit limit requests for this customer from prior runs
        cl_existing = await c.get(f"{BASE}/credit-limits/?customer_id={cust_id}&status=pending", headers=h)
        if cl_existing.status_code == 200:
            for req_item in cl_existing.json().get("items", []):
                await c.post(f"{BASE}/credit-limits/{req_item['id']}/decide", headers=h, json={
                    "action": "reject",
                    "approval_notes": "Cleanup before test run",
                })
            if cl_existing.json().get("items"):
                print(f"Cleaned {len(cl_existing.json()['items'])} pending credit requests")

        # ============================
        # DISPUTE WORKFLOW
        # ============================
        print("\n=== DISPUTE MANAGEMENT ===")

        # 1. Create dispute
        dsp = await c.post(f"{BASE}/disputes/", headers=h, json={
            "customer_id": cust_id,
            "invoice_id": inv_id,
            "reason": "pricing",
            "reason_detail": "Customer claims unit price was agreed at 10% discount",
            "amount": 15000,
            "currency": "AED",
            "priority": "high",
            "assigned_department": "Finance",
        })
        print(f"1. Create dispute: {dsp.status_code}")
        dsp_id = None
        if dsp.status_code == 201:
            dd = dsp.json()
            dsp_id = dd["id"]
            print(f"   #{dd['dispute_number']} | {dd['status']} | {dd['amount']} {dd['currency']} | SLA: {dd['sla_due_date']}")

        # 2. Transition: open -> in_review
        if dsp_id:
            t1 = await c.post(f"{BASE}/disputes/{dsp_id}/transition", headers=h, json={
                "action": "review",
                "notes": "Checking pricing agreement with sales team",
            })
            print(f"2. Open -> In Review: {t1.status_code} | status={t1.json().get('status')}")

        # 3. Transition: in_review -> escalated
        if dsp_id:
            t2 = await c.post(f"{BASE}/disputes/{dsp_id}/transition", headers=h, json={
                "action": "escalate",
                "notes": "Needs CFO approval for credit note",
            })
            print(f"3. In Review -> Escalated: {t2.status_code} | status={t2.json().get('status')}")

        # 4. Transition: escalated -> resolved (credit note)
        if dsp_id:
            t3 = await c.post(f"{BASE}/disputes/{dsp_id}/transition", headers=h, json={
                "action": "resolve",
                "resolution_type": "credit_note",
                "resolution_amount": 12000,
                "notes": "Confirmed pricing error. Issuing credit note for AED 12,000",
            })
            print(f"4. Escalated -> Resolved: {t3.status_code} | status={t3.json().get('status')} | resolution={t3.json().get('resolution_type')}")

        # 5. Invalid transition (resolve already resolved)
        if dsp_id:
            t4 = await c.post(f"{BASE}/disputes/{dsp_id}/transition", headers=h, json={
                "action": "resolve",
            })
            print(f"5. Invalid transition (already resolved): {t4.status_code} (expect 400)")

        # 6. Reopen resolved dispute
        if dsp_id:
            t5 = await c.post(f"{BASE}/disputes/{dsp_id}/transition", headers=h, json={
                "action": "reopen",
                "notes": "Customer found additional discrepancy",
            })
            print(f"6. Reopen: {t5.status_code} | status={t5.json().get('status')}")

        # 7. Create second dispute and reject it
        dsp2 = await c.post(f"{BASE}/disputes/", headers=h, json={
            "customer_id": cust_id,
            "reason": "duplicate",
            "reason_detail": "Customer claims invoice was sent twice",
            "amount": 5000,
            "priority": "low",
        })
        if dsp2.status_code == 201:
            dsp2_id = dsp2.json()["id"]
            rej = await c.post(f"{BASE}/disputes/{dsp2_id}/transition", headers=h, json={
                "action": "reject",
                "notes": "Verified invoice is unique - no duplicate found",
            })
            print(f"7. Create + Reject: {rej.status_code} | status={rej.json().get('status')}")

        # 8. Dispute summary
        summary = await c.get(f"{BASE}/disputes/summary/overview", headers=h)
        print(f"8. Dispute Summary: {summary.status_code}")
        if summary.status_code == 200:
            sd = summary.json()
            print(f"   Total: {sd['total_disputes']} | Open: {sd['open_count']} | Resolved: {sd['resolved_count']}")
            print(f"   Disputed amount: {sd['total_disputed_amount']} | SLA breached: {sd['sla_breached_count']}")
            print(f"   By reason: {sd['by_reason']}")

        # ============================
        # CREDIT LIMIT WORKFLOW
        # ============================
        print("\n=== CREDIT LIMIT APPROVAL ===")

        # 9. Create credit limit request
        cl = await c.post(f"{BASE}/credit-limits/", headers=h, json={
            "customer_id": cust_id,
            "requested_limit": float(cust_credit) * 1.5 if cust_credit else 500000,
            "currency": "AED",
            "justification": "Customer expanding operations, order volume increasing 40%",
        })
        print(f"9. Create credit request: {cl.status_code}")
        cl_id = None
        if cl.status_code == 201:
            cld = cl.json()
            cl_id = cld["id"]
            print(f"   Current: {cld['current_limit']} | Requested: {cld['requested_limit']} | AI recommended: {cld['ai_recommended_limit']}")
            print(f"   Status: {cld['approval_status']}")
            if cld.get("ai_risk_assessment"):
                ai = cld["ai_risk_assessment"]
                print(f"   Risk score: {ai.get('risk_score')} | Recommendation: {ai.get('recommendation')}")
                for rf in ai.get("risk_factors", [])[:3]:
                    print(f"     - {rf['factor']}: {rf['detail']} ({rf['impact']})")

        # 10. Approve credit limit (with modified amount)
        if cl_id:
            approve = await c.post(f"{BASE}/credit-limits/{cl_id}/decide", headers=h, json={
                "action": "approve",
                "approved_limit": float(cust_credit) * 1.3 if cust_credit else 400000,
                "approval_notes": "Approved at 130% of current limit based on payment history",
            })
            print(f"10. Approve: {approve.status_code} | status={approve.json().get('approval_status')} | approved={approve.json().get('approved_limit')}")

        # 11. Verify customer credit limit updated
        cust_after = await c.get(f"{BASE}/customers/{cust_id}", headers=h)
        if cust_after.status_code == 200:
            print(f"11. Customer updated: credit_limit={cust_after.json()['credit_limit']}")

        # 12. New request after first was approved (should succeed since no pending exists)
        cl2 = await c.post(f"{BASE}/credit-limits/", headers=h, json={
            "customer_id": cust_id,
            "requested_limit": 1000000,
        })
        print(f"12. Second request (after approval): {cl2.status_code} (expect 201)")

        # 13. List credit requests
        cl_list = await c.get(f"{BASE}/credit-limits/", headers=h)
        print(f"13. List requests: {cl_list.status_code} | total={cl_list.json().get('total')}")

        # ============================
        # COLLECTION ACTIVITIES
        # ============================
        print("\n=== COLLECTION ACTIVITIES ===")

        # 14. Log email reminder
        act1 = await c.post(f"{BASE}/collections/", headers=h, json={
            "customer_id": cust_id,
            "invoice_id": inv_id,
            "action_type": "email_reminder",
            "action_date": "2026-03-15",
            "notes": "Sent first payment reminder email",
        })
        print(f"14. Email reminder: {act1.status_code}")

        # 15. Log phone call
        act2 = await c.post(f"{BASE}/collections/", headers=h, json={
            "customer_id": cust_id,
            "invoice_id": inv_id,
            "action_type": "phone_call",
            "action_date": "2026-03-16",
            "notes": "Spoke with accounts payable manager",
        })
        print(f"15. Phone call: {act2.status_code}")

        # 16. Log promise to pay
        ptp = await c.post(f"{BASE}/collections/", headers=h, json={
            "customer_id": cust_id,
            "invoice_id": inv_id,
            "action_type": "promise_to_pay",
            "action_date": "2026-03-17",
            "notes": "Customer promised to settle by end of month",
            "ptp_date": "2026-03-31",
            "ptp_amount": 50000,
        })
        ptp_id = None
        if ptp.status_code == 201:
            ptp_id = ptp.json()["id"]
            print(f"16. PTP logged: {ptp.status_code} | ptp_date={ptp.json()['ptp_date']} | amount={ptp.json()['ptp_amount']}")

        # 17. Mark PTP as fulfilled
        if ptp_id:
            ptp_update = await c.patch(f"{BASE}/collections/{ptp_id}", headers=h, json={
                "ptp_fulfilled": True,
                "notes": "Payment received as promised",
            })
            print(f"17. PTP fulfilled: {ptp_update.status_code} | fulfilled={ptp_update.json().get('ptp_fulfilled')}")

        # 18. Collection summary
        coll_summary = await c.get(f"{BASE}/collections/summary", headers=h)
        print(f"18. Collection Summary: {coll_summary.status_code}")
        if coll_summary.status_code == 200:
            cs = coll_summary.json()
            print(f"    Total: {cs['total_activities']} | This month: {cs['activities_this_month']}")
            print(f"    PTP: {cs['promises_to_pay']} | Fulfilled: {cs['ptp_fulfilled']} | Broken: {cs['ptp_broken']}")
            print(f"    By type: {cs['by_action_type']}")

        # ============================
        # FINAL CHECKS
        # ============================
        print("\n=== FINAL CHECKS ===")
        all_pass = all([
            dsp.status_code == 201,
            t1.status_code == 200 if "t1" in dir() else True,
            t2.status_code == 200 if "t2" in dir() else True,
            t3.status_code == 200 if "t3" in dir() else True,
            t4.status_code == 400 if "t4" in dir() else True,
            t5.status_code == 200 if "t5" in dir() else True,
            summary.status_code == 200,
            cl.status_code == 201,
            approve.status_code == 200 if "approve" in dir() else True,
            cl2.status_code == 201,
            act1.status_code == 201,
            ptp.status_code == 201,
            ptp_update.status_code == 200 if "ptp_update" in dir() else True,
            coll_summary.status_code == 200,
        ])
        print("=== ALL DAY 7 TESTS PASSED ===" if all_pass else "=== SOME TESTS FAILED ===")

        # Cleanup demo data
        await c.request("DELETE", f"{BASE}/demo-data/clear", headers=h, json={"confirm": True})
        print("Demo data cleaned up.")


asyncio.run(main())
