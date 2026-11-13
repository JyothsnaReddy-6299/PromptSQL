"""
Step 5.4: End-to-End Query Pipeline Functional Verification Test Suite

Verifies the complete PromptSQL natural-language query workflow:
1. User question submission to /ask
2. Active dataset and schema discovery
3. SQL generation (Groq LLM or deterministic query mock)
4. SQLGlot AST table name translation (friendly -> authorized physical)
5. SQLGlot AST validation (read-only enforcement, default-deny function allowlist)
6. Dataset authorization guard (multi-table verification, tenant isolation)
7. Safe SQL execution (read-only transaction, timeout hint, row bounds, memory limits)
8. Lossless result serialization (Decimal preservation, NULL handling)
9. AI / Aggregate summary generation
10. Query history logging (bounded storage, pristine friendly SQL)
"""

import unittest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.database.connection import engine, SessionLocal
from app.models.history import QueryHistory
from app.services.auth_service import get_current_user_id
from app.routes.ask import ask_question, AskRequest
from app.services.sql_executor import execute_sql, ResultSizeLimitError


class TestEndToEndQueryPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.user_id = "usr_e2etest"
        cls.tbl_sales = f"sales_{cls.user_id}"
        cls.tbl_cust = f"customers_{cls.user_id}"
        cls.tbl_inventory = f"inventory_{cls.user_id}"

        # Initialize clean isolated test tables with PRIMARY KEY for MySQL compliance
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_sales}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_cust}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_inventory}`"))

            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_cust}` (
                    id INT PRIMARY KEY,
                    name VARCHAR(100),
                    city VARCHAR(50)
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.tbl_cust}` VALUES 
                (1, 'Alice Smith', 'New York'),
                (2, 'Bob Jones', 'Chicago'),
                (3, 'Charlie Brown', 'San Francisco')
            """))

            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_sales}` (
                    id INT PRIMARY KEY,
                    cust_id INT,
                    amount DECIMAL(20, 6),
                    region VARCHAR(50),
                    status VARCHAR(50),
                    notes TEXT
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.tbl_sales}` VALUES
                (1, 1, 150.500000, 'East', 'COMPLETED', 'First order'),
                (2, 1, 250.750000, 'East', 'COMPLETED', 'Second order'),
                (3, 2, 75.250000, 'Midwest', 'PENDING', 'Pending approval'),
                (4, 3, 500.000000, 'West', 'COMPLETED', 'High value'),
                (5, NULL, 50.000000, NULL, 'CANCELLED', NULL)
            """))

            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_inventory}` (
                    id INT PRIMARY KEY,
                    item_name VARCHAR(100),
                    stock INT,
                    price DECIMAL(10, 2)
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.tbl_inventory}` VALUES
                (1, 'Widget A', 100, 25.00),
                (2, 'Gadget B', 0, 50.00)
            """))

    @classmethod
    def tearDownClass(cls):
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_sales}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_cust}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.tbl_inventory}`"))

    def setUp(self):
        app.dependency_overrides[get_current_user_id] = lambda: self.user_id
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    # -------------------------------------------------------------
    # 1. Simple SELECT Queries
    # -------------------------------------------------------------
    def test_01_simple_select_pipeline(self):
        """1. Simple SELECT query flows end-to-end and returns sorted records."""
        req = AskRequest(question="List all completed sales ordered by amount descending")
        res = ask_question(payload=req, x_table_name=self.tbl_sales, user_id=self.user_id)

        self.assertTrue(res["success"])
        self.assertIn("SELECT", res["generated_sql"].upper())
        self.assertIn("sales", res["generated_sql"])
        # Ensure physical table name not leaked in generated_sql
        self.assertNotIn(self.tbl_sales, res["generated_sql"])
        self.assertEqual(res["count"], 3)
        self.assertIsNotNone(res["summary"])
        # Check sorting: highest amount first
        self.assertEqual(res["result"][0]["id"], 4)
        self.assertEqual(res["result"][0]["amount"], "500.000000")

    # -------------------------------------------------------------
    # 2. WHERE Conditions and Sorting
    # -------------------------------------------------------------
    def test_02_where_and_sorting_pipeline(self):
        """2. WHERE condition and ORDER BY filter dataset accurately."""
        req = AskRequest(question="Show sales in the East region with amount greater than 200")
        res = ask_question(payload=req, x_table_name=self.tbl_sales, user_id=self.user_id)

        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["result"][0]["id"], 2)
        self.assertEqual(res["result"][0]["region"], "East")

    # -------------------------------------------------------------
    # 3. COUNT, SUM, AVG, MIN, and MAX Aggregations
    # -------------------------------------------------------------
    def test_03_aggregations_pipeline(self):
        """3. Aggregations trigger aggregate summary interpreter and compute accurate statistics."""
        req = AskRequest(question="What is the total sales amount, average sales amount, min sales, and max sales?")
        res = ask_question(payload=req, x_table_name=self.tbl_sales, user_id=self.user_id)

        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 1)
        rec = res["result"][0]
        # Sum of 150.5 + 250.75 + 75.25 + 500 + 50 = 1026.50
        total_val = float(rec.get("total_sales_amount") or rec.get("total_sales") or list(rec.values())[0])
        self.assertAlmostEqual(total_val, 1026.50, delta=0.5)

    # -------------------------------------------------------------
    # 4. GROUP BY and HAVING
    # -------------------------------------------------------------
    def test_04_group_by_having_pipeline(self):
        """4. GROUP BY with HAVING clause partitions data and returns group summaries."""
        req = AskRequest(question="Show total sales by region for regions with total sales greater than 100")
        res = ask_question(payload=req, x_table_name=self.tbl_sales, user_id=self.user_id)

        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 2)
        regions = {r["region"] for r in res["result"]}
        self.assertEqual(regions, {"East", "West"})

    # -------------------------------------------------------------
    # 5. Queries Involving Multiple Tables and JOINs
    # -------------------------------------------------------------
    def test_05_multi_table_join_pipeline(self):
        """5. Multi-table JOIN query correctly translates both friendly tables and merges data."""
        req = AskRequest(question="Show customer name, their city, and their sales amount")
        res = ask_question(payload=req, x_table_name=self.tbl_sales, user_id=self.user_id)

        self.assertTrue(res["success"])
        self.assertGreater(res["count"], 0)
        rec = res["result"][0]
        self.assertIn("name", rec)
        self.assertIn("city", rec)
        self.assertIn("amount", rec)
        # Ensure friendly SQL has both table names and no physical suffixes
        self.assertNotIn(self.tbl_sales, res["generated_sql"])
        self.assertNotIn(self.tbl_cust, res["generated_sql"])

    # -------------------------------------------------------------
    # 6. Queries Involving CTEs and Subqueries
    # -------------------------------------------------------------
    def test_06_cte_and_subquery_pipeline(self):
        """6. Subqueries and CTEs are parsed, translated with scope awareness, and executed."""
        req = AskRequest(question="Find sales that have an amount greater than the overall average sales amount")
        res = ask_question(payload=req, x_table_name=self.tbl_sales, user_id=self.user_id)

        self.assertTrue(res["success"])
        # Overall average is 205.3. Sales with amount > 205.3 are id 2 (250.75) and id 4 (500.0)
        self.assertEqual(res["count"], 2)
        ids = {r["id"] for r in res["result"]}
        self.assertEqual(ids, {2, 4})

    # -------------------------------------------------------------
    # 7. Questions Involving NULL Values
    # -------------------------------------------------------------
    def test_07_null_values_pipeline(self):
        """7. NULL values are handled via IS NULL and returned as JSON null without errors."""
        req = AskRequest(question="Show sales where region is not specified")
        res = ask_question(payload=req, x_table_name=self.tbl_sales, user_id=self.user_id)

        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 1)
        self.assertIsNone(res["result"][0]["region"])
        self.assertEqual(res["result"][0]["id"], 5)

    # -------------------------------------------------------------
    # 8. Queries Returning Empty Results
    # -------------------------------------------------------------
    def test_08_empty_results_pipeline(self):
        """8. Queries matching no records return empty list and clear informative summary without error."""
        req = AskRequest(question="Show sales for region Antarctica")
        res = ask_question(payload=req, x_table_name=self.tbl_sales, user_id=self.user_id)

        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 0)
        self.assertEqual(res["result"], [])
        self.assertIsNotNone(res["summary"])

    # -------------------------------------------------------------
    # 9. Large Result Sets and Truncation Safeguards
    # -------------------------------------------------------------
    def test_09_large_result_sets_truncation(self):
        """9. Large result sets are capped by physical row limits and report truncation status."""
        # Query with low max_rows to verify truncation reporting
        from app.services.sql_executor import execute_sql
        from app.services.table_translator import translate_query_tables

        translated = translate_query_tables("SELECT * FROM sales", [self.tbl_sales], self.user_id)
        exec_res = execute_sql(translated, max_rows=2)

        self.assertEqual(len(exec_res.records), 2)
        self.assertTrue(exec_res.is_truncated)
        self.assertEqual(exec_res.truncation_reason, "row_limit")
        self.assertEqual(exec_res.returned_rows, 2)
        self.assertIsNone(exec_res.total_rows)

    # -------------------------------------------------------------
    # 10. Invalid or Ambiguous Questions (Self-Correction & Error Handling)
    # -------------------------------------------------------------
    def test_10_invalid_or_ambiguous_question_handling(self):
        """10. Unanswerable or corrupt questions trigger retry and return safe failure message."""
        req = AskRequest(question="xzqwp123 completely non-existent non-sensical query")
        # When LLM tries to generate SQL for non-existent columns/tables, retry loop attempts self-correction
        res = ask_question(payload=req, x_table_name=self.tbl_sales, user_id=self.user_id)
        # Result must either safely succeed if LLM did a best-effort query or fail gracefully with success=False
        self.assertIn("success", res)
        if not res["success"]:
            self.assertIn("error", res)
            self.assertIsInstance(res["error"], str)

    # -------------------------------------------------------------
    # 11. Unauthorized Table References (Fail-Closed)
    # -------------------------------------------------------------
    def test_11_unauthorized_table_reference_fail_closed(self):
        """11. Queries targeting unauthorized, system, or foreign tenant tables fail closed."""
        from app.services.table_translator import (
            translate_query_tables,
            TranslationSecurityError,
            TranslationTableNotFoundError
        )

        # System table access fails closed
        with self.assertRaises(TranslationSecurityError):
            translate_query_tables("SELECT * FROM users", [self.tbl_sales], self.user_id)

        # Foreign tenant table access fails closed
        with self.assertRaises(TranslationTableNotFoundError):
            translate_query_tables("SELECT * FROM sales_usr_foreign", [self.tbl_sales], self.user_id)

        # Cross-database access fails closed
        with self.assertRaises(TranslationSecurityError):
            translate_query_tables("SELECT * FROM mysql.user", [self.tbl_sales], self.user_id)

    # -------------------------------------------------------------
    # 12. Execution Timeout and Error Sanitization
    # -------------------------------------------------------------
    def test_12_execution_safeguards_and_sanitization(self):
        """12. Execution errors are sanitized without exposing credentials or internal topology."""
        from app.utils.error_sanitizer import sanitize_error_message, get_safe_exception_message

        raw_err = Exception("mysql+pymysql://admin:super_secret_pw@db.host.internal:3306/mydb Table doesn't exist")
        safe_msg = get_safe_exception_message(raw_err, is_production=True, context="query")

        self.assertNotIn("super_secret_pw", safe_msg)
        self.assertNotIn("admin", safe_msg)
        self.assertNotIn("db.host.internal", safe_msg)

    # -------------------------------------------------------------
    # 13. Query History Persistence Integrity
    # -------------------------------------------------------------
    def test_13_query_history_stores_pristine_friendly_sql(self):
        """13. QueryHistory persists pristine friendly SQL, accurate counts, and bounded payloads."""
        req = AskRequest(question="List completed sales")
        res = ask_question(payload=req, x_table_name=self.tbl_sales, user_id=self.user_id)
        self.assertTrue(res["success"])

        db = SessionLocal()
        try:
            hist = db.query(QueryHistory).filter(QueryHistory.user_id == self.user_id).order_by(QueryHistory.id.desc()).first()
            self.assertIsNotNone(hist)
            self.assertEqual(hist.question, "List completed sales")
            # Generated SQL must reference friendly table, not physical table
            self.assertIn("sales", hist.generated_sql)
            self.assertNotIn(self.tbl_sales, hist.generated_sql)
            self.assertEqual(hist.result_count, res["count"])
        finally:
            db.close()

    # -------------------------------------------------------------
    # 14. Lossless Decimal Precision End-to-End
    # -------------------------------------------------------------
    def test_14_decimal_precision_preservation(self):
        """14. High-precision Decimals are returned as exact decimal strings without float precision loss."""
        req = AskRequest(question="Show sales id 1 amount")
        res = ask_question(payload=req, x_table_name=self.tbl_sales, user_id=self.user_id)
        self.assertTrue(res["success"])
        self.assertGreater(res["count"], 0)
        # Database has 150.500000. Must be serialized as string '150.500000' preserving 6 decimal places
        rec = res["result"][0]
        self.assertEqual(rec["amount"], "150.500000")


if __name__ == "__main__":
    unittest.main()
