"""
PromptSQL — Single-Cell Update Behavior Focused Verification Test Suite

Covers the 5 required checks:
1. Matches exactly one row -> correct cell updated, other rows intact.
2. Matches zero rows -> clear error returned without changing data.
3. Matches multiple rows -> clear error returned asking for more specific condition, NO silent arbitrary row update.
4. User and dataset restriction -> tenant isolation strictly enforced (HTTP 403 on cross-tenant attempt).
5. Modification preview, confirmation, audit history, and undo remain completely correct.
"""

import os
import sys
import unittest
import time
from fastapi.testclient import TestClient
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.database.connection import engine, SessionLocal
from app.models.audit_log import AuditLog
from app.models.history import QueryHistory
from app.services.auth_service import create_access_token


class TestSingleCellUpdateVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.suffix = int(time.time()) % 100000

        cls.user_a_num = 99710 + (cls.suffix % 50)
        cls.user_b_num = 99760 + (cls.suffix % 50)
        cls.user_a_id = f"usr_{cls.user_a_num}"
        cls.user_b_id = f"usr_{cls.user_b_num}"

        cls.token_a = create_access_token(cls.user_a_num)
        cls.token_b = create_access_token(cls.user_b_num)
        cls.headers_a = {"Authorization": f"Bearer {cls.token_a}"}
        cls.headers_b = {"Authorization": f"Bearer {cls.token_b}"}

        cls.tbl_a = f"inventory_{cls.user_a_id}"
        cls.tbl_b = f"inventory_{cls.user_b_id}"

        # Setup User B's table
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_b}`"))
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_b}` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `sku` VARCHAR(50),
                    `item_name` VARCHAR(100),
                    `stock` INT
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.tbl_b}` (`sku`, `item_name`, `stock`) VALUES
                ('SKU-B1', 'User B Item', 100);
            """))

    def setUp(self):
        # Reset User A's test table
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{self.tbl_a}`"))
            conn.execute(text(f"""
                CREATE TABLE `{self.tbl_a}` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `sku` VARCHAR(50),
                    `item_name` VARCHAR(100),
                    `category` VARCHAR(50),
                    `price` DOUBLE NULL,
                    `stock` INT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """))
            conn.execute(text(f"""
                INSERT INTO `{self.tbl_a}` (`sku`, `item_name`, `category`, `price`, `stock`) VALUES
                ('SKU-101', 'Ergonomic Keyboard', 'Hardware', 129.99, 50),
                ('SKU-102', 'Wireless Mouse', 'Hardware', 49.99, 80),
                ('SKU-103', 'USB-C Cable', 'Accessories', 19.99, 200),
                ('SKU-104', 'HDMI Cable', 'Accessories', 15.99, 150)
            """))

    @classmethod
    def tearDownClass(cls):
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_a}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_b}`"))

    def test_01_exact_single_row_match_updates_correctly(self):
        """1. When the update condition matches exactly one row, the correct cell is updated."""
        headers = {**self.headers_a, "x-table-name": self.tbl_a}
        res = self.client.post(
            "/api/clean/update-cell",
            headers=headers,
            json={
                "column_name": "price",
                "new_value": "139.99",
                "row_data": {"sku": "SKU-101"}
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["rows_affected"], 1)

        # Verify in DB: SKU-101 price is 139.99, all others unchanged
        with engine.connect() as conn:
            sku101_price = conn.execute(text(f"SELECT price FROM `{self.tbl_a}` WHERE sku = 'SKU-101'")).scalar()
            sku102_price = conn.execute(text(f"SELECT price FROM `{self.tbl_a}` WHERE sku = 'SKU-102'")).scalar()
        self.assertEqual(sku101_price, 139.99)
        self.assertEqual(sku102_price, 49.99)

        # Verify Audit Log
        db = SessionLocal()
        try:
            audit = db.query(AuditLog).filter(
                AuditLog.user_id == self.user_a_id,
                AuditLog.table_name == self.tbl_a,
                AuditLog.operation == "UPDATE"
            ).order_by(AuditLog.id.desc()).first()
            self.assertIsNotNone(audit)
            self.assertEqual(audit.status, "SUCCESS")
            self.assertEqual(audit.rows_affected, 1)
        finally:
            db.close()

    def test_02_zero_row_match_returns_clear_error(self):
        """2. When it matches zero rows, return a clear error without changing data."""
        headers = {**self.headers_a, "x-table-name": self.tbl_a}
        res = self.client.post(
            "/api/clean/update-cell",
            headers=headers,
            json={
                "column_name": "price",
                "new_value": "999.00",
                "row_data": {"sku": "SKU-NON-EXISTENT"}
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["success"])
        self.assertIn("No matching row found", data["error"])

        # Verify in DB: no data changed
        with engine.connect() as conn:
            prices = [r[0] for r in conn.execute(text(f"SELECT price FROM `{self.tbl_a}`")).fetchall()]
        self.assertNotIn(999.00, prices)

    def test_03_multiple_rows_match_refuses_update(self):
        """3. When it matches multiple rows, do not silently update an arbitrary row. Return clear error."""
        headers = {**self.headers_a, "x-table-name": self.tbl_a}
        # Category 'Hardware' matches 2 rows (SKU-101 and SKU-102)
        res = self.client.post(
            "/api/clean/update-cell",
            headers=headers,
            json={
                "column_name": "price",
                "new_value": "999.00",
                "row_data": {"category": "Hardware"}
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["success"])
        self.assertIn("Multiple rows", data["error"])
        self.assertIn("Please provide a more specific condition", data["error"])

        # Verify in DB: neither SKU-101 nor SKU-102 was silently modified
        with engine.connect() as conn:
            sku101_price = conn.execute(text(f"SELECT price FROM `{self.tbl_a}` WHERE sku = 'SKU-101'")).scalar()
            sku102_price = conn.execute(text(f"SELECT price FROM `{self.tbl_a}` WHERE sku = 'SKU-102'")).scalar()
        self.assertEqual(sku101_price, 129.99)
        self.assertEqual(sku102_price, 49.99)

    def test_04_tenant_and_dataset_restriction(self):
        """4. Verify that the operation is restricted to the intended user and dataset."""
        # User A attempts to update User B's dataset
        headers_hack = {**self.headers_a, "x-table-name": self.tbl_b}
        res = self.client.post(
            "/api/clean/update-cell",
            headers=headers_hack,
            json={
                "column_name": "stock",
                "new_value": "0",
                "row_data": {"sku": "SKU-B1"}
            }
        )
        self.assertEqual(res.status_code, 403)

        # Verify User B's data is untouched
        with engine.connect() as conn:
            stock_b = conn.execute(text(f"SELECT stock FROM `{self.tbl_b}` WHERE sku = 'SKU-B1'")).scalar()
        self.assertEqual(stock_b, 100)

    def test_05_preview_confirm_audit_history_and_undo_workflow(self):
        """5. Verify that preview, confirmation, audit history, and undo remain correct."""
        headers = {**self.headers_a, "x-table-name": self.tbl_a}

        # Step 1: Preview single-cell modification
        ask_res = self.client.post(
            "/api/modification/ask",
            headers=headers,
            json={"question": "Update price to 199.99 for SKU SKU-101"}
        )
        self.assertEqual(ask_res.status_code, 200)
        ask_data = ask_res.json()
        self.assertTrue(ask_data["success"])
        self.assertTrue(ask_data["requires_confirmation"])
        token = ask_data["confirmation_token"]

        # Table is untouched before confirmation
        with engine.connect() as conn:
            price_before = conn.execute(text(f"SELECT price FROM `{self.tbl_a}` WHERE sku = 'SKU-101'")).scalar()
        self.assertEqual(price_before, 129.99)

        # Step 2: Confirm modification
        exec_res = self.client.post(
            "/api/modification/execute",
            headers=headers,
            json={"confirmation_token": token}
        )
        self.assertEqual(exec_res.status_code, 200)
        exec_data = exec_res.json()
        self.assertTrue(exec_data["success"])
        history_id = exec_data["history_id"]

        # Table price is updated after confirmation
        with engine.connect() as conn:
            price_after = conn.execute(text(f"SELECT price FROM `{self.tbl_a}` WHERE sku = 'SKU-101'")).scalar()
        self.assertEqual(price_after, 199.99)

        # Step 3: Undo modification
        undo_res = self.client.post(f"/api/history/{history_id}/undo", headers=headers)
        self.assertEqual(undo_res.status_code, 200)
        self.assertTrue(undo_res.json()["success"])

        # Table price is restored to original 129.99
        with engine.connect() as conn:
            price_restored = conn.execute(text(f"SELECT price FROM `{self.tbl_a}` WHERE sku = 'SKU-101'")).scalar()
        self.assertEqual(price_restored, 129.99)


if __name__ == "__main__":
    unittest.main()
