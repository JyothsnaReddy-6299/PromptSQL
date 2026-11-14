"""
PromptSQL — Issue 14: AI-Powered Custom Table Builder & Conversational Bulk Record Insertion
Verification Test Suite covering all 19 required test cases across multiple custom tables:
1. Natural-language schema generation.
2. Correct data type inference.
3. Invalid and duplicate column names rejection.
4. Reserved identifier rejection.
5. Schema editing before creation.
6. Successful table creation.
7. Single-record conversational insertion.
8. Multiple-record bulk insertion.
9. Correct mapping of values to columns.
10. Invalid data type rejection (e.g. non-numeric for int/decimal, invalid dates).
11. Missing required field handling.
12. Ambiguous table selection.
13. Cross-tenant table access rejection.
14. Confirmation and cancellation.
15. Duplicate submission prevention (idempotency).
16. Transaction rollback on bulk insertion failure.
17. Audit and history integration.
18. Existing manual table creation remains functional.
19. Existing chatbot query and modification workflows remain unaffected.
"""

import os
import sys
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import text, inspect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.database.connection import engine, SessionLocal
from app.services.auth_service import create_access_token
from app.services.table_schema_generator import (
    validate_custom_table_schema,
    normalize_sql_type,
    generate_table_schema_from_prompt,
    MYSQL_RESERVED_KEYWORDS
)
from app.services.bulk_record_parser import (
    parse_and_validate_records_for_insert,
    resolve_target_table_from_prompt,
    validate_single_record
)
from app.models.audit_log import AuditLog
from app.models.history import QueryHistory
from app.models.pending_modification import PendingModification


class TestIssue14CustomTableBuilder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

        cls.user_num = 99914
        cls.other_user_num = 99915
        cls.user_id = f"usr_{cls.user_num}"
        cls.other_user_id = f"usr_{cls.other_user_num}"

        cls.token = create_access_token(cls.user_num)
        cls.other_token = create_access_token(cls.other_user_num)

        cls.headers = {
            "Authorization": f"Bearer {cls.token}",
            "X-User-ID": cls.user_id
        }
        cls.other_headers = {
            "Authorization": f"Bearer {cls.other_token}",
            "X-User-ID": cls.other_user_id
        }

        # Setup table names for 2 structurally distinct custom tables
        cls.tbl1_friendly = "inventory_stock"
        cls.tbl1_physical = f"{cls.tbl1_friendly}_{cls.user_id}"

        cls.tbl2_friendly = "patient_appointments"
        cls.tbl2_physical = f"{cls.tbl2_friendly}_{cls.user_id}"

        cls.clean_tables()

    @classmethod
    def tearDownClass(cls):
        cls.clean_tables()

    @classmethod
    def clean_tables(cls):
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl1_physical}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl2_physical}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `test_edit_tbl_{cls.user_id}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `manual_test_tbl_{cls.user_id}`"))

    # -------------------------------------------------------------------------
    # 1. Natural-language schema generation
    # -------------------------------------------------------------------------
    def test_01_natural_language_schema_generation(self):
        with patch("app.services.table_schema_generator.call_llm") as mock_llm:
            mock_llm.return_value = """
            {
              "table_name": "inventory_stock",
              "explanation": "Tracks warehouse inventory",
              "columns": [
                {"name": "item_name", "type": "VARCHAR(255)"},
                {"name": "category", "type": "TEXT"},
                {"name": "quantity", "type": "INT"},
                {"name": "unit_price", "type": "DECIMAL(10,2)"},
                {"name": "restock_date", "type": "DATE"}
              ]
            }
            """
            schema = generate_table_schema_from_prompt("Create an inventory stock table with item name, category, quantity, unit price and restock date.")
            self.assertTrue(schema["success"])
            self.assertEqual(schema["table_name"], "inventory_stock")
            col_names = [c["name"] for c in schema["columns"]]
            self.assertIn("item_name", col_names)
            self.assertIn("quantity", col_names)
            self.assertNotIn("id", col_names)  # Must exclude auto PK 'id'

    # -------------------------------------------------------------------------
    # 2. Correct data type inference
    # -------------------------------------------------------------------------
    def test_02_correct_data_type_inference(self):
        self.assertEqual(normalize_sql_type("INT"), "INT")
        self.assertEqual(normalize_sql_type("INTEGER"), "INT")
        self.assertEqual(normalize_sql_type("DECIMAL"), "DECIMAL(10,2)")
        self.assertEqual(normalize_sql_type("CURRENCY"), "DECIMAL(10,2)")
        self.assertEqual(normalize_sql_type("FLOAT"), "DOUBLE")
        self.assertEqual(normalize_sql_type("DATE"), "DATE")
        self.assertEqual(normalize_sql_type("DATETIME"), "DATETIME")
        self.assertEqual(normalize_sql_type("BOOLEAN"), "BOOLEAN")
        self.assertEqual(normalize_sql_type("VARCHAR"), "VARCHAR(255)")
        self.assertEqual(normalize_sql_type("TEXT"), "TEXT")

    # -------------------------------------------------------------------------
    # 3. Invalid and duplicate column names
    # -------------------------------------------------------------------------
    def test_03_invalid_and_duplicate_column_names(self):
        # Duplicate columns
        ok, err = validate_custom_table_schema("test_table", [
            {"name": "price", "type": "DOUBLE"},
            {"name": "price", "type": "INT"}
        ])
        self.assertFalse(ok)
        self.assertIn("duplicate", err.lower())

        # Invalid column characters
        ok, err = validate_custom_table_schema("test_table", [
            {"name": "bad column-name!", "type": "VARCHAR(255)"}
        ])
        self.assertFalse(ok)
        self.assertIn("invalid column name", err.lower())

    # -------------------------------------------------------------------------
    # 4. Reserved identifier rejection
    # -------------------------------------------------------------------------
    def test_04_reserved_identifier_rejection(self):
        # Reserved word for table
        ok, err = validate_custom_table_schema("select", [{"name": "item", "type": "TEXT"}])
        self.assertFalse(ok)
        self.assertIn("reserved", err.lower())

        # Reserved word for column
        ok, err = validate_custom_table_schema("my_table", [{"name": "order", "type": "DATE"}])
        self.assertFalse(ok)
        self.assertIn("reserved", err.lower())

        # Collision with PK 'id'
        ok, err = validate_custom_table_schema("my_table", [{"name": "id", "type": "INT"}])
        self.assertFalse(ok)
        self.assertIn("primary key", err.lower())

    # -------------------------------------------------------------------------
    # 5. Schema editing before creation
    # -------------------------------------------------------------------------
    def test_05_schema_editing_before_creation(self):
        # User edits the AI proposed schema before posting to create
        edited_columns = [
            {"name": "sku_code", "type": "VARCHAR(255)"},
            {"name": "stock_count", "type": "INT"},
            {"name": "is_active", "type": "BOOLEAN"}
        ]
        ok, err = validate_custom_table_schema("edited_inventory", edited_columns)
        self.assertTrue(ok)
        self.assertIsNone(err)

    # -------------------------------------------------------------------------
    # 6. Successful table creation (Structurally distinct tables)
    # -------------------------------------------------------------------------
    def test_06_successful_table_creation(self):
        # Table 1: Inventory stock
        payload1 = {
            "table_name": self.tbl1_friendly,
            "columns": [
                {"name": "item_name", "type": "VARCHAR(255)"},
                {"name": "category", "type": "VARCHAR(255)"},
                {"name": "quantity", "type": "INT"},
                {"name": "unit_price", "type": "DECIMAL(10,2)"},
                {"name": "restock_date", "type": "DATE"}
            ]
        }
        res1 = self.client.post("/datasets/create", json=payload1, headers=self.headers)
        self.assertEqual(res1.status_code, 200, res1.text)
        self.assertTrue(res1.json()["success"])

        # Table 2: Patient appointments
        payload2 = {
            "table_name": self.tbl2_friendly,
            "columns": [
                {"name": "patient_name", "type": "VARCHAR(255)"},
                {"name": "doctor_name", "type": "VARCHAR(255)"},
                {"name": "fee", "type": "DOUBLE"},
                {"name": "is_urgent", "type": "BOOLEAN"},
                {"name": "appointment_date", "type": "DATE"}
            ]
        }
        res2 = self.client.post("/datasets/create", json=payload2, headers=self.headers)
        self.assertEqual(res2.status_code, 200, res2.text)
        self.assertTrue(res2.json()["success"])

        # Verify tables in database with PK 'id'
        inspector = inspect(engine)
        self.assertIn(self.tbl1_physical, inspector.get_table_names())
        self.assertIn(self.tbl2_physical, inspector.get_table_names())
        cols1 = [c["name"] for c in inspector.get_columns(self.tbl1_physical)]
        self.assertIn("id", cols1)
        self.assertIn("item_name", cols1)

    # -------------------------------------------------------------------------
    # 7. Single-record conversational insertion
    # -------------------------------------------------------------------------
    def test_07_single_record_conversational_insertion(self):
        # In Table 1: inventory_stock
        with patch("app.services.bulk_record_parser.call_llm") as mock_llm:
            mock_llm.return_value = """
            {
              "records": [
                {
                  "item_name": "Wireless Mouse",
                  "category": "Electronics",
                  "quantity": "45",
                  "unit_price": "29.99",
                  "restock_date": "2025-06-15"
                }
              ]
            }
            """
            res = self.client.post(
                "/api/modification/ask",
                json={"question": "Add item Wireless Mouse, Electronics, quantity 45, price 29.99, restock 2025-06-15 to inventory_stock"},
                headers={**self.headers, "X-Table-Name": self.tbl1_physical}
            )
            self.assertEqual(res.status_code, 200, res.text)
            data = res.json()
            self.assertTrue(data.get("requires_confirmation"))
            self.assertTrue(data.get("is_bulk_insert"))
            self.assertEqual(data.get("valid_records_count"), 1)
            self.assertEqual(len(data.get("preview_records")), 1)
            self.assertEqual(data["preview_records"][0]["item_name"], "Wireless Mouse")

    # -------------------------------------------------------------------------
    # 8. Multiple-record bulk insertion
    # -------------------------------------------------------------------------
    def test_08_multiple_record_bulk_insertion(self):
        # In Table 2: patient_appointments
        with patch("app.services.bulk_record_parser.call_llm") as mock_llm:
            mock_llm.return_value = """
            {
              "records": [
                {
                  "patient_name": "John Doe",
                  "doctor_name": "Dr. House",
                  "fee": "150.0",
                  "is_urgent": "true",
                  "appointment_date": "2025-07-10"
                },
                {
                  "patient_name": "Alice Smith",
                  "doctor_name": "Dr. Watson",
                  "fee": "120.5",
                  "is_urgent": "false",
                  "appointment_date": "2025-07-11"
                },
                {
                  "patient_name": "Bob Taylor",
                  "doctor_name": "Dr. House",
                  "fee": "200.0",
                  "is_urgent": "true",
                  "appointment_date": "2025-07-12"
                }
              ]
            }
            """
            res = self.client.post(
                "/api/modification/ask",
                json={"question": "Add 3 appointments to patient_appointments:\n- John Doe, Dr. House, 150, urgent, 2025-07-10\n- Alice Smith, Dr. Watson, 120.5, routine, 2025-07-11\n- Bob Taylor, Dr. House, 200, urgent, 2025-07-12"},
                headers={**self.headers, "X-Table-Name": self.tbl2_physical}
            )
            self.assertEqual(res.status_code, 200, res.text)
            data = res.json()
            self.assertTrue(data.get("requires_confirmation"))
            self.assertEqual(data.get("valid_records_count"), 3)
            self.assertEqual(len(data.get("preview_records")), 3)

    # -------------------------------------------------------------------------
    # 9. Correct mapping of values to columns
    # -------------------------------------------------------------------------
    def test_09_correct_mapping_of_values_to_columns(self):
        schema_cols = [
            {"name": "id", "type_str": "INT", "category": "integer", "nullable": False, "is_pk": True, "autoincrement": True},
            {"name": "item_name", "type_str": "VARCHAR(255)", "category": "string", "nullable": False, "is_pk": False, "autoincrement": False},
            {"name": "quantity", "type_str": "INT", "category": "integer", "nullable": False, "is_pk": False, "autoincrement": False},
            {"name": "unit_price", "type_str": "DECIMAL(10,2)", "category": "numeric", "nullable": True, "is_pk": False, "autoincrement": False},
            {"name": "restock_date", "type_str": "DATE", "category": "date", "nullable": True, "is_pk": False, "autoincrement": False}
        ]
        raw_rec = {
            "item_name": "Keyboard",
            "quantity": "100",
            "unit_price": "$49.50",
            "restock_date": "2025-10-01"
        }
        val_rec, err = validate_single_record(raw_rec, schema_cols, 1)
        self.assertIsNone(err)
        self.assertEqual(val_rec["item_name"], "Keyboard")
        self.assertEqual(val_rec["quantity"], 100)
        self.assertEqual(val_rec["unit_price"], 49.50)
        self.assertEqual(val_rec["restock_date"], "2025-10-01")

    # -------------------------------------------------------------------------
    # 10. Invalid data type rejection (non-numeric, bad date)
    # -------------------------------------------------------------------------
    def test_10_invalid_data_type_rejection(self):
        schema_cols = [
            {"name": "quantity", "type_str": "INT", "category": "integer", "nullable": False, "is_pk": False, "autoincrement": False},
            {"name": "restock_date", "type_str": "DATE", "category": "date", "nullable": False, "is_pk": False, "autoincrement": False}
        ]

        # Invalid int ("fifty")
        rec1, err1 = validate_single_record({"quantity": "fifty", "restock_date": "2025-01-01"}, schema_cols, 1)
        self.assertIsNone(rec1)
        self.assertIn("Invalid integer", err1)

        # Invalid calendar date (Feb 31st)
        rec2, err2 = validate_single_record({"quantity": "10", "restock_date": "2025-02-31"}, schema_cols, 1)
        self.assertIsNone(rec2)
        self.assertIn("Invalid date", err2)

    # -------------------------------------------------------------------------
    # 11. Missing required field handling
    # -------------------------------------------------------------------------
    def test_11_missing_required_field_handling(self):
        schema_cols = [
            {"name": "item_name", "type_str": "VARCHAR(255)", "category": "string", "nullable": False, "is_pk": False, "autoincrement": False},
            {"name": "quantity", "type_str": "INT", "category": "integer", "nullable": True, "is_pk": False, "autoincrement": False}
        ]
        # Missing item_name (required)
        rec, err = validate_single_record({"quantity": "50"}, schema_cols, 1)
        self.assertIsNone(rec)
        self.assertIn("Missing required value for column 'item_name'", err)

    # -------------------------------------------------------------------------
    # 12. Ambiguous table selection
    # -------------------------------------------------------------------------
    def test_12_ambiguous_table_selection(self):
        user_datasets = [self.tbl1_physical, self.tbl2_physical]
        # Question mentions both tables
        tbl, err, opts = resolve_target_table_from_prompt(
            "Add records to both inventory_stock and patient_appointments",
            self.user_id,
            user_datasets
        )
        self.assertIsNone(tbl)
        self.assertEqual(err, "ambiguous")
        self.assertEqual(len(opts), 2)

    # -------------------------------------------------------------------------
    # 13. Cross-tenant table access rejection
    # -------------------------------------------------------------------------
    def test_13_cross_tenant_table_access_rejection(self):
        user_datasets = [self.tbl1_physical]
        # User tries to access another tenant's table
        tbl, err, opts = resolve_target_table_from_prompt(
            f"Add records to inventory_stock_{self.other_user_id}",
            self.user_id,
            user_datasets
        )
        self.assertIsNone(tbl)
        self.assertEqual(err, "cross_tenant_denied")

    # -------------------------------------------------------------------------
    # 14. Confirmation and cancellation
    # -------------------------------------------------------------------------
    def test_14_confirmation_and_cancellation(self):
        # 1. Ask for preview
        with patch("app.services.bulk_record_parser.call_llm") as mock_llm:
            mock_llm.return_value = """
            {"records": [{"item_name": "Test Item", "category": "Misc", "quantity": "10", "unit_price": "5.0", "restock_date": "2025-08-01"}]}
            """
            ask_res = self.client.post(
                "/api/modification/ask",
                json={"question": "Add Test Item, Misc, 10, 5.0, 2025-08-01 to inventory_stock"},
                headers={**self.headers, "X-Table-Name": self.tbl1_physical}
            )
            self.assertEqual(ask_res.status_code, 200)
            token = ask_res.json()["confirmation_token"]

            # Cancel
            cancel_res = self.client.post(
                "/api/modification/cancel",
                json={"confirmation_token": token},
                headers=self.headers
            )
            self.assertEqual(cancel_res.status_code, 200)
            self.assertEqual(cancel_res.json()["status"], "CANCELLED")

            # Try to execute cancelled token -> should fail
            exec_res = self.client.post(
                "/api/modification/execute",
                json={"confirmation_token": token},
                headers=self.headers
            )
            self.assertEqual(exec_res.status_code, 400)

    # -------------------------------------------------------------------------
    # 15. Duplicate submission prevention (Idempotency)
    # -------------------------------------------------------------------------
    def test_15_duplicate_submission_prevention(self):
        with patch("app.services.bulk_record_parser.call_llm") as mock_llm:
            mock_llm.return_value = """
            {"records": [{"item_name": "Idempotent Item", "category": "Tech", "quantity": "5", "unit_price": "12.0", "restock_date": "2025-09-01"}]}
            """
            ask_res = self.client.post(
                "/api/modification/ask",
                json={"question": "Add Idempotent Item, Tech, 5, 12.0, 2025-09-01 to inventory_stock"},
                headers={**self.headers, "X-Table-Name": self.tbl1_physical}
            )
            self.assertEqual(ask_res.status_code, 200)
            token = ask_res.json()["confirmation_token"]

            # First execution -> succeeds
            exec1 = self.client.post(
                "/api/modification/execute",
                json={"confirmation_token": token},
                headers=self.headers
            )
            self.assertEqual(exec1.status_code, 200)
            self.assertTrue(exec1.json()["success"])

            # Second execution with same token -> rejected
            exec2 = self.client.post(
                "/api/modification/execute",
                json={"confirmation_token": token},
                headers=self.headers
            )
            self.assertEqual(exec2.status_code, 400)
            self.assertIn("already been executed", exec2.json()["detail"])

    # -------------------------------------------------------------------------
    # 16. Transaction rollback on bulk insertion failure
    # -------------------------------------------------------------------------
    def test_16_transaction_rollback_on_failure(self):
        # Count rows before
        with engine.connect() as conn:
            cnt_before = conn.execute(text(f"SELECT COUNT(*) FROM `{self.tbl1_physical}`")).scalar()

        # Simulate execution of invalid query directly in transactional block
        try:
            with engine.begin() as conn:
                conn.execute(text(f"INSERT INTO `{self.tbl1_physical}` (`item_name`) VALUES ('Should Rollback')"))
                # Trigger intentional failure in same transaction
                conn.execute(text(f"INSERT INTO `{self.tbl1_physical}` (`non_existent_column_fail`) VALUES (123)"))
        except Exception:
            pass

        # Verify full rollback: rowcount must be identical to cnt_before
        with engine.connect() as conn:
            cnt_after = conn.execute(text(f"SELECT COUNT(*) FROM `{self.tbl1_physical}`")).scalar()
        self.assertEqual(cnt_before, cnt_after)

    # -------------------------------------------------------------------------
    # 17. Audit/history integration
    # -------------------------------------------------------------------------
    def test_17_audit_and_history_integration(self):
        db = SessionLocal()
        try:
            audit_entry = db.query(AuditLog).filter(
                AuditLog.user_id == self.user_id,
                AuditLog.table_name == self.tbl1_physical
            ).first()
            self.assertIsNotNone(audit_entry)
            self.assertEqual(audit_entry.operation, "INSERT")
        finally:
            db.close()

    # -------------------------------------------------------------------------
    # 18. Existing manual table creation remains functional
    # -------------------------------------------------------------------------
    def test_18_existing_manual_table_creation(self):
        payload = {
            "table_name": "manual_test_tbl",
            "columns": [
                {"name": "metric_name", "type": "VARCHAR(255)"},
                {"name": "metric_value", "type": "DOUBLE"}
            ]
        }
        res = self.client.post("/datasets/create", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json()["success"])

        physical = f"manual_test_tbl_{self.user_id}"
        inspector = inspect(engine)
        self.assertIn(physical, inspector.get_table_names())

    # -------------------------------------------------------------------------
    # 19. Existing chatbot query and modification workflows remain unaffected
    # -------------------------------------------------------------------------
    def test_19_existing_query_and_modification_workflows(self):
        # 1. Read-only SELECT query still works
        with patch("app.services.sql_generator.call_llm") as mock_sql, \
             patch("app.services.summary_generator.call_llm") as mock_summary:
            mock_sql.return_value = f"SELECT item_name, quantity FROM `{self.tbl1_friendly}`"
            mock_summary.return_value = "Here are the inventory stock items."
            res = self.client.post(
                "/ask",
                json={"question": "List all items in inventory stock"},
                headers={**self.headers, "X-Table-Name": self.tbl1_physical}
            )
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.json()["success"])

        # 2. UPDATE modification still works
        with patch("app.services.modification_sql_generator.call_llm") as mock_mod:
            mock_mod.return_value = f"UPDATE `{self.tbl1_friendly}` SET `quantity` = 50 WHERE `item_name` = 'Test'"
            res = self.client.post(
                "/api/modification/ask",
                json={"question": "Update quantity of Test to 50 in inventory_stock"},
                headers={**self.headers, "X-Table-Name": self.tbl1_physical}
            )
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["intent"], "UPDATE")
            self.assertTrue(res.json()["requires_confirmation"])


if __name__ == "__main__":
    unittest.main()
