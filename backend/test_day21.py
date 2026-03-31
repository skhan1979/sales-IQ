"""Day 21 End-to-End Tests: Milestone 1 Demo Preparation & Full Regression"""
import asyncio, httpx, sys, io, time

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:8000/api/v1"


async def main():
    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as c:
        r = await c.post(f"{BASE}/auth/login", json={"email": "admin@salesiq.ai", "password": "Admin@2024", "tenant_slug": "demo"})
        tok = r.json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        print("=== Login OK ===\n")

        print("=" * 60)
        print("DAY 21: MILESTONE 1 — DEMO PREPARATION & FULL REGRESSION")
        print("=" * 60)

        passed = 0
        failed = 0

        def check(num, name, status, expected, extra=""):
            nonlocal passed, failed
            ok = status == expected
            mark = "PASS" if ok else "FAIL"
            if ok:
                passed += 1
            else:
                failed += 1
            print(f"  {mark} {num}. {name}: {status} (expected {expected}) {extra}")
            return ok

        # ══════════════════════════════════════
        # SECTION A: Milestone 1 Endpoints
        # ══════════════════════════════════════
        print("\n--- A. Milestone 1 Endpoints ---")

        # 1. Demo readiness check
        r1 = await c.get(f"{BASE}/milestone/readiness", headers=h)
        ok1 = check(1, "Demo readiness check", r1.status_code, 200)
        if ok1:
            d = r1.json()
            print(f"     Overall ready: {d['overall_ready']} | Score: {d['score']}%")
            for chk in d["checks"]:
                status_icon = "+" if chk["status"] == "pass" else "-"
                print(f"       [{status_icon}] {chk['check']}: {chk['detail']}")

        # 2. Demo script
        r2 = await c.get(f"{BASE}/milestone/demo-script", headers=h)
        ok2 = check(2, "Demo script", r2.status_code, 200)
        if ok2:
            d = r2.json()
            print(f"     Title: {d['title']}")
            print(f"     Duration: {d['duration_minutes']} min | Sections: {len(d['sections'])}")
            for s in d["sections"]:
                print(f"       {s['name']} ({s['duration']}) - {len(s['api_calls'])} API calls")

        # 3. Onboarding checklist
        r3 = await c.get(f"{BASE}/milestone/onboarding/checklist", headers=h)
        ok3 = check(3, "Onboarding checklist", r3.status_code, 200)
        if ok3:
            d = r3.json()
            print(f"     Sections: {len(d['sections'])}")
            for s in d["sections"]:
                print(f"       {s['name']}: {len(s['items'])} items")

        # 4. Register design partner
        r4 = await c.post(f"{BASE}/milestone/onboarding/register", headers=h, json={
            "company_name": "Gulf Trading Enterprises",
            "contact_name": "Ahmed Al-Rashid",
            "contact_email": "ahmed@gulftrading.ae",
            "erp_system": "d365_fo",
            "crm_system": "salesforce",
            "estimated_customers": 150,
            "industry": "trading",
            "region": "GCC",
        })
        ok4 = check(4, "Register design partner", r4.status_code, 200)
        if ok4:
            d = r4.json()
            print(f"     Status: {d['status']} | Company: {d['company']}")
            print(f"     Config: {d['demo_config']}")
            print(f"     Next steps: {len(d['next_steps'])} items")

        # ══════════════════════════════════════
        # SECTION B: Full Feature Regression (Days 5-20)
        # ══════════════════════════════════════
        print("\n--- B. Full Milestone 1 Regression ---")

        regression_tests = [
            # Day 5: Customers & Data Quality
            ("GET", f"{BASE}/customers/?page=1&page_size=5", "Customers list (Day 5)", 200),
            ("GET", f"{BASE}/data-quality/history", "Data quality history (Day 5)", 200),

            # Day 6: Invoices, Payments, Dashboard
            ("GET", f"{BASE}/invoices/?page=1&page_size=5", "Invoices list (Day 6)", 200),
            ("GET", f"{BASE}/payments/?page=1&page_size=5", "Payments list (Day 6)", 200),
            ("GET", f"{BASE}/dashboard/ar-summary", "Dashboard AR summary (Day 6)", 200),
            ("GET", f"{BASE}/dashboard/top-overdue", "Top overdue (Day 6)", 200),

            # Day 10: Briefings
            ("GET", f"{BASE}/briefings/", "Briefing center (Day 10)", 200),
            ("GET", f"{BASE}/briefings/latest", "Latest briefing (Day 10)", 200),

            # Day 11: Intelligence Chat
            ("POST", f"{BASE}/intelligence/chat", "AI Chat (Day 11)", 200),

            # Day 12-13: Collections Copilot
            ("GET", f"{BASE}/collections/", "Collections list (Day 12)", 200),
            ("GET", f"{BASE}/collections-copilot/ptp/dashboard", "PTP dashboard (Day 13)", 200),
            ("GET", f"{BASE}/collections-copilot/disputes/aging", "Dispute aging (Day 13)", 200),

            # Day 14: Health scores, Credit limits, Notifications
            ("GET", f"{BASE}/credit-limits/", "Credit limits (Day 14)", 200),
            ("GET", f"{BASE}/intelligence/credit/recommendations", "Credit AI recs (Day 14)", 200),
            ("GET", f"{BASE}/notifications/inbox", "Notifications (Day 14)", 200),

            # Day 15: CFO Dashboard
            ("GET", f"{BASE}/cfo/dso-trend", "CFO DSO trend (Day 15)", 200),
            ("GET", f"{BASE}/cfo/cash-flow-forecast", "Cash flow forecast (Day 15)", 200),
            ("GET", f"{BASE}/cfo/top-overdue-customers", "CFO top overdue (Day 15)", 200),

            # Day 16: Sales Dashboard
            ("GET", f"{BASE}/sales/summary", "Sales summary (Day 16)", 200),
            ("GET", f"{BASE}/sales/churn-watchlist", "Churn watchlist (Day 16)", 200),
            ("GET", f"{BASE}/sales/reorder-alerts", "Reorder alerts (Day 16)", 200),

            # Day 17: Executive Dashboard
            ("GET", f"{BASE}/executive/kpis", "Executive KPIs (Day 17)", 200),
            ("GET", f"{BASE}/executive/summary", "Executive summary (Day 17)", 200),

            # Day 18: Admin Panel & Agent Hub
            ("GET", f"{BASE}/admin/settings/me", "Admin settings (Day 18)", 200),
            ("GET", f"{BASE}/admin/business-rules", "Business rules (Day 18)", 200),
            ("GET", f"{BASE}/admin/system/health", "System health (Day 18)", 200),
            ("GET", f"{BASE}/admin/audit-logs?page_size=5", "Audit logs (Day 18)", 200),
            ("GET", f"{BASE}/agent-hub/agents", "All agents (Day 18)", 200),
            ("GET", f"{BASE}/agent-hub/dashboard", "Agent dashboard (Day 18)", 200),
            ("GET", f"{BASE}/admin/agents/dependency-map", "Agent dependency map (Day 18)", 200),
            ("GET", f"{BASE}/admin/demo/presets", "Demo presets (Day 18)", 200),
            ("GET", f"{BASE}/admin/demo/summary", "Demo data summary (Day 18)", 200),

            # Day 19: i18n / Locale
            ("GET", f"{BASE}/i18n/locales", "Supported locales (Day 19)", 200),
            ("GET", f"{BASE}/i18n/locales/ar/config", "AR RTL config (Day 19)", 200),
            ("GET", f"{BASE}/i18n/locales/en/translations", "EN translations (Day 19)", 200),

            # Day 20: Performance
            ("GET", f"{BASE}/perf/metrics/summary", "Perf metrics (Day 20)", 200),
            ("GET", f"{BASE}/perf/metrics/cache", "Cache stats (Day 20)", 200),

            # Health
            ("GET", "http://localhost:8000/health", "Health check", 200),
        ]

        test_num = 5
        for method, url, label, expected in regression_tests:
            if method == "POST" and "chat" in url:
                r = await c.post(url, headers=h, json={"message": "What is DSO?"})
            elif method == "POST":
                r = await c.post(url, headers=h, json={})
            elif "i18n/locales/ar/config" in url:
                r = await c.get(url, headers=h)
            else:
                r = await c.get(url, headers=h)
            check(test_num, label, r.status_code, expected)
            test_num += 1

        # ══════════════════════════════════════
        # SECTION C: Milestone 1 Feature Count
        # ══════════════════════════════════════
        print("\n--- C. Milestone 1 Feature Summary ---")

        # Count total API routes
        openapi = await c.get("http://localhost:8000/openapi.json")
        if openapi.status_code == 200:
            paths = openapi.json().get("paths", {})
            route_count = sum(len(methods) for methods in paths.values())
            print(f"     Total API routes: {route_count}")
            print(f"     Total endpoint groups: {len(paths)}")

            # Count by tag
            tags = {}
            for path, methods in paths.items():
                for method, info in methods.items():
                    for tag in info.get("tags", ["untagged"]):
                        tags[tag] = tags.get(tag, 0) + 1
            print(f"     Feature modules: {len(tags)}")
            for tag, count in sorted(tags.items(), key=lambda x: -x[1])[:10]:
                print(f"       {tag}: {count} endpoints")

        # ══════════════════════════════════════
        # SUMMARY
        # ══════════════════════════════════════
        total = passed + failed
        print(f"\n{'=' * 60}")
        print(f"MILESTONE 1 RESULTS: {passed}/{total} PASSED")
        if failed > 0:
            print(f"  FAILURES: {failed}")
        else:
            print("  ALL TESTS PASSED — MILESTONE 1 DEMO-READY!")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
