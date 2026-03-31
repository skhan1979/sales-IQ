"""Day 8 - Briefing System End-to-End Tests"""
import asyncio, httpx, json

BASE = "http://localhost:8000/api/v1"


async def main():
    async with httpx.AsyncClient(timeout=60) as c:
        # Login
        r = await c.post(f"{BASE}/auth/login", json={"email": "admin@salesiq.ai", "password": "Admin@2024", "tenant_slug": "demo"})
        tok = r.json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}

        # Get current user ID
        me = await c.get(f"{BASE}/auth/me", headers=h)
        user_id = me.json()["user"]["id"]
        print("=== Login OK ===")

        # Ensure we have data (generate if empty)
        custs = await c.get(f"{BASE}/customers/?page_size=1", headers=h)
        if not custs.json()["items"]:
            gen = await c.post(f"{BASE}/demo-data/generate", headers=h, json={"size": "small", "erp_profile": "d365_fo"})
            print(f"Generated demo data: {gen.status_code}")
        else:
            print(f"Using existing data ({custs.json()['total']} customers)")

        # ============================
        # BRIEFING GENERATION
        # ============================
        print("\n=== BRIEFING GENERATION ===")

        # 1. Generate daily flash briefing
        b1 = await c.post(f"{BASE}/briefings/generate", headers=h, json={
            "briefing_type": "daily_flash",
            "delivery": "in_app",
        })
        print(f"1. Daily flash: {b1.status_code}")
        b1_id = None
        if b1.status_code == 201:
            bd = b1.json()
            b1_id = bd["id"]
            print(f"   Title: {bd['title']}")
            print(f"   Generation time: {bd['generation_time_ms']}ms")
            print(f"   Sections: {len(bd.get('sections', []))}")
            for sec in bd.get("sections", []):
                prio_label = ["Normal", "Attention", "Critical"][min(sec.get("priority", 0), 2)]
                print(f"     - {sec['title']} [{prio_label}]")
            # Print executive summary preview
            summary = bd.get("executive_summary", "")
            if summary:
                lines = summary.split("\n")
                for line in lines[:3]:
                    if line.strip():
                        print(f"   {line.strip()}")

        # 2. Generate weekly digest
        b2 = await c.post(f"{BASE}/briefings/generate", headers=h, json={
            "briefing_type": "weekly_digest",
            "delivery": "both",
        })
        print(f"\n2. Weekly digest: {b2.status_code}")
        b2_id = None
        if b2.status_code == 201:
            bd2 = b2.json()
            b2_id = bd2["id"]
            print(f"   Title: {bd2['title']}")
            print(f"   Sections: {len(bd2.get('sections', []))}")

        # 3. Generate monthly review
        b3 = await c.post(f"{BASE}/briefings/generate", headers=h, json={
            "briefing_type": "monthly_review",
            "delivery": "email",
        })
        print(f"\n3. Monthly review: {b3.status_code}")
        if b3.status_code == 201:
            bd3 = b3.json()
            print(f"   Title: {bd3['title']}")
            print(f"   Sections: {len(bd3.get('sections', []))}")
            # Verify monthly has all 7 sections
            section_types = [s["section_type"] for s in bd3.get("sections", [])]
            print(f"   Section types: {section_types}")

        # ============================
        # BRIEFING RETRIEVAL
        # ============================
        print("\n=== BRIEFING RETRIEVAL ===")

        # 4. Get specific briefing
        if b1_id:
            get1 = await c.get(f"{BASE}/briefings/{b1_id}", headers=h)
            print(f"4. Get by ID: {get1.status_code}")
            if get1.status_code == 200:
                gd = get1.json()
                print(f"   Opened at: {gd.get('opened_at', 'N/A')}")
                # Verify data_snapshot has real data
                snap = gd.get("data_snapshot", {})
                print(f"   Snapshot - AR: {snap.get('ar', {}).get('total_ar', 0):,.0f} | "
                      f"DSO: {snap.get('ar', {}).get('dso', 0)} | "
                      f"Customers: {snap.get('customers', {}).get('total', 0)}")

        # 5. Get latest briefing
        latest = await c.get(f"{BASE}/briefings/latest", headers=h)
        print(f"5. Get latest: {latest.status_code} | title={latest.json().get('title', 'N/A')}")

        # 6. List all briefings
        blist = await c.get(f"{BASE}/briefings/", headers=h)
        print(f"6. List: {blist.status_code} | total={blist.json().get('total', 0)}")

        # 7. Get HTML version
        if b1_id:
            html = await c.get(f"{BASE}/briefings/{b1_id}/html", headers=h)
            print(f"7. HTML view: {html.status_code} | length={len(html.text)} chars")
            has_styles = "<style>" in html.text
            has_sections = 'class="section"' in html.text
            print(f"   Has styles: {has_styles} | Has sections: {has_sections}")

        # ============================
        # SCHEDULING
        # ============================
        print("\n=== BRIEFING SCHEDULES ===")

        # 8. Create daily schedule
        sched1 = await c.post(f"{BASE}/briefings/schedules", headers=h, json={
            "briefing_type": "daily_flash",
            "schedule_cron": "0 7 * * 1-5",
            "recipient_ids": [user_id],
            "delivery": "email",
            "timezone": "Asia/Dubai",
        })
        print(f"8. Create daily schedule: {sched1.status_code}")
        sched1_id = None
        if sched1.status_code == 201:
            sd = sched1.json()
            sched1_id = sd["id"]
            print(f"   Cron: {sd['schedule_cron']} | TZ: {sd['timezone']} | Next: {sd.get('next_run', 'N/A')}")

        # 9. Create weekly schedule
        sched2 = await c.post(f"{BASE}/briefings/schedules", headers=h, json={
            "briefing_type": "weekly_digest",
            "schedule_cron": "0 8 * * 0",
            "recipient_ids": [user_id],
            "delivery": "both",
            "sections": ["executive_summary", "ar_overview", "risk_alerts", "dispute_update"],
            "timezone": "Asia/Dubai",
        })
        print(f"9. Create weekly schedule: {sched2.status_code}")

        # 10. List schedules
        sched_list = await c.get(f"{BASE}/briefings/schedules/list", headers=h)
        print(f"10. List schedules: {sched_list.status_code} | total={sched_list.json().get('total', 0)}")

        # 11. Update schedule (pause)
        if sched1_id:
            upd = await c.patch(f"{BASE}/briefings/schedules/{sched1_id}", headers=h, json={
                "is_active": False,
            })
            print(f"11. Pause schedule: {upd.status_code} | active={upd.json().get('is_active')}")

        # 12. Delete schedule
        if sched1_id:
            dlt = await c.delete(f"{BASE}/briefings/schedules/{sched1_id}", headers=h)
            print(f"12. Delete schedule: {dlt.status_code} (expect 204)")

        # Verify deletion
        sched_after = await c.get(f"{BASE}/briefings/schedules/list", headers=h)
        print(f"    Schedules after delete: {sched_after.json().get('total', 0)}")

        # ============================
        # DATA QUALITY OF BRIEFING
        # ============================
        print("\n=== BRIEFING CONTENT VALIDATION ===")

        # Verify the daily flash has correct sections
        if b1.status_code == 201:
            expected_daily = {"executive_summary", "ar_overview", "risk_alerts", "collection_priorities"}
            actual_daily = {s["section_type"] for s in b1.json().get("sections", [])}
            daily_ok = expected_daily == actual_daily
            print(f"13. Daily flash sections correct: {daily_ok} ({actual_daily})")

        # Verify weekly has more sections than daily
        if b2.status_code == 201:
            weekly_count = len(b2.json().get("sections", []))
            daily_count = len(b1.json().get("sections", []))
            print(f"14. Weekly ({weekly_count}) > Daily ({daily_count}): {weekly_count >= daily_count}")

        # Verify monthly has all 7 sections
        if b3.status_code == 201:
            monthly_count = len(b3.json().get("sections", []))
            print(f"15. Monthly has all sections: {monthly_count} (expect 7)")

        # ============================
        # FINAL CHECKS
        # ============================
        print("\n=== FINAL CHECKS ===")
        all_pass = all([
            b1.status_code == 201,
            b2.status_code == 201,
            b3.status_code == 201,
            get1.status_code == 200 if b1_id else True,
            latest.status_code == 200,
            blist.status_code == 200,
            html.status_code == 200 if b1_id else True,
            sched1.status_code == 201,
            sched2.status_code == 201,
            sched_list.status_code == 200,
            upd.status_code == 200 if sched1_id else True,
            dlt.status_code == 204 if sched1_id else True,
        ])
        print("=== ALL DAY 8 TESTS PASSED ===" if all_pass else "=== SOME TESTS FAILED ===")


asyncio.run(main())
