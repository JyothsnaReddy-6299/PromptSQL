"""
Step 5.5: Query Accuracy and Dataset Generalization Test Suite

Validates that PromptSQL reliably understands natural-language questions,
generates accurate SQL, and computes correct answers across 5 independent,
diverse datasets without relying on hardcoded table/column names or test-specific assumptions.

Datasets tested:
1. Sales & Revenue (sales_revenue)
2. Customers & Orders (orders, clients)
3. Employees & Departments (staff, departments)
4. Products & Inventory (warehouse_stock)
5. IoT Telemetry with Unfamiliar Schema (sensor_readings, telemetry_nodes)
"""

import unittest
import json
from decimal import Decimal
from sqlalchemy import text
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import engine
from app.services.auth_service import get_current_user_id
from app.routes.ask import ask_question, AskRequest


class TestDatasetGeneralization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.user_id = "usr_step55"
        cls.d1_sales = f"sales_revenue_{cls.user_id}"
        cls.d2_orders = f"orders_{cls.user_id}"
        cls.d2_clients = f"clients_{cls.user_id}"
        cls.d3_staff = f"staff_{cls.user_id}"
        cls.d3_depts = f"departments_{cls.user_id}"
        cls.d4_stock = f"warehouse_stock_{cls.user_id}"
        cls.d5_readings = f"sensor_readings_{cls.user_id}"
        cls.d5_nodes = f"telemetry_nodes_{cls.user_id}"

        cls.all_tables = [
            cls.d1_sales, cls.d2_orders, cls.d2_clients,
            cls.d3_staff, cls.d3_depts, cls.d4_stock,
            cls.d5_readings, cls.d5_nodes
        ]

        with engine.begin() as conn:
            for t in cls.all_tables:
                conn.execute(text(f"DROP TABLE IF EXISTS `{t}`"))

            # Dataset 1: Sales & Revenue
            conn.execute(text(f"""
                CREATE TABLE `{cls.d1_sales}` (
                    order_id INT PRIMARY KEY,
                    region VARCHAR(50),
                    payment_method VARCHAR(50),
                    gross_revenue DECIMAL(12, 2),
                    discount_amount DECIMAL(10, 2),
                    net_revenue DECIMAL(12, 2),
                    order_date DATE,
                    is_refunded BOOLEAN
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.d1_sales}` VALUES
                (101, 'North', 'Credit Card', 1200.00, 100.00, 1100.00, '2026-01-15', 0),
                (102, 'South', 'PayPal', 450.00, 0.00, 450.00, '2026-01-16', 0),
                (103, 'East', 'Credit Card', 890.00, 50.00, 840.00, '2026-01-18', 0),
                (104, 'North', 'Wire Transfer', 3500.00, 200.00, 3300.00, '2026-01-20', 0),
                (105, 'West', 'Credit Card', 600.00, 0.00, 600.00, '2026-01-22', 1),
                (106, 'South', 'Credit Card', 1500.00, 150.00, 1350.00, '2026-01-25', 0)
            """))

            # Dataset 2: Customers & Orders
            conn.execute(text(f"""
                CREATE TABLE `{cls.d2_clients}` (
                    client_id INT PRIMARY KEY,
                    client_name VARCHAR(100),
                    membership_tier VARCHAR(50),
                    credit_limit DECIMAL(10, 2),
                    country VARCHAR(50)
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.d2_clients}` VALUES
                (1, 'Acme Corp', 'Platinum', 50000.00, 'USA'),
                (2, 'Globex Ltd', 'Gold', 25000.00, 'UK'),
                (3, 'Initech LLC', 'Silver', 10000.00, 'Canada'),
                (4, 'Soylent Inc', 'Bronze', 5000.00, 'USA')
            """))

            conn.execute(text(f"""
                CREATE TABLE `{cls.d2_orders}` (
                    order_number INT PRIMARY KEY,
                    client_id INT,
                    order_status VARCHAR(50),
                    total_price DECIMAL(10, 2),
                    delivery_days INT
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.d2_orders}` VALUES
                (5001, 1, 'DELIVERED', 4500.00, 3),
                (5002, 1, 'PROCESSING', 12000.00, 7),
                (5003, 2, 'DELIVERED', 3200.00, 4),
                (5004, 3, 'CANCELLED', 850.00, 2),
                (5005, 2, 'DELIVERED', 6100.00, 5)
            """))

            # Dataset 3: Employees & Departments
            conn.execute(text(f"""
                CREATE TABLE `{cls.d3_depts}` (
                    dept_id INT PRIMARY KEY,
                    dept_name VARCHAR(100),
                    building_code VARCHAR(20),
                    annual_budget DECIMAL(15, 2)
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.d3_depts}` VALUES
                (10, 'Engineering', 'BLD-A', 1500000.00),
                (20, 'Marketing', 'BLD-B', 800000.00),
                (30, 'Finance', 'BLD-A', 600000.00)
            """))

            conn.execute(text(f"""
                CREATE TABLE `{cls.d3_staff}` (
                    emp_id INT PRIMARY KEY,
                    dept_id INT,
                    first_name VARCHAR(50),
                    last_name VARCHAR(50),
                    job_title VARCHAR(100),
                    salary DECIMAL(10, 2),
                    commission_rate DECIMAL(5, 2),
                    hire_date DATE
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.d3_staff}` VALUES
                (1001, 10, 'David', 'Miller', 'Senior Engineer', 120000.00, NULL, '2020-03-01'),
                (1002, 10, 'Elena', 'Rostova', 'Software Developer', 95000.00, NULL, '2021-06-15'),
                (1003, 20, 'Marcus', 'Vance', 'Marketing Director', 110000.00, 0.15, '2019-11-10'),
                (1004, 20, 'Chloe', 'Bennett', 'Content Specialist', 65000.00, 0.05, '2022-01-20'),
                (1005, 30, 'Franklin', 'Torres', 'Lead Accountant', 90000.00, NULL, '2018-08-05')
            """))

            # Dataset 4: Products & Inventory
            conn.execute(text(f"""
                CREATE TABLE `{cls.d4_stock}` (
                    sku INT PRIMARY KEY,
                    product_name VARCHAR(100),
                    category VARCHAR(50),
                    unit_cost DECIMAL(10, 2),
                    units_on_hand INT,
                    reorder_threshold INT,
                    supplier_rating DECIMAL(3, 1)
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.d4_stock}` VALUES
                (201, 'Industrial Sensor X1', 'Hardware', 45.00, 15, 20, 4.8),
                (202, 'Optical Fiber Cable 10m', 'Networking', 12.50, 120, 50, 4.5),
                (203, 'Thermal Shield Panel', 'Materials', 85.00, 8, 10, 4.9),
                (204, 'Hydraulic Valve V2', 'Hardware', 62.00, 30, 25, 4.2),
                (205, 'Copper Conduit 5m', 'Materials', 22.00, 5, 15, 3.9)
            """))

            # Dataset 5: IoT Sensor Telemetry (Unfamiliar Schema Domain)
            conn.execute(text(f"""
                CREATE TABLE `{cls.d5_nodes}` (
                    node_id INT PRIMARY KEY,
                    firmware_version VARCHAR(20),
                    deployment_zone VARCHAR(50),
                    is_active BOOLEAN
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.d5_nodes}` VALUES
                (901, 'v2.4.1', 'Sector-Alpha', 1),
                (902, 'v2.4.1', 'Sector-Beta', 1),
                (903, 'v1.9.0', 'Sector-Gamma', 0)
            """))

            conn.execute(text(f"""
                CREATE TABLE `{cls.d5_readings}` (
                    reading_id INT PRIMARY KEY,
                    node_id INT,
                    temp_celsius DECIMAL(6, 2),
                    humidity_pct DECIMAL(5, 2),
                    battery_millivolts INT,
                    packet_error_rate DECIMAL(6, 4),
                    signal_rssi_dbm INT
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.d5_readings}` VALUES
                (8001, 901, 22.50, 45.20, 3280, 0.0012, -68),
                (8002, 901, 23.10, 44.80, 3260, 0.0015, -70),
                (8003, 902, 28.40, 62.10, 3190, 0.0045, -82),
                (8004, 902, 29.00, 63.50, 3175, 0.0050, -85),
                (8005, 903, 18.20, 38.00, 3020, 0.0210, -94)
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
    # Dataset 1: Sales & Revenue
    # -------------------------------------------------------------
    def test_d1_01_filter_and_sort(self):
        """D1-01: Filter unrefunded sales and order by net revenue desc."""
        req = AskRequest(question="Show unrefunded sales orders ordered by net revenue descending")
        res = ask_question(payload=req, x_table_name=self.d1_sales, user_id=self.user_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 5)
        self.assertEqual(float(res["result"][0]["net_revenue"]), 3300.00)
        self.assertEqual(float(res["result"][-1]["net_revenue"]), 450.00)

    def test_d1_02_aggregations_sum_avg_count(self):
        """D1-02: Aggregations SUM, AVG, and COUNT on sales revenue."""
        req = AskRequest(question="What is the total gross revenue, average discount amount, and total count of orders?")
        res = ask_question(payload=req, x_table_name=self.d1_sales, user_id=self.user_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 1)
        # Sum of gross revenues: 1200+450+890+3500+600+1500 = 8140
        gross_sum = float(res["result"][0].get("total_gross_revenue") or list(res["result"][0].values())[0])
        self.assertAlmostEqual(gross_sum, 8140.00, delta=1.0)

    def test_d1_03_group_by_having(self):
        """D1-03: GROUP BY region with HAVING clause on net revenue."""
        req = AskRequest(question="Show total net revenue by region for regions with total net revenue greater than 1000")
        res = ask_question(payload=req, x_table_name=self.d1_sales, user_id=self.user_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 2)
        regions = {r["region"] for r in res["result"]}
        self.assertEqual(regions, {"North", "South"})

    # -------------------------------------------------------------
    # Dataset 2: Customers & Orders
    # -------------------------------------------------------------
    def test_d2_01_multi_table_join(self):
        """D2-01: Multi-table JOIN between orders and clients on client_id."""
        req = AskRequest(question="Show client name, country, and total price of their delivered orders")
        res = ask_question(payload=req, x_table_name=self.d2_orders, user_id=self.user_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 3)
        for r in res["result"]:
            self.assertTrue("client_name" in r or "name" in r or "country" in r)

    def test_d2_02_semantic_paraphrasing(self):
        """D2-02: Semantic paraphrases produce equivalent analytical results."""
        req_a = AskRequest(question="Which client spent the most on a single order?")
        res_a = ask_question(payload=req_a, x_table_name=self.d2_orders, user_id=self.user_id)
        self.assertTrue(res_a["success"])
        self.assertIn("Acme Corp", json.dumps(res_a["result"]))

        req_b = AskRequest(question="Show the client name and total price for the highest value order")
        res_b = ask_question(payload=req_b, x_table_name=self.d2_orders, user_id=self.user_id)
        self.assertTrue(res_b["success"])
        self.assertIn("Acme Corp", json.dumps(res_b["result"]))

    def test_d2_03_subquery_comparison(self):
        """D2-03: Subquery comparing orders against overall average price."""
        req = AskRequest(question="List orders that have a total price higher than the average order price")
        res = ask_question(payload=req, x_table_name=self.d2_orders, user_id=self.user_id)
        self.assertTrue(res["success"])
        # Overall average is 5330.00; orders > 5330 are 5002 ($12000) and 5005 ($6100)
        self.assertEqual(res["count"], 2)

    # -------------------------------------------------------------
    # Dataset 3: Employees & Departments
    # -------------------------------------------------------------
    def test_d3_01_multi_table_join_avg(self):
        """D3-01: Multi-table JOIN with department grouping and average salary."""
        req = AskRequest(question="Show each department name and the average employee salary")
        res = ask_question(payload=req, x_table_name=self.d3_staff, user_id=self.user_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 3)

    def test_d3_02_null_values_handling(self):
        """D3-02: Correct handling of NULL commission rates via IS NULL."""
        req = AskRequest(question="List staff members who do not have a commission rate")
        res = ask_question(payload=req, x_table_name=self.d3_staff, user_id=self.user_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 3)
        emp_ids = {r["emp_id"] for r in res["result"] if "emp_id" in r}
        self.assertEqual(emp_ids, {1001, 1002, 1005})

    def test_d3_03_null_exclusion_filter(self):
        """D3-03: Filter condition properly excludes NULLs and returns matching rows."""
        req = AskRequest(question="Show staff members with a commission rate greater than 0.10")
        res = ask_question(payload=req, x_table_name=self.d3_staff, user_id=self.user_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["result"][0].get("first_name"), "Marcus")

    # -------------------------------------------------------------
    # Dataset 4: Products & Inventory
    # -------------------------------------------------------------
    def test_d4_01_business_intent_paraphrase(self):
        """D4-01: Business intent ('need to be reordered') correctly maps to threshold condition."""
        req_a = AskRequest(question="Which products need to be reordered?")
        res_a = ask_question(payload=req_a, x_table_name=self.d4_stock, user_id=self.user_id)
        self.assertTrue(res_a["success"])
        self.assertEqual(res_a["count"], 3)
        skus_a = {r["sku"] for r in res_a["result"] if "sku" in r}
        self.assertEqual(skus_a, {201, 203, 205})

        req_b = AskRequest(question="Show products where units on hand is less than or equal to reorder threshold")
        res_b = ask_question(payload=req_b, x_table_name=self.d4_stock, user_id=self.user_id)
        self.assertTrue(res_b["success"])
        self.assertEqual(res_b["count"], 3)
        skus_b = {r["sku"] for r in res_b["result"] if "sku" in r}
        self.assertEqual(skus_b, {201, 203, 205})

    def test_d4_02_calculated_columns(self):
        """D4-02: Computed inventory value (cost * quantity) across inventory."""
        req = AskRequest(question="Show product name, category, and total inventory value for each product")
        res = ask_question(payload=req, x_table_name=self.d4_stock, user_id=self.user_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 5)

    def test_d4_03_top_n_by_attribute(self):
        """D4-03: Top 1 product by supplier rating."""
        req = AskRequest(question="Show the top product by supplier rating")
        res = ask_question(payload=req, x_table_name=self.d4_stock, user_id=self.user_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 1)
        self.assertIn("Thermal Shield", json.dumps(res["result"][0]))

    # -------------------------------------------------------------
    # Dataset 5: IoT Telemetry (Unfamiliar Schema Domain)
    # -------------------------------------------------------------
    def test_d5_01_unfamiliar_column_filtering(self):
        """D5-01: Correctly filters domain-specific columns (battery_millivolts < 3200)."""
        req = AskRequest(question="Show sensor readings where battery millivolts is below 3200")
        res = ask_question(payload=req, x_table_name=self.d5_readings, user_id=self.user_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 3)
        reading_ids = {r["reading_id"] for r in res["result"] if "reading_id" in r}
        self.assertEqual(reading_ids, {8003, 8004, 8005})

    def test_d5_02_unfamiliar_domain_join(self):
        """D5-02: Multi-table JOIN on unfamiliar telemetry entities with boolean condition."""
        req = AskRequest(question="Show deployment zone, firmware version, and temperature for readings from active nodes")
        res = ask_question(payload=req, x_table_name=self.d5_readings, user_id=self.user_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 4)
        for r in res["result"]:
            self.assertTrue("deployment_zone" in r or "firmware_version" in r or "temp_celsius" in r)

    def test_d5_03_telemetry_aggregations(self):
        """D5-03: Aggregates across unusual technical column names."""
        req = AskRequest(question="What is the maximum packet error rate and minimum signal rssi dbm?")
        res = ask_question(payload=req, x_table_name=self.d5_readings, user_id=self.user_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 1)

    # -------------------------------------------------------------
    # Hallucination Defense & Edge Cases
    # -------------------------------------------------------------
    def test_edge_01_nonexistent_columns_rejected(self):
        """Edge-01: Questions referring to nonexistent columns fail closed without hallucinating."""
        req = AskRequest(question="Show the spacecraft orbital velocity and lunar landing coordinates")
        res = ask_question(payload=req, x_table_name=self.d1_sales, user_id=self.user_id)
        self.assertFalse(res["success"])
        self.assertIn("error", res)

    def test_edge_02_empty_result_set(self):
        """Edge-02: Valid query yielding no matching records returns count 0 and clear message."""
        req = AskRequest(question="Show staff hired in the year 1990")
        res = ask_question(payload=req, x_table_name=self.d3_staff, user_id=self.user_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 0)
        self.assertEqual(res["result"], [])
        self.assertIsNotNone(res["summary"])


if __name__ == "__main__":
    unittest.main()
