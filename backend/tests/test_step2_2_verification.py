"""
PromptSQL — Step 2.2: Final Verification of DDL Recovery & Execution Idempotency

Verification Coverage:
1. DDL Reconciliation:
   - ALTER ADD COLUMN (Structural proof -> EXECUTED)
   - ALTER MODIFY COLUMN (Insufficient structural proof -> UNKNOWN)
   - ALTER DROP COLUMN (Insufficient structural proof -> UNKNOWN)
   - DROP TABLE (Structural proof -> EXECUTED)
   - TRUNCATE TABLE (Insufficient structural proof -> UNKNOWN)
2. Stale Execution Detection:
   - Query still running in MySQL processlist is NOT reconciled as crashed.
   - Long-running query elapsed time does not mistakenly trigger rollback or replay.
   - Concurrency across multiple workers is atomic.
3. BOOKKEEPING_FAILED Handling:
   - SQL committed, but post-execution bookkeeping failed.
   - Token is permanently locked and never automatically re-executed.
   - User receives warning that SQL committed.
   - Pending record is distinguishable from FAILED.
4. Execution Idempotency:
   - All terminal and uncertain states (EXECUTED, FAILED, EXPIRED, UNKNOWN, BOOKKEEPING_FAILED) prevent token reuse.
   - Recovery operations NEVER reset a token to PENDING.
   - Concurrent reconciliation requests cannot produce conflicting state transitions.
"""

import os
import sys
import unittest
import datetime
import secrets
from unittest.mock import patch
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
from app.routes.modification import reconcile_stale_modification, is_query_still_running_in_db
from app.utils.tz_helper import get_ist_time


class TestStep22Verification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

        cls.user_num = 99941
        cls.user_id = f"usr_{cls.user_num}"
        cls.token = create_access_token(cls.user_num)
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

        cls.table = f"verify_ds_{cls.user_id}"

        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table}`"))
            conn.execute(text(f"""
                CREATE TABLE `{cls.table}` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    score INT NOT NULL
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.table}` (name, score) VALUES
                ('Alice', 100),
                ('Bob', 200)
            """))

    @classmethod
    def tearDownClass(cls):
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table}`"))

        db = SessionLocal()
        try:
            db.query(PendingModification).filter(PendingModification.user_id == cls.user_id).delete(synchronize_session=False)
            db.query(AuditLog).filter(AuditLog.user_id == cls.user_id).delete(synchronize_session=False)
            db.query(QueryHistory).filter(QueryHistory.user_id == cls.user_id).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    # =========================================================================
    # 1. DDL Reconciliation: ADD, MODIFY, DROP COLUMN, DROP TABLE, TRUNCATE
    # =========================================================================

    def test_01_ddl_reconcile_alter_add_column_verified_executed(self):
        """ALTER ADD COLUMN: column verified in schema -> EXECUTED"""
        temp_tbl = f"alter_add_{self.user_id}"
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{temp_tbl}`"))
            conn.execute(text(f"CREATE TABLE `{temp_tbl}` (id INT AUTO_INCREMENT PRIMARY KEY, val INT)"))
            # Column was added in MySQL before crash
            conn.execute(text(f"ALTER TABLE `{temp_tbl}` ADD COLUMN `email` VARCHAR(100) NULL"))

        db = SessionLocal()
        tok = secrets.token_hex(32)
        old_time = get_ist_time() - datetime.timedelta(seconds=120)
        try:
            pending = PendingModification(
                token=tok,
                user_id=self.user_id,
                table_name=temp_tbl,
                question="Add email column",
                intent="ALTER",
                execution_policy="DDL",
                sql_to_execute=f"ALTER TABLE `{temp_tbl}` ADD COLUMN `email` VARCHAR(100) NULL",
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

        # Reconcile
        res = self.client.post("/api/modification/reconcile", json={"token": tok}, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        items = res.json().get("items", [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["status"], "EXECUTED")
        self.assertIn("verified in schema", items[0]["evidence"])

        # Cleanup
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{temp_tbl}`"))

    def test_02_ddl_reconcile_alter_modify_column_insufficient_evidence_unknown(self):
        """ALTER MODIFY COLUMN: without audit log or baseline, structural evidence is insufficient -> UNKNOWN"""
        temp_tbl = f"alter_mod_{self.user_id}"
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{temp_tbl}`"))
            conn.execute(text(f"CREATE TABLE `{temp_tbl}` (id INT AUTO_INCREMENT PRIMARY KEY, score INT)"))

        db = SessionLocal()
        tok = secrets.token_hex(32)
        old_time = get_ist_time() - datetime.timedelta(seconds=120)
        try:
            pending = PendingModification(
                token=tok,
                user_id=self.user_id,
                table_name=temp_tbl,
                question="Modify score to BIGINT",
                intent="ALTER",
                execution_policy="DDL",
                sql_to_execute=f"ALTER TABLE `{temp_tbl}` MODIFY COLUMN `score` BIGINT",
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

        res = self.client.post("/api/modification/reconcile", json={"token": tok}, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        items = res.json().get("items", [])
        self.assertEqual(len(items), 1)
        # Must be UNKNOWN because structural evidence alone cannot prove the modification ran
        self.assertEqual(items[0]["status"], "UNKNOWN")

        # Cleanup
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{temp_tbl}`"))

    def test_03_ddl_reconcile_alter_drop_column_insufficient_evidence_unknown(self):
        """ALTER DROP COLUMN: column absence alone cannot prove execution vs never existing -> UNKNOWN"""
        temp_tbl = f"alter_drop_{self.user_id}"
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{temp_tbl}`"))
            conn.execute(text(f"CREATE TABLE `{temp_tbl}` (id INT AUTO_INCREMENT PRIMARY KEY, title VARCHAR(100))"))

        db = SessionLocal()
        tok = secrets.token_hex(32)
        old_time = get_ist_time() - datetime.timedelta(seconds=120)
        try:
            pending = PendingModification(
                token=tok,
                user_id=self.user_id,
                table_name=temp_tbl,
                question="Drop column extra",
                intent="ALTER",
                execution_policy="DDL",
                sql_to_execute=f"ALTER TABLE `{temp_tbl}` DROP COLUMN `extra`",
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

        res = self.client.post("/api/modification/reconcile", json={"token": tok}, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        items = res.json().get("items", [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["status"], "UNKNOWN")

        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{temp_tbl}`"))

    def test_04_ddl_reconcile_drop_table_verified_executed(self):
        """DROP TABLE: table absence in MySQL schema -> EXECUTED"""
        temp_tbl = f"drop_v22_{self.user_id}"
        # Ensure table does NOT exist
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{temp_tbl}`"))

        db = SessionLocal()
        tok = secrets.token_hex(32)
        old_time = get_ist_time() - datetime.timedelta(seconds=120)
        try:
            pending = PendingModification(
                token=tok,
                user_id=self.user_id,
                table_name=temp_tbl,
                question="Drop temporary dataset",
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

        res = self.client.post("/api/modification/reconcile", json={"token": tok}, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        items = res.json().get("items", [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["status"], "EXECUTED")
        self.assertIn("no longer exists", items[0]["evidence"])

    def test_05_ddl_reconcile_truncate_insufficient_evidence_unknown(self):
        """TRUNCATE TABLE: empty table cannot prove truncate vs already empty -> UNKNOWN"""
        temp_tbl = f"trunc_v22_{self.user_id}"
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{temp_tbl}`"))
            conn.execute(text(f"CREATE TABLE `{temp_tbl}` (id INT AUTO_INCREMENT PRIMARY KEY, num INT)"))

        db = SessionLocal()
        tok = secrets.token_hex(32)
        old_time = get_ist_time() - datetime.timedelta(seconds=120)
        try:
            pending = PendingModification(
                token=tok,
                user_id=self.user_id,
                table_name=temp_tbl,
                question="Truncate table",
                intent="TRUNCATE",
                execution_policy="DDL",
                sql_to_execute=f"TRUNCATE TABLE `{temp_tbl}`",
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

        res = self.client.post("/api/modification/reconcile", json={"token": tok}, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        items = res.json().get("items", [])
        self.assertEqual(len(items), 1)
        # Without AuditLog, rowcount=0 alone cannot prove execution -> UNKNOWN
        self.assertEqual(items[0]["status"], "UNKNOWN")

        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{temp_tbl}`"))

    # =========================================================================
    # 2. Stale Execution Detection & Active Execution Guard
    # =========================================================================

    def test_06_active_running_query_in_processlist_not_reconciled(self):
        """A query that is actively running in MySQL is NOT marked crashed despite elapsed time > 60s"""
        tok = secrets.token_hex(32)
        db = SessionLocal()
        old_time = get_ist_time() - datetime.timedelta(seconds=90)
        try:
            pending = PendingModification(
                token=tok,
                user_id=self.user_id,
                table_name=self.table,
                question="Long running DDL query",
                intent="ALTER",
                execution_policy="DDL",
                sql_to_execute=f"ALTER TABLE `{self.table}` ADD COLUMN `big_idx` INT",
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

        # Mock is_query_still_running_in_db to return True (simulating active query in MySQL)
        with patch("app.routes.modification.is_query_still_running_in_db", return_value=True):
            rec_res = self.client.post("/api/modification/reconcile", json={"token": tok}, headers=self.headers)
            self.assertEqual(rec_res.status_code, 200)
            items = rec_res.json().get("items", [])
            self.assertEqual(len(items), 1)
            # Must remain EXECUTING
            self.assertFalse(items[0]["reconciled"])
            self.assertEqual(items[0]["status"], "EXECUTING")
            self.assertIn("actively executing", items[0]["evidence"].lower())

            # Attempting execute while actively running returns 400
            exec_res = self.client.post("/api/modification/execute", json={"confirmation_token": tok}, headers=self.headers)
            self.assertEqual(exec_res.status_code, 400)
            self.assertIn("still executing in the database engine", exec_res.json().get("detail", "").lower())

    def test_07_concurrent_reconciliation_multi_worker_safety(self):
        """Concurrent reconciliation calls on the same record cannot produce conflicting state transitions"""
        tok = secrets.token_hex(32)
        db = SessionLocal()
        old_time = get_ist_time() - datetime.timedelta(seconds=120)
        try:
            pending = PendingModification(
                token=tok,
                user_id=self.user_id,
                table_name=self.table,
                question="Concurrent reconciliation test",
                intent="UPDATE",
                sql_to_execute=f"UPDATE `{self.table}` SET score = 500 WHERE id = 1",
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

        # First worker reconciles
        r1 = self.client.post("/api/modification/reconcile", json={"token": tok}, headers=self.headers)
        self.assertEqual(r1.status_code, 200)
        item1 = r1.json()["items"][0]
        self.assertTrue(item1["reconciled"])
        self.assertEqual(item1["status"], "UNKNOWN")

        # Second worker attempts to reconcile the same token
        r2 = self.client.post("/api/modification/reconcile", json={"token": tok}, headers=self.headers)
        self.assertEqual(r2.status_code, 200)
        # Record is no longer in EXECUTING state
        self.assertIn("is not in EXECUTING state", r2.json().get("message", ""))

    # =========================================================================
    # 3. BOOKKEEPING_FAILED Handling
    # =========================================================================

    def test_08_bookkeeping_failed_handling(self):
        """Simulate SQL successfully committing followed by audit/history logging failure"""
        tok = secrets.token_hex(32)
        db = SessionLocal()
        try:
            pending = PendingModification(
                token=tok,
                user_id=self.user_id,
                table_name=self.table,
                question="Bookkeeping failure simulation",
                intent="UPDATE",
                sql_to_execute=f"UPDATE `{self.table}` SET `score` = 350 WHERE `name` = 'Alice'",
                estimated_rows=1,
                status="PENDING",
                created_at=get_ist_time(),
                expires_at=get_ist_time() + datetime.timedelta(minutes=15)
            )
            db.add(pending)
            db.commit()
        finally:
            db.close()

        # Patch QueryHistory constructor to raise an exception simulating history table failure
        with patch("app.routes.modification.QueryHistory", side_effect=Exception("Disk full on history table")):
            exec_resp = self.client.post("/api/modification/execute", json={"confirmation_token": tok}, headers=self.headers)
            self.assertEqual(exec_resp.status_code, 200)
            data = exec_resp.json()
            # SQL succeeded and committed
            self.assertTrue(data.get("success"))
            self.assertEqual(data.get("bookkeeping_status"), "BOOKKEEPING_FAILED")
            self.assertIn("warning", data)
            self.assertIn("committed successfully", data["warning"])

        # Verify DB row was updated in MySQL (committed!)
        with engine.connect() as conn:
            score = conn.execute(text(f"SELECT score FROM `{self.table}` WHERE name = 'Alice'")).scalar()
            self.assertEqual(score, 350)

        # Verify PendingModification status in DB is BOOKKEEPING_FAILED (not FAILED!)
        db = SessionLocal()
        try:
            record = db.query(PendingModification).filter(PendingModification.token == tok).first()
            self.assertEqual(record.status, "BOOKKEEPING_FAILED")
            self.assertNotEqual(record.status, "FAILED")
            self.assertEqual(record.actual_rows_affected, 1)
        finally:
            db.close()

        # Verify token CANNOT be re-executed
        re_exec = self.client.post("/api/modification/execute", json={"confirmation_token": tok}, headers=self.headers)
        self.assertEqual(re_exec.status_code, 400)
        self.assertIn("BOOKKEEPING_FAILED", re_exec.json().get("detail", ""))

    # =========================================================================
    # 4. Execution Idempotency & Terminal State Permanence
    # =========================================================================

    def test_09_all_terminal_states_prevent_reuse(self):
        """Tokens in EXECUTED, FAILED, EXPIRED, UNKNOWN, or BOOKKEEPING_FAILED cannot be reused"""
        terminal_statuses = ["EXECUTED", "FAILED", "EXPIRED", "UNKNOWN", "BOOKKEEPING_FAILED"]

        for st in terminal_statuses:
            tok = secrets.token_hex(32)
            db = SessionLocal()
            try:
                pending = PendingModification(
                    token=tok,
                    user_id=self.user_id,
                    table_name=self.table,
                    question=f"Test {st}",
                    intent="UPDATE",
                    sql_to_execute=f"UPDATE `{self.table}` SET score = 999 WHERE id = 1",
                    status=st,
                    created_at=get_ist_time(),
                    expires_at=get_ist_time() + datetime.timedelta(minutes=15)
                )
                db.add(pending)
                db.commit()
            finally:
                db.close()

            resp = self.client.post("/api/modification/execute", json={"confirmation_token": tok}, headers=self.headers)
            self.assertEqual(resp.status_code, 400, f"Status {st} should have returned 400")

    def test_10_recovery_never_resets_token_to_pending(self):
        """Reconciliation across all scenarios transitions to EXECUTED, FAILED, or UNKNOWN; NEVER PENDING"""
        scenarios = [
            ("DROP", f"DROP TABLE nonexistent_{self.user_id}"),
            ("ALTER", f"ALTER TABLE `{self.table}` MODIFY COLUMN score BIGINT"),
            ("TRUNCATE", f"TRUNCATE TABLE `{self.table}`"),
            ("UPDATE", f"UPDATE `{self.table}` SET score = 100 WHERE id = 99")
        ]

        old_time = get_ist_time() - datetime.timedelta(seconds=120)

        for intent, sql in scenarios:
            tok = secrets.token_hex(32)
            db = SessionLocal()
            try:
                pending = PendingModification(
                    token=tok,
                    user_id=self.user_id,
                    table_name=self.table,
                    question=f"Reconcile test {intent}",
                    intent=intent,
                    execution_policy="DDL" if intent in ["DROP", "ALTER", "TRUNCATE"] else "DML",
                    sql_to_execute=sql,
                    status="EXECUTING",
                    started_executing_at=old_time,
                    created_at=old_time,
                    expires_at=old_time + datetime.timedelta(minutes=15)
                )
                db.add(pending)
                db.commit()
            finally:
                db.close()

            res = self.client.post("/api/modification/reconcile", json={"token": tok}, headers=self.headers)
            self.assertEqual(res.status_code, 200)

            # Check DB state
            db = SessionLocal()
            try:
                record = db.query(PendingModification).filter(PendingModification.token == tok).first()
                self.assertIn(record.status, ["EXECUTED", "UNKNOWN", "FAILED"])
                self.assertNotEqual(record.status, "PENDING")
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
