"""Day 19 End-to-End Tests: RTL/i18n Backend, Error Handling, Cross-Screen Regression"""
import asyncio, httpx, sys, io, time

# Fix Windows console encoding
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
        print("DAY 19: RTL/i18n BACKEND, ERROR HANDLING & REGRESSION")
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
        # SECTION A: i18n / Locale Endpoints
        # ══════════════════════════════════════
        print("\n--- A. Locale / i18n Endpoints ---")

        # 1. Supported locales (no auth required)
        r1 = await c.get(f"{BASE}/i18n/locales")
        ok1 = check(1, "Supported locales", r1.status_code, 200)
        if ok1:
            d = r1.json()
            print(f"     Locales: {[l['code'] for l in d['locales']]} | Default: {d['default']}")
            assert d["default"] == "en"
            assert len(d["locales"]) == 2

        # 2. English locale config
        r2 = await c.get(f"{BASE}/i18n/locales/en/config", headers=h)
        ok2 = check(2, "EN locale config", r2.status_code, 200)
        if ok2:
            d = r2.json()
            print(f"     Direction: {d['rtl']['direction']} | Sidebar: {d['rtl']['sidebar_position']} | Calendar: {d['rtl']['calendar_type']}")
            assert d["rtl"]["is_rtl"] == False
            assert d["rtl"]["direction"] == "ltr"

        # 3. Arabic locale config (RTL)
        r3 = await c.get(f"{BASE}/i18n/locales/ar/config", headers=h)
        ok3 = check(3, "AR locale config (RTL)", r3.status_code, 200)
        if ok3:
            d = r3.json()
            print(f"     Direction: {d['rtl']['direction']} | Sidebar: {d['rtl']['sidebar_position']} | Numbers: {d['rtl']['number_display']}")
            assert d["rtl"]["is_rtl"] == True
            assert d["rtl"]["direction"] == "rtl"
            assert d["rtl"]["sidebar_position"] == "right"
            assert d["rtl"]["chart_axis_direction"] == "right-to-left"

        # 4. Unsupported locale
        r4 = await c.get(f"{BASE}/i18n/locales/fr/config", headers=h)
        check(4, "Unsupported locale 404", r4.status_code, 404)

        # 5. English translations
        r5 = await c.get(f"{BASE}/i18n/locales/en/translations")
        ok5 = check(5, "EN translations", r5.status_code, 200)
        if ok5:
            d = r5.json()
            print(f"     Namespaces: {d['namespaces']}")
            assert "common" in d["namespaces"]
            assert "dashboard" in d["namespaces"]

        # 6. Arabic translations
        r6 = await c.get(f"{BASE}/i18n/locales/ar/translations")
        ok6 = check(6, "AR translations", r6.status_code, 200)
        if ok6:
            d = r6.json()
            # Check Arabic content
            common = next(b for b in d["bundles"] if b["namespace"] == "common")
            print(f"     AR app_name: {common['translations']['app_name']}")
            print(f"     AR welcome: {common['translations']['welcome']}")
            assert common["translations"]["welcome"] == "\u0645\u0631\u062d\u0628\u0627\u064b"

        # 7. Specific namespace translation
        r7 = await c.get(f"{BASE}/i18n/locales/ar/translations/dashboard")
        ok7 = check(7, "AR dashboard namespace", r7.status_code, 200)
        if ok7:
            d = r7.json()
            print(f"     AR total_ar: {d['translations']['total_ar']}")
            print(f"     AR avg_dso: {d['translations']['avg_dso']}")

        # 8. Response headers: Content-Language and X-Text-Direction
        r8 = await c.get(f"{BASE}/i18n/locales", headers={"Accept-Language": "ar-SA,ar;q=0.9"})
        check(8, "Content-Language header", r8.status_code, 200)
        cl = r8.headers.get("content-language", "")
        td = r8.headers.get("x-text-direction", "")
        print(f"     Content-Language: {cl} | X-Text-Direction: {td}")
        if cl == "ar" and td == "rtl":
            print(f"     RTL headers correct!")

        # 9. ?lang= query param override
        r9 = await c.get(f"{BASE}/i18n/locales?lang=ar", headers={"Accept-Language": "en"})
        check(9, "?lang= override", r9.status_code, 200)
        cl9 = r9.headers.get("content-language", "")
        print(f"     Query override -> Content-Language: {cl9}")

        # ══════════════════════════════════════
        # SECTION B: Error Handling
        # ══════════════════════════════════════
        print("\n--- B. Error Handling ---")

        # 10. 401 Unauthorized (no token)
        r10 = await c.get(f"{BASE}/admin/settings/me")
        check(10, "401 no token", r10.status_code, 401)
        if r10.status_code == 401:
            d = r10.json()
            has_error = "error" in d or "detail" in d
            print(f"     Structured error: {has_error}")

        # 11. 404 Not found
        r11 = await c.get(f"{BASE}/nonexistent/endpoint", headers=h)
        check(11, "404 not found", r11.status_code, 404)

        # 12. 422 Validation error (bad body)
        r12 = await c.post(f"{BASE}/admin/users/invite", headers=h, json={})
        check(12, "422 validation error", r12.status_code, 422)
        if r12.status_code == 422:
            d = r12.json()
            has_details = "error" in d and "details" in d.get("error", {})
            print(f"     Structured validation errors: {has_details}")
            if has_details:
                print(f"     Fields: {[e['field'] for e in d['error']['details']]}")

        # 13. X-Request-ID header present
        r13 = await c.get(f"{BASE}/ping")
        check(13, "X-Request-ID header", r13.status_code, 200)
        rid = r13.headers.get("x-request-id", "")
        rtime = r13.headers.get("x-response-time", "")
        print(f"     Request-ID: {rid[:20]}... | Response-Time: {rtime}")

        # ══════════════════════════════════════
        # SECTION C: Cross-Screen Regression (Days 6-18)
        # ══════════════════════════════════════
        print("\n--- C. Cross-Screen Regression ---")

        # 14. Customers list (Day 5)
        r14 = await c.get(f"{BASE}/customers/?page=1&page_size=5", headers=h)
        check(14, "Customers list", r14.status_code, 200)

        # 15. Invoices (Day 6)
        r15 = await c.get(f"{BASE}/invoices/?page=1&page_size=5", headers=h)
        check(15, "Invoices list", r15.status_code, 200)

        # 16. Payments (Day 6)
        r16 = await c.get(f"{BASE}/payments/?page=1&page_size=5", headers=h)
        check(16, "Payments list", r16.status_code, 200)

        # 17. Dashboard AR summary (Day 6)
        r17 = await c.get(f"{BASE}/dashboard/ar-summary", headers=h)
        check(17, "Dashboard AR summary", r17.status_code, 200)

        # 18. Data Quality history (Day 5)
        r18 = await c.get(f"{BASE}/data-quality/history", headers=h)
        check(18, "Data quality history", r18.status_code, 200)

        # 19. Disputes aging (Day 13)
        r19 = await c.get(f"{BASE}/collections-copilot/disputes/aging", headers=h)
        check(19, "Disputes aging", r19.status_code, 200)

        # 20. Credit limits (Day 14)
        r20 = await c.get(f"{BASE}/credit-limits/", headers=h)
        check(20, "Credit limits", r20.status_code, 200)

        # 21. Collections list (Day 12-13)
        r21 = await c.get(f"{BASE}/collections/", headers=h)
        check(21, "Collections list", r21.status_code, 200)

        # 22. Briefing center (Day 10)
        r22 = await c.get(f"{BASE}/briefings/", headers=h)
        check(22, "Briefing center", r22.status_code, 200)

        # 23. Intelligence chat (Day 11)
        r23 = await c.post(f"{BASE}/intelligence/chat", headers=h, json={
            "message": "What is the current DSO?",
        })
        check(23, "Intelligence chat", r23.status_code, 200)

        # 24. CFO Dashboard (Day 15)
        r24 = await c.get(f"{BASE}/cfo/dso-trend", headers=h)
        check(24, "CFO DSO trend", r24.status_code, 200)

        # 25. Sales Dashboard (Day 16)
        r25 = await c.get(f"{BASE}/sales/summary", headers=h)
        check(25, "Sales summary", r25.status_code, 200)

        # 26. Executive Dashboard (Day 17)
        r26 = await c.get(f"{BASE}/executive/kpis", headers=h)
        check(26, "Executive KPIs", r26.status_code, 200)

        # 27. Admin settings (Day 18)
        r27 = await c.get(f"{BASE}/admin/settings/me", headers=h)
        check(27, "Admin settings", r27.status_code, 200)

        # 28. Agent Hub (Day 18)
        r28 = await c.get(f"{BASE}/agent-hub/agents", headers=h)
        check(28, "Agent Hub agents", r28.status_code, 200)
        if r28.status_code == 200:
            print(f"     Total agents: {len(r28.json())}")

        # 29. Notifications (Day 14)
        r29 = await c.get(f"{BASE}/notifications/inbox", headers=h)
        check(29, "Notifications inbox", r29.status_code, 200)

        # 30. Health check
        r30 = await c.get("http://localhost:8000/health")
        check(30, "Health check", r30.status_code, 200)

        # ══════════════════════════════════════
        # SUMMARY
        # ══════════════════════════════════════
        print(f"\n{'=' * 60}")
        print(f"DAY 19 RESULTS: {passed}/{passed + failed} PASSED")
        if failed > 0:
            print(f"  FAILURES: {failed}")
        else:
            print("  ALL TESTS PASSED!")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
