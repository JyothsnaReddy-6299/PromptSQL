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
import app.routes.metrics as metrics_route
from app.models.metric import BusinessMetric
from app.models.clarification import ClarificationSession
from app.models.history import QueryHistory
from app.utils.tz_helper import get_ist_time
from app.services.metric_parser import validate_and_compile_expression
from app.services.metric_service import (
    create_or_update_metric,
    list_metrics,
    get_metric,
    delete_metric,
    resolve_metrics_for_phrase,
    get_authorized_dataset_columns,
    set_default_metric,
    reset_default_metric,
    get_default_metric
)
from app.services.query_planner import (
    detect_sales_ambiguity,
    resolve_or_create_plan,
    compile_plan_to_sql,
    refine_and_execute_plan,
    PlanCompilationError,
    UnsupportedMetricError
)
from app.services.aggregate_summary import generate_aggregate_summary, format_value


class TestMetricsAndClarificationAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Configure self-contained SQLite test database
        cls.test_db_file = os.path.abspath("test_metrics_suite.db")
        cls.test_engine = create_engine(f"sqlite:///{cls.test_db_file}", echo=False)
        cls.TestSessionLocal = sessionmaker(bind=cls.test_engine, autocommit=False, autoflush=False)

        # Monkey-patch database connection for test runs
        cls.orig_engine = db_conn.engine
        cls.orig_session = db_conn.SessionLocal
        db_conn.engine = cls.test_engine
        db_conn.SessionLocal = cls.TestSessionLocal
        metric_svc.engine = cls.test_engine
        metric_svc.SessionLocal = cls.TestSessionLocal
        planner_svc.engine = cls.test_engine
        planner_svc.SessionLocal = cls.TestSessionLocal
        metrics_route.engine = cls.test_engine
        metrics_route.SessionLocal = cls.TestSessionLocal

        Base.metadata.create_all(bind=cls.test_engine)

        cls.user_a = "usr_alice_1"
        cls.user_b = "usr_bob_2"
        cls.table_a = f"ecommerce_sales_dataset_{cls.user_a}"
        cls.table_b = f"finance_dataset_{cls.user_b}"

        # Synthetic fixture with spaced column names, dates, statuses, and differing revenue vs units leaders:
        # Completed 2023 orders:
        # - North: Rev 1000.0, Qty 10.0
        # - South: Rev 1250.0, Qty 5.0   -> REVENUE LEADER
        # - East:  Rev 800.0,  Qty 20.0  -> UNITS LEADER (completed)
        # All orders:
        # - West:  Rev 500.0,  Qty 50.0  (cancelled in 2023) -> OVERALL UNITS LEADER
        # - North: Rev 200.0,  Qty 4.0   (completed in 2022)
        df_a = pd.DataFrame({
            "id": [1, 2, 3, 4, 5, 6],
            "Order ID": ["ORD-101", "ORD-102", "ORD-103", "ORD-104", "ORD-105", "ORD-106"],
            "Order Date": ["2023-03-15", "2023-05-20", "2023-07-10", "2023-09-05", "2022-11-12", "2023-12-01"],
            "Sales Region": ["North", "South", "East", "West", "North", "Central"],
            "Order Status": ["completed", "completed", "completed", "cancelled", "completed", "completed"],
            "Unit Price": [100.0, 250.0, 40.0, 10.0, 50.0, 0.0],
            "Quantity Ordered": [10.0, 5.0, 20.0, 50.0, 4.0, 0.0],
            "Total Sales Amount": [1000.0, 1250.0, 800.0, 500.0, 200.0, 0.0]
        })
        df_a.to_sql(cls.table_a, con=cls.test_engine, if_exists="replace", index=False)

        # Table for User B
        df_b = pd.DataFrame({
            "id": [1],
            "Account": ["Marketing"],
            "Budget": [50000.0]
        })
        df_b.to_sql(cls.table_b, con=cls.test_engine, if_exists="replace", index=False)

    @classmethod
    def tearDownClass(cls):
        db_conn.engine = cls.orig_engine
        db_conn.SessionLocal = cls.orig_session
        metric_svc.engine = cls.orig_engine
        metric_svc.SessionLocal = cls.orig_session
        planner_svc.engine = cls.orig_engine
        planner_svc.SessionLocal = cls.orig_session
        metrics_route.engine = cls.orig_engine
        metrics_route.SessionLocal = cls.orig_session

        cls.test_engine.dispose()
        if os.path.exists(cls.test_db_file):
            try:
                os.remove(cls.test_db_file)
            except Exception:
                pass

    # =========================================================================
    # Acceptance Check 1:
    # "Which region has the highest sales?" requests clarification.
    # Revenue selection returns the correct revenue-leading region and its total.
    # Units selection returns the correct units-leading region and its quantity.
    # =========================================================================
    def test_01_highest_sales_clarification_and_resolution(self):
        result = resolve_or_create_plan("Which region has the highest sales?", self.table_a, self.user_a)
        self.assertTrue(result.get("needs_clarification"), "Must request clarification when sales is ambiguous")
        clar_id = result["clarification_id"]
        options = {opt["id"]: opt for opt in result["options"]}
        self.assertIn("revenue", options)
        self.assertIn("quantity", options)

        cols = get_authorized_dataset_columns(self.table_a, self.user_a)

        # 1. Resolve with Revenue
        plan_rev = resolve_or_create_plan(
            "Which region has the highest sales?",
            self.table_a,
            self.user_a,
            override_metric=options["revenue"]
        )["plan"]
        sql_rev, params_rev = compile_plan_to_sql(plan_rev, self.table_a, cols)

        with self.test_engine.connect() as conn:
            rows_rev = [dict(r._mapping) for r in conn.execute(text(sql_rev), params_rev)]

        self.assertEqual(len(rows_rev), 1)
        # Revenue leader is South ($1,250.00)
        self.assertEqual(rows_rev[0]["Sales Region"], "South")
        self.assertEqual(rows_rev[0]["Revenue"], 1250.0)
        self.assertIn("Revenue", rows_rev[0], "Result column must be named 'Revenue', not generic 'Metric'")

        # 2. Resolve with Quantity (Units)
        plan_qty = resolve_or_create_plan(
            "Which region has the highest sales?",
            self.table_a,
            self.user_a,
            override_metric=options["quantity"]
        )["plan"]
        sql_qty, params_qty = compile_plan_to_sql(plan_qty, self.table_a, cols)

        with self.test_engine.connect() as conn:
            rows_qty = [dict(r._mapping) for r in conn.execute(text(sql_qty), params_qty)]

        self.assertEqual(len(rows_qty), 1)
        # Overall Units leader across all orders is West (50 units)
        self.assertEqual(rows_qty[0]["Sales Region"], "West")
        self.assertEqual(rows_qty[0]["Units_Sold"], 50.0)

    # =========================================================================
    # Acceptance Check 2:
    # "Revenue by Sales Region" returns one row per region and independently verified totals.
    # GROUP BY does not accidentally include the underlying sales amount.
    # =========================================================================
    def test_02_revenue_by_sales_region_separation(self):
        # Save approved Revenue definition
        create_or_update_metric(
            user_id=self.user_a,
            name="Revenue",
            source_dataset=self.table_a,
            expression="Total Sales Amount",
            supported_aggregation="SUM",
            currency_unit="USD"
        )

        plan = resolve_or_create_plan("Revenue by Sales Region", self.table_a, self.user_a)["plan"]
        self.assertEqual(plan["grouping_dimensions"], ["Sales Region"])
        self.assertNotIn("Total Sales Amount", plan["grouping_dimensions"], "Measure column must not be in dimensions")

        cols = get_authorized_dataset_columns(self.table_a, self.user_a)
        sql, params = compile_plan_to_sql(plan, self.table_a, cols)

        self.assertIn("GROUP BY `Sales Region`", sql)
        self.assertNotIn("GROUP BY `Sales Region`, `Total Sales Amount`", sql)

        with self.test_engine.connect() as conn:
            records = [dict(r._mapping) for r in conn.execute(text(sql), params)]

        # Exactly 5 regions: North, South, East, West, Central
        self.assertEqual(len(records), 5, "Must return exactly 1 row per distinct region")
        rec_map = {r["Sales Region"]: r["Revenue"] for r in records}
        # Verified totals: North = 1000 + 200 = 1200; South = 1250; East = 800; West = 500; Central = 0
        self.assertEqual(rec_map["North"], 1200.0)
        self.assertEqual(rec_map["South"], 1250.0)
        self.assertEqual(rec_map["East"], 800.0)
        self.assertEqual(rec_map["West"], 500.0)
        self.assertEqual(rec_map["Central"], 0.0)

    # =========================================================================
    # Acceptance Check 3:
    # "What is total revenue?" uses the saved Revenue definition without inventing "Total Revenue".
    # Matches the metric preview's underlying calculation.
    # =========================================================================
    def test_03_total_revenue_saved_definition(self):
        plan = resolve_or_create_plan("What is total revenue?", self.table_a, self.user_a)["plan"]
        self.assertEqual(plan["metric_name"], "Revenue")
        self.assertEqual(plan["metric_expression"], "Total Sales Amount")
        self.assertEqual(plan["grouping_dimensions"], [])

        cols = get_authorized_dataset_columns(self.table_a, self.user_a)
        sql, params = compile_plan_to_sql(plan, self.table_a, cols)

        with self.test_engine.connect() as conn:
            records = [dict(r._mapping) for r in conn.execute(text(sql), params)]

        total_rev = records[0]["Revenue"]
        # Total sum of all rows = 1000 + 1250 + 800 + 500 + 200 = 3750.0
        self.assertEqual(total_rev, 3750.0)

        # Test preview calculation matches exactly
        compiled_test, _ = validate_and_compile_expression("Total Sales Amount", cols, "SUM")
        with self.test_engine.connect() as conn:
            preview_val = conn.execute(text(f"SELECT {compiled_test} AS preview FROM `{self.table_a}`")).scalar()
        self.assertEqual(total_rev, preview_val)

    # =========================================================================
    # Acceptance Check 4:
    # "Which region has the lowest sales for completed orders in 2023?"
    # Clarification preserves the status filter, date range, grouping, ascending sort and limit.
    # =========================================================================
    def test_04_lowest_sales_completed_orders_in_2023(self):
        res = resolve_or_create_plan(
            "Which region has the lowest sales for completed orders in 2023?",
            self.table_a,
            self.user_a
        )
        self.assertTrue(res.get("needs_clarification"))
        clar_id = res["clarification_id"]

        # Check server-stored clarification session preserves all plan constraints
        db = self.TestSessionLocal()
        session = db.query(ClarificationSession).filter(ClarificationSession.id == clar_id).first()
        db.close()
        self.assertIsNotNone(session)

        stored_plan = json.loads(session.proposed_plan_json)
        self.assertEqual(stored_plan["grouping_dimensions"], ["Sales Region"])
        self.assertEqual(stored_plan["ordering"]["direction"], "ASC")
        self.assertEqual(stored_plan["limit"], 1)
        self.assertTrue(any(f["column"] == "Order Status" and f["value"] == "completed" for f in stored_plan["filters"]))
        self.assertEqual(stored_plan["date_range"]["year"], 2023)

        # Resolve clarification using Revenue option
        options = {opt["id"]: opt for opt in res["options"]}
        resolved_plan = resolve_or_create_plan(
            "Which region has the lowest sales for completed orders in 2023?",
            self.table_a,
            self.user_a,
            override_metric=options["revenue"]
        )["plan"]

        cols = get_authorized_dataset_columns(self.table_a, self.user_a)
        sql, params = compile_plan_to_sql(resolved_plan, self.table_a, cols)

        self.assertIn("ORDER BY `Revenue` ASC", sql)
        self.assertIn("LIMIT 1", sql)

        # For SQLite test compatibility, convert YEAR(col) to strftime('%Y', col) if needed
        exec_sql = sql.replace("YEAR(`Order Date`)", "CAST(strftime('%Y', `Order Date`) AS INTEGER)")
        with self.test_engine.connect() as conn:
            rows = [dict(r._mapping) for r in conn.execute(text(exec_sql), params)]

        self.assertEqual(len(rows), 1)
        # In completed 2023 orders (Central has 0, East has 800, North has 1000, South has 1250)
        # Central has 0.0
        self.assertEqual(rows[0]["Sales Region"], "Central")
        self.assertEqual(rows[0]["Revenue"], 0.0)

    # =========================================================================
    # Acceptance Check 5:
    # Supported paraphrases resolve consistently. Conflicting aliases request clarification.
    # =========================================================================
    def test_05_paraphrases_and_conflicting_aliases(self):
        # 1. Consistent paraphrases
        create_or_update_metric(
            user_id=self.user_a,
            name="Gross Turnover",
            source_dataset=self.table_a,
            expression="Total Sales Amount",
            supported_aggregation="SUM",
            approved_aliases=["turnover", "proceeds", "income"]
        )

        p1 = resolve_metrics_for_phrase("Show turnover by region", self.user_a, self.table_a)
        self.assertEqual(p1[0]["name"], "Gross Turnover")

        p2 = resolve_metrics_for_phrase("What are the proceeds?", self.user_a, self.table_a)
        self.assertEqual(p2[0]["name"], "Gross Turnover")

        # 2. Conflicting aliases detection
        create_or_update_metric(
            user_id=self.user_a,
            name="Operating Margin",
            source_dataset=self.table_a,
            expression="Total Sales Amount * 0.15",
            supported_aggregation="SUM",
            approved_aliases=["proceeds"]  # Conflict on "proceeds"
        )

        res = resolve_or_create_plan("Show proceeds by region", self.table_a, self.user_a)
        self.assertTrue(res.get("needs_clarification"), "Conflicting aliases across distinct metrics must trigger clarification")
        self.assertEqual(len(res["options"]), 2)

    # =========================================================================
    # Acceptance Check 6:
    # Spaced-column arithmetic works. Test both previously failing forms and column-picker representation.
    # =========================================================================
    def test_06_spaced_column_arithmetic(self):
        cols = get_authorized_dataset_columns(self.table_a, self.user_a)

        # Form 1: Unquoted spaced column names
        sql1, ref1 = validate_and_compile_expression("Unit Price * Quantity Ordered", cols, "SUM")
        self.assertEqual(sql1, "SUM(`Unit Price` * `Quantity Ordered`)")
        self.assertIn("Unit Price", ref1)
        self.assertIn("Quantity Ordered", ref1)

        # Form 2: Backticked spaced column names
        sql2, ref2 = validate_and_compile_expression("`Unit Price` * `Quantity Ordered`", cols, "SUM")
        self.assertEqual(sql2, "SUM(`Unit Price` * `Quantity Ordered`)")

        # Form 3: Bracketed column names (from column picker)
        sql3, ref3 = validate_and_compile_expression("[Unit Price] * [Quantity Ordered]", cols, "SUM")
        self.assertEqual(sql3, "SUM(`Unit Price` * `Quantity Ordered`)")

        # Test execution in database
        with self.test_engine.connect() as conn:
            val = conn.execute(text(f"SELECT {sql1} FROM `{self.table_a}`")).scalar()
        self.assertEqual(val, 3750.0)

    # =========================================================================
    # Acceptance Check 7:
    # Unknown columns and unsupported expression constructs are rejected safely.
    # Unsupported profit questions return clear explanation without substituting revenue.
    # =========================================================================
    def test_07_security_and_unsupported_metrics_rejected(self):
        cols = get_authorized_dataset_columns(self.table_a, self.user_a)

        # Unknown column
        with self.assertRaises(ValueError) as cm:
            validate_and_compile_expression("UnknownColumn * 10", cols)
        self.assertIn("does not exist in dataset schema", str(cm.exception))

        # Statement separator / injection
        with self.assertRaises(ValueError) as cm2:
            validate_and_compile_expression("Total Sales Amount; DROP TABLE users;", cols)
        self.assertIn("invalid characters", str(cm2.exception).lower())

        # Profit question without cost columns or profit metric
        with self.assertRaises(UnsupportedMetricError) as cm3:
            resolve_or_create_plan("What is the profit by region?", self.table_a, self.user_a)
        self.assertIn("profit cannot be calculated", str(cm3.exception).lower())

    # =========================================================================
    # Acceptance Check 8:
    # Metric defaults persist across refresh, can be reset, and do not override explicit requests.
    # =========================================================================
    def test_08_metric_defaults_management(self):
        # 1. Create metric and set as default for 'sales'
        m = create_or_update_metric(
            user_id=self.user_a,
            name="Official Revenue",
            source_dataset=self.table_a,
            expression="Total Sales Amount",
            supported_aggregation="SUM",
            is_default=True,
            default_concept="sales"
        )

        def_m = get_default_metric(self.user_a, self.table_a, concept="sales")
        self.assertIsNotNone(def_m)
        self.assertEqual(def_m["name"], "Official Revenue")

        # Ambiguous question should now use default WITHOUT requiring clarification
        plan_res = resolve_or_create_plan("Highest sales by region", self.table_a, self.user_a)
        self.assertFalse(plan_res.get("needs_clarification"), "Default metric must resolve without clarification")
        self.assertEqual(plan_res["plan"]["metric_name"], "Official Revenue")

        # Explicit request overrides default
        plan_explicit = resolve_or_create_plan("Highest quantity by region", self.table_a, self.user_a)
        self.assertEqual(plan_explicit["plan"]["metric_name"], "Units Sold")

        # Reset default
        reset_default_metric(self.user_a, self.table_a, concept="sales")
        self.assertIsNone(get_default_metric(self.user_a, self.table_a, concept="sales"))

    # =========================================================================
    # Acceptance Check 9:
    # Expired/stale clarification responses fail clearly. Two pending questions remain independent.
    # =========================================================================
    def test_09_clarification_expiry_and_independence(self):
        # Create two distinct clarification sessions
        res1 = resolve_or_create_plan("Which region has the highest sales?", self.table_a, self.user_a)
        res2 = resolve_or_create_plan("Which region has the lowest sales?", self.table_a, self.user_a)

        clar1 = res1["clarification_id"]
        clar2 = res2["clarification_id"]
        self.assertNotEqual(clar1, clar2, "Two pending questions must have distinct sessions")

        # Test expired session
        db = self.TestSessionLocal()
        s1 = db.query(ClarificationSession).filter(ClarificationSession.id == clar1).first()
        s1.expires_at = get_ist_time() - timedelta(minutes=5)
        db.commit()
        db.close()

        # Resolving expired session must fail
        from app.routes.metrics import resolve_clarification, ClarificationResolveRequest
        from fastapi import HTTPException
        req = ClarificationResolveRequest(clarification_id=clar1, selected_option_id="revenue")
        with self.assertRaises(HTTPException) as cm:
            resolve_clarification(req, user_id=self.user_a)
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("expired", cm.exception.detail.lower())

        # Session 2 is unaffected and can be resolved
        req2 = ClarificationResolveRequest(clarification_id=clar2, selected_option_id="quantity")
        res_resolved = resolve_clarification(req2, user_id=self.user_a)
        self.assertTrue(res_resolved["success"])

        # Replaying session 2 fails (stale protection)
        with self.assertRaises(HTTPException) as cm_stale:
            resolve_clarification(req2, user_id=self.user_a)
        self.assertEqual(cm_stale.exception.status_code, 404)

    # =========================================================================
    # Acceptance Check 10:
    # Users cannot access another user's metrics, datasets or clarification records.
    # =========================================================================
    def test_10_multitenant_isolation(self):
        m_a = create_or_update_metric(
            user_id=self.user_a,
            name="Alice Secret Revenue",
            source_dataset=self.table_a,
            expression="Total Sales Amount"
        )

        # User B cannot see Alice's metric in listing
        b_metrics = list_metrics(self.user_b)
        self.assertNotIn(m_a["id"], [m["id"] for m in b_metrics])

        # User B cannot access Alice's metric directly
        self.assertIsNone(get_metric(m_a["id"], self.user_b))

        # User B cannot delete Alice's metric
        self.assertFalse(delete_metric(m_a["id"], self.user_b))

        # User B cannot query Alice's dataset
        with self.assertRaises(PermissionError):
            get_authorized_dataset_columns(self.table_a, self.user_b)

        # User B cannot resolve Alice's clarification session
        clar_res = resolve_or_create_plan("Which region has the highest sales?", self.table_a, self.user_a)
        req_b = metrics_route.ClarificationResolveRequest(
            clarification_id=clar_res["clarification_id"],
            selected_option_id="revenue"
        )
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as cm_b:
            metrics_route.resolve_clarification(req_b, user_id=self.user_b)
        self.assertEqual(cm_b.exception.status_code, 404)

    # =========================================================================
    # Acceptance Check 11:
    # Nulls, empty results, decimal values, ties and division by zero follow documented rules.
    # =========================================================================
    def test_11_nulls_decimals_and_division_by_zero(self):
        cols = get_authorized_dataset_columns(self.table_a, self.user_a)

        # Division by zero safety: NULLIF compiles in SQL
        sql_div, _ = validate_and_compile_expression("Total Sales Amount / Quantity Ordered", cols, "SUM")
        self.assertIn("NULLIF(`Quantity Ordered`, 0)", sql_div)

        # Row 6 has 0.0 quantity, must evaluate cleanly to NULL without crashing
        with self.test_engine.connect() as conn:
            div_val = conn.execute(text(f"SELECT {sql_div} FROM `{self.table_a}` WHERE `Sales Region` = 'Central'")).scalar()
        self.assertIsNone(div_val, "Division by 0 in SQL must produce NULL")

        # Decimal precision formatting: no floating-point junk
        formatted = format_value(1234.5600000000002, currency_unit="USD")
        self.assertEqual(formatted, "$1,234.56")

        # Summary generation with plan
        plan = {
            "metric_name": "Revenue",
            "currency_unit": "USD",
            "grouping_dimensions": ["Sales Region"],
            "ordering": {"direction": "DESC"}
        }
        summary = generate_aggregate_summary("Highest revenue", "", [{"Sales Region": "South", "Revenue": 1250.0}], plan=plan)
        self.assertEqual(summary, "South has the highest Revenue of $1,250.")

    # =========================================================================
    # Acceptance Check 12:
    # Refine updates only intended plan fields, then executes the corrected query.
    # =========================================================================
    def test_12_refine_flow(self):
        # Base plan: highest revenue by region (limit 1, DESC)
        base_plan = resolve_or_create_plan("Which region has the highest revenue?", self.table_a, self.user_a)["plan"]
        self.assertEqual(base_plan["limit"], 1)
        self.assertEqual(base_plan["ordering"]["direction"], "DESC")

        # Refine: change to 2 lowest regions (limit 2, ASC)
        refinements = {
            "limit": 2,
            "direction": "ASC"
        }
        res = refine_and_execute_plan(base_plan, refinements, self.table_a, self.user_a)
        refined_plan = res["plan"]

        self.assertEqual(refined_plan["limit"], 2)
        self.assertEqual(refined_plan["ordering"]["direction"], "ASC")
        self.assertEqual(refined_plan["grouping_dimensions"], ["Sales Region"], "Dimensions must remain intact")
        self.assertEqual(refined_plan["metric_name"], "Revenue", "Metric must remain intact")

        with self.test_engine.connect() as conn:
            rows = [dict(r._mapping) for r in conn.execute(text(res["sql"]), res["params"])]

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Sales Region"], "Central")
        self.assertEqual(rows[0]["Revenue"], 0.0)
        self.assertEqual(rows[1]["Sales Region"], "West")
        self.assertEqual(rows[1]["Revenue"], 500.0)


if __name__ == "__main__":
    unittest.main()
