"""
PromptSQL — Comprehensive Independent Tenant Isolation & Access Control Security Test Suite

Covers the complete verification matrix:
1. Cross-tenant saved reports isolation (create, list, get, update, delete, export).
2. Cross-tenant audit records isolation (list, delete).
3. Cross-tenant query history isolation (list, undo, delete).
4. Cross-tenant dataset activation denial (/datasets/active).
5. System tables protection through dataset creation and deletion.
6. Cross-tenant nested JOIN queries rejection.
7. Cross-tenant CTE (Common Table Expressions) rejection.
8. Authorization bypass prevention using SQL aliases.
9. Every data cleaning endpoint rejection of unauthorized datasets and system tables.
10. Every report endpoint user ownership enforcement.
11. Invalid and forged table identifier rejection.
12. Consistent authentication failure handling across endpoints.
"""

import os
import sys

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
import json
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app.database.connection import engine, SessionLocal
from app.models.report import SavedReport
from app.models.history import QueryHistory
from app.models.audit_log import AuditLog
from app.services.auth_service import create_access_token
from app.services.dataset_guard import (
    resolve_and_authorize_dataset,
    verify_all_referenced_tables,
    is_system_table,
    validate_table_identifier_format
)
from app.services.sql_validator import validate_sql
from fastapi import HTTPException


class TestTenantIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

        # Isolated test user IDs (numeric IDs passed to JWT generator)
        cls.user_a_num = 99901
        cls.user_b_num = 99902
        cls.user_a_id = f"usr_{cls.user_a_num}"
        cls.user_b_id = f"usr_{cls.user_b_num}"

        # Generate Bearer tokens
        cls.token_a = create_access_token(cls.user_a_num)
        cls.token_b = create_access_token(cls.user_b_num)
        cls.headers_a = {"Authorization": f"Bearer {cls.token_a}"}
        cls.headers_b = {"Authorization": f"Bearer {cls.token_b}"}

        # Isolated physical test tables for User A and User B
        cls.table_a = f"test_sales_{cls.user_a_id}"
        cls.table_b = f"test_orders_{cls.user_b_id}"

        # Create temporary isolated tables in DB
        with engine.begin() as conn:
            conn.execute(text("SET SESSION sql_require_primary_key = 0"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_a}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_b}`"))

            conn.execute(text(f"""
                CREATE TABLE `{cls.table_a}` (
                    id INT,
                    product VARCHAR(255),
                    amount DOUBLE
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.table_a}` (id, product, amount) VALUES
                (1, 'Laptop', 1200.0),
                (2, 'Mouse', 25.0),
                (2, 'Mouse', 25.0)
            """))

            conn.execute(text(f"""
                CREATE TABLE `{cls.table_b}` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    customer VARCHAR(255),
                    total DOUBLE
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.table_b}` (customer, total) VALUES
                ('Alice', 500.0),
                ('Bob', 750.0)
            """))

        # Seed isolated test records in application system tables
        db = SessionLocal()
        try:
            # User B's saved report
            cls.report_b = SavedReport(
                user_id=cls.user_b_id,
                title="User B Secret Report",
                table_name=cls.table_b,
                question="What are total sales?",
                generated_sql=f"SELECT * FROM `{cls.table_b}`",
                summary="User B sensitive summary data",
                result_json=json.dumps([{"customer": "Alice", "total": 500.0}])
            )
            db.add(cls.report_b)

            # User B's audit log
            cls.audit_b = AuditLog(
                user_id=cls.user_b_id,
                operation="INSERT",
                table_name=cls.table_b,
                generated_sql=f"INSERT INTO `{cls.table_b}` VALUES (3, 'Secret', 999)",
                rows_affected=1,
                status="SUCCESS"
            )
            db.add(cls.audit_b)

            # User B's query history
            cls.history_b = QueryHistory(
                user_id=cls.user_b_id,
                table_name=cls.table_b,
                question="Show User B customer records",
                generated_sql=f"SELECT * FROM `{cls.table_b}`",
                summary="User B private query result",
                result_count=2,
                result_json=json.dumps([{"customer": "Alice", "total": 500.0}]),
                undo_sql=f"DELETE FROM `{cls.table_b}` WHERE id = 3"
            )
            db.add(cls.history_b)
            db.commit()

            cls.report_b_id = cls.report_b.id
            cls.audit_b_id = cls.audit_b.id
            cls.history_b_id = cls.history_b.id
        finally:
            db.close()

    @classmethod
    def tearDownClass(cls):
        # Drop temporary isolated test tables
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_a}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_b}`"))

        # Clean up seeded system table records
        db = SessionLocal()
        try:
            db.query(SavedReport).filter(SavedReport.user_id.in_([cls.user_a_id, cls.user_b_id])).delete(synchronize_session=False)
            db.query(AuditLog).filter(AuditLog.user_id.in_([cls.user_a_id, cls.user_b_id])).delete(synchronize_session=False)
            db.query(QueryHistory).filter(QueryHistory.user_id.in_([cls.user_a_id, cls.user_b_id])).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    # =========================================================================
    # 1. CROSS-TENANT SAVED REPORTS ISOLATION
    # =========================================================================

    def test_01_user_a_cannot_access_user_b_saved_reports(self):
        """User A cannot view, retrieve, edit, delete, or export User B's saved reports."""
        # 1. Listing reports: User A does not see User B's report
        list_resp = self.client.get("/api/reports", headers=self.headers_a)
        self.assertEqual(list_resp.status_code, 200)
        report_ids = [r["id"] for r in list_resp.json()]
        self.assertNotIn(self.report_b_id, report_ids)

        # 2. Detail: User A gets 404 for User B's report
        detail_resp = self.client.get(f"/api/reports/{self.report_b_id}", headers=self.headers_a)
        self.assertEqual(detail_resp.status_code, 404)

        # 3. Rename: User A cannot rename User B's report
        rename_resp = self.client.put(
            f"/api/reports/{self.report_b_id}",
            json={"title": "Hacked Title"},
            headers=self.headers_a
        )
        self.assertEqual(rename_resp.status_code, 404)

        # 4. Export: User A cannot export User B's report
        export_resp = self.client.get(f"/api/reports/{self.report_b_id}/export/csv", headers=self.headers_a)
        self.assertEqual(export_resp.status_code, 404)

        # 5. Delete: User A cannot delete User B's report
        del_resp = self.client.delete(f"/api/reports/{self.report_b_id}", headers=self.headers_a)
        self.assertEqual(del_resp.status_code, 404)

    # =========================================================================
    # 2. CROSS-TENANT AUDIT RECORDS ISOLATION
    # =========================================================================

    def test_02_user_a_cannot_access_user_b_audit_records(self):
        """User A cannot list or delete User B's audit log records."""
        # 1. Listing audit logs: User A does not see User B's audit log
        list_resp = self.client.get("/api/audit", headers=self.headers_a)
        self.assertEqual(list_resp.status_code, 200)
        audit_ids = [a["id"] for a in list_resp.json()]
        self.assertNotIn(self.audit_b_id, audit_ids)

        # 2. Delete: User A cannot delete User B's audit log
        del_resp = self.client.delete(f"/api/audit/{self.audit_b_id}", headers=self.headers_a)
        self.assertEqual(del_resp.status_code, 404)

    # =========================================================================
    # 3. CROSS-TENANT QUERY HISTORY ISOLATION
    # =========================================================================

    def test_03_user_a_cannot_access_user_b_query_history(self):
        """User A cannot list, undo, or delete User B's query history."""
        # 1. Listing history: User A does not see User B's history
        list_resp = self.client.get("/api/history", headers=self.headers_a)
        self.assertEqual(list_resp.status_code, 200)
        history_ids = [h["id"] for h in list_resp.json()]
        self.assertNotIn(self.history_b_id, history_ids)

        # 2. Undo: User A cannot trigger undo on User B's history
        undo_resp = self.client.post(f"/api/history/{self.history_b_id}/undo", headers=self.headers_a)
        self.assertEqual(undo_resp.status_code, 404)

        # 3. Delete: User A cannot delete User B's history
        del_resp = self.client.delete(f"/api/history/{self.history_b_id}", headers=self.headers_a)
        self.assertEqual(del_resp.status_code, 404)

    # =========================================================================
    # 4. CROSS-TENANT DATASET ACTIVATION DENIAL
    # =========================================================================

    def test_04_user_a_cannot_activate_user_b_dataset(self):
        """User A cannot set User B's dataset as active."""
        resp = self.client.post(
            "/datasets/active",
            json={"table_name": self.table_b},
            headers=self.headers_a
        )
        self.assertEqual(resp.status_code, 403)

    # =========================================================================
    # 5. SYSTEM TABLE PROTECTION THROUGH DATASET CREATION OR DELETION
    # =========================================================================

    def test_05_system_table_protection_dataset_creation_and_deletion(self):
        """System tables cannot be overwritten via creation or dropped via dataset deletion."""
        protected_names = ["users", "query_history", "audit_logs", "saved_reports"]

        for sys_name in protected_names:
            # Creation attempt with system table name
            create_resp = self.client.post(
                "/datasets/create",
                json={
                    "table_name": sys_name,
                    "columns": [{"name": "fake_col", "type": "VARCHAR(255)"}]
                },
                headers=self.headers_a
            )
            self.assertIn(create_resp.status_code, [400, 403], f"Failed blocking creation of {sys_name}")

            # Deletion attempt on system table
            del_resp = self.client.delete(f"/datasets/{sys_name}", headers=self.headers_a)
            self.assertEqual(del_resp.status_code, 403, f"Failed blocking deletion of {sys_name}")

    # =========================================================================
    # 6. NESTED JOINS REFERENCING ANOTHER TENANT'S DATASET
    # =========================================================================

    def test_06_cannot_access_other_dataset_through_nested_joins(self):
        """Nested JOINs referencing another tenant's dataset are blocked."""
        nested_join_query = (
            f"SELECT a.*, sub.total FROM `{self.table_a}` a "
            f"JOIN (SELECT id, total FROM `{self.table_b}`) sub ON a.id = sub.id"
        )
        # 1. Guard check
        with self.assertRaises(HTTPException) as cm:
            verify_all_referenced_tables(nested_join_query, self.user_a_id, [self.table_a])
        self.assertEqual(cm.exception.status_code, 403)

        # 2. Validator check
        valid, msg = validate_sql(nested_join_query, [self.table_a])
        self.assertFalse(valid)
        self.assertNotIn(self.table_b, msg)

    # =========================================================================
    # 7. CTEs REFERENCING ANOTHER TENANT'S DATASET
    # =========================================================================

    def test_07_cannot_access_other_dataset_through_ctes(self):
        """Common Table Expressions (CTEs) referencing another tenant's dataset are blocked."""
        cte_query = (
            f"WITH stolen AS (SELECT * FROM `{self.table_b}`) "
            f"SELECT a.*, s.total FROM `{self.table_a}` a JOIN stolen s ON a.id = s.id"
        )
        # 1. Guard check
        with self.assertRaises(HTTPException) as cm:
            verify_all_referenced_tables(cte_query, self.user_a_id, [self.table_a])
        self.assertEqual(cm.exception.status_code, 403)

        # 2. Validator check
        valid, msg = validate_sql(cte_query, [self.table_a])
        self.assertFalse(valid)
        self.assertNotIn(self.table_b, msg)

    # =========================================================================
    # 8. SQL ALIASES CANNOT BYPASS AUTHORIZATION
    # =========================================================================

    def test_08_cannot_bypass_authorization_using_sql_aliases(self):
        """Aliases on unauthorized tables or aliasing as system tables are strictly blocked."""
        alias_query_1 = f"SELECT x.customer FROM `{self.table_b}` AS x"
        with self.assertRaises(HTTPException) as cm:
            verify_all_referenced_tables(alias_query_1, self.user_a_id, [self.table_a])
        self.assertEqual(cm.exception.status_code, 403)

        alias_query_2 = f"SELECT u.* FROM `{self.table_a}` AS users"
        with self.assertRaises(HTTPException) as cm:
            verify_all_referenced_tables(alias_query_2, self.user_a_id, [self.table_a])
        self.assertEqual(cm.exception.status_code, 403)

    # =========================================================================
    # 9. EVERY CLEANING ENDPOINT REJECTS UNAUTHORIZED DATASETS
    # =========================================================================

    def test_09_every_cleaning_endpoint_rejects_unauthorized_datasets(self):
        """All 9 data-cleaning endpoints reject unauthorized cross-tenant tables and system tables."""
        targets = [self.table_b, "users", "query_history", "saved_reports"]

        cleaning_endpoints = [
            ("post", "/api/clean/remove-duplicates", None),
            ("post", "/api/clean/impute", {"column_name": "product", "strategy": "drop"}),
            ("get",  "/api/clean/locate-missing?column_name=product", None),
            ("post", "/api/clean/update-cell", {"column_name": "product", "new_value": "test", "row_data": {"id": 1}}),
            ("post", "/api/clean/convert-type", {"column_name": "product", "target_type": "text"}),
            ("post", "/api/clean/standardize-text", {"column_name": "product", "operation": "trim"}),
            ("post", "/api/clean/extract-numbers", {"column_name": "amount"}),
            ("get",  "/api/clean/detect-numeric-text", None),
            ("post", "/api/clean/extract-and-convert", {"column_name": "amount"}),
        ]

        for target in targets:
            headers = {**self.headers_a, "X-Table-Name": target}
            for method, url, payload in cleaning_endpoints:
                if method == "get":
                    resp = self.client.get(url, headers=headers)
                else:
                    resp = self.client.post(url, json=payload or {}, headers=headers)
                self.assertEqual(
                    resp.status_code, 403,
                    f"Cleaner endpoint {url} failed to return 403 for target '{target}' (got {resp.status_code})"
                )

    # =========================================================================
    # 10. EVERY REPORT ENDPOINT ENFORCES USER OWNERSHIP
    # =========================================================================

    def test_10_every_report_endpoint_enforces_user_ownership(self):
        """Creating reports requires ownership of the dataset; all report CRUD strictly enforces user."""
        # 1. Attempt creating report referencing User B's dataset -> 403 Forbidden
        create_b_resp = self.client.post(
            "/api/reports",
            json={
                "title": "Unauthorized Report",
                "table_name": self.table_b,
                "question": "Steal data",
                "generated_sql": f"SELECT * FROM `{self.table_b}`",
                "summary": "hacked",
                "records": []
            },
            headers=self.headers_a
        )
        self.assertEqual(create_b_resp.status_code, 403)

        # 2. Attempt creating report referencing system table 'users' -> 403 Forbidden
        create_sys_resp = self.client.post(
            "/api/reports",
            json={
                "title": "System Table Report",
                "table_name": "users",
                "question": "Steal passwords",
                "generated_sql": "SELECT * FROM `users`",
                "summary": "passwords",
                "records": []
            },
            headers=self.headers_a
        )
        self.assertEqual(create_sys_resp.status_code, 403)

        # 3. Legitimate creation under own dataset succeeds
        create_ok_resp = self.client.post(
            "/api/reports",
            json={
                "title": "User A Legitimate Report",
                "table_name": self.table_a,
                "question": "User A question",
                "generated_sql": f"SELECT * FROM `{self.table_a}`",
                "summary": "Summary",
                "records": [{"id": 1, "product": "Laptop"}]
            },
            headers=self.headers_a
        )
        self.assertEqual(create_ok_resp.status_code, 200)
        report_a_id = create_ok_resp.json()["id"]

        # 4. User B cannot access User A's newly created report
        detail_b = self.client.get(f"/api/reports/{report_a_id}", headers=self.headers_b)
        self.assertEqual(detail_b.status_code, 404)

        export_b = self.client.get(f"/api/reports/{report_a_id}/export/pdf", headers=self.headers_b)
        self.assertEqual(export_b.status_code, 404)

        del_b = self.client.delete(f"/api/reports/{report_a_id}", headers=self.headers_b)
        self.assertEqual(del_b.status_code, 404)

    # =========================================================================
    # 11. INVALID AND FORGED TABLE IDENTIFIERS REJECTED
    # =========================================================================

    def test_11_invalid_or_forged_table_identifiers_rejected(self):
        """Path traversal, injected SQL tokens, and malformed strings are rejected."""
        malicious_inputs = [
            "table; DROP TABLE users;--",
            "table' OR '1'='1",
            "table` WHERE 1=1",
            "../secret_file",
            "../../etc/passwd",
            "table/**/UNION/**/SELECT",
            "@@version",
            "select 1",
            "a" * 65  # exceeds 64 characters
        ]
        for bad_id in malicious_inputs:
            headers = {**self.headers_a, "X-Table-Name": bad_id}
            resp = self.client.get("/preview", headers=headers)
            self.assertIn(
                resp.status_code, [400, 403],
                f"Expected 400 or 403 for malformed identifier '{bad_id}', got {resp.status_code}"
            )

    # =========================================================================
    # 12. CONSISTENT AUTHENTICATION FAILURE HANDLING
    # =========================================================================

    def test_12_authentication_failures_handled_consistently(self):
        """Unauthenticated, invalid format, or forged tokens receive 401 across all protected routes."""
        test_routes = [
            ("get",  "/preview"),
            ("get",  "/datasets"),
            ("post", "/datasets/active"),
            ("delete", f"/datasets/{self.table_a}"),
            ("post", "/ask"),
            ("get",  "/api/export/raw/csv"),
            ("get",  "/api/export/raw/excel"),
            ("post", "/api/clean/remove-duplicates"),
            ("get",  "/api/history"),
            ("get",  "/api/reports"),
            ("get",  "/api/audit"),
            ("post", "/api/modification/execute"),
        ]

        # Case 1: Missing Authorization header
        for method, route in test_routes:
            if method == "get":
                resp = self.client.get(route)
            elif method == "post":
                resp = self.client.post(route, json={})
            else:
                resp = self.client.delete(route)
            self.assertEqual(resp.status_code, 401, f"Route {route} did not return 401 when unauthenticated")

        # Case 2: Invalid Bearer token format
        bad_format_headers = {"Authorization": "Basic 123456"}
        resp = self.client.get("/preview", headers=bad_format_headers)
        self.assertEqual(resp.status_code, 401)

        # Case 3: Forged / invalid signature token
        forged_headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.bogussignature"}
        resp = self.client.get("/preview", headers=forged_headers)
        self.assertEqual(resp.status_code, 401)

    # =========================================================================
    # POSITIVE BASELINE TESTS
    # =========================================================================

    def test_13_positive_user_a_and_b_baseline_operations(self):
        """User A and User B can perform all legitimate operations on their own datasets."""
        # User A preview & list
        headers_a = {**self.headers_a, "X-Table-Name": self.table_a}
        resp_a = self.client.get("/preview", headers=headers_a)
        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(resp_a.json().get("total_rows"), 3)

        list_a = self.client.get("/datasets", headers=self.headers_a)
        self.assertIn(self.table_a, list_a.json().get("datasets", []))

        # User A export CSV
        exp_a = self.client.get("/api/export/raw/csv", headers=headers_a)
        self.assertEqual(exp_a.status_code, 200)

        # User A clean (remove duplicates)
        clean_a = self.client.post("/api/clean/remove-duplicates", headers=headers_a)
        self.assertEqual(clean_a.status_code, 200)
        self.assertTrue(clean_a.json().get("success"))

        # User A preview modification
        from unittest.mock import patch, MagicMock
        mock_groq = MagicMock()
        def fake_create(**kwargs):
            messages = kwargs.get("messages", [])
            sys_msg = messages[0]["content"].lower() if messages else ""
            res = MagicMock()
            if "intent" in sys_msg:
                content = "UPDATE"
            elif "impact" in sys_msg or "explain" in sys_msg:
                content = "This will update 1 row."
            else:
                content = f"UPDATE `{self.table_a}` SET amount = 1250.0 WHERE product = 'Laptop'"
            res.choices = [MagicMock(message=MagicMock(content=content))]
            return res

        mock_groq.return_value.chat.completions.create.side_effect = fake_create

        with patch("app.services.llm_service.Groq", mock_groq):
            prev_a = self.client.post(
                "/api/modification/ask",
                json={"question": "Update price of Laptop to 1250"},
                headers=headers_a
            )
            self.assertEqual(prev_a.status_code, 200)
            token_a = prev_a.json().get("confirmation_token")
            self.assertTrue(token_a)

            # User A execute modification with confirmation token
            mod_a = self.client.post(
                "/api/modification/execute",
                json={"confirmation_token": token_a},
                headers=self.headers_a
            )
            self.assertEqual(mod_a.status_code, 200)
            self.assertTrue(mod_a.json().get("success"))


if __name__ == "__main__":
    unittest.main()
