"""Day 9 - Agent Hub Dashboard End-to-End Tests"""
import asyncio, httpx, json

BASE = "http://localhost:8000/api/v1"


async def main():
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{BASE}/auth/login", json={"email": "admin@salesiq.ai", "password": "Admin@2024", "tenant_slug": "demo"})
        tok = r.json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        print("=== Login OK ===")

        # ============================
        # AGENT HUB DASHBOARD
        # ============================
        print("\n=== AGENT HUB DASHBOARD ===")

        # 1. Get dashboard overview
        dash = await c.get(f"{BASE}/agent-hub/dashboard", headers=h)
        print(f"1. Dashboard: {dash.status_code}")
        if dash.status_code == 200:
            dd = dash.json()
            print(f"   Total agents: {dd['total_agents']} | Active: {dd['active_agents']}")
            print(f"   Runs 24h: {dd['total_runs_24h']} | Runs 7d: {dd['total_runs_7d']}")
            print(f"   Success rate: {dd['overall_success_rate']}%")
            print(f"   Records processed 24h: {dd['total_records_processed_24h']}")
            print(f"   Agent health:")
            for ag in dd["agents"]:
                print(f"     - {ag['display_name']}: {ag['status']} | health={ag['health_score']} | runs_24h={ag['runs_24h']}")
            if dd["recent_errors"]:
                print(f"   Recent errors: {len(dd['recent_errors'])}")
                for err in dd["recent_errors"][:2]:
                    print(f"     - {err['agent_name']}: {err['error'][:80]}...")
            print(f"   Performance trend (7d): {len(dd['performance_trend'])} days")

        # ============================
        # AGENT LISTING & DETAILS
        # ============================
        print("\n=== AGENT REGISTRY ===")

        # 2. List all agents
        agents = await c.get(f"{BASE}/agent-hub/agents", headers=h)
        print(f"2. List agents: {agents.status_code} | count={len(agents.json())}")
        for ag in agents.json():
            print(f"   - {ag['agent_name']}: {ag['display_name']} ({ag['category']})")
            print(f"     Stages: {[s['name'] for s in ag['stages']]}")
            print(f"     Status: {ag['status']} | Health: {ag['health_score']} | Total runs: {ag['total_runs']}")

        # 3. Get specific agent detail
        dq = await c.get(f"{BASE}/agent-hub/agents/data_quality", headers=h)
        print(f"\n3. DQ Agent detail: {dq.status_code}")
        if dq.status_code == 200:
            dqd = dq.json()
            print(f"   Version: {dqd['version']} | Success rate: {dqd['success_rate']}%")
            print(f"   Avg duration: {dqd['avg_duration_ms']}ms")
            print(f"   Last run: {dqd['last_run_at']} ({dqd['last_run_status']})")

        # 4. Get briefing agent detail
        ba = await c.get(f"{BASE}/agent-hub/agents/briefing_agent", headers=h)
        print(f"4. Briefing Agent detail: {ba.status_code}")
        if ba.status_code == 200:
            bad = ba.json()
            print(f"   Success rate: {bad['success_rate']}% | Total runs: {bad['total_runs']}")

        # 5. Non-existent agent
        na = await c.get(f"{BASE}/agent-hub/agents/nonexistent", headers=h)
        print(f"5. Unknown agent: {na.status_code} (expect 404)")

        # ============================
        # RUN HISTORY
        # ============================
        print("\n=== RUN HISTORY ===")

        # 6. All runs
        runs = await c.get(f"{BASE}/agent-hub/runs", headers=h)
        print(f"6. All runs: {runs.status_code} | total={runs.json()['total']}")
        for run in runs.json()["items"][:3]:
            print(f"   - {run['agent_name']} | {run['status']} | {run['duration_ms']}ms | processed={run['records_processed']}")

        # 7. Filter by agent
        dq_runs = await c.get(f"{BASE}/agent-hub/runs?agent_name=data_quality", headers=h)
        print(f"7. DQ runs: {dq_runs.status_code} | total={dq_runs.json()['total']}")

        # 8. Filter by status
        failed_runs = await c.get(f"{BASE}/agent-hub/runs?status=failed", headers=h)
        print(f"8. Failed runs: {failed_runs.status_code} | total={failed_runs.json()['total']}")

        # 9. Get specific run detail
        if runs.json()["items"]:
            first_run_id = runs.json()["items"][0]["id"]
            run_detail = await c.get(f"{BASE}/agent-hub/runs/{first_run_id}", headers=h)
            print(f"9. Run detail: {run_detail.status_code}")
            if run_detail.status_code == 200:
                rd = run_detail.json()
                print(f"   Agent: {rd['agent_name']} | Type: {rd['run_type']} | Duration: {rd['duration_ms']}ms")

        # ============================
        # AGENT CONTROLS
        # ============================
        print("\n=== AGENT CONTROLS ===")

        # 10. Trigger DQ agent manually
        trigger = await c.post(f"{BASE}/agent-hub/agents/data_quality/trigger", headers=h, json={
            "entity_type": "customers",
        })
        print(f"10. Trigger DQ: {trigger.status_code}")
        if trigger.status_code == 200:
            td = trigger.json()
            print(f"    Status: {td['status']} | Message: {td['message']}")

        # 11. Trigger Briefing agent
        trigger_br = await c.post(f"{BASE}/agent-hub/agents/briefing_agent/trigger", headers=h, json={
            "run_params": {"briefing_type": "daily_flash"},
        })
        print(f"11. Trigger Briefing: {trigger_br.status_code}")
        if trigger_br.status_code == 200:
            tbd = trigger_br.json()
            print(f"    Status: {tbd['status']} | Message: {tbd['message']}")

        # 12. Pause agent
        pause = await c.post(f"{BASE}/agent-hub/agents/data_quality/pause", headers=h)
        print(f"12. Pause DQ: {pause.status_code} | status={pause.json().get('status')}")

        # 13. Try triggering paused agent (should fail)
        trigger_paused = await c.post(f"{BASE}/agent-hub/agents/data_quality/trigger", headers=h, json={
            "entity_type": "customers",
        })
        print(f"13. Trigger paused: {trigger_paused.status_code} (expect 400)")

        # 14. Resume agent
        resume = await c.post(f"{BASE}/agent-hub/agents/data_quality/resume", headers=h)
        print(f"14. Resume DQ: {resume.status_code} | status={resume.json().get('status')}")

        # 15. Update agent config
        cfg = await c.patch(f"{BASE}/agent-hub/agents/data_quality/config", headers=h, json={
            "config": {"dedup_threshold": 0.70, "auto_apply_normalizations": True},
            "schedule_cron": "0 2 * * *",
        })
        print(f"15. Update config: {cfg.status_code}")
        if cfg.status_code == 200:
            cd = cfg.json()
            print(f"    Schedule: {cd.get('schedule_cron')} | Config: {cd.get('config')}")

        # 16. Resume non-paused agent (should fail)
        resume_active = await c.post(f"{BASE}/agent-hub/agents/data_quality/resume", headers=h)
        print(f"16. Resume active agent: {resume_active.status_code} (expect 400)")

        # 17. Verify dashboard updated after triggers
        dash2 = await c.get(f"{BASE}/agent-hub/dashboard", headers=h)
        if dash2.status_code == 200:
            dd2 = dash2.json()
            print(f"\n17. Updated dashboard:")
            print(f"    Runs 24h: {dd2['total_runs_24h']} | Records 24h: {dd2['total_records_processed_24h']}")

        # ============================
        # FINAL CHECKS
        # ============================
        print("\n=== FINAL CHECKS ===")
        all_pass = all([
            dash.status_code == 200,
            agents.status_code == 200,
            len(agents.json()) == 2,
            dq.status_code == 200,
            ba.status_code == 200,
            na.status_code == 404,
            runs.status_code == 200,
            dq_runs.status_code == 200,
            failed_runs.status_code == 200,
            trigger.status_code == 200,
            trigger_br.status_code == 200,
            pause.status_code == 200,
            trigger_paused.status_code == 400,
            resume.status_code == 200,
            cfg.status_code == 200,
            resume_active.status_code == 400,
            dash2.status_code == 200,
        ])
        print("=== ALL DAY 9 TESTS PASSED ===" if all_pass else "=== SOME TESTS FAILED ===")


asyncio.run(main())
