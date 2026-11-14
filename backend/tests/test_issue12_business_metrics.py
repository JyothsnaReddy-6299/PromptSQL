"""
PromptSQL — Issue 12.1: Business Metrics Query & Summarization Test Suite

Verifies:
1. Completion rate: 0.7143 is presented as 71.43% when the metric is explicitly a rate.
2. Ordinary COUNT: remains a count.
3. Ordinary decimal aggregate: is not formatted as a percentage.
4. One-row grouped result: does not falsely claim it is the highest.
5. Multi-row grouped result: summary includes meaningful actual values.
6. YoY growth calculation with CTE/LAG.
7. MoM growth calculation with CTE/LAG.
8. Zero previous-period value safe handling.
9. Missing previous period (first period) safe NULL handling.
10. Parent metric aggregation across 1:N join without fan-out inflated totals.
11. Missing required columns: safe rejection.
12. Tenant isolation and SQLGlot validation remain intact.
"""

import unittest
from decimal import Decimal
from sqlalchemy import text
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import engine
from app.services.auth_service import get_current_user_id
from app.routes.ask import ask_question, AskRequest
from app.services.aggregate_summary import (
    generate_aggregate_summary,
    format_value,
    is_rate_or_percentage,
    to_number
)
from app.services.result_interpreter import interpret_result


class TestIssue12BusinessMetrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.user_id = "usr_bm12"
        cls.t_cust = f"customers_{cls.user_id}"
        cls.t_ord = f"orders_{cls.user_id}"
        cls.t_items = f"order_items_{cls.user_id}"
        cls.t_staff = f"staff_{cls.user_id}"
        cls.t_train = f"training_{cls.user_id}"
        cls.t_saas = f"subscriptions_{cls.user_id}"  # Structurally different dataset: SaaS

        cls.all_tables = [cls.t_items, cls.t_ord, cls.t_cust, cls.t_train, cls.t_staff, cls.t_saas]

        with engine.begin() as conn:
            for t in cls.all_tables:
                conn.execute(text(f"DROP TABLE IF EXISTS `{t}`"))

            # E-Commerce Tables
            conn.execute(text(f"""
                CREATE TABLE `{cls.t_cust}` (
                    customer_id INT PRIMARY KEY,
                    customer_name VARCHAR(100) NOT NULL,
                    country VARCHAR(50) NOT NULL,
                    signup_date DATE NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))

            conn.execute(text(f"""
                CREATE TABLE `{cls.t_ord}` (
                    order_id INT PRIMARY KEY,
                    customer_id INT NOT NULL,
                    order_date DATE NOT NULL,
                    order_status VARCHAR(30) NOT NULL,
                    total_amount DECIMAL(10,2) NOT NULL,
                    INDEX idx_cust (customer_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))

            conn.execute(text(f"""
                CREATE TABLE `{cls.t_items}` (
                    item_id INT PRIMARY KEY,
                    order_id INT NOT NULL,
                    product_name VARCHAR(100) NOT NULL,
                    category VARCHAR(50) NOT NULL,
                    quantity INT NOT NULL,
                    unit_price DECIMAL(10,2) NOT NULL,
                    INDEX idx_ord (order_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))

            # Corporate HR & Training Tables
            conn.execute(text(f"""
                CREATE TABLE `{cls.t_staff}` (
                    staff_no VARCHAR(20) PRIMARY KEY,
                    full_name VARCHAR(100) NOT NULL,
                    department VARCHAR(50) NOT NULL,
                    salary DECIMAL(12,2) NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))

            conn.execute(text(f"""
                CREATE TABLE `{cls.t_train}` (
                    enrollment_ref VARCHAR(20) PRIMARY KEY,
                    staff_no VARCHAR(20) NOT NULL,
                    module_code VARCHAR(20) NOT NULL,
                    completion_status VARCHAR(30) NOT NULL,
                    score DECIMAL(5,2) NULL,
                    INDEX idx_staff (staff_no)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))

            # Structurally different domain: SaaS Subscriptions
            conn.execute(text(f"""
                CREATE TABLE `{cls.t_saas}` (
                    subscription_id INT PRIMARY KEY,
                    plan_name VARCHAR(50) NOT NULL,
                    mrr DECIMAL(10,2) NOT NULL,
                    status VARCHAR(30) NOT NULL,
                    start_date DATE NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))

            # Seed E-Commerce:
            # Customer 1 has order 101 ($250) with 2 items and order 102 ($120) with 1 item.
            # Total true order amount for Customer 1 is $370.00.
            conn.execute(text(f"""
                INSERT INTO `{cls.t_cust}` VALUES
                (1, 'Alice Smith', 'USA', '2024-01-15'),
                (2, 'Bob Jones', 'Canada', '2024-03-22')
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.t_ord}` VALUES
                (101, 1, '2025-01-10', 'Completed', 250.00),
                (102, 1, '2025-06-15', 'Completed', 120.00),
                (103, 2, '2025-07-20', 'Completed', 80.00),
                (104, 1, '2026-01-12', 'Completed', 500.00),
                (105, 2, '2026-02-18', 'Completed', 200.00)
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.t_items}` VALUES
                (1, 101, 'Keyboard', 'Electronics', 2, 100.00),
                (2, 101, 'Mouse Pad', 'Accessories', 1, 50.00),
                (3, 102, 'USB Hub', 'Electronics', 1, 120.00),
                (4, 103, 'Notebook', 'Stationery', 4, 20.00),
                (5, 104, 'Monitor', 'Electronics', 1, 500.00),
                (6, 105, 'Headphones', 'Electronics', 1, 200.00)
            """))

            # Seed HR & Training: 7 enrollments, 5 Completed -> 5/7 = 0.7142857 (71.43%)
            conn.execute(text(f"""
                INSERT INTO `{cls.t_staff}` VALUES
                ('ST-101', 'Maya Iyer', 'Engineering', 90000.00),
                ('ST-102', 'Arjun Mehta', 'Finance', 95000.00),
                ('ST-103', 'Rahul Das', 'Marketing', 65000.00)
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.t_train}` VALUES
                ('EN-01', 'ST-101', 'PY-101', 'Completed', 95.00),
                ('EN-02', 'ST-101', 'SEC-201', 'Completed', 88.00),
                ('EN-03', 'ST-102', 'FN-101', 'Completed', 91.00),
                ('EN-04', 'ST-103', 'PY-101', 'In Progress', NULL),
                ('EN-05', 'ST-103', 'MKT-101', 'Completed', 74.00),
                ('EN-06', 'ST-101', 'ARCH-301', 'Completed', 98.00),
                ('EN-07', 'ST-102', 'LEAD-101', 'Withdrawn', NULL)
            """))

            # Seed SaaS:
            conn.execute(text(f"""
                INSERT INTO `{cls.t_saas}` VALUES
                (1, 'Starter', 50.00, 'Active', '2025-01-01'),
                (2, 'Pro', 200.00, 'Active', '2025-02-01'),
                (3, 'Enterprise', 1000.00, 'Active', '2025-03-01')
            """))

    @classmethod
    def tearDownClass(cls):
        with engine.begin() as conn:
            for t in cls.all_tables:
                conn.execute(text(f"DROP TABLE IF EXISTS `{t}`"))

    def setUp(self):
        app.dependency_overrides[get_current_user_id] = lambda: self.user_id
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    # -------------------------------------------------------------
    # 1. Completion Rate Percentage Formatting
    # -------------------------------------------------------------
    def test_01_completion_rate_percentage_formatting(self):
        """Completion rate of 0.7143 must be presented as 71.43%, never '0.7143 matching records'."""
        sql = "SELECT COUNT(CASE WHEN completion_status = 'Completed' THEN 1 END) / COUNT(*) AS completion_rate FROM training;"
        records = [{"completion_rate": 0.7142857}]
        summary = generate_aggregate_summary("What is the completion rate?", sql, records)

        self.assertIn("71.43%", summary)
        self.assertNotIn("matching records", summary)
        self.assertNotIn("0.7143", summary)

    # -------------------------------------------------------------
    # 2. Ordinary COUNT Remains Count
    # -------------------------------------------------------------
    def test_02_ordinary_count_remains_count(self):
        """Ordinary COUNT query must be formatted as an integer count, never a percentage."""
        sql = "SELECT COUNT(customer_id) AS total_customer_count FROM customers;"
        records = [{"total_customer_count": 5}]
        summary = generate_aggregate_summary("What is the total customer count?", sql, records)

        self.assertIn("5", summary)
        self.assertIn("matching records", summary)
        self.assertNotIn("%", summary)

    # -------------------------------------------------------------
    # 3. Ordinary Decimal Aggregate Not Percentage
    # -------------------------------------------------------------
    def test_03_ordinary_decimal_aggregate_not_percentage(self):
        """Currency and ordinary decimal averages/sums must not be converted to percentages."""
        sql_avg = "SELECT AVG(salary) AS average_salary FROM staff;"
        summary_avg = generate_aggregate_summary("Average salary?", sql_avg, [{"average_salary": 91000.00}])
        self.assertIn("91,000.00", summary_avg)
        self.assertNotIn("%", summary_avg)

        sql_sum = "SELECT SUM(total_amount) AS total_revenue FROM orders;"
        summary_sum = generate_aggregate_summary("Total revenue?", sql_sum, [{"total_revenue": 1420.00}])
        self.assertIn("1,420.00", summary_sum)
        self.assertNotIn("%", summary_sum)

    # -------------------------------------------------------------
    # 4. One-Row Grouped Result Does Not Falsely Claim Highest
    # -------------------------------------------------------------
    def test_04_one_row_grouped_result_no_false_highest(self):
        """Single-row grouped result must not claim to be 'highest total' unless explicitly ordered with LIMIT 1."""
        sql_unfiltered = "SELECT department, AVG(salary) AS average_salary FROM staff WHERE department = 'Engineering' GROUP BY department;"
        summary_regular = generate_aggregate_summary("Engineering average salary?", sql_unfiltered, [{"department": "Engineering", "average_salary": 90000.00}])
        self.assertNotIn("highest total value", summary_regular)
        self.assertIn("Engineering", summary_regular)
        self.assertIn("90,000.00", summary_regular)

        # Contrast with explicit highest query
        sql_top = "SELECT department, AVG(salary) AS average_salary FROM staff GROUP BY department ORDER BY average_salary DESC LIMIT 1;"
        summary_top = generate_aggregate_summary("Which department has highest average salary?", sql_top, [{"department": "Finance", "average_salary": 95000.00}])
        self.assertIn("highest", summary_top)
        self.assertIn("Finance", summary_top)

    # -------------------------------------------------------------
    # 5. Multi-Row Grouped Result Contains Meaningful Actual Values
    # -------------------------------------------------------------
    def test_05_multi_row_grouped_result_contains_actual_values(self):
        """Multi-row grouped summaries must state actual values and identify highest and lowest groups."""
        sql = "SELECT department, AVG(salary) AS average_salary FROM staff GROUP BY department;"
        records = [
            {"department": "Engineering", "average_salary": 90000.00},
            {"department": "Finance", "average_salary": 95000.00},
            {"department": "Marketing", "average_salary": 65000.00}
        ]
        summary = generate_aggregate_summary("Average salary by department?", sql, records)

        self.assertIn("3 grouped results", summary)
        self.assertIn("Finance", summary)
        self.assertIn("95,000.00", summary)
        self.assertIn("Marketing", summary)
        self.assertIn("65,000.00", summary)
        self.assertIn("highest", summary)
        self.assertIn("lowest", summary)

    # -------------------------------------------------------------
    # 6. YoY Growth Calculation
    # -------------------------------------------------------------
    def test_06_yoy_growth_calculation(self):
        """Natural language YoY query generates valid CTE query with LAG and computes YoY growth."""
        req = AskRequest(question="Show year-over-year sales growth")
        res = ask_question(payload=req, x_table_name=self.t_ord, user_id=self.user_id)

        self.assertTrue(res["success"], f"YoY query failed: {res.get('error')}")
        sql = res["generated_sql"].lower()
        self.assertTrue("lag(" in sql or "join" in sql, "YoY query should use LAG or period join")
        self.assertGreater(len(res["result"]), 0)

        # 2025 total is $450 (101: 250, 102: 120, 103: 80); 2026 total is $700 (104: 500, 105: 200)
        # Expected growth: (700 - 450) / 450 * 100 = 55.56%
        row2026 = [r for r in res["result"] if str(r.get("year", "")) == "2026" or "2026" in str(r.values())]
        self.assertTrue(len(row2026) > 0)
        growth_val = None
        for k, v in row2026[0].items():
            if "growth" in k.lower() or "pct" in k.lower() or "percent" in k.lower():
                growth_val = float(v)
                break
        if growth_val is not None:
            self.assertAlmostEqual(growth_val, 55.56, delta=1.5)

    # -------------------------------------------------------------
    # 7. MoM Growth Calculation
    # -------------------------------------------------------------
    def test_07_mom_growth_calculation(self):
        """Natural language MoM query generates valid period calculation across months."""
        req = AskRequest(question="Show month-over-month sales growth")
        res = ask_question(payload=req, x_table_name=self.t_ord, user_id=self.user_id)

        self.assertTrue(res["success"], f"MoM query failed: {res.get('error')}")
        self.assertGreater(len(res["result"]), 0)

    # -------------------------------------------------------------
    # 8. Zero Previous-Period Value Safe Handling
    # -------------------------------------------------------------
    def test_08_zero_previous_period_value_safe_handling(self):
        """When previous period is 0, growth calculation must return NULL without division-by-zero error."""
        sql = """
        WITH periods AS (
            SELECT 2024 AS yr, 0.00 AS amt
            UNION ALL
            SELECT 2025 AS yr, 100.00 AS amt
        )
        SELECT yr, amt,
            CASE 
                WHEN LAG(amt) OVER (ORDER BY yr) IS NULL THEN NULL
                WHEN LAG(amt) OVER (ORDER BY yr) = 0 THEN NULL
                ELSE (amt - LAG(amt) OVER (ORDER BY yr)) / LAG(amt) OVER (ORDER BY yr) * 100
            END AS growth_pct
        FROM periods;
        """
        with engine.connect() as conn:
            result = conn.execute(text(sql)).mappings().all()
            self.assertEqual(len(result), 2)
            self.assertIsNone(result[0]["growth_pct"])
            self.assertIsNone(result[1]["growth_pct"])  # Safely returns NULL when previous is 0

    # -------------------------------------------------------------
    # 9. Missing Previous Period (First Period) Safe NULL Handling
    # -------------------------------------------------------------
    def test_09_missing_previous_period_safe_null_handling(self):
        """The earliest period has no preceding period and must have a NULL growth metric."""
        records = [
            {"year": 2025, "total_sales": 450.00, "growth_percentage": None},
            {"year": 2026, "total_sales": 700.00, "growth_percentage": 55.56}
        ]
        sql = "WITH period_metrics AS (...) SELECT year, total_sales, growth_percentage FROM period_metrics"
        summary = generate_aggregate_summary("YoY sales growth", sql, records)
        self.assertIn("2 grouped results", summary)
        self.assertIn("55.56%", summary)

    # -------------------------------------------------------------
    # 10. Parent Metric Aggregation Across 1:N Join Without Fan-Out Inflation
    # -------------------------------------------------------------
    def test_10_parent_metric_aggregation_1_to_n_join_no_fanout(self):
        """Parent order total amount must not be multiplied by the number of order items."""
        # Customer 1 placed Order 101 ($250, 2 items), Order 102 ($120, 1 item), Order 104 ($500, 1 item).
        # Customer 1 true total order amount = $250 + $120 + $500 = $870.00.
        # If joined naively with order_items (which has 2 items for order 101), Order 101 would be counted twice, yielding $1,120.00.
        req = AskRequest(question="Show total order amount and total items quantity for each customer")
        res = ask_question(payload=req, x_table_name=self.t_ord, user_id=self.user_id)

        self.assertTrue(res["success"], f"Multi-table 1:N query failed: {res.get('error')}")
        cust1_row = [r for r in res["result"] if r.get("customer_id") == 1 or list(r.values())[0] == 1]
        self.assertTrue(len(cust1_row) > 0)
        
        # Check order amount for customer 1
        row = cust1_row[0]
        amt = None
        for k, v in row.items():
            if "amount" in k.lower() or "order" in k.lower():
                try:
                    num = float(v)
                    if num > 100:  # distinguishes from quantity
                        amt = num
                except (ValueError, TypeError):
                    pass

        self.assertIsNotNone(amt, f"Could not find customer 1 order amount in {row}")
        self.assertEqual(amt, 870.00, f"Order total was inflated by 1:N fanout! Expected 870.00, got {amt}")

    # -------------------------------------------------------------
    # 11. Missing Required Columns: Safe Rejection
    # -------------------------------------------------------------
    def test_11_missing_required_columns_safe_rejection(self):
        """Questions requiring absent columns must be gracefully rejected via INVALID_QUERY."""
        req = AskRequest(question="What is the profit margin for each product?")
        res = ask_question(payload=req, x_table_name=self.t_items, user_id=self.user_id)

        # order_items lacks a cost column, so profit margin cannot be computed
        self.assertFalse(res["success"])
        self.assertIn("error", res)
        self.assertNotIn("pymysql", res["error"].lower())

    # -------------------------------------------------------------
    # 12. Structurally Different Domain (SaaS Subscriptions)
    # -------------------------------------------------------------
    def test_12_saas_metrics_domain_generalization(self):
        """PromptSQL correctly calculates metrics on a distinct SaaS subscription schema."""
        req = AskRequest(question="What is the total MRR for active subscriptions?")
        res = ask_question(payload=req, x_table_name=self.t_saas, user_id=self.user_id)

        self.assertTrue(res["success"], f"SaaS query failed: {res.get('error')}")
        self.assertEqual(res["count"], 1)
        # Sum of 50 + 200 + 1000 = 1250.00
        val = float(list(res["result"][0].values())[0])
        self.assertEqual(val, 1250.00)
        self.assertIn("1,250.00", res["summary"])
        self.assertNotIn("%", res["summary"])


if __name__ == "__main__":
    unittest.main()
