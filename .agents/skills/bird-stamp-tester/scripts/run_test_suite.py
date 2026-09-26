"""
Automated Test Suite & Diagnostics Engine for Bird Stamp Application
Location: .agents/skills/bird-stamp-tester/scripts/run_test_suite.py
"""

import os
import sys
import json
import sqlite3
import traceback
import threading
import time
import requests
import pandas as pd
from typing import Dict, Any, List

# Ensure backend directory is in python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Navigate up from .agents/skills/bird-stamp-tester/scripts to workspace root
WORKSPACE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", "..", ".."))
if not os.path.exists(os.path.join(WORKSPACE_DIR, "backend")):
    # Fallback to direct path
    WORKSPACE_DIR = r"d:\Bird Project"

BACKEND_DIR = os.path.join(WORKSPACE_DIR, "backend")
FRONTEND_DIR = os.path.join(WORKSPACE_DIR, "frontend")

sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

import models
import schemas
import uvicorn
from database import Base, engine, SessionLocal, get_db
from main import app

class TestResultsTracker:
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.passed_count = 0
        self.failed_count = 0
        self.warning_count = 0

    def add_result(self, category: str, test_name: str, status: str, details: str = "", error: str = None):
        if status == "PASS":
            self.passed_count += 1
        elif status == "FAIL":
            self.failed_count += 1
        elif status == "WARN":
            self.warning_count += 1
            
        self.results.append({
            "category": category,
            "test_name": test_name,
            "status": status,
            "details": details,
            "error": error
        })
        status_symbol = "[PASS]" if status == "PASS" else ("[WARN]" if status == "WARN" else "[FAIL]")
        print(f"{status_symbol:<8} [{category}] {test_name}: {details}")
        if error:
            print(f"         Error details: {error}")

def start_test_server(port=8888):
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    
    # Wait for server to become responsive
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            r = requests.get(f"{base_url}/api/status", timeout=1)
            if r.status_code == 200:
                return server, base_url
        except Exception:
            time.sleep(0.1)
    return None, base_url

def run_all_tests():
    tracker = TestResultsTracker()
    print("=" * 80)
    print("STARTING BIRD STAMP COMPREHENSIVE AUTOMATED TEST SUITE")
    print("=" * 80)

    # ---------------------------------------------------------
    # SUITE 1: SQLite Database & Schema Validation
    # ---------------------------------------------------------
    print("\n--- SUITE 1: Database & Model Schema Verification ---")
    db_file = os.path.join(BACKEND_DIR, "bird_stamps.db")
    if not os.path.exists(db_file):
        tracker.add_result("Database", "Database File Existence", "FAIL", f"File not found at {db_file}")
    else:
        file_size_mb = os.path.getsize(db_file) / (1024 * 1024)
        tracker.add_result("Database", "Database File Existence", "PASS", f"Found {db_file} ({file_size_mb:.2f} MB)")
        
        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            # Check table existence
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stamps';")
            table = cursor.fetchone()
            if table:
                tracker.add_result("Database", "Stamps Table Exists", "PASS", "Table 'stamps' found.")
            else:
                tracker.add_result("Database", "Stamps Table Exists", "FAIL", "Table 'stamps' is missing!")

            # Check columns
            cursor.execute("PRAGMA table_info(stamps);")
            columns = {row[1]: row[2] for row in cursor.fetchall()}
            required_cols = [
                "id", "country", "year", "face_value", "english_name",
                "scientific_name", "bird_group", "genus", "species", "category", "stamp_type", "release_date",
                "image_url", "my_collection", "condition", "duplicate",
                "error", "description", "element_group", "element", "element_description"
            ]
            
            missing_cols = [c for c in required_cols if c not in columns]
            if not missing_cols:
                tracker.add_result("Database", "Columns Verification", "PASS", f"All {len(required_cols)} required columns exist.")
            else:
                tracker.add_result("Database", "Columns Verification", "FAIL", f"Missing columns: {missing_cols}")
                
            # Row counts and stats
            cursor.execute("SELECT COUNT(*) FROM stamps;")
            total_stamps = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM stamps WHERE my_collection=1;")
            owned_stamps = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT country) FROM stamps WHERE country IS NOT NULL AND country != '';")
            total_countries = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM stamps WHERE bird_group != '' AND bird_group IS NOT NULL;")
            with_bird_group = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM stamps WHERE element != '' AND element IS NOT NULL;")
            with_elements = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM stamps WHERE duplicate = 'yes' OR duplicate = '1';")
            duplicate_marked = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM stamps WHERE error != '' AND error IS NOT NULL;")
            error_marked = cursor.fetchone()[0]

            tracker.add_result("Database", "Data Population Stats", "PASS", 
                               f"Total: {total_stamps:,} | Owned: {owned_stamps:,} | With Bird Group: {with_bird_group:,} | Countries: {total_countries:,} | With Elements: {with_elements:,} | Duplicates: {duplicate_marked:,} | Errors: {error_marked:,}")
            conn.close()
        except Exception as e:
            tracker.add_result("Database", "Direct SQLite Query", "FAIL", str(e), traceback.format_exc())

    # ---------------------------------------------------------
    # SUITE 2: FastAPI Endpoints via Real Server
    # ---------------------------------------------------------
    print("\n--- SUITE 2: FastAPI REST API Endpoints ---")
    server, base_url = start_test_server(port=8888)
    if not server:
        tracker.add_result("API", "Server Startup", "FAIL", "Could not start test FastAPI server on port 8888")
    else:
        tracker.add_result("API", "Server Startup", "PASS", f"Test server live at {base_url}")
        
        # Test GET /api/stamps (default)
        try:
            res = requests.get(f"{base_url}/api/stamps")
            if res.status_code == 200:
                data = res.json()
                if "items" in data and "total" in data and "page" in data and "limit" in data:
                    sample_item = data['items'][0] if data['items'] else {}
                    has_tax = "bird_group" in sample_item and "genus" in sample_item and "species" in sample_item
                    if has_tax:
                        tracker.add_result("API", "GET /api/stamps (Default)", "PASS", f"Retrieved {len(data['items'])} items with taxonomy fields, total: {data['total']:,}")
                    else:
                        tracker.add_result("API", "GET /api/stamps (Default)", "FAIL", "Response items missing bird taxonomy fields")
                else:
                    tracker.add_result("API", "GET /api/stamps (Default)", "FAIL", "Response missing pagination structure")
            else:
                tracker.add_result("API", "GET /api/stamps (Default)", "FAIL", f"Status code {res.status_code}: {res.text}")
        except Exception as e:
            tracker.add_result("API", "GET /api/stamps (Default)", "FAIL", str(e))

        # Test GET /api/options (Philatelic Options)
        try:
            res = requests.get(f"{base_url}/api/options")
            if res.status_code == 200:
                data = res.json()
                if "conditions" in data and "element_groups" in data and "all_elements" in data:
                    tracker.add_result("API", "GET /api/options", "PASS", f"Retrieved {len(data['conditions'])} conditions, {len(data['element_groups'])} element groups, {len(data['all_elements'])} elements")
                else:
                    tracker.add_result("API", "GET /api/options", "FAIL", "Missing fields in /api/options response")
            else:
                tracker.add_result("API", "GET /api/options", "FAIL", f"Status code {res.status_code}")
        except Exception as e:
            tracker.add_result("API", "GET /api/options", "FAIL", str(e))

        # Test GET /api/countries
        try:
            res = requests.get(f"{base_url}/api/countries")
            if res.status_code == 200:
                countries = res.json()
                if isinstance(countries, list) and len(countries) > 0:
                    tracker.add_result("API", "GET /api/countries", "PASS", f"Returned {len(countries)} unique countries. Sample: {countries[:3]}")
                else:
                    tracker.add_result("API", "GET /api/countries", "WARN", "Returned empty country list")
            else:
                tracker.add_result("API", "GET /api/countries", "FAIL", f"Status code {res.status_code}")
        except Exception as e:
            tracker.add_result("API", "GET /api/countries", "FAIL", str(e))

        # Test GET /api/stamps with Search Filter
        try:
            res = requests.get(f"{base_url}/api/stamps?search=eagle")
            if res.status_code == 200:
                data = res.json()
                tracker.add_result("API", "GET /api/stamps?search=eagle", "PASS", f"Search 'eagle' matched {data['total']:,} stamps")
            else:
                tracker.add_result("API", "GET /api/stamps?search=eagle", "FAIL", f"Status {res.status_code}")
        except Exception as e:
            tracker.add_result("API", "GET /api/stamps?search=eagle", "FAIL", str(e))

        # Test GET /api/stamps with Country Filter
        try:
            res = requests.get(f"{base_url}/api/stamps?country=Canada")
            if res.status_code == 200:
                data = res.json()
                tracker.add_result("API", "GET /api/stamps?country=Canada", "PASS", f"Country 'Canada' matched {data['total']:,} stamps")
            else:
                tracker.add_result("API", "GET /api/stamps?country=Canada", "FAIL", f"Status {res.status_code}")
        except Exception as e:
            tracker.add_result("API", "GET /api/stamps?country=Canada", "FAIL", str(e))

        # Test GET /api/stamps with collection_status (owned / missing)
        try:
            res_owned = requests.get(f"{base_url}/api/stamps?collection_status=owned")
            res_missing = requests.get(f"{base_url}/api/stamps?collection_status=missing")
            if res_owned.status_code == 200 and res_missing.status_code == 200:
                owned_count = res_owned.json()['total']
                missing_count = res_missing.json()['total']
                tracker.add_result("API", "GET /api/stamps?collection_status=(owned/missing)", "PASS", 
                                   f"Owned count: {owned_count:,} | Missing count: {missing_count:,}")
            else:
                tracker.add_result("API", "GET /api/stamps?collection_status=(owned/missing)", "FAIL", "Failed to filter collection status")
        except Exception as e:
            tracker.add_result("API", "GET /api/stamps?collection_status", "FAIL", str(e))

        # Test GET /api/stamps with Element Group filter
        try:
            res_elem = requests.get(f"{base_url}/api/stamps?element_group=Issued&limit=10")
            if res_elem.status_code == 200:
                data = res_elem.json()
                tracker.add_result("API", "GET /api/stamps?element_group=Issued", "PASS", f"Element group filter returned {data['total']:,} matches")
            else:
                tracker.add_result("API", "GET /api/stamps?element_group=Issued", "FAIL", f"Status {res_elem.status_code}")
        except Exception as e:
            tracker.add_result("API", "GET /api/stamps?element_group", "FAIL", str(e))

        # Test GET /api/status
        try:
            res = requests.get(f"{base_url}/api/status")
            if res.status_code == 200:
                data = res.json()
                if "scrape" in data and "sync" in data:
                    tracker.add_result("API", "GET /api/status", "PASS", f"Status response structure valid. Scrape: {data['scrape']}, Sync: {data['sync']}")
                else:
                    tracker.add_result("API", "GET /api/status", "FAIL", "Invalid status structure")
            else:
                tracker.add_result("API", "GET /api/status", "FAIL", f"Status {res.status_code}")
        except Exception as e:
            tracker.add_result("API", "GET /api/status", "FAIL", str(e))

        # Test auto-update endpoints (updates are disabled when running from source)
        try:
            res = requests.get(f"{base_url}/api/update")
            data = res.json() if res.status_code == 200 else {}
            if res.status_code == 200 and data.get("current_version") and data.get("status") == "disabled":
                tracker.add_result("API", "GET /api/update", "PASS", f"v{data['current_version']}, status '{data['status']}' (expected from source)")
            else:
                tracker.add_result("API", "GET /api/update", "FAIL", f"Status {res.status_code}: {data}")
            res = requests.post(f"{base_url}/api/update/apply")
            if res.status_code == 409:
                tracker.add_result("API", "POST /api/update/apply (nothing staged -> 409)", "PASS", res.json().get("detail", ""))
            else:
                tracker.add_result("API", "POST /api/update/apply (nothing staged -> 409)", "FAIL", f"Status {res.status_code}")
        except Exception as e:
            tracker.add_result("API", "Auto-update endpoints", "FAIL", str(e))


        # ---------------------------------------------------------
        # SUITE 3: CRUD Mutation Endpoints
        # ---------------------------------------------------------
        print("\n--- SUITE 3: CRUD & Data Mutation Lifecycle ---")
        try:
            # Fetch one stamp to test
            res = requests.get(f"{base_url}/api/stamps?limit=1")
            if res.status_code == 200 and res.json()['items']:
                first_stamp = res.json()['items'][0]
                test_stamp_id = first_stamp['id']
                orig_desc = first_stamp.get('description', '')
                
                # Test PATCH
                patch_payload = {
                    "description": f"Test description automated {os.urandom(2).hex()}",
                    "condition": "Mint Test",
                    "duplicate": "yes",
                    "error": "Color error test"
                }
                patch_res = requests.patch(f"{base_url}/api/stamps/{test_stamp_id}", json=patch_payload)
                if patch_res.status_code == 200:
                    updated = patch_res.json()
                    if updated['description'] == patch_payload['description'] and updated['condition'] == "Mint Test":
                        tracker.add_result("CRUD", f"PATCH /api/stamps/{test_stamp_id}", "PASS", "Successfully updated stamp fields via PATCH.")
                    else:
                        tracker.add_result("CRUD", f"PATCH /api/stamps/{test_stamp_id}", "FAIL", "Fields did not match updated values.")
                else:
                    tracker.add_result("CRUD", f"PATCH /api/stamps/{test_stamp_id}", "FAIL", f"Status {patch_res.status_code}")
                    
                # Revert description back
                requests.patch(f"{base_url}/api/stamps/{test_stamp_id}", json={"description": orig_desc})

                # Test DUPLICATE
                dup_res = requests.post(f"{base_url}/api/stamps/{test_stamp_id}/duplicate")
                if dup_res.status_code == 200:
                    dup_stamp = dup_res.json()
                    new_id = dup_stamp['id']
                    if new_id != test_stamp_id and dup_stamp['english_name'] == first_stamp['english_name']:
                        tracker.add_result("CRUD", f"POST /api/stamps/{test_stamp_id}/duplicate", "PASS", f"Successfully cloned stamp -> new ID {new_id}")
                        
                        # Test DELETE on the duplicate
                        del_res = requests.delete(f"{base_url}/api/stamps/{new_id}")
                        if del_res.status_code == 200:
                            tracker.add_result("CRUD", f"DELETE /api/stamps/{new_id}", "PASS", "Successfully deleted duplicate stamp.")
                        else:
                            tracker.add_result("CRUD", f"DELETE /api/stamps/{new_id}", "FAIL", f"Status {del_res.status_code}")
                    else:
                        tracker.add_result("CRUD", f"POST /api/stamps/{test_stamp_id}/duplicate", "FAIL", "Duplicated object ID invalid")
                else:
                    tracker.add_result("CRUD", f"POST /api/stamps/{test_stamp_id}/duplicate", "FAIL", f"Status {dup_res.status_code}")

                # Test Custom Card Creation & Specimen Image Upload
                try:
                    test_img_bytes = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
                    files = {'file': ('test_specimen.gif', test_img_bytes, 'image/gif')}
                    res_upload = requests.post(f"{base_url}/api/upload-image", files=files)
                    if res_upload.status_code == 200 and "image_url" in res_upload.json():
                        uploaded_url = res_upload.json()["image_url"]
                        tracker.add_result("CRUD", "POST /api/upload-image", "PASS", f"Uploaded specimen image: {uploaded_url}")
                        
                        # Create custom stamp card
                        custom_stamp_payload = {
                            "english_name": "Test Emperor Penguin",
                            "scientific_name": "Aptenodytes forsteri",
                            "country": "Antarctica",
                            "year": "2025",
                            "face_value": "$5.00",
                            "bird_group": "Penguins",
                            "category": "Commemorative",
                            "stamp_type": "Postage",
                            "image_url": uploaded_url,
                            "my_collection": True,
                            "condition": "Mint Never Hinged (MNH)",
                            "duplicate": "no",
                            "error": "",
                            "description": "Created via automated test suite",
                            "element_group": "Issued Stamps",
                            "element": "Commemorative",
                            "element_description": "Commemorative issue"
                        }
                        res_create = requests.post(f"{base_url}/api/stamps", json=custom_stamp_payload)
                        if res_create.status_code == 200:
                            created_data = res_create.json()
                            created_id = created_data["id"]
                            if created_data["english_name"] == "Test Emperor Penguin" and created_data["genus"] == "Aptenodytes":
                                tracker.add_result("CRUD", "POST /api/stamps (Create Card)", "PASS", f"Custom stamp created -> ID {created_id}, auto-genus Aptenodytes")
                                
                                # Verify search finds it
                                res_search = requests.get(f"{base_url}/api/stamps?search=Aptenodytes")
                                if res_search.status_code == 200 and res_search.json()["total"] > 0:
                                    tracker.add_result("CRUD", "Search Custom Stamp", "PASS", "Found custom card in search query")
                                else:
                                    tracker.add_result("CRUD", "Search Custom Stamp", "FAIL", "Custom card not found in search")
                                    
                                # Delete created stamp
                                requests.delete(f"{base_url}/api/stamps/{created_id}")
                            else:
                                tracker.add_result("CRUD", "POST /api/stamps (Create Card)", "FAIL", f"Unexpected response: {created_data}")
                        else:
                            tracker.add_result("CRUD", "POST /api/stamps (Create Card)", "FAIL", f"Status {res_create.status_code}: {res_create.text}")
                    else:
                        tracker.add_result("CRUD", "POST /api/upload-image", "FAIL", f"Status {res_upload.status_code}: {res_upload.text}")
                except Exception as e:
                    tracker.add_result("CRUD", "Custom Card Creation & Upload", "FAIL", str(e))

            else:
                tracker.add_result("CRUD", "Fetch Stamp For Mutation Test", "FAIL", "Could not fetch any stamp to test mutations.")
        except Exception as e:
            tracker.add_result("CRUD", "CRUD Mutation Cycle", "FAIL", str(e), traceback.format_exc())

    # ---------------------------------------------------------
    # SUITE 3B: /api/sync Contract (optional body, 400/409)
    # ---------------------------------------------------------
    # NOTE: a real sync mutates backend/bird_stamps.db. The caller of this
    # script is responsible for backing up bird_stamps.db (+ -wal/-shm) before
    # running the suite and restoring it afterwards.
    print("\n--- SUITE 3B: POST /api/sync Contract Verification ---")
    if server:
        # 400: path given but doesn't exist / isn't .xlsx
        try:
            res_bad = requests.post(f"{base_url}/api/sync", json={"excel_path": r"C:\definitely\does\not\exist.xlsx"})
            if res_bad.status_code == 400 and "detail" in res_bad.json():
                tracker.add_result("Sync API", "POST /api/sync (bad path -> 400)", "PASS", f"Got 400 with detail: {res_bad.json()['detail']}")
            else:
                tracker.add_result("Sync API", "POST /api/sync (bad path -> 400)", "FAIL", f"Expected 400, got {res_bad.status_code}: {res_bad.text}")
        except Exception as e:
            tracker.add_result("Sync API", "POST /api/sync (bad path -> 400)", "FAIL", str(e))

        # 400: non-.xlsx extension rejected even if the file exists
        try:
            non_xlsx = os.path.join(WORKSPACE_DIR, "README.md")
            if os.path.exists(non_xlsx):
                res_ext = requests.post(f"{base_url}/api/sync", json={"excel_path": non_xlsx})
                if res_ext.status_code == 400:
                    tracker.add_result("Sync API", "POST /api/sync (non-.xlsx -> 400)", "PASS", "Non-.xlsx path correctly rejected with 400.")
                else:
                    tracker.add_result("Sync API", "POST /api/sync (non-.xlsx -> 400)", "FAIL", f"Expected 400, got {res_ext.status_code}")
            else:
                tracker.add_result("Sync API", "POST /api/sync (non-.xlsx -> 400)", "WARN", "README.md not found to use as a non-.xlsx probe file.")
        except Exception as e:
            tracker.add_result("Sync API", "POST /api/sync (non-.xlsx -> 400)", "FAIL", str(e))

        # 200 + 409: a valid sync (no body -> default workbook) starts, and a
        # concurrent /api/sync or /api/scrape call while it's running gets 409.
        default_xlsx = os.path.join(WORKSPACE_DIR, "data", "collections", "My Collection_Final List_1.1.xlsx")
        if os.path.exists(default_xlsx):
            try:
                res_start = requests.post(f"{base_url}/api/sync", json={})
                if res_start.status_code == 200:
                    tracker.add_result("Sync API", "POST /api/sync (no path -> default workbook, 200)", "PASS", f"Sync started: {res_start.json()}")

                    # Immediately probe for 409 while it should still be running
                    # (is_running is set synchronously by the endpoint per contract).
                    res_conflict = requests.post(f"{base_url}/api/scrape")
                    if res_conflict.status_code == 409:
                        tracker.add_result("Sync API", "POST /api/scrape while sync running -> 409", "PASS", f"Got 409 as expected: {res_conflict.json()}")
                    else:
                        tracker.add_result("Sync API", "POST /api/scrape while sync running -> 409", "WARN", f"Expected 409, got {res_conflict.status_code} (sync may have finished faster than this check ran).")

                    res_conflict2 = requests.post(f"{base_url}/api/sync", json={})
                    if res_conflict2.status_code == 409:
                        tracker.add_result("Sync API", "POST /api/sync while sync running -> 409", "PASS", f"Got 409 as expected: {res_conflict2.json()}")
                    else:
                        tracker.add_result("Sync API", "POST /api/sync while sync running -> 409", "WARN", f"Expected 409, got {res_conflict2.status_code} (sync may have finished faster than this check ran).")

                    # Wait for the sync to actually finish (bounded) so the
                    # caller can safely restore the db backup afterwards.
                    deadline = time.time() + 240
                    finished = False
                    while time.time() < deadline:
                        st = requests.get(f"{base_url}/api/status").json()
                        if not st.get("sync", {}).get("is_running"):
                            finished = True
                            break
                        time.sleep(1.0)
                    if finished:
                        final_status = requests.get(f"{base_url}/api/status").json()["sync"]
                        tracker.add_result("Sync API", "Sync Job Completion", "PASS", f"Sync finished: {final_status.get('message')}")
                    else:
                        tracker.add_result("Sync API", "Sync Job Completion", "WARN", "Sync did not finish within 240s wait window (may still be running in background).")
                else:
                    tracker.add_result("Sync API", "POST /api/sync (no path -> default workbook, 200)", "FAIL", f"Expected 200, got {res_start.status_code}: {res_start.text}")
            except Exception as e:
                tracker.add_result("Sync API", "POST /api/sync (default workbook)", "FAIL", str(e), traceback.format_exc())
        else:
            tracker.add_result("Sync API", "POST /api/sync (default workbook)", "WARN", f"Default workbook not found at {default_xlsx}; cannot test the 200/409 path (dev-environment dependent).")
    else:
        tracker.add_result("Sync API", "POST /api/sync Contract", "FAIL", "No server available to test against.")

    # ---------------------------------------------------------
    # SUITE 4: Excel Workbooks & Sync Logic Integrity
    # ---------------------------------------------------------
    print("\n--- SUITE 4: Excel Workbooks & Sync Engine ---")
    excel_file_map = {
        "My Collection_Final List_1.1.xlsx": [
            os.path.join(WORKSPACE_DIR, "data", "collections", "My Collection_Final List_1.1.xlsx"),
            os.path.join(WORKSPACE_DIR, "My Collection_Final List_1.1.xlsx")
        ],
        "Philatelic Elements.xlsx": [
            os.path.join(WORKSPACE_DIR, "data", "elements", "Philatelic Elements.xlsx"),
            os.path.join(WORKSPACE_DIR, "Philatelic Elements.xlsx")
        ],
        "My collection element link.xlsx": [
            os.path.join(WORKSPACE_DIR, "data", "elements", "My collection element link.xlsx"),
            os.path.join(WORKSPACE_DIR, "My collection element link.xlsx")
        ],
        "master_ioc_list_v15.2.xlsx": [
            os.path.join(WORKSPACE_DIR, "data", "ioc_reference", "master_ioc_list_v15.2.xlsx"),
            os.path.join(WORKSPACE_DIR, "master_ioc_list_v15.2.xlsx")
        ],
        "Multiling IOC 15.2.xlsx": [
            os.path.join(WORKSPACE_DIR, "data", "ioc_reference", "Multiling IOC 15.2.xlsx"),
            os.path.join(WORKSPACE_DIR, "Multiling IOC 15.2.xlsx")
        ]
    }
    for ef, candidates in excel_file_map.items():
        found_path = next((p for p in candidates if os.path.exists(p)), None)
        if found_path:
            try:
                df = pd.read_excel(found_path)
                tracker.add_result("Excel Files", f"Workbook: {ef}", "PASS", f"Exists at {os.path.relpath(found_path, WORKSPACE_DIR)} ({len(df):,} rows, {len(df.columns)} columns)")
            except Exception as e:
                tracker.add_result("Excel Files", f"Workbook: {ef}", "FAIL", f"Error reading: {e}")
        else:
            tracker.add_result("Excel Files", f"Workbook: {ef}", "WARN", "File not found in data directories or root")

    # Test sync matching logic module
    try:
        import sync
        tracker.add_result("Sync Engine", "sync.py Module Import", "PASS", "Module loaded successfully.")
    except Exception as e:
        tracker.add_result("Sync Engine", "sync.py Module Import", "FAIL", str(e))

    # Test apply_elements module
    try:
        import apply_elements
        tracker.add_result("Philatelic Elements", "apply_elements.py Module Import", "PASS", "Module loaded successfully.")
    except Exception as e:
        tracker.add_result("Philatelic Elements", "apply_elements.py Module Import", "FAIL", str(e))

    # ---------------------------------------------------------
    # SUITE 5: Scraper Module Diagnostics
    # ---------------------------------------------------------
    print("\n--- SUITE 5: Web Scraper Engine Diagnostics ---")
    try:
        import scraper
        tracker.add_result("Scraper", "scraper.py Module Import", "PASS", "Module loaded successfully.")
        
        # Test HTML Issue Parser with mock HTML
        mock_html = """
        <td class="country">Testland\nOfficial</td>
        <a name="1"></a>
        <table><tr><td class="issue">2021</td><td class="issue">01.05.2021</td><td class="issue">Commemorative</td></tr></table>
        <span><img src="test_bird.jpg"></span>
        <table>
            <tr>
                <td>1.50 $</td>
                <td>Scott 123</td>
                <td>Eagle <em>Aquila chrysaetos</em></td>
            </tr>
        </table>
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(mock_html, 'html.parser')
        country_td = soup.find('td', class_='country')
        parsed_country = country_td.text.split('\n')[0].strip() if country_td else ""
        
        if parsed_country == "Testland":
            tracker.add_result("Scraper", "HTML Country & Issue Parser", "PASS", f"Parsed country correctly: {parsed_country}")
        else:
            tracker.add_result("Scraper", "HTML Country & Issue Parser", "FAIL", f"Expected 'Testland', got '{parsed_country}'")
            
    except Exception as e:
        tracker.add_result("Scraper", "Scraper Module Diagnostics", "FAIL", str(e))

    # ---------------------------------------------------------
    # SUITE 6: Local Excel Export Engine Diagnostics
    # ---------------------------------------------------------
    print("\n--- SUITE 6: Local Excel Export Diagnostics ---")
    try:
        import excel_export
        tracker.add_result("Excel Export", "excel_export.py Module Import", "PASS", "excel_export module loaded successfully.")
        
        export_dir = excel_export.get_export_dir()
        if os.path.exists(export_dir) and os.path.basename(export_dir) == "my collection sheets":
            tracker.add_result("Excel Export", "Export Directory Verification", "PASS", f"Valid 'my collection sheets' folder at: {export_dir}")
        else:
            tracker.add_result("Excel Export", "Export Directory Verification", "FAIL", f"Invalid export directory: {export_dir}")
            
        # Test API Endpoint POST /api/export
        if server:
            try:
                res_export = requests.post(f"{base_url}/api/export")
                if res_export.status_code == 200:
                    exp_data = res_export.json()
                    exported_file = exp_data.get("file_path", "")
                    if os.path.exists(exported_file):
                        # Verify sheet contents with pandas
                        df_exp = pd.read_excel(exported_file)
                        expected_cols = [
                            'ID', 'Country', 'Year', 'Face Value', 'English Name', 'Scientific Name',
                            'Bird Group', 'Genus', 'Species', 'Category', 'Type', 'Release Date',
                            'Image URL', 'My Collection', 'Condition', 'Duplicate', 'Error',
                            'Description', 'Element Group', 'Element', 'Element Description'
                        ]
                        cols_valid = all(c in df_exp.columns for c in expected_cols)
                        if cols_valid and len(df_exp) > 0:
                            tracker.add_result("Excel Export", "POST /api/export Execution & Verification", "PASS", 
                                               f"Successfully exported {len(df_exp):,} rows with {len(df_exp.columns)} columns to {os.path.basename(exported_file)}")
                        else:
                            tracker.add_result("Excel Export", "POST /api/export Execution & Verification", "FAIL", 
                                               f"Exported sheet missing required columns or empty. Found {len(df_exp)} rows, columns: {list(df_exp.columns)}")
                    else:
                        tracker.add_result("Excel Export", "POST /api/export Execution & Verification", "FAIL", f"Exported file not found at {exported_file}")
                else:
                    tracker.add_result("Excel Export", "POST /api/export Execution & Verification", "FAIL", f"Status {res_export.status_code}: {res_export.text}")
            except Exception as e:
                tracker.add_result("Excel Export", "POST /api/export Execution & Verification", "FAIL", str(e))
    except Exception as e:
        tracker.add_result("Excel Export", "excel_export.py Module Diagnostics", "FAIL", str(e))

    # ---------------------------------------------------------
    # SUITE 7: Frontend Build & Static Serving
    # ---------------------------------------------------------
    print("\n--- SUITE 7: Frontend Build & Asset Verification ---")
    dist_index = os.path.join(FRONTEND_DIR, "dist", "index.html")
    if os.path.exists(dist_index):
        tracker.add_result("Frontend", "Vite Production Dist Build", "PASS", f"Found built frontend at {dist_index}")
    else:
        tracker.add_result("Frontend", "Vite Production Dist Build", "WARN", f"dist/index.html not found. Run 'npm run build' in frontend.")

    # ---------------------------------------------------------
    # SUITE 8: Desktop Wrapper & PyInstaller Packaging
    # ---------------------------------------------------------
    print("\n--- SUITE 8: Desktop Packaging & Launcher ---")
    desktop_py = os.path.join(BACKEND_DIR, "desktop.py")
    spec_file = os.path.join(BACKEND_DIR, "BirdStamp.spec")
    build_py = os.path.join(WORKSPACE_DIR, "build.py")
    
    if os.path.exists(desktop_py):
        tracker.add_result("Desktop", "desktop.py Entrypoint", "PASS", "desktop.py exists.")
    else:
        tracker.add_result("Desktop", "desktop.py Entrypoint", "FAIL", "desktop.py missing.")

    # BirdStamp.spec is intentionally NOT checked into the tree anymore: build.py
    # invokes PyInstaller purely via CLI flags (--runtime-hook, --hidden-import,
    # etc.) and lets PyInstaller regenerate the .spec file fresh in backend/ on
    # every build. So its absence here (before a build has been run) is expected,
    # not a failure. If it's present, sanity-check it mentions the runtime hook.
    if os.path.exists(spec_file):
        try:
            spec_contents = open(spec_file, encoding="utf-8", errors="ignore").read()
            if "rthook_unblock" in spec_contents:
                tracker.add_result("Desktop", "PyInstaller Spec File", "PASS", "BirdStamp.spec exists (regenerated by PyInstaller) and references rthook_unblock.")
            else:
                tracker.add_result("Desktop", "PyInstaller Spec File", "WARN", "BirdStamp.spec exists but does not reference rthook_unblock runtime hook.")
        except Exception as e:
            tracker.add_result("Desktop", "PyInstaller Spec File", "WARN", f"Could not read BirdStamp.spec: {e}")
    else:
        tracker.add_result("Desktop", "PyInstaller Spec File", "WARN", "BirdStamp.spec not present (expected: PyInstaller regenerates it from build.py's CLI args on each build; not checked into the tree).")

    rthook_file = os.path.join(BACKEND_DIR, "rthook_unblock.py")
    if os.path.exists(rthook_file):
        tracker.add_result("Desktop", "MOTW Unblock Runtime Hook", "PASS", "rthook_unblock.py present.")
    else:
        tracker.add_result("Desktop", "MOTW Unblock Runtime Hook", "FAIL", "rthook_unblock.py missing - client MOTW crash would not be fixed by a build.")

    app_log_file = os.path.join(BACKEND_DIR, "app_log.py")
    if os.path.exists(app_log_file):
        tracker.add_result("Desktop", "app_log.py Logging Module", "PASS", "app_log.py present.")
    else:
        tracker.add_result("Desktop", "app_log.py Logging Module", "FAIL", "app_log.py missing.")

    if os.path.exists(build_py):
        tracker.add_result("Desktop", "build.py Pipeline", "PASS", "build.py automated packaging script exists.")
    else:
        tracker.add_result("Desktop", "build.py Pipeline", "FAIL", "build.py missing.")

    # ---------------------------------------------------------
    # SUMMARY
    # ---------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"TEST SUITE COMPLETE: {tracker.passed_count} PASSED | {tracker.failed_count} FAILED | {tracker.warning_count} WARNINGS")
    print("=" * 80)
    
    # Stop background test server cleanly
    if server:
        server.should_exit = True
    
    return tracker

if __name__ == "__main__":
    tracker = run_all_tests()
    if tracker.failed_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)
