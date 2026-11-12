"""
Step 5.3: SQLGlot AST-Based Table Name Translation Test Suite

Validates:
1. Basic friendly table translation.
2. Case-insensitive friendly-name resolution.
3. Backtick-quoted identifiers.
4. Existing table aliases.
5. Qualified columns using friendly table names.
6. Column names identical to friendly table names.
7. String literals containing friendly table names.
8. SQL comments containing friendly table names.
9. CTE definitions and references.
10. CTE names shadowing physical table names.
11. Recursive CTEs.
12. Derived tables.
13. Correlated subqueries.
14. Multiple-table joins.
15. Self-joins.
16. Table names containing spaces.
17. Table names containing hyphens.
18. Reserved keyword table names.
19. Schema-qualified references.
20. Cross-tenant physical table references.
21. Unknown table references.
22. Ambiguous friendly-to-physical mappings.
23. Alias collision cases.
24. Malformed SQL.
25. Multiple SQL statements.
26. Translation failure propagation into the regeneration flow.
27. Verification that validated SQL and executed SQL are identical.
28. Verification that friendly SQL remains unchanged in query history and API responses.
"""

import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.services.table_translator import (
    translate_query_tables,
    build_friendly_to_physical_map,
    TableTranslationError,
    MalformedSQLError,
    MultipleStatementsError,
    AmbiguousTableMappingError,
    TranslationSecurityError,
    TranslationTableNotFoundError,
    AliasCollisionError,
)
from app.services.sql_executor import ExecutionResult
from app.main import app
from app.services.auth_service import get_current_user_id


class TestTableTranslator(unittest.TestCase):
    """Unit and Integration Tests for AST-Based Table Name Translation."""

    def setUp(self):
        self.user_id = "usr_test1"
        self.authorized_tables = [
            f"sales_{self.user_id}",
            f"orders_{self.user_id}",
            f"customers_{self.user_id}",
            f"order-items_{self.user_id}",
            f"monthly sales_{self.user_id}",
            f"order_{self.user_id}",
        ]

    # -------------------------------------------------------------
    # 1. Basic Friendly Table Translation
    # -------------------------------------------------------------
    def test_01_basic_friendly_table_translation(self):
        """1. Basic friendly table names are translated to quoted physical tables."""
        sql = "SELECT * FROM sales"
        translated = translate_query_tables(sql, self.authorized_tables, self.user_id)
        self.assertIn(f"`sales_{self.user_id}`", translated)
        self.assertIn("AS `sales`", translated)

    # -------------------------------------------------------------
    # 2. Case-Insensitive Friendly-Name Resolution
    # -------------------------------------------------------------
    def test_02_case_insensitive_resolution(self):
        """2. Friendly table names resolve correctly regardless of case."""
        for variant in ["SELECT * FROM SALES", "SELECT * FROM Sales", "SELECT * FROM sAlEs"]:
            translated = translate_query_tables(variant, self.authorized_tables, self.user_id)
            self.assertIn(f"`sales_{self.user_id}`", translated)

    # -------------------------------------------------------------
    # 3. Backtick-Quoted Identifiers
    # -------------------------------------------------------------
    def test_03_backtick_quoted_identifiers(self):
        """3. Backtick-quoted friendly identifiers resolve without error or duplicate ticks."""
        sql = "SELECT * FROM `sales`"
        translated = translate_query_tables(sql, self.authorized_tables, self.user_id)
        self.assertIn(f"`sales_{self.user_id}`", translated)
        self.assertNotIn("``", translated)

    # -------------------------------------------------------------
    # 4. Existing Table Aliases
    # -------------------------------------------------------------
    def test_04_existing_table_aliases(self):
        """4. Existing table aliases are preserved exactly and not overwritten."""
        sql = "SELECT s.id, s.amount FROM sales AS s"
        translated = translate_query_tables(sql, self.authorized_tables, self.user_id)
        self.assertIn(f"`sales_{self.user_id}` AS s", translated)
        self.assertNotIn("AS `sales`", translated)

    # -------------------------------------------------------------
    # 5. Qualified Columns Using Friendly Table Names
    # -------------------------------------------------------------
    def test_05_qualified_columns_using_friendly_table_names(self):
        """5. Qualified columns like sales.id resolve through the preserved friendly alias."""
        sql = "SELECT sales.id, sales.amount FROM sales WHERE sales.amount > 100"
        translated = translate_query_tables(sql, self.authorized_tables, self.user_id)
        self.assertIn(f"`sales_{self.user_id}` AS `sales`", translated)
        self.assertIn("sales.id", translated)
        self.assertIn("sales.amount", translated)

    # -------------------------------------------------------------
    # 6. Column Names Identical to Friendly Table Names
    # -------------------------------------------------------------
    def test_06_column_names_identical_to_friendly_table_names(self):
        """6. Columns named identically to friendly table names are not mutated."""
        sql = "SELECT sales, amount FROM sales WHERE sales > 50"
        translated = translate_query_tables(sql, self.authorized_tables, self.user_id)
        self.assertIn("SELECT sales, amount", translated)
        self.assertIn(f"FROM `sales_{self.user_id}` AS `sales`", translated)

    # -------------------------------------------------------------
    # 7. String Literals Containing Friendly Table Names
    # -------------------------------------------------------------
    def test_07_string_literals_containing_friendly_table_names(self):
        """7. String literals containing table names are preserved strictly without mutation."""
        sql = "SELECT * FROM sales WHERE category = 'sales' AND note = 'total sales figures'"
        translated = translate_query_tables(sql, self.authorized_tables, self.user_id)
        self.assertIn("category = 'sales'", translated)
        self.assertIn("note = 'total sales figures'", translated)
        self.assertNotIn(f"category = '`sales_{self.user_id}`'", translated)

    # -------------------------------------------------------------
    # 8. SQL Comments Containing Friendly Table Names
    # -------------------------------------------------------------
    def test_08_sql_comments_containing_friendly_table_names(self):
        """8. SQL comments containing table names do not corrupt AST translation."""
        sql = "SELECT * FROM sales /* comment referencing sales */ WHERE id = 1"
        translated = translate_query_tables(sql, self.authorized_tables, self.user_id)
        self.assertIn(f"`sales_{self.user_id}`", translated)

    # -------------------------------------------------------------
    # 9. CTE Definitions and References
    # -------------------------------------------------------------
    def test_09_cte_definitions_and_references(self):
        """9. CTE definitions and outer references are preserved without being mistaken for base tables."""
        sql = "WITH summary AS (SELECT id, amount FROM sales) SELECT * FROM summary"
        translated = translate_query_tables(sql, self.authorized_tables, self.user_id)
        self.assertIn(f"`sales_{self.user_id}`", translated)
        self.assertIn("WITH summary AS", translated)
        self.assertIn("FROM summary", translated)
        self.assertNotIn(f"summary_{self.user_id}", translated)

    # -------------------------------------------------------------
    # 10. CTE Names Shadowing Physical Table Names
    # -------------------------------------------------------------
    def test_10_cte_shadowing_physical_table_names(self):
        """10. When a CTE shadows a base table name, the CTE reference is not translated."""
        sql = "WITH sales AS (SELECT 1 AS val) SELECT * FROM sales"
        translated = translate_query_tables(sql, self.authorized_tables, self.user_id)
        self.assertIn("WITH sales AS", translated)
        self.assertIn("FROM sales", translated)
        self.assertNotIn(f"`sales_{self.user_id}`", translated)

    # -------------------------------------------------------------
    # 11. Recursive CTEs
    # -------------------------------------------------------------
    def test_11_recursive_ctes(self):
        """11. Recursive CTE self-references are identified as CTEs and not translated."""
        sql = """
        WITH RECURSIVE cte_hierarchy AS (
            SELECT id, 1 AS level FROM sales WHERE id = 1
            UNION ALL
            SELECT s.id, h.level + 1 FROM sales s JOIN cte_hierarchy h ON s.id = h.id + 1
        )
        SELECT * FROM cte_hierarchy
        """
        translated = translate_query_tables(sql, self.authorized_tables, self.user_id)
        self.assertIn(f"`sales_{self.user_id}`", translated)
        self.assertIn("FROM cte_hierarchy", translated)
        self.assertNotIn(f"cte_hierarchy_{self.user_id}", translated)

    # -------------------------------------------------------------
    # 12. Derived Tables
    # -------------------------------------------------------------
    def test_12_derived_tables(self):
        """12. Derived tables in FROM/JOIN clauses do not suffer syntax corruption."""
        sql = "SELECT sub.id FROM (SELECT id, amount FROM sales) AS sub"
        translated = translate_query_tables(sql, self.authorized_tables, self.user_id)
        self.assertIn(f"`sales_{self.user_id}`", translated)
        self.assertIn(") AS sub", translated)
        self.assertIn("(SELECT", translated.replace(" ", ""))  # Ensure opening paren is intact

    # -------------------------------------------------------------
    # 13. Correlated Subqueries
    # -------------------------------------------------------------
    def test_13_correlated_subqueries(self):
        """13. Correlated subqueries translate physical tables across all lexical scopes."""
        sql = "SELECT o.id, (SELECT c.name FROM customers c WHERE c.id = o.cust_id) AS cname FROM orders o"
        translated = translate_query_tables(sql, self.authorized_tables, self.user_id)
        self.assertIn(f"`orders_{self.user_id}` AS o", translated)
        self.assertIn(f"`customers_{self.user_id}` AS c", translated)

    # -------------------------------------------------------------
    # 14. Multiple-Table Joins
    # -------------------------------------------------------------
    def test_14_multiple_table_joins(self):
        """14. Multiple-table JOINs correctly translate each individual table reference."""
        sql = "SELECT * FROM orders o JOIN customers c ON o.cust_id = c.id JOIN sales s ON o.sale_id = s.id"
        translated = translate_query_tables(sql, self.authorized_tables, self.user_id)
        self.assertIn(f"`orders_{self.user_id}` AS o", translated)
        self.assertIn(f"`customers_{self.user_id}` AS c", translated)
        self.assertIn(f"`sales_{self.user_id}` AS s", translated)

    # -------------------------------------------------------------
    # 15. Self-Joins
    # -------------------------------------------------------------
    def test_15_self_joins(self):
        """15. Self-joins translate the physical table repeatedly while preserving aliases."""
        sql = "SELECT a.id, b.id FROM sales a JOIN sales b ON a.id = b.parent_id"
        translated = translate_query_tables(sql, self.authorized_tables, self.user_id)
        self.assertIn(f"`sales_{self.user_id}` AS a", translated)
        self.assertIn(f"`sales_{self.user_id}` AS b", translated)

    # -------------------------------------------------------------
    # 16. Table Names Containing Spaces
    # -------------------------------------------------------------
    def test_16_table_names_containing_spaces(self):
        """16. Table names with spaces translate with backtick quotes and preserve syntax."""
        sql = "SELECT * FROM `monthly sales` WHERE amount > 0"
        translated = translate_query_tables(sql, self.authorized_tables, self.user_id)
        self.assertIn(f"`monthly sales_{self.user_id}`", translated)

    # -------------------------------------------------------------
    # 17. Table Names Containing Hyphens
    # -------------------------------------------------------------
    def test_17_table_names_containing_hyphens(self):
        """17. Table names with hyphens do not suffer boundary mangling with overlapping tables."""
        sql = "SELECT * FROM `order-items` WHERE id = 1"
        translated = translate_query_tables(sql, self.authorized_tables, self.user_id)
        self.assertIn(f"`order-items_{self.user_id}`", translated)
        self.assertNotIn(f"`order_{self.user_id}`-items", translated)

    # -------------------------------------------------------------
    # 18. Reserved Keyword Table Names
    # -------------------------------------------------------------
    def test_18_reserved_keyword_table_names(self):
        """18. Table names identical to SQL keywords do not corrupt clauses like ORDER BY."""
        sql = "SELECT * FROM `order` ORDER BY id"
        translated = translate_query_tables(sql, self.authorized_tables, self.user_id)
        self.assertIn(f"`order_{self.user_id}`", translated)
        self.assertIn("ORDER BY id", translated)

    # -------------------------------------------------------------
    # 19. Schema-Qualified References
    # -------------------------------------------------------------
    def test_19_schema_qualified_references_rejected(self):
        """19. Schema-qualified table references are strictly rejected."""
        queries = [
            "SELECT * FROM mydb.sales",
            "SELECT * FROM information_schema.tables",
            "SELECT * FROM mysql.user",
        ]
        for q in queries:
            with self.assertRaises(TranslationSecurityError):
                translate_query_tables(q, self.authorized_tables, self.user_id)

    # -------------------------------------------------------------
    # 20. Cross-Tenant Physical Table References
    # -------------------------------------------------------------
    def test_20_cross_tenant_physical_table_references_rejected(self):
        """20. Direct references to physical tables belonging to other users are rejected."""
        sql = "SELECT * FROM sales_usr_otheruser"
        with self.assertRaises(TranslationTableNotFoundError):
            translate_query_tables(sql, self.authorized_tables, self.user_id)

    # -------------------------------------------------------------
    # 21. Unknown Table References
    # -------------------------------------------------------------
    def test_21_unknown_table_references_rejected(self):
        """21. Unknown table references fail closed and raise TranslationTableNotFoundError."""
        sql = "SELECT * FROM ghost_table"
        with self.assertRaises(TranslationTableNotFoundError):
            translate_query_tables(sql, self.authorized_tables, self.user_id)

    # -------------------------------------------------------------
    # 22. Ambiguous Friendly-to-Physical Mappings
    # -------------------------------------------------------------
    def test_22_ambiguous_friendly_to_physical_mappings(self):
        """22. Colliding physical tables mapping to the same friendly name are rejected."""
        colliding_tables = ["sales_usr_1", "Sales_usr_1"]
        with self.assertRaises(AmbiguousTableMappingError):
            build_friendly_to_physical_map(colliding_tables, "usr_1")

    # -------------------------------------------------------------
    # 23. Alias Collision Cases
    # -------------------------------------------------------------
    def test_23_alias_collision_cases(self):
        """23. Duplicate table aliases in the same query scope are rejected."""
        sql = "SELECT * FROM sales AS s JOIN orders AS s ON s.id = s.id"
        with self.assertRaises(AliasCollisionError):
            translate_query_tables(sql, self.authorized_tables, self.user_id)

    # -------------------------------------------------------------
    # 24. Malformed SQL
    # -------------------------------------------------------------
    def test_24_malformed_sql_rejected(self):
        """24. Syntactically invalid SQL raises MalformedSQLError."""
        sql = "SELECT FROM WHERE"
        with self.assertRaises(MalformedSQLError):
            translate_query_tables(sql, self.authorized_tables, self.user_id)

    # -------------------------------------------------------------
    # 25. Multiple SQL Statements
    # -------------------------------------------------------------
    def test_25_multiple_sql_statements_rejected(self):
        """25. Multiple SQL statements separated by semicolons are rejected."""
        sql = "SELECT * FROM sales; SELECT * FROM orders"
        with self.assertRaises(MultipleStatementsError):
            translate_query_tables(sql, self.authorized_tables, self.user_id)

    # -------------------------------------------------------------
    # 26. Translation Failure Propagation into Regeneration Flow
    # -------------------------------------------------------------
    def test_26_translation_failure_triggers_regeneration(self):
        """26. A translation error in /ask is fed back to regenerate_sql for self-correction."""
        app.dependency_overrides[get_current_user_id] = lambda: self.user_id
        client = TestClient(app)
        try:
            # 1st call generates invalid table, 2nd call generates valid table
            generated_queries = [
                "SELECT * FROM non_existent_table",
                "SELECT * FROM sales"
            ]

            mock_session = MagicMock()
            with patch("app.routes.ask.resolve_and_authorize_dataset", return_value=f"sales_{self.user_id}"), \
                 patch("app.routes.ask.get_user_datasets", return_value=[f"sales_{self.user_id}"]), \
                 patch("app.routes.ask.verify_all_referenced_tables"), \
                 patch("app.routes.ask.generate_sql", return_value=generated_queries[0]), \
                 patch("app.routes.ask.regenerate_sql", return_value=generated_queries[1]) as mock_regen, \
                 patch("app.routes.ask.validate_sql", return_value=(True, "")), \
                 patch("app.routes.ask.execute_sql", return_value=ExecutionResult([{"val": 1}], False, None, 1, 15, 1)), \
                 patch("app.routes.ask.interpret_result", return_value="GENERAL"), \
                 patch("app.routes.ask.generate_summary", return_value="Summary."), \
                 patch("app.database.connection.SessionLocal", return_value=mock_session):

                resp = client.post("/ask", json={"question": "show records"})
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertTrue(data["success"])
                # Verify regenerate_sql was called with the translation error
                mock_regen.assert_called_once()
                err_msg = mock_regen.call_args[0][3]
                self.assertIn("non_existent_table", err_msg)
        finally:
            app.dependency_overrides.clear()

    # -------------------------------------------------------------
    # 27. Verification that Validated and Executed SQL Are Identical
    # -------------------------------------------------------------
    def test_27_validated_and_executed_sql_are_identical(self):
        """27. The SQL string passed to validate_sql is byte-for-byte identical to the executed SQL."""
        app.dependency_overrides[get_current_user_id] = lambda: self.user_id
        client = TestClient(app)
        validated_sql_captured = []
        executed_sql_captured = []

        def mock_validate(sql, user_tables):
            validated_sql_captured.append(sql)
            return True, ""

        def mock_execute(sql):
            executed_sql_captured.append(sql)
            return ExecutionResult([{"id": 1}], False, None, 1, 15, 1)

        try:
            mock_session = MagicMock()
            with patch("app.routes.ask.resolve_and_authorize_dataset", return_value=f"sales_{self.user_id}"), \
                 patch("app.routes.ask.get_user_datasets", return_value=[f"sales_{self.user_id}"]), \
                 patch("app.routes.ask.verify_all_referenced_tables"), \
                 patch("app.routes.ask.generate_sql", return_value="SELECT sales.id FROM sales WHERE sales.id = 1"), \
                 patch("app.routes.ask.validate_sql", side_effect=mock_validate), \
                 patch("app.routes.ask.execute_sql", side_effect=mock_execute), \
                 patch("app.routes.ask.interpret_result", return_value="GENERAL"), \
                 patch("app.routes.ask.generate_summary", return_value="Summary."), \
                 patch("app.database.connection.SessionLocal", return_value=mock_session):

                resp = client.post("/ask", json={"question": "show record 1"})
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(len(validated_sql_captured), 1)
                self.assertEqual(len(executed_sql_captured), 1)
                # Byte-for-byte equality assertion
                self.assertEqual(validated_sql_captured[0], executed_sql_captured[0])
                self.assertIn(f"`sales_{self.user_id}`", executed_sql_captured[0])
        finally:
            app.dependency_overrides.clear()

    # -------------------------------------------------------------
    # 28. Verification that Friendly SQL Remains Unchanged in Output
    # -------------------------------------------------------------
    def test_28_friendly_sql_preserved_in_history_and_api_response(self):
        """28. The original friendly SQL is returned in the API response and stored in QueryHistory."""
        app.dependency_overrides[get_current_user_id] = lambda: self.user_id
        client = TestClient(app)
        try:
            mock_session = MagicMock()
            friendly_input_sql = "SELECT id, amount FROM sales WHERE category = 'books'"
            with patch("app.routes.ask.resolve_and_authorize_dataset", return_value=f"sales_{self.user_id}"), \
                 patch("app.routes.ask.get_user_datasets", return_value=[f"sales_{self.user_id}"]), \
                 patch("app.routes.ask.verify_all_referenced_tables"), \
                 patch("app.routes.ask.generate_sql", return_value=friendly_input_sql), \
                 patch("app.routes.ask.validate_sql", return_value=(True, "")), \
                 patch("app.routes.ask.execute_sql", return_value=ExecutionResult([{"id": 1, "amount": 100}], False, None, 1, 20, 1)), \
                 patch("app.routes.ask.interpret_result", return_value="GENERAL"), \
                 patch("app.routes.ask.generate_summary", return_value="Summary."), \
                 patch("app.database.connection.SessionLocal", return_value=mock_session):

                resp = client.post("/ask", json={"question": "show book sales"})
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertTrue(data["success"])
                # Verify API response has friendly SQL
                self.assertEqual(data["generated_sql"], friendly_input_sql)

                # Verify QueryHistory was persisted with friendly SQL
                added_history = mock_session.add.call_args[0][0]
                self.assertEqual(added_history.generated_sql, friendly_input_sql)
        finally:
            app.dependency_overrides.clear()

    # -------------------------------------------------------------
    # 29. Verification on Real MySQL Server with Qualified Columns
    # -------------------------------------------------------------
    def test_29_actual_mysql_execution_with_table_translation(self):
        """29. An actual MySQL table is queried using translated AST syntax with table qualification."""
        from app.database.connection import engine
        from sqlalchemy import text
        from app.services.sql_executor import execute_sql

        temp_physical = f"test_trans_{self.user_id}"
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{temp_physical}`"))
            conn.execute(text(f"CREATE TABLE `{temp_physical}` (id INT PRIMARY KEY, amount INT)"))
            conn.execute(text(f"INSERT INTO `{temp_physical}` VALUES (1, 500)"))

        try:
            authorized = [temp_physical]
            # Friendly query using table qualification without explicit alias
            friendly_sql = "SELECT test_trans.id, test_trans.amount FROM test_trans WHERE test_trans.id = 1"
            translated = translate_query_tables(friendly_sql, authorized, self.user_id)
            self.assertIn(f"`{temp_physical}` AS `test_trans`", translated)

            res = execute_sql(translated)
            self.assertEqual(len(res.records), 1)
            self.assertEqual(res.records[0]["id"], 1)
            self.assertEqual(res.records[0]["amount"], 500)
        finally:
            with engine.begin() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS `{temp_physical}`"))


if __name__ == "__main__":
    unittest.main()
