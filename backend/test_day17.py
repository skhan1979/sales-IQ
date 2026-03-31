"""Day 17 End-to-End Tests: Executive Dashboard, KPI Engine, Role-Based Home Screen, Widgets"""
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

        # Pre-calculate health scores
        print("\n--- Pre-calculating health scores ---")
        batch_hs = await c.post(f"{BASE}/intelligence/health-score/batch", headers=h, json={})
        if batch_hs.status_code == 200:
            print(f"    Scored {batch_hs.json()['customers_processed']} customers")

        # ==============================
        # DAY 17: EXECUTIVE DASHBOARD
        # ==============================
        print("\n" + "=" * 60)
        print("DAY 17: EXECUTIVE DASHBOARD, KPI ENGINE & HOME SCREEN")
        print("=" * 60)

        # ── 1. KPI Cards ──
        print("\n--- KPI Cards ---")
        kpis = await c.get(f"{BASE}/executive/kpis", headers=h)
        print(f"\n1. KPI cards: {kpis.status_code}")
        if kpis.status_code == 200:
            kd = kpis.json()
            print(f"   Cards: {len(kd['cards'])}")
            for card in kd["cards"]:
                trend_7d = len(card.get("trend_7d", []))
                trend_30d = len(card.get("trend_30d", []))
                print(f"     [{card['status']}] {card['label']}: {card['formatted_value']} "
                      f"(change: {card['change_pct']}% {card['change_direction']}) "
                      f"sparklines: 7d={trend_7d}pts, 30d={trend_30d}pts")

        # ── 2. AI Executive Summary ──
        print("\n--- AI Executive Summary ---")
        summary = await c.get(f"{BASE}/executive/summary", headers=h)
        print(f"\n2. Executive summary: {summary.status_code}")
        if summary.status_code == 200:
            sd = summary.json()
            print(f"   Summary: {sd['summary'][:200]}...")
            print(f"   Highlights: {len(sd['highlights'])}")
            for hl in sd["highlights"]:
                print(f"     - {hl}")
            if sd["alerts"]:
                print(f"   Alerts: {len(sd['alerts'])}")
                for al in sd["alerts"]:
                    print(f"     ! {al}")

        # ── 3. Full Executive Dashboard ──
        print("\n--- Full Executive Dashboard ---")
        dash = await c.get(f"{BASE}/executive/dashboard", headers=h)
        print(f"\n3. Executive dashboard: {dash.status_code}")
        if dash.status_code == 200:
            dd = dash.json()
            print(f"   KPIs: {len(dd['kpis'])} cards")
            print(f"   Top overdue: {len(dd['top_overdue_customers'])} customers")
            if dd["top_overdue_customers"]:
                top = dd["top_overdue_customers"][0]
                print(f"     #1: {top['customer_name']} - {top['amount_remaining']:,.0f} {top['currency']} ({top['days_overdue']}d)")
            print(f"   Pipeline stages: {len(dd['pipeline_snapshot']['stages'])}")
            print(f"   Pipeline value: {dd['pipeline_snapshot']['total_pipeline_value']:,.0f}")
            print(f"   Cash flow buckets: {len(dd['cash_flow_forecast']['buckets'])}")
            print(f"   Health distribution: {dd['health_distribution']}")

        # ── 4. Role-Based Home Screen (CFO/admin user) ──
        print("\n--- Role-Based Home Screen ---")
        home = await c.get(f"{BASE}/executive/home", headers=h)
        print(f"\n4. Home screen: {home.status_code}")
        if home.status_code == 200:
            hd = home.json()
            print(f"   Role: {hd['role']} ({hd['role_label']})")
            print(f"   Greeting: {hd['greeting']}")
            print(f"   Widgets: {len(hd['widgets'])}")
            for w in hd["widgets"]:
                vis = "visible" if w["is_visible"] else "hidden"
                pin = " [PINNED]" if w["is_pinned"] else ""
                data_str = f" data={json.dumps(w['data'])[:60]}" if w.get("data") else ""
                print(f"     {w['position']}. [{w['widget_type']}] {w['title']} ({w['size']}, {vis}){pin}{data_str}")
            print(f"   Quick stats: {hd['quick_stats']}")

        # ── 5. Available Widgets ──
        print("\n--- Available Widgets ---")
        avail = await c.get(f"{BASE}/executive/widgets/available", headers=h)
        print(f"\n5. Available widgets: {avail.status_code}")
        if avail.status_code == 200:
            ad = avail.json()
            print(f"   Total available: {ad['total']}")
            for w in ad["widgets"]:
                print(f"     - {w['widget_id']}: {w['title']} ({w['widget_type']}, {w['default_size']})")

        # ── 6. Widget Configuration ──
        print("\n--- Widget Configuration ---")
        config = await c.get(f"{BASE}/executive/widgets/config", headers=h)
        print(f"\n6. Widget config: {config.status_code}")
        if config.status_code == 200:
            cd = config.json()
            print(f"   Role: {cd['role']}")
            print(f"   Layout items: {len(cd['layout'])}")

        # ── 7. Update Widget Layout (reorder + pin) ──
        print("\n--- Update Widget Layout ---")
        new_layout = await c.put(f"{BASE}/executive/widgets/config", headers=h, json={
            "widget_ids": ["todays_briefing", "kpi_cards", "top_overdue", "cash_flow_forecast"],
            "hidden_widget_ids": ["cash_flow_forecast"],
            "pinned_widget_ids": ["todays_briefing"],
        })
        print(f"\n7. Update layout: {new_layout.status_code}")
        if new_layout.status_code == 200:
            nl = new_layout.json()
            print(f"   New layout items: {len(nl['layout'])}")
            for w in nl["layout"]:
                vis = "visible" if w["is_visible"] else "HIDDEN"
                pin = " [PINNED]" if w["is_pinned"] else ""
                print(f"     {w['position']}. {w['title']} ({vis}){pin}")

        # Verify home screen reflects new layout
        home2 = await c.get(f"{BASE}/executive/home", headers=h)
        if home2.status_code == 200:
            hd2 = home2.json()
            print(f"   Home screen now shows: {len(hd2['widgets'])} widgets")
            first = hd2["widgets"][0] if hd2["widgets"] else {}
            print(f"   First widget: {first.get('title', '?')} (pinned={first.get('is_pinned', False)})")

        # ── 8. Cache Management ──
        print("\n--- Cache Management ---")
        cache = await c.get(f"{BASE}/executive/cache/status", headers=h)
        print(f"\n8. Cache status: {cache.status_code}")
        if cache.status_code == 200:
            cs = cache.json()
            print(f"   Cached keys: {cs['cached_keys']}")
            print(f"   TTL: {cs['ttl_seconds']}s")

        # Invalidate and verify
        inv_cache = await c.post(f"{BASE}/executive/cache/invalidate", headers=h)
        print(f"   Invalidate: {inv_cache.status_code}")
        if inv_cache.status_code == 200:
            print(f"   Cleared: {inv_cache.json()['cleared']} entries")

        cache2 = await c.get(f"{BASE}/executive/cache/status", headers=h)
        if cache2.status_code == 200:
            print(f"   Post-invalidate cached keys: {cache2.json()['cached_keys']}")

        # ── 9. Cross-Feature: Intelligence still works ──
        print("\n--- Cross-Feature Verification ---")
        c360 = await c.get(f"{BASE}/intelligence/customer-360/{(await c.get(f'{BASE}/customers/?page_size=1', headers=h)).json()['items'][0]['id']}?sections=health_score", headers=h)
        print(f"\n9. Customer 360: {c360.status_code}")
        if c360.status_code == 200:
            print(f"   Customer: {c360.json()['customer_name']}")

        # ── 10. Cross-Feature: Sales dashboard still works ──
        sales = await c.get(f"{BASE}/sales/summary", headers=h)
        print(f"\n10. Sales dashboard: {sales.status_code}")
        if sales.status_code == 200:
            print(f"    Pipeline value: {sales.json()['pipeline']['total_pipeline_value']:,.0f}")

        # ── 11. Cross-Feature: CFO dashboard still works ──
        dso = await c.get(f"{BASE}/cfo/dso-trend", headers=h)
        print(f"\n11. CFO DSO trend: {dso.status_code}")
        if dso.status_code == 200:
            print(f"    Current DSO: {dso.json()['current_dso']}")

        # ── 12. Chat about executive metrics ──
        chat = await c.post(f"{BASE}/intelligence/chat", headers=h, json={
            "message": "Show me the overall health of our accounts receivable",
        })
        print(f"\n12. Chat (AR health): {chat.status_code}")
        if chat.status_code == 200:
            print(f"    Response: {chat.json()['message']['content'][:120]}...")

        print("\n" + "=" * 60)
        print("ALL DAY 17 TESTS COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
