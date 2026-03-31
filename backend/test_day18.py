"""Day 18 End-to-End Tests: Admin Panel, Agent Hub Dashboard, Demo Data Manager"""
import asyncio, httpx, json, sys, io, time

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

        # Ensure demo data
        demo = await c.post(f"{BASE}/demo-data/generate", json={"dataset_size": "medium", "erp_profile": "d365_fo"}, headers=h)
        print(f"Demo data: {demo.status_code}")

        print("\n" + "=" * 60)
        print("DAY 18: ADMIN PANEL, AGENT HUB & DEMO MANAGER")
        print("=" * 60)

        # ── 1. User Settings ──
        print("\n--- User Settings ---")
        settings = await c.get(f"{BASE}/admin/settings/me", headers=h)
        print(f"\n1. My settings: {settings.status_code}")
        if settings.status_code == 200:
            sd = settings.json()
            print(f"   Name: {sd['full_name']} | Role: {sd['role']} | TZ: {sd['timezone']} | Lang: {sd['language']}")
            print(f"   Notifications: {sd['notification_preferences']}")

        # 2. Update profile
        update = await c.put(f"{BASE}/admin/settings/me", headers=h, json={
            "timezone": "Asia/Riyadh",
            "language": "ar",
        })
        print(f"\n2. Update profile: {update.status_code}")
        if update.status_code == 200:
            ud = update.json()
            print(f"   TZ now: {ud['timezone']} | Lang now: {ud['language']}")

        # 3. Notification preferences
        notif = await c.put(f"{BASE}/admin/settings/me/notifications", headers=h, json={
            "email_enabled": True, "in_app_enabled": True, "daily_briefing": True,
            "overdue_alerts": True, "dispute_updates": False,
            "credit_hold_alerts": True, "agent_failure_alerts": True,
        })
        print(f"\n3. Notification prefs: {notif.status_code}")
        if notif.status_code == 200:
            print(f"   Agent failure alerts: {notif.json()['agent_failure_alerts']}")

        # ── 4. User Management ──
        print("\n--- User Management ---")
        users = await c.get(f"{BASE}/admin/users", headers=h)
        print(f"\n4. User list: {users.status_code}")
        if users.status_code == 200:
            ud = users.json()
            print(f"   Total users: {ud['total']}")
            for u in ud["items"][:3]:
                print(f"     {u['email']} ({u['role']}) active={u['is_active']}")

        # 5. Invite a user
        unique_email = f"testuser_{int(time.time())}@salesiq.ai"
        invite = await c.post(f"{BASE}/admin/users/invite", headers=h, json={
            "email": unique_email,
            "full_name": "Test Collector",
            "role": "collector",
        })
        print(f"\n5. Invite user: {invite.status_code}")
        if invite.status_code == 201:
            inv = invite.json()
            print(f"   Created: {inv['email']} as {inv['role']}")
            new_user_id = inv["id"]

            # 6. Update role
            role_up = await c.put(f"{BASE}/admin/users/{new_user_id}/role", headers=h, json={
                "role": "finance_manager",
                "territory_ids": ["a1b2c3d4-e5f6-7890-abcd-ef1234567890", "b2c3d4e5-f6a7-8901-bcde-f12345678901"],
            })
            print(f"\n6. Update role: {role_up.status_code}")
            if role_up.status_code == 200:
                print(f"   New role: {role_up.json()['role']} territories: {role_up.json().get('territory_ids')}")

            # 7. Deactivate
            deact = await c.post(f"{BASE}/admin/users/{new_user_id}/deactivate", headers=h)
            print(f"\n7. Deactivate: {deact.status_code}")
            if deact.status_code == 200:
                print(f"   Active: {deact.json()['is_active']}")

        # ── 8. Business Rules ──
        print("\n--- Business Rules ---")
        rules = await c.get(f"{BASE}/admin/business-rules", headers=h)
        print(f"\n8. Business rules: {rules.status_code}")
        if rules.status_code == 200:
            rd = rules.json()["config"]
            print(f"   Scoring model: {rd['ai_scoring_model']}")
            print(f"   Weights: pay={rd['payment_weight']} eng={rd['engagement_weight']} order={rd['order_trend_weight']} risk={rd['risk_flag_weight']}")
            print(f"   Overdue alert: {rd['overdue_alert_days']}d | Churn threshold: {rd['churn_alert_threshold']}")

        # 9. Update rules
        new_rules = await c.put(f"{BASE}/admin/business-rules", headers=h, json={
            "overdue_alert_days": 5,
            "churn_alert_threshold": 0.25,
            "payment_weight": 0.45,
        })
        print(f"\n9. Update rules: {new_rules.status_code}")
        if new_rules.status_code == 200:
            nr = new_rules.json()["config"]
            print(f"   Overdue alert now: {nr['overdue_alert_days']}d | Churn: {nr['churn_alert_threshold']} | Pay weight: {nr['payment_weight']}")

        # ── 10. System Health ──
        print("\n--- System Monitor ---")
        health = await c.get(f"{BASE}/admin/system/health", headers=h)
        print(f"\n10. System health: {health.status_code}")
        if health.status_code == 200:
            hd = health.json()
            print(f"    API: {hd['api_status']} | DB: {hd['database_status']} | Cache: {hd['cache_status']}")
            print(f"    Uptime: {hd['uptime_seconds']}s | API calls 24h: {hd['api_calls_24h']}")
            print(f"    Error rate: {hd['error_rate_24h']}% | BG jobs: {len(hd['background_jobs'])}")

        # ── 11. Audit Logs ──
        print("\n--- Audit Logs ---")
        audits = await c.get(f"{BASE}/admin/audit-logs?page_size=5", headers=h)
        print(f"\n11. Audit logs: {audits.status_code}")
        if audits.status_code == 200:
            ad = audits.json()
            print(f"    Total: {ad['total']} | Showing: {len(ad['items'])}")
            for a in ad["items"][:3]:
                print(f"      [{a['action']}] {a['entity_type']} by {a['user_email'] or 'system'}")

        # ── 12. Agent Hub - All 7 Agents ──
        print("\n--- Agent Hub (All 7 Agents) ---")
        agents = await c.get(f"{BASE}/agent-hub/agents", headers=h)
        print(f"\n12. All agents: {agents.status_code}")
        if agents.status_code == 200:
            ag = agents.json()
            print(f"    Total agents: {len(ag)}")
            for a in ag:
                print(f"      [{a['status']}] {a['display_name']} (v{a['version']}) health={a['health_score']} runs={a['total_runs']}")

        # ── 13. Agent Dependency Map ──
        print("\n--- Agent Dependency Map ---")
        deps = await c.get(f"{BASE}/admin/agents/dependency-map", headers=h)
        print(f"\n13. Dependency map: {deps.status_code}")
        if deps.status_code == 200:
            dm = deps.json()
            print(f"    Agents: {dm['agents']}")
            print(f"    Links: {len(dm['links'])}")
            for link in dm["links"]:
                print(f"      {link['source_agent']} --[{link['relationship']}]--> {link['target_agent']}")

        # ── 14. Agent Performance History ──
        print("\n--- Agent Performance History ---")
        perf = await c.get(f"{BASE}/admin/agents/data_quality/performance?days=7", headers=h)
        print(f"\n14. DQ agent performance: {perf.status_code}")
        if perf.status_code == 200:
            pd = perf.json()
            print(f"    Agent: {pd['display_name']} | Period: {pd['period_days']}d")
            print(f"    Success rate: {pd['overall_success_rate']}% | Records: {pd['total_records_processed']}")
            print(f"    Data points: {len(pd['data_points'])}")

        # ── 15. Agent Hub Dashboard ──
        print("\n--- Agent Hub Dashboard ---")
        hub = await c.get(f"{BASE}/agent-hub/dashboard", headers=h)
        print(f"\n15. Hub dashboard: {hub.status_code}")
        if hub.status_code == 200:
            hb = hub.json()
            print(f"    Total agents: {hb['total_agents']} | Active: {hb['active_agents']}")
            print(f"    Runs 24h: {hb['total_runs_24h']} | 7d: {hb['total_runs_7d']}")
            print(f"    Success rate: {hb['overall_success_rate']}%")

        # ── 16. Demo Presets ──
        print("\n--- Demo Data Manager ---")
        presets = await c.get(f"{BASE}/admin/demo/presets", headers=h)
        print(f"\n16. Demo presets: {presets.status_code}")
        if presets.status_code == 200:
            pd = presets.json()
            print(f"    Total presets: {pd['total']}")
            for p in pd["presets"]:
                print(f"      [{p['preset_id']}] {p['name']} ({p['erp_profile']}, {p['dataset_size']})")

        # 17. Get specific preset
        preset = await c.get(f"{BASE}/admin/demo/presets/gcc_fmcg", headers=h)
        print(f"\n17. GCC FMCG preset: {preset.status_code}")
        if preset.status_code == 200:
            p = preset.json()
            print(f"    {p['name']}: {p['description'][:80]}...")
            print(f"    Params: {p['parameters']}")

        # 18. Demo data summary
        summary = await c.get(f"{BASE}/admin/demo/summary", headers=h)
        print(f"\n18. Data summary: {summary.status_code}")
        if summary.status_code == 200:
            sd = summary.json()
            print(f"    Customers: {sd['customers']} | Invoices: {sd['invoices']} | Payments: {sd['payments']}")
            print(f"    Disputes: {sd['disputes']} | Collections: {sd['collection_activities']}")
            print(f"    Total records: {sd['total_records']}")

        # ── Cross-feature ──
        print("\n--- Cross-Feature Verification ---")

        # 19. Executive dashboard still works
        exec_d = await c.get(f"{BASE}/executive/kpis", headers=h)
        print(f"\n19. Executive KPIs: {exec_d.status_code}")
        if exec_d.status_code == 200:
            print(f"    Cards: {len(exec_d.json()['cards'])}")

        # 20. Chat still works
        chat = await c.post(f"{BASE}/intelligence/chat", headers=h, json={
            "message": "How many agents are in the system?",
        })
        print(f"\n20. Chat: {chat.status_code}")
        if chat.status_code == 200:
            print(f"    Response: {chat.json()['message']['content'][:120]}...")

        print("\n" + "=" * 60)
        print("ALL DAY 18 TESTS COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
