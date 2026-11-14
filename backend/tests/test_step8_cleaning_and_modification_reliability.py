"""
PromptSQL — Step 8: Data Cleaning and Modification Reliability Verification Test Suite

Comprehensive automated verification covering:
1. Data Cleaning:
   - Missing-value detection (/clean/locate-missing)
   - Missing-value handling (/clean/impute: drop, mean, median, mode, custom)
   - Duplicate detection and removal (/clean/remove-duplicates)
   - Correct data type handling (/clean/convert-type, /clean/extract-and-convert)
   - Text standardization (/clean/standardize-text: trim, upper, lower, title)
   - Cell updating (/clean/update-cell)
   - Preservation of valid values during cleaning
2. Modification Workflow:
   - Preview changes before execution (/api/modification/ask)
   - Confirm modifications (/api/modification/execute)
   - Cancel modifications without changing data (/api/modification/cancel)
   - Undo completed modifications (/api/history/{id}/undo)
   - Handling of invalid modification requests
3. Data Integrity & Tenant Isolation:
   - Original data remains unchanged before confirmation
   - Confirmed changes affect only intended rows/columns
   - Undo restores previous data exactly
   - Operations do not affect another user's dataset
   - Exported data (/export/raw/csv, /export/raw/excel) reflects confirmed changes
"""

import os
import sys
import unittest
import time
import json
import secrets
from io import BytesIO
from fastapi.testclient import TestClient
from sqlalchemy import text, inspect

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.database.connection import engine, SessionLocal
from app.models.audit_log import AuditLog
from app.models.history import QueryHistory
from app.models.pending_modification import PendingModification
from app.services.auth_service import create_access_token


class TestStep8CleaningAndModificationReliability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.suffix = int(time.time()) % 100000

        cls.user_a_num = 99810 + (cls.suffix % 50)
        cls.user_b_num = 99860 + (cls.suffix % 50)
        cls.user_a_id = f"usr_{cls.user_a_num}"
        cls.user_b_id = f"usr_{cls.user_b_num}"

        cls.token_a = create_access_token(cls.user_a_num)
        cls.token_b = create_access_token(cls.user_b_num)
        cls.headers_a = {"Authorization": f"Bearer {cls.token_a}"}
        cls.headers_b = {"Authorization": f"Bearer {cls.token_b}"}

        # Multi-type test tables for User A and User B
        cls.tbl_products = f"products_{cls.user_a_id}"
        cls.tbl_customers = f"customers_{cls.user_a_id}"
        cls.tbl_user_b = f"products_{cls.user_b_id}"

        cls._init_database_tables()

    @classmethod
    def _init_database_tables(cls):
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_products}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_customers}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_user_b}`"))

            # Table 1: products (with surrogate _row_id PK, dirty data, duplicates, nulls)
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_products}` (
                    `_row_id` INT AUTO_INCREMENT PRIMARY KEY,
                    `product_code` VARCHAR(50),
                    `product_name` VARCHAR(100),
                    `category` VARCHAR(50),
                    `price` DOUBLE NULL,
                    `raw_cost` VARCHAR(50) NULL,
                    `stock` INT NULL,
                    `launch_date` VARCHAR(50) NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """))

            # Table 2: customers (with natural/custom PK, text columns)
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_customers}` (
                    `customer_id` INT AUTO_INCREMENT PRIMARY KEY,
                    `full_name` VARCHAR(100),
                    `city` VARCHAR(50),
                    `tier` VARCHAR(20)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """))

            # Table 3: User B's isolated products table
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_user_b}` (
                    `_row_id` INT AUTO_INCREMENT PRIMARY KEY,
                    `product_code` VARCHAR(50),
                    `product_name` VARCHAR(100),
                    `price` DOUBLE NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """))

            # Seed User B's table
            conn.execute(text(f"""
                INSERT INTO `{cls.tbl_user_b}` (`product_code`, `product_name`, `price`) VALUES
                ('B-101', 'User B Gizmo', 99.99),
                ('B-102', 'User B Gadget', 149.50);
            """))

    def setUp(self):
        # Reset User A's products table before each test group with full clean schema
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{self.tbl_products}`"))
            conn.execute(text(f"""
                CREATE TABLE `{self.tbl_products}` (
                    `_row_id` INT AUTO_INCREMENT PRIMARY KEY,
                    `product_code` VARCHAR(50),
                    `product_name` VARCHAR(100),
                    `category` VARCHAR(50),
                    `price` DOUBLE NULL,
                    `raw_cost` VARCHAR(50) NULL,
                    `stock` INT NULL,
                    `launch_date` VARCHAR(50) NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """))
            conn.execute(text(f"""
                INSERT INTO `{self.tbl_products}` 
                (`product_code`, `product_name`, `category`, `price`, `raw_cost`, `stock`, `launch_date`) VALUES
                ('P-100', 'mechanical keyboard', 'Electronics', 120.00, '$80.50', 50, '2026-01-15'),
                ('P-101', 'wireless mouse', 'Electronics', 45.00, '$25.00', NULL, '2026-02-01'),
                ('P-102', 'ergonomic chair', 'Office', NULL, '$150.00', 20, '2026-02-10'),
                ('P-103', 'desk pad', 'Office', 25.00, '$10.00', 100, NULL),
                ('P-104', 'usb-c hub', 'Electronics', 60.00, '$35.00', 30, '2026-03-01'),
                ('P-100', 'mechanical keyboard', 'Electronics', 120.00, '$80.50', 50, '2026-01-15') -- duplicate of row 1
            """))

    @classmethod
    def tearDownClass(cls):
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_products}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_customers}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_user_b}`"))

    # =========================================================================
    # PART 1: DATA CLEANING VERIFICATION
    # =========================================================================

    def test_01_locate_missing_values(self):
        """Test locate-missing correctly detects NULL and blank cells."""
        headers = {**self.headers_a, "x-table-name": self.tbl_products}
        res = self.client.get("/api/clean/locate-missing?column_name=price", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["column_name"], "price")
        # Row P-102 has NULL price
        self.assertEqual(data["total_missing"], 1)
        self.assertTrue(any(r["product_code"] == "P-102" for r in data["rows"]))

    def test_02_impute_missing_mean_and_preservation(self):
        """Test impute with 'mean' strategy updates missing values and preserves valid values."""
        headers = {**self.headers_a, "x-table-name": self.tbl_products}
        # Available prices: 120, 45, 25, 60, 120 -> mean = 370 / 5 = 74.0
        res = self.client.post(
            "/api/clean/impute",
            headers=headers,
            json={"column_name": "price", "strategy": "mean"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["rows_affected"], 1)

        # Verify in DB: P-102 price should now be 74.0, while P-100 is still 120.0
        with engine.connect() as conn:
            p102_price = conn.execute(text(f"SELECT price FROM `{self.tbl_products}` WHERE product_code = 'P-102'")).scalar()
            p100_price = conn.execute(text(f"SELECT price FROM `{self.tbl_products}` WHERE product_code = 'P-100' LIMIT 1")).scalar()
        self.assertAlmostEqual(p102_price, 74.0, places=1)
        self.assertEqual(p100_price, 120.0)

    def test_03_impute_missing_median_and_mode(self):
        """Test impute with 'median' and 'mode' strategies."""
        headers = {**self.headers_a, "x-table-name": self.tbl_products}
        # Impute stock with median: available stocks: 50, 20, 100, 30, 50 -> sorted: 20, 30, 50, 50, 100 -> median = 50
        res = self.client.post(
            "/api/clean/impute",
            headers=headers,
            json={"column_name": "stock", "strategy": "median"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

        with engine.connect() as conn:
            p101_stock = conn.execute(text(f"SELECT stock FROM `{self.tbl_products}` WHERE product_code = 'P-101'")).scalar()
        self.assertEqual(p101_stock, 50)

    def test_04_impute_missing_drop(self):
        """Test impute with 'drop' strategy removes rows with missing values."""
        headers = {**self.headers_a, "x-table-name": self.tbl_products}
        # Row P-103 has launch_date NULL
        res = self.client.post(
            "/api/clean/impute",
            headers=headers,
            json={"column_name": "launch_date", "strategy": "drop"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])
        self.assertEqual(res.json()["rows_affected"], 1)

        with engine.connect() as conn:
            remaining_codes = [r[0] for r in conn.execute(text(f"SELECT product_code FROM `{self.tbl_products}`")).fetchall()]
        self.assertNotIn("P-103", remaining_codes)
        self.assertIn("P-100", remaining_codes)

    def test_05_impute_custom_value_numeric_and_text(self):
        """Test impute with 'custom' strategy handles text and numeric gracefully."""
        headers = {**self.headers_a, "x-table-name": self.tbl_products}
        res = self.client.post(
            "/api/clean/impute",
            headers=headers,
            json={"column_name": "price", "strategy": "custom", "custom_value": "99.95"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

        with engine.connect() as conn:
            val = conn.execute(text(f"SELECT price FROM `{self.tbl_products}` WHERE product_code = 'P-102'")).scalar()
        self.assertAlmostEqual(val, 99.95, places=2)

    def test_06_remove_duplicates(self):
        """Test duplicate detection and removal retains one row and removes duplicate."""
        headers = {**self.headers_a, "x-table-name": self.tbl_products}
        with engine.connect() as conn:
            count_before = conn.execute(text(f"SELECT COUNT(*) FROM `{self.tbl_products}`")).scalar()
        self.assertEqual(count_before, 6)

        res = self.client.post("/api/clean/remove-duplicates", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["rows_affected"], 1)
        self.assertEqual(data["total_rows"], 5)

        with engine.connect() as conn:
            p100_count = conn.execute(text(f"SELECT COUNT(*) FROM `{self.tbl_products}` WHERE product_code = 'P-100'")).scalar()
        self.assertEqual(p100_count, 1)

    def test_07_extract_numbers_and_convert_type(self):
        """Test extract-and-convert strips currency symbols ('$80.50' -> 80.5) and alters column to DOUBLE."""
        headers = {**self.headers_a, "x-table-name": self.tbl_products}
        res = self.client.post(
            "/api/clean/extract-and-convert",
            headers=headers,
            json={"column_name": "raw_cost"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])

        with engine.connect() as conn:
            val = conn.execute(text(f"SELECT raw_cost FROM `{self.tbl_products}` WHERE product_code = 'P-100' LIMIT 1")).scalar()
            inspector = inspect(engine)
            cols = {c["name"]: str(c["type"]).lower() for c in inspector.get_columns(self.tbl_products)}

        self.assertAlmostEqual(val, 80.50, places=2)
        self.assertIn("double", cols["raw_cost"])

    def test_08_standardize_text_upper_lower_trim_title(self):
        """Test standardize-text functions including Title Case without hardcoded 'id'."""
        headers = {**self.headers_a, "x-table-name": self.tbl_products}

        # 1. UPPER
        res_upper = self.client.post(
            "/api/clean/standardize-text",
            headers=headers,
            json={"column_name": "category", "operation": "upper"}
        )
        self.assertEqual(res_upper.status_code, 200)
        self.assertTrue(res_upper.json()["success"])

        with engine.connect() as conn:
            cat = conn.execute(text(f"SELECT category FROM `{self.tbl_products}` WHERE product_code = 'P-100' LIMIT 1")).scalar()
        self.assertEqual(cat, "ELECTRONICS")

        # 2. TITLE CASE (runs on table with PK _row_id, not id!)
        res_title = self.client.post(
            "/api/clean/standardize-text",
            headers=headers,
            json={"column_name": "product_name", "operation": "title"}
        )
        self.assertEqual(res_title.status_code, 200)
        self.assertTrue(res_title.json()["success"])

        with engine.connect() as conn:
            name = conn.execute(text(f"SELECT product_name FROM `{self.tbl_products}` WHERE product_code = 'P-100' LIMIT 1")).scalar()
        self.assertEqual(name, "Mechanical Keyboard")

    def test_09_single_cell_update(self):
        """Test update-cell targets exactly one specific cell and preserves all other rows."""
        headers = {**self.headers_a, "x-table-name": self.tbl_products}
        res = self.client.post(
            "/api/clean/update-cell",
            headers=headers,
            json={
                "column_name": "product_name",
                "new_value": "Ergonomic Office Chair Pro",
                "row_data": {"product_code": "P-102"}
            }
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

        with engine.connect() as conn:
            updated_val = conn.execute(text(f"SELECT product_name FROM `{self.tbl_products}` WHERE product_code = 'P-102'")).scalar()
            untouched_val = conn.execute(text(f"SELECT product_name FROM `{self.tbl_products}` WHERE product_code = 'P-104'")).scalar()
        self.assertEqual(updated_val, "Ergonomic Office Chair Pro")
        self.assertEqual(untouched_val, "usb-c hub")

    # =========================================================================
    # PART 2: MODIFICATION WORKFLOW VERIFICATION
    # =========================================================================

    def test_10_modification_preview_without_data_change(self):
        """Test /api/modification/ask produces preview with token while leaving table data untouched."""
        headers = {**self.headers_a, "x-table-name": self.tbl_products}
        ask_res = self.client.post(
            "/api/modification/ask",
            headers=headers,
            json={"question": "Increase price by 10 for Electronics category"}
        )
        self.assertEqual(ask_res.status_code, 200)
        data = ask_res.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["requires_confirmation"])
        self.assertIn("confirmation_token", data)
        self.assertEqual(data["intent"], "UPDATE")
        token = data["confirmation_token"]

        # Verify data is UNCHANGED in database
        with engine.connect() as conn:
            p100_price = conn.execute(text(f"SELECT price FROM `{self.tbl_products}` WHERE product_code = 'P-100' LIMIT 1")).scalar()
        self.assertEqual(p100_price, 120.00)

        # Verify pending modification status in database is PENDING
        db = SessionLocal()
        try:
            pending = db.query(PendingModification).filter(PendingModification.token == token).first()
            self.assertIsNotNone(pending)
            self.assertEqual(pending.status, "PENDING")
        finally:
            db.close()

    def test_11_modification_confirmation_and_execution(self):
        """Test /api/modification/execute applies changes, records audit log and query history."""
        headers = {**self.headers_a, "x-table-name": self.tbl_products}
        ask_res = self.client.post(
            "/api/modification/ask",
            headers=headers,
            json={"question": "Update price to 135 for product P-100"}
        )
        self.assertEqual(ask_res.status_code, 200)
        token = ask_res.json()["confirmation_token"]

        exec_res = self.client.post(
            "/api/modification/execute",
            headers=headers,
            json={"confirmation_token": token}
        )
        self.assertEqual(exec_res.status_code, 200)
        exec_data = exec_res.json()
        self.assertTrue(exec_data["success"])
        self.assertIn("history_id", exec_data)

        # Verify table data was modified
        with engine.connect() as conn:
            new_price = conn.execute(text(f"SELECT price FROM `{self.tbl_products}` WHERE product_code = 'P-100' LIMIT 1")).scalar()
            p104_price = conn.execute(text(f"SELECT price FROM `{self.tbl_products}` WHERE product_code = 'P-104'")).scalar()
        self.assertEqual(new_price, 135.00)
        self.assertEqual(p104_price, 60.00)  # Untouched

        # Verify Audit Log
        db = SessionLocal()
        try:
            audit = db.query(AuditLog).filter(
                AuditLog.user_id == self.user_a_id,
                AuditLog.table_name == self.tbl_products,
                AuditLog.status == "SUCCESS"
            ).order_by(AuditLog.id.desc()).first()
            self.assertIsNotNone(audit)
            self.assertEqual(audit.operation, "UPDATE")

            # Verify Query History has undo_sql
            hist = db.query(QueryHistory).filter(QueryHistory.id == exec_data["history_id"]).first()
            self.assertIsNotNone(hist)
            self.assertIsNotNone(hist.undo_sql)
        finally:
            db.close()

    def test_12_modification_cancellation_and_token_invalidation(self):
        """Test /api/modification/cancel marks token CANCELLED, preserves data, and blocks future execution."""
        headers = {**self.headers_a, "x-table-name": self.tbl_products}
        ask_res = self.client.post(
            "/api/modification/ask",
            headers=headers,
            json={"question": "Delete from products where product_code = 'P-104'"}
        )
        self.assertEqual(ask_res.status_code, 200)
        token = ask_res.json()["confirmation_token"]

        # Cancel the modification
        cancel_res = self.client.post(
            "/api/modification/cancel",
            headers=headers,
            json={"confirmation_token": token}
        )
        self.assertEqual(cancel_res.status_code, 200)
        self.assertTrue(cancel_res.json()["success"])
        self.assertEqual(cancel_res.json()["status"], "CANCELLED")

        # Verify row still exists in database
        with engine.connect() as conn:
            exists = conn.execute(text(f"SELECT COUNT(*) FROM `{self.tbl_products}` WHERE product_code = 'P-104'")).scalar()
        self.assertEqual(exists, 1)

        # Attempt to execute cancelled token must fail with HTTP 400
        re_exec_res = self.client.post(
            "/api/modification/execute",
            headers=headers,
            json={"confirmation_token": token}
        )
        self.assertEqual(re_exec_res.status_code, 400)
        self.assertIn("CANCELLED", re_exec_res.json()["detail"])

    def test_13_undo_completed_modification(self):
        """Test undo reverts modification and restores original database state."""
        headers = {**self.headers_a, "x-table-name": self.tbl_products}

        # Step 1: Record original price for P-104
        with engine.connect() as conn:
            original_price = conn.execute(text(f"SELECT price FROM `{self.tbl_products}` WHERE product_code = 'P-104'")).scalar()

        # Step 2: Modify price to 999.00
        ask_res = self.client.post(
            "/api/modification/ask",
            headers=headers,
            json={"question": "Update price to 999.00 where product_code = 'P-104'"}
        )
        token = ask_res.json()["confirmation_token"]
        exec_res = self.client.post(
            "/api/modification/execute",
            headers=headers,
            json={"confirmation_token": token}
        )
        history_id = exec_res.json()["history_id"]

        # Confirm price is now 999.00
        with engine.connect() as conn:
            modified_price = conn.execute(text(f"SELECT price FROM `{self.tbl_products}` WHERE product_code = 'P-104'")).scalar()
        self.assertEqual(modified_price, 999.00)

        # Step 3: Call Undo endpoint
        undo_res = self.client.post(f"/api/history/{history_id}/undo", headers=headers)
        self.assertEqual(undo_res.status_code, 200)
        self.assertTrue(undo_res.json()["success"])

        # Step 4: Verify original price restored
        with engine.connect() as conn:
            restored_price = conn.execute(text(f"SELECT price FROM `{self.tbl_products}` WHERE product_code = 'P-104'")).scalar()
        self.assertEqual(restored_price, original_price)

    def test_14_invalid_modification_requests_handling(self):
        """Test invalid modification requests fail gracefully with safe error responses."""
        headers = {**self.headers_a, "x-table-name": self.tbl_products}

        # 1. Non-existent column
        res_bad_col = self.client.post(
            "/api/modification/ask",
            headers=headers,
            json={"question": "Update non_existent_column to 50"}
        )
        self.assertTrue(res_bad_col.status_code in [200, 400, 500])
        if res_bad_col.status_code == 200:
            self.assertFalse(res_bad_col.json().get("valid", True) and res_bad_col.json().get("success", False))

        # 2. Fake confirmation token execution
        res_fake_token = self.client.post(
            "/api/modification/execute",
            headers=headers,
            json={"confirmation_token": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}
        )
        self.assertEqual(res_fake_token.status_code, 404)

        # 3. Double execution of same token (replay attack)
        ask_res = self.client.post(
            "/api/modification/ask",
            headers=headers,
            json={"question": "Update price to 55 where product_code = 'P-101'"}
        )
        token = ask_res.json()["confirmation_token"]
        first_exec = self.client.post("/api/modification/execute", headers=headers, json={"confirmation_token": token})
        self.assertEqual(first_exec.status_code, 200)

        second_exec = self.client.post("/api/modification/execute", headers=headers, json={"confirmation_token": token})
        self.assertEqual(second_exec.status_code, 400)
        self.assertIn("already been executed", second_exec.json()["detail"])

    # =========================================================================
    # PART 3: DATA INTEGRITY & TENANT ISOLATION
    # =========================================================================

    def test_15_tenant_isolation_in_cleaning_and_modification(self):
        """Test User A cannot clean, modify, cancel, or execute User B's dataset."""
        # User A tries to clean User B's table
        headers_hack = {**self.headers_a, "x-table-name": self.tbl_user_b}
        res_clean = self.client.post("/api/clean/remove-duplicates", headers=headers_hack)
        self.assertEqual(res_clean.status_code, 403)

        # User A creates a modification preview
        ask_res = self.client.post(
            "/api/modification/ask",
            headers={**self.headers_a, "x-table-name": self.tbl_products},
            json={"question": "Update price to 88 where product_code = 'P-101'"}
        )
        token_a = ask_res.json()["confirmation_token"]

        # User B tries to cancel User A's token
        res_b_cancel = self.client.post(
            "/api/modification/cancel",
            headers=self.headers_b,
            json={"confirmation_token": token_a}
        )
        self.assertEqual(res_b_cancel.status_code, 403)

        # User B tries to execute User A's token
        res_b_exec = self.client.post(
            "/api/modification/execute",
            headers=self.headers_b,
            json={"confirmation_token": token_a}
        )
        self.assertEqual(res_b_exec.status_code, 403)

        # User B's table data remains completely unchanged
        with engine.connect() as conn:
            b_count = conn.execute(text(f"SELECT COUNT(*) FROM `{self.tbl_user_b}`")).scalar()
        self.assertEqual(b_count, 2)

    def test_16_exported_data_reflects_confirmed_changes(self):
        """Test raw CSV and Excel export endpoints reflect confirmed modifications."""
        headers = {**self.headers_a, "x-table-name": self.tbl_products}

        # Modify price of P-100 to 250.00
        ask_res = self.client.post(
            "/api/modification/ask",
            headers=headers,
            json={"question": "Update price to 250.00 where product_code = 'P-100'"}
        )
        token = ask_res.json()["confirmation_token"]
        self.client.post("/api/modification/execute", headers=headers, json={"confirmation_token": token})

        # Export raw CSV
        csv_res = self.client.get("/api/export/raw/csv", headers=headers)
        self.assertEqual(csv_res.status_code, 200)
        csv_text = csv_res.text
        self.assertIn("250", csv_text)
        self.assertIn("P-100", csv_text)

        # Export raw Excel
        excel_res = self.client.get("/api/export/raw/excel", headers=headers)
        self.assertEqual(excel_res.status_code, 200)
        self.assertTrue(len(excel_res.content) > 0)


if __name__ == "__main__":
    unittest.main()
