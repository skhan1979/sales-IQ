"""Day 10-12 End-to-End Tests: Notifications, Analytics, Webhooks"""
import asyncio, httpx, json, sys, io

# Fix Windows console encoding for unicode arrows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:8000/api/v1"


async def main():
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{BASE}/auth/login", json={"email": "admin@salesiq.ai", "password": "Admin@2024", "tenant_slug": "demo"})
        tok = r.json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        print("=== Login OK ===")

        # Generate demo data first (for analytics to have data)
        print("\n--- Generating demo data ---")
        demo = await c.post(f"{BASE}/demo-data/generate", json={"dataset_size": "medium", "erp_profile": "d365_fo"}, headers=h)
        if demo.status_code in (200, 201):
            dd = demo.json()
            print(f"    Demo data: {dd.get('customers_created', '?')} customers, {dd.get('invoices_created', '?')} invoices, {dd.get('payments_created', '?')} payments")
        else:
            print(f"    Demo data: {demo.status_code} (may already exist)")

        # ==============================
        # DAY 10: NOTIFICATIONS & ALERTS
        # ==============================
        print("\n" + "=" * 60)
        print("DAY 10: NOTIFICATIONS & ALERTS")
        print("=" * 60)

        # 1. List alert rules (should auto-seed defaults)
        rules = await c.get(f"{BASE}/notifications/rules", headers=h)
        print(f"\n1. List alert rules: {rules.status_code}")
        if rules.status_code == 200:
            rd = rules.json()
            print(f"   Total rules: {rd['total']}")
            for r in rd["items"][:3]:
                print(f"   - {r['name']} [{r['severity']}] category={r['category']} active={r['is_active']}")

        # 2. Create custom alert rule
        custom_rule = await c.post(f"{BASE}/notifications/rules", headers=h, json={
            "name": "Large Invoice Alert",
            "description": "Fires for invoices over 500,000",
            "category": "custom",
            "severity": "warning",
            "condition": {"entity": "invoices", "field": "amount", "operator": ">", "value": 500000},
            "channels": ["in_app", "email"],
            "cooldown_minutes": 120,
        })
        print(f"\n2. Create custom rule: {custom_rule.status_code}")
        rule_id = None
        if custom_rule.status_code == 201:
            crd = custom_rule.json()
            rule_id = crd["id"]
            print(f"   Created: {crd['name']} (id={rule_id[:8]}...)")

        # 3. Update alert rule
        if rule_id:
            updated = await c.patch(f"{BASE}/notifications/rules/{rule_id}", headers=h, json={
                "severity": "critical",
                "cooldown_minutes": 60,
            })
            print(f"\n3. Update rule: {updated.status_code}")
            if updated.status_code == 200:
                print(f"   Severity changed to: {updated.json()['severity']}")

        # 4. Run alert scan
        scan = await c.post(f"{BASE}/notifications/scan", headers=h)
        print(f"\n4. Alert scan: {scan.status_code}")
        if scan.status_code == 200:
            sd = scan.json()
            print(f"   Alerts generated: {sd['alerts_generated']}")
            print(f"   By category: {sd['by_category']}")
            print(f"   By severity: {sd['by_severity']}")
            print(f"   Scan duration: {sd['scan_duration_ms']}ms")

        # 5. Get notification inbox
        inbox = await c.get(f"{BASE}/notifications/inbox", headers=h)
        print(f"\n5. Notification inbox: {inbox.status_code}")
        if inbox.status_code == 200:
            ib = inbox.json()
            print(f"   Total: {ib['total']} | Unread: {ib['unread_count']}")
            for n in ib["items"][:3]:
                print(f"   - [{n['severity']}] {n['title'][:60]}")

        # 6. Filter by category
        filtered = await c.get(f"{BASE}/notifications/inbox?category=overdue_threshold", headers=h)
        print(f"\n6. Filtered inbox (overdue): {filtered.status_code}")
        if filtered.status_code == 200:
            fd = filtered.json()
            print(f"   Matching: {fd['total']}")

        # 7. Mark notifications read
        if inbox.status_code == 200 and ib["items"]:
            mark_ids = [ib["items"][0]["id"]]
            marked = await c.post(f"{BASE}/notifications/inbox/mark-read", headers=h, json={
                "notification_ids": mark_ids,
            })
            print(f"\n7. Mark read: {marked.status_code}")
            if marked.status_code == 200:
                print(f"   Marked: {marked.json()['marked_read']}")

        # 8. Mark all read
        mark_all = await c.post(f"{BASE}/notifications/inbox/mark-all-read", headers=h)
        print(f"\n8. Mark all read: {mark_all.status_code}")
        if mark_all.status_code == 200:
            print(f"   Marked: {mark_all.json()['marked_read']}")

        # 9. Delete custom rule
        if rule_id:
            deleted = await c.delete(f"{BASE}/notifications/rules/{rule_id}", headers=h)
            print(f"\n9. Delete rule: {deleted.status_code}")

        # ==============================
        # DAY 11: ANALYTICS & REPORTING
        # ==============================
        print("\n" + "=" * 60)
        print("DAY 11: ANALYTICS & REPORTING")
        print("=" * 60)

        # 10. KPI Dashboard
        kpis = await c.get(f"{BASE}/analytics/kpis", headers=h)
        print(f"\n10. KPI Dashboard: {kpis.status_code}")
        if kpis.status_code == 200:
            kd = kpis.json()
            print(f"    Period: {kd['period']['date_from']} → {kd['period']['date_to']}")
            for kpi in kd["kpis"][:6]:
                arrow = "↑" if kpi["trend"] == "up" else ("↓" if kpi["trend"] == "down" else "→")
                target_str = f" (target: {kpi['target']})" if kpi["target"] else ""
                print(f"    - {kpi['name']}: {kpi['value']} {kpi['unit']} {arrow} {kpi['change_pct']:+.1f}%{target_str}")

        # 11. KPI Dashboard with custom dates
        kpis2 = await c.get(f"{BASE}/analytics/kpis?date_from=2025-01-01&date_to=2025-12-31", headers=h)
        print(f"\n11. KPI Dashboard (2025): {kpis2.status_code}")

        # 12. Trend Analysis
        trends = await c.get(f"{BASE}/analytics/trends?metrics=total_ar,dso,payment_total&granularity=weekly", headers=h)
        print(f"\n12. Trend Analysis: {trends.status_code}")
        if trends.status_code == 200:
            td = trends.json()
            for series in td["series"]:
                vals = [dp["value"] for dp in series["data"]]
                print(f"    - {series['display_name']}: {len(series['data'])} points")
                if series.get("summary"):
                    print(f"      Min={series['summary']['min']} Max={series['summary']['max']} Avg={series['summary']['avg']}")

        # 13. Period Comparison
        comp = await c.get(f"{BASE}/analytics/comparison", headers=h)
        print(f"\n13. Period Comparison: {comp.status_code}")
        if comp.status_code == 200:
            cd = comp.json()
            print(f"    Current: {cd['current_period']['date_from']} → {cd['current_period']['date_to']}")
            print(f"    Previous: {cd['previous_period']['date_from']} → {cd['previous_period']['date_to']}")
            for c_item in cd["comparisons"][:5]:
                arrow = "↑" if c_item["trend"] == "up" else ("↓" if c_item["trend"] == "down" else "→")
                print(f"    - {c_item['display_name']}: {c_item['current_value']} vs {c_item['previous_value']} ({c_item['change_pct']:+.1f}% {arrow})")

        # 14. Customer Analytics
        cust_analytics = await c.get(f"{BASE}/analytics/customers?sort_by=overdue_amount&limit=5", headers=h)
        print(f"\n14. Customer Analytics: {cust_analytics.status_code}")
        if cust_analytics.status_code == 200:
            ca = cust_analytics.json()
            print(f"    Total customers: {ca['total']}")
            for item in ca["items"][:5]:
                print(f"    - {item['customer_name']}: AR={item['total_ar']} overdue={item['overdue_amount']} DSO≈{item['avg_days_to_pay']}d risk={item['risk_score']}")

        # 15. AR Aging Report
        aging = await c.post(f"{BASE}/analytics/reports", headers=h, json={
            "report_type": "ar_aging",
        })
        print(f"\n15. AR Aging Report: {aging.status_code}")
        if aging.status_code == 200:
            ar = aging.json()
            print(f"    Title: {ar['title']}")
            print(f"    Rows: {ar['row_count']}")
            if ar.get("summary"):
                print(f"    Total AR: {ar['summary'].get('total_ar')}")
                print(f"    Buckets: {ar['summary'].get('buckets')}")

        # 16. Collection Performance Report
        coll_report = await c.post(f"{BASE}/analytics/reports", headers=h, json={
            "report_type": "collection_performance",
            "date_from": "2025-01-01",
            "date_to": "2026-12-31",
        })
        print(f"\n16. Collection Performance Report: {coll_report.status_code}")
        if coll_report.status_code == 200:
            cr = coll_report.json()
            print(f"    Title: {cr['title']}")
            if cr.get("summary"):
                print(f"    Total collected: {cr['summary'].get('total_collected')}")
                print(f"    PTP effectiveness: {cr['summary'].get('ptp_effectiveness')}%")

        # 17. Customer Risk Report
        risk_report = await c.post(f"{BASE}/analytics/reports", headers=h, json={
            "report_type": "customer_risk",
        })
        print(f"\n17. Customer Risk Report: {risk_report.status_code}")
        if risk_report.status_code == 200:
            rr = risk_report.json()
            print(f"    Title: {rr['title']}")
            if rr.get("summary"):
                print(f"    Risk distribution: {rr['summary'].get('risk_distribution')}")
                print(f"    Avg risk score: {rr['summary'].get('avg_risk_score')}")

        # 18. Executive Summary Report
        exec_report = await c.post(f"{BASE}/analytics/reports", headers=h, json={
            "report_type": "executive_summary",
        })
        print(f"\n18. Executive Summary: {exec_report.status_code}")
        if exec_report.status_code == 200:
            er = exec_report.json()
            if er.get("summary"):
                print(f"    Health Score: {er['summary'].get('health_score')}")
                print(f"    Concerns: {er['summary'].get('top_concerns')}")

        # 19. Invalid report type
        bad_report = await c.post(f"{BASE}/analytics/reports", headers=h, json={
            "report_type": "nonexistent",
        })
        print(f"\n19. Invalid report type: {bad_report.status_code} (expected 400)")

        # ==============================
        # DAY 12: WEBHOOKS & INTEGRATIONS
        # ==============================
        print("\n" + "=" * 60)
        print("DAY 12: WEBHOOKS & INTEGRATIONS")
        print("=" * 60)

        # 20. List event types
        evt_types = await c.get(f"{BASE}/integrations/event-types", headers=h)
        print(f"\n20. Event types: {evt_types.status_code}")
        if evt_types.status_code == 200:
            et = evt_types.json()
            categories = set(e["category"] for e in et["event_types"])
            print(f"    Total event types: {len(et['event_types'])}")
            print(f"    Categories: {', '.join(sorted(categories))}")

        # 21. Create webhook
        wh_create = await c.post(f"{BASE}/integrations/webhooks", headers=h, json={
            "name": "ERP Sync Hook",
            "url": "https://erp.example.com/webhook/salesiq",
            "events": ["invoice.created", "payment.received", "customer.credit_hold"],
            "secret": "my-webhook-secret-123",
            "headers": {"X-Source": "SalesIQ"},
            "retry_count": 5,
            "timeout_seconds": 30,
            "description": "Push updates to ERP system",
        })
        print(f"\n21. Create webhook: {wh_create.status_code}")
        wh_id = None
        if wh_create.status_code == 201:
            whd = wh_create.json()
            wh_id = whd["id"]
            print(f"    Created: {whd['name']} → {whd['url']}")
            print(f"    Events: {whd['events']}")
            print(f"    Status: {whd['status']}")

        # 22. Create second webhook
        wh2_create = await c.post(f"{BASE}/integrations/webhooks", headers=h, json={
            "name": "Slack Notifications",
            "url": "https://hooks.slack.com/services/T00/B00/xxxx",
            "events": ["alert.triggered", "dispute.escalated", "collection.ptp_broken"],
            "retry_count": 3,
        })
        print(f"\n22. Create second webhook: {wh2_create.status_code}")
        wh2_id = wh2_create.json()["id"] if wh2_create.status_code == 201 else None

        # 23. List webhooks
        wh_list = await c.get(f"{BASE}/integrations/webhooks", headers=h)
        print(f"\n23. List webhooks: {wh_list.status_code}")
        if wh_list.status_code == 200:
            wl = wh_list.json()
            print(f"    Total: {wl['total']}")
            for w in wl["items"]:
                print(f"    - {w['name']}: {w['status']} | events={len(w['events'])} | deliveries={w['total_deliveries']}")

        # 24. Update webhook
        if wh_id:
            wh_update = await c.patch(f"{BASE}/integrations/webhooks/{wh_id}", headers=h, json={
                "name": "ERP Sync Hook (Updated)",
                "events": ["invoice.created", "payment.received", "customer.credit_hold", "invoice.overdue"],
            })
            print(f"\n24. Update webhook: {wh_update.status_code}")
            if wh_update.status_code == 200:
                print(f"    Name: {wh_update.json()['name']}")
                print(f"    Events: {wh_update.json()['events']}")

        # 25. Test webhook
        if wh_id:
            wh_test = await c.post(f"{BASE}/integrations/webhooks/{wh_id}/test", headers=h)
            print(f"\n25. Test webhook: {wh_test.status_code}")
            if wh_test.status_code == 200:
                wt = wh_test.json()
                print(f"    Success: {wt['success']} | Response: {wt['response_code']} | Duration: {wt['duration_ms']}ms")

        # 26. Publish event (matching webhook)
        evt_pub = await c.post(f"{BASE}/integrations/events", headers=h, json={
            "event_type": "invoice.created",
            "entity_type": "invoices",
            "entity_id": "test-invoice-001",
            "payload": {"invoice_number": "INV-TEST-001", "amount": 50000, "currency": "AED"},
        })
        print(f"\n26. Publish event (invoice.created): {evt_pub.status_code}")
        if evt_pub.status_code == 201:
            ep = evt_pub.json()
            print(f"    Event ID: {ep['event_id'][:8]}...")
            print(f"    Webhooks matched: {ep['webhooks_matched']}")
            print(f"    Deliveries queued: {ep['deliveries_queued']}")

        # 27. Publish event (alert triggered - should match slack hook)
        evt_pub2 = await c.post(f"{BASE}/integrations/events", headers=h, json={
            "event_type": "alert.triggered",
            "entity_type": "alerts",
            "payload": {"alert_name": "SLA Breach", "severity": "critical"},
        })
        print(f"\n27. Publish event (alert.triggered): {evt_pub2.status_code}")
        if evt_pub2.status_code == 201:
            ep2 = evt_pub2.json()
            print(f"    Webhooks matched: {ep2['webhooks_matched']} (expected 1 = Slack)")

        # 28. Publish event (no matching hooks)
        evt_pub3 = await c.post(f"{BASE}/integrations/events", headers=h, json={
            "event_type": "system.briefing_generated",
            "payload": {"briefing_id": "test-123"},
        })
        print(f"\n28. Publish event (no match): {evt_pub3.status_code}")
        if evt_pub3.status_code == 201:
            ep3 = evt_pub3.json()
            print(f"    Webhooks matched: {ep3['webhooks_matched']} (expected 0)")

        # 29. List events
        evt_list = await c.get(f"{BASE}/integrations/events", headers=h)
        print(f"\n29. List events: {evt_list.status_code}")
        if evt_list.status_code == 200:
            el = evt_list.json()
            print(f"    Total: {el['total']}")
            for e in el["items"][:5]:
                print(f"    - {e['event_type']}: webhooks_triggered={e['webhooks_triggered']}")

        # 30. List delivery logs
        dl_list = await c.get(f"{BASE}/integrations/deliveries", headers=h)
        print(f"\n30. Delivery logs: {dl_list.status_code}")
        if dl_list.status_code == 200:
            dll = dl_list.json()
            print(f"    Total: {dll['total']}")
            for dl in dll["items"][:5]:
                print(f"    - {dl['event_type']}: {dl['status']} | code={dl['response_code']} | {dl['duration_ms']}ms | {dl['payload_size']}B")

        # 31. Filter delivery logs by webhook
        if wh_id:
            dl_filtered = await c.get(f"{BASE}/integrations/deliveries?webhook_id={wh_id}", headers=h)
            print(f"\n31. Delivery logs (filtered): {dl_filtered.status_code}")
            if dl_filtered.status_code == 200:
                print(f"    For ERP hook: {dl_filtered.json()['total']} deliveries")

        # 32. Verify webhook stats after deliveries
        if wh_id:
            wh_detail = await c.get(f"{BASE}/integrations/webhooks", headers=h)
            if wh_detail.status_code == 200:
                for w in wh_detail.json()["items"]:
                    if w["id"] == wh_id:
                        print(f"\n32. Webhook stats after deliveries:")
                        print(f"    Total: {w['total_deliveries']} | Success: {w['successful_deliveries']} | Failed: {w['failed_deliveries']}")
                        print(f"    Last delivery: {w['last_delivery_status']} at {w['last_delivery_at']}")

        # 33. Invalid event type
        bad_evt = await c.post(f"{BASE}/integrations/events", headers=h, json={
            "event_type": "invalid.event",
            "payload": {},
        })
        print(f"\n33. Invalid event type: {bad_evt.status_code} (expected 400)")

        # 34. Delete webhooks
        if wh2_id:
            del2 = await c.delete(f"{BASE}/integrations/webhooks/{wh2_id}", headers=h)
            print(f"\n34. Delete Slack webhook: {del2.status_code}")
        if wh_id:
            del1 = await c.delete(f"{BASE}/integrations/webhooks/{wh_id}", headers=h)
            print(f"    Delete ERP webhook: {del1.status_code}")

        # Final verification
        final_wh = await c.get(f"{BASE}/integrations/webhooks", headers=h)
        print(f"\n35. Final webhook count: {final_wh.json()['total']} (expected 0)")

        print("\n" + "=" * 60)
        print("ALL DAYS 10-12 TESTS COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
