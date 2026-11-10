"""
PromptSQL - Step 4.2: Database Schema Migration Reliability & Consistency Tests
================================================================================
Comprehensive verification of:
1. Missing table gets created.
2. Existing valid table passes verification.
3. Existing table with a missing required column is rejected.
4. Existing table with an incompatible column type is rejected.
5. Database connection failure prevents successful initialization (sanitized).
6. Migration failure prevents application startup.
7. Concurrent initialization across workers does not corrupt or invalidate the table.
8. Lock acquisition timeout handling.

Tests clearly identify Real MySQL Integration Tests vs Mocked Tests.
"""

import os
import sys
import unittest
import subprocess
from unittest.mock import MagicMock
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.database.connection import engine
from app.services.migration_guard import (
    acquire_advisory_lock,
    release_advisory_lock,
    verify_user_active_datasets_schema,
    ensure_user_active_datasets_table,
    MIGRATION_LOCK_NAME
)
from app.main import run_startup_migrations


class Step42MigrationReliabilityTests(unittest.TestCase):
    """
    Step 4.2 Schema Migration Reliability Tests.
    """

    def setUp(self):
        self.cleanup_tables = []

    def tearDown(self):
        if self.cleanup_tables:
            with engine.connect() as conn:
                for tbl in self.cleanup_tables:
                    try:
                        conn.execute(text(f"DROP TABLE IF EXISTS `{tbl}`"))
                    except Exception:
                        pass
                conn.commit()

    # -------------------------------------------------------------------------
    # Test 1: Real MySQL - Missing table gets created
    # -------------------------------------------------------------------------
    def test_01_missing_table_gets_created_real_mysql(self):
        """
        [Real MySQL] Verifies that when the required table is missing,
        ensure_user_active_datasets_table creates it with the correct schema.
        """
        table_name = "_test_step42_missing_tbl"
        self.cleanup_tables.append(table_name)

        # Ensure table does not exist
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{table_name}`"))
            conn.commit()

        inspector_before = inspect(engine)
        self.assertNotIn(table_name, inspector_before.get_table_names())

        # Action: Ensure table
        ensure_user_active_datasets_table(
            engine,
            table_name=table_name,
            lock_name="_test_lock_test01",
            lock_timeout=10
        )

        # Verification: Table exists and matches schema
        inspector_after = inspect(engine)
        self.assertIn(table_name, inspector_after.get_table_names())

        res = verify_user_active_datasets_schema(engine, table_name=table_name)
        self.assertTrue(res["valid"])
        self.assertIn("user_id", res["columns"])
        self.assertIn("table_name", res["columns"])
        self.assertIn("updated_at", res["columns"])
        self.assertEqual(res["primary_key"], ["user_id"])

    # -------------------------------------------------------------------------
    # Test 2: Real MySQL - Existing valid table passes verification
    # -------------------------------------------------------------------------
    def test_02_existing_valid_table_passes_verification_real_mysql(self):
        """
        [Real MySQL] Verifies that an existing valid table passes verification
        and its pre-existing data is completely preserved.
        """
        table_name = "_test_step42_valid_preserved"
        self.cleanup_tables.append(table_name)

        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{table_name}`"))
            conn.execute(text(f"""
                CREATE TABLE `{table_name}` (
                    `user_id` VARCHAR(50) NOT NULL PRIMARY KEY,
                    `table_name` VARCHAR(100) NOT NULL,
                    `updated_at` DATETIME NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """))
            conn.execute(
                text(f"INSERT INTO `{table_name}` (user_id, table_name) VALUES (:u, :t)"),
                {"u": "usr_9999", "t": "preserved_dataset"}
            )
            conn.commit()

        # Action: Run ensure and verify
        ensure_user_active_datasets_table(
            engine,
            table_name=table_name,
            lock_name="_test_lock_test02",
            lock_timeout=10
        )
        res = verify_user_active_datasets_schema(engine, table_name=table_name)
        self.assertTrue(res["valid"])

        # Assert data was NOT destroyed or truncated
        with engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT table_name FROM `{table_name}` WHERE user_id = :u"),
                {"u": "usr_9999"}
            ).scalar()
            self.assertEqual(row, "preserved_dataset")

    # -------------------------------------------------------------------------
    # Test 3: Real MySQL - Missing required column is rejected
    # -------------------------------------------------------------------------
    def test_03_missing_required_column_rejected_real_mysql(self):
        """
        [Real MySQL] Verifies that an existing table missing a required column (table_name)
        is rejected with a clear RuntimeError without dropping or altering data.
        """
        table_name = "_test_step42_missing_col"
        self.cleanup_tables.append(table_name)

        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{table_name}`"))
            conn.execute(text(f"""
                CREATE TABLE `{table_name}` (
                    `user_id` VARCHAR(50) NOT NULL PRIMARY KEY
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """))
            conn.execute(
                text(f"INSERT INTO `{table_name}` (user_id) VALUES (:u)"),
                {"u": "usr_safe_1"}
            )
            conn.commit()

        # Action & Assertion
        with self.assertRaises(RuntimeError) as ctx:
            verify_user_active_datasets_schema(engine, table_name=table_name)

        self.assertIn("missing required column 'table_name'", str(ctx.exception).lower())

        # Verify existing table and data were NOT deleted
        with engine.connect() as conn:
            val = conn.execute(
                text(f"SELECT user_id FROM `{table_name}` WHERE user_id = :u"),
                {"u": "usr_safe_1"}
            ).scalar()
            self.assertEqual(val, "usr_safe_1")

    # -------------------------------------------------------------------------
    # Test 4: Real MySQL - Incompatible column types & PKs are rejected
    # -------------------------------------------------------------------------
    def test_04_incompatible_column_type_rejected_real_mysql(self):
        """
        [Real MySQL] Verifies that existing tables with incompatible column types
        or incorrect primary keys are rejected.
        """
        # Case A: user_id is INTEGER instead of VARCHAR/String
        tbl_bad_type = "_test_step42_bad_type"
        self.cleanup_tables.append(tbl_bad_type)

        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{tbl_bad_type}`"))
            conn.execute(text(f"""
                CREATE TABLE `{tbl_bad_type}` (
                    `user_id` INT NOT NULL PRIMARY KEY,
                    `table_name` VARCHAR(100) NOT NULL,
                    `updated_at` DATETIME NULL
                ) ENGINE=InnoDB;
            """))
            conn.commit()

        with self.assertRaises(RuntimeError) as ctx_a:
            verify_user_active_datasets_schema(engine, table_name=tbl_bad_type)
        self.assertIn("incompatible type", str(ctx_a.exception).lower())
        self.assertIn("user_id", str(ctx_a.exception).lower())

        # Case B: user_id length is too short (< 50)
        tbl_short_uid = "_test_step42_short_uid"
        self.cleanup_tables.append(tbl_short_uid)

        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{tbl_short_uid}`"))
            conn.execute(text(f"""
                CREATE TABLE `{tbl_short_uid}` (
                    `user_id` VARCHAR(20) NOT NULL PRIMARY KEY,
                    `table_name` VARCHAR(100) NOT NULL,
                    `updated_at` DATETIME NULL
                ) ENGINE=InnoDB;
            """))
            conn.commit()

        with self.assertRaises(RuntimeError) as ctx_b:
            verify_user_active_datasets_schema(engine, table_name=tbl_short_uid)
        self.assertIn("too short", str(ctx_b.exception).lower())

        # Case C: Primary key is missing or on wrong column
        tbl_wrong_pk = "_test_step42_wrong_pk"
        self.cleanup_tables.append(tbl_wrong_pk)

        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{tbl_wrong_pk}`"))
            conn.execute(text(f"""
                CREATE TABLE `{tbl_wrong_pk}` (
                    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
                    `user_id` VARCHAR(50) NOT NULL,
                    `table_name` VARCHAR(100) NOT NULL,
                    `updated_at` DATETIME NULL
                ) ENGINE=InnoDB;
            """))
            conn.commit()

        with self.assertRaises(RuntimeError) as ctx_c:
            verify_user_active_datasets_schema(engine, table_name=tbl_wrong_pk)
        self.assertIn("invalid primary key", str(ctx_c.exception).lower())

    # -------------------------------------------------------------------------
    # Test 5: Mocked - Database connection failure prevents initialization
    # -------------------------------------------------------------------------
    def test_05_database_connection_failure_prevents_initialization_mocked(self):
        """
        [Mocked Engine] Verifies that database connection failure during required
        initialization raises a sanitized RuntimeError and does NOT leak credentials.
        """
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = OperationalError(
            "Can't connect to MySQL server",
            params=None,
            orig=Exception("mysql+pymysql://admin:secret_pass_exposed@remote.db.internal:3306/prod_db failed to connect")
        )

        with self.assertRaises(RuntimeError) as ctx:
            ensure_user_active_datasets_table(mock_engine, table_name="user_active_datasets")

        err_msg = str(ctx.exception)
        # Ensure failure is not silently ignored
        self.assertIn("initialization failed", err_msg.lower())
        # Ensure credentials are completely sanitized
        self.assertNotIn("secret_pass_exposed", err_msg)
        self.assertNotIn("admin:secret_pass_exposed", err_msg)
        self.assertIn("[database-host]", err_msg)

    # -------------------------------------------------------------------------
    # Test 6: Mocked & Process - Migration failure prevents application startup
    # -------------------------------------------------------------------------
    def test_06_migration_failure_prevents_application_startup_mocked(self):
        """
        [Mocked & Lifecycle] Verifies that run_startup_migrations raises RuntimeError
        when ensure_user_active_datasets_table fails, stopping application startup.
        """
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = SQLAlchemyError("Database disk is full")

        # Calling run_startup_migrations with a broken engine must raise RuntimeError
        with self.assertRaises(RuntimeError) as ctx:
            run_startup_migrations(db_engine=mock_engine)

        self.assertIn("database initialization failed", str(ctx.exception).lower())

    def test_06b_subshell_startup_aborts_on_invalid_db_real_process(self):
        """
        [Real Process] Spawns python importing app.main with an unreachable database host.
        Verifies that application startup exits with non-zero exit code (aborts startup).
        """
        env = os.environ.copy()
        env["DATABASE_URL"] = "mysql+pymysql://nonexistent_user:bad_pass@127.0.0.1:54321/fake_db"
        # Ensure PROMPTSQL_SKIP_STARTUP_DB_CHECK is not set
        env.pop("PROMPTSQL_SKIP_STARTUP_DB_CHECK", None)

        cmd = [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, 'backend'); from app.main import app; print('UNEXPECTED_SUCCESS')"
        ]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=15)

        # Must have failed (non-zero returncode)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("UNEXPECTED_SUCCESS", result.stdout)
        # Ensure credentials are masked even in process stderr
        self.assertNotIn("bad_pass", result.stderr)

    # -------------------------------------------------------------------------
    # Test 7: Real MySQL - Concurrent initialization does not corrupt table
    # -------------------------------------------------------------------------
    def test_07_concurrent_initialization_real_mysql(self):
        """
        [Real MySQL] Simulates 5 workers simultaneously calling ensure_user_active_datasets_table
        on the exact same table.
        Verifies that advisory locking prevents race conditions, table corruption, or DDL errors.
        """
        table_name = "_test_step42_concurrent_init"
        lock_name = "_test_lock_step42_concur"
        self.cleanup_tables.append(table_name)

        # Drop table before test
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{table_name}`"))
            conn.commit()

        results = []
        errors = []

        def worker_task(worker_id):
            try:
                ensure_user_active_datasets_table(
                    engine,
                    table_name=table_name,
                    lock_name=lock_name,
                    lock_timeout=15
                )
                results.append(worker_id)
            except Exception as e:
                errors.append((worker_id, str(e)))

        # Launch 5 concurrent threads
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker_task, i) for i in range(5)]
            for f in futures:
                f.result()

        # All workers must succeed with 0 exceptions
        self.assertEqual(len(errors), 0, f"Concurrent workers encountered errors: {errors}")
        self.assertEqual(len(results), 5)

        # Final table must exist and have completely valid schema
        res = verify_user_active_datasets_schema(engine, table_name=table_name)
        self.assertTrue(res["valid"])
        self.assertEqual(res["primary_key"], ["user_id"])

    # -------------------------------------------------------------------------
    # Test 8: Real MySQL - Advisory Lock Timeout Handling
    # -------------------------------------------------------------------------
    def test_08_advisory_lock_timeout_handling_real_mysql(self):
        """
        [Real MySQL] Verifies that when another worker holds the advisory lock,
        a secondary worker waiting with a short timeout times out safely
        and raises a descriptive RuntimeError.
        """
        lock_name = "_test_lock_step42_timeout"

        # Conn 1 acquires and holds lock
        conn1 = engine.connect()
        try:
            acquired = acquire_advisory_lock(conn1, lock_name=lock_name, timeout_seconds=5)
            self.assertTrue(acquired)

            # Conn 2 attempts to acquire lock with 1 second timeout
            with self.assertRaises(RuntimeError) as ctx:
                ensure_user_active_datasets_table(
                    engine,
                    table_name="user_active_datasets",
                    lock_name=lock_name,
                    lock_timeout=1
                )
            self.assertIn("failed to acquire advisory migration lock", str(ctx.exception).lower())
        finally:
            release_advisory_lock(conn1, lock_name=lock_name)
            conn1.close()


if __name__ == "__main__":
    unittest.main()
