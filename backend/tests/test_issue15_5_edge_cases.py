"""
PromptSQL — Issue 15.5 Final AI Analytics Edge-Case Corrections & Verification Test Suite

Covers mandatory test groups from Issue 15.5:
- Test Group A: Order-grain detection (Cases A, B, C, equal line amounts, ambiguous amount semantics).
- Test Group B: Zero-baseline percentage changes (0->10k, 0->0, 10k->0, 10k->12k, 12k->10k, neg->pos, pos->neg, NULL prev, NULL cur).
- Test Group C: Mixed currency (INR only, USD only, INR+USD, INR+USD+JPY, missing currency, unknown currency, no currency).
"""

import unittest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from sqlalchemy import text

from app.database.connection import engine
from app.services.data_discovery_service import (
    classify_columns,
    profile_dataset,
    identify_dataset_domain,
    generate_dynamic_kpis,
    detect_dataset_currency,
    detect_dataset_currency_details,
    evaluate_period_change,
    inspect_order_amount_grain,
    format_kpi_value
)


def _get_profile(tbl):
    classes = classify_columns(tbl)
    return profile_dataset(tbl, classes)


class TestIssue15_5EdgeCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Create and seed database tables for all edge case scenarios."""
        with engine.connect() as conn:
            # -----------------------------------------------------------------
            # Group A Tables: Order-Grain Detection
            # -----------------------------------------------------------------
            # Test 1: One row per order (Case A)
            conn.execute(text("DROP TABLE IF EXISTS `test15_5_case_a_usr_t155`"))
            conn.execute(text("""
                CREATE TABLE `test15_5_case_a_usr_t155` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id VARCHAR(50),
                    product VARCHAR(100),
                    order_amount DECIMAL(10, 2),
                    order_date DATETIME
                )
            """))
            conn.execute(text("""
                INSERT INTO `test15_5_case_a_usr_t155` (order_id, product, order_amount, order_date)
                VALUES
                ('O101', 'Laptop', 50000.00, '2024-01-15 10:00:00'),
                ('O102', 'Keyboard', 2000.00, '2024-02-15 11:00:00')
            """))

            # Test 2: Line-item amounts (Case B)
            conn.execute(text("DROP TABLE IF EXISTS `test15_5_case_b_usr_t155`"))
            conn.execute(text("""
                CREATE TABLE `test15_5_case_b_usr_t155` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id VARCHAR(50),
                    product VARCHAR(100),
                    line_amount DECIMAL(10, 2),
                    order_date DATETIME
                )
            """))
            conn.execute(text("""
                INSERT INTO `test15_5_case_b_usr_t155` (order_id, product, line_amount, order_date)
                VALUES
                ('O101', 'Laptop', 40000.00, '2024-01-15 10:00:00'),
                ('O101', 'Mouse', 10000.00, '2024-01-15 10:00:00'),
                ('O102', 'Keyboard', 2000.00, '2024-02-15 11:00:00')
            """))

            # Test 3: Repeated order-level totals (Case C)
            conn.execute(text("DROP TABLE IF EXISTS `test15_5_case_c_usr_t155`"))
            conn.execute(text("""
                CREATE TABLE `test15_5_case_c_usr_t155` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id VARCHAR(50),
                    product VARCHAR(100),
                    total_amount DECIMAL(10, 2),
                    order_date DATETIME
                )
            """))
            conn.execute(text("""
                INSERT INTO `test15_5_case_c_usr_t155` (order_id, product, total_amount, order_date)
                VALUES
                ('O101', 'Laptop', 50000.00, '2024-01-15 10:00:00'),
                ('O101', 'Mouse', 50000.00, '2024-01-15 10:00:00'),
                ('O102', 'Keyboard', 2000.00, '2024-02-15 11:00:00')
            """))

            # Test 4: Repeated values that are genuinely separate line-item amounts (Case B equal lines)
            conn.execute(text("DROP TABLE IF EXISTS `test15_5_equal_lines_usr_t155`"))
            conn.execute(text("""
                CREATE TABLE `test15_5_equal_lines_usr_t155` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id VARCHAR(50),
                    product VARCHAR(100),
                    line_amount DECIMAL(10, 2),
                    order_date DATETIME
                )
            """))
            conn.execute(text("""
                INSERT INTO `test15_5_equal_lines_usr_t155` (order_id, product, line_amount, order_date)
                VALUES
                ('O101', 'Mouse A', 25000.00, '2024-01-15 10:00:00'),
                ('O101', 'Mouse B', 25000.00, '2024-01-15 10:00:00'),
                ('O102', 'Keyboard', 2000.00, '2024-02-15 11:00:00')
            """))

            # Test 5: Ambiguous amount semantics
            conn.execute(text("DROP TABLE IF EXISTS `test15_5_ambiguous_grain_usr_t155`"))
            conn.execute(text("""
                CREATE TABLE `test15_5_ambiguous_grain_usr_t155` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id VARCHAR(50),
                    product VARCHAR(100),
                    amount DECIMAL(10, 2),
                    order_date DATETIME
                )
            """))
            conn.execute(text("""
                INSERT INTO `test15_5_ambiguous_grain_usr_t155` (order_id, product, amount, order_date)
                VALUES
                ('O101', 'Item A', 25000.00, '2024-01-15 10:00:00'),
                ('O101', 'Item B', 25000.00, '2024-01-15 10:00:00'),
                ('O102', 'Item C', 2000.00, '2024-02-15 11:00:00')
            """))

            # -----------------------------------------------------------------
            # Group C Tables: Currency Scenarios
            # -----------------------------------------------------------------
            # C1: INR only
            conn.execute(text("DROP TABLE IF EXISTS `test15_5_curr_inr_usr_t155`"))
            conn.execute(text("""
                CREATE TABLE `test15_5_curr_inr_usr_t155` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    transaction_id VARCHAR(50),
                    amount DECIMAL(10, 2),
                    currency VARCHAR(10)
                )
            """))
            conn.execute(text("""
                INSERT INTO `test15_5_curr_inr_usr_t155` (transaction_id, amount, currency)
                VALUES ('T1', 15000.00, 'INR'), ('T2', 5000.00, 'INR')
            """))

            # C2: USD only
            conn.execute(text("DROP TABLE IF EXISTS `test15_5_curr_usd_usr_t155`"))
            conn.execute(text("""
                CREATE TABLE `test15_5_curr_usd_usr_t155` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    transaction_id VARCHAR(50),
                    amount DECIMAL(10, 2),
                    currency VARCHAR(10)
                )
            """))
            conn.execute(text("""
                INSERT INTO `test15_5_curr_usd_usr_t155` (transaction_id, amount, currency)
                VALUES ('T1', 10000.00, 'USD'), ('T2', 2000.00, 'USD')
            """))

            # C3: INR and USD together
            conn.execute(text("DROP TABLE IF EXISTS `test15_5_curr_inr_usd_usr_t155`"))
            conn.execute(text("""
                CREATE TABLE `test15_5_curr_inr_usd_usr_t155` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    transaction_id VARCHAR(50),
                    amount DECIMAL(10, 2),
                    currency VARCHAR(10)
                )
            """))
            conn.execute(text("""
                INSERT INTO `test15_5_curr_inr_usd_usr_t155` (transaction_id, amount, currency)
                VALUES
                ('T001', 15000.00, 'INR'),
                ('T002', 10000.00, 'USD')
            """))

            # C4: INR, USD and JPY together
            conn.execute(text("DROP TABLE IF EXISTS `test15_5_curr_inr_usd_jpy_usr_t155`"))
            conn.execute(text("""
                CREATE TABLE `test15_5_curr_inr_usd_jpy_usr_t155` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    transaction_id VARCHAR(50),
                    amount DECIMAL(10, 2),
                    currency VARCHAR(10)
                )
            """))
            conn.execute(text("""
                INSERT INTO `test15_5_curr_inr_usd_jpy_usr_t155` (transaction_id, amount, currency)
                VALUES
                ('T001', 15000.00, 'INR'),
                ('T002', 10000.00, 'USD'),
                ('T003', 5000.00, 'JPY')
            """))

            # C5: Missing currency values
            conn.execute(text("DROP TABLE IF EXISTS `test15_5_curr_missing_usr_t155`"))
            conn.execute(text("""
                CREATE TABLE `test15_5_curr_missing_usr_t155` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    transaction_id VARCHAR(50),
                    amount DECIMAL(10, 2),
                    currency VARCHAR(10)
                )
            """))
            conn.execute(text("""
                INSERT INTO `test15_5_curr_missing_usr_t155` (transaction_id, amount, currency)
                VALUES
                ('T001', 15000.00, 'INR'),
                ('T002', 10000.00, NULL),
                ('T003', 5000.00, '')
            """))

            # C6: Unknown currency codes
            conn.execute(text("DROP TABLE IF EXISTS `test15_5_curr_unknown_usr_t155`"))
            conn.execute(text("""
                CREATE TABLE `test15_5_curr_unknown_usr_t155` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    transaction_id VARCHAR(50),
                    amount DECIMAL(10, 2),
                    currency VARCHAR(10)
                )
            """))
            conn.execute(text("""
                INSERT INTO `test15_5_curr_unknown_usr_t155` (transaction_id, amount, currency)
                VALUES
                ('T001', 15000.00, 'INR'),
                ('T002', 10000.00, 'ZZZ')
            """))

            # C7: Dataset with currency information unavailable
            conn.execute(text("DROP TABLE IF EXISTS `test15_5_curr_none_usr_t155`"))
            conn.execute(text("""
                CREATE TABLE `test15_5_curr_none_usr_t155` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    metric_id VARCHAR(50),
                    volume DECIMAL(10, 2)
                )
            """))
            conn.execute(text("""
                INSERT INTO `test15_5_curr_none_usr_t155` (metric_id, volume)
                VALUES ('M01', 52000.00), ('M02', 26000.00)
            """))

            conn.commit()

    # =========================================================================
    # Test Group A: Order-Grain Detection
    # =========================================================================
    def test_group_a_case_a_single_row_per_order(self):
        """Test A1: One row per order correctly produces verified totals."""
        tbl = "test15_5_case_a_usr_t155"
        prof = _get_profile(tbl)
        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)
        kpi_map = {k["id"]: k for k in kpis}

        self.assertIn("kpi_total_revenue", kpi_map)
        self.assertIn("kpi_total_orders", kpi_map)
        self.assertIn("kpi_aov", kpi_map)
        self.assertIn("kpi_max_order", kpi_map)

        self.assertEqual(kpi_map["kpi_total_revenue"]["raw_value"], 52000.00)
        self.assertEqual(kpi_map["kpi_total_orders"]["raw_value"], 2)
        self.assertEqual(kpi_map["kpi_aov"]["raw_value"], 26000.00)
        self.assertEqual(kpi_map["kpi_max_order"]["raw_value"], 50000.00)

    def test_group_a_case_b_line_item_amounts(self):
        """Test A2: Multiple line items with line amounts consolidate per order."""
        tbl = "test15_5_case_b_usr_t155"
        prof = _get_profile(tbl)
        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)
        kpi_map = {k["id"]: k for k in kpis}

        self.assertIn("kpi_total_revenue", kpi_map)
        self.assertIn("kpi_total_orders", kpi_map)
        self.assertIn("kpi_aov", kpi_map)
        self.assertIn("kpi_max_order", kpi_map)

        self.assertEqual(kpi_map["kpi_total_revenue"]["raw_value"], 52000.00)
        self.assertEqual(kpi_map["kpi_total_orders"]["raw_value"], 2)
        self.assertEqual(kpi_map["kpi_aov"]["raw_value"], 26000.00)
        self.assertEqual(kpi_map["kpi_max_order"]["raw_value"], 50000.00)

    def test_group_a_case_c_repeated_order_totals(self):
        """Test A3: Repeated order totals are NOT double-counted across product rows."""
        tbl = "test15_5_case_c_usr_t155"
        prof = _get_profile(tbl)
        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)
        kpi_map = {k["id"]: k for k in kpis}

        self.assertIn("kpi_total_revenue", kpi_map)
        self.assertIn("kpi_total_orders", kpi_map)
        self.assertIn("kpi_aov", kpi_map)
        self.assertIn("kpi_max_order", kpi_map)

        # Revenue must be 52000, NOT 102000!
        self.assertEqual(kpi_map["kpi_total_revenue"]["raw_value"], 52000.00)
        self.assertEqual(kpi_map["kpi_total_orders"]["raw_value"], 2)
        # AOV must be 26000, NOT 51000!
        self.assertEqual(kpi_map["kpi_aov"]["raw_value"], 26000.00)
        self.assertEqual(kpi_map["kpi_max_order"]["raw_value"], 50000.00)

    def test_group_a_case_b_equal_line_amounts_not_mistaken_for_order_totals(self):
        """Test A4: Genuinely separate equal line amounts are not misclassified as repeated totals."""
        tbl = "test15_5_equal_lines_usr_t155"
        prof = _get_profile(tbl)
        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)
        kpi_map = {k["id"]: k for k in kpis}

        self.assertIn("kpi_total_revenue", kpi_map)
        self.assertIn("kpi_total_orders", kpi_map)
        self.assertIn("kpi_aov", kpi_map)
        self.assertIn("kpi_max_order", kpi_map)

        # Revenue for O101 (25k + 25k = 50k) + O102 (2k) = 52000.00
        self.assertEqual(kpi_map["kpi_total_revenue"]["raw_value"], 52000.00)
        self.assertEqual(kpi_map["kpi_total_orders"]["raw_value"], 2)
        self.assertEqual(kpi_map["kpi_aov"]["raw_value"], 26000.00)
        self.assertEqual(kpi_map["kpi_max_order"]["raw_value"], 50000.00)

    def test_group_a_ambiguous_amount_semantics(self):
        """Test A5: Ambiguous amount granularity suppresses revenue & AOV without guessing."""
        tbl = "test15_5_ambiguous_grain_usr_t155"
        prof = _get_profile(tbl)
        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)
        kpi_map = {k["id"]: k for k in kpis}

        # Revenue and AOV must be suppressed!
        self.assertNotIn("kpi_total_revenue", kpi_map)
        self.assertNotIn("kpi_aov", kpi_map)

        # Total orders is preserved
        self.assertIn("kpi_total_orders", kpi_map)
        self.assertEqual(kpi_map["kpi_total_orders"]["raw_value"], 2)

        # Ambiguity explanation card is present
        self.assertIn("kpi_revenue_ambiguous", kpi_map)
        amb_card = kpi_map["kpi_revenue_ambiguous"]
        self.assertTrue(amb_card.get("is_ambiguous"))
        self.assertIn("ambiguous", amb_card.get("explanation", "").lower())

    # =========================================================================
    # Test Group B: Zero-Baseline & Edge Percentage Changes
    # =========================================================================
    def test_group_b_zero_to_positive(self):
        """Test B1: Previous=0, Current=10000 does NOT report 100% or infinity."""
        res = evaluate_period_change(10000.0, 0.0, "2024-02", "2024-01", "Revenue", "₹")
        self.assertIsNone(res["percentage_change"])
        self.assertIsNone(res["change_pct"])
        self.assertEqual(res["absolute_change"], 10000.0)
        self.assertIn("increased from ₹0.00 to ₹10,000.00 (baseline was zero)", res["narrative"])

    def test_group_b_zero_to_zero(self):
        """Test B2: Previous=0, Current=0 reports 0% / no change cleanly."""
        res = evaluate_period_change(0.0, 0.0, "2024-02", "2024-01", "Revenue", "₹")
        self.assertEqual(res["percentage_change"], 0.0)
        self.assertEqual(res["change_pct"], 0.0)
        self.assertEqual(res["absolute_change"], 0.0)
        self.assertIn("No change. Both periods have zero recorded revenue", res["narrative"])

    def test_group_b_positive_to_zero(self):
        """Test B3: Previous=10000, Current=0 reports -100% decrease."""
        res = evaluate_period_change(0.0, 10000.0, "2024-02", "2024-01", "Revenue", "₹")
        self.assertEqual(res["percentage_change"], -100.0)
        self.assertEqual(res["change_pct"], -100.0)
        self.assertEqual(res["absolute_change"], -10000.0)
        self.assertIn("decreased from ₹10,000.00 to ₹0.00 (-100%)", res["narrative"])

    def test_group_b_normal_growth(self):
        """Test B4: Previous=10000, Current=12000 reports +20.0%."""
        res = evaluate_period_change(12000.0, 10000.0, "2024-02", "2024-01", "Revenue", "₹")
        self.assertEqual(res["percentage_change"], 20.0)
        self.assertEqual(res["change_pct"], 20.0)
        self.assertEqual(res["absolute_change"], 2000.0)
        self.assertIn("+20.0%", res["narrative"])

    def test_group_b_normal_decline(self):
        """Test B5: Previous=12000, Current=10000 reports -16.7%."""
        res = evaluate_period_change(10000.0, 12000.0, "2024-02", "2024-01", "Revenue", "₹")
        self.assertEqual(res["percentage_change"], -16.7)
        self.assertEqual(res["change_pct"], -16.7)
        self.assertEqual(res["absolute_change"], -2000.0)
        self.assertIn("-16.7%", res["narrative"])

    def test_group_b_negative_to_positive(self):
        """Test B6: Previous=-5000, Current=10000 reports improvement without misleading percentage."""
        res = evaluate_period_change(10000.0, -5000.0, "2024-02", "2024-01", "Revenue", "₹")
        self.assertIsNone(res["percentage_change"])
        self.assertEqual(res["absolute_change"], 15000.0)
        self.assertIn("improved by +₹15,000.00", res["narrative"])

    def test_group_b_positive_to_negative(self):
        """Test B7: Previous=10000, Current=-5000 reports net drop clearly."""
        res = evaluate_period_change(-5000.0, 10000.0, "2024-02", "2024-01", "Revenue", "₹")
        self.assertEqual(res["percentage_change"], -150.0)
        self.assertEqual(res["absolute_change"], -15000.0)
        self.assertIn("-150.0%", res["narrative"])

    def test_group_b_null_previous_or_current(self):
        """Test B8: NULL previous or current period returns unavailable comparison."""
        res_prev_null = evaluate_period_change(10000.0, None, "2024-02", "2024-01", "Revenue", "₹")
        self.assertEqual(res_prev_null["status"], "unavailable")
        self.assertIsNone(res_prev_null["percentage_change"])
        self.assertIn("previous period data is missing", res_prev_null["narrative"])

        res_cur_null = evaluate_period_change(None, 10000.0, "2024-02", "2024-01", "Revenue", "₹")
        self.assertEqual(res_cur_null["status"], "unavailable")
        self.assertIsNone(res_cur_null["percentage_change"])
        self.assertIn("current period data is missing", res_cur_null["narrative"])

    # =========================================================================
    # Test Group C: Multi-Currency & Currency Semantics
    # =========================================================================
    def test_group_c_inr_only(self):
        """Test C1: Single established INR currency uses ₹ and INR code."""
        tbl = "test15_5_curr_inr_usr_t155"
        prof = _get_profile(tbl)
        details = detect_dataset_currency_details(tbl, prof)
        self.assertEqual(details["status"], "single")
        self.assertEqual(details["primary_currency"], ("₹", "INR"))

        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)
        kpi_map = {k["id"]: k for k in kpis}
        self.assertIn("kpi_total_volume", kpi_map)
        self.assertIn("₹", kpi_map["kpi_total_volume"]["value"])
        self.assertEqual(kpi_map["kpi_total_volume"]["raw_value"], 20000.00)

    def test_group_c_usd_only(self):
        """Test C2: Single established USD currency uses $ and USD code."""
        tbl = "test15_5_curr_usd_usr_t155"
        prof = _get_profile(tbl)
        details = detect_dataset_currency_details(tbl, prof)
        self.assertEqual(details["status"], "single")
        self.assertEqual(details["primary_currency"], ("$", "USD"))

        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)
        kpi_map = {k["id"]: k for k in kpis}
        self.assertIn("kpi_total_volume", kpi_map)
        self.assertIn("$", kpi_map["kpi_total_volume"]["value"])
        self.assertEqual(kpi_map["kpi_total_volume"]["raw_value"], 12000.00)

    def test_group_c_inr_and_usd_together(self):
        """Test C3: Mixed INR & USD never produces an added combined total."""
        tbl = "test15_5_curr_inr_usd_usr_t155"
        prof = _get_profile(tbl)
        details = detect_dataset_currency_details(tbl, prof)
        self.assertEqual(details["status"], "multi")
        self.assertTrue(details["is_multi_currency"])

        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)
        kpi_map = {k["id"]: k for k in kpis}

        vol_card = kpi_map.get("kpi_total_volume")
        self.assertIsNotNone(vol_card)
        self.assertTrue(vol_card.get("is_multi_currency"))
        self.assertIsNone(vol_card.get("raw_value"))

        breakdown = {b["code"]: b["amount"] for b in vol_card["currency_breakdown"]}
        self.assertEqual(breakdown.get("INR"), 15000.00)
        self.assertEqual(breakdown.get("USD"), 10000.00)

    def test_group_c_inr_usd_and_jpy_together(self):
        """Test C4: 3 distinct currencies displayed separately without combined addition."""
        tbl = "test15_5_curr_inr_usd_jpy_usr_t155"
        prof = _get_profile(tbl)
        details = detect_dataset_currency_details(tbl, prof)
        self.assertEqual(details["status"], "multi")

        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)
        kpi_map = {k["id"]: k for k in kpis}

        vol_card = kpi_map.get("kpi_total_volume")
        self.assertIsNotNone(vol_card)
        self.assertTrue(vol_card.get("is_multi_currency"))

        breakdown = {b["code"]: b["amount"] for b in vol_card["currency_breakdown"]}
        self.assertEqual(breakdown.get("INR"), 15000.00)
        self.assertEqual(breakdown.get("USD"), 10000.00)
        self.assertEqual(breakdown.get("JPY"), 5000.00)

    def test_group_c_missing_currency_suppresses_monetary_aggregation(self):
        """Test C5: Missing/NULL currency values suppress monetary aggregation with clear explanation."""
        tbl = "test15_5_curr_missing_usr_t155"
        prof = _get_profile(tbl)
        details = detect_dataset_currency_details(tbl, prof)
        self.assertEqual(details["status"], "unresolved")

        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)
        kpi_map = {k["id"]: k for k in kpis}

        self.assertNotIn("kpi_total_volume", kpi_map)
        self.assertIn("kpi_volume_unresolved", kpi_map)
        self.assertTrue(kpi_map["kpi_volume_unresolved"].get("is_ambiguous"))

    def test_group_c_unknown_currency_code_suppresses_monetary_aggregation(self):
        """Test C6: Unknown currency codes (e.g. ZZZ) suppress monetary aggregation."""
        tbl = "test15_5_curr_unknown_usr_t155"
        prof = _get_profile(tbl)
        details = detect_dataset_currency_details(tbl, prof)
        self.assertEqual(details["status"], "unresolved")

        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)
        kpi_map = {k["id"]: k for k in kpis}

        self.assertNotIn("kpi_total_volume", kpi_map)
        self.assertIn("kpi_volume_unresolved", kpi_map)

    def test_group_c_no_currency_information_displays_neutral_number(self):
        """Test C7: Unestablished currency displays neutral numbers without assuming $ or ₹."""
        tbl = "test15_5_curr_none_usr_t155"
        prof = _get_profile(tbl)
        details = detect_dataset_currency_details(tbl, prof)
        self.assertEqual(details["status"], "none")
        self.assertEqual(details["primary_currency"], ("", ""))

        dom = identify_dataset_domain(tbl, prof)
        kpis = generate_dynamic_kpis(tbl, prof, dom)
        for k in kpis:
            if "volume" in k["id"]:
                self.assertNotIn("$", k["value"])
                self.assertNotIn("₹", k["value"])


if __name__ == "__main__":
    unittest.main()
