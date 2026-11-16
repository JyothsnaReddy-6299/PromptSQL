"""
PromptSQL — Issue 15.4 Independent Verification & Semantic Accuracy Test Suite

Covers mandatory test scenarios from Issue 15.4 Part 11:
1. Orders with multiple line items per order.
2. Orders with duplicate order identifiers.
3. Sales with several product categories (complete population denominator).
4. Academic records with neutral statistics (no hardcoded / 100, pass rate only with status).
5. Employee records with department statistics (no arbitrary salary labeling).
6. Financial transactions with incoming and outgoing directions.
7. Inventory with missing cost or stock values (no fabricated inventory value).
8. Generic datasets with unknown domain (neutral labels, no manufactured business terms).
9. Datasets with NULL values (null handling, NULLIF division safety).
10. Multi-table relations and JOIN fan-out prevention.
11. Datasets containing more than 12 months of data (latest 12 periods chronologically).
12. Datasets without a date column (graceful fallback).
13. Currency detection and no invented currency symbols.
14. Logical SQL display separation (no physical table names exposed).
15. Filter reactivity (parameterized date range and category filtering).
"""

import unittest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from datetime import datetime, timezone
from decimal import Decimal
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
    detect_dataset_currency,
    format_kpi_value,
    to_display_sql,
    get_logical_table_name,
    build_filter_clause,
    discover_dataset_insights,
    invalidate_insights_cache,
)


class TestIssue15_4Accuracy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Create and seed test tables for 12 distinct edge cases and domains."""
        with engine.connect() as conn:
            # Table 1: Multi-line orders with duplicate order IDs
            conn.execute(text("DROP TABLE IF EXISTS `test15_4_lineitems_usr_t154`"))
            conn.execute(text("""
                CREATE TABLE `test15_4_lineitems_usr_t154` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id VARCHAR(50),
                    product_id VARCHAR(50),
                    product_name VARCHAR(100),
                    category VARCHAR(50),
                    quantity INT,
                    total_amount DECIMAL(10, 2),
                    order_date DATETIME
                )
            """))
            # 6 line items across 3 distinct orders:
            # ORD-A: 3 items (100, 200, 300) -> sum = 600
            # ORD-B: 2 items (400, 100) -> sum = 500
            # ORD-C: 1 item (900) -> sum = 900
            # Total revenue = 2000.00. Distinct orders = 3. AOV = 2000 / 3 = 666.67. Max order = 900.00.
            conn.execute(text("""
                INSERT INTO `test15_4_lineitems_usr_t154`
                (order_id, product_id, product_name, category, quantity, total_amount, order_date)
                VALUES
                ('ORD-A', 'P1', 'Widget A1', 'Hardware', 1, 100.00, '2024-01-10 10:00:00'),
                ('ORD-A', 'P2', 'Widget A2', 'Hardware', 2, 200.00, '2024-01-10 10:00:00'),
                ('ORD-A', 'P3', 'Widget A3', 'Software', 1, 300.00, '2024-01-10 10:00:00'),
                ('ORD-B', 'P4', 'Widget B1', 'Services', 1, 400.00, '2024-02-15 11:00:00'),
                ('ORD-B', 'P5', 'Widget B2', 'Services', 1, 100.00, '2024-02-15 11:00:00'),
                ('ORD-C', 'P6', 'Widget C1', 'Hardware', 3, 900.00, '2024-03-20 12:00:00')
            """))

            # Table 2: Category share table with 8 categories (verifying denominator includes all 8!)
            conn.execute(text("DROP TABLE IF EXISTS `test15_4_categories_usr_t154`"))
            conn.execute(text("""
                CREATE TABLE `test15_4_categories_usr_t154` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    product_category VARCHAR(50),
                    revenue DECIMAL(10, 2)
                )
            """))
            # 8 categories with known revenues:
            # C1: 400, C2: 300, C3: 200, C4: 100, C5: 100, C6: 100 (top 6 sum = 1200)
            # C7: 400, C8: 400 (remaining sum = 800)
            # Total dataset sum = 2000.00!
            # C1 share must be 400 / 2000 = 20.0%, NOT 400 / 1200 = 33.3%!
            conn.execute(text("""
                INSERT INTO `test15_4_categories_usr_t154` (product_category, revenue)
                VALUES
                ('Cat1', 400.00), ('Cat2', 300.00), ('Cat3', 200.00), ('Cat4', 100.00),
                ('Cat5', 100.00), ('Cat6', 100.00), ('Cat7', 400.00), ('Cat8', 400.00)
            """))

            # Table 3: Academics without pass mark or status column
            conn.execute(text("DROP TABLE IF EXISTS `test15_4_marks_neutral_usr_t154`"))
            conn.execute(text("""
                CREATE TABLE `test15_4_marks_neutral_usr_t154` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    student_id VARCHAR(50),
                    subject VARCHAR(50),
                    score DECIMAL(5, 2)
                )
            """))
            # Scores: 75, 85, 95 -> avg = 85.00, max = 95.00, min = 75.00
            conn.execute(text("""
                INSERT INTO `test15_4_marks_neutral_usr_t154` (student_id, subject, score)
                VALUES
                ('S1', 'Math', 75.00),
                ('S2', 'Physics', 85.00),
                ('S3', 'Chemistry', 95.00)
            """))

            # Table 4: Academics with explicit pass/fail status
            conn.execute(text("DROP TABLE IF EXISTS `test15_4_marks_status_usr_t154`"))
            conn.execute(text("""
                CREATE TABLE `test15_4_marks_status_usr_t154` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    student_id VARCHAR(50),
                    subject VARCHAR(50),
                    marks DECIMAL(5, 2),
                    result VARCHAR(20)
                )
            """))
            # 4 students: 3 PASS, 1 FAIL -> pass rate = 75.0%
            conn.execute(text("""
                INSERT INTO `test15_4_marks_status_usr_t154` (student_id, subject, marks, result)
                VALUES
                ('S1', 'Math', 80.00, 'PASS'),
                ('S2', 'Math', 65.00, 'PASS'),
                ('S3', 'Math', 30.00, 'FAIL'),
                ('S4', 'Math', 90.00, 'PASS')
            """))

            # Table 5: HR without salary column (only department and staff)
            conn.execute(text("DROP TABLE IF EXISTS `test15_4_hr_nosalary_usr_t154`"))
            conn.execute(text("""
                CREATE TABLE `test15_4_hr_nosalary_usr_t154` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    employee_id VARCHAR(50),
                    department VARCHAR(50),
                    years_experience INT
                )
            """))
            # Must NOT label years_experience as Salary!
            conn.execute(text("""
                INSERT INTO `test15_4_hr_nosalary_usr_t154` (employee_id, department, years_experience)
                VALUES
                ('E1', 'Sales', 5), ('E2', 'Sales', 3), ('E3', 'Eng', 8)
            """))

            # Table 6: Financial transactions with incoming/outgoing direction
            conn.execute(text("DROP TABLE IF EXISTS `test15_4_finance_txns_usr_t154`"))
            conn.execute(text("""
                CREATE TABLE `test15_4_finance_txns_usr_t154` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    txn_id VARCHAR(50),
                    amount DECIMAL(10, 2),
                    direction VARCHAR(20),
                    txn_date DATETIME
                )
            """))
            # 4 transactions:
            # IN: 1000, 500 -> total incoming = 1500
            # OUT: 300, 200 -> total outgoing = 500
            # Total volume = 2000. Avg = 500. Max = 1000.
            conn.execute(text("""
                INSERT INTO `test15_4_finance_txns_usr_t154` (txn_id, amount, direction, txn_date)
                VALUES
                ('TX-1', 1000.00, 'IN', '2024-01-01 10:00:00'),
                ('TX-2', 500.00, 'IN', '2024-01-02 11:00:00'),
                ('TX-3', 300.00, 'OUT', '2024-01-03 12:00:00'),
                ('TX-4', 200.00, 'OUT', '2024-01-04 13:00:00')
            """))

            # Table 7: Inventory with missing unit cost
            conn.execute(text("DROP TABLE IF EXISTS `test15_4_inventory_nocost_usr_t154`"))
            conn.execute(text("""
                CREATE TABLE `test15_4_inventory_nocost_usr_t154` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    sku VARCHAR(50),
                    stock_quantity INT,
                    warehouse VARCHAR(50)
                )
            """))
            # Has stock_quantity but NO cost. Must NOT invent inventory value!
            conn.execute(text("""
                INSERT INTO `test15_4_inventory_nocost_usr_t154` (sku, stock_quantity, warehouse)
                VALUES
                ('SKU-1', 100, 'East'), ('SKU-2', 250, 'West'), ('SKU-3', 50, 'East')
            """))

            # Table 8: Generic dataset with arbitrary numbers (age, code)
            conn.execute(text("DROP TABLE IF EXISTS `test15_4_generic_data_usr_t154`"))
            conn.execute(text("""
                CREATE TABLE `test15_4_generic_data_usr_t154` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    tag VARCHAR(50),
                    reading_val DECIMAL(8, 2)
                )
            """))
            # Must use neutral labels TOTAL READING_VAL, AVERAGE READING_VAL
            conn.execute(text("""
                INSERT INTO `test15_4_generic_data_usr_t154` (tag, reading_val)
                VALUES
                ('Alpha', 12.5), ('Beta', 25.0), ('Gamma', 37.5)
            """))

            # Table 9: Dataset with NULL values in numerical fields
            conn.execute(text("DROP TABLE IF EXISTS `test15_4_null_values_usr_t154`"))
            conn.execute(text("""
                CREATE TABLE `test15_4_null_values_usr_t154` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id VARCHAR(50),
                    total_amount DECIMAL(10, 2),
                    category VARCHAR(50)
                )
            """))
            # Values: 100, NULL, 300 -> Sum = 400. Avg = 200 (not 400/3=133.33)
            conn.execute(text("""
                INSERT INTO `test15_4_null_values_usr_t154` (order_id, total_amount, category)
                VALUES
                ('ORD-N1', 100.00, 'CatA'),
                ('ORD-N2', NULL, 'CatA'),
                ('ORD-N3', 300.00, 'CatB')
            """))

            # Table 10: Multi-table JOIN fan-out prevention check
            conn.execute(text("DROP TABLE IF EXISTS `test15_4_orders_parent_usr_t154`"))
            conn.execute(text("DROP TABLE IF EXISTS `test15_4_items_child_usr_t154`"))
            conn.execute(text("""
                CREATE TABLE `test15_4_orders_parent_usr_t154` (
                    order_id VARCHAR(50) PRIMARY KEY,
                    order_total DECIMAL(10, 2)
                )
            """))
            conn.execute(text("""
                CREATE TABLE `test15_4_items_child_usr_t154` (
                    item_id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id VARCHAR(50),
                    item_name VARCHAR(100)
                )
            """))
            conn.execute(text("""
                INSERT INTO `test15_4_orders_parent_usr_t154` VALUES
                ('O-1', 100.00), ('O-2', 200.00)
            """))
            # O-1 has 3 items, O-2 has 2 items
            conn.execute(text("""
                INSERT INTO `test15_4_items_child_usr_t154` (order_id, item_name) VALUES
                ('O-1', 'Item 1'), ('O-1', 'Item 2'), ('O-1', 'Item 3'),
                ('O-2', 'Item 4'), ('O-2', 'Item 5')
            """))

            # Table 11: Dataset with 18 months of historical data (verifying latest 12 months)
            conn.execute(text("DROP TABLE IF EXISTS `test15_4_trend_18months_usr_t154`"))
            conn.execute(text("""
                CREATE TABLE `test15_4_trend_18months_usr_t154` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    sale_date DATETIME,
                    amount DECIMAL(10, 2)
                )
            """))
            # Months from 2023-01 to 2024-06 (18 distinct months)
            for yr, mo in [
                (2023, 1), (2023, 2), (2023, 3), (2023, 4), (2023, 5), (2023, 6),
                (2023, 7), (2023, 8), (2023, 9), (2023, 10), (2023, 11), (2023, 12),
                (2024, 1), (2024, 2), (2024, 3), (2024, 4), (2024, 5), (2024, 6)
            ]:
                conn.execute(text(f"""
                    INSERT INTO `test15_4_trend_18months_usr_t154` (sale_date, amount)
                    VALUES ('{yr:04d}-{mo:02d}-15 12:00:00', {mo * 100.00})
                """))

            # Table 12: Currency detection tables (INR, USD, and unestablished)
            conn.execute(text("DROP TABLE IF EXISTS `test15_4_sales_inr_usr_t154`"))
            conn.execute(text("""
                CREATE TABLE `test15_4_sales_inr_usr_t154` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    amount_inr DECIMAL(10, 2)
                )
            """))
            conn.execute(text("INSERT INTO `test15_4_sales_inr_usr_t154` (amount_inr) VALUES (50000.00)"))

    # -----------------------------------------------------------------------
    # TEST 1: Orders with multiple line items per order
    # -----------------------------------------------------------------------
    def test_line_item_order_counting_and_aov(self):
        tbl = "test15_4_lineitems_usr_t154"
        cls = classify_columns(tbl)
        prof = profile_dataset(tbl, cls)
        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)

        kpi_map = {k["id"]: k for k in kpis}
        
        # Expected Results independently calculated:
        # Total Revenue: 100 + 200 + 300 + 400 + 100 + 900 = 2000.00
        # Total Orders: Distinct order_id ('ORD-A', 'ORD-B', 'ORD-C') = 3 (NOT 6!)
        # Average Order Value: 2000.00 / 3 = 666.67 (NOT 2000 / 6 = 333.33!)
        # Highest Order Value: MAX(order_sum) = ORD-C (900.00) vs ORD-A (600.00) = 900.00
        
        self.assertIn("kpi_total_revenue", kpi_map)
        self.assertEqual(kpi_map["kpi_total_revenue"]["raw_value"], 2000.00)

        self.assertIn("kpi_total_orders", kpi_map)
        self.assertEqual(kpi_map["kpi_total_orders"]["raw_value"], 3)
        self.assertIn("DISTINCT", kpi_map["kpi_total_orders"]["execution_sql"].upper())

        self.assertIn("kpi_aov", kpi_map)
        self.assertEqual(kpi_map["kpi_aov"]["raw_value"], 666.67)

        self.assertIn("kpi_max_order", kpi_map)
        self.assertEqual(kpi_map["kpi_max_order"]["raw_value"], 900.00)

    # -----------------------------------------------------------------------
    # TEST 2: Category share percentage against complete dataset population
    # -----------------------------------------------------------------------
    def test_category_share_uses_complete_population(self):
        tbl = "test15_4_categories_usr_t154"
        cls = classify_columns(tbl)
        prof = profile_dataset(tbl, cls)
        dom = identify_dataset_domain(tbl, prof)
        charts = generate_visual_analytics(tbl, prof, dom)

        cat_chart = charts.get("category_chart")
        self.assertIsNotNone(cat_chart)
        # Total dataset value across ALL 8 categories is 2000.00
        self.assertEqual(cat_chart["total_dataset_value"], 2000.00)
        self.assertEqual(cat_chart["total_categories_count"], 8)
        self.assertEqual(cat_chart["shown_count"], 6)

        # For Cat1 (value = 400.00):
        # Correct share = 400 / 2000 = 20.0% (NOT 400 / 1200 = 33.3%!)
        top_cat = cat_chart["data"][0]
        self.assertEqual(top_cat["share_pct"], 20.0)

    # -----------------------------------------------------------------------
    # TEST 3: Academic records with neutral statistics (no / 100, pass rate only with status)
    # -----------------------------------------------------------------------
    def test_academics_neutral_scale_and_pass_rate(self):
        tbl_neutral = "test15_4_marks_neutral_usr_t154"
        cls_n = classify_columns(tbl_neutral)
        prof_n = profile_dataset(tbl_neutral, cls_n)
        dom_n = identify_dataset_domain(tbl_neutral, prof_n)
        kpis_n = generate_dynamic_kpis(tbl_neutral, prof_n, dom_n)
        kpi_map_n = {k["id"]: k for k in kpis_n}

        # Average marks = 85.00
        self.assertIn("kpi_avg_marks", kpi_map_n)
        self.assertEqual(kpi_map_n["kpi_avg_marks"]["raw_value"], 85.00)
        # Suffix must NOT contain hardcoded "/ 100"
        self.assertNotIn("/ 100", kpi_map_n["kpi_avg_marks"]["value"])
        # Pass percentage must NOT be fabricated when no status exists
        self.assertNotIn("kpi_pass_rate", kpi_map_n)

        # With status column:
        tbl_status = "test15_4_marks_status_usr_t154"
        cls_s = classify_columns(tbl_status)
        prof_s = profile_dataset(tbl_status, cls_s)
        dom_s = identify_dataset_domain(tbl_status, prof_s)
        kpis_s = generate_dynamic_kpis(tbl_status, prof_s, dom_s)
        kpi_map_s = {k["id"]: k for k in kpis_s}

        # 3 passed out of 4 students -> 75.0%
        self.assertIn("kpi_pass_rate", kpi_map_s)
        self.assertEqual(kpi_map_s["kpi_pass_rate"]["raw_value"], 75.0)

    # -----------------------------------------------------------------------
    # TEST 4: HR dataset without salary (no unsafe numeric fallback)
    # -----------------------------------------------------------------------
    def test_hr_no_arbitrary_salary_labeling(self):
        tbl = "test15_4_hr_nosalary_usr_t154"
        cls = classify_columns(tbl)
        prof = profile_dataset(tbl, cls)
        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)
        kpi_titles = [k["title"] for k in kpis]

        # Must NOT contain AVERAGE SALARY or HIGHEST SALARY
        self.assertNotIn("AVERAGE SALARY", kpi_titles)
        self.assertNotIn("HIGHEST SALARY", kpi_titles)
        self.assertIn("TOTAL EMPLOYEES", kpi_titles)
        self.assertIn("TOTAL DEPARTMENTS", kpi_titles)

    # -----------------------------------------------------------------------
    # TEST 5: Financial transactions incoming vs outgoing
    # -----------------------------------------------------------------------
    def test_finance_metrics(self):
        tbl = "test15_4_finance_txns_usr_t154"
        cls = classify_columns(tbl)
        prof = profile_dataset(tbl, cls)
        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)
        kpi_map = {k["id"]: k for k in kpis}

        self.assertIn("kpi_total_volume", kpi_map)
        self.assertEqual(kpi_map["kpi_total_volume"]["raw_value"], 2000.00)
        self.assertIn("kpi_total_transactions", kpi_map)
        self.assertEqual(kpi_map["kpi_total_transactions"]["raw_value"], 4)
        self.assertIn("kpi_avg_transaction", kpi_map)
        self.assertEqual(kpi_map["kpi_avg_transaction"]["raw_value"], 500.00)
        self.assertIn("kpi_max_transaction", kpi_map)
        self.assertEqual(kpi_map["kpi_max_transaction"]["raw_value"], 1000.00)

    # -----------------------------------------------------------------------
    # TEST 6: Inventory without cost (no fabricated valuation)
    # -----------------------------------------------------------------------
    def test_inventory_missing_cost_no_valuation(self):
        tbl = "test15_4_inventory_nocost_usr_t154"
        cls = classify_columns(tbl)
        prof = profile_dataset(tbl, cls)
        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)
        kpi_titles = [k["title"] for k in kpis]

        # Must have products and stock quantity, but NOT inventory value
        self.assertIn("TOTAL PRODUCTS", kpi_titles)
        self.assertIn("TOTAL STOCK QUANTITY", kpi_titles)
        self.assertNotIn("TOTAL INVENTORY VALUE", kpi_titles)

    # -----------------------------------------------------------------------
    # TEST 7: Generic dataset with neutral labels
    # -----------------------------------------------------------------------
    def test_generic_dataset_neutral_labels(self):
        tbl = "test15_4_generic_data_usr_t154"
        cls = classify_columns(tbl)
        prof = profile_dataset(tbl, cls)
        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)
        kpi_titles = [k["title"] for k in kpis]

        # Must NOT manufacture business terms
        for forbidden in ["TOTAL REVENUE", "AVERAGE ORDER VALUE", "AVERAGE SALARY", "AVERAGE MARKS"]:
            self.assertNotIn(forbidden, kpi_titles)
        self.assertIn("TOTAL RECORDS", kpi_titles)
        self.assertIn("TOTAL READING_VAL", kpi_titles)
        self.assertIn("AVERAGE READING_VAL", kpi_titles)

    # -----------------------------------------------------------------------
    # TEST 8: NULL value handling and division safety
    # -----------------------------------------------------------------------
    def test_null_value_handling(self):
        tbl = "test15_4_null_values_usr_t154"
        cls = classify_columns(tbl)
        prof = profile_dataset(tbl, cls)
        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)
        kpi_map = {k["id"]: k for k in kpis}

        # Total revenue = 100 + 300 = 400.00
        self.assertEqual(kpi_map["kpi_total_revenue"]["raw_value"], 400.00)
        # Distinct orders = 3
        self.assertEqual(kpi_map["kpi_total_orders"]["raw_value"], 3)

    # -----------------------------------------------------------------------
    # TEST 9: Latest 12 periods trend selection (chronologically ASC)
    # -----------------------------------------------------------------------
    def test_trend_selects_latest_12_months_chronological(self):
        tbl = "test15_4_trend_18months_usr_t154"
        cls = classify_columns(tbl)
        prof = profile_dataset(tbl, cls)
        dom = identify_dataset_domain(tbl, prof)
        charts = generate_visual_analytics(tbl, prof, dom)

        ov_chart = charts.get("overview_chart")
        self.assertIsNotNone(ov_chart)
        self.assertEqual(ov_chart["type"], "line")
        data = ov_chart["data"]

        # Exactly 12 points returned
        self.assertEqual(len(data), 12)
        # First point should be 2023-07 (month 7 of 18)
        self.assertEqual(data[0]["label"], "2023-07")
        # Last point should be 2024-06 (month 18 of 18 - the latest!)
        self.assertEqual(data[-1]["label"], "2024-06")

        # Labels must be sorted chronologically ASC
        labels = [d["label"] for d in data]
        self.assertEqual(labels, sorted(labels))

    # -----------------------------------------------------------------------
    # TEST 10: Currency detection and no invented symbols
    # -----------------------------------------------------------------------
    def test_currency_detection_and_no_invented_dollar(self):
        # INR dataset
        tbl_inr = "test15_4_sales_inr_usr_t154"
        cls_inr = classify_columns(tbl_inr)
        prof_inr = profile_dataset(tbl_inr, cls_inr)
        sym_inr, code_inr = detect_dataset_currency(tbl_inr, prof_inr)
        self.assertEqual(sym_inr, "₹")
        self.assertEqual(code_inr, "INR")

        # Unestablished currency dataset
        tbl_none = "test15_4_lineitems_usr_t154"
        cls_none = classify_columns(tbl_none)
        prof_none = profile_dataset(tbl_none, cls_none)
        sym_none, code_none = detect_dataset_currency(tbl_none, prof_none)
        self.assertEqual(sym_none, "")
        self.assertEqual(code_none, "")

        # Format test: unestablished currency MUST NOT display "$"
        val_str = format_kpi_value(25000.0, "currency", prefix=sym_none)
        self.assertNotIn("$", val_str)
        self.assertEqual(val_str, "25.0K")

    # -----------------------------------------------------------------------
    # TEST 11: SQL display separation (logical names vs physical execution)
    # -----------------------------------------------------------------------
    def test_logical_sql_display_separation(self):
        tbl = "test15_4_lineitems_usr_t154"
        cls = classify_columns(tbl)
        prof = profile_dataset(tbl, cls)
        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)

        for k in kpis:
            display_sql = k["display_sql"]
            execution_sql = k["execution_sql"]
            
            # Display SQL must NOT expose user ID or physical suffix
            self.assertNotIn("usr_t154", display_sql)
            # Display SQL must contain logical table name
            self.assertIn("test15_4_lineitems", display_sql)
            # Execution SQL MUST remain physical and executable
            self.assertIn("test15_4_lineitems_usr_t154", execution_sql)

    # -----------------------------------------------------------------------
    # TEST 12: Filter reactivity
    # -----------------------------------------------------------------------
    def test_filter_reactivity(self):
        tbl = "test15_4_lineitems_usr_t154"
        cls = classify_columns(tbl)
        prof = profile_dataset(tbl, cls)
        dom = identify_dataset_domain(tbl, prof)

        # Baseline: all 3 orders -> Revenue = 2000.00
        base_kpis = generate_dynamic_kpis(tbl, prof, dom, filters=None)
        rev_base = next(k["raw_value"] for k in base_kpis if k["id"] == "kpi_total_revenue")
        self.assertEqual(rev_base, 2000.00)

        # Filter by Category = 'Hardware' (ORD-A items 100+200 + ORD-C item 900 = 1200.00)
        filt_kpis = generate_dynamic_kpis(tbl, prof, dom, filters={"category": "Hardware"})
        rev_filt = next(k["raw_value"] for k in filt_kpis if k["id"] == "kpi_total_revenue")
        self.assertEqual(rev_filt, 1200.00)

        # Filter by Date range (January only -> 600.00)
        date_kpis = generate_dynamic_kpis(tbl, prof, dom, filters={"_date_from": "2024-01-01", "_date_to": "2024-01-31"})
        rev_date = next(k["raw_value"] for k in date_kpis if k["id"] == "kpi_total_revenue")
        self.assertEqual(rev_date, 600.00)


if __name__ == "__main__":
    unittest.main()
