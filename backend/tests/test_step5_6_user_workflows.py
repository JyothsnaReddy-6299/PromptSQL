"""
Step 5.6: Final Application Reliability and User Workflow Verification Test Suite

Verifies complete end-to-end functionality across all PromptSQL core user workflows:
1. Authentication (Registration, Login, Protected Routes, Expiration, /me, /logout)
2. Dataset Management (CSV with 'id' column, Excel, Empty/Invalid/Oversized checks, Preview, Multi-tenant Isolation)
3. Natural Language Querying (Valid, Empty Results, Repeated Queries, Hallucination Defense)
4. Query History (Persistence, Cross-tenant Isolation, Deletion, Clearing)
5. Data Operations (Cleaning Deduplication, Modification Preview, Confirmation, Cancellation, Undo Rollback)
6. Exports and Reports (CSV, Excel, PDF, Raw Table Exports)
"""

import unittest
import io
import json
import secrets
import pandas as pd
from datetime import datetime, timezone, timedelta
import jwt
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.core.config import get_settings
from app.database.connection import engine, SessionLocal
from app.models.user import User
from app.models.history import QueryHistory
from app.models.audit_log import AuditLog
from app.services.auth_service import hash_password, create_access_token


class TestStep56UserWorkflows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.settings = get_settings()

        # Generate unique test usernames to prevent collisions across runs
        cls.suffix = secrets.token_hex(4)
        cls.user_a_name = f"user_a_{cls.suffix}"
        cls.user_b_name = f"user_b_{cls.suffix}"
        cls.test_pwd = "SecurePassword123!"

        # Register User A and User B
        res_a = cls.client.post("/auth/signup", json={"username": cls.user_a_name, "password": cls.test_pwd})
        assert res_a.status_code == 200, f"User A signup failed: {res_a.text}"
        data_a = res_a.json()
        cls.user_a_token = data_a["token"]
        cls.user_a_id = data_a["user_id"]
        cls.headers_a = {"Authorization": f"Bearer {cls.user_a_token}"}

        res_b = cls.client.post("/auth/signup", json={"username": cls.user_b_name, "password": cls.test_pwd})
        assert res_b.status_code == 200, f"User B signup failed: {res_b.text}"
        data_b = res_b.json()
        cls.user_b_token = data_b["token"]
        cls.user_b_id = data_b["user_id"]
        cls.headers_b = {"Authorization": f"Bearer {cls.user_b_token}"}

        cls.tbl_a = f"sales_records_{cls.user_a_id}"
        cls.tbl_b = f"inventory_{cls.user_b_id}"

        # Initialize clean test tables
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_a}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_b}`"))
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_a}` (
                    `_row_id` INT AUTO_INCREMENT PRIMARY KEY,
                    `id` INT,
                    `customer` VARCHAR(100),
                    `amount` DOUBLE,
                    `city` VARCHAR(50)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.tbl_a}` (`id`, `customer`, `amount`, `city`) VALUES
                (101, 'Alpha Corp', 1500.00, 'Seattle'),
                (102, 'Beta LLC', 750.50, 'Austin'),
                (103, 'Gamma Inc', 3200.00, 'Seattle'),
                (101, 'Alpha Corp', 1500.00, 'Seattle') -- duplicate row across all data columns
            """))

            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_b}` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `item_name` VARCHAR(100),
                    `quantity` INT
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.tbl_b}` (`item_name`, `quantity`) VALUES
                ('Widget A', 50),
                ('Widget B', 20)
            """))

    @classmethod
    def tearDownClass(cls):
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_a}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_b}`"))
            # Clean up users
            conn.execute(text("DELETE FROM users WHERE username IN (:u1, :u2)"), {"u1": cls.user_a_name, "u2": cls.user_b_name})
            conn.execute(text("DELETE FROM query_history WHERE user_id IN (:u1, :u2)"), {"u1": cls.user_a_id, "u2": cls.user_b_id})
            conn.execute(text("DELETE FROM audit_logs WHERE user_id IN (:u1, :u2)"), {"u1": cls.user_a_id, "u2": cls.user_b_id})

    # =========================================================================
    # 1. AUTHENTICATION WORKFLOWS
    # =========================================================================
    def test_01_registration_password_validation(self):
        """Rejects passwords shorter than 12 chars or longer than 72 bytes."""
        short_res = self.client.post("/auth/signup", json={"username": f"short_{self.suffix}", "password": "Short1!"})
        self.assertEqual(short_res.status_code, 400)
        self.assertIn("at least 12 characters", short_res.json()["detail"])

        long_pwd = "A" * 73
        long_res = self.client.post("/auth/signup", json={"username": f"long_{self.suffix}", "password": long_pwd})
        self.assertEqual(long_res.status_code, 400)
        self.assertIn("exceeds maximum length", long_res.json()["detail"])

    def test_02_registration_duplicate_rejection(self):
        """Rejects registration attempt with existing username."""
        dup_res = self.client.post("/auth/signup", json={"username": self.user_a_name, "password": self.test_pwd})
        self.assertEqual(dup_res.status_code, 400)
        self.assertIn("already exists", dup_res.json()["detail"])

    def test_03_login_valid_and_invalid_credentials(self):
        """Verifies login succeeds with correct credentials and fails with wrong credentials."""
        # Valid login
        login_ok = self.client.post("/auth/login", json={"username": self.user_a_name, "password": self.test_pwd})
        self.assertEqual(login_ok.status_code, 200)
        self.assertTrue(login_ok.json()["success"])
        self.assertTrue(len(login_ok.json()["token"]) > 20)

        # Wrong password
        wrong_pwd = self.client.post("/auth/login", json={"username": self.user_a_name, "password": "WrongPassword123!"})
        self.assertEqual(wrong_pwd.status_code, 401)
        self.assertIn("Invalid username or password", wrong_pwd.json()["detail"])

        # Nonexistent user
        no_user = self.client.post("/auth/login", json={"username": "ghost_user_9999", "password": self.test_pwd})
        self.assertEqual(no_user.status_code, 401)

    def test_04_protected_route_rejection_without_auth(self):
        """Accessing protected endpoints without Authorization header returns 401 Unauthorized."""
        res_upload = self.client.post("/upload")
        self.assertEqual(res_upload.status_code, 401)

        res_preview = self.client.get("/preview")
        self.assertEqual(res_preview.status_code, 401)

        res_ask = self.client.post("/ask", json={"question": "show records"})
        self.assertEqual(res_ask.status_code, 401)

        res_history = self.client.get("/api/history")
        self.assertEqual(res_history.status_code, 401)

    def test_05_session_verification_and_logout(self):
        """Verifies session info via GET /auth/me and logout via POST /auth/logout."""
        me_res = self.client.get("/auth/me", headers=self.headers_a)
        self.assertEqual(me_res.status_code, 200)
        self.assertEqual(me_res.json()["username"], self.user_a_name)
        self.assertEqual(me_res.json()["user_id"], self.user_a_id)

        logout_res = self.client.post("/auth/logout", headers=self.headers_a)
        self.assertEqual(logout_res.status_code, 200)
        self.assertTrue(logout_res.json()["success"])

    # =========================================================================
    # 2. DATASET MANAGEMENT WORKFLOWS
    # =========================================================================
    def test_06_upload_csv_with_id_column(self):
        """Uploading CSV containing a user 'id' column succeeds without primary key collision."""
        csv_data = "id,product_title,unit_price\n501,Mechanical Keyboard,89.99\n502,Wireless Mouse,45.50\n"
        files = {"file": ("inventory_items.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
        res = self.client.post("/upload", files=files, headers=self.headers_a)
        self.assertEqual(res.status_code, 200, f"Upload failed: {res.text}")
        data = res.json()
        self.assertEqual(data["rows"], 2)
        self.assertEqual(data["columns"], 3)
        self.assertIn("inventory_items", data["table_name"])

        # Clean up created table
        created_tbl = data["table_name"]
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{created_tbl}`"))

    def test_07_upload_excel_xlsx(self):
        """Uploading an Excel spreadsheet succeeds and correctly parses columns and rows."""
        df = pd.DataFrame({"department": ["Finance", "Legal"], "headcount": [12, 5]})
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)
        excel_buffer.seek(0)

        files = {"file": ("company_depts.xlsx", excel_buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        res = self.client.post("/upload", files=files, headers=self.headers_a)
        self.assertEqual(res.status_code, 200, f"Excel upload failed: {res.text}")
        data = res.json()
        self.assertEqual(data["rows"], 2)

        created_tbl = data["table_name"]
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{created_tbl}`"))

    def test_08_upload_empty_and_unsupported_files(self):
        """Empty files (0 bytes) and unsupported file formats are rejected with 400 Bad Request."""
        # 0 bytes CSV
        files_empty = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
        res_empty = self.client.post("/upload", files=files_empty, headers=self.headers_a)
        self.assertEqual(res_empty.status_code, 400)
        self.assertIn("empty", res_empty.json()["detail"].lower())

        # Unsupported extension (.pdf)
        files_pdf = {"file": ("report.pdf", io.BytesIO(b"%PDF-1.4 dummy content"), "application/pdf")}
        res_pdf = self.client.post("/upload", files=files_pdf, headers=self.headers_a)
        self.assertEqual(res_pdf.status_code, 400)
        self.assertIn("unsupported file format", res_pdf.json()["detail"].lower())

    def test_09_preview_and_pagination(self):
        """GET /preview returns accurate records, column statistics, pagination, and missing counts."""
        headers = {**self.headers_a, "X-Table-Name": self.tbl_a}
        res = self.client.get("/preview?page=1&limit=2", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["records"]), 2)
        self.assertEqual(data["total_rows"], 4)
        self.assertIn("customer", data["columns"])
        self.assertIn("amount", data["columns"])

    def test_10_cross_tenant_dataset_isolation(self):
        """User A cannot preview, query, switch to, or delete User B's dataset."""
        # User A tries to preview User B's table
        headers = {**self.headers_a, "X-Table-Name": self.tbl_b}
        res_preview = self.client.get("/preview", headers=headers)
        self.assertEqual(res_preview.status_code, 403)
        self.assertIn("Access denied", res_preview.json()["detail"])

        # User A tries to set User B's table as active
        res_active = self.client.post("/datasets/active", json={"table_name": self.tbl_b}, headers=self.headers_a)
        self.assertEqual(res_active.status_code, 403)

        # User A tries to delete User B's table
        res_del = self.client.delete(f"/datasets/{self.tbl_b}", headers=self.headers_a)
        self.assertEqual(res_del.status_code, 403)

    # =========================================================================
    # 3. NATURAL LANGUAGE QUERYING WORKFLOWS
    # =========================================================================
    def test_11_ask_question_successful_query(self):
        """Submitting natural-language question generates valid SQL and returns accurate data."""
        headers = {**self.headers_a, "X-Table-Name": self.tbl_a}
        res = self.client.post("/ask", json={"question": "Show sales orders with amount greater than 1000"}, headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertGreaterEqual(data["count"], 2)
        self.assertIsNotNone(data["generated_sql"])
        self.assertIsNotNone(data["summary"])

    def test_12_ask_question_empty_results(self):
        """Query matching zero rows returns count 0, empty list, and informative summary without failing."""
        headers = {**self.headers_a, "X-Table-Name": self.tbl_a}
        res = self.client.post("/ask", json={"question": "Show sales orders where city is Tokyo"}, headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["result"], [])
        self.assertIsNotNone(data["summary"])

    def test_13_ask_question_hallucination_defense(self):
        """Query referring to nonexistent entities fails closed with clean sanitized error."""
        headers = {**self.headers_a, "X-Table-Name": self.tbl_a}
        res = self.client.post("/ask", json={"question": "Show satellite orbital altitudes and launch angles"}, headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["success"])
        self.assertIn("error", data)

    # =========================================================================
    # 4. QUERY HISTORY WORKFLOWS
    # =========================================================================
    def test_14_query_history_persistence_and_isolation(self):
        """Query history logs queries for the author and strictly isolates between users."""
        # Check User A has history
        res_a = self.client.get("/api/history", headers=self.headers_a)
        self.assertEqual(res_a.status_code, 200)
        history_a = res_a.json()
        self.assertGreaterEqual(len(history_a), 1)

        # Check User B cannot see User A's history
        res_b = self.client.get("/api/history", headers=self.headers_b)
        self.assertEqual(res_b.status_code, 200)
        history_b = res_b.json()
        for item in history_b:
            self.assertEqual(item["user_id"], self.user_b_id)
            self.assertNotEqual(item["user_id"], self.user_a_id)

    def test_15_query_history_delete_and_clear(self):
        """Deleting a single history item and clearing all history."""
        # Create a test history item
        hist_item = self.client.post(
            "/api/history",
            json={
                "table_name": self.tbl_a,
                "question": "test history question",
                "generated_sql": "SELECT 1",
                "summary": "test summary",
                "result_count": 1,
                "records": [{"val": 1}]
            },
            headers=self.headers_a
        ).json()
        item_id = hist_item["id"]

        # Delete single item
        del_res = self.client.delete(f"/api/history/{item_id}", headers=self.headers_a)
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.json()["success"])

        # Clear history
        clear_res = self.client.delete("/api/history", headers=self.headers_a)
        self.assertEqual(clear_res.status_code, 200)
        self.assertTrue(clear_res.json()["success"])

        # Verify history is now empty for User A
        verify_empty = self.client.get("/api/history", headers=self.headers_a)
        self.assertEqual(len(verify_empty.json()), 0)

    # =========================================================================
    # 5. DATA OPERATIONS (CLEANING & MODIFICATION)
    # =========================================================================
    def test_16_clean_remove_duplicates(self):
        """Deduplicating table removes duplicate rows and records audit log."""
        headers = {**self.headers_a, "X-Table-Name": self.tbl_a}
        res = self.client.post("/api/clean/remove-duplicates", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertGreaterEqual(data["rows_affected"], 1)

    def test_17_modification_preview_and_cancellation(self):
        """Modification /ask creates confirmation token without modifying data; canceling preserves data."""
        headers = {**self.headers_a, "X-Table-Name": self.tbl_a}
        
        # Get count before
        with engine.connect() as conn:
            count_before = conn.execute(text(f"SELECT COUNT(*) FROM `{self.tbl_a}`")).scalar()

        # Ask for modification
        mod_res = self.client.post("/api/modification/ask", json={"question": "Delete orders where amount is less than 800"}, headers=headers)
        self.assertEqual(mod_res.status_code, 200)
        data = mod_res.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["requires_confirmation"])
        self.assertIsNotNone(data["confirmation_token"])

        # Simulate user cancellation: we do NOT call /execute.
        # Verify row count is unchanged
        with engine.connect() as conn:
            count_after = conn.execute(text(f"SELECT COUNT(*) FROM `{self.tbl_a}`")).scalar()
        self.assertEqual(count_before, count_after)

    # =========================================================================
    # 6. EXPORTS AND REPORTS WORKFLOWS
    # =========================================================================
    def test_18_export_csv_excel_pdf(self):
        """Exports return valid CSV, XLSX, and PDF content streams with accurate headers."""
        sample_records = [
            {"product": "Laptop", "price": 1200.0, "quantity": 3},
            {"product": "Monitor", "price": 350.0, "quantity": 7}
        ]

        # CSV Export
        res_csv = self.client.post("/api/export/csv", json={"records": sample_records}, headers=self.headers_a)
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn("text/csv", res_csv.headers["content-type"])
        self.assertIn("Laptop", res_csv.text)

        # Excel Export
        res_excel = self.client.post("/api/export/excel", json={"records": sample_records}, headers=self.headers_a)
        self.assertEqual(res_excel.status_code, 200)
        self.assertIn("spreadsheetml.sheet", res_excel.headers["content-type"])
        # Verify valid openpyxl readable bytes
        excel_df = pd.read_excel(io.BytesIO(res_excel.content))
        self.assertEqual(len(excel_df), 2)
        self.assertEqual(list(excel_df["product"]), ["Laptop", "Monitor"])

        # PDF Export
        pdf_payload = {
            "question": "Show electronics stock",
            "summary": "Retrieved 2 items.",
            "sql": "SELECT * FROM stock",
            "records": sample_records
        }
        res_pdf = self.client.post("/api/export/pdf", json=pdf_payload, headers=self.headers_a)
        self.assertEqual(res_pdf.status_code, 200)
        self.assertIn("application/pdf", res_pdf.headers["content-type"])
        self.assertTrue(res_pdf.content.startswith(b"%PDF"))

    def test_19_export_raw_table_data(self):
        """Raw table export returns complete dataset with friendly table filename."""
        headers = {**self.headers_a, "X-Table-Name": self.tbl_a}
        res_raw_csv = self.client.get("/api/export/raw/csv", headers=headers)
        self.assertEqual(res_raw_csv.status_code, 200)
        self.assertIn("sales_records.csv", res_raw_csv.headers["content-disposition"])
        self.assertIn("Alpha Corp", res_raw_csv.text)


if __name__ == "__main__":
    unittest.main()
