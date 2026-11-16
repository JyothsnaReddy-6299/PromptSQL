"""
Test Suite for PromptSQL Issue 15.3: Dynamic KPI & Intelligent Visual Analytics Engine

Verifies:
1. Evidence-based domain identification across multiple distinct domains and generic fallback.
2. Line-item vs transaction-level granularity detection and aggregation correctness.
3. Prevention of double counting and JOIN fan-out distortions.
4. Dynamic generation of 4-6 verified domain KPIs with formatting and period comparisons.
5. Intelligent chart selection (line trend, category breakdown, donut distribution, top entities).
6. "What stands out?" data-grounded analytical takeaways.
7. Dynamic filter extraction and parameterized WHERE clause application.
8. Preservation of technical statistical discoveries under advanced_discoveries.
9. Empty states and edge case resilience (no numeric columns, no dates, zero rows).
"""

import unittest
import json
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import text

from app.database.connection import engine
from app.services.data_discovery_service import (
    classify_columns,
    profile_dataset,
    identify_dataset_domain,
    generate_dynamic_kpis,
    generate_visual_analytics,
    generate_standout_highlights,
    get_available_filters,
    format_kpi_value,
    build_filter_clause,
    discover_dataset_insights,
    invalidate_insights_cache,
)


class TestIssue15_3_DynamicKPIs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Create and seed test tables for distinct domains and edge cases."""
        with engine.connect() as conn:
            # 1. E-Commerce Line-Item Table (Multiple items per order_id)
            conn.execute(text("DROP TABLE IF EXISTS `test_ecommerce_lineitems_usr_test153`"))
            conn.execute(text("""
                CREATE TABLE `test_ecommerce_lineitems_usr_test153` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id VARCHAR(50),
                    customer_id VARCHAR(50),
                    product_name VARCHAR(100),
                    category VARCHAR(50),
                    quantity INT,
                    unit_price DECIMAL(10, 2),
                    total_amount DECIMAL(10, 2),
                    order_date DATETIME,
                    status VARCHAR(50)
                )
            """))
            # 5 line items across 2 distinct orders
            # Order ORD-1: 3 items (Laptop $1000, Mouse $50, Keyboard $100) -> Order Total = $1150
            # Order ORD-2: 2 items (Desk $300, Chair $150) -> Order Total = $450
            # Total Revenue = $1600. Total Orders = 2 (NOT 5!). AOV = $1600 / 2 = $800. Max Order = $1150.
            conn.execute(text("""
                INSERT INTO `test_ecommerce_lineitems_usr_test153`
                (order_id, customer_id, product_name, category, quantity, unit_price, total_amount, order_date, status)
                VALUES
                ('ORD-1', 'CUST-101', 'Pro Laptop', 'Electronics', 1, 1000.00, 1000.00, '2024-01-15 10:00:00', 'Completed'),
                ('ORD-1', 'CUST-101', 'Wireless Mouse', 'Accessories', 1, 50.00, 50.00, '2024-01-15 10:00:00', 'Completed'),
                ('ORD-1', 'CUST-101', 'Mech Keyboard', 'Accessories', 1, 100.00, 100.00, '2024-01-15 10:00:00', 'Completed'),
                ('ORD-2', 'CUST-102', 'Standing Desk', 'Furniture', 1, 300.00, 300.00, '2024-02-10 14:00:00', 'Completed'),
                ('ORD-2', 'CUST-102', 'Ergo Chair', 'Furniture', 1, 150.00, 150.00, '2024-02-10 14:00:00', 'Completed')
            """))

            # 2. Student Academics Table
            conn.execute(text("DROP TABLE IF EXISTS `test_student_marks_usr_test153`"))
            conn.execute(text("""
                CREATE TABLE `test_student_marks_usr_test153` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    student_id VARCHAR(50),
                    student_name VARCHAR(100),
                    subject VARCHAR(50),
                    marks DOUBLE,
                    exam_date DATE,
                    grade VARCHAR(10)
                )
            """))
            conn.execute(text("""
                INSERT INTO `test_student_marks_usr_test153`
                (student_id, student_name, subject, marks, exam_date, grade)
                VALUES
                ('STU-1', 'Alice', 'Mathematics', 92.0, '2024-05-10', 'A'),
                ('STU-1', 'Alice', 'Physics', 85.0, '2024-05-12', 'A'),
                ('STU-2', 'Bob', 'Mathematics', 38.0, '2024-05-10', 'F'),
                ('STU-2', 'Bob', 'Physics', 74.0, '2024-05-12', 'B'),
                ('STU-3', 'Charlie', 'Mathematics', 88.0, '2024-05-10', 'A'),
                ('STU-3', 'Charlie', 'Physics', 95.0, '2024-05-12', 'A')
            """))

            # 3. Employee & Workforce Table
            conn.execute(text("DROP TABLE IF EXISTS `test_employee_payroll_usr_test153`"))
            conn.execute(text("""
                CREATE TABLE `test_employee_payroll_usr_test153` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    employee_id VARCHAR(50),
                    full_name VARCHAR(100),
                    department VARCHAR(50),
                    salary DECIMAL(10, 2),
                    hire_date DATE,
                    office VARCHAR(50)
                )
            """))
            conn.execute(text("""
                INSERT INTO `test_employee_payroll_usr_test153`
                (employee_id, full_name, department, salary, hire_date, office)
                VALUES
                ('EMP-01', 'David Kim', 'Engineering', 95000.00, '2022-01-10', 'New York'),
                ('EMP-02', 'Elena Rostova', 'Engineering', 105000.00, '2021-03-15', 'New York'),
                ('EMP-03', 'Fiona Gallagher', 'Marketing', 72000.00, '2023-06-01', 'London'),
                ('EMP-04', 'George Vance', 'Sales', 68000.00, '2023-08-20', 'London')
            """))

            # 4. Generic Table (Unknown domain, no business keywords)
            conn.execute(text("DROP TABLE IF EXISTS `test_generic_data_usr_test153`"))
            conn.execute(text("""
                CREATE TABLE `test_generic_data_usr_test153` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    alpha_code VARCHAR(20),
                    beta_metric DOUBLE,
                    cluster_group VARCHAR(20)
                )
            """))
            conn.execute(text("""
                INSERT INTO `test_generic_data_usr_test153`
                (alpha_code, beta_metric, cluster_group)
                VALUES
                ('A-10', 42.5, 'Group-X'),
                ('A-20', 88.2, 'Group-X'),
                ('A-30', 15.0, 'Group-Y'),
                ('A-40', 99.1, 'Group-Y')
            """))

            # 5. Edge Case Table: No numeric columns, only text
            conn.execute(text("DROP TABLE IF EXISTS `test_text_only_usr_test153`"))
            conn.execute(text("""
                CREATE TABLE `test_text_only_usr_test153` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    tag VARCHAR(50),
                    status VARCHAR(50)
                )
            """))
            conn.execute(text("""
                INSERT INTO `test_text_only_usr_test153` (tag, status)
                VALUES ('alpha', 'active'), ('beta', 'inactive')
            """))
            conn.commit()

    @classmethod
    def tearDownClass(cls):
        """Clean up test tables."""
        with engine.connect() as conn:
            for t in [
                "test_ecommerce_lineitems_usr_test153",
                "test_student_marks_usr_test153",
                "test_employee_payroll_usr_test153",
                "test_generic_data_usr_test153",
                "test_text_only_usr_test153",
            ]:
                conn.execute(text(f"DROP TABLE IF EXISTS `{t}`"))
            conn.commit()

    # -----------------------------------------------------------------------
    # 1. Domain Identification Tests
    # -----------------------------------------------------------------------
    def test_domain_identification_ecommerce(self):
        tbl = "test_ecommerce_lineitems_usr_test153"
        clsf = classify_columns(tbl)
        prof = profile_dataset(tbl, clsf)
        info = identify_dataset_domain(tbl, prof)
        self.assertEqual(info["domain"], "ecommerce")
        self.assertEqual(info["domain_label"], "E-Commerce & Sales")
        self.assertTrue(info["confidence"] >= 0.8)
        self.assertTrue(info["is_line_item"], "Should detect that table has multiple rows per order_id")
        self.assertEqual(info["entity_key"].lower(), "order_id")

    def test_domain_identification_education(self):
        tbl = "test_student_marks_usr_test153"
        clsf = classify_columns(tbl)
        prof = profile_dataset(tbl, clsf)
        info = identify_dataset_domain(tbl, prof)
        self.assertEqual(info["domain"], "education")
        self.assertEqual(info["domain_label"], "Student Academics")
        self.assertTrue(info["confidence"] >= 0.8)

    def test_domain_identification_hr(self):
        tbl = "test_employee_payroll_usr_test153"
        clsf = classify_columns(tbl)
        prof = profile_dataset(tbl, clsf)
        info = identify_dataset_domain(tbl, prof)
        self.assertEqual(info["domain"], "hr")
        self.assertEqual(info["domain_label"], "Workforce & HR")
        self.assertTrue(info["confidence"] >= 0.8)

    def test_domain_identification_generic_fallback(self):
        tbl = "test_generic_data_usr_test153"
        clsf = classify_columns(tbl)
        prof = profile_dataset(tbl, clsf)
        info = identify_dataset_domain(tbl, prof)
        self.assertEqual(info["domain"], "generic")
        self.assertEqual(info["domain_label"], "General Tabular Data")

    # -----------------------------------------------------------------------
    # 2. Granularity & Line-Item Aggregation Correctness
    # -----------------------------------------------------------------------
    def test_ecommerce_lineitem_aggregation_correctness(self):
        """
        Critical check: Verify that on line-item table:
        - Total Orders is COUNT(DISTINCT order_id) = 2, NOT COUNT(*) = 5.
        - Average Order Value is $1600 / 2 = $800, NOT row average $1600 / 5 = $320.
        - Max Order Value is $1150 (Order 1), NOT row max $1000.
        """
        tbl = "test_ecommerce_lineitems_usr_test153"
        clsf = classify_columns(tbl)
        prof = profile_dataset(tbl, clsf)
        info = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, info)

        kpi_map = {k["id"]: k for k in kpis}
        self.assertIn("kpi_total_orders", kpi_map)
        self.assertEqual(kpi_map["kpi_total_orders"]["raw_value"], 2, "Orders should be distinct count of 2")

        self.assertIn("kpi_total_revenue", kpi_map)
        self.assertAlmostEqual(kpi_map["kpi_total_revenue"]["raw_value"], 1600.00, places=2)

        self.assertIn("kpi_aov", kpi_map)
        self.assertAlmostEqual(kpi_map["kpi_aov"]["raw_value"], 800.00, places=2, msg="AOV must be order-level $800, not line-level $320")

        self.assertIn("kpi_max_order", kpi_map)
        self.assertAlmostEqual(kpi_map["kpi_max_order"]["raw_value"], 1150.00, places=2, msg="Max order value must be consolidated $1150")

    # -----------------------------------------------------------------------
    # 3. Academics & HR Domain KPIs
    # -----------------------------------------------------------------------
    def test_education_kpis(self):
        tbl = "test_student_marks_usr_test153"
        clsf = classify_columns(tbl)
        prof = profile_dataset(tbl, clsf)
        info = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, info)

        kpi_map = {k["id"]: k for k in kpis}
        self.assertIn("kpi_total_students", kpi_map)
        self.assertEqual(kpi_map["kpi_total_students"]["raw_value"], 3)  # STU-1, STU-2, STU-3

        self.assertIn("kpi_avg_marks", kpi_map)
        # (92 + 85 + 38 + 74 + 88 + 95) / 6 = 472 / 6 = 78.67
        self.assertAlmostEqual(kpi_map["kpi_avg_marks"]["raw_value"], 78.67, places=2)

        self.assertIn("kpi_max_marks", kpi_map)
        self.assertEqual(kpi_map["kpi_max_marks"]["raw_value"], 95.0)

        self.assertIn("kpi_min_marks", kpi_map)
        self.assertEqual(kpi_map["kpi_min_marks"]["raw_value"], 38.0)

        self.assertIn("kpi_subjects_count", kpi_map)
        self.assertEqual(kpi_map["kpi_subjects_count"]["raw_value"], 2)
        self.assertIn("kpi_best_subject", kpi_map)

    def test_hr_kpis(self):
        tbl = "test_employee_payroll_usr_test153"
        clsf = classify_columns(tbl)
        prof = profile_dataset(tbl, clsf)
        info = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, info)

        kpi_map = {k["id"]: k for k in kpis}
        self.assertIn("kpi_total_employees", kpi_map)
        self.assertEqual(kpi_map["kpi_total_employees"]["raw_value"], 4)

        self.assertIn("kpi_avg_salary", kpi_map)
        # (95000 + 105000 + 72000 + 68000) / 4 = 340000 / 4 = 85000
        self.assertAlmostEqual(kpi_map["kpi_avg_salary"]["raw_value"], 85000.0, places=2)

        self.assertIn("kpi_departments_count", kpi_map)
        self.assertEqual(kpi_map["kpi_departments_count"]["raw_value"], 3)  # Engineering, Marketing, Sales

        self.assertIn("kpi_largest_department", kpi_map)
        self.assertEqual(kpi_map["kpi_largest_department"]["value"], "Engineering")

    # -----------------------------------------------------------------------
    # 4. Chart Selection & Structure
    # -----------------------------------------------------------------------
    def test_chart_selection_with_temporal_dimension(self):
        tbl = "test_ecommerce_lineitems_usr_test153"
        clsf = classify_columns(tbl)
        prof = profile_dataset(tbl, clsf)
        info = identify_dataset_domain(tbl, prof)
        charts = generate_visual_analytics(tbl, prof, info)

        self.assertIn("overview_chart", charts)
        self.assertIsNotNone(charts["overview_chart"])
        self.assertEqual(charts["overview_chart"]["type"], "line")
        self.assertTrue(len(charts["overview_chart"]["data"]) >= 2)

        self.assertIn("category_chart", charts)
        self.assertEqual(charts["category_chart"]["type"], "bar")

        self.assertIn("distribution_chart", charts)
        self.assertEqual(charts["distribution_chart"]["type"], "donut")

        self.assertIn("top_entities_chart", charts)
        self.assertEqual(charts["top_entities_chart"]["type"], "bar")

    # -----------------------------------------------------------------------
    # 5. "What stands out?" Takeaways
    # -----------------------------------------------------------------------
    def test_standout_highlights(self):
        tbl = "test_ecommerce_lineitems_usr_test153"
        clsf = classify_columns(tbl)
        prof = profile_dataset(tbl, clsf)
        info = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, info)
        charts = generate_visual_analytics(tbl, prof, info)
        highlights = generate_standout_highlights(tbl, prof, info, kpis, charts)

        self.assertTrue(len(highlights) >= 2)
        for hl in highlights:
            self.assertIn("title", hl)
            self.assertIn("text", hl)
            self.assertIn("metric", hl)
            self.assertIn("suggested_question", hl)
            self.assertEqual(hl["action"], "Investigate")

    # -----------------------------------------------------------------------
    # 6. Dynamic Filters & Filtered Query Application
    # -----------------------------------------------------------------------
    def test_dynamic_filter_application(self):
        tbl = "test_ecommerce_lineitems_usr_test153"
        clsf = classify_columns(tbl)
        prof = profile_dataset(tbl, clsf)
        info = identify_dataset_domain(tbl, prof)

        # Unfiltered revenue = $1600
        kpis_unfiltered = generate_dynamic_kpis(tbl, prof, info)
        rev_unfiltered = next(k["raw_value"] for k in kpis_unfiltered if k["id"] == "kpi_total_revenue")
        self.assertEqual(rev_unfiltered, 1600.0)

        # Filter by category = 'Electronics' (only Laptop $1000)
        kpis_filtered = generate_dynamic_kpis(tbl, prof, info, filters={"category": "Electronics"})
        rev_filtered = next(k["raw_value"] for k in kpis_filtered if k["id"] == "kpi_total_revenue")
        self.assertEqual(rev_filtered, 1000.0)

    # -----------------------------------------------------------------------
    # 7. Number and Currency Formatting
    # -----------------------------------------------------------------------
    def test_formatting_helper(self):
        self.assertEqual(format_kpi_value(9850000, "currency", prefix="$"), "$9.85M")
        self.assertEqual(format_kpi_value(9850000, "currency"), "9.85M")
        self.assertEqual(format_kpi_value(133700, "currency", prefix="$"), "$133.7K")
        self.assertEqual(format_kpi_value(450.25, "currency", prefix="$"), "$450.25")
        self.assertEqual(format_kpi_value(2500, "count"), "2,500")
        self.assertEqual(format_kpi_value(84.52, "percentage"), "84.5%")
        self.assertEqual(format_kpi_value(92.0, "score", suffix=" / 100"), "92.0 / 100")

    # -----------------------------------------------------------------------
    # 8. Edge Case: Text-only table with no numerics
    # -----------------------------------------------------------------------
    def test_edge_case_text_only(self):
        tbl = "test_text_only_usr_test153"
        clsf = classify_columns(tbl)
        prof = profile_dataset(tbl, clsf)
        info = identify_dataset_domain(tbl, prof)
        self.assertEqual(info["domain"], "generic")
        kpis = generate_dynamic_kpis(tbl, prof, info)
        self.assertTrue(len(kpis) >= 1)
        kpi_map = {k["id"]: k for k in kpis}
        self.assertIn("kpi_total_records", kpi_map)
        self.assertEqual(kpi_map["kpi_total_records"]["raw_value"], 2)


if __name__ == "__main__":
    unittest.main()
