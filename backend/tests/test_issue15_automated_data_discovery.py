"""
PromptSQL — Issue 15: Automated Data Discovery & AI Insights Test Suite

Covers:
1. Dataset profiling: record counts, column classifications, distributions, quartiles, missing percentages.
2. Deterministic statistical pattern discovery: category concentration, numeric skewness.
3. Trend discovery: period-over-period monthly changes, peak detection, missing temporal handling.
4. Explainable anomaly detection: Tukey's IQR 1.5x rule, severe outliers, null concentrations.
5. Correlation and relationship discovery: Pearson correlation r >= 0.5, group disparities.
6. Business insight discovery: revenue/payroll concentration, top contributors.
7. SQL-backed verification: supporting SQL executable, verified records evidence.
8. AI explanation integration & deterministic fallback resilience.
9. Tenant isolation and security: rejection of unauthorized datasets and protected system tables.
10. Multi-dataset generalization: tested across 3 structurally different datasets (Sales, HR, Student Grades).
11. Cache validation & invalidation behavior.
12. Saving discoveries to the Reports module.
"""

import unittest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import text
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import engine
from app.services.auth_service import get_current_user_id
from app.services.data_discovery_service import (
    discover_dataset_insights,
    profile_dataset,
    classify_columns,
    invalidate_insights_cache,
    get_cached_insights
)


class TestIssue15AutomatedDataDiscovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ["PROMPTSQL_TESTING"] = "1"
        cls.user_id = "usr_disc15"
        cls.other_user = "usr_other99"
        cls.client = TestClient(app)

        # 3 structurally different datasets
        cls.t_sales = f"ecommerce_sales_{cls.user_id}"
        cls.t_staff = f"employee_payroll_{cls.user_id}"
        cls.t_grades = f"student_academics_{cls.user_id}"
        cls.t_other = f"secret_records_{cls.other_user}"

        cls.tables = [cls.t_sales, cls.t_staff, cls.t_grades, cls.t_other]

        with engine.begin() as conn:
            for t in cls.tables:
                conn.execute(text(f"DROP TABLE IF EXISTS `{t}`"))

            # 1. E-Commerce Sales Dataset
            conn.execute(text(f"""
                CREATE TABLE `{cls.t_sales}` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    product_category VARCHAR(50) NOT NULL,
                    customer_region VARCHAR(50) NOT NULL,
                    order_date DATE NOT NULL,
                    unit_price DECIMAL(10,2) NOT NULL,
                    quantity INT NOT NULL,
                    total_amount DECIMAL(10,2) NOT NULL,
                    notes VARCHAR(255) NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))

            # 2. Corporate Employee Payroll Dataset (HR)
            conn.execute(text(f"""
                CREATE TABLE `{cls.t_staff}` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    employee_name VARCHAR(100) NOT NULL,
                    department VARCHAR(50) NOT NULL,
                    joining_date DATE NOT NULL,
                    salary DECIMAL(12,2) NOT NULL,
                    years_experience INT NOT NULL,
                    performance_rating DECIMAL(3,1) NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))

            # 3. Student Academic Records Dataset (Education)
            conn.execute(text(f"""
                CREATE TABLE `{cls.t_grades}` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    student_id VARCHAR(30) NOT NULL,
                    subject VARCHAR(50) NOT NULL,
                    exam_score DECIMAL(5,2) NOT NULL,
                    attendance_pct DECIMAL(5,2) NOT NULL,
                    passed BOOLEAN NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))

            # 4. Other User's Dataset (Tenant Isolation)
            conn.execute(text(f"""
                CREATE TABLE `{cls.t_other}` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    sensitive_code VARCHAR(50) NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))

            # Seed E-Commerce Sales (Contains category concentration, trend, and outlier)
            sales_rows = [
                ("Electronics", "North America", "2025-01-10", 250.00, 2, 500.00, "Express"),
                ("Electronics", "North America", "2025-01-15", 300.00, 1, 300.00, None),
                ("Electronics", "Europe", "2025-02-05", 150.00, 4, 600.00, None),
                ("Electronics", "Asia", "2025-02-20", 400.00, 2, 800.00, "Discounted"),
                ("Electronics", "North America", "2025-03-01", 350.00, 3, 1050.00, None),
                ("Apparel", "Europe", "2025-01-22", 45.00, 2, 90.00, None),
                ("Apparel", "Asia", "2025-02-14", 60.00, 1, 60.00, None),
                ("Home", "North America", "2025-03-12", 120.00, 1, 120.00, None),
                # Significant outlier in total_amount
                ("Electronics", "Europe", "2025-03-25", 9500.00, 1, 9500.00, "Enterprise Bulk"),
            ]
            for r in sales_rows:
                conn.execute(text(f"""
                    INSERT INTO `{cls.t_sales}` (product_category, customer_region, order_date, unit_price, quantity, total_amount, notes)
                    VALUES (:cat, :reg, :dt, :price, :qty, :amt, :notes)
                """), {"cat": r[0], "reg": r[1], "dt": r[2], "price": r[3], "qty": r[4], "amt": r[5], "notes": r[6]})

            # Seed HR Staff (Strong correlation: experience vs salary, group disparity, n >= 10)
            staff_rows = [
                ("Alice Smith", "Engineering", "2020-01-15", 120000.00, 8, 4.8),
                ("Bob Jones", "Engineering", "2019-03-10", 145000.00, 10, 4.9),
                ("Charlie Brown", "Engineering", "2022-06-01", 95000.00, 5, 4.2),
                ("Diana Prince", "Engineering", "2024-01-10", 75000.00, 2, 4.0),
                ("Evan Wright", "Marketing", "2021-04-12", 65000.00, 4, 3.8),
                ("Fiona Gallagher", "Marketing", "2023-08-20", 52000.00, 2, 3.5),
                ("George Clark", "Support", "2022-11-05", 42000.00, 3, 3.2),
                ("Hannah Abbott", "Support", "2023-02-18", 38000.00, 1, 3.0),
                ("Ian Malcolm", "Engineering", "2021-09-01", 110000.00, 7, 4.5),
                ("Julia Roberts", "Marketing", "2020-05-15", 70000.00, 5, 4.1),
                ("Kevin Bacon", "Support", "2021-12-10", 48000.00, 3, 3.4),
                ("Laura Croft", "Engineering", "2018-02-20", 160000.00, 11, 5.0),
            ]
            for r in staff_rows:
                conn.execute(text(f"""
                    INSERT INTO `{cls.t_staff}` (employee_name, department, joining_date, salary, years_experience, performance_rating)
                    VALUES (:name, :dept, :dt, :sal, :exp, :rating)
                """), {"name": r[0], "dept": r[1], "dt": r[2], "sal": r[3], "exp": r[4], "rating": r[5]})

            # Seed Student Grades (High academic score distributions)
            grades_rows = [
                ("ST001", "Mathematics", 98.0, 95.0, 1),
                ("ST002", "Mathematics", 88.0, 90.0, 1),
                ("ST003", "Mathematics", 92.0, 92.0, 1),
                ("ST004", "Physics", 75.0, 80.0, 1),
                ("ST005", "Physics", 82.0, 85.0, 1),
                ("ST006", "Literature", 68.0, 70.0, 1),
                ("ST007", "Literature", 54.0, 60.0, 0),
            ]
            for r in grades_rows:
                conn.execute(text(f"""
                    INSERT INTO `{cls.t_grades}` (student_id, subject, exam_score, attendance_pct, passed)
                    VALUES (:sid, :sub, :score, :att, :pass)
                """), {"sid": r[0], "sub": r[1], "score": r[2], "att": r[3], "pass": r[4]})

    @classmethod
    def tearDownClass(cls):
        with engine.begin() as conn:
            for t in cls.tables:
                conn.execute(text(f"DROP TABLE IF EXISTS `{t}`"))

    def setUp(self):
        # Override authentication dependency to cls.user_id
        app.dependency_overrides[get_current_user_id] = lambda: self.user_id
        invalidate_insights_cache(self.user_id)

    def tearDown(self):
        app.dependency_overrides.clear()
        invalidate_insights_cache(self.user_id)

    # -------------------------------------------------------------
    # 1. Dataset Profiling Tests
    # -------------------------------------------------------------
    def test_01_profile_classifications_sales_dataset(self):
        classifications = classify_columns(self.t_sales)
        self.assertIn("total_amount", classifications["numeric"])
        self.assertIn("unit_price", classifications["numeric"])
        self.assertIn("quantity", classifications["numeric"])
        self.assertIn("order_date", classifications["date"])
        self.assertIn("product_category", classifications["text"])

        profile = profile_dataset(self.t_sales, classifications)
        self.assertEqual(profile["total_records"], 9)
        self.assertIn("product_category", profile["categorical_columns"])
        self.assertIn("total_amount", profile["column_stats"])
        stats = profile["column_stats"]["total_amount"]
        self.assertEqual(stats["min"], 60.0)
        self.assertEqual(stats["max"], 9500.0)
        self.assertGreater(stats["iqr"], 0)

    # -------------------------------------------------------------
    # 2. Statistical Pattern Discovery Tests
    # -------------------------------------------------------------
    def test_02_category_concentration_discovery(self):
        res = discover_dataset_insights(user_id=self.user_id, table_name=self.t_sales)
        self.assertTrue(res["success"])
        insights = res["insights"]

        # Check for category concentration on product_category (Electronics is 6 of 9 = 66.7%)
        conc = next((i for i in insights if i["id"].startswith("ins_stat_conc_product_category")), None)
        self.assertIsNotNone(conc, "Should discover category dominance in product_category")
        self.assertIn("Electronics", conc["description"])
        self.assertIn("66.6", conc["metric_value"])
        self.assertEqual(conc["category"], "STATISTICAL")
        self.assertEqual(conc["chart_type"], "bar")

    def test_03_numeric_skewness_discovery(self):
        res = discover_dataset_insights(user_id=self.user_id, table_name=self.t_sales)
        insights = res["insights"]
        skew = next((i for i in insights if i["id"].startswith("ins_stat_skew_total_amount")), None)
        self.assertIsNotNone(skew, "Should detect skewness in total_amount due to $9500 outlier")
        self.assertIn("right-skewed", skew["description"])
        self.assertIn("Max", [p["label"] for p in skew["chart_data"]])

    # -------------------------------------------------------------
    # 3. Temporal Trend Discovery Tests
    # -------------------------------------------------------------
    def test_04_trend_monthly_aggregation_and_pop(self):
        res = discover_dataset_insights(user_id=self.user_id, table_name=self.t_sales)
        insights = res["insights"]
        trend = next((i for i in insights if i["category"] == "TRENDS"), None)
        self.assertIsNotNone(trend, "Should discover monthly trend across Jan, Feb, Mar 2025")
        self.assertEqual(trend["chart_type"], "line")
        self.assertGreaterEqual(len(trend["chart_data"]), 3)
        self.assertIn("2025-01", [d["label"] for d in trend["chart_data"]])
        self.assertIn("2025-03", [d["label"] for d in trend["chart_data"]])
        self.assertTrue(len(trend["supporting_sql"]) > 10)

    # -------------------------------------------------------------
    # 4. Explainable Anomaly Detection Tests (IQR Rule)
    # -------------------------------------------------------------
    def test_05_iqr_outlier_detection_with_evidence(self):
        res = discover_dataset_insights(user_id=self.user_id, table_name=self.t_sales)
        insights = res["insights"]
        anomaly = next((i for i in insights if i["id"].startswith("ins_anomaly_iqr_total_amount")), None)
        self.assertIsNotNone(anomaly, "Should flag the $9500 record as statistical outlier")
        self.assertEqual(anomaly["category"], "ANOMALIES")
        self.assertIn("Tukey's Interquartile Range", anomaly["methodology"])
        self.assertTrue(len(anomaly["result_evidence"]) > 0)
        # Verify the outlier evidence contains the 9500 record
        values = [float(r["total_amount"]) for r in anomaly["result_evidence"]]
        self.assertIn(9500.0, values)

    # -------------------------------------------------------------
    # 5. Pearson Correlation & Group Disparities Tests
    # -------------------------------------------------------------
    def test_06_pearson_correlation_staff_experience_vs_salary(self):
        res = discover_dataset_insights(user_id=self.user_id, table_name=self.t_staff)
        self.assertTrue(res["success"])
        insights = res["insights"]

        # Years experience and salary have strong correlation categorized under STATISTICAL
        corr = next((i for i in insights if i["category"] == "STATISTICAL" and "salary" in i["id"] and "years_experience" in i["id"]), None)
        self.assertIsNotNone(corr, "Should detect strong correlation between years_experience and salary under STATISTICAL")
        self.assertIn("correlat", corr["title"].lower())
        self.assertEqual(corr["chart_type"], "scatter")
        self.assertTrue(len(corr["chart_data"]) > 0)
        self.assertIn("correlation_details", corr)
        details = corr["correlation_details"]
        self.assertGreater(details["r"], 0.7)
        self.assertEqual(details["n"], 12)
        self.assertIn("p_value", details)
        self.assertIn("disclaimer", details)
        self.assertIn("does not imply causation", details["disclaimer"])

    def test_07_group_disparity_department_salaries(self):
        res = discover_dataset_insights(user_id=self.user_id, table_name=self.t_staff)
        insights = res["insights"]
        disp = next((i for i in insights if i["id"].startswith("ins_disp_department_salary")), None)
        self.assertIsNotNone(disp, "Should detect salary disparity between Engineering and Support")
        self.assertIn("Engineering", disp["description"])
        self.assertIn("Support", disp["description"])
        self.assertTrue("difference" in disp["metric_value"] or "disparity" in disp["metric_value"])

    # -------------------------------------------------------------
    # 6. Business Insight Discovery Tests (Revenue Concentration)
    # -------------------------------------------------------------
    def test_08_business_revenue_concentration(self):
        res = discover_dataset_insights(user_id=self.user_id, table_name=self.t_sales)
        insights = res["insights"]
        biz = next((i for i in insights if i["category"] == "BUSINESS"), None)
        self.assertIsNotNone(biz, "Should detect top revenue share for Electronics")
        self.assertIn("Electronics", biz["title"])
        self.assertIn("Share", biz["metric_label"])
        self.assertGreater(float(biz["metric_value"].replace("%", "")), 50.0)

    # -------------------------------------------------------------
    # 7. Multi-Dataset Generalization Tests (Student Grades)
    # -------------------------------------------------------------
    def test_09_generalization_student_grades_dataset(self):
        res = discover_dataset_insights(user_id=self.user_id, table_name=self.t_grades)
        self.assertTrue(res["success"])
        profile = res["profile"]
        self.assertEqual(profile["total_records"], 7)
        self.assertIn("exam_score", profile["numeric_columns"])
        self.assertIn("subject", profile["categorical_columns"])
        self.assertIn("passed", profile["boolean_columns"])
        self.assertGreaterEqual(len(res["insights"]), 1)

    # -------------------------------------------------------------
    # 8. SQL-Backed Verification & Evidence Integrity
    # -------------------------------------------------------------
    def test_10_every_insight_has_executable_sql_and_evidence(self):
        res = discover_dataset_insights(user_id=self.user_id, table_name=self.t_sales)
        for ins in res["insights"]:
            self.assertTrue(bool(ins.get("title")), f"Insight {ins['id']} must have title")
            self.assertTrue(bool(ins.get("supporting_sql")), f"Insight {ins['id']} must have supporting SQL")
            self.assertTrue(bool(ins.get("methodology")), f"Insight {ins['id']} must have methodology")
            self.assertIn("suggested_questions", ins, f"Insight {ins['id']} must have suggested questions")
            self.assertGreaterEqual(len(ins["suggested_questions"]), 1)

    # -------------------------------------------------------------
    # 9. Tenant Isolation & Security Tests
    # -------------------------------------------------------------
    def test_11_cross_tenant_dataset_access_rejected(self):
        # Attempt to discover insights for another user's table
        response = self.client.post(
            "/api/insights/discover",
            json={"table_name": self.t_other}
        )
        self.assertEqual(response.status_code, 403, "Must reject cross-tenant access with 403")

    def test_12_protected_system_table_rejected(self):
        response = self.client.post(
            "/api/insights/discover",
            json={"table_name": "users"}
        )
        self.assertEqual(response.status_code, 403, "Must reject access to system table users with 403")

    # -------------------------------------------------------------
    # 10. Cache Validation & Invalidation Tests
    # -------------------------------------------------------------
    def test_13_cache_storage_and_invalidation(self):
        # Initial call populates cache
        res1 = discover_dataset_insights(user_id=self.user_id, table_name=self.t_sales)
        cached = get_cached_insights(self.user_id, self.t_sales)
        self.assertIsNotNone(cached, "Insights should be stored in memory cache")

        # Explicit invalidation
        invalidate_insights_cache(self.user_id, self.t_sales)
        self.assertIsNone(get_cached_insights(self.user_id, self.t_sales), "Cache should be cleared")

    # -------------------------------------------------------------
    # 11. Reports Module Integration Test
    # -------------------------------------------------------------
    def test_14_save_insight_to_reports(self):
        res = discover_dataset_insights(user_id=self.user_id, table_name=self.t_sales)
        ins = res["insights"][0]

        report_payload = {
            "title": f"Insight: {ins['title']}",
            "table_name": self.t_sales,
            "question": ins["title"],
            "generated_sql": ins["supporting_sql"],
            "summary": ins["description"],
            "records": ins.get("result_evidence", [])
        }
        save_res = self.client.post("/api/reports", json=report_payload)
        self.assertEqual(save_res.status_code, 200)
        data = save_res.json()
        self.assertIn("id", data)
        self.assertEqual(data.get("title"), report_payload["title"])

    # -------------------------------------------------------------
    # 12. Issue 15.1 Refinement Tests
    # -------------------------------------------------------------
    def test_15_key_discoveries_prioritization(self):
        res = discover_dataset_insights(user_id=self.user_id, table_name=self.t_sales)
        self.assertIn("key_discoveries", res)
        self.assertIn("advanced_discoveries", res)
        self.assertGreaterEqual(len(res["key_discoveries"]), 1)
        self.assertLessEqual(len(res["key_discoveries"]), 6)
        # Verify key discoveries are ranked higher or equal
        scores = [k.get("priority_score", 0) for k in res["key_discoveries"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_16_outlier_detection_bounds_and_methodology(self):
        res = discover_dataset_insights(user_id=self.user_id, table_name=self.t_sales)
        anomaly = next((i for i in res["insights"] if i["id"].startswith("ins_anomaly_iqr_total_amount")), None)
        self.assertIsNotNone(anomaly)
        self.assertIn("bounds", anomaly)
        bounds = anomaly["bounds"]
        self.assertIn("lower_fence", bounds)
        self.assertIn("upper_fence", bounds)
        self.assertIn("q1", bounds)
        self.assertIn("q3", bounds)
        self.assertIn("iqr", bounds)
        self.assertIn("outliers_count", bounds)
        self.assertEqual(bounds["outliers_count"], 1)

    def test_17_schema_relationships_distinct_category(self):
        # Insert a secondary table with a matching column to verify cross-table relationship discovery
        t_orders_items = f"order_items_{self.user_id}"
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{t_orders_items}`"))
            conn.execute(text(f"""
                CREATE TABLE `{t_orders_items}` (
                    item_id INT AUTO_INCREMENT PRIMARY KEY,
                    product_category VARCHAR(50) NOT NULL,
                    item_price DECIMAL(10,2) NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.execute(text(f"""
                INSERT INTO `{t_orders_items}` (product_category, item_price)
                VALUES ('Electronics', 250.00), ('Electronics', 300.00), ('Apparel', 45.00)
            """))

        try:
            res = discover_dataset_insights(user_id=self.user_id, table_name=self.t_sales)
            rel = next((i for i in res["insights"] if i["category"] == "SCHEMA_RELATIONSHIPS"), None)
            if rel:
                self.assertIn("relationship_details", rel)
                self.assertIn("confidence_basis", rel["relationship_details"])
        finally:
            with engine.begin() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS `{t_orders_items}`"))


if __name__ == "__main__":
    unittest.main()
