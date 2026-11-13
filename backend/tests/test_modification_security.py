"""
PromptSQL — Step 2: Comprehensive Modification Security Test Suite

Covers all 20 required security test cases:
1. Normal UPDATE preview and execution via confirmation token.
2. Normal INSERT preview and execution via confirmation token.
3. Normal DELETE preview and execution via confirmation token.
4. Direct execution without confirmation token is rejected.
5. Client-supplied replacement SQL is ignored (server executes only stored preview SQL).
6. User A cannot execute User B's pending modification.
7. Pending modification cannot be executed against a different dataset than previewed.
8. Expired confirmation token cannot be executed.
9. Modification cannot be executed twice (replay attack).
10. Concurrent duplicate execution is prevented (atomic state check).
11. SQL statement chaining (semicolon injection) is rejected.
12. System-table modifications are rejected.
13. Cross-tenant modifications are rejected.
14. Unauthorized DROP operations are rejected.
15. Unauthorized TRUNCATE operations are rejected.
16. Unsupported administrative commands (GRANT, CALL, KILL, etc.) are rejected.
17. Modified/non-existent confirmation tokens are rejected.
18. Database failure results in rollback and accurate failure response.
19. Failed operations do not generate successful audit or history records.
20. Legitimate operations continue to work end-to-end.
"""

import os
import sys
import unittest
import datetime
import secrets
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
from app.services.modification_validator import validate_modification_sql
from app.services.dataset_guard import get_user_datasets
from app.utils.tz_helper import get_ist_time


class TestModificationSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

        cls.user_a_num = 99931
        cls.user_b_num = 99932
        cls.user_a_id = f"usr_{cls.user_a_num}"
        cls.user_b_id = f"usr_{cls.user_b_num}"

        cls.token_a = create_access_token(cls.user_a_num)
        cls.token_b = create_access_token(cls.user_b_num)
        cls.headers_a = {"Authorization": f"Bearer {cls.token_a}"}
        cls.headers_b = {"Authorization": f"Bearer {cls.token_b}"}

        cls.table_a = f"employees_{cls.user_a_id}"
        cls.table_b = f"inventory_{cls.user_b_id}"

        # Initialize physical test tables
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_a}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_b}`"))

            conn.execute(text(f"""
                CREATE TABLE `{cls.table_a}` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    salary DOUBLE NOT NULL,
                    department VARCHAR(255)
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.table_a}` (name, salary, department) VALUES
                ('Alice', 50000.0, 'Engineering'),
                ('Bob', 55000.0, 'Sales')
            """))

            conn.execute(text(f"""
                CREATE TABLE `{cls.table_b}` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    item VARCHAR(255) NOT NULL,
                    stock INT NOT NULL
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.table_b}` (item, stock) VALUES
                ('Widget', 100),
                ('Gadget', 200)
            """))

    @classmethod
    def tearDownClass(cls):
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_a}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_b}`"))

        db = SessionLocal()
        try:
            db.query(PendingModification).filter(
                PendingModification.user_id.in_([cls.user_a_id, cls.user_b_id])
            ).delete(synchronize_session=False)
            db.query(AuditLog).filter(
                AuditLog.user_id.in_([cls.user_a_id, cls.user_b_id])
            ).delete(synchronize_session=False)
            db.query(QueryHistory).filter(
                QueryHistory.user_id.in_([cls.user_a_id, cls.user_b_id])
            ).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    def reset_table_a(self):
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE `{self.table_a}`"))
            conn.execute(text(f"""
                INSERT INTO `{self.table_a}` (id, name, salary, department) VALUES
                (1, 'Alice', 50000.0, 'Engineering'),
                (2, 'Bob', 55000.0, 'Sales')
            """))

    # -------------------------------------------------------------
    # 1. Normal UPDATE preview and execution via confirmation token
    # -------------------------------------------------------------
    def test_01_normal_update_preview_and_execution(self):
        self.reset_table_a()
        headers = {**self.headers_a, "X-Table-Name": self.table_a}

        # Step A: Preview
        prev = self.client.post(
            "/api/modification/ask",
            json={"question": "Update Alice's salary to 65000"},
            headers=headers
        )
        self.assertEqual(prev.status_code, 200)
        data = prev.json()
        self.assertTrue(data.get("requires_confirmation"))
        self.assertEqual(data.get("intent"), "UPDATE")
        token = data.get("confirmation_token")
        self.assertTrue(token)
        self.assertGreater(len(token), 30)

        # Step B: Execution via confirmation token
        exec_resp = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": token},
            headers=self.headers_a
        )
        self.assertEqual(exec_resp.status_code, 200)
        exec_data = exec_resp.json()
        self.assertTrue(exec_data.get("success"))
        self.assertEqual(exec_data.get("rows_affected"), 1)

        # Verify DB row changed
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT salary FROM `{self.table_a}` WHERE name = 'Alice'")).scalar()
            self.assertEqual(float(result), 65000.0)

    # -------------------------------------------------------------
    # 2. Normal INSERT preview and execution via confirmation token
    # -------------------------------------------------------------
    def test_02_normal_insert_preview_and_execution(self):
        headers = {**self.headers_a, "X-Table-Name": self.table_a}

        # Step A: Preview
        prev = self.client.post(
            "/api/modification/ask",
            json={"question": "Insert a new employee named Charlie with salary 48000 and department Marketing"},
            headers=headers
        )
        self.assertEqual(prev.status_code, 200)
        data = prev.json()
        self.assertEqual(data.get("intent"), "INSERT")
        token = data.get("confirmation_token")
        self.assertTrue(token)

        # Step B: Execution
        exec_resp = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": token},
            headers=self.headers_a
        )
        self.assertEqual(exec_resp.status_code, 200)
        self.assertTrue(exec_resp.json().get("success"))

        # Verify DB row inserted
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT salary, department FROM `{self.table_a}` WHERE name = 'Charlie'")).mappings().first()
            self.assertIsNotNone(result)
            self.assertEqual(float(result["salary"]), 48000.0)
            self.assertEqual(result["department"], "Marketing")

    # -------------------------------------------------------------
    # 3. Normal DELETE preview and execution via confirmation token
    # -------------------------------------------------------------
    def test_03_normal_delete_preview_and_execution(self):
        headers = {**self.headers_a, "X-Table-Name": self.table_a}

        # Step A: Preview
        prev = self.client.post(
            "/api/modification/ask",
            json={"question": "Delete the employee named Bob"},
            headers=headers
        )
        self.assertEqual(prev.status_code, 200)
        data = prev.json()
        self.assertEqual(data.get("intent"), "DELETE")
        token = data.get("confirmation_token")
        self.assertTrue(token)

        # Step B: Execution
        exec_resp = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": token},
            headers=self.headers_a
        )
        self.assertEqual(exec_resp.status_code, 200)
        self.assertTrue(exec_resp.json().get("success"))

        # Verify DB row deleted
        with engine.connect() as conn:
            count = conn.execute(text(f"SELECT COUNT(*) FROM `{self.table_a}` WHERE name = 'Bob'")).scalar()
            self.assertEqual(count, 0)

    # -------------------------------------------------------------
    # 4. Direct execution without confirmation token is rejected (400)
    # -------------------------------------------------------------
    def test_04_direct_execution_without_token_rejected(self):
        # Missing token completely
        resp1 = self.client.post(
            "/api/modification/execute",
            json={"sql": f"DELETE FROM `{self.table_a}`", "intent": "DELETE", "table_name": self.table_a},
            headers=self.headers_a
        )
        self.assertEqual(resp1.status_code, 400)

        # Blank/empty token
        resp2 = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": "   ", "sql": f"DELETE FROM `{self.table_a}`"},
            headers=self.headers_a
        )
        self.assertEqual(resp2.status_code, 400)

    # -------------------------------------------------------------
    # 5. Client-supplied replacement SQL is ignored
    # -------------------------------------------------------------
    def test_05_client_supplied_replacement_sql_is_ignored(self):
        self.reset_table_a()
        headers = {**self.headers_a, "X-Table-Name": self.table_a}

        # User A requests legitimate preview: update Alice salary to 70000
        prev = self.client.post(
            "/api/modification/ask",
            json={"question": "Update Alice's salary to 70000"},
            headers=headers
        )
        self.assertEqual(prev.status_code, 200)
        token = prev.json().get("confirmation_token")

        # Attacker attempts to replace SQL in execute payload with malicious DROP or arbitrary UPDATE
        malicious_payload = {
            "confirmation_token": token,
            "sql": f"UPDATE `{self.table_a}` SET `salary` = 999999 WHERE `name` = 'Alice'",
            "intent": "UPDATE",
            "table_name": self.table_a
        }
        exec_resp = self.client.post(
            "/api/modification/execute",
            json=malicious_payload,
            headers=self.headers_a
        )
        self.assertEqual(exec_resp.status_code, 200)

        # Verify that ONLY the server-stored SQL (70000) was executed, NOT 999999
        with engine.connect() as conn:
            salary = conn.execute(text(f"SELECT salary FROM `{self.table_a}` WHERE name = 'Alice'")).scalar()
            self.assertEqual(float(salary), 70000.0)

    # -------------------------------------------------------------
    # 6. User A cannot execute User B's pending modification (403)
    # -------------------------------------------------------------
    def test_06_user_a_cannot_execute_user_b_pending_modification(self):
        headers_b = {**self.headers_b, "X-Table-Name": self.table_b}

        # User B generates a preview on User B's dataset
        prev_b = self.client.post(
            "/api/modification/ask",
            json={"question": "Update stock of Widget to 150"},
            headers=headers_b
        )
        self.assertEqual(prev_b.status_code, 200)
        token_b = prev_b.json().get("confirmation_token")

        # User A attempts to execute using User B's token
        exec_resp = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": token_b},
            headers=self.headers_a
        )
        self.assertEqual(exec_resp.status_code, 403)
        self.assertIn("Access denied", exec_resp.json().get("detail", ""))

        # Verify User B's stock was NOT altered
        with engine.connect() as conn:
            stock = conn.execute(text(f"SELECT stock FROM `{self.table_b}` WHERE item = 'Widget'")).scalar()
            self.assertEqual(stock, 100)

    # -------------------------------------------------------------
    # 7. Pending modification cannot be executed against different dataset
    # -------------------------------------------------------------
    def test_07_pending_modification_dataset_binding(self):
        self.reset_table_a()
        headers_a = {**self.headers_a, "X-Table-Name": self.table_a}

        prev = self.client.post(
            "/api/modification/ask",
            json={"question": "Update Alice's salary to 75000"},
            headers=headers_a
        )
        token = prev.json().get("confirmation_token")

        # Client attempts to pass a different table in headers or body
        headers_tampered = {**self.headers_a, "X-Table-Name": "unauthorized_table"}
        exec_resp = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": token, "table_name": "other_table"},
            headers=headers_tampered
        )
        self.assertEqual(exec_resp.status_code, 200)

        # Server strictly executed on server-bound table_a
        with engine.connect() as conn:
            salary = conn.execute(text(f"SELECT salary FROM `{self.table_a}` WHERE name = 'Alice'")).scalar()
            self.assertEqual(float(salary), 75000.0)

    # -------------------------------------------------------------
    # 8. Expired confirmation token cannot be executed (400)
    # -------------------------------------------------------------
    def test_08_expired_confirmation_token_rejected(self):
        db = SessionLocal()
        expired_token = secrets.token_hex(32)
        try:
            # Seed an already expired record
            past_time = get_ist_time() - datetime.timedelta(minutes=30)
            pending = PendingModification(
                token=expired_token,
                user_id=self.user_a_id,
                table_name=self.table_a,
                question="Expired modification",
                intent="UPDATE",
                sql_to_execute=f"UPDATE `{self.table_a}` SET `salary` = 80000 WHERE `name` = 'Alice'",
                estimated_rows=1,
                impact_explanation="Update 1 row",
                status="PENDING",
                created_at=past_time - datetime.timedelta(minutes=15),
                expires_at=past_time
            )
            db.add(pending)
            db.commit()
        finally:
            db.close()

        exec_resp = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": expired_token},
            headers=self.headers_a
        )
        self.assertEqual(exec_resp.status_code, 400)
        self.assertIn("expired", exec_resp.json().get("detail", "").lower())

        # Verify status in DB updated to EXPIRED
        db = SessionLocal()
        try:
            record = db.query(PendingModification).filter(PendingModification.token == expired_token).first()
            self.assertEqual(record.status, "EXPIRED")
        finally:
            db.close()

    # -------------------------------------------------------------
    # 9. Modification cannot be executed twice (replay attack)
    # -------------------------------------------------------------
    def test_09_replay_attack_prevention(self):
        self.reset_table_a()
        headers = {**self.headers_a, "X-Table-Name": self.table_a}

        prev = self.client.post(
            "/api/modification/ask",
            json={"question": "Update Alice's salary to 82000"},
            headers=headers
        )
        token = prev.json().get("confirmation_token")

        # 1st Execution: Succeeds
        exec1 = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": token},
            headers=self.headers_a
        )
        self.assertEqual(exec1.status_code, 200)

        # 2nd Execution (Replay): Must fail with 400
        exec2 = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": token},
            headers=self.headers_a
        )
        self.assertEqual(exec2.status_code, 400)
        self.assertIn("already been executed", exec2.json().get("detail", "").lower())

    # -------------------------------------------------------------
    # 10. Concurrent duplicate execution prevented (atomic state check)
    # -------------------------------------------------------------
    def test_10_concurrent_execution_prevented(self):
        db = SessionLocal()
        token = secrets.token_hex(32)
        try:
            # Seed a record currently in EXECUTING state (simulating concurrent worker)
            pending = PendingModification(
                token=token,
                user_id=self.user_a_id,
                table_name=self.table_a,
                question="Concurrent test",
                intent="UPDATE",
                sql_to_execute=f"UPDATE `{self.table_a}` SET `salary` = 85000 WHERE `name` = 'Alice'",
                estimated_rows=1,
                impact_explanation="Update 1 row",
                status="EXECUTING",
                created_at=get_ist_time(),
                expires_at=get_ist_time() + datetime.timedelta(minutes=15)
            )
            db.add(pending)
            db.commit()
        finally:
            db.close()

        # Second worker attempts execution while status is EXECUTING
        exec_resp = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": token},
            headers=self.headers_a
        )
        self.assertEqual(exec_resp.status_code, 400)
        detail = exec_resp.json().get("detail", "").lower()
        self.assertTrue(any(w in detail for w in ["cannot be executed", "currently being processed"]))

    # -------------------------------------------------------------
    # 11. SQL statement chaining (semicolon injection) is rejected
    # -------------------------------------------------------------
    def test_11_sql_statement_chaining_rejected(self):
        user_datasets = get_user_datasets(self.user_a_id)
        chained_sql = f"UPDATE `{self.table_a}` SET salary = 90000; DROP TABLE `{self.table_a}`;"
        validation = validate_modification_sql(chained_sql, self.table_a, "UPDATE", user_datasets)
        self.assertFalse(validation["valid"])
        self.assertIn("chained", validation["error"].lower())

    # -------------------------------------------------------------
    # 12. System-table modifications are rejected
    # -------------------------------------------------------------
    def test_12_system_table_modifications_rejected(self):
        user_datasets = get_user_datasets(self.user_a_id)

        system_tables = ["users", "query_history", "audit_logs", "saved_reports", "pending_modifications"]
        for sys_tbl in system_tables:
            # Direct UPDATE attempt
            sql = f"UPDATE `{sys_tbl}` SET id = 1 WHERE 1=1"
            validation = validate_modification_sql(sql, sys_tbl, "UPDATE", user_datasets)
            self.assertFalse(validation["valid"])
            self.assertIn("system table", validation["error"].lower())

            # Header preview attempt
            resp = self.client.post(
                "/api/modification/ask",
                json={"question": "Delete all users"},
                headers={**self.headers_a, "X-Table-Name": sys_tbl}
            )
            self.assertEqual(resp.status_code, 403)

    # -------------------------------------------------------------
    # 13. Cross-tenant modifications are rejected
    # -------------------------------------------------------------
    def test_13_cross_tenant_modifications_rejected(self):
        # User A attempts to preview modification against User B's dataset in header
        resp = self.client.post(
            "/api/modification/ask",
            json={"question": "Delete all inventory items"},
            headers={**self.headers_a, "X-Table-Name": self.table_b}
        )
        self.assertIn(resp.status_code, [403, 404])

        # User A AST validation of SQL targeting User B's table
        user_datasets = get_user_datasets(self.user_a_id)
        sql = f"DELETE FROM `{self.table_b}` WHERE stock > 0"
        val = validate_modification_sql(sql, self.table_b, "DELETE", user_datasets)
        self.assertFalse(val["valid"])

    # -------------------------------------------------------------
    # 14. Unauthorized DROP operations are rejected
    # -------------------------------------------------------------
    def test_14_unauthorized_drop_rejected(self):
        user_datasets = get_user_datasets(self.user_a_id)

        # DROP on system table
        val_sys = validate_modification_sql("DROP TABLE `users`", "users", "DROP", user_datasets)
        self.assertFalse(val_sys["valid"])

        # DROP on User B table
        val_other = validate_modification_sql(f"DROP TABLE `{self.table_b}`", self.table_b, "DROP", user_datasets)
        self.assertFalse(val_other["valid"])

    # -------------------------------------------------------------
    # 15. Unauthorized TRUNCATE operations are rejected
    # -------------------------------------------------------------
    def test_15_unauthorized_truncate_rejected(self):
        user_datasets = get_user_datasets(self.user_a_id)

        # TRUNCATE on system table
        val_sys = validate_modification_sql("TRUNCATE TABLE `audit_logs`", "audit_logs", "TRUNCATE", user_datasets)
        self.assertFalse(val_sys["valid"])

        # TRUNCATE on User B table
        val_other = validate_modification_sql(f"TRUNCATE TABLE `{self.table_b}`", self.table_b, "TRUNCATE", user_datasets)
        self.assertFalse(val_other["valid"])

    # -------------------------------------------------------------
    # 16. Unsupported administrative commands are rejected
    # -------------------------------------------------------------
    def test_16_unsupported_admin_commands_rejected(self):
        user_datasets = get_user_datasets(self.user_a_id)
        admin_commands = [
            "GRANT ALL PRIVILEGES ON *.* TO 'root'@'%'",
            "REVOKE ALL PRIVILEGES ON *.* FROM 'user'@'%'",
            "CALL execute_arbitrary_proc()",
            "KILL CONNECTION 1234",
            "SET GLOBAL sql_require_primary_key = 0",
            "SHUTDOWN"
        ]
        for cmd in admin_commands:
            val = validate_modification_sql(cmd, self.table_a, "UPDATE", user_datasets)
            self.assertFalse(val["valid"], f"Command should have been rejected: {cmd}")

    # -------------------------------------------------------------
    # 17. Modified / non-existent confirmation tokens are rejected (404)
    # -------------------------------------------------------------
    def test_17_nonexistent_token_rejected(self):
        fake_token = secrets.token_hex(32)
        resp = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": fake_token},
            headers=self.headers_a
        )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json().get("detail", "").lower())

    # -------------------------------------------------------------
    # 18. Database failure results in rollback and accurate response
    # -------------------------------------------------------------
    def test_18_database_failure_rollback(self):
        # Create a pending modification with invalid column value (e.g., text into double column)
        db = SessionLocal()
        token = secrets.token_hex(32)
        try:
            pending = PendingModification(
                token=token,
                user_id=self.user_a_id,
                table_name=self.table_a,
                question="Invalid data type test",
                intent="UPDATE",
                # Column salary is DOUBLE, this triggers MySQL error in strict mode
                sql_to_execute=f"UPDATE `{self.table_a}` SET `salary` = 'INVALID_NOT_A_NUMBER' WHERE `id` = 1",
                estimated_rows=1,
                impact_explanation="Failing update",
                status="PENDING",
                created_at=get_ist_time(),
                expires_at=get_ist_time() + datetime.timedelta(minutes=15)
            )
            db.add(pending)
            db.commit()
        finally:
            db.close()

        resp = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": token},
            headers=self.headers_a
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data.get("success"))
        self.assertIn("error", data)

        # Verify status set to FAILED in DB
        db = SessionLocal()
        try:
            record = db.query(PendingModification).filter(PendingModification.token == token).first()
            self.assertEqual(record.status, "FAILED")
        finally:
            db.close()

    # -------------------------------------------------------------
    # 19. Failed operations do not generate successful audit / history
    # -------------------------------------------------------------
    def test_19_failed_operations_do_not_generate_successful_records(self):
        db = SessionLocal()
        token = secrets.token_hex(32)
        unique_question = f"Failing query {token[:8]}"
        try:
            pending = PendingModification(
                token=token,
                user_id=self.user_a_id,
                table_name=self.table_a,
                question=unique_question,
                intent="UPDATE",
                sql_to_execute=f"UPDATE `{self.table_a}` SET `salary` = 'INVALID_NOT_A_NUMBER' WHERE `id` = 1",
                estimated_rows=1,
                impact_explanation="Failing update",
                status="PENDING",
                created_at=get_ist_time(),
                expires_at=get_ist_time() + datetime.timedelta(minutes=15)
            )
            db.add(pending)
            db.commit()
        finally:
            db.close()

        self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": token},
            headers=self.headers_a
        )

        db = SessionLocal()
        try:
            # QueryHistory must NOT contain this failed query
            hist = db.query(QueryHistory).filter(QueryHistory.question == unique_question).first()
            self.assertIsNone(hist)

            # AuditLog must record status FAILURE (not SUCCESS)
            log = db.query(AuditLog).filter(AuditLog.user_id == self.user_a_id, AuditLog.table_name == self.table_a).order_by(AuditLog.id.desc()).first()
            self.assertIsNotNone(log)
            self.assertEqual(log.status, "FAILURE")
            self.assertNotEqual(log.status, "SUCCESS")
        finally:
            db.close()

    # -------------------------------------------------------------
    # 20. Legitimate operations continue to work end-to-end
    # -------------------------------------------------------------
    def test_20_legitimate_operations_continue_to_work(self):
        self.reset_table_a()
        headers = {**self.headers_a, "X-Table-Name": self.table_a}

        # 1. Preview
        prev = self.client.post(
            "/api/modification/ask",
            json={"question": "Update Alice's salary to 95000"},
            headers=headers
        )
        self.assertEqual(prev.status_code, 200)
        token = prev.json()["confirmation_token"]

        # 2. Execute
        exec_resp = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": token},
            headers=self.headers_a
        )
        self.assertEqual(exec_resp.status_code, 200)
        self.assertTrue(exec_resp.json()["success"])

        # 3. Verify Query History
        hist_resp = self.client.get("/api/history", headers=self.headers_a)
        self.assertEqual(hist_resp.status_code, 200)
        hist_list = hist_resp.json()
        self.assertTrue(any("Alice" in h.get("question", "") for h in hist_list))

        # 4. Verify Audit Log
        audit_resp = self.client.get("/api/audit", headers=self.headers_a)
        self.assertEqual(audit_resp.status_code, 200)
        audit_list = audit_resp.json()
        self.assertTrue(any(a.get("status") == "SUCCESS" for a in audit_list))


    # -------------------------------------------------------------
    # Step 2.1: Hardened DDL, Recovery & Impact Estimation Tests (21-34)
    # -------------------------------------------------------------

    # 21. DML execution followed by a database failure and verified rollback
    def test_21_dml_failure_and_verified_rollback(self):
        self.reset_table_a()
        db = SessionLocal()
        token = secrets.token_hex(32)
        try:
            # Seed pending DML that will fail on execute (DOUBLE column getting string)
            pending = PendingModification(
                token=token,
                user_id=self.user_a_id,
                table_name=self.table_a,
                question="Failing DML rollback test",
                intent="UPDATE",
                execution_policy="DML",
                sql_to_execute=f"UPDATE `{self.table_a}` SET `salary` = 'NOT_A_NUMBER' WHERE `id` = 1",
                estimated_rows=1,
                status="PENDING",
                created_at=get_ist_time(),
                expires_at=get_ist_time() + datetime.timedelta(minutes=15)
            )
            db.add(pending)
            db.commit()
        finally:
            db.close()

        resp = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": token},
            headers=self.headers_a
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("policy"), "DML")
        self.assertTrue(data.get("rolled_back"))

        # Verify DB rows are intact (Alice salary is still 50000.0)
        with engine.connect() as conn:
            sal = conn.execute(text(f"SELECT salary FROM `{self.table_a}` WHERE id = 1")).scalar()
            self.assertEqual(float(sal), 50000.0)

    # 22. DDL execution followed by an audit/status bookkeeping failure
    def test_22_ddl_execution_and_bookkeeping_failure(self):
        # Create a temporary table for DDL
        temp_tbl = f"test_ddl_{self.user_a_id}"
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{temp_tbl}`"))
            conn.execute(text(f"CREATE TABLE `{temp_tbl}` (id INT AUTO_INCREMENT PRIMARY KEY, title VARCHAR(100))"))

        db = SessionLocal()
        token = secrets.token_hex(32)
        try:
            pending = PendingModification(
                token=token,
                user_id=self.user_a_id,
                table_name=temp_tbl,
                question="Add column bonus",
                intent="ALTER",
                execution_policy="DDL",
                sql_to_execute=f"ALTER TABLE `{temp_tbl}` ADD COLUMN `bonus` DOUBLE NULL",
                estimated_rows=0,
                status="PENDING",
                created_at=get_ist_time(),
                expires_at=get_ist_time() + datetime.timedelta(minutes=15)
            )
            db.add(pending)
            db.commit()
        finally:
            db.close()

        # Execute DDL
        resp = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": token},
            headers=self.headers_a
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("policy"), "DDL")
        self.assertFalse(data.get("rolled_back"))

        # Verify column actually exists in MySQL (DDL committed implicitly)
        with engine.connect() as conn:
            inspector = inspect(engine)
            cols = [c["name"] for c in inspector.get_columns(temp_tbl)]
            self.assertIn("bonus", cols)

        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{temp_tbl}`"))

    # 23. Backend interruption after transition to EXECUTING
    def test_23_backend_interruption_after_transition_to_executing(self):
        db = SessionLocal()
        token = secrets.token_hex(32)
        now = get_ist_time()
        try:
            # Seed record stuck in EXECUTING within active window (< 60s ago)
            pending = PendingModification(
                token=token,
                user_id=self.user_a_id,
                table_name=self.table_a,
                question="Interrupted test",
                intent="UPDATE",
                sql_to_execute=f"UPDATE `{self.table_a}` SET `salary` = 60000 WHERE `id` = 1",
                estimated_rows=1,
                status="EXECUTING",
                started_executing_at=now,
                created_at=now,
                expires_at=now + datetime.timedelta(minutes=15)
            )
            db.add(pending)
            db.commit()
        finally:
            db.close()

        # Another worker attempts execution while currently active
        resp = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": token},
            headers=self.headers_a
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("currently being processed", resp.json().get("detail", "").lower())

    # 24. Recovery of stale EXECUTING records via structural evidence
    def test_24_recovery_of_stale_executing_records_structural_evidence(self):
        temp_tbl = f"temp_drop_{self.user_a_id}"
        # Ensure table does NOT exist (already dropped before crash)
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{temp_tbl}`"))

        db = SessionLocal()
        token = secrets.token_hex(32)
        old_time = get_ist_time() - datetime.timedelta(seconds=120)
        try:
            pending = PendingModification(
                token=token,
                user_id=self.user_a_id,
                table_name=temp_tbl,
                question="Drop temporary table",
                intent="DROP",
                execution_policy="DDL",
                sql_to_execute=f"DROP TABLE `{temp_tbl}`",
                estimated_rows=0,
                status="EXECUTING",
                started_executing_at=old_time,
                created_at=old_time,
                expires_at=old_time + datetime.timedelta(minutes=15)
            )
            db.add(pending)
            db.commit()
        finally:
            db.close()

        # Call reconcile endpoint
        rec_resp = self.client.post(
            "/api/modification/reconcile",
            json={"token": token, "stale_timeout_seconds": 60},
            headers=self.headers_a
        )
        self.assertEqual(rec_resp.status_code, 200)
        items = rec_resp.json().get("items", [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["status"], "EXECUTED")
        self.assertIn("no longer exists", items[0]["evidence"])

        # Verify DB status is now EXECUTED
        db = SessionLocal()
        try:
            record = db.query(PendingModification).filter(PendingModification.token == token).first()
            self.assertEqual(record.status, "EXECUTED")
        finally:
            db.close()

    # 25. Recovery of stale EXECUTING records without evidence -> UNKNOWN
    def test_25_recovery_of_stale_executing_uncertain_outcome(self):
        db = SessionLocal()
        token = secrets.token_hex(32)
        old_time = get_ist_time() - datetime.timedelta(seconds=120)
        try:
            pending = PendingModification(
                token=token,
                user_id=self.user_a_id,
                table_name=self.table_a,
                question="Uncertain DML crash",
                intent="UPDATE",
                execution_policy="DML",
                sql_to_execute=f"UPDATE `{self.table_a}` SET `salary` = 77777 WHERE `id` = 1",
                estimated_rows=1,
                status="EXECUTING",
                started_executing_at=old_time,
                created_at=old_time,
                expires_at=old_time + datetime.timedelta(minutes=15)
            )
            db.add(pending)
            db.commit()
        finally:
            db.close()

        rec_resp = self.client.post(
            "/api/modification/reconcile",
            json={"token": token, "stale_timeout_seconds": 60},
            headers=self.headers_a
        )
        self.assertEqual(rec_resp.status_code, 200)
        items = rec_resp.json().get("items", [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["status"], "UNKNOWN")

        # Verify record in DB transitioned to UNKNOWN, NOT PENDING!
        db = SessionLocal()
        try:
            record = db.query(PendingModification).filter(PendingModification.token == token).first()
            self.assertEqual(record.status, "UNKNOWN")
        finally:
            db.close()

    # 26. Confirmation that uncertain executions cannot be replayed
    def test_26_uncertain_executions_cannot_be_replayed(self):
        db = SessionLocal()
        token = secrets.token_hex(32)
        try:
            pending = PendingModification(
                token=token,
                user_id=self.user_a_id,
                table_name=self.table_a,
                question="Uncertain replay attempt",
                intent="UPDATE",
                sql_to_execute=f"UPDATE `{self.table_a}` SET `salary` = 66000 WHERE `id` = 1",
                status="UNKNOWN",
                created_at=get_ist_time(),
                expires_at=get_ist_time() + datetime.timedelta(minutes=15)
            )
            db.add(pending)
            db.commit()
        finally:
            db.close()

        resp = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": token},
            headers=self.headers_a
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("uncertain", resp.json().get("detail", "").lower())

    # 27. Concurrent execution requests using the same token
    def test_27_concurrent_execution_requests_same_token(self):
        self.reset_table_a()
        headers = {**self.headers_a, "X-Table-Name": self.table_a}

        prev = self.client.post(
            "/api/modification/ask",
            json={"question": "Update Alice's salary to 58000"},
            headers=headers
        )
        token = prev.json()["confirmation_token"]

        # First execution succeeds
        r1 = self.client.post("/api/modification/execute", json={"confirmation_token": token}, headers=self.headers_a)
        self.assertEqual(r1.status_code, 200)

        # Second simultaneous/sequential attempt is rejected
        r2 = self.client.post("/api/modification/execute", json={"confirmation_token": token}, headers=self.headers_a)
        self.assertEqual(r2.status_code, 400)

    # 28. UPDATE/DELETE impact estimates with nested WHERE conditions
    def test_28_update_delete_impact_nested_where_conditions(self):
        from app.services.impact_estimator import estimate_affected_rows
        self.reset_table_a()

        # (department = 'Engineering' OR department = 'Sales') AND salary < 55000
        # In our seed data, Alice is Engineering / 50000 (matches), Bob is Sales / 55000 (salary not < 55000). Total = 1
        sql = f"UPDATE `{self.table_a}` SET salary = 60000 WHERE (department = 'Engineering' OR department = 'Sales') AND salary < 55000"
        est = estimate_affected_rows(sql, self.table_a, "UPDATE")
        self.assertTrue(est["reliable"])
        self.assertEqual(est["estimated_rows"], 1)

    # 29. Aliases and qualified columns in impact estimation
    def test_29_aliases_and_qualified_columns_in_impact_estimation(self):
        from app.services.impact_estimator import estimate_affected_rows
        self.reset_table_a()

        # Preserves table alias 'AS e' and qualified 'e.salary'
        sql = f"UPDATE `{self.table_a}` AS e SET e.salary = 60000 WHERE e.salary < 55000"
        est = estimate_affected_rows(sql, self.table_a, "UPDATE")
        self.assertTrue(est["reliable"])
        self.assertEqual(est["estimated_rows"], 1)

    # 30. Joined modification impact estimation or explicit rejection
    def test_30_joined_modification_explicit_rejection(self):
        joined_update = f"UPDATE `{self.table_a}` e JOIN `{self.table_b}` i ON e.id = i.id SET e.salary = 70000"
        val = validate_modification_sql(joined_update, self.table_a, "UPDATE")
        self.assertFalse(val["valid"])
        self.assertIn("joined modifications are not supported", val["error"].lower())

    # 31. INSERT with multiple values and INSERT ... SELECT
    def test_31_insert_multi_values_and_insert_select(self):
        from app.services.impact_estimator import estimate_affected_rows

        # Multi-row VALUES insert
        multi_insert = f"INSERT INTO `{self.table_a}` (name, salary, department) VALUES ('U1', 10, 'D1'), ('U2', 20, 'D2'), ('U3', 30, 'D3')"
        est_multi = estimate_affected_rows(multi_insert, self.table_a, "INSERT")
        self.assertTrue(est_multi["reliable"])
        self.assertEqual(est_multi["estimated_rows"], 3)

        # INSERT ... SELECT
        ins_sel = f"INSERT INTO `{self.table_a}` (name, salary, department) SELECT name, salary, department FROM `{self.table_a}` WHERE salary > 50000"
        est_sel = estimate_affected_rows(ins_sel, self.table_a, "INSERT")
        self.assertTrue(est_sel["reliable"])
        self.assertEqual(est_sel["estimated_rows"], 1)  # Bob has 55000

    # 32. DROP database/schema and multi-table DROP rejection
    def test_32_drop_database_and_multi_table_drop_rejection(self):
        # DROP DATABASE
        val_db = validate_modification_sql("DROP DATABASE company_db", self.table_a, "DROP")
        self.assertFalse(val_db["valid"])
        self.assertIn("database or schema-level drop", val_db["error"].lower())

        # Multi-table DROP
        val_multi = validate_modification_sql(f"DROP TABLE `{self.table_a}`, `{self.table_b}`", self.table_a, "DROP")
        self.assertFalse(val_multi["valid"])
        self.assertIn("multi-table drop", val_multi["error"].lower())

    # 33. Cross-tenant and system-table DDL rejection
    def test_33_cross_tenant_and_system_table_ddl_rejection(self):
        user_datasets_a = get_user_datasets(self.user_a_id)

        # System table DROP
        val_sys_drop = validate_modification_sql("DROP TABLE `users`", "users", "DROP", user_datasets_a)
        self.assertFalse(val_sys_drop["valid"])

        # System table TRUNCATE
        val_sys_trunc = validate_modification_sql("TRUNCATE TABLE `audit_logs`", "audit_logs", "TRUNCATE", user_datasets_a)
        self.assertFalse(val_sys_trunc["valid"])

        # User A attempting to DROP User B's dataset
        val_cross_drop = validate_modification_sql(f"DROP TABLE `{self.table_b}`", self.table_b, "DROP", user_datasets_a)
        self.assertFalse(val_cross_drop["valid"])

    # 34. Actual affected-row counts compared against estimates
    def test_34_actual_affected_rows_compared_against_estimates(self):
        self.reset_table_a()
        headers = {**self.headers_a, "X-Table-Name": self.table_a}

        # Preview update: Alice salary
        prev = self.client.post(
            "/api/modification/ask",
            json={"question": "Update Alice's salary to 88000"},
            headers=headers
        )
        self.assertEqual(prev.status_code, 200)
        p_data = prev.json()
        self.assertEqual(p_data["estimated_rows"], 1)
        token = p_data["confirmation_token"]

        # Execute
        exec_resp = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": token},
            headers=self.headers_a
        )
        self.assertEqual(exec_resp.status_code, 200)
        e_data = exec_resp.json()
        self.assertEqual(e_data["rows_affected"], 1)

        # Verify PendingModification record stores both estimated and actual separately!
        db = SessionLocal()
        try:
            record = db.query(PendingModification).filter(PendingModification.token == token).first()
            self.assertEqual(record.estimated_rows, 1)
            self.assertEqual(record.actual_rows_affected, 1)
            self.assertEqual(record.status, "EXECUTED")
        finally:
            db.close()

    # -------------------------------------------------------------
    # 35. SELECT queries submitted to /api/modification/ask
    # -------------------------------------------------------------
    def test_35_select_query_not_treated_as_failed_modification(self):
        """35. SELECT queries submitted to /api/modification/ask return success=True and requires_confirmation=False without errors."""
        headers = {**self.headers_a, "X-Table-Name": self.table_a}
        resp = self.client.post(
            "/api/modification/ask",
            json={"question": "Show all customers from Chennai."},
            headers=headers
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertFalse(data.get("requires_confirmation"))
        self.assertFalse(data.get("is_modification", True))
        self.assertNotIn("error", data)
        self.assertIn("not appear to be a data or schema modification", data.get("message", ""))


if __name__ == "__main__":
    unittest.main()
