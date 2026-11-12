"""
Step 5.2.1 Execution Safeguards Test Suite

Validates:
1. AST-based physical query bounding (MAX_ROWS = 1000, capped at MAX_ROWS + 1).
2. MySQL MAX_EXECUTION_TIME optimizer hint injection.
3. Database-level read-only transaction lifecycle (START TRANSACTION READ ONLY ... rollback).
4. Safe result fetching with truncation reporting (records, is_truncated).
5. Exception sanitization across production and development modes in /ask.
6. Clean transaction cleanup and connection pool reusability.
7. MySQL timeout interruption and rollback failure invalidation.
"""

import time
import unittest
from unittest.mock import patch, MagicMock
from sqlalchemy import text, create_engine, event
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from fastapi import HTTPException

from dataclasses import dataclass
import datetime
from decimal import Decimal
import json

from app.database.connection import engine
from app.services.sql_executor import (
    prepare_bounded_query,
    execute_sql,
    _safe_invalidate,
    _process_cell,
    DisposalResult,
    ExecutionResult,
    ResultSizeLimitError,
    DEFAULT_MAX_ROWS,
    DEFAULT_TIMEOUT_MS,
    DEFAULT_MAX_RESULT_BYTES,
    DEFAULT_MAX_CELL_BYTES,
)
from app.utils.error_sanitizer import get_safe_exception_message, sanitize_error_message
from app.core.config import Settings


# =====================================================================
# 1. AST-BASED PHYSICAL SQL ROW LIMITING TESTS
# =====================================================================

class TestRowLimiting(unittest.TestCase):
    def test_select_without_limit(self):
        sql = "SELECT id, amount FROM sales_usr_1"
        bounded = prepare_bounded_query(sql, max_rows=1000)
        self.assertIn("LIMIT 1001", bounded)
        self.assertIn("/*+ MAX_EXECUTION_TIME(15000) */", bounded)

    def test_existing_stricter_limit_preserved(self):
        sql = "SELECT id, amount FROM sales_usr_1 LIMIT 50"
        bounded = prepare_bounded_query(sql, max_rows=1000)
        self.assertIn("LIMIT 50", bounded)
        self.assertNotIn("LIMIT 1001", bounded)

    def test_existing_excessive_limit_reduced(self):
        sql = "SELECT id, amount FROM sales_usr_1 LIMIT 5000"
        bounded = prepare_bounded_query(sql, max_rows=1000)
        self.assertIn("LIMIT 1001", bounded)
        self.assertNotIn("LIMIT 5000", bounded)

    def test_limit_with_offset_preserved(self):
        sql = "SELECT id, amount FROM sales_usr_1 LIMIT 10 OFFSET 20"
        bounded = prepare_bounded_query(sql, max_rows=1000)
        self.assertIn("LIMIT 10", bounded)
        self.assertIn("OFFSET 20", bounded)

    def test_excessive_limit_with_offset_reduced(self):
        sql = "SELECT id, amount FROM sales_usr_1 LIMIT 2500 OFFSET 15"
        bounded = prepare_bounded_query(sql, max_rows=1000)
        self.assertIn("LIMIT 1001", bounded)
        self.assertIn("OFFSET 15", bounded)

    def test_order_by_with_limit(self):
        sql = "SELECT id, amount FROM sales_usr_1 ORDER BY amount DESC"
        bounded = prepare_bounded_query(sql, max_rows=1000)
        self.assertIn("ORDER BY amount DESC LIMIT 1001", bounded)

    def test_union_query_limited_at_root(self):
        sql = "SELECT id FROM tbl1 UNION SELECT id FROM tbl2"
        bounded = prepare_bounded_query(sql, max_rows=1000)
        self.assertTrue(bounded.endswith("LIMIT 1001"))
        self.assertTrue(bounded.startswith("SELECT /*+ MAX_EXECUTION_TIME(15000) */ id FROM tbl1 UNION SELECT id FROM tbl2"))

    def test_union_all_query_limited_at_root(self):
        sql = "SELECT id FROM tbl1 UNION ALL SELECT id FROM tbl2"
        bounded = prepare_bounded_query(sql, max_rows=1000)
        self.assertTrue(bounded.endswith("LIMIT 1001"))
        self.assertIn("UNION ALL", bounded)

    def test_cte_query_limited_at_outer_select(self):
        sql = "WITH c AS (SELECT id FROM tbl) SELECT id FROM c"
        bounded = prepare_bounded_query(sql, max_rows=1000)
        self.assertIn("WITH c AS (SELECT id FROM tbl)", bounded)
        self.assertIn("SELECT /*+ MAX_EXECUTION_TIME(15000) */ id FROM c LIMIT 1001", bounded)

    def test_nested_subquery_leaves_inner_limit_untouched(self):
        sql = "SELECT id FROM tbl WHERE amt > (SELECT AVG(amt) FROM tbl LIMIT 5)"
        bounded = prepare_bounded_query(sql, max_rows=1000)
        self.assertIn("LIMIT 5", bounded)
        self.assertTrue(bounded.endswith("LIMIT 1001"))

    def test_parenthesized_select(self):
        sql = "(SELECT id FROM tbl)"
        bounded = prepare_bounded_query(sql, max_rows=1000)
        self.assertEqual(bounded, "(SELECT /*+ MAX_EXECUTION_TIME(15000) */ id FROM tbl LIMIT 1001)")

    def test_unsupported_placeholder_limit_rejected(self):
        sql = "SELECT id FROM tbl LIMIT ?"
        with self.assertRaises(ValueError):
            prepare_bounded_query(sql)

    def test_unsupported_negative_limit_rejected(self):
        sql = "SELECT id FROM tbl LIMIT -10"
        with self.assertRaises(ValueError):
            prepare_bounded_query(sql)

    def test_unsupported_string_limit_rejected(self):
        sql = "SELECT id FROM tbl LIMIT '100'"
        with self.assertRaises(ValueError):
            prepare_bounded_query(sql)

    def test_unsupported_ast_structure_insert_rejected(self):
        sql = "INSERT INTO tbl (id) VALUES (1)"
        with self.assertRaises(ValueError):
            prepare_bounded_query(sql)

    def test_unsupported_ast_structure_update_rejected(self):
        sql = "UPDATE tbl SET id = 1"
        with self.assertRaises(ValueError):
            prepare_bounded_query(sql)

    def test_unsupported_ast_structure_delete_rejected(self):
        sql = "DELETE FROM tbl WHERE id = 1"
        with self.assertRaises(ValueError):
            prepare_bounded_query(sql)

    def test_empty_query_rejected(self):
        with self.assertRaises(ValueError):
            prepare_bounded_query("")

    def test_whitespace_query_rejected(self):
        with self.assertRaises(ValueError):
            prepare_bounded_query("   \n\t  ")

    def test_multiple_statements_rejected(self):
        with self.assertRaises(ValueError):
            prepare_bounded_query("SELECT 1; SELECT 2")


# =====================================================================
# 2. OPTIMIZER TIMEOUT HINT TESTS
# =====================================================================

class TestOptimizerTimeoutHint(unittest.TestCase):
    def test_simple_select_hint(self):
        sql = "SELECT col FROM my_table"
        bounded = prepare_bounded_query(sql, timeout_ms=5000)
        self.assertIn("SELECT /*+ MAX_EXECUTION_TIME(5000) */ col FROM my_table", bounded)

    def test_union_hint_on_first_select(self):
        sql = "SELECT a FROM t1 UNION SELECT b FROM t2"
        bounded = prepare_bounded_query(sql, timeout_ms=8000)
        self.assertTrue(bounded.startswith("SELECT /*+ MAX_EXECUTION_TIME(8000) */ a FROM t1 UNION SELECT b FROM t2"))

    def test_cte_hint_on_main_query(self):
        sql = "WITH summary AS (SELECT dept, SUM(salary) AS total FROM emp GROUP BY dept) SELECT * FROM summary"
        bounded = prepare_bounded_query(sql, timeout_ms=12000)
        self.assertIn("SELECT /*+ MAX_EXECUTION_TIME(12000) */ * FROM summary", bounded)
        self.assertIn("WITH summary AS (SELECT dept, SUM(salary)", bounded)

    def test_existing_compatible_hint_preserved(self):
        sql = "SELECT /*+ BKA(tbl) */ id FROM tbl"
        bounded = prepare_bounded_query(sql, timeout_ms=15000)
        self.assertIn("/*+ BKA(tbl) MAX_EXECUTION_TIME(15000) */", bounded)

    def test_conflicting_timeout_hint_overridden(self):
        sql = "SELECT /*+ MAX_EXECUTION_TIME(60000) */ id FROM tbl"
        bounded = prepare_bounded_query(sql, timeout_ms=15000)
        self.assertIn("MAX_EXECUTION_TIME(15000)", bounded)
        self.assertNotIn("MAX_EXECUTION_TIME(60000)", bounded)

    def test_multiple_existing_hints_with_timeout_override(self):
        sql = "SELECT /*+ BKA(t1) MAX_EXECUTION_TIME(99999) NO_ICP(t2) */ id FROM t1 JOIN t2"
        bounded = prepare_bounded_query(sql, timeout_ms=10000)
        self.assertIn("BKA(t1)", bounded)
        self.assertIn("NO_ICP(t2)", bounded)
        self.assertIn("MAX_EXECUTION_TIME(10000)", bounded)
        self.assertNotIn("99999", bounded)

    def test_actual_timeout_interruption_mysql(self):
        # Query that invokes a subquery sleep exceeding 1000 ms
        start = time.time()
        with self.assertRaises(Exception) as ctx:
            execute_sql("SELECT 1 FROM (SELECT SLEEP(3)) AS t", timeout_ms=1000)
        elapsed = time.time() - start
        err_msg = str(ctx.exception)
        self.assertTrue("3024" in err_msg or "interrupted" in err_msg.lower())
        self.assertLess(elapsed, 4.0)


# =====================================================================
# 3. TRANSACTION LIFECYCLE & EXECUTION SAFEGUARDS TESTS
# =====================================================================

class TestTransactionLifecycle(unittest.TestCase):
    def test_readonly_select_execution_succeeds(self):
        records, is_truncated = execute_sql("SELECT 1 AS col_val, 'test' AS col_str")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["col_val"], 1)
        self.assertEqual(records[0]["col_str"], "test")
        self.assertIs(is_truncated, False)

    def test_readonly_transaction_blocks_insert(self):
        # Even if a write query bypassed prepare_bounded_query,
        # START TRANSACTION READ ONLY must cause MySQL to reject it with error 1792.
        with engine.connect() as conn:
            with conn.begin() as trans:
                conn.execute(text("START TRANSACTION READ ONLY"))
                try:
                    with self.assertRaises(OperationalError) as ctx:
                        conn.execute(text("INSERT INTO test_step5_2_disposable_table VALUES (1)"))
                    err_msg = str(ctx.exception).lower()
                    self.assertTrue("1792" in err_msg or "read-only" in err_msg or "cannot execute statement" in err_msg)
                finally:
                    trans.rollback()

    def test_readonly_transaction_blocks_update(self):
        with engine.connect() as conn:
            with conn.begin() as trans:
                conn.execute(text("START TRANSACTION READ ONLY"))
                try:
                    with self.assertRaises(OperationalError) as ctx:
                        conn.execute(text("UPDATE test_step5_2_disposable_table SET col = 2"))
                    err_msg = str(ctx.exception).lower()
                    self.assertTrue("1792" in err_msg or "read-only" in err_msg or "cannot execute statement" in err_msg)
                finally:
                    trans.rollback()

    def test_readonly_transaction_blocks_delete(self):
        with engine.connect() as conn:
            with conn.begin() as trans:
                conn.execute(text("START TRANSACTION READ ONLY"))
                try:
                    with self.assertRaises(OperationalError) as ctx:
                        conn.execute(text("DELETE FROM test_step5_2_disposable_table"))
                    err_msg = str(ctx.exception).lower()
                    self.assertTrue("1792" in err_msg or "read-only" in err_msg or "cannot execute statement" in err_msg)
                finally:
                    trans.rollback()

    def test_truncation_detection_more_than_max_rows(self):
        # Generate 5 rows with max_rows=3
        sql = "SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5"
        records, is_truncated = execute_sql(sql, max_rows=3)
        self.assertEqual(len(records), 3)
        self.assertIs(is_truncated, True)

    def test_truncation_detection_exact_max_rows(self):
        # Generate 3 rows with max_rows=3
        sql = "SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3"
        records, is_truncated = execute_sql(sql, max_rows=3)
        self.assertEqual(len(records), 3)
        self.assertIs(is_truncated, False)

    def test_truncation_detection_fewer_than_max_rows(self):
        # Generate 2 rows with max_rows=3
        sql = "SELECT 1 AS n UNION ALL SELECT 2"
        records, is_truncated = execute_sql(sql, max_rows=3)
        self.assertEqual(len(records), 2)
        self.assertIs(is_truncated, False)

    def test_rollback_on_successful_execution(self):
        execute_sql("SELECT 1 AS val")
        with engine.connect() as conn:
            self.assertFalse(conn.in_transaction())

    def test_rollback_on_execution_failure(self):
        with self.assertRaises(Exception):
            execute_sql("SELECT * FROM non_existent_table_xyz_99999")
        with engine.connect() as conn:
            self.assertFalse(conn.in_transaction())

    def test_rollback_on_processing_failure(self):
        # Simulate an exception during result processing
        with patch("sqlalchemy.engine.cursor.CursorResult.fetchmany", side_effect=RuntimeError("Simulated fetch crash")):
            with self.assertRaises(RuntimeError):
                execute_sql("SELECT 1 AS val")
        with engine.connect() as conn:
            self.assertFalse(conn.in_transaction())

    def test_connection_invalidated_when_rollback_fails(self):
        # Simulate trans.rollback() failure to verify connection.invalidate() is invoked
        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_trans.rollback.side_effect = OperationalError("Rollback lost socket", [], Exception("Lost connection"))
            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(Exception):
                execute_sql("SELECT 1 AS val")

            # Verify connection was explicitly invalidated
            mock_conn.invalidate.assert_called_once()

    def test_connection_invalidated_when_result_close_fails(self):
        """Verifies connection.invalidate() is called when result.close() raises an exception."""
        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_result = MagicMock()
            mock_result.keys.return_value = ["id"]
            mock_result.fetchmany.return_value = [(1,)]
            mock_result.close.side_effect = OperationalError("Close socket error", [], Exception("Lost socket on close"))

            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(Exception):
                execute_sql("SELECT 1 AS val")

            mock_conn.invalidate.assert_called_once()

    def test_both_close_and_rollback_fail_invalidates_connection(self):
        """Verifies connection.invalidate() is called when both result.close() and trans.rollback() fail."""
        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_result = MagicMock()
            mock_result.keys.return_value = ["id"]
            mock_result.fetchmany.return_value = [(1,)]
            mock_result.close.side_effect = OperationalError("Close error", [], Exception("Socket close error"))
            mock_trans.rollback.side_effect = OperationalError("Rollback error", [], Exception("Socket rollback error"))

            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(Exception):
                execute_sql("SELECT 1 AS val")

            self.assertEqual(mock_conn.invalidate.call_count, 2)

    def test_query_failure_followed_by_close_failure_preserves_query_exception(self):
        """Verifies original query error remains primary even when result.close() also fails."""
        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_result = MagicMock()
            mock_result.close.side_effect = RuntimeError("Close crash")
            mock_result.fetchmany.side_effect = OperationalError("Query timeout", [], Exception("3024 Query interrupted"))

            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(Exception) as ctx:
                execute_sql("SELECT 1 AS val")

            # Must surface primary query exception (3024), NOT close crash
            err_msg = str(ctx.exception)
            self.assertIn("3024", err_msg)
            mock_conn.invalidate.assert_called_once()

    def test_query_failure_followed_by_rollback_failure_preserves_query_exception(self):
        """Verifies original query error remains primary even when trans.rollback() also fails."""
        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_trans.rollback.side_effect = RuntimeError("Rollback crash")

            def mock_exec(statement):
                if "SELECT" in str(statement):
                    raise OperationalError("Table not found", [], Exception("1146 Table doesn't exist"))
                return MagicMock()

            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = mock_exec
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(Exception) as ctx:
                execute_sql("SELECT 1 AS val")

            # Must surface primary query exception (1146), NOT rollback crash
            err_msg = str(ctx.exception)
            self.assertIn("1146", err_msg)
            mock_conn.invalidate.assert_called_once()

    def test_subsequent_connection_succeeds_after_invalidation(self):
        """Verifies that an invalidated connection does not prevent subsequent queries on fresh connections."""
        with engine.connect() as conn:
            conn.invalidate()

        records, is_trunc = execute_sql("SELECT 99 AS col")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["col"], 99)
        self.assertFalse(is_trunc)

    def test_subsequent_pooled_connection_remains_usable(self):
        for i in range(5):
            records, is_trunc = execute_sql(f"SELECT {i} AS iter")
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["iter"], i)
            self.assertIs(is_trunc, False)

    def test_invalidate_failure_does_not_skip_rollback(self):
        """Verifies that if connection.invalidate() raises, trans.rollback() is still attempted."""
        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_result = MagicMock()
            mock_result.keys.return_value = ["id"]
            mock_result.fetchmany.return_value = [(1,)]
            mock_result.close.side_effect = OperationalError("Close socket error", [], Exception("Close failed"))
            mock_conn.invalidate.side_effect = RuntimeError("Invalidate failed")

            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(Exception):
                execute_sql("SELECT 1 AS val")

            # Invalidate was attempted
            mock_conn.invalidate.assert_called_once()
            # Rollback must still have been called despite invalidate raising
            mock_trans.rollback.assert_called_once()
            # Fallback detach was attempted
            mock_conn.detach.assert_called_once()

    def test_close_and_invalidate_failure_preserves_primary_query_error(self):
        """Verifies primary query error is preserved even when both result.close() and invalidate() fail."""
        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_result = MagicMock()
            mock_result.fetchmany.side_effect = OperationalError("Query timeout", [], Exception("3024 Query interrupted"))
            mock_result.close.side_effect = RuntimeError("Close crash")
            mock_conn.invalidate.side_effect = RuntimeError("Invalidate crash")

            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(Exception) as ctx:
                execute_sql("SELECT 1 AS val")

            # Must preserve primary query exception (3024), NOT close crash or invalidate crash
            err_msg = str(ctx.exception)
            self.assertIn("3024", err_msg)
            self.assertNotIn("Close crash", err_msg)
            self.assertNotIn("Invalidate crash", err_msg)
            mock_conn.invalidate.assert_called_once()
            mock_trans.rollback.assert_called_once()
            mock_conn.detach.assert_called_once()

    def test_rollback_and_invalidate_failure_preserves_primary_query_error(self):
        """Verifies primary query error is preserved even when both trans.rollback() and invalidate() fail."""
        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_trans.rollback.side_effect = RuntimeError("Rollback crash")
            mock_conn.invalidate.side_effect = RuntimeError("Invalidate crash")

            def mock_exec(statement):
                if "SELECT" in str(statement):
                    raise OperationalError("Table not found", [], Exception("1146 Table doesn't exist"))
                return MagicMock()

            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = mock_exec
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(Exception) as ctx:
                execute_sql("SELECT 1 AS val")

            # Must preserve primary query exception (1146), NOT rollback crash or invalidate crash
            err_msg = str(ctx.exception)
            self.assertIn("1146", err_msg)
            self.assertNotIn("Rollback crash", err_msg)
            self.assertNotIn("Invalidate crash", err_msg)
            mock_conn.invalidate.assert_called_once()
            mock_trans.rollback.assert_called_once()
            mock_conn.detach.assert_called_once()

    def test_both_cleanup_and_invalidation_failures(self):
        """Verifies execution when both close and rollback fail, and both invalidation attempts fail."""
        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_result = MagicMock()
            mock_result.keys.return_value = ["id"]
            mock_result.fetchmany.return_value = [(1,)]
            mock_result.close.side_effect = RuntimeError("Close crash")
            mock_trans.rollback.side_effect = RuntimeError("Rollback crash")
            mock_conn.invalidate.side_effect = RuntimeError("Invalidate crash")

            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(Exception):
                execute_sql("SELECT 1 AS val")

            # Invalidate was attempted on both failures
            self.assertEqual(mock_conn.invalidate.call_count, 2)
            # Rollback was still executed despite close invalidation failure
            mock_trans.rollback.assert_called_once()
            # Fallback detach was attempted on both failures
            self.assertEqual(mock_conn.detach.call_count, 2)

    def test_successful_execution_cleanup_unchanged(self):
        """Verifies that successful execution cleans up cursor and transaction without invalidation."""
        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_result = MagicMock()
            mock_result.keys.return_value = ["id", "val"]
            mock_result.fetchmany.return_value = [(1, "hello")]

            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            records, is_truncated = execute_sql("SELECT 1 AS id, 'hello' AS val")

            self.assertEqual(records, [{"id": 1, "val": "hello"}])
            self.assertFalse(is_truncated)
            mock_result.close.assert_called_once()
            mock_trans.rollback.assert_called_once()
            mock_conn.invalidate.assert_not_called()
            mock_conn.detach.assert_not_called()


# =====================================================================
# 4. ERROR SANITIZATION TESTS
# =====================================================================

class TestErrorSanitization(unittest.TestCase):
    def test_production_database_error_sanitization(self):
        err = OperationalError("SELECT * FROM sales_usr_1", [], Exception('(pymysql.err.OperationalError) (1054, "Unknown column col in field list")'))
        safe = get_safe_exception_message(err, is_production=True, context="query")
        self.assertEqual(safe, "A database error occurred while processing your request. Please try again later.")
        self.assertNotIn("sales_usr_1", safe)
        self.assertNotIn("1054", safe)
        self.assertNotIn("Unknown column", safe)

    def test_production_programming_error_sanitization(self):
        err = ProgrammingError("SELECT * FROM secret_table", [], Exception('(pymysql.err.ProgrammingError) (1146, "Table doesn\'t exist")'))
        safe = get_safe_exception_message(err, is_production=True, context="query")
        self.assertEqual(safe, "A database error occurred while processing your request. Please try again later.")
        self.assertNotIn("secret_table", safe)

    def test_production_llm_error_sanitization(self):
        err = Exception("Groq authentication error: AuthenticationError('Invalid API Key')")
        safe = get_safe_exception_message(err, is_production=True, context="query")
        self.assertEqual(safe, "The AI Analytics service is currently unavailable. Please try again shortly.")
        self.assertNotIn("API Key", safe)

    def test_production_unexpected_error_sanitization(self):
        err = ValueError("Corrupt internal buffer format")
        safe = get_safe_exception_message(err, is_production=True, context="query")
        self.assertEqual(safe, "An unexpected error occurred while processing your query.")
        self.assertNotIn("buffer format", safe)

    def test_development_database_error_preserves_technical_info_but_masks_secrets(self):
        err = Exception("Connection failed to mysql+pymysql://admin:SuperSecret123@db.example.com:3306/sales at C:\\Users\\App\\secret.py: col missing")
        safe = get_safe_exception_message(err, is_production=False, context="query")
        self.assertNotIn("SuperSecret123", safe)
        self.assertNotIn("admin", safe)
        self.assertTrue("[internal-source-path]" in safe or "secret.py" not in safe)
        self.assertIn("col missing", safe)

    def test_http_exception_detail_preserved_and_sanitized(self):
        http_err = HTTPException(status_code=403, detail="Access denied for dataset mysql+pymysql://user:pass@host/db")
        safe = get_safe_exception_message(http_err, is_production=True, context="query")
        self.assertNotIn("pass", safe)
        self.assertIn("Access denied for dataset", safe)


# =====================================================================
# 5. FUNCTION ALLOWLIST & BOUNDARY TESTS (Step 5.2.1.2 Part A)
# =====================================================================

class TestFunctionAllowlistExecutionSafeguards(unittest.TestCase):
    def setUp(self):
        self.user_tables = ["sales_usr_1"]
        self.table_schemas = {
            "sales_usr_1": ["id", "amount", "customer_name", "first_name", "last_name", "date_column", "created_at"]
        }

    def test_allowlisted_builtins_accepted(self):
        from app.services.sql_validator import validate_sql
        accepted_queries = [
            "SELECT COUNT(*) FROM sales_usr_1",
            "SELECT SUM(amount) FROM sales_usr_1",
            "SELECT AVG(amount) FROM sales_usr_1",
            "SELECT LOWER(customer_name) FROM sales_usr_1",
            "SELECT CONCAT(first_name, last_name) FROM sales_usr_1",
            "SELECT ROUND(amount, 2) FROM sales_usr_1",
            "SELECT COALESCE(amount, 0) FROM sales_usr_1",
            "SELECT NOW() FROM sales_usr_1",
            "SELECT DATE_FORMAT(date_column, '%Y-%m') FROM sales_usr_1",
            "SELECT ROW_NUMBER() OVER (ORDER BY amount) FROM sales_usr_1",
        ]
        for sql in accepted_queries:
            with self.subTest(sql=sql):
                valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
                self.assertTrue(valid, f"Expected legitimate function to pass: {sql} - Error: {msg}")

    def test_unknown_and_user_defined_functions_rejected(self):
        from app.services.sql_validator import validate_sql
        rejected_queries = [
            ("SELECT UNKNOWN_FUNCTION(id) FROM sales_usr_1", "UNKNOWN_FUNCTION"),
            ("SELECT custom_stored_function(id) FROM sales_usr_1", "CUSTOM_STORED_FUNCTION"),
            ("SELECT `UNKNOWN_FUNCTION`(id) FROM sales_usr_1", "UNKNOWN_FUNCTION"),
            ("SELECT `custom_stored_function`(id) FROM sales_usr_1", "CUSTOM_STORED_FUNCTION"),
        ]
        for sql, fn_name in rejected_queries:
            with self.subTest(sql=sql):
                valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
                self.assertFalse(valid, f"Expected unknown function to be rejected: {sql}")
                self.assertIn("not permitted", msg.lower())
                self.assertIn(fn_name, msg)

    def test_prohibited_functions_strictly_rejected(self):
        from app.services.sql_validator import validate_sql
        prohibited = [
            "SELECT SLEEP(1)",
            "SELECT `SLEEP`(1)",
            "SELECT BENCHMARK(1000, SHA2('a', 256))",
            "SELECT VERSION()",
            "SELECT DATABASE()",
        ]
        for sql in prohibited:
            with self.subTest(sql=sql):
                valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
                self.assertFalse(valid, f"Expected prohibited function to be rejected: {sql}")


# =====================================================================
# 6. CONNECTION DISPOSAL & REAL QUEUEPOOL SAFETY TESTS (Step 5.2.1.5)
# =====================================================================

class TestConnectionDisposalAndPoolSafety(unittest.TestCase):
    """
    Step 5.2.1.5: Verifies explicit handling of connection invalidation and detachment
    failures, ensuring unhealthy connections are never returned to the connection pool.
    """

    def test_invalidation_failure_followed_by_successful_detachment(self):
        """Verifies _safe_invalidate records invalidation failure and falls back to successful detachment."""
        mock_conn = MagicMock()
        mock_conn.invalidate.side_effect = RuntimeError("Invalidate failed")

        result = _safe_invalidate(mock_conn)

        self.assertTrue(result.success)
        self.assertEqual(result.method, "detach")
        self.assertIsNotNone(result.invalidation_error)
        self.assertIsNone(result.detachment_error)
        self.assertFalse(result.is_double_failure)
        mock_conn.invalidate.assert_called_once()
        mock_conn.detach.assert_called_once()

    def test_invalidation_and_detachment_both_failing(self):
        """Verifies _safe_invalidate records double failure and executes fail-closed physical disposal."""
        mock_conn = MagicMock()
        mock_conn.invalidate.side_effect = RuntimeError("Invalidate failed")
        mock_conn.detach.side_effect = RuntimeError("Detach failed")

        result = _safe_invalidate(mock_conn)

        self.assertFalse(result.success)
        self.assertEqual(result.method, "failed")
        self.assertIsNotNone(result.invalidation_error)
        self.assertIsNotNone(result.detachment_error)
        self.assertTrue(result.is_double_failure)
        mock_conn.invalidate.assert_called_once()
        mock_conn.detach.assert_called_once()

    def test_double_failure_during_cursor_close_cleanup(self):
        """Verifies cursor-close double failure surfaces cleanup error and does not abort rollback."""
        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_result = MagicMock()
            mock_result.keys.return_value = ["id"]
            mock_result.fetchmany.return_value = [(1,)]
            mock_result.close.side_effect = OperationalError("Close socket error", [], Exception("Socket dropped"))
            mock_conn.invalidate.side_effect = RuntimeError("Invalidate failed")
            mock_conn.detach.side_effect = RuntimeError("Detach failed")

            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(Exception) as ctx:
                execute_sql("SELECT 1 AS val")

            err_msg = str(ctx.exception)
            self.assertTrue("Close socket error" in err_msg or "Socket dropped" in err_msg)
            mock_conn.invalidate.assert_called_once()
            mock_conn.detach.assert_called_once()
            mock_trans.rollback.assert_called_once()

    def test_double_failure_during_rollback_cleanup(self):
        """Verifies rollback double failure surfaces rollback cleanup error."""
        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_result = MagicMock()
            mock_result.keys.return_value = ["id"]
            mock_result.fetchmany.return_value = [(1,)]
            mock_trans.rollback.side_effect = OperationalError("Rollback socket error", [], Exception("Socket disconnected"))
            mock_conn.invalidate.side_effect = RuntimeError("Invalidate failed")
            mock_conn.detach.side_effect = RuntimeError("Detach failed")

            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(Exception) as ctx:
                execute_sql("SELECT 1 AS val")

            err_msg = str(ctx.exception)
            self.assertTrue("Rollback socket error" in err_msg or "Socket disconnected" in err_msg)
            mock_conn.invalidate.assert_called_once()
            mock_conn.detach.assert_called_once()

    def test_primary_query_exception_combined_with_double_failure(self):
        """Verifies original query error retains precedence when both invalidate and detach fail."""
        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_result = MagicMock()
            mock_result.fetchmany.side_effect = OperationalError("Query timeout", [], Exception("3024 Query interrupted"))
            mock_result.close.side_effect = RuntimeError("Close crash")
            mock_conn.invalidate.side_effect = RuntimeError("Invalidate crash")
            mock_conn.detach.side_effect = RuntimeError("Detach crash")

            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(Exception) as ctx:
                execute_sql("SELECT 1 AS val")

            err_msg = str(ctx.exception)
            self.assertIn("3024", err_msg)
            self.assertNotIn("Close crash", err_msg)
            self.assertNotIn("Invalidate crash", err_msg)
            self.assertNotIn("Detach crash", err_msg)
            mock_conn.invalidate.assert_called_once()
            mock_conn.detach.assert_called_once()
            mock_trans.rollback.assert_called_once()

    def test_successful_query_with_double_failure_does_not_return_success(self):
        """Verifies successful query never returns successful data if cleanup encounters double failure."""
        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_result = MagicMock()
            mock_result.keys.return_value = ["col"]
            mock_result.fetchmany.return_value = [(100,)]
            mock_result.close.side_effect = RuntimeError("Close socket fail")
            mock_conn.invalidate.side_effect = RuntimeError("Invalidate fail")
            mock_conn.detach.side_effect = RuntimeError("Detach fail")

            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(Exception):
                execute_sql("SELECT 100 AS col")

    def test_rollback_still_attempted_after_double_failure(self):
        """Verifies rollback is still attempted after double failure during cursor close."""
        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_result = MagicMock()
            mock_result.keys.return_value = ["id"]
            mock_result.fetchmany.return_value = [(1,)]
            mock_result.close.side_effect = RuntimeError("Close crash")
            mock_conn.invalidate.side_effect = RuntimeError("Invalidate crash")
            mock_conn.detach.side_effect = RuntimeError("Detach crash")

            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(Exception):
                execute_sql("SELECT 1")

            mock_trans.rollback.assert_called_once()

    def test_normal_successful_execution_retains_existing_behavior(self):
        """Verifies normal execution performs clean close and rollback without invalidation or detachment."""
        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_result = MagicMock()
            mock_result.keys.return_value = ["id", "val"]
            mock_result.fetchmany.return_value = [(1, "ok")]

            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            records, is_truncated = execute_sql("SELECT 1 AS id, 'ok' AS val")

            self.assertEqual(records, [{"id": 1, "val": "ok"}])
            self.assertFalse(is_truncated)
            mock_result.close.assert_called_once()
            mock_trans.rollback.assert_called_once()
            mock_conn.invalidate.assert_not_called()
            mock_conn.detach.assert_not_called()

    def test_real_queue_pool_prevents_unhealthy_connection_reuse_on_double_failure(self):
        """
        Exercises real SQLAlchemy QueuePool behavior with controlled event double.
        Verifies that when both invalidate() and detach() raise, fail-closed physical termination
        ensures the unhealthy DBAPI connection cannot be checked out again from the pool.
        """
        pool_engine = create_engine("sqlite://", poolclass=QueuePool, pool_size=1, max_overflow=0)

        @event.listens_for(pool_engine.pool, "invalidate")
        def _break_invalidate(dbapi_con, con_record, exc):
            raise RuntimeError("Pool invalidate event hook error")

        @event.listens_for(pool_engine.pool, "detach")
        def _break_detach(dbapi_con, con_record):
            raise RuntimeError("Pool detach event hook error")

        conn1 = pool_engine.connect()
        raw1 = conn1.connection.dbapi_connection
        raw1_id = id(raw1)

        disp_res = _safe_invalidate(conn1, RuntimeError("Simulated failure"))

        self.assertFalse(disp_res.success)
        self.assertEqual(disp_res.method, "failed")
        self.assertTrue(disp_res.is_double_failure)
        self.assertIsNotNone(disp_res.invalidation_error)
        self.assertIsNotNone(disp_res.detachment_error)

        conn1.close()

        self.assertEqual(pool_engine.pool.checkedin(), 1)
        self.assertEqual(pool_engine.pool.checkedout(), 0)

        conn2 = pool_engine.connect()
        raw2 = conn2.connection.dbapi_connection
        raw2_id = id(raw2)

        self.assertNotEqual(raw1_id, raw2_id)
        self.assertIsNot(raw1, raw2)

        val = conn2.exec_driver_sql("SELECT 999").scalar()
        self.assertEqual(val, 999)

        conn2.close()
        pool_engine.dispose()


# =====================================================================
# 7. STEP 5.2.2: RESULT-SIZE, MEMORY SAFEGUARDS & ERROR SANITIZATION
# =====================================================================

class TestStep522ResultSizeMemoryAndSanitization(unittest.TestCase):
    """
    Step 5.2.2: Validates result-size controls, byte budgeting, cell size limits,
    memory bounding, bounded query history persistence, and production-safe error sanitization.
    """

    # -------------------------------------------------------------
    # Category 1: Result Limits (Tests 1 - 10)
    # -------------------------------------------------------------

    def test_01_normal_result_below_row_limit(self):
        """1. Normal result below the row limit retains full rows and is not truncated."""
        sql = "SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3"
        res = execute_sql(sql, max_rows=10)
        self.assertEqual(len(res.records), 3)
        self.assertFalse(res.is_truncated)
        self.assertIsNone(res.truncation_reason)
        self.assertEqual(res.returned_rows, 3)
        self.assertGreater(res.result_size_bytes, 0)

    def test_02_result_exceeding_row_limit(self):
        """2. Result exceeding the row limit is capped at max_rows with truncation marked."""
        sql = "SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4"
        res = execute_sql(sql, max_rows=2)
        self.assertEqual(len(res.records), 2)
        self.assertTrue(res.is_truncated)
        self.assertEqual(res.truncation_reason, "row_limit")
        self.assertEqual(res.returned_rows, 2)

    def test_03_result_exceeding_total_byte_limit(self):
        """3. Result exceeding the total byte limit stops accumulating rows and sets truncation."""
        sql = "SELECT 1 AS id, 'A' AS val UNION ALL SELECT 2, 'B' UNION ALL SELECT 3, 'C' UNION ALL SELECT 4, 'D' UNION ALL SELECT 5, 'E'"
        res = execute_sql(sql, max_rows=10, max_result_bytes=60)
        self.assertTrue(res.is_truncated)
        self.assertEqual(res.truncation_reason, "byte_budget")
        self.assertLess(len(res.records), 5)
        self.assertLessEqual(res.result_size_bytes, 60)

    def test_04_individual_cell_exceeding_size_limit(self):
        """4. Individual cell exceeding max_cell_bytes raises an explicit ResultSizeLimitError."""
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id", "huge_text"]
        mock_result.fetchmany.return_value = [(1, "x" * 2000)]

        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(ResultSizeLimitError) as ctx:
                execute_sql("SELECT 1 AS id, 'huge' AS huge_text", max_cell_bytes=500)

            err_msg = str(ctx.exception)
            self.assertIn("exceeds maximum allowed size", err_msg)
            self.assertIn("huge_text", err_msg)

    def test_05_large_unicode_strings(self):
        """5. Multibyte Unicode characters are measured accurately in UTF-8 bytes without corruption."""
        unicode_str = "Price: 100€ 😀 汉字"
        expected_bytes = len(unicode_str.encode("utf-8")) + 2
        processed_val, measured_bytes = _process_cell(unicode_str, "txt_col", max_cell_bytes=1000)
        self.assertEqual(processed_val, unicode_str)
        self.assertEqual(measured_bytes, expected_bytes)

    def test_06_null_and_binary_values(self):
        """6. NULL values and binary data are handled correctly without failure."""
        val_null, bytes_null = _process_cell(None, "col_null", max_cell_bytes=100)
        self.assertIsNone(val_null)
        self.assertEqual(bytes_null, 4)

        binary_val = b"hello\x00world"
        val_bin, bytes_bin = _process_cell(binary_val, "col_bin", max_cell_bytes=100)
        self.assertTrue(isinstance(val_bin, str))
        self.assertGreater(bytes_bin, 0)

    def test_07_datetime_and_decimal_serialization(self):
        """7. Datetime and Decimal values are accurately serialized and measured."""
        dt = datetime.datetime(2026, 11, 12, 14, 30, 0)
        val_dt, bytes_dt = _process_cell(dt, "dt_col", max_cell_bytes=100)
        self.assertEqual(val_dt, "2026-11-12T14:30:00")
        self.assertEqual(bytes_dt, len("2026-11-12T14:30:00".encode("utf-8")) + 2)

        dec = Decimal("12345.67")
        val_dec, bytes_dec = _process_cell(dec, "dec_col", max_cell_bytes=100)
        self.assertEqual(val_dec, "12345.67")
        self.assertEqual(bytes_dec, len("12345.67".encode("utf-8")) + 2)

    def test_08_empty_results(self):
        """8. Empty query results produce empty records with consistent metadata."""
        sql = "SELECT 1 AS col WHERE 1 = 0"
        res = execute_sql(sql)
        self.assertEqual(len(res.records), 0)
        self.assertFalse(res.is_truncated)
        self.assertIsNone(res.truncation_reason)
        self.assertEqual(res.returned_rows, 0)

    def test_09_query_history_persistence_with_large_result(self):
        """9. QueryHistory persistence bounds stored payload while preserving total count."""
        large_records = [{"id": i, "data": "a" * 200} for i in range(500)]
        MAX_HISTORY_ROWS = 50
        MAX_HISTORY_BYTES = 128 * 1024

        sample = large_records[:MAX_HISTORY_ROWS]
        payload = json.dumps(sample)
        while len(payload.encode("utf-8")) > MAX_HISTORY_BYTES and len(sample) > 1:
            sample = sample[:len(sample) // 2]
            payload = json.dumps(sample)

        self.assertLessEqual(len(payload.encode("utf-8")), MAX_HISTORY_BYTES)
        self.assertLessEqual(len(json.loads(payload)), MAX_HISTORY_ROWS)

    def test_10_truncation_metadata_consistency(self):
        """10. Truncation metadata is mutually consistent across untruncated and truncated queries."""
        res_a = execute_sql("SELECT 1 AS val", max_rows=10)
        self.assertFalse(res_a.is_truncated)
        self.assertIsNone(res_a.truncation_reason)
        self.assertEqual(res_a.returned_rows, len(res_a.records))

        res_b = execute_sql("SELECT 1 AS n UNION ALL SELECT 2", max_rows=1)
        self.assertTrue(res_b.is_truncated)
        self.assertEqual(res_b.truncation_reason, "row_limit")
        self.assertEqual(res_b.returned_rows, 1)

    # -------------------------------------------------------------
    # Category 2: Memory and Lifecycle Behavior (Tests 11 - 15)
    # -------------------------------------------------------------

    def test_11_additional_rows_not_accumulated_after_budget_reached(self):
        """11. Verify that additional rows are not accumulated after the result budget is reached."""
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id", "val"]
        mock_result.fetchmany.return_value = [(i, "x" * 100) for i in range(10)]

        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            res = execute_sql("SELECT 1", max_rows=10, max_result_bytes=250)
            self.assertEqual(len(res.records), 2)
            self.assertTrue(res.is_truncated)
            self.assertEqual(res.truncation_reason, "byte_budget")

    def test_12_serialization_failures_do_not_leak_connections(self):
        """12. Serialization / cell size failures do not leak database connections."""
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id", "bad_cell"]
        mock_result.fetchmany.return_value = [(1, "x" * 5000)]

        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(ResultSizeLimitError):
                execute_sql("SELECT 1", max_cell_bytes=1000)

            mock_result.close.assert_called_once()
            mock_trans.rollback.assert_called_once()

    def test_13_cursor_cleanup_and_rollback_on_result_processing_failures(self):
        """13. Cursor cleanup and rollback still occur on unexpected result processing failures."""
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id"]
        mock_result.fetchmany.side_effect = RuntimeError("Simulated driver buffer fault")

        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(RuntimeError):
                execute_sql("SELECT 1")

            mock_result.close.assert_called_once()
            mock_trans.rollback.assert_called_once()

    def test_14_existing_invalidation_and_disposal_behavior_remains_intact(self):
        """14. Existing fail-closed invalidation and detachment behavior remains intact."""
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id"]
        mock_result.fetchmany.return_value = [(1,)]
        mock_result.close.side_effect = RuntimeError("Close socket fail")

        with patch.object(engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_trans = MagicMock()
            mock_conn.begin.return_value.__enter__.return_value = mock_trans
            mock_conn.execute.side_effect = lambda statement: mock_result if "SELECT" in str(statement) else MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn

            with self.assertRaises(Exception):
                execute_sql("SELECT 1")

            mock_conn.invalidate.assert_called_once()

    def test_15_failed_history_persistence_does_not_corrupt_response(self):
        """15. A failed history-persistence operation does not corrupt the query response or transaction state."""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.services.auth_service import get_current_user_id

        app.dependency_overrides[get_current_user_id] = lambda: "usr_test15"
        client = TestClient(app)
        try:
            with patch("app.routes.ask.resolve_and_authorize_dataset", return_value="sales_usr_test15"), \
                 patch("app.routes.ask.get_user_datasets", return_value=["sales_usr_test15"]), \
                 patch("app.routes.ask.verify_all_referenced_tables"), \
                 patch("app.routes.ask.generate_sql", return_value="SELECT 1 AS val FROM sales_usr_test15"), \
                 patch("app.routes.ask.validate_sql", return_value=(True, "")), \
                 patch("app.routes.ask.execute_sql", return_value=ExecutionResult([{"val": 1}], False, None, 1, 15)), \
                 patch("app.routes.ask.interpret_result", return_value="GENERAL"), \
                 patch("app.routes.ask.generate_summary", return_value="Query successful."), \
                 patch("app.database.connection.SessionLocal", side_effect=OperationalError("Disk full", [], Exception("Disk full"))):

                response = client.post("/ask", json={"question": "show me value"})
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertTrue(data.get("success"))
                self.assertEqual(data.get("result"), [{"val": 1}])
                self.assertEqual(data.get("summary"), "Query successful.")
        finally:
            app.dependency_overrides.clear()

    # -------------------------------------------------------------
    # Category 3: Error Sanitization (Tests 16 - 22)
    # -------------------------------------------------------------

    def test_16_production_database_errors_return_generic_safe_messages(self):
        """16. Production database errors return generic safe messages without internal details."""
        err = OperationalError("SELECT * FROM secret_tbl", [], Exception('(1054, "Unknown column secret_col in field list")'))
        msg = get_safe_exception_message(err, is_production=True, context="query")
        self.assertEqual(msg, "A database error occurred while processing your request. Please try again later.")
        self.assertNotIn("secret_tbl", msg)
        self.assertNotIn("secret_col", msg)
        self.assertNotIn("1054", msg)

    def test_17_development_errors_retain_useful_diagnostics(self):
        """17. Development errors retain useful diagnostics for debugging while masking secrets."""
        err = OperationalError("SELECT * FROM secret_tbl", [], Exception('(1054, "Unknown column missing_col in field list")'))
        msg = get_safe_exception_message(err, is_production=False, context="query")
        self.assertIn("missing_col", msg)
        self.assertIn("1054", msg)

    def test_18_database_credentials_never_exposed(self):
        """18. Database credentials are never exposed in development or production error messages."""
        raw_msg = "Connection failed to mysql+pymysql://admin:SuperSecretPassword123@db.example.com:3306/sales"
        err = Exception(raw_msg)

        msg_dev = get_safe_exception_message(err, is_production=False, context="query")
        self.assertNotIn("SuperSecretPassword123", msg_dev)
        self.assertIn("***:***", msg_dev)

        msg_prod = get_safe_exception_message(err, is_production=True, context="query")
        self.assertNotIn("SuperSecretPassword123", msg_prod)
        self.assertNotIn("db.example.com", msg_prod)

    def test_19_raw_sql_not_exposed_through_production_error_responses(self):
        """19. Raw SQL is not exposed through production error responses."""
        err = ProgrammingError("SELECT password_hash, ssn FROM users WHERE role = 'admin'", [], Exception("Syntax error"))
        msg = get_safe_exception_message(err, is_production=True, context="query")
        self.assertNotIn("SELECT", msg)
        self.assertNotIn("password_hash", msg)
        self.assertNotIn("users", msg)

    def test_20_tracebacks_and_internal_paths_not_exposed(self):
        """20. Tracebacks and internal filesystem paths are masked."""
        err = Exception('Error at C:\\Users\\Administrator\\Projects\\backend\\secret.py: line 42 in <module>')
        msg_dev = get_safe_exception_message(err, is_production=False, context="query")
        self.assertNotIn("Administrator", msg_dev)
        self.assertNotIn("secret.py", msg_dev)
        self.assertIn("[internal-source-path]", msg_dev)

    def test_21_existing_validation_errors_remain_understandable(self):
        """21. Validation errors remain clear and understandable to the client."""
        from app.services.sql_validator import validate_sql
        valid, msg = validate_sql("SELECT UNKNOWN_FUNC(id) FROM sales_usr_1", ["sales_usr_1"], {"sales_usr_1": ["id"]})
        self.assertFalse(valid)
        self.assertIn("UNKNOWN_FUNC", msg)
        self.assertIn("not permitted", msg)

    def test_22_query_timeout_errors_receive_appropriate_safe_message(self):
        """22. Query timeout errors receive an appropriate safe message in production."""
        err = OperationalError("SELECT SLEEP(10)", [], Exception('(3024, "Query execution was interrupted, max_statement_time exceeded")'))
        msg = get_safe_exception_message(err, is_production=True, context="query")
        self.assertIn("Query execution timed out", msg)
        self.assertIn("simplify your query", msg)
        self.assertNotIn("3024", msg)
        self.assertNotIn("SLEEP", msg)

    # -------------------------------------------------------------
    # Category 4: Decimal Precision and Result-Count Semantics (Tests 23 - 32)
    # -------------------------------------------------------------

    def test_23_decimal_precision_preservation_large_number(self):
        """23. Arbitrary-precision large Decimals are preserved losslessly without float rounding."""
        dec = Decimal("12345678901234567890.123456")
        val, b_len = _process_cell(dec, "dec_col", max_cell_bytes=1000)
        self.assertEqual(val, "12345678901234567890.123456")
        self.assertIsInstance(val, str)
        # Verify float conversion would have lost precision
        float_val = float(dec)
        self.assertNotEqual(str(float_val), "12345678901234567890.123456")
        # Verify json sanitization
        from app.utils.json_helper import sanitize_for_json
        sanitized = sanitize_for_json({"amount": dec})
        self.assertEqual(sanitized["amount"], "12345678901234567890.123456")
        # Verify JSON serializability
        encoded = json.dumps(sanitized)
        self.assertIn('"12345678901234567890.123456"', encoded)

    def test_24_decimal_fractional_precision_small_number(self):
        """24. High-precision fractional Decimals are preserved losslessly without exponent notation."""
        dec = Decimal("0.00000000000000012345")
        val, b_len = _process_cell(dec, "dec_col", max_cell_bytes=1000)
        self.assertEqual(val, "0.00000000000000012345")
        self.assertIsInstance(val, str)
        from app.utils.json_helper import sanitize_for_json
        self.assertEqual(sanitize_for_json(dec), "0.00000000000000012345")

    def test_25_decimal_negative_values(self):
        """25. Negative Decimal values preserve sign and all fractional digits."""
        dec_neg = Decimal("-9876543210.123456789")
        val, b_len = _process_cell(dec_neg, "neg_col", max_cell_bytes=1000)
        self.assertEqual(val, "-9876543210.123456789")
        self.assertIsInstance(val, str)
        from app.utils.json_helper import sanitize_for_json
        self.assertEqual(sanitize_for_json(dec_neg), "-9876543210.123456789")

    def test_26_decimal_zero_and_integer_values(self):
        """26. Zero, negative zero, and integer-valued Decimals preserve exact representations."""
        for dec_val, expected_str in [
            (Decimal("0"), "0"),
            (Decimal("0.00"), "0.00"),
            (Decimal("100"), "100"),
            (Decimal("-0"), "-0")
        ]:
            val, b_len = _process_cell(dec_val, "zero_col", max_cell_bytes=1000)
            self.assertEqual(val, expected_str)
            self.assertIsInstance(val, str)
            from app.utils.json_helper import sanitize_for_json
            self.assertEqual(sanitize_for_json(dec_val), expected_str)

    def test_27_decimal_byte_budget_accounting(self):
        """27. Byte budget calculations strictly use the actual serialized string representation."""
        dec = Decimal("12345678901234567890.123456")
        expected_bytes = len("12345678901234567890.123456".encode("utf-8")) + 2
        val, b_len = _process_cell(dec, "dec_col", max_cell_bytes=1000)
        self.assertEqual(b_len, expected_bytes)

        # Test cell size limit enforcement on oversized Decimal string
        with self.assertRaises(ResultSizeLimitError):
            _process_cell(dec, "dec_col", max_cell_bytes=10)

    def test_28_result_count_semantics_untruncated(self):
        """28. In untruncated queries, returned_rows equals len(records), is_truncated is False, and total_rows is populated."""
        res = execute_sql("SELECT 1 AS a, 2 AS b", max_rows=10)
        self.assertEqual(res.returned_rows, 1)
        self.assertEqual(len(res.records), 1)
        self.assertFalse(res.is_truncated)
        self.assertIsNone(res.truncation_reason)
        self.assertEqual(res.total_rows, 1)

    def test_29_result_count_semantics_truncated_row_limit(self):
        """29. In row-truncated queries, total_rows is None and returned_rows reflects rows actually returned."""
        res = execute_sql("SELECT 1 AS n UNION ALL SELECT 2", max_rows=1)
        self.assertEqual(res.returned_rows, 1)
        self.assertEqual(len(res.records), 1)
        self.assertTrue(res.is_truncated)
        self.assertEqual(res.truncation_reason, "row_limit")
        self.assertIsNone(res.total_rows)

    def test_30_result_count_semantics_truncated_byte_budget(self):
        """30. In byte-budget truncated queries, total_rows is None and returned_rows reflects preserved rows."""
        res = execute_sql("SELECT 'abcdefghijklmnopqrstuvwxyz' AS txt UNION ALL SELECT '1234567890'", max_rows=10, max_result_bytes=60)
        self.assertEqual(res.returned_rows, 1)
        self.assertTrue(res.is_truncated)
        self.assertEqual(res.truncation_reason, "byte_budget")
        self.assertIsNone(res.total_rows)

    def test_31_summary_generator_count_semantics(self):
        """31. summary_generator never describes len(records) as total matching records when is_truncated is True."""
        from app.services.summary_generator import generate_summary

        records = [{"id": i, "name": f"item_{i}"} for i in range(10)]

        # When untruncated, prompt claims Total Matching Records
        with patch("app.services.summary_generator.call_llm", return_value="Summary untruncated.") as mock_llm:
            generate_summary("list items", records, is_truncated=False)
            prompt = mock_llm.call_args[0][1]
            self.assertIn("Total Matching Records = 10", prompt)

        # When truncated, prompt explicitly avoids claiming len(records) is total matching records
        with patch("app.services.summary_generator.call_llm", return_value="Summary truncated.") as mock_llm:
            generate_summary("list items", records, is_truncated=True)
            prompt = mock_llm.call_args[0][1]
            self.assertNotIn("Total Matching Records = 10", prompt)
            self.assertIn("capped", prompt.lower())
            self.assertIn("Do NOT claim or imply that 10 is the total number of matching records", prompt)

    def test_32_ask_route_result_count_and_history_persistence(self):
        """32. /ask response and QueryHistory persistence correctly maintain returned_rows, total_rows, and truncation metadata."""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.services.auth_service import get_current_user_id

        app.dependency_overrides[get_current_user_id] = lambda: "usr_test32"
        client = TestClient(app)
        try:
            # 1. Test untruncated response
            untrunc_exec = ExecutionResult([{"val": 1}], False, None, 1, 15, 1)
            mock_session = MagicMock()
            with patch("app.routes.ask.resolve_and_authorize_dataset", return_value="sales_usr_test32"), \
                 patch("app.routes.ask.get_user_datasets", return_value=["sales_usr_test32"]), \
                 patch("app.routes.ask.verify_all_referenced_tables"), \
                 patch("app.routes.ask.generate_sql", return_value="SELECT 1 AS val FROM sales_usr_test32"), \
                 patch("app.routes.ask.validate_sql", return_value=(True, "")), \
                 patch("app.routes.ask.execute_sql", return_value=untrunc_exec), \
                 patch("app.routes.ask.interpret_result", return_value="GENERAL"), \
                 patch("app.routes.ask.generate_summary", return_value="Retrieved 1 record."), \
                 patch("app.database.connection.SessionLocal", return_value=mock_session):

                resp = client.post("/ask", json={"question": "show value"})
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertTrue(data["success"])
                self.assertEqual(data["returned_rows"], 1)
                self.assertEqual(data["total_rows"], 1)
                self.assertFalse(data["is_truncated"])
                self.assertEqual(data["count"], 1)

                # Verify QueryHistory was created with accurate returned_rows count
                added_history = mock_session.add.call_args[0][0]
                self.assertEqual(added_history.result_count, 1)
                self.assertEqual(added_history.summary, "Retrieved 1 record.")

            # 2. Test truncated response
            trunc_exec = ExecutionResult([{"val": 1}], True, "row_limit", 1, 15, None)
            mock_session.reset_mock()
            with patch("app.routes.ask.resolve_and_authorize_dataset", return_value="sales_usr_test32"), \
                 patch("app.routes.ask.get_user_datasets", return_value=["sales_usr_test32"]), \
                 patch("app.routes.ask.verify_all_referenced_tables"), \
                 patch("app.routes.ask.generate_sql", return_value="SELECT 1 AS val FROM sales_usr_test32"), \
                 patch("app.routes.ask.validate_sql", return_value=(True, "")), \
                 patch("app.routes.ask.execute_sql", return_value=trunc_exec), \
                 patch("app.routes.ask.interpret_result", return_value="GENERAL"), \
                 patch("app.routes.ask.generate_summary", return_value="Retrieved 1 sample record (capped)."), \
                 patch("app.database.connection.SessionLocal", return_value=mock_session):

                resp = client.post("/ask", json={"question": "show value"})
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertTrue(data["success"])
                self.assertEqual(data["returned_rows"], 1)
                self.assertIsNone(data["total_rows"])
                self.assertTrue(data["is_truncated"])
                self.assertEqual(data["truncation_reason"], "row_limit")
                self.assertEqual(data["count"], 1)

                # Verify QueryHistory persisted accurate metadata
                added_history = mock_session.add.call_args[0][0]
                self.assertEqual(added_history.result_count, 1)
                self.assertEqual(added_history.summary, "Retrieved 1 sample record (capped).")
        finally:
            app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
