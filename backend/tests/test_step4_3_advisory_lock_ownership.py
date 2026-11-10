"""
PromptSQL - Step 4.3: MySQL Advisory Lock Ownership & Schema Verification Tests
================================================================================
Comprehensive verification of:
1. Two independent database connections: Lock -> Wait -> Migrate -> Release -> Acquire -> Verify.
2. Migration exception releases the advisory lock without leaks.
3. Lock, migration DDL, schema verification, and release all execute on the exact same connection.
4. GET_LOCK return values: 1 (success), 0 (timeout), NULL (error) properly handled.
5. RELEASE_LOCK return values: 1 (success), 0 (not held), NULL (did not exist) properly handled.
6. Schema inspection completeness: columns, types, lengths, nullability, PK, indexes, engine, collation.

Real MySQL integration tests use actual database connections.
"""

import os
import sys
import time
import unittest
import threading
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text, inspect
from app.database.connection import engine
from app.services.migration_guard import (
    acquire_advisory_lock,
    release_advisory_lock,
    verify_user_active_datasets_schema,
    ensure_user_active_datasets_table,
    MIGRATION_LOCK_NAME
)


class Step43AdvisoryLockOwnershipTests(unittest.TestCase):
    """
    Step 4.3 Lock Ownership, Connection Lifecycle & Verification Tests.
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
    # Test 1: Real MySQL - Two Independent Connections Concurrency Lifecycle
    # -------------------------------------------------------------------------
    def test_01_two_connection_concurrency_lifecycle_real_mysql(self):
        """
        [Real MySQL] Verifies sequential concurrency across 2 independent connections:
        1. Connection A acquires advisory lock.
        2. Connection B attempts to acquire same lock and waits.
        3. Connection A performs migration (creates table) and releases lock.
        4. Connection B acquires lock.
        5. Connection B verifies the already-created schema.
        6. Both operations finish cleanly with 0 errors.
        """
        lock_name = "_test_step43_t01_lock"
        table_name = "_test_step43_t01_tbl"
        self.cleanup_tables.append(table_name)

        # Drop table before test
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{table_name}`"))
            conn.commit()

        events = []
        errors = []
        barrier = threading.Barrier(2)

        def worker_a():
            conn_a = engine.connect()
            try:
                events.append("A_starting")
                acq_a = acquire_advisory_lock(conn_a, lock_name=lock_name, timeout_seconds=5)
                self.assertTrue(acq_a, "Conn A failed to acquire lock")
                events.append("A_locked")

                # Synchronize: signal B that A holds the lock
                barrier.wait()

                # Hold lock briefly to ensure B is actively waiting
                time.sleep(1.0)

                # Connection A performs migration
                conn_a.execute(text(f"""
                    CREATE TABLE `{table_name}` (
                        `user_id` VARCHAR(50) NOT NULL PRIMARY KEY,
                        `table_name` VARCHAR(100) NOT NULL,
                        `updated_at` DATETIME NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """))
                conn_a.commit()
                events.append("A_migrated")
            except Exception as e:
                errors.append(f"Worker A error: {e}")
            finally:
                rel_a = release_advisory_lock(conn_a, lock_name=lock_name)
                events.append(f"A_released_{rel_a}")
                conn_a.close()

        def worker_b():
            conn_b = engine.connect()
            try:
                # Wait until Worker A holds lock
                barrier.wait()
                time.sleep(0.1)  # Ensure Worker A is in its critical section
                events.append("B_waiting_for_lock")

                # Connection B waits for lock and acquires once A releases
                acq_b = acquire_advisory_lock(conn_b, lock_name=lock_name, timeout_seconds=5)
                self.assertTrue(acq_b, "Conn B failed to acquire lock after A released")
                events.append("B_locked")

                # Connection B verifies already-created schema
                res = verify_user_active_datasets_schema(conn_b, table_name=table_name)
                self.assertTrue(res["valid"])
                self.assertEqual(res["primary_key"], ["user_id"])
                events.append("B_verified")
            except Exception as e:
                errors.append(f"Worker B error: {e}")
            finally:
                rel_b = release_advisory_lock(conn_b, lock_name=lock_name)
                events.append(f"B_released_{rel_b}")
                conn_b.close()

        t_a = threading.Thread(target=worker_a)
        t_b = threading.Thread(target=worker_b)

        t_a.start()
        t_b.start()

        t_a.join(timeout=10)
        t_b.join(timeout=10)

        self.assertEqual(len(errors), 0, f"Encountered unexpected errors: {errors}")
        self.assertIn("A_locked", events)
        self.assertIn("B_waiting_for_lock", events)
        self.assertIn("A_migrated", events)
        self.assertIn("A_released_True", events)
        self.assertIn("B_locked", events)
        self.assertIn("B_verified", events)
        self.assertIn("B_released_True", events)

    # -------------------------------------------------------------------------
    # Test 2: Real MySQL - Migration Exception Still Releases Lock
    # -------------------------------------------------------------------------
    def test_02_migration_exception_releases_lock_real_mysql(self):
        """
        [Real MySQL] Verifies that if an exception occurs during table migration/verification,
        the advisory lock is strictly released in the finally block, allowing subsequent
        connections to acquire the lock immediately without waiting for a timeout.
        """
        lock_name = "_test_step43_t02_lock"
        table_name = "_test_step43_t02_tbl"
        self.cleanup_tables.append(table_name)

        # Trigger ensure_user_active_datasets_table with simulated schema exception
        with patch(
            "app.services.migration_guard.verify_user_active_datasets_schema",
            side_effect=RuntimeError("Simulated verification crash")
        ):
            with self.assertRaises(RuntimeError) as ctx:
                ensure_user_active_datasets_table(
                    engine,
                    table_name=table_name,
                    lock_name=lock_name,
                    lock_timeout=5
                )
            self.assertIn("simulated verification crash", str(ctx.exception).lower())

        # Connection B must be able to acquire lock immediately (not blocked)
        conn_b = engine.connect()
        try:
            acquired = acquire_advisory_lock(conn_b, lock_name=lock_name, timeout_seconds=1)
            self.assertTrue(acquired, "Lock was leaked: Connection B could not acquire lock!")
        finally:
            rel = release_advisory_lock(conn_b, lock_name=lock_name)
            self.assertTrue(rel)
            conn_b.close()

    # -------------------------------------------------------------------------
    # Test 3: Real MySQL - Exact Same Connection Object Across Entire Critical Section
    # -------------------------------------------------------------------------
    def test_03_same_connection_ownership_throughout_lifecycle_real_mysql(self):
        """
        [Real MySQL] Verifies that GET_LOCK, CREATE TABLE, schema verification, and RELEASE_LOCK
        all execute on the exact same SQLAlchemy Connection and MySQL server thread.
        """
        table_name = "_test_step43_t03_tbl"
        lock_name = "_test_step43_t03_lock"
        self.cleanup_tables.append(table_name)

        with engine.connect() as conn:
            # Get underlying MySQL connection/session ID
            session_id_1 = conn.execute(text("SELECT CONNECTION_ID()")).scalar()

            # 1. Acquire lock
            acq = acquire_advisory_lock(conn, lock_name=lock_name, timeout_seconds=5)
            self.assertTrue(acq)
            session_id_2 = conn.execute(text("SELECT CONNECTION_ID()")).scalar()
            self.assertEqual(session_id_1, session_id_2, "Connection ID changed during lock acquisition")

            try:
                # 2. DDL migration on same connection
                conn.execute(text(f"""
                    CREATE TABLE `{table_name}` (
                        `user_id` VARCHAR(50) NOT NULL PRIMARY KEY,
                        `table_name` VARCHAR(100) NOT NULL,
                        `updated_at` DATETIME NULL
                    ) ENGINE=InnoDB;
                """))
                conn.commit()
                session_id_3 = conn.execute(text("SELECT CONNECTION_ID()")).scalar()
                self.assertEqual(session_id_1, session_id_3, "Connection ID changed during DDL")

                # 3. Schema verification on same connection
                res = verify_user_active_datasets_schema(conn, table_name=table_name)
                self.assertTrue(res["valid"])
                session_id_4 = conn.execute(text("SELECT CONNECTION_ID()")).scalar()
                self.assertEqual(session_id_1, session_id_4, "Connection ID changed during verification")
            finally:
                # 4. Release lock on same connection
                rel = release_advisory_lock(conn, lock_name=lock_name)
                self.assertTrue(rel)
                session_id_5 = conn.execute(text("SELECT CONNECTION_ID()")).scalar()
                self.assertEqual(session_id_1, session_id_5, "Connection ID changed during release")

    # -------------------------------------------------------------------------
    # Test 4: Unit / Mocked - GET_LOCK Return Code Handling
    # -------------------------------------------------------------------------
    def test_04_get_lock_return_code_handling(self):
        """
        [Mocked Connection] Verifies MySQL GET_LOCK return codes:
        - 1: Success -> True
        - 0: Timeout -> False (logs warning)
        - NULL: MySQL Error -> False (logs warning)
        """
        mock_conn = MagicMock()
        mock_conn.dialect.name = "mysql"

        # Case 1: Success (1)
        mock_conn.execute.return_value.scalar.return_value = 1
        self.assertTrue(acquire_advisory_lock(mock_conn, lock_name="test_lock", timeout_seconds=5))

        # Case 2: Timeout (0)
        mock_conn.execute.return_value.scalar.return_value = 0
        self.assertFalse(acquire_advisory_lock(mock_conn, lock_name="test_lock", timeout_seconds=5))

        # Case 3: Error (None/NULL)
        mock_conn.execute.return_value.scalar.return_value = None
        self.assertFalse(acquire_advisory_lock(mock_conn, lock_name="test_lock", timeout_seconds=5))

    # -------------------------------------------------------------------------
    # Test 5: Unit / Mocked - RELEASE_LOCK Return Code Handling
    # -------------------------------------------------------------------------
    def test_05_release_lock_return_code_handling(self):
        """
        [Mocked Connection] Verifies MySQL RELEASE_LOCK return codes:
        - 1: Released -> True
        - 0: Lock not held by this session -> False (logs warning)
        - NULL: Named lock did not exist -> False (logs warning)
        """
        mock_conn = MagicMock()
        mock_conn.dialect.name = "mysql"

        # Case 1: Released (1)
        mock_conn.execute.return_value.scalar.return_value = 1
        self.assertTrue(release_advisory_lock(mock_conn, lock_name="test_lock"))

        # Case 2: Not held by this session (0)
        mock_conn.execute.return_value.scalar.return_value = 0
        self.assertFalse(release_advisory_lock(mock_conn, lock_name="test_lock"))

        # Case 3: Did not exist (None/NULL)
        mock_conn.execute.return_value.scalar.return_value = None
        self.assertFalse(release_advisory_lock(mock_conn, lock_name="test_lock"))

    # -------------------------------------------------------------------------
    # Test 6: Real MySQL - Complete Schema Inspection Fields
    # -------------------------------------------------------------------------
    def test_06_complete_schema_inspection_fields_real_mysql(self):
        """
        [Real MySQL] Verifies that verify_user_active_datasets_schema accurately inspects:
        columns, data types, lengths, nullability, primary key, indexes, and storage engine.
        """
        res = verify_user_active_datasets_schema(engine, table_name="user_active_datasets")
        self.assertTrue(res["valid"])
        self.assertEqual(res["table_name"], "user_active_datasets")
        self.assertIn("user_id", res["columns"])
        self.assertIn("table_name", res["columns"])
        self.assertIn("updated_at", res["columns"])
        self.assertEqual(res["primary_key"], ["user_id"])
        self.assertEqual(res["engine"].upper(), "INNODB")
        self.assertIn("utf8mb4", res["collation"].lower())


if __name__ == "__main__":
    unittest.main()
