"""Day 13 End-to-End Tests: Collections Copilot - AI Messages, Escalation, PTP, Dispute Aging"""
import asyncio, httpx, json, sys, io
from datetime import date, timedelta

# Fix Windows console encoding for unicode
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:8000/api/v1"


async def main():
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{BASE}/auth/login", json={"email": "admin@salesiq.ai", "password": "Admin@2024", "tenant_slug": "demo"})
        tok = r.json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        print("=== Login OK ===")

        # Generate demo data (ensures customers, invoices, disputes exist)
        print("\n--- Generating demo data ---")
        demo = await c.post(f"{BASE}/demo-data/generate", json={"dataset_size": "medium", "erp_profile": "d365_fo"}, headers=h)
        if demo.status_code in (200, 201):
            dd = demo.json()
            print(f"    Demo data: {dd.get('customers_created', '?')} customers, {dd.get('invoices_created', '?')} invoices")
        else:
            print(f"    Demo data: {demo.status_code} (may already exist)")

        # Get a customer with overdue invoices for testing
        custs = await c.get(f"{BASE}/customers/?page_size=5", headers=h)
        cust_id = None
        if custs.status_code == 200 and custs.json()["items"]:
            cust_id = custs.json()["items"][0]["id"]
            cust_name = custs.json()["items"][0]["name"]
            print(f"\n    Test customer: {cust_name} ({cust_id[:8]}...)")

        if not cust_id:
            print("\nERROR: No customers found. Cannot proceed with tests.")
            return

        # ==============================
        # DAY 13: COLLECTIONS COPILOT
        # ==============================
        print("\n" + "=" * 60)
        print("DAY 13: COLLECTIONS COPILOT")
        print("=" * 60)

        # ── AI Message Drafting ──
        print("\n--- AI Message Drafting ---")

        # 1. Draft friendly email (English)
        draft1 = await c.post(f"{BASE}/collections-copilot/draft", headers=h, json={
            "customer_id": cust_id,
            "channel": "email",
            "tone": "friendly",
            "language": "en",
            "include_payment_link": False,
        })
        print(f"\n1. Draft friendly email: {draft1.status_code}")
        draft_id = None
        if draft1.status_code == 201:
            d1 = draft1.json()
            draft_id = d1["draft_id"]
            print(f"   Draft ID: {draft_id[:8]}...")
            print(f"   Customer: {d1['customer_name']}")
            print(f"   Subject: {d1.get('subject', 'N/A')[:60]}")
            print(f"   Body preview: {d1['body'][:100]}...")
            print(f"   Invoices referenced: {len(d1['invoices_referenced'])}")
            print(f"   Total amount due: {d1['total_amount_due']} {d1['currency']}")
            print(f"   AI confidence: {d1['ai_confidence']}")
            print(f"   Suggested follow-up: {d1['suggested_follow_up_days']} days")
        else:
            print(f"   Response: {draft1.text[:200]}")

        # 2. Draft urgent email (English)
        draft2 = await c.post(f"{BASE}/collections-copilot/draft", headers=h, json={
            "customer_id": cust_id,
            "channel": "email",
            "tone": "urgent",
            "language": "en",
            "include_payment_link": True,
        })
        print(f"\n2. Draft urgent email: {draft2.status_code}")
        if draft2.status_code == 201:
            d2 = draft2.json()
            print(f"   Subject: {d2.get('subject', 'N/A')[:60]}")
            print(f"   Contains payment link: {'pay.salesiq.ai' in d2['body']}")

        # 3. Draft WhatsApp message
        draft3 = await c.post(f"{BASE}/collections-copilot/draft", headers=h, json={
            "customer_id": cust_id,
            "channel": "whatsapp",
            "tone": "friendly",
            "language": "en",
        })
        print(f"\n3. Draft WhatsApp message: {draft3.status_code}")
        if draft3.status_code == 201:
            d3 = draft3.json()
            print(f"   Body: {d3['body'][:100]}...")
            print(f"   No subject (WhatsApp): {d3.get('subject') is None}")

        # 4. Draft Arabic email
        draft4 = await c.post(f"{BASE}/collections-copilot/draft", headers=h, json={
            "customer_id": cust_id,
            "channel": "email",
            "tone": "friendly",
            "language": "ar",
        })
        print(f"\n4. Draft Arabic email: {draft4.status_code}")
        if draft4.status_code == 201:
            d4 = draft4.json()
            print(f"   Subject (AR): {d4.get('subject', 'N/A')[:60]}")
            print(f"   Language: {d4['language']}")

        # 5. Draft with custom instructions
        draft5 = await c.post(f"{BASE}/collections-copilot/draft", headers=h, json={
            "customer_id": cust_id,
            "channel": "email",
            "tone": "firm",
            "language": "en",
            "custom_instructions": "Mention the upcoming credit review",
        })
        print(f"\n5. Draft with custom instructions: {draft5.status_code}")
        if draft5.status_code == 201:
            d5 = draft5.json()
            print(f"   Custom note in body: {'credit review' in d5['body'].lower()}")

        # 6. Send drafted message (with edits)
        if draft_id:
            send1 = await c.post(f"{BASE}/collections-copilot/draft/{draft_id}/send", headers=h, json={
                "draft_id": draft_id,
                "edited_subject": "Updated: Payment Reminder",
                "edited_body": None,
                "send_now": True,
            })
            print(f"\n6. Send message (with edit): {send1.status_code}")
            if send1.status_code == 200:
                s1 = send1.json()
                print(f"   Message ID: {s1['message_id'][:8]}...")
                print(f"   Status: {s1['status']}")
                print(f"   Channel: {s1['channel']}")
                print(f"   Sent at: {s1.get('sent_at', 'N/A')}")

        # 7. Send another draft as-is
        draft_id_2 = None
        if draft2.status_code == 201:
            draft_id_2 = draft2.json()["draft_id"]
            send2 = await c.post(f"{BASE}/collections-copilot/draft/{draft_id_2}/send", headers=h, json={
                "draft_id": draft_id_2,
                "send_now": True,
            })
            print(f"\n7. Send message (no edits): {send2.status_code}")
            if send2.status_code == 200:
                print(f"   Status: {send2.json()['status']}")

        # 8. List message history
        messages = await c.get(f"{BASE}/collections-copilot/messages", headers=h)
        print(f"\n8. List messages: {messages.status_code}")
        if messages.status_code == 200:
            ml = messages.json()
            print(f"   Total sent: {ml['total']}")
            for m in ml["items"][:3]:
                print(f"   - [{m['channel']}] {m['status']} | {m.get('subject', m['body'][:40])}...")

        # 9. List messages filtered by customer
        msgs_filtered = await c.get(f"{BASE}/collections-copilot/messages?customer_id={cust_id}", headers=h)
        print(f"\n9. Messages for customer: {msgs_filtered.status_code}")
        if msgs_filtered.status_code == 200:
            print(f"   Count: {msgs_filtered.json()['total']}")

        # 10. Draft for non-existent customer (expect 400)
        bad_draft = await c.post(f"{BASE}/collections-copilot/draft", headers=h, json={
            "customer_id": "00000000-0000-0000-0000-000000000000",
            "channel": "email",
            "tone": "friendly",
            "language": "en",
        })
        print(f"\n10. Draft for invalid customer: {bad_draft.status_code} (expected 400)")

        # ── Escalation Templates ──
        print("\n--- Escalation Templates ---")

        # 11. Create escalation template
        tpl1 = await c.post(f"{BASE}/collections-copilot/templates", headers=h, json={
            "name": "Standard Overdue Sequence",
            "description": "3-step escalation for overdue invoices",
            "trigger_type": "overdue_days",
            "trigger_threshold": 30,
            "steps": [
                {"day_offset": 0, "action_type": "email", "message_tone": "friendly", "auto_execute": True},
                {"day_offset": 7, "action_type": "phone_call", "message_tone": "firm", "auto_execute": False,
                 "assignee_role": "collector"},
                {"day_offset": 14, "action_type": "manager_escalation", "message_tone": "urgent",
                 "auto_execute": True, "description": "Escalate to finance manager"},
            ],
            "is_active": True,
        })
        print(f"\n11. Create escalation template: {tpl1.status_code}")
        tpl_id = None
        if tpl1.status_code == 201:
            t1 = tpl1.json()
            tpl_id = t1["id"]
            print(f"    Template: {t1['name']} (id={tpl_id[:8]}...)")
            print(f"    Trigger: {t1['trigger_type']} >= {t1['trigger_threshold']} days")
            print(f"    Steps: {len(t1['steps'])}")
            for s in t1["steps"]:
                print(f"      Day +{s['day_offset']}: {s['action_type']} [{s['message_tone']}] auto={s['auto_execute']}")

        # 12. Create PTP-broken template
        tpl2 = await c.post(f"{BASE}/collections-copilot/templates", headers=h, json={
            "name": "PTP Broken Follow-Up",
            "description": "Actions when PTP is broken",
            "trigger_type": "ptp_broken",
            "trigger_threshold": 1,
            "steps": [
                {"day_offset": 0, "action_type": "whatsapp", "message_tone": "firm", "auto_execute": True},
                {"day_offset": 3, "action_type": "credit_hold", "message_tone": "urgent", "auto_execute": False},
            ],
            "is_active": True,
        })
        print(f"\n12. Create PTP-broken template: {tpl2.status_code}")
        tpl2_id = tpl2.json()["id"] if tpl2.status_code == 201 else None

        # 13. List templates
        tpl_list = await c.get(f"{BASE}/collections-copilot/templates", headers=h)
        print(f"\n13. List templates: {tpl_list.status_code}")
        if tpl_list.status_code == 200:
            tl = tpl_list.json()
            print(f"    Total: {tl['total']}")
            for t in tl["items"]:
                print(f"    - {t['name']}: trigger={t['trigger_type']} steps={len(t['steps'])} active={t['is_active']}")

        # 14. Update template
        if tpl_id:
            tpl_upd = await c.patch(f"{BASE}/collections-copilot/templates/{tpl_id}", headers=h, json={
                "trigger_threshold": 45,
                "description": "Updated: 3-step escalation for 45+ days overdue",
            })
            print(f"\n14. Update template: {tpl_upd.status_code}")
            if tpl_upd.status_code == 200:
                print(f"    New threshold: {tpl_upd.json()['trigger_threshold']}")

        # 15. Run escalation scan
        scan = await c.post(f"{BASE}/collections-copilot/escalations/scan", headers=h)
        print(f"\n15. Escalation scan: {scan.status_code}")
        if scan.status_code == 200:
            sc = scan.json()
            print(f"    Customers evaluated: {sc['customers_evaluated']}")
            print(f"    Escalations triggered: {sc['escalations_triggered']}")
            print(f"    Actions queued: {sc['actions_queued']}")
            print(f"    By template: {sc['by_template']}")
            print(f"    By action type: {sc['by_action_type']}")
            print(f"    Duration: {sc['duration_ms']}ms")

        # ── Enhanced PTP Tracking ──
        print("\n--- Promise-to-Pay Tracking ---")

        # 16. Create PTP
        future_date = (date.today() + timedelta(days=14)).isoformat()
        ptp1 = await c.post(f"{BASE}/collections-copilot/ptp", headers=h, json={
            "customer_id": cust_id,
            "promised_date": future_date,
            "promised_amount": 50000.00,
            "currency": "AED",
            "notes": "Agreed via phone call on March 18",
            "contact_person": "Ahmad Finance Dept",
            "contact_method": "phone",
        })
        print(f"\n16. Create PTP: {ptp1.status_code}")
        ptp_id = None
        if ptp1.status_code == 201:
            p1 = ptp1.json()
            ptp_id = p1["id"]
            print(f"    PTP ID: {ptp_id[:8]}...")
            print(f"    Customer: {p1['customer_name']}")
            print(f"    Promised: {p1['promised_amount']} {p1['currency']} by {p1['promised_date']}")
            print(f"    Status: {p1['status']}")
            print(f"    Days until due: {p1['days_until_due']}")
            print(f"    Contact: {p1.get('contact_person')} via {p1.get('contact_method')}")

        # 17. Create second PTP (different amount)
        future_date2 = (date.today() + timedelta(days=7)).isoformat()
        ptp2 = await c.post(f"{BASE}/collections-copilot/ptp", headers=h, json={
            "customer_id": cust_id,
            "promised_date": future_date2,
            "promised_amount": 25000.00,
            "currency": "AED",
            "notes": "Partial payment arrangement",
            "contact_person": "Finance Team",
            "contact_method": "email",
        })
        print(f"\n17. Create second PTP: {ptp2.status_code}")
        ptp2_id = ptp2.json()["id"] if ptp2.status_code == 201 else None

        # 18. Update PTP (partial fulfillment)
        if ptp_id:
            ptp_upd = await c.patch(f"{BASE}/collections-copilot/ptp/{ptp_id}", headers=h, json={
                "actual_amount": 30000.00,
                "actual_date": date.today().isoformat(),
                "notes": "Partial payment received - 30K of 50K",
            })
            print(f"\n18. Update PTP (partial): {ptp_upd.status_code}")
            if ptp_upd.status_code == 200:
                pu = ptp_upd.json()
                print(f"    Status: {pu['status']} (expected partially_fulfilled)")
                print(f"    Actual amount: {pu.get('actual_amount')}")

        # 19. Update PTP (mark fulfilled)
        if ptp2_id:
            ptp_upd2 = await c.patch(f"{BASE}/collections-copilot/ptp/{ptp2_id}", headers=h, json={
                "actual_amount": 25000.00,
                "actual_date": date.today().isoformat(),
                "notes": "Full payment received",
            })
            print(f"\n19. Update PTP (fulfilled): {ptp_upd2.status_code}")
            if ptp_upd2.status_code == 200:
                pu2 = ptp_upd2.json()
                print(f"    Status: {pu2['status']} (expected fulfilled)")

        # 20. List PTPs
        ptps = await c.get(f"{BASE}/collections-copilot/ptp", headers=h)
        print(f"\n20. List PTPs: {ptps.status_code}")
        if ptps.status_code == 200:
            pl = ptps.json()
            print(f"    Total: {pl['total']}")
            print(f"    Summary: fulfilled={pl['summary']['fulfilled_count']} broken={pl['summary']['broken_count']} pending={pl['summary']['pending_count']}")
            print(f"    Fulfillment rate: {pl['summary']['fulfillment_rate']}%")
            for p in pl["items"][:3]:
                print(f"    - {p['customer_name']}: {p['promised_amount']} {p['currency']} by {p['promised_date']} [{p['status']}]")

        # 21. Filter PTPs by status
        ptps_filtered = await c.get(f"{BASE}/collections-copilot/ptp?status=fulfilled", headers=h)
        print(f"\n21. PTPs (fulfilled only): {ptps_filtered.status_code}")
        if ptps_filtered.status_code == 200:
            print(f"    Count: {ptps_filtered.json()['total']}")

        # 22. PTP Dashboard
        ptp_dash = await c.get(f"{BASE}/collections-copilot/ptp/dashboard", headers=h)
        print(f"\n22. PTP Dashboard: {ptp_dash.status_code}")
        if ptp_dash.status_code == 200:
            pd = ptp_dash.json()
            print(f"    Total promises: {pd['total_promises']}")
            print(f"    Promised amount: {pd['total_promised_amount']} {pd['currency']}")
            print(f"    Fulfilled: {pd['fulfilled_count']} ({pd['fulfilled_amount']} {pd['currency']})")
            print(f"    Broken: {pd['broken_count']}")
            print(f"    Pending: {pd['pending_count']}")
            print(f"    Due today: {pd['due_today']}")
            print(f"    Due this week: {pd['due_this_week']}")
            print(f"    Fulfillment rate: {pd['fulfillment_rate']}%")

        # 23. Create PTP for invalid customer (expect 400)
        bad_ptp = await c.post(f"{BASE}/collections-copilot/ptp", headers=h, json={
            "customer_id": "00000000-0000-0000-0000-000000000000",
            "promised_date": future_date,
            "promised_amount": 10000.00,
        })
        print(f"\n23. PTP for invalid customer: {bad_ptp.status_code} (expected 400)")

        # ── Dispute Aging Report ──
        print("\n--- Dispute Aging Report ---")

        # 24. Get dispute aging report
        aging = await c.get(f"{BASE}/collections-copilot/disputes/aging", headers=h)
        print(f"\n24. Dispute aging report: {aging.status_code}")
        if aging.status_code == 200:
            ar = aging.json()
            print(f"    Total open disputes: {ar['total_open']}")
            print(f"    Total amount: {ar['total_amount']}")
            print(f"    Avg resolution days: {ar['avg_resolution_days']}")
            print(f"    Resolution rate: {ar['resolution_rate']}%")
            print(f"    SLA breaches: {ar['sla_breach_count']}")
            print(f"    By reason: {ar['by_reason']}")
            print(f"    By department: {ar['by_department']}")
            print(f"    Aging buckets:")
            for bucket in ar["buckets"]:
                if bucket["count"] > 0:
                    print(f"      {bucket['bucket']}: {bucket['count']} disputes, {bucket['total_amount']} amount, avg {bucket['avg_days_open']} days")

        # ── Cleanup & Final Verification ──
        print("\n--- Cleanup ---")

        # 25. Delete escalation templates
        if tpl2_id:
            del2 = await c.delete(f"{BASE}/collections-copilot/templates/{tpl2_id}", headers=h)
            print(f"\n25. Delete PTP-broken template: {del2.status_code}")
        if tpl_id:
            del1 = await c.delete(f"{BASE}/collections-copilot/templates/{tpl_id}", headers=h)
            print(f"    Delete overdue template: {del1.status_code}")

        # 26. Verify templates deleted
        final_tpl = await c.get(f"{BASE}/collections-copilot/templates", headers=h)
        print(f"\n26. Final template count: {final_tpl.json()['total']} (expected 0)")

        # 27. Send to non-existent draft (expect 404)
        bad_send = await c.post(f"{BASE}/collections-copilot/draft/00000000-0000-0000-0000-000000000000/send", headers=h, json={
            "draft_id": "00000000-0000-0000-0000-000000000000",
            "send_now": True,
        })
        print(f"\n27. Send invalid draft: {bad_send.status_code} (expected 404)")

        # 28. Update non-existent PTP (expect 404)
        bad_ptp_upd = await c.patch(f"{BASE}/collections-copilot/ptp/00000000-0000-0000-0000-000000000000", headers=h, json={
            "status": "fulfilled",
        })
        print(f"\n28. Update invalid PTP: {bad_ptp_upd.status_code} (expected 404)")

        print("\n" + "=" * 60)
        print("ALL DAY 13 TESTS COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
