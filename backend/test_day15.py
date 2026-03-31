"""Day 15 End-to-End Tests: AR Dashboard, Write-Off Management, IFRS 9 ECL Provisioning"""
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

        # Get test customer and invoice
        custs = await c.get(f"{BASE}/customers/?page_size=5", headers=h)
        cust_id = None
        if custs.status_code == 200 and custs.json()["items"]:
            cust_id = custs.json()["items"][0]["id"]
            cust_name = custs.json()["items"][0]["name"]
            print(f"\n    Test customer: {cust_name} ({cust_id[:8]}...)")

        # Get an invoice
        invs = await c.get(f"{BASE}/invoices/?page_size=5", headers=h)
        inv_id = None
        inv_num = None
        if invs.status_code == 200 and invs.json()["items"]:
            inv_id = invs.json()["items"][0]["id"]
            inv_num = invs.json()["items"][0].get("invoice_number")
            print(f"    Test invoice: {inv_num} ({inv_id[:8]}...)")

        if not cust_id:
            print("\nERROR: No customers found.")
            return

        # ==============================
        # DAY 15: CFO DASHBOARD
        # ==============================
        print("\n" + "=" * 60)
        print("DAY 15: CFO DASHBOARD")
        print("=" * 60)

        # ── Enhanced AR Dashboard ──
        print("\n--- Enhanced AR Dashboard ---")

        # 1. DSO Trend
        dso = await c.get(f"{BASE}/cfo/dso-trend?months=6", headers=h)
        print(f"\n1. DSO Trend (6 months): {dso.status_code}")
        if dso.status_code == 200:
            dd = dso.json()
            print(f"   Current DSO: {dd['current_dso']}")
            print(f"   Average DSO: {dd['avg_dso']}")
            print(f"   Best: {dd['best_dso']} | Worst: {dd['worst_dso']}")
            print(f"   Trend: {dd['trend_direction']}")
            for p in dd["trend"][:3]:
                print(f"     {p['month']}: DSO={p['dso']} recv={p['total_receivables']:,.0f}")

        # 2. Overdue Trend
        overdue = await c.get(f"{BASE}/cfo/overdue-trend?months=6", headers=h)
        print(f"\n2. Overdue Trend (6 months): {overdue.status_code}")
        if overdue.status_code == 200:
            od = overdue.json()
            print(f"   Current overdue: {od['current_overdue']:,.0f} {od['currency']}")
            print(f"   Current count: {od['current_overdue_count']}")
            for p in od["trend"][-3:]:
                print(f"     {p['month']}: {p['overdue_amount']:,.0f} ({p['overdue_count']} invoices, {p['overdue_pct']}%)")

        # 3. Cash Flow Forecast
        cashflow = await c.get(f"{BASE}/cfo/cash-flow-forecast", headers=h)
        print(f"\n3. Cash Flow Forecast: {cashflow.status_code}")
        if cashflow.status_code == 200:
            cf = cashflow.json()
            print(f"   Total predicted: {cf['total_predicted']:,.0f} {cf['currency']}")
            print(f"   High confidence: {cf['total_high_confidence']:,.0f}")
            print(f"   Medium confidence: {cf['total_medium_confidence']:,.0f}")
            print(f"   Low confidence: {cf['total_low_confidence']:,.0f}")
            for b in cf["buckets"]:
                print(f"     {b['label']}: {b['predicted_inflow']:,.0f} ({b['invoice_count']} invoices)")

        # 4. Top Overdue Customers
        top_od = await c.get(f"{BASE}/cfo/top-overdue-customers?limit=5", headers=h)
        print(f"\n4. Top Overdue Customers: {top_od.status_code}")
        if top_od.status_code == 200:
            tc = top_od.json()
            print(f"   Total overdue: {tc['total_overdue_amount']:,.0f} {tc['currency']}")
            for t in tc["items"][:5]:
                print(f"     - {t['customer_name']}: {t['total_overdue']:,.0f} ({t['invoice_count']} inv, max {t['max_days_overdue']}d)")

        # ── Write-Off Management ──
        print("\n--- Write-Off Management ---")

        # 5. Create write-off (full)
        wo1 = await c.post(f"{BASE}/cfo/write-offs", headers=h, json={
            "customer_id": cust_id,
            "invoice_id": inv_id,
            "write_off_type": "full",
            "amount": 15000.00,
            "currency": "AED",
            "reason": "Customer declared bankruptcy - unrecoverable debt",
        })
        print(f"\n5. Create write-off (full): {wo1.status_code}")
        wo_id = None
        if wo1.status_code == 201:
            w1 = wo1.json()
            wo_id = w1["id"]
            print(f"   Write-off ID: {wo_id[:8]}...")
            print(f"   Customer: {w1['customer_name']}")
            print(f"   Amount: {w1['amount']} {w1['currency']}")
            print(f"   ECL Stage: {w1['ecl_stage']}")
            print(f"   ECL Probability: {w1['ecl_probability']}")
            print(f"   Provision amount: {w1['provision_amount']}")
            print(f"   Status: {w1['approval_status']}")

        # 6. Create write-off (partial)
        wo2 = await c.post(f"{BASE}/cfo/write-offs", headers=h, json={
            "customer_id": cust_id,
            "write_off_type": "partial",
            "amount": 8000.00,
            "reason": "Negotiated settlement - partial recovery",
        })
        print(f"\n6. Create write-off (partial): {wo2.status_code}")
        wo2_id = wo2.json()["id"] if wo2.status_code == 201 else None

        # 7. Create provision
        wo3 = await c.post(f"{BASE}/cfo/write-offs", headers=h, json={
            "customer_id": cust_id,
            "write_off_type": "provision",
            "amount": 25000.00,
            "reason": "ECL Stage 2 provision increase",
        })
        print(f"\n7. Create provision: {wo3.status_code}")
        wo3_id = wo3.json()["id"] if wo3.status_code == 201 else None

        # 8. Approve write-off
        if wo_id:
            approve = await c.post(f"{BASE}/cfo/write-offs/{wo_id}/decide", headers=h, json={
                "action": "approve",
                "approval_notes": "Approved - verified bankruptcy filing",
            })
            print(f"\n8. Approve write-off: {approve.status_code}")
            if approve.status_code == 200:
                ad = approve.json()
                print(f"   Status: {ad['approval_status']}")
                print(f"   Approved at: {ad.get('approved_at', 'N/A')}")

        # 9. Reject write-off
        if wo2_id:
            reject = await c.post(f"{BASE}/cfo/write-offs/{wo2_id}/decide", headers=h, json={
                "action": "reject",
                "approval_notes": "Need more evidence of settlement",
            })
            print(f"\n9. Reject write-off: {reject.status_code}")
            if reject.status_code == 200:
                print(f"   Status: {reject.json()['approval_status']}")

        # 10. Approve provision
        if wo3_id:
            approve3 = await c.post(f"{BASE}/cfo/write-offs/{wo3_id}/decide", headers=h, json={
                "action": "approve",
            })
            print(f"\n10. Approve provision: {approve3.status_code}")

        # 11. Reverse write-off
        if wo_id:
            reverse = await c.post(f"{BASE}/cfo/write-offs/{wo_id}/reverse", headers=h, json={
                "reason": "Recovery received - reversing write-off",
            })
            print(f"\n11. Reverse write-off: {reverse.status_code}")
            if reverse.status_code == 200:
                rv = reverse.json()
                print(f"   Reversed: {rv['is_reversed']}")
                print(f"   Reason: {rv.get('reversal_reason')}")

        # 12. List write-offs
        wo_list = await c.get(f"{BASE}/cfo/write-offs", headers=h)
        print(f"\n12. List write-offs: {wo_list.status_code}")
        if wo_list.status_code == 200:
            wl = wo_list.json()
            print(f"   Total: {wl['total']}")
            print(f"   Summary: approved={wl['summary']['total_approved']:,.0f} pending={wl['summary']['total_pending']:,.0f} reversed={wl['summary']['total_reversed']:,.0f}")
            print(f"   By type: {wl['summary']['by_type']}")
            for w in wl["items"][:3]:
                print(f"   - {w['write_off_type']}: {w['amount']} {w['currency']} [{w['approval_status']}] reversed={w['is_reversed']}")

        # 13. Filter write-offs by status
        wo_pending = await c.get(f"{BASE}/cfo/write-offs?status=pending", headers=h)
        print(f"\n13. Write-offs (pending): {wo_pending.status_code}")
        if wo_pending.status_code == 200:
            print(f"   Count: {wo_pending.json()['total']}")

        # 14. Write-off for invalid customer
        bad_wo = await c.post(f"{BASE}/cfo/write-offs", headers=h, json={
            "customer_id": "00000000-0000-0000-0000-000000000000",
            "write_off_type": "full",
            "amount": 1000,
        })
        print(f"\n14. Write-off invalid customer: {bad_wo.status_code} (expected 400)")

        # 15. Double-approve (should fail)
        if wo_id:
            double = await c.post(f"{BASE}/cfo/write-offs/{wo_id}/decide", headers=h, json={
                "action": "approve",
            })
            print(f"\n15. Double-approve: {double.status_code} (expected 400)")

        # ── IFRS 9 ECL Provisioning ──
        print("\n--- IFRS 9 ECL Provisioning ---")

        # 16. Run ECL provisioning
        ecl = await c.post(f"{BASE}/cfo/ecl/run", headers=h)
        print(f"\n16. Run ECL provisioning: {ecl.status_code}")
        if ecl.status_code == 200:
            ed = ecl.json()
            print(f"   Customers analyzed: {ed['customers_analyzed']}")
            print(f"   Total exposure: {ed['total_exposure']:,.0f} {ed['currency']}")
            print(f"   ML provision: {ed['total_ml_provision']:,.0f}")
            print(f"   Traditional provision: {ed['total_traditional_provision']:,.0f}")
            print(f"   Provision gap: {ed['provision_gap']:,.0f}")
            print(f"   Under-provisioned: {ed['under_provisioned_count']} | Over: {ed['over_provisioned_count']} | Adequate: {ed['adequate_count']}")
            print(f"   By stage: {list(ed['by_stage'].keys())}")
            for stage, data in ed["by_stage"].items():
                print(f"     {stage}: {data['count']} customers, exposure={data['exposure']:,.0f}, ML={data['ml_provision']:,.0f} vs Trad={data['trad_provision']:,.0f}")
            print(f"   Model: {ed['model_version']}")
            print(f"   Duration: {ed['duration_ms']}ms")

            if ed['recommendations']:
                print(f"   Top recommendations ({len(ed['recommendations'])}):")
                for rec in ed['recommendations'][:3]:
                    print(f"     - {rec['customer']}: gap={rec['gap']:,.0f} ({rec['reason'][:80]})")

        # 17. Provisioning Dashboard
        prov_dash = await c.get(f"{BASE}/cfo/ecl/dashboard", headers=h)
        print(f"\n17. Provisioning Dashboard: {prov_dash.status_code}")
        if prov_dash.status_code == 200:
            pd = prov_dash.json()
            print(f"   Required: {pd['total_provision_required']:,.0f} {pd['currency']}")
            print(f"   Current: {pd['total_current_provision']:,.0f}")
            print(f"   Adequacy ratio: {pd['provision_adequacy_ratio']}%")
            print(f"   Movement: new={pd['movement_analysis']['new_provisions']:,.0f} releases={pd['movement_analysis']['releases']:,.0f} write-offs={pd['movement_analysis']['write_offs']:,.0f}")
            print(f"   AI vs Traditional: AI={pd['ai_vs_traditional']['ai_total']:,.0f} Trad={pd['ai_vs_traditional']['traditional_total']:,.0f} diff={pd['ai_vs_traditional']['difference']:,.0f} ({pd['ai_vs_traditional']['pct_difference']}%)")
            print(f"   By stage: {list(pd['by_stage'].keys())}")
            print(f"   By segment: {list(pd['by_segment'].keys())}")
            if pd['top_under_provisioned']:
                print(f"   Top under-provisioned: {len(pd['top_under_provisioned'])} accounts")

        # ── Cross-feature verification ──
        print("\n--- Cross-Feature Verification ---")

        # 18. Existing AR summary still works
        ar = await c.get(f"{BASE}/dashboard/ar-summary", headers=h)
        print(f"\n18. AR Summary (existing): {ar.status_code}")
        if ar.status_code == 200:
            ard = ar.json()
            print(f"   Total receivables: {float(ard['total_receivables']):,.0f} {ard['currency']}")
            print(f"   DSO: {ard['average_dso']}")

        # 19. Collection effectiveness still works
        ce = await c.get(f"{BASE}/dashboard/collection-effectiveness?months=3", headers=h)
        print(f"\n19. Collection effectiveness: {ce.status_code}")
        if ce.status_code == 200:
            print(f"   Months: {len(ce.json())}")

        # 20. Top overdue (existing) still works
        top = await c.get(f"{BASE}/dashboard/top-overdue?limit=3", headers=h)
        print(f"\n20. Top overdue (existing): {top.status_code}")
        if top.status_code == 200:
            print(f"   Invoices returned: {len(top.json())}")

        print("\n" + "=" * 60)
        print("ALL DAY 15 TESTS COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
