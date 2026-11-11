"""
PromptSQL — Step 5.1: SQLGlot AST Read-Query Validation Engine Test Suite

Comprehensive test coverage across:
- Category A: Valid analytical queries (SELECT, WHERE, GROUP BY, HAVING, ORDER BY, JOIN, UNION, CTE, subqueries, aliases, literals)
- Category B: Statement rejections (multi-statement, DML, DDL, admin, procedures, transactions, malformed)
- Category C: Tenant and table authorization (own tables, other tenants, system tables, cross-db, nested scopes, CTE shadowing)
- Category D: Scope-aware column resolution (quoted/unquoted, qualified, aliases, CTE/derived exports, ambiguity, correlated)
- Category E: Prohibited functions and constructs (SLEEP, BENCHMARK, LOAD_FILE, locks, user/version, SELECT INTO, variables)
- Category F: Live/end-to-end compatibility (default database inspector schema resolution)
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.sql_validator import validate_sql


class TestStep51ASTReadValidator(unittest.TestCase):
    def setUp(self):
        # Isolated test schema
        self.user_tables = ["sales_usr_1", "customers_usr_1", "products_usr_1"]
        self.table_schemas = {
            "sales_usr_1": ["id", "cust_id", "prod_id", "amount", "status", "created_at"],
            "customers_usr_1": ["id", "cust_name", "email", "city"],
            "products_usr_1": ["id", "prod_name", "price", "category"]
        }

    # =========================================================================
    # Category A: Valid Analytical Queries
    # =========================================================================

    def test_a01_simple_select(self):
        sql = "SELECT id, amount FROM sales_usr_1"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)
        self.assertEqual(msg, "SQL is valid.")

    def test_a02_select_with_where(self):
        sql = "SELECT id, amount FROM sales_usr_1 WHERE amount > 100 AND status = 'COMPLETED'"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_a03_aggregation_group_by_having(self):
        sql = (
            "SELECT status, COUNT(*) AS order_cnt, SUM(amount) AS total_val "
            "FROM sales_usr_1 "
            "GROUP BY status "
            "HAVING order_cnt > 5"
        )
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_a04_order_by_and_limit(self):
        sql = "SELECT id, amount FROM sales_usr_1 ORDER BY amount DESC, id ASC LIMIT 25"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_a05_valid_joins_across_two_tables(self):
        sql = (
            "SELECT a.id, a.amount, b.cust_name "
            "FROM sales_usr_1 a "
            "JOIN customers_usr_1 b ON a.cust_id = b.id "
            "WHERE b.city = 'New York'"
        )
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_a06_union_and_union_all(self):
        sql_union = "SELECT id, amount FROM sales_usr_1 UNION SELECT id, amount FROM sales_usr_1"
        valid, msg = validate_sql(sql_union, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

        sql_union_all = "SELECT id, amount FROM sales_usr_1 UNION ALL SELECT id, amount FROM sales_usr_1"
        valid, msg = validate_sql(sql_union_all, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_a07_valid_cte(self):
        sql = (
            "WITH high_sales AS ("
            "  SELECT id, cust_id, amount FROM sales_usr_1 WHERE amount > 500"
            ") "
            "SELECT id, amount FROM high_sales"
        )
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_a08_nested_subquery(self):
        sql = (
            "SELECT id, amount FROM sales_usr_1 "
            "WHERE cust_id IN (SELECT id FROM customers_usr_1 WHERE city = 'Boston')"
        )
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_a09_derived_table(self):
        sql = (
            "SELECT dt.cust_id, dt.total_spend "
            "FROM (SELECT cust_id, SUM(amount) AS total_spend FROM sales_usr_1 GROUP BY cust_id) AS dt "
            "WHERE dt.total_spend > 1000"
        )
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_a10_backticked_and_unquoted_identifiers(self):
        sql = "SELECT `id`, amount, `created_at` FROM `sales_usr_1` WHERE `status` = 'pending'"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_a11_table_and_column_aliases(self):
        sql = "SELECT s.id AS transaction_id, s.amount AS gross_revenue FROM sales_usr_1 AS s"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_a12_string_literals_containing_keywords(self):
        sql = (
            "SELECT id, 'DROP TABLE users' AS note, 'DELETE FROM records' AS action "
            "FROM sales_usr_1 "
            "WHERE status = 'UPDATE' OR status = 'ALTER'"
        )
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_a13_standard_analytical_functions(self):
        sql = (
            "SELECT COUNT(DISTINCT cust_id), AVG(amount), MIN(amount), MAX(amount), "
            "COALESCE(amount, 0), ROUND(amount, 2), LOWER(status), UPPER(status), "
            "NOW(), DATE_ADD(created_at, INTERVAL 7 DAY), DATEDIFF(NOW(), created_at) "
            "FROM sales_usr_1"
        )
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    # =========================================================================
    # Category B: Statement Rejection
    # =========================================================================

    def test_b01_multiple_semicolon_statements(self):
        sql = "SELECT 1 FROM sales_usr_1; SELECT 2 FROM sales_usr_1"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)
        self.assertIn("Multiple or chained", msg)

    def test_b02_chained_statement_with_drop(self):
        sql = "SELECT id FROM sales_usr_1; DROP TABLE sales_usr_1;"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)

    def test_b03_insert_statement_rejected(self):
        sql = "INSERT INTO sales_usr_1 (id, amount) VALUES (1, 100)"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)
        self.assertIn("Only read-only SELECT", msg)

    def test_b04_update_statement_rejected(self):
        sql = "UPDATE sales_usr_1 SET amount = 200 WHERE id = 1"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)

    def test_b05_delete_statement_rejected(self):
        sql = "DELETE FROM sales_usr_1 WHERE id = 1"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)

    def test_b06_replace_statement_rejected(self):
        sql = "REPLACE INTO sales_usr_1 (id, amount) VALUES (1, 100)"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)

    def test_b07_ddl_statements_rejected(self):
        for stmt_sql in [
            "DROP TABLE sales_usr_1",
            "ALTER TABLE sales_usr_1 ADD COLUMN extra_col INT",
            "CREATE TABLE temp_tbl (id INT)",
            "TRUNCATE TABLE sales_usr_1",
        ]:
            with self.subTest(sql=stmt_sql):
                valid, msg = validate_sql(stmt_sql, self.user_tables, self.table_schemas)
                self.assertFalse(valid)

    def test_b08_grant_and_revoke_rejected(self):
        for stmt_sql in [
            "GRANT ALL PRIVILEGES ON *.* TO 'user'@'%'",
            "REVOKE ALL PRIVILEGES ON *.* FROM 'user'@'%'"
        ]:
            with self.subTest(sql=stmt_sql):
                valid, msg = validate_sql(stmt_sql, self.user_tables, self.table_schemas)
                self.assertFalse(valid)

    def test_b09_call_and_do_rejected(self):
        for stmt_sql in ["CALL execute_backup()", "DO SLEEP(5)"]:
            with self.subTest(sql=stmt_sql):
                valid, msg = validate_sql(stmt_sql, self.user_tables, self.table_schemas)
                self.assertFalse(valid)

    def test_b10_set_and_transaction_control_rejected(self):
        for stmt_sql in [
            "SET @my_var = 1",
            "START TRANSACTION",
            "COMMIT",
            "ROLLBACK",
        ]:
            with self.subTest(sql=stmt_sql):
                valid, msg = validate_sql(stmt_sql, self.user_tables, self.table_schemas)
                self.assertFalse(valid)

    def test_b11_malformed_and_empty_sql_rejected(self):
        for stmt_sql in ["", "   ", "SELECT * FROM", "SELECT WHERE", ";"]:
            with self.subTest(sql=stmt_sql):
                valid, msg = validate_sql(stmt_sql, self.user_tables, self.table_schemas)
                self.assertFalse(valid)

    # =========================================================================
    # Category C: Tenant and Table Authorization
    # =========================================================================

    def test_c01_own_authorized_table_accepted(self):
        sql = "SELECT id, amount FROM sales_usr_1"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid)

    def test_c02_another_user_table_rejected(self):
        sql = "SELECT id, amount FROM sales_usr_2"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)
        self.assertIn("unauthorized", msg.lower())
        self.assertNotIn("sales_usr_2", msg)

    def test_c03_protected_system_table_rejected(self):
        for sys_tbl in ["users", "user_active_datasets", "query_history", "audit_logs"]:
            with self.subTest(table=sys_tbl):
                sql = f"SELECT * FROM {sys_tbl}"
                valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
                self.assertFalse(valid)
                self.assertIn("unauthorized", msg.lower())

    def test_c04_cross_database_schema_qualification_rejected(self):
        for sql in [
            "SELECT * FROM mysql.user",
            "SELECT * FROM information_schema.tables",
            "SELECT * FROM performance_schema.threads",
            "SELECT * FROM other_db.sales_usr_1"
        ]:
            with self.subTest(sql=sql):
                valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
                self.assertFalse(valid)
                self.assertIn("schema-qualified", msg.lower())

    def test_c05_unauthorized_table_inside_cte_rejected(self):
        sql = "WITH stolen AS (SELECT * FROM orders_usr_99) SELECT * FROM stolen"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)
        self.assertIn("unauthorized", msg.lower())
        self.assertNotIn("orders_usr_99", msg)

    def test_c06_unauthorized_table_inside_nested_subquery_rejected(self):
        sql = "SELECT * FROM (SELECT * FROM orders_usr_99) AS secret"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)
        self.assertIn("unauthorized", msg.lower())
        self.assertNotIn("orders_usr_99", msg)

    def test_c07_unauthorized_table_inside_join_rejected(self):
        sql = "SELECT a.id, b.id FROM sales_usr_1 a JOIN orders_usr_99 b ON a.id = b.id"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)
        self.assertIn("unauthorized", msg.lower())

    def test_c08_cte_alias_sharing_name_with_physical_table(self):
        # A CTE defining its own name should not be falsely treated as unauthorized physical table
        sql = "WITH sales_usr_1 AS (SELECT 1 AS fake_col) SELECT fake_col FROM sales_usr_1"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_c09_nested_ctes_with_shadowed_and_chained_names(self):
        sql = (
            "WITH c1 AS (SELECT id, amount FROM sales_usr_1), "
            "     c2 AS (SELECT id, amount FROM c1 WHERE amount > 100) "
            "SELECT id, amount FROM c2"
        )
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_c10_alias_matching_system_table_rejected(self):
        sql = "SELECT u.id FROM sales_usr_1 AS users"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)
        self.assertIn("unauthorized", msg.lower())

    # =========================================================================
    # Category D: Scope-Aware Column Resolution
    # =========================================================================

    def test_d01_valid_unquoted_columns(self):
        sql = "SELECT id, amount, status FROM sales_usr_1"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_d02_valid_backticked_columns(self):
        sql = "SELECT `id`, `amount`, `status` FROM `sales_usr_1`"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_d03_unknown_unquoted_column_rejected(self):
        sql = "SELECT id, non_existent_column FROM sales_usr_1"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)
        self.assertIn("Unknown column 'non_existent_column'", msg)

    def test_d04_unknown_backticked_column_rejected(self):
        sql = "SELECT `id`, `fake_metric` FROM `sales_usr_1`"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)
        self.assertIn("Unknown column 'fake_metric'", msg)

    def test_d05_qualified_column_with_table_name(self):
        sql = "SELECT sales_usr_1.id, sales_usr_1.amount FROM sales_usr_1"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_d06_column_through_table_alias(self):
        sql = "SELECT s.id, s.amount FROM sales_usr_1 AS s"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_d07_unknown_column_through_table_alias_rejected(self):
        sql = "SELECT s.id, s.not_a_real_col FROM sales_usr_1 AS s"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)
        self.assertIn("not_a_real_col", msg)

    def test_d08_valid_cte_output_column(self):
        sql = "WITH c AS (SELECT id, amount AS total FROM sales_usr_1) SELECT total FROM c"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_d09_unknown_cte_output_column_rejected(self):
        sql = "WITH c AS (SELECT id, amount AS total FROM sales_usr_1) SELECT ghost_col FROM c"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)
        self.assertIn("Unknown column 'ghost_col'", msg)

    def test_d10_valid_derived_table_output_column(self):
        sql = "SELECT sub.total FROM (SELECT amount AS total FROM sales_usr_1) AS sub"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_d11_unknown_derived_table_output_column_rejected(self):
        sql = "SELECT sub.fake_val FROM (SELECT amount AS total FROM sales_usr_1) AS sub"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)
        self.assertIn("fake_val", msg)

    def test_d12_ambiguous_unqualified_column_across_joins_rejected(self):
        # Both sales_usr_1 and customers_usr_1 have an 'id' column
        sql = "SELECT id, cust_name FROM sales_usr_1 a JOIN customers_usr_1 b ON a.cust_id = b.id"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)
        self.assertIn("Ambiguous column 'id'", msg)

    def test_d13_disambiguated_qualified_columns_across_joins_accepted(self):
        sql = "SELECT a.id, b.id, b.cust_name FROM sales_usr_1 a JOIN customers_usr_1 b ON a.cust_id = b.id"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_d14_correlated_subquery_column_resolution(self):
        sql = (
            "SELECT a.id, "
            "       (SELECT c.cust_name FROM customers_usr_1 c WHERE c.id = a.cust_id) AS cname "
            "FROM sales_usr_1 a"
        )
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_d15_aliases_in_having_order_by_group_by_contexts(self):
        sql = (
            "SELECT status, COUNT(*) AS order_cnt "
            "FROM sales_usr_1 "
            "GROUP BY status "
            "HAVING order_cnt > 5 "
            "ORDER BY order_cnt DESC"
        )
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    def test_d16_case_insensitive_matching(self):
        sql = "SELECT ID, Amount, STATUS FROM SALES_USR_1 WHERE AMOUNT > 10"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertTrue(valid, msg)

    # =========================================================================
    # Category E: Dangerous Functions and Constructs
    # =========================================================================

    def test_e01_sleep_rejected(self):
        for sql in [
            "SELECT SLEEP(5) FROM sales_usr_1",
            "SELECT id FROM sales_usr_1 WHERE SLEEP(1) = 0",
            "SELECT id FROM sales_usr_1 ORDER BY SLEEP(1)"
        ]:
            with self.subTest(sql=sql):
                valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
                self.assertFalse(valid)
                self.assertIn("SLEEP", msg)

    def test_e02_benchmark_rejected(self):
        sql = "SELECT BENCHMARK(1000000, MD5(1)) FROM sales_usr_1"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)
        self.assertIn("BENCHMARK", msg)

    def test_e03_load_file_rejected(self):
        sql = "SELECT LOAD_FILE('/etc/passwd') FROM sales_usr_1"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)
        self.assertIn("LOAD_FILE", msg)

    def test_e04_get_lock_and_release_lock_rejected(self):
        for sql, fn in [
            ("SELECT GET_LOCK('my_lock', 10) FROM sales_usr_1", "GET_LOCK"),
            ("SELECT RELEASE_LOCK('my_lock') FROM sales_usr_1", "RELEASE_LOCK"),
            ("SELECT IS_FREE_LOCK('my_lock') FROM sales_usr_1", "IS_FREE_LOCK")
        ]:
            with self.subTest(fn=fn):
                valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
                self.assertFalse(valid)
                self.assertIn(fn, msg)

    def test_e05_user_and_version_functions_rejected(self):
        for sql, fn in [
            ("SELECT USER() FROM sales_usr_1", "USER"),
            ("SELECT CURRENT_USER() FROM sales_usr_1", "CURRENT_USER"),
            ("SELECT SESSION_USER() FROM sales_usr_1", "SESSION_USER"),
            ("SELECT SYSTEM_USER() FROM sales_usr_1", "SYSTEM_USER"),
            ("SELECT VERSION() FROM sales_usr_1", "VERSION"),
        ]:
            with self.subTest(fn=fn):
                valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
                self.assertFalse(valid)

    def test_e06_database_and_schema_functions_rejected(self):
        for sql in [
            "SELECT DATABASE() FROM sales_usr_1",
            "SELECT SCHEMA() FROM sales_usr_1",
        ]:
            with self.subTest(sql=sql):
                valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
                self.assertFalse(valid)

    def test_e07_select_into_outfile_and_dumpfile_rejected(self):
        for sql in [
            "SELECT * FROM sales_usr_1 INTO OUTFILE '/tmp/leak.txt'",
            "SELECT * FROM sales_usr_1 INTO DUMPFILE '/tmp/leak.bin'",
        ]:
            with self.subTest(sql=sql):
                valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
                self.assertFalse(valid)
                self.assertIn("SELECT INTO", msg)

    def test_e08_user_and_session_variables_rejected(self):
        for sql in [
            "SELECT @user_var FROM sales_usr_1",
            "SELECT @@version FROM sales_usr_1",
            "SELECT @@hostname FROM sales_usr_1",
        ]:
            with self.subTest(sql=sql):
                valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
                self.assertFalse(valid)
                self.assertIn("variables are not permitted", msg)

    def test_e09_nested_prohibited_function_rejected(self):
        sql = "SELECT id FROM sales_usr_1 WHERE amount = (SELECT CASE WHEN 1=1 THEN SLEEP(1) ELSE 0 END)"
        valid, msg = validate_sql(sql, self.user_tables, self.table_schemas)
        self.assertFalse(valid)
        self.assertIn("SLEEP", msg)

    # =========================================================================
    # Category F: Live / Compatibility Mode (Database Inspector)
    # =========================================================================

    @patch("app.services.sql_validator.inspect")
    def test_f01_inspect_called_when_table_schemas_omitted(self, mock_inspect):
        mock_inspector = MagicMock()
        mock_inspect.return_value = mock_inspector
        mock_inspector.get_columns.side_effect = lambda tbl: [
            {"name": "id"},
            {"name": "amount"},
            {"name": "status"},
        ]

        # Call with 2 arguments only (legacy signature compatibility)
        sql = "SELECT id, amount FROM sales_usr_1 WHERE status = 'OK'"
        valid, msg = validate_sql(sql, ["sales_usr_1"])
        self.assertTrue(valid, msg)
        mock_inspector.get_columns.assert_called_with("sales_usr_1")


if __name__ == "__main__":
    unittest.main()
