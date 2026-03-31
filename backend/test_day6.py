"""Day 6 - CSV Import End-to-End Test"""
import asyncio, httpx, json

BASE = "http://localhost:8000/api/v1"

CUSTOMER_CSV = """Company Name,Arabic Name,Code,Industry,Territory,Country,City,Phone,Email,Credit Limit,Payment Terms
Al Khaleej Steel LLC,الخليج للحديد,CUS-5001,Manufacturing,Dubai,AE,Dubai,+971-4-888-1234,finance@alkhaleejsteel.ae,750000,45
Desert Rose Trading,وردة الصحراء للتجارة,CUS-5002,FMCG,Abu Dhabi,AE,Abu Dhabi,02-555-6789,ar@desertrose.ae,200000,30
Nakheel Supplies FZCO,,CUS-5003,Construction Materials,Sharjah,AE,Sharjah,06-444-5555,billing@nakheelsupplies.ae,350000,60
Gulf Star Logistics,,CUS-5004,Services,Dubai,UAE,Dubai,,admin@gulfstar.ae,,30
Riyadh Wholesale Co,الرياض للجملة,CUS-5005,FMCG,Central,SA,Riyadh,+966-11-234-5678,finance@riyadhwholesale.sa,500000,45
"""

INVOICE_CSV = """Invoice No,Customer Code,Invoice Date,Due Date,Amount,Tax,Currency,PO Number,Notes
INV-CSV-001,CUS-5001,2026-01-15,2026-02-28,120000,6000,AED,PO-8801,Q1 Steel order
INV-CSV-002,CUS-5001,2026-02-01,2026-03-15,85000,4250,AED,PO-8802,Rebar delivery
INV-CSV-003,CUS-5002,15/01/2026,28/02/2026,45000,2250,AED,,FMCG monthly
INV-CSV-004,CUS-5003,2026-01-20,2026-03-20,200000,10000,AED,PO-9901,Cement batch
INV-CSV-005,CUS-5005,2026-02-10,2026-04-10,175000,26250,SAR,,KSA shipment
"""

PAYMENT_CSV = """Customer Code,Payment Date,Amount,Currency,Method,Reference,Bank Ref,Against Invoice
CUS-5001,2026-03-01,126000,AED,bank_transfer,TRF-90001,BNK-X001,INV-CSV-001
CUS-5002,2026-03-05,20000,AED,check,CHQ-70001,,INV-CSV-003
CUS-5003,2026-03-10,100000,AED,bank_transfer,TRF-90002,BNK-X002,INV-CSV-004
"""


async def main():
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{BASE}/auth/login", json={"email": "admin@salesiq.ai", "password": "Admin@2024", "tenant_slug": "demo"})
        tok = r.json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        print("=== Login OK ===")

        # 1. Get importable fields
        print("\n=== Importable Fields (customers) ===")
        fields = await c.get(f"{BASE}/import/fields/customers", headers=h)
        print(f"Status: {fields.status_code}")
        if fields.status_code == 200:
            fd = fields.json()
            print(f"Required: {fd['required_fields']}")
            print(f"Total fields: {len(fd['fields'])}")

        # 2. Upload & auto-map customers
        print("\n=== Upload & Auto-Map Customers ===")
        upload = await c.post(
            f"{BASE}/import/upload-and-map",
            headers=h,
            data={"entity_type": "customers"},
            files={"file": ("customers.csv", CUSTOMER_CSV.encode(), "text/csv")},
        )
        print(f"Status: {upload.status_code}")
        customer_csv_content = None
        customer_mapping = None
        if upload.status_code == 200:
            ud = upload.json()
            print(f"Headers: {ud['headers']}")
            print(f"Auto mapping: {json.dumps(ud['auto_mapping'], indent=2)}")
            print(f"Unmapped: {ud['unmapped_headers']}")
            print(f"Total rows: {ud['total_rows']}")
            customer_csv_content = ud["csv_content"]
            customer_mapping = ud["auto_mapping"]
        else:
            print("ERROR:", upload.text[:500])
            return

        # 3. Preview
        print("\n=== Preview Customer Import ===")
        preview = await c.post(f"{BASE}/import/preview", headers=h, json={
            "entity_type": "customers",
            "csv_content": customer_csv_content,
            "mapping": customer_mapping,
        })
        print(f"Status: {preview.status_code}")
        if preview.status_code == 200:
            pd = preview.json()
            print(f"Can import: {pd['can_import']}")
            print(f"Missing required: {pd['missing_required_fields']}")
            print(f"Errors: {len(pd['errors'])}")
            for pr in pd["preview_rows"][:3]:
                print(f"  Row {pr['row_number']}: {pr['parsed'].get('name', '')} | errors: {len(pr['errors'])}")

        # 4. Execute customer import
        print("\n=== Execute Customer Import ===")
        exe = await c.post(f"{BASE}/import/execute", headers=h, json={
            "entity_type": "customers",
            "csv_content": customer_csv_content,
            "mapping": customer_mapping,
            "skip_preview": True,
        })
        print(f"Status: {exe.status_code}")
        if exe.status_code == 201:
            ed = exe.json()
            print(f"Created: {ed['created']} | Updated: {ed['updated']} | Skipped: {ed['skipped']}")
            if ed["errors"]:
                print(f"Errors: {ed['errors']}")
        else:
            print("ERROR:", exe.text[:500])

        # 5. Invoice import
        print("\n=== Upload & Import Invoices ===")
        inv_upload = await c.post(
            f"{BASE}/import/upload-and-map",
            headers=h,
            data={"entity_type": "invoices"},
            files={"file": ("invoices.csv", INVOICE_CSV.encode(), "text/csv")},
        )
        inv_exe = None
        if inv_upload.status_code == 200:
            ivd = inv_upload.json()
            print(f"Auto mapping: {json.dumps(ivd['auto_mapping'])}")
            inv_exe = await c.post(f"{BASE}/import/execute", headers=h, json={
                "entity_type": "invoices",
                "csv_content": ivd["csv_content"],
                "mapping": ivd["auto_mapping"],
                "skip_preview": True,
            })
            print(f"Import status: {inv_exe.status_code}")
            if inv_exe.status_code == 201:
                ied = inv_exe.json()
                print(f"Created: {ied['created']} | Skipped: {ied['skipped']}")
                if ied["errors"]:
                    for e in ied["errors"]:
                        print(f"  {e}")
            else:
                print("ERROR:", inv_exe.text[:500])
        else:
            print("ERROR:", inv_upload.text[:500])

        # 6. Payment import
        print("\n=== Upload & Import Payments ===")
        pmt_upload = await c.post(
            f"{BASE}/import/upload-and-map",
            headers=h,
            data={"entity_type": "payments"},
            files={"file": ("payments.csv", PAYMENT_CSV.encode(), "text/csv")},
        )
        pmt_exe = None
        if pmt_upload.status_code == 200:
            pmd = pmt_upload.json()
            print(f"Auto mapping: {json.dumps(pmd['auto_mapping'])}")
            pmt_exe = await c.post(f"{BASE}/import/execute", headers=h, json={
                "entity_type": "payments",
                "csv_content": pmd["csv_content"],
                "mapping": pmd["auto_mapping"],
                "skip_preview": True,
            })
            print(f"Import status: {pmt_exe.status_code}")
            if pmt_exe.status_code == 201:
                ped = pmt_exe.json()
                print(f"Created: {ped['created']} | Matched: {ped.get('matched', 0)} | Skipped: {ped['skipped']}")
                if ped["errors"]:
                    for e in ped["errors"]:
                        print(f"  {e}")
            else:
                print("ERROR:", pmt_exe.text[:500])
        else:
            print("ERROR:", pmt_upload.text[:500])

        # 7. Verify imported data
        print("\n=== Verify Imported Data ===")
        custs = await c.get(f"{BASE}/customers/?search=khaleej", headers=h)
        if custs.status_code == 200:
            cd = custs.json()
            print(f'Search "khaleej": {cd["total"]} found')
            if cd["items"]:
                ci = cd["items"][0]
                print(f"  {ci['name']} | {ci['industry']} | credit={ci['credit_limit']} | ext_id={ci.get('external_id')}")

        # 8. Import history
        print("\n=== Import History ===")
        hist = await c.get(f"{BASE}/import/history", headers=h)
        if hist.status_code == 200:
            hd = hist.json()
            print(f"Total imports: {hd['total']}")
            for item in hd["items"]:
                print(f"  {item['entity_type']} | {item['result']}")

        # 9. RBAC
        print()
        r2 = await c.post(f"{BASE}/auth/login", json={"email": "sales@salesiq.ai", "password": "Sales@2024!", "tenant_slug": "demo"})
        h2 = {"Authorization": f"Bearer {r2.json()['access_token']}"}
        rbac = await c.post(
            f"{BASE}/import/upload-and-map",
            headers=h2,
            data={"entity_type": "customers"},
            files={"file": ("test.csv", b"name\nTest", "text/csv")},
        )
        print(f"RBAC (sales_rep -> upload): {rbac.status_code} (expect 403)")

        print()
        all_pass = all([
            fields.status_code == 200,
            upload.status_code == 200,
            preview.status_code == 200,
            exe.status_code == 201,
            inv_exe is not None and inv_exe.status_code == 201,
            pmt_exe is not None and pmt_exe.status_code == 201,
            hist.status_code == 200,
            rbac.status_code == 403,
        ])
        print("=== ALL DAY 6 TESTS PASSED ===" if all_pass else "=== SOME TESTS FAILED ===")


asyncio.run(main())
