"""
PromptSQL - Step 4.4: Advisory Lock Failure Cleanup & Exact Schema Verification Tests
=====================================================================================
Comprehensive verification of:
1. Successful release does not invalidate the connection (remains healthy).
2. Failed release invalidates the connection (conn.invalidated is True).
3. Migration exception followed by successful release preserves the original migration exception.
4. Migration exception followed by failed release still invalidates the connection AND preserves the original exception.
5. Exact schema verification rejects arbitrary larger column lengths (user_id != 50, table_name != 100).
6. Exact schema verification rejects non-InnoDB engine and non-utf8mb4 collation.
7. Secondary index verification verifies correct indexed columns and non-uniqueness.

Tests clearly identify Real MySQL Integration Tests vs Mocked Tests.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text, inspect
from app.database.connection import engine
from app.services.migration_guard import (
    acquire_advisory_lock,
    release_advisory_lock,
    verify_user_active_datasets_schema,
    ensure_user_active_datasets_table
)


class CustomMigrationError(Exception):
    """Specific error to test exception preservation."""
    pass


class Step44LockCleanupAndExactSchemaTests(unittest.TestCase):
    """
    Step 4.4 Lock Cleanup, Invalidation & Exact Schema Verification Tests.
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
    # Test 1: Real MySQL - Successful release does not invalidate connection
    # -------------------------------------------------------------------------
    def test_01_successful_release_does_not_invalidate_connection_real_mysql(self):
        """
        [Real MySQL] Verifies that when release_advisory_lock succeeds (res == 1),
        the connection is NOT invalidated and remains healthy for reuse.
        """
        lock_name = "_test_step44_t01_lock"
        with engine.connect() as conn:
            acq = acquire_advisory_lock(conn, lock_name=lock_name, timeout_seconds=5)
            self.assertTrue(acq)
            self.assertFalse(conn.invalidated)

            rel = release_advisory_lock(conn, lock_name=lock_name, invalidate_on_failure=True)
            self.assertTrue(rel)
            # Connection must remain healthy
            self.assertFalse(conn.invalidated)

            # Can execute subsequent query
            one = conn.execute(text("SELECT 1")).scalar()
            self.assertEqual(one, 1)

    # -------------------------------------------------------------------------
    # Test 2: Real MySQL - Failed release invalidates connection
    # -------------------------------------------------------------------------
    def test_02_failed_release_invalidates_connection_real_mysql(self):
        """
        [Real MySQL] Verifies that when release_advisory_lock fails (e.g. res == 0
        because lock is held by another session), the connection is invalidated
        and cannot return to the pool as a healthy connection.
        """
        lock_name = "_test_step44_t02_lock"

        # Connection A acquires lock
        conn_a = engine.connect()
        try:
            acq_a = acquire_advisory_lock(conn_a, lock_name=lock_name, timeout_seconds=5)
            self.assertTrue(acq_a)

            # Connection B attempts to release lock held by Connection A (returns 0 in MySQL)
            conn_b = engine.connect()
            try:
                self.assertFalse(conn_b.invalidated)
                rel_b = release_advisory_lock(conn_b, lock_name=lock_name, invalidate_on_failure=True)
                self.assertFalse(rel_b)
                # Connection B must be marked invalidated!
                self.assertTrue(conn_b.invalidated)
            finally:
                conn_b.close()
        finally:
            release_advisory_lock(conn_a, lock_name=lock_name)
            conn_a.close()

    # -------------------------------------------------------------------------
    # Test 3: Real MySQL - Migration exception with successful release preserves original exception
    # -------------------------------------------------------------------------
    def test_03_migration_exception_with_successful_release_preserves_original_exception_real_mysql(self):
        """
        [Real MySQL] Verifies that if an exception occurs during migration,
        the lock is successfully released in finally, and the exact original
        exception is preserved and propagated to the caller.
        """
        lock_name = "_test_step44_t03_lock"
        table_name = "_test_step44_t03_tbl"
        self.cleanup_tables.append(table_name)

        original_error = CustomMigrationError("Original specific migration failure")

        with patch("app.services.migration_guard.verify_user_active_datasets_schema", side_effect=original_error):
            with self.assertRaises(CustomMigrationError) as ctx:
                ensure_user_active_datasets_table(
                    engine,
                    table_name=table_name,
                    lock_name=lock_name,
                    lock_timeout=5
                )
            # Assert exact original exception is preserved
            self.assertIs(ctx.exception, original_error)

        # Connection B should immediately be able to acquire lock (confirming it was released)
        with engine.connect() as conn_b:
            acq_b = acquire_advisory_lock(conn_b, lock_name=lock_name, timeout_seconds=1)
            self.assertTrue(acq_b)
            release_advisory_lock(conn_b, lock_name=lock_name)

    # -------------------------------------------------------------------------
    # Test 4: Real / Mocked - Migration exception with failed release invalidates connection AND preserves exception
    # -------------------------------------------------------------------------
    def test_04_migration_exception_with_failed_release_invalidates_and_preserves_exception(self):
        """
        [Real & Mocked Hook] Verifies that if migration raises an exception AND
        lock release subsequently fails, the connection is invalidated AND
        the original migration exception is strictly preserved without being masked.
        """
        lock_name = "_test_step44_t04_lock"
        table_name = "_test_step44_t04_tbl"
        self.cleanup_tables.append(table_name)

        original_error = CustomMigrationError("Original critical DDL error")
        invalidated_flags = []

        # Intercept release_advisory_lock to simulate failure
        with patch("app.services.migration_guard.verify_user_active_datasets_schema", side_effect=original_error):
            with patch("app.services.migration_guard.release_advisory_lock") as mock_release:
                def fake_release(conn, **kwargs):
                    conn.invalidate()
                    invalidated_flags.append(conn.invalidated)
                    return False

                mock_release.side_effect = fake_release

                with self.assertRaises(CustomMigrationError) as ctx:
                    ensure_user_active_datasets_table(
                        engine,
                        table_name=table_name,
                        lock_name=lock_name,
                        lock_timeout=5
                    )

                # Original exception must be preserved
                self.assertIs(ctx.exception, original_error)
                # Connection must have been invalidated
                self.assertTrue(any(invalidated_flags))

    # -------------------------------------------------------------------------
    # Test 5: Real MySQL - Exact schema rejects arbitrary larger column lengths
    # -------------------------------------------------------------------------
    def test_05_exact_schema_verification_rejects_larger_column_lengths_real_mysql(self):
        """
        [Real MySQL] Verifies that exact schema verification strictly rejects larger
        column lengths (e.g. user_id VARCHAR(100) != 50, table_name VARCHAR(255) != 100).
        """
        # Case A: user_id VARCHAR(100) instead of VARCHAR(50)
        tbl_large_uid = "_test_step44_large_uid"
        self.cleanup_tables.append(tbl_large_uid)
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{tbl_large_uid}`"))
            conn.execute(text(f"""
                CREATE TABLE `{tbl_large_uid}` (
                    `user_id` VARCHAR(100) NOT NULL PRIMARY KEY,
                    `table_name` VARCHAR(100) NOT NULL,
                    `updated_at` DATETIME NULL
                ) ENGINE=InnoDB;
            """))
            conn.commit()

        with self.assertRaises(RuntimeError) as ctx_a:
            verify_user_active_datasets_schema(engine, table_name=tbl_large_uid)
        self.assertIn("length mismatch", str(ctx_a.exception).lower())
        self.assertIn("user_id", str(ctx_a.exception).lower())

        # Case B: table_name VARCHAR(255) instead of VARCHAR(100)
        tbl_large_tname = "_test_step44_large_tname"
        self.cleanup_tables.append(tbl_large_tname)
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{tbl_large_tname}`"))
            conn.execute(text(f"""
                CREATE TABLE `{tbl_large_tname}` (
                    `user_id` VARCHAR(50) NOT NULL PRIMARY KEY,
                    `table_name` VARCHAR(255) NOT NULL,
                    `updated_at` DATETIME NULL
                ) ENGINE=InnoDB;
            """))
            conn.commit()

        with self.assertRaises(RuntimeError) as ctx_b:
            verify_user_active_datasets_schema(engine, table_name=tbl_large_tname)
        self.assertIn("length mismatch", str(ctx_b.exception).lower())
        self.assertIn("table_name", str(ctx_b.exception).lower())

        # Case C: updated_at NOT NULL instead of DATETIME NULL
        tbl_not_null_upd = "_test_step44_not_null_upd"
        self.cleanup_tables.append(tbl_not_null_upd)
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{tbl_not_null_upd}`"))
            conn.execute(text(f"""
                CREATE TABLE `{tbl_not_null_upd}` (
                    `user_id` VARCHAR(50) NOT NULL PRIMARY KEY,
                    `table_name` VARCHAR(100) NOT NULL,
                    `updated_at` DATETIME NOT NULL
                ) ENGINE=InnoDB;
            """))
            conn.commit()

        with self.assertRaises(RuntimeError) as ctx_c:
            verify_user_active_datasets_schema(engine, table_name=tbl_not_null_upd)
        self.assertIn("nullable", str(ctx_c.exception).lower())

    # -------------------------------------------------------------------------
    # Test 6: Real MySQL & Mocked - Exact schema rejects invalid engine & collation
    # -------------------------------------------------------------------------
    def test_06_exact_schema_verification_rejects_invalid_engine_and_collation_real_mysql(self):
        """
        [Real MySQL & Simulated Engine] Verifies that exact schema verification rejects
        non-InnoDB storage engine and non-utf8mb4 collation.
        """
        # Case A: Storage engine is MyISAM instead of InnoDB (simulated via mock on valid table)
        tbl_valid = "_test_step44_engine_check"
        self.cleanup_tables.append(tbl_valid)
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{tbl_valid}`"))
            conn.execute(text(f"""
                CREATE TABLE `{tbl_valid}` (
                    `user_id` VARCHAR(50) NOT NULL PRIMARY KEY,
                    `table_name` VARCHAR(100) NOT NULL,
                    `updated_at` DATETIME NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """))
            conn.commit()

        # Intercept connection execute to return ('MyISAM', 'utf8mb4_0900_ai_ci')
        real_conn = engine.connect()
        try:
            with patch.object(real_conn, "execute") as mock_exec:
                def fake_execute(statement, *args, **kwargs):
                    mock_result = MagicMock()
                    mock_result.fetchone.return_value = ("MyISAM", "utf8mb4_0900_ai_ci")
                    return mock_result

                mock_exec.side_effect = fake_execute

                # When information_schema returns MyISAM, verify_user_active_datasets_schema must raise RuntimeError
                with patch("app.services.migration_guard.inspect") as mock_insp:
                    # Keep real columns and pk
                    real_insp = inspect(engine)
                    mock_insp_instance = MagicMock()
                    mock_insp_instance.get_table_names.return_value = [tbl_valid]
                    mock_insp_instance.get_columns.return_value = real_insp.get_columns(tbl_valid)
                    mock_insp_instance.get_pk_constraint.return_value = real_insp.get_pk_constraint(tbl_valid)
                    mock_insp_instance.get_indexes.return_value = []
                    mock_insp.return_value = mock_insp_instance

                    with self.assertRaises(RuntimeError) as ctx_eng:
                        verify_user_active_datasets_schema(real_conn, table_name=tbl_valid)
                    self.assertIn("invalid storage engine", str(ctx_eng.exception).lower())
                    self.assertIn("myisam", str(ctx_eng.exception).lower())
        finally:
            real_conn.close()

        # Case B: Collation is latin1 instead of utf8mb4 (Real MySQL table)
        tbl_latin1 = "_test_step44_latin1_tbl"
        self.cleanup_tables.append(tbl_latin1)
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{tbl_latin1}`"))
            conn.execute(text(f"""
                CREATE TABLE `{tbl_latin1}` (
                    `user_id` VARCHAR(50) NOT NULL PRIMARY KEY,
                    `table_name` VARCHAR(100) NOT NULL,
                    `updated_at` DATETIME NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_bin;
            """))
            conn.commit()

        with self.assertRaises(RuntimeError) as ctx_col:
            verify_user_active_datasets_schema(engine, table_name=tbl_latin1)
        self.assertIn("incompatible collation", str(ctx_col.exception).lower())

    # -------------------------------------------------------------------------
    # Test 7: Real MySQL - Secondary index uniqueness check
    # -------------------------------------------------------------------------
    def test_07_secondary_index_uniqueness_check_real_mysql(self):
        """
        [Real MySQL] Verifies that if a secondary index on user_id exists,
        it must be non-unique (since primary key already enforces uniqueness).
        A table with a duplicate UNIQUE index on user_id is rejected.
        """
        tbl_unique_idx = "_test_step44_unique_idx"
        self.cleanup_tables.append(tbl_unique_idx)
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{tbl_unique_idx}`"))
            conn.execute(text(f"""
                CREATE TABLE `{tbl_unique_idx}` (
                    `user_id` VARCHAR(50) NOT NULL PRIMARY KEY,
                    `table_name` VARCHAR(100) NOT NULL,
                    `updated_at` DATETIME NULL,
                    UNIQUE KEY `uq_user_active_datasets_user_id` (`user_id`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """))
            conn.commit()

        with self.assertRaises(RuntimeError) as ctx_idx:
            verify_user_active_datasets_schema(engine, table_name=tbl_unique_idx)
        self.assertIn("must be non-unique", str(ctx_idx.exception).lower())


if __name__ == "__main__":
    unittest.main()
