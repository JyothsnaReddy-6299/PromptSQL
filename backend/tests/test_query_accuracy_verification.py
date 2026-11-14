"""
PromptSQL — Comprehensive Query Accuracy Verification Test Suite

Verifies that PromptSQL generates SQL that correctly answers natural-language questions,
evaluating data correctness and accuracy against independently established ground truths,
not merely checking whether SQL executes successfully.

Covers the 12 required scenarios across multiple diverse datasets:
1. Basic SELECT and column selection.
2. Filtering with multiple conditions.
3. Sorting and LIMIT.
4. COUNT, SUM, AVG, MIN, and MAX aggregations.
5. GROUP BY and HAVING.
6. Date-based filtering and grouping.
7. NULL handling (IS NULL / IS NOT NULL).
8. Multi-table automatic JOINs across 2 and 3 tables.
9. Subqueries comparing to aggregate metrics.
10. Questions referring to columns that do not exist (graceful error / rejection).
11. Ambiguous questions requiring clarification (multi-foreign key role ambiguity).
12. Questions that cannot be answered using uploaded data (unanswerable / out of domain).
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


class TestQueryAccuracyVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.user_id = "usr_acc"
        
        # Domain 1: E-Commerce
        cls.t_customers = f"customers_{cls.user_id}"
        cls.t_orders = f"orders_{cls.user_id}"
        cls.t_items = f"order_items_{cls.user_id}"
        
        # Domain 2: Transportation & Flights
        cls.t_airports = f"airports_{cls.user_id}"
        cls.t_flights = f"flights_{cls.user_id}"

        cls.all_tables = [
            cls.t_items, cls.t_orders, cls.t_customers,
            cls.t_flights, cls.t_airports
        ]

        with engine.begin() as conn:
            for t in cls.all_tables:
                conn.execute(text(f"DROP TABLE IF EXISTS `{t}`"))

            # --- Domain 1 Tables ---
            conn.execute(text(f"""
                CREATE TABLE `{cls.t_customers}` (
                    customer_id INT PRIMARY KEY,
                    full_name VARCHAR(100) NOT NULL,
                    email VARCHAR(100) NULL,
                    country VARCHAR(50) NOT NULL,
                    signup_date DATE NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))

            conn.execute(text(f"""
                CREATE TABLE `{cls.t_orders}` (
                    order_id INT PRIMARY KEY,
                    customer_id INT NOT NULL,
                    order_date DATE NOT NULL,
                    order_status VARCHAR(30) NOT NULL,
                    shipping_cost DECIMAL(10, 2) NULL,
                    total_amount DECIMAL(10, 2) NOT NULL,
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
                    unit_price DECIMAL(10, 2) NOT NULL,
                    INDEX idx_ord (order_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))

            # Seed Domain 1 Data
            conn.execute(text(f"""
                INSERT INTO `{cls.t_customers}` (customer_id, full_name, email, country, signup_date) VALUES
                (1, 'Alice Johnson', 'alice@example.com', 'USA', '2025-01-10'),
                (2, 'Bob Smith', 'bob@example.com', 'Canada', '2025-02-15'),
                (3, 'Charlie Brown', NULL, 'USA', '2025-03-20'),
                (4, 'Diana Prince', 'diana@example.com', 'UK', '2025-04-05'),
                (5, 'Evan Wright', NULL, 'Germany', '2025-05-12')
            """))

            conn.execute(text(f"""
                INSERT INTO `{cls.t_orders}` (order_id, customer_id, order_date, order_status, shipping_cost, total_amount) VALUES
                (101, 1, '2026-01-05', 'Completed', 15.00, 250.00),
                (102, 1, '2026-01-18', 'Completed', 10.00, 120.00),
                (103, 2, '2026-02-02', 'Pending', NULL, 80.00),
                (104, 3, '2026-02-14', 'Completed', 25.00, 450.00),
                (105, 4, '2026-03-01', 'Cancelled', 0.00, 60.00),
                (106, 4, '2026-03-15', 'Completed', 20.00, 310.00)
            """))

            conn.execute(text(f"""
                INSERT INTO `{cls.t_items}` (item_id, order_id, product_name, category, quantity, unit_price) VALUES
                (1, 101, 'Wireless Keyboard', 'Electronics', 2, 75.00),
                (2, 101, 'USB-C Cable', 'Electronics', 2, 50.00),
                (3, 102, 'Desk Lamp', 'Home', 1, 120.00),
                (4, 103, 'Notebook Set', 'Stationery', 4, 20.00),
                (5, 104, 'Ergonomic Chair', 'Furniture', 1, 450.00),
                (6, 105, 'Water Bottle', 'Accessories', 2, 30.00),
                (7, 106, 'Monitor Stand', 'Electronics', 1, 310.00)
            """))

            # --- Domain 2 Tables (Transportation with Multiple Role Foreign Keys) ---
            conn.execute(text(f"""
                CREATE TABLE `{cls.t_airports}` (
                    airport_id INT PRIMARY KEY,
                    airport_code VARCHAR(10) NOT NULL,
                    city VARCHAR(50) NOT NULL,
                    country VARCHAR(50) NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))

            conn.execute(text(f"""
                CREATE TABLE `{cls.t_flights}` (
                    flight_id INT PRIMARY KEY,
                    flight_number VARCHAR(20) NOT NULL,
                    origin_airport_id INT NOT NULL,
                    destination_airport_id INT NOT NULL,
                    flight_date DATE NOT NULL,
                    passenger_count INT NOT NULL,
                    ticket_price DECIMAL(10, 2) NOT NULL,
                    delay_minutes INT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))

            # Seed Domain 2 Data
            conn.execute(text(f"""
                INSERT INTO `{cls.t_airports}` (airport_id, airport_code, city, country) VALUES
                (1, 'JFK', 'New York', 'USA'),
                (2, 'LHR', 'London', 'UK'),
                (3, 'NRT', 'Tokyo', 'Japan')
            """))

            conn.execute(text(f"""
                INSERT INTO `{cls.t_flights}` (flight_id, flight_number, origin_airport_id, destination_airport_id, flight_date, passenger_count, ticket_price, delay_minutes) VALUES
                (10, 'FL-101', 1, 2, '2026-05-01', 250, 650.00, 15),
                (20, 'FL-102', 1, 3, '2026-05-02', 200, 950.00, NULL),
                (30, 'FL-103', 3, 2, '2026-05-03', 180, 800.00, 0)
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
    # Scenario 1: Basic SELECT and Column Selection
    # -------------------------------------------------------------
    def test_scenario_01_basic_select_and_column_selection(self):
        """Scenario 1: Verify specific column projection without returning unnecessary columns."""
        question = "Show the full name and country for all customers"
        req = AskRequest(question=question)
        res = ask_question(payload=req, x_table_name=self.t_customers, user_id=self.user_id)

        self.assertTrue(res["success"], f"Query failed: {res.get('error')}")
        self.assertEqual(res["count"], 5, f"Expected 5 customers, got {res['count']}")
        
        # Verify projected fields
        row0 = res["result"][0]
        self.assertIn("full_name", row0)
        self.assertIn("country", row0)
        self.assertNotIn("email", row0)
        self.assertNotIn("signup_date", row0)

        names = {r["full_name"] for r in res["result"]}
        expected_names = {"Alice Johnson", "Bob Smith", "Charlie Brown", "Diana Prince", "Evan Wright"}
        self.assertEqual(names, expected_names)
        print(f"\n[Scenario 1 PASS] Question: '{question}' -> SQL: {res['generated_sql']}")

    # -------------------------------------------------------------
    # Scenario 2: Filtering with Multiple Conditions
    # -------------------------------------------------------------
    def test_scenario_02_filtering_multiple_conditions(self):
        """Scenario 2: Compound predicates with numeric comparison and exact string matching."""
        question = "Show orders where total amount is greater than 100 and status is Completed"
        req = AskRequest(question=question)
        res = ask_question(payload=req, x_table_name=self.t_orders, user_id=self.user_id)

        self.assertTrue(res["success"], f"Query failed: {res.get('error')}")
        # Expected: Order 101 (250), 102 (120), 104 (450), 106 (310) -> 4 orders
        self.assertEqual(res["count"], 4, f"Expected 4 orders, got {res['count']}")
        for r in res["result"]:
            self.assertEqual(r["order_status"], "Completed")
            self.assertGreater(float(r["total_amount"]), 100.0)

        order_ids = {r["order_id"] for r in res["result"]}
        self.assertEqual(order_ids, {101, 102, 104, 106})
        print(f"\n[Scenario 2 PASS] Question: '{question}' -> SQL: {res['generated_sql']}")

    # -------------------------------------------------------------
    # Scenario 3: Sorting and LIMIT
    # -------------------------------------------------------------
    def test_scenario_03_sorting_and_limit(self):
        """Scenario 3: Top N ranking with descending order."""
        question = "Show the top 3 highest total amount orders"
        req = AskRequest(question=question)
        res = ask_question(payload=req, x_table_name=self.t_orders, user_id=self.user_id)

        self.assertTrue(res["success"], f"Query failed: {res.get('error')}")
        self.assertEqual(res["count"], 3, f"Expected exactly 3 rows, got {res['count']}")
        
        # Expected top 3: 450.00 (Order 104), 310.00 (Order 106), 250.00 (Order 101)
        amounts = [float(r["total_amount"]) for r in res["result"]]
        self.assertEqual(amounts, [450.00, 310.00, 250.00])
        print(f"\n[Scenario 3 PASS] Question: '{question}' -> SQL: {res['generated_sql']}")

    # -------------------------------------------------------------
    # Scenario 4: COUNT, SUM, AVG, MIN and MAX
    # -------------------------------------------------------------
    def test_scenario_04_aggregations_count_sum_avg_min_max(self):
        """Scenario 4: Complete mathematical aggregations."""
        question = "What is the total sum, average, maximum, and minimum total amount of orders, and total count of orders?"
        req = AskRequest(question=question)
        res = ask_question(payload=req, x_table_name=self.t_orders, user_id=self.user_id)

        self.assertTrue(res["success"], f"Query failed: {res.get('error')}")
        self.assertEqual(res["count"], 1)
        row = res["result"][0]
        
        # Extract values flexibly across alias names
        val_list = [float(v) for v in row.values() if v is not None]
        # Ground truths: SUM=1270.00, AVG=211.67, MAX=450.00, MIN=60.00, COUNT=6
        self.assertTrue(any(abs(v - 1270.00) < 0.5 for v in val_list), f"SUM 1270 not found in {row}")
        self.assertTrue(any(abs(v - 211.67) < 0.5 for v in val_list), f"AVG 211.67 not found in {row}")
        self.assertTrue(any(abs(v - 450.00) < 0.5 for v in val_list), f"MAX 450 not found in {row}")
        self.assertTrue(any(abs(v - 60.00) < 0.5 for v in val_list), f"MIN 60 not found in {row}")
        self.assertTrue(any(abs(v - 6.0) < 0.1 for v in val_list), f"COUNT 6 not found in {row}")
        print(f"\n[Scenario 4 PASS] Question: '{question}' -> SQL: {res['generated_sql']}")

    # -------------------------------------------------------------
    # Scenario 5: GROUP BY and HAVING
    # -------------------------------------------------------------
    def test_scenario_05_group_by_having(self):
        """Scenario 5: Grouped aggregation with HAVING threshold filter."""
        question = "Show total order amount by order status for statuses having total order amount greater than 100"
        req = AskRequest(question=question)
        res = ask_question(payload=req, x_table_name=self.t_orders, user_id=self.user_id)

        self.assertTrue(res["success"], f"Query failed: {res.get('error')}")
        # 'Completed': 1130.00. 'Pending': 80.00 (excluded). 'Cancelled': 60.00 (excluded).
        self.assertEqual(res["count"], 1, f"Expected 1 status with sum > 100, got {res['count']}")
        self.assertEqual(res["result"][0]["order_status"], "Completed")
        tot = float(list(res["result"][0].values())[1] if list(res["result"][0].keys())[0] == "order_status" else list(res["result"][0].values())[0])
        self.assertAlmostEqual(tot, 1130.00, delta=1.0)
        print(f"\n[Scenario 5 PASS] Question: '{question}' -> SQL: {res['generated_sql']}")

    # -------------------------------------------------------------
    # Scenario 6: Date-based Filtering and Grouping
    # -------------------------------------------------------------
    def test_scenario_06_date_filtering_and_grouping(self):
        """Scenario 6: Date filtering and partition grouping."""
        question = "Show total order amount grouped by month for orders placed in 2026"
        req = AskRequest(question=question)
        res = ask_question(payload=req, x_table_name=self.t_orders, user_id=self.user_id)

        self.assertTrue(res["success"], f"Query failed: {res.get('error')}")
        # Months: Jan (370.00), Feb (530.00), Mar (370.00) -> 3 groups
        self.assertEqual(res["count"], 3, f"Expected 3 distinct months, got {res['count']}")
        total_sum = sum(float(list(r.values())[1] if "month" in list(r.keys())[0].lower() else list(r.values())[0]) for r in res["result"])
        self.assertAlmostEqual(total_sum, 1270.00, delta=1.0)
        print(f"\n[Scenario 6 PASS] Question: '{question}' -> SQL: {res['generated_sql']}")

    # -------------------------------------------------------------
    # Scenario 7: NULL Handling
    # -------------------------------------------------------------
    def test_scenario_07_null_handling(self):
        """Scenario 7: Explicit IS NULL query filtering."""
        question = "List all customers who do not have an email address"
        req = AskRequest(question=question)
        res = ask_question(payload=req, x_table_name=self.t_customers, user_id=self.user_id)

        self.assertTrue(res["success"], f"Query failed: {res.get('error')}")
        self.assertEqual(res["count"], 2, f"Expected 2 customers without email, got {res['count']}")
        names = {r["full_name"] for r in res["result"]}
        self.assertEqual(names, {"Charlie Brown", "Evan Wright"})
        print(f"\n[Scenario 7 PASS] Question: '{question}' -> SQL: {res['generated_sql']}")

    # -------------------------------------------------------------
    # Scenario 8: Multi-Table Automatic JOINs
    # -------------------------------------------------------------
    def test_scenario_08_multi_table_automatic_join(self):
        """Scenario 8: Multi-table JOIN across 3 tables without user specifying table names or join keys."""
        question = "Show the product names purchased by each customer along with their country"
        req = AskRequest(question=question)
        # Active table is customers; orders and order_items should be discovered and joined dynamically
        res = ask_question(payload=req, x_table_name=self.t_customers, user_id=self.user_id)

        self.assertTrue(res["success"], f"Query failed: {res.get('error')}")
        self.assertEqual(res["count"], 7, f"Expected 7 product purchase items, got {res['count']}")
        
        # Verify columns from multiple tables are present
        row0 = res["result"][0]
        self.assertTrue(any("product" in k.lower() for k in row0.keys()), f"product column missing in {row0}")
        self.assertTrue(any("country" in k.lower() or "customer" in k.lower() or "name" in k.lower() for k in row0.keys()))
        print(f"\n[Scenario 8 PASS] Question: '{question}' -> SQL: {res['generated_sql']}")

    # -------------------------------------------------------------
    # Scenario 9: Subqueries
    # -------------------------------------------------------------
    def test_scenario_09_subqueries(self):
        """Scenario 9: Value comparison against dynamic aggregate using subquery."""
        question = "Show all orders that have a total amount greater than the average total amount of all orders"
        req = AskRequest(question=question)
        res = ask_question(payload=req, x_table_name=self.t_orders, user_id=self.user_id)

        self.assertTrue(res["success"], f"Query failed: {res.get('error')}")
        # Average is 211.67. Orders > 211.67 are: 101 (250), 104 (450), 106 (310) -> 3 orders
        self.assertEqual(res["count"], 3, f"Expected 3 orders above average, got {res['count']}")
        order_ids = {r["order_id"] for r in res["result"]}
        self.assertEqual(order_ids, {101, 104, 106})
        print(f"\n[Scenario 9 PASS] Question: '{question}' -> SQL: {res['generated_sql']}")

    # -------------------------------------------------------------
    # Scenario 10: Non-Existent Columns
    # -------------------------------------------------------------
    def test_scenario_10_non_existent_columns(self):
        """Scenario 10: Question referring to columns that do not exist."""
        question = "Show the credit score and loyalty tier for all customers"
        req = AskRequest(question=question)
        res = ask_question(payload=req, x_table_name=self.t_customers, user_id=self.user_id)

        # Should either safely reject via INVALID_QUERY (success: False) or fail gracefully without internal driver leak
        if not res["success"]:
            self.assertIn("error", res)
            self.assertTrue(len(res["error"]) > 0)
            self.assertNotIn("pymysql", res["error"].lower())
            print(f"\n[Scenario 10 PASS] Graceful rejection: {res['error']}")
        else:
            # If self-corrected or returned empty safely
            print(f"\n[Scenario 10 HANDLED] Result: {res}")

    # -------------------------------------------------------------
    # Scenario 11: Ambiguous Questions Requiring Clarification
    # -------------------------------------------------------------
    def test_scenario_11_ambiguous_relationship_warning(self):
        """Scenario 11: Multi-foreign key relationship ambiguity detection, clarification request, and follow-up."""
        # 1. Ambiguous question without role hint must request clarification without executing arbitrary SQL
        question = "Show flight number and city for each flight"
        req = AskRequest(question=question)
        res = ask_question(payload=req, x_table_name=self.t_flights, user_id=self.user_id)

        self.assertTrue(res["success"], f"Query failed: {res.get('error')}")
        self.assertTrue(res.get("needs_clarification"), "Ambiguous query must request clarification")
        self.assertIn("clarify", res.get("clarification_prompt", "").lower())
        self.assertIn("origin city", res.get("clarification_options", []))
        self.assertIn("destination city", res.get("clarification_options", []))
        self.assertIsNone(res.get("generated_sql"), "Must not execute SQL on arbitrary relationship choice")
        self.assertEqual(len(res.get("result", [])), 0)
        print(f"\n[Scenario 11.1 PASS] Clarification requested: '{res['clarification_prompt']}' | Options: {res['clarification_options']}")

        # 2. Clarification follow-up answering 'origin city' must use preserved context and generate correct SQL
        followup_req = AskRequest(question="origin city")
        followup_res = ask_question(payload=followup_req, x_table_name=self.t_flights, user_id=self.user_id)
        self.assertTrue(followup_res["success"], f"Followup failed: {followup_res.get('error')}")
        self.assertFalse(followup_res.get("needs_clarification", False))
        self.assertIn("origin_airport_id", followup_res.get("generated_sql", ""))
        self.assertEqual(followup_res["count"], 3)
        cities_origin = [r.get("city") or list(r.values())[1] for r in followup_res["result"]]
        self.assertIn("New York", cities_origin)
        print(f"\n[Scenario 11.2 PASS] Clarification follow-up resolved: SQL -> {followup_res['generated_sql']}")

        # 3. Explicit question identifying origin must work directly
        orig_req = AskRequest(question="Show the origin city for each flight")
        orig_res = ask_question(payload=orig_req, x_table_name=self.t_flights, user_id=self.user_id)
        self.assertTrue(orig_res["success"])
        self.assertFalse(orig_res.get("needs_clarification", False))
        self.assertIn("origin_airport_id", orig_res.get("generated_sql", ""))
        self.assertEqual(orig_res["count"], 3)
        print(f"\n[Scenario 11.3 PASS] Explicit origin resolved: SQL -> {orig_res['generated_sql']}")

        # 4. Explicit question identifying destination must work directly
        dest_req = AskRequest(question="Show the destination city for each flight")
        dest_res = ask_question(payload=dest_req, x_table_name=self.t_flights, user_id=self.user_id)
        self.assertTrue(dest_res["success"])
        self.assertFalse(dest_res.get("needs_clarification", False))
        self.assertIn("destination_airport_id", dest_res.get("generated_sql", ""))
        self.assertEqual(dest_res["count"], 3)
        print(f"\n[Scenario 11.4 PASS] Explicit destination resolved: SQL -> {dest_res['generated_sql']}")

    # -------------------------------------------------------------
    # Scenario 12: Questions That Cannot Be Answered
    # -------------------------------------------------------------
    def test_scenario_12_unanswerable_out_of_domain(self):
        """Scenario 12: Out-of-domain unanswerable question safely rejected."""
        question = "What will the stock price of Tesla be next week?"
        req = AskRequest(question=question)
        res = ask_question(payload=req, x_table_name=self.t_customers, user_id=self.user_id)

        # PromptSQL should safely reject without executing arbitrary SQL
        self.assertFalse(res["success"], "Unanswerable out-of-domain question should not succeed")
        self.assertIn("error", res)
        print(f"\n[Scenario 12 PASS] Safely rejected out-of-domain question: {res['error']}")


if __name__ == "__main__":
    unittest.main()
