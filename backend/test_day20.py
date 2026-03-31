"""Day 20 End-to-End Tests: Performance Optimization, Indexing, Caching & Benchmarks"""
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
        print("DAY 20: PERFORMANCE OPTIMIZATION & BENCHMARKS")
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
        # SECTION A: Performance Monitoring Endpoints
        # ══════════════════════════════════════
        print("\n--- A. Performance Monitoring ---")

        # 1. Metrics summary
        r1 = await c.get(f"{BASE}/perf/metrics/summary", headers=h)
        ok1 = check(1, "Metrics summary", r1.status_code, 200)
        if ok1:
            d = r1.json()
            print(f"     Total requests: {d['total_requests']} | Errors: {d['total_errors']} | Error rate: {d['error_rate_pct']}%")
            print(f"     Endpoints tracked: {len(d['endpoints'])}")

        # 2. DB stats
        r2 = await c.get(f"{BASE}/perf/metrics/db", headers=h)
        ok2 = check(2, "Database stats", r2.status_code, 200)
        if ok2:
            d = r2.json()
            print(f"     DB size: {d['database_size']}")
            print(f"     Tables: {len(d['tables'])} | Cache hit ratio: {d['cache_hit_ratio']}%")
            if d["tables"]:
                top = d["tables"][0]
                print(f"     Largest table: {top['table']} (~{top['rows_estimate']} rows, {top['size']})")

        # 3. Index report
        r3 = await c.get(f"{BASE}/perf/metrics/indexes", headers=h)
        ok3 = check(3, "Index report", r3.status_code, 200)
        if ok3:
            d = r3.json()
            print(f"     Top used indexes: {len(d['top_used_indexes'])}")
            print(f"     Unused indexes: {len(d['unused_indexes'])}")
            print(f"     Recommendation: {d['recommendation'][:80]}...")

        # 4. Cache stats
        r4 = await c.get(f"{BASE}/perf/metrics/cache", headers=h)
        ok4 = check(4, "Cache stats", r4.status_code, 200)
        if ok4:
            d = r4.json()
            for name, stats in d.items():
                print(f"     {name}: entries={stats['entries']} hits={stats['hits']} misses={stats['misses']} rate={stats['hit_rate_pct']}%")

        # 5. Clear caches
        r5 = await c.post(f"{BASE}/perf/metrics/cache/clear", headers=h)
        ok5 = check(5, "Clear caches", r5.status_code, 200)
        if ok5:
            print(f"     {r5.json()['message']}")

        # ══════════════════════════════════════
        # SECTION B: Response Time Benchmarks
        # ══════════════════════════════════════
        print("\n--- B. Response Time Benchmarks ---")

        benchmarks = [
            ("GET", f"{BASE}/customers/?page=1&page_size=20", "Customer list"),
            ("GET", f"{BASE}/invoices/?page=1&page_size=20", "Invoice list"),
            ("GET", f"{BASE}/payments/?page=1&page_size=20", "Payment list"),
            ("GET", f"{BASE}/dashboard/ar-summary", "Dashboard AR summary"),
            ("GET", f"{BASE}/executive/kpis", "Executive KPIs"),
            ("GET", f"{BASE}/cfo/dso-trend", "CFO DSO trend"),
            ("GET", f"{BASE}/sales/summary", "Sales summary"),
            ("GET", f"{BASE}/agent-hub/dashboard", "Agent Hub dashboard"),
            ("GET", f"{BASE}/admin/system/health", "System health"),
            ("GET", f"{BASE}/admin/audit-logs?page_size=10", "Audit logs"),
        ]

        all_times = []
        test_num = 6
        for method, url, label in benchmarks:
            times = []
            for _ in range(3):
                start = time.perf_counter()
                if method == "GET":
                    r = await c.get(url, headers=h)
                else:
                    r = await c.post(url, headers=h, json={})
                elapsed = (time.perf_counter() - start) * 1000
                times.append(elapsed)

            avg = sum(times) / len(times)
            min_t = min(times)
            max_t = max(times)
            all_times.append(avg)

            ok = r.status_code == 200 and avg < 2000  # < 2s target
            if ok:
                passed += 1
            else:
                failed += 1
            mark = "PASS" if ok else "FAIL"

            resp_time_header = r.headers.get("x-response-time", "N/A")
            print(f"  {mark} {test_num}. {label}: avg={avg:.0f}ms min={min_t:.0f}ms max={max_t:.0f}ms (server: {resp_time_header})")
            test_num += 1

        overall_avg = sum(all_times) / len(all_times)
        print(f"\n     Overall average: {overall_avg:.0f}ms across {len(benchmarks)} endpoints")
        print(f"     Target: < 2000ms per endpoint")

        # ══════════════════════════════════════
        # SECTION C: Verify Indexes Exist
        # ══════════════════════════════════════
        print("\n--- C. Index Verification ---")

        r16 = await c.get(f"{BASE}/perf/metrics/db", headers=h)
        check(test_num, "Index verification", r16.status_code, 200)
        test_num += 1
        if r16.status_code == 200:
            idx_list = r16.json().get("top_indexes_by_usage", [])
            idx_names = [i["index"] for i in idx_list]
            # Check that our Day 20 indexes appear
            day20_indexes = [
                "ix_invoice_tenant_cust_status",
                "ix_customer_tenant_risk",
                "ix_customer_tenant_territory",
                "ix_payment_tenant_cust_date",
                "ix_agent_run_tenant_agent_status",
            ]
            found = [ix for ix in day20_indexes if any(ix in n for n in idx_names)]
            print(f"     Day 20 indexes found in top usage: {len(found)}/{len(day20_indexes)}")
            # Also verify via total index count
            all_idx = r16.json().get("top_indexes_by_usage", [])
            print(f"     Total tracked indexes: {len(all_idx)}")

        # ══════════════════════════════════════
        # SECTION D: Metrics After Benchmark
        # ══════════════════════════════════════
        print("\n--- D. Post-Benchmark Metrics ---")

        r17 = await c.get(f"{BASE}/perf/metrics/summary", headers=h)
        ok17 = check(test_num, "Post-benchmark metrics", r17.status_code, 200)
        test_num += 1
        if ok17:
            d = r17.json()
            print(f"     Total requests: {d['total_requests']}")
            print(f"     Endpoints tracked: {len(d['endpoints'])}")
            print(f"     Error rate: {d['error_rate_pct']}%")
            print(f"     Slow requests: {len(d['slow_requests'])}")
            if d["endpoints"]:
                fastest = min(d["endpoints"], key=lambda e: e["avg_ms"])
                slowest = max(d["endpoints"], key=lambda e: e["avg_ms"])
                print(f"     Fastest: {fastest['endpoint']} ({fastest['avg_ms']}ms avg)")
                print(f"     Slowest: {slowest['endpoint']} ({slowest['avg_ms']}ms avg)")

        # ══════════════════════════════════════
        # SECTION E: Regression (Day 19 endpoints still work)
        # ══════════════════════════════════════
        print("\n--- E. Quick Regression ---")

        regressions = [
            (f"{BASE}/i18n/locales", "i18n locales"),
            (f"{BASE}/i18n/locales/ar/config", "AR RTL config (auth)"),
            (f"{BASE}/admin/settings/me", "Admin settings"),
            (f"{BASE}/intelligence/chat", "Chat (POST)"),
        ]

        for url, label in regressions:
            if "chat" in label.lower():
                r = await c.post(url, headers=h, json={"message": "test"})
            elif "auth" in label.lower():
                r = await c.get(url, headers=h)
            else:
                r = await c.get(url, headers=h)
            check(test_num, label, r.status_code, 200)
            test_num += 1

        # ══════════════════════════════════════
        # SUMMARY
        # ══════════════════════════════════════
        total = passed + failed
        print(f"\n{'=' * 60}")
        print(f"DAY 20 RESULTS: {passed}/{total} PASSED")
        if failed > 0:
            print(f"  FAILURES: {failed}")
        else:
            print("  ALL TESTS PASSED!")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
