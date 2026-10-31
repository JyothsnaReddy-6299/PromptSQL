import os
import sys
import unittest
import json
import pandas as pd
from datetime import datetime, timedelta

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.database.connection import Base
import app.database.connection as db_conn
import app.services.metric_service as metric_svc
import app.services.query_planner as planner_svc
from app.models.metric import BusinessMetric
from app.models.clarification import ClarificationSession
from app.services.metric_parser import validate_and_compile_expression
from app.services.metric_service import (
    create_or_update_metric,
    list_metrics,
    get_metric,
    delete_metric,
    resolve_metrics_for_phrase,
    get_authorized_dataset_columns
)
from app.services.query_planner import (
    detect_sales_ambiguity,
    resolve_or_create_plan,
    compile_plan_to_sql,
    PlanCompilationError
)


class TestMetricsAndClarification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Configure a self-contained SQLite test database so tests run reliably in any environment
        cls.test_db_file = os.path.abspath("test_metrics.db")
        cls.test_engine = create_engine(f"sqlite:///{cls.test_db_file}", echo=False)
        cls.TestSessionLocal = sessionmaker(bind=cls.test_engine, autocommit=False, autoflush=False)

        # Monkey-patch database connection for the test runner
        cls.orig_engine = db_conn.engine
        cls.orig_session = db_conn.SessionLocal
        db_conn.engine = cls.test_engine
        db_conn.SessionLocal = cls.TestSessionLocal
        metric_svc.engine = cls.test_engine
        metric_svc.SessionLocal = cls.TestSessionLocal
        planner_svc.engine = cls.test_engine
        planner_svc.SessionLocal = cls.TestSessionLocal

        Base.metadata.create_all(bind=cls.test_engine)

        cls.user_a = "usr_test_user_a"
        cls.user_b = "usr_test_user_b"
        cls.table_a = f"test_sales_{cls.user_a}"
        cls.table_b = f"test_finance_{cls.user_b}"

        # Create table A with revenue and quantity columns
        df_a = pd.DataFrame({
            "id": [1, 2, 3, 4],
            "Product_Category": ["Electronics", "Furniture", "Electronics", "Clothing"],
            "Sales_Region": ["North", "South", "North", "East"],
            "Quantity_Ordered": [10.0, 5.0, 20.0, 15.0],
            "Unit_Price": [100.0, 250.0, 90.0, 50.0],
            "Total_Sales": [1000.0, 1250.0, 1800.0, 750.0]
        })
        df_a.to_sql(cls.table_a, con=cls.test_engine, if_exists="replace", index=False)

        # Create table B for user B
        df_b = pd.DataFrame({
            "id": [1, 2],
            "Account": ["Ops", "Marketing"],
            "Budget": [50000.0, 30000.0]
        })
        df_b.to_sql(cls.table_b, con=cls.test_engine, if_exists="replace", index=False)

    @classmethod
    def tearDownClass(cls):
        # Restore original connections
        db_conn.engine = cls.orig_engine
        db_conn.SessionLocal = cls.orig_session
        metric_svc.engine = cls.orig_engine
        metric_svc.SessionLocal = cls.orig_session
        planner_svc.engine = cls.orig_engine
        planner_svc.SessionLocal = cls.orig_session

        # Dispose and clean up test SQLite file
        cls.test_engine.dispose()
        if os.path.exists(cls.test_db_file):
            try:
                os.remove(cls.test_db_file)
            except Exception:
                pass

    def test_01_highest_sales_requests_clarification(self):
        """
        Acceptance Check 1:
        'Highest sales' requests clarification when both revenue and quantity are plausible.
        """
        result = resolve_or_create_plan("Highest sales by category", self.table_a, self.user_a)
        self.assertTrue(result.get("needs_clarification"), "Should request clarification for ambiguous 'sales'")
        self.assertIn("clarification_id", result)
        self.assertEqual(len(result["options"]), 2)

        # Check options cover both monetary revenue and quantity volume
        option_ids = [opt["id"] for opt in result["options"]]
        self.assertIn("revenue", option_ids)
        self.assertIn("quantity", option_ids)

        # Verify clarification session is saved in database with ownership & expiry
        db = self.TestSessionLocal()
        session = db.query(ClarificationSession).filter(
            ClarificationSession.id == result["clarification_id"]
        ).first()
        db.close()
        self.assertIsNotNone(session)
        self.assertEqual(session.user_id, self.user_a)
        from app.utils.tz_helper import get_ist_time
        self.assertTrue(session.expires_at > get_ist_time() - timedelta(hours=1))

    def test_02_explicit_highest_revenue_uses_approved_definition(self):
        """
        Acceptance Check 2:
        Explicit 'highest revenue' uses the approved revenue definition without asking.
        """
        result = resolve_or_create_plan("Highest revenue by category", self.table_a, self.user_a)
        self.assertFalse(result.get("needs_clarification"), "Explicit revenue must not request clarification")
        plan = result.get("plan")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["metric_name"], "Revenue")
        self.assertEqual(plan["metric_aggregation"], "SUM")
        self.assertIn("Product_Category", plan["grouping_dimensions"])

        # Test deterministic SQL compilation
        cols = get_authorized_dataset_columns(self.table_a, self.user_a)
        sql, _ = compile_plan_to_sql(plan, self.table_a, cols)
        self.assertIn("SELECT `Product_Category`, SUM(`Total_Sales`) AS `Revenue`", sql)
        self.assertIn("GROUP BY `Product_Category`", sql)
        self.assertIn("ORDER BY `Revenue` DESC", sql)

    def test_03_synonyms_and_paraphrases_resolve_consistently(self):
        """
        Acceptance Check 3:
        Synonyms and paraphrases (turnover, monetary sales, volume, units) resolve consistently.
        """
        create_or_update_metric(
            user_id=self.user_a,
            name="Net Turnover",
            source_dataset=self.table_a,
            expression="Total_Sales",
            supported_aggregation="SUM",
            approved_aliases=["turnover", "income", "gross proceeds"]
        )

        matches = resolve_metrics_for_phrase("Show turnover by region", self.user_a, self.table_a)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["name"], "Net Turnover")

        matches2 = resolve_metrics_for_phrase("What is the gross proceeds?", self.user_a, self.table_a)
        self.assertEqual(len(matches2), 1)
        self.assertEqual(matches2[0]["name"], "Net Turnover")

    def test_04_user_cannot_access_other_users_metric_or_dataset(self):
        """
        Acceptance Check 4:
        A user cannot reference another user's metric or dataset.
        """
        metric_a = create_or_update_metric(
            user_id=self.user_a,
            name="Confidential Margin",
            source_dataset=self.table_a,
            expression="Total_Sales * 0.2",
            supported_aggregation="SUM"
        )

        # User B should NOT see User A's metric
        metrics_b = list_metrics(self.user_b)
        metric_b_ids = [m["id"] for m in metrics_b]
        self.assertNotIn(metric_a["id"], metric_b_ids)

        # User B cannot get User A's metric by ID
        metric_fetched_by_b = get_metric(metric_a["id"], self.user_b)
        self.assertIsNone(metric_fetched_by_b)

        # User B cannot delete User A's metric
        deleted = delete_metric(metric_a["id"], self.user_b)
        self.assertFalse(deleted)

        # User A cannot define metric on User B's dataset table
        with self.assertRaises(PermissionError):
            create_or_update_metric(
                user_id=self.user_a,
                name="Illegal Metric",
                source_dataset=self.table_b,
                expression="Budget",
                supported_aggregation="SUM"
            )

    def test_05_invalid_or_injected_expressions_cannot_bypass_authorization(self):
        """
        Acceptance Check 5:
        Invalid or injected model output cannot bypass authorization.
        """
        cols = get_authorized_dataset_columns(self.table_a, self.user_a)

        # Test injection of Python builtins / eval
        with self.assertRaises(ValueError):
            validate_and_compile_expression("__import__('os').system('echo pwned')", cols, "SUM")

        # Test SQL semicolon / multi-statement injection
        with self.assertRaises(ValueError):
            validate_and_compile_expression("Total_Sales; DROP TABLE users; --", cols, "SUM")

        # Test attribute access / dunder traversal
        with self.assertRaises(ValueError):
            validate_and_compile_expression("Total_Sales.__class__.__bases__", cols, "SUM")

        # Test referencing unapproved column
        with self.assertRaises(ValueError):
            validate_and_compile_expression("UnauthorizedColumn * 2", cols, "SUM")

    def test_06_unanswerable_requests_return_useful_explanation(self):
        """
        Acceptance Check 6:
        Unanswerable requests (asking for columns that don't exist in dataset)
        return a clear, actionable explanation.
        """
        cols = get_authorized_dataset_columns(self.table_a, self.user_a)
        invalid_plan = {
            "metric_name": "NonexistentMetric",
            "metric_expression": "NonexistentCol",
            "metric_aggregation": "SUM",
            "grouping_dimensions": ["FakeDim"],
            "filters": []
        }
        with self.assertRaises(Exception) as cm:
            compile_plan_to_sql(invalid_plan, self.table_a, cols)
        self.assertIn("not exist", str(cm.exception).lower())

    def test_07_existing_supported_queries_continue_working(self):
        """
        Acceptance Check 7:
        Existing supported queries continue working.
        """
        with self.test_engine.connect() as conn:
            res = conn.execute(text(f"SELECT Product_Category, SUM(Total_Sales) as total FROM `{self.table_a}` GROUP BY Product_Category"))
            records = [dict(r._mapping) for r in res]
        self.assertTrue(len(records) > 0)
        self.assertIn("Product_Category", records[0])
        self.assertIn("total", records[0])


if __name__ == "__main__":
    unittest.main()
