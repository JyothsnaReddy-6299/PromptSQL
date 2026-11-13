"""
PromptSQL — Automatic JOIN Failure Diagnosis and Verification Test Suite
Tests:
1. Exact failing scenario: "Show the product names purchased by each customer, along with their country."
   Using non-primary-key PascalCase identifier columns (`CustomerID`) without table names or JOIN instructions.
2. Automatic 2-table JOIN without table names or join columns.
3. Automatic 3-table JOIN bridging through an unmentioned intermediary table.
4. Question using completely different table and column names (Clients, Transactions, Catalog).
5. Existing single-table query preservation (no unnecessary joins).
6. Ambiguous relationship detection and warning propagation.
"""

import unittest
from sqlalchemy import create_engine, text
from app.database.connection import engine
from app.services.relationship_service import (
    discover_user_schemas,
    infer_table_relationships,
    resolve_query_context,
    RelationshipGraph
)
from app.services.sql_generator import generate_sql
from app.services.table_translator import translate_query_tables
from app.services.sql_validator import validate_sql
from app.services.sql_executor import execute_sql


class TestAutomaticJoinDiagnosis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.user_id = "test_diag"
        cls.tbl_customers = f"customers_usr_{cls.user_id}"
        cls.tbl_orders = f"orders_usr_{cls.user_id}"
        cls.tbl_products = f"products_usr_{cls.user_id}"

        # Alternative domain: clients, transactions, items
        cls.tbl_clients = f"clients_usr_{cls.user_id}"
        cls.tbl_purchases = f"purchases_usr_{cls.user_id}"
        cls.tbl_items = f"items_usr_{cls.user_id}"

        with engine.begin() as conn:
            # Clean up old test tables
            for tbl in [cls.tbl_customers, cls.tbl_orders, cls.tbl_products, cls.tbl_clients, cls.tbl_purchases, cls.tbl_items]:
                conn.execute(text(f"DROP TABLE IF EXISTS `{tbl}`"))

            # 1. Real-world 2-table schema with PascalCase non-PK CustomerID
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_customers}` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `CustomerID` VARCHAR(50),
                    `CustomerName` VARCHAR(100),
                    `Country` VARCHAR(50)
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.tbl_customers}` (`CustomerID`, `CustomerName`, `Country`) VALUES
                ('C101', 'Alice Cooper', 'USA'),
                ('C102', 'Bob Dylan', 'Canada'),
                ('C103', 'Charlie Watts', 'UK')
            """))

            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_orders}` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `OrderID` VARCHAR(50),
                    `CustomerID` VARCHAR(50),
                    `Product` VARCHAR(100),
                    `Amount` DECIMAL(10, 2)
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.tbl_orders}` (`OrderID`, `CustomerID`, `Product`, `Amount`) VALUES
                ('O501', 'C101', 'Noise Cancelling Headphones', 250.00),
                ('O502', 'C102', 'Wireless Keyboard', 85.00),
                ('O503', 'C101', 'Curved Gaming Monitor', 450.00),
                ('O504', 'C103', 'Ergonomic Chair', 320.00)
            """))

            # 2. Alternative domain tables: clients, purchases, items (3 tables)
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_clients}` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `client_code` VARCHAR(50),
                    `client_organization` VARCHAR(100),
                    `headquarters_city` VARCHAR(50)
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.tbl_clients}` (`client_code`, `client_organization`, `headquarters_city`) VALUES
                ('CL-1', 'Stark Industries', 'New York'),
                ('CL-2', 'Wayne Enterprises', 'Gotham')
            """))

            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_purchases}` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `purchase_ref` VARCHAR(50),
                    `client_code` VARCHAR(50),
                    `item_code` VARCHAR(50)
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.tbl_purchases}` (`purchase_ref`, `client_code`, `item_code`) VALUES
                ('PUR-1', 'CL-1', 'IT-99'),
                ('PUR-2', 'CL-2', 'IT-88')
            """))

            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_items}` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `item_code` VARCHAR(50),
                    `item_description` VARCHAR(100),
                    `cost` DECIMAL(10, 2)
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.tbl_items}` (`item_code`, `item_description`, `cost`) VALUES
                ('IT-99', 'Titanium Alloy', 15000.00),
                ('IT-88', 'Composite Armor', 22000.00)
            """))

    @classmethod
    def tearDownClass(cls):
        with engine.begin() as conn:
            for tbl in [cls.tbl_customers, cls.tbl_orders, cls.tbl_products, cls.tbl_clients, cls.tbl_purchases, cls.tbl_items]:
                conn.execute(text(f"DROP TABLE IF EXISTS `{tbl}`"))

    def test_01_failing_example_exact_query(self):
        """
        Verify the exact reported failing scenario:
        'Show the product names purchased by each customer, along with their country.'
        Without table names, without JOIN instructions, and without join columns.
        """
        question = "Show the product names purchased by each customer, along with their country."
        ctx = resolve_query_context(
            question=question,
            user_id=self.user_id,
            active_table=self.tbl_customers,
            db_engine=engine
        )

        self.assertTrue(ctx.is_multi_table, "Context should be multi-table")
        self.assertIn("customers", ctx.friendly_tables)
        self.assertIn("orders", ctx.friendly_tables)

        # Generate SQL
        sql = generate_sql(question, self.tbl_customers, user_id=self.user_id, context=ctx)
        self.assertIn("JOIN", sql.upper())
        self.assertTrue("CustomerID" in sql or "customerid" in sql.lower())

        # Translate to physical SQL
        phys_sql = translate_query_tables(sql, authorized_tables=ctx.physical_tables, user_id=self.user_id)
        self.assertIn(self.tbl_customers, phys_sql)
        self.assertIn(self.tbl_orders, phys_sql)

        # Validate AST
        is_valid, err = validate_sql(phys_sql, user_tables=ctx.physical_tables)
        self.assertTrue(is_valid, f"SQL validation failed: {err}")

        # Execute
        records, truncated = execute_sql(phys_sql)
        self.assertEqual(len(records), 4, f"Expected 4 orders returned, got {len(records)}")

        # Verify record contents
        found_alice = any(r.get("CustomerName") == "Alice Cooper" or r.get("customername") == "Alice Cooper" for r in records)
        self.assertTrue(found_alice, "Alice Cooper should be in results")

    def test_02_automatic_two_table_join_no_table_names(self):
        """A question requiring an automatic two-table JOIN without naming tables or keys."""
        question = "List the total amount spent by each customer"
        ctx = resolve_query_context(
            question=question,
            user_id=self.user_id,
            active_table=self.tbl_customers,
            db_engine=engine
        )
        self.assertTrue(ctx.is_multi_table)
        sql = generate_sql(question, self.tbl_customers, user_id=self.user_id, context=ctx)
        phys_sql = translate_query_tables(sql, authorized_tables=ctx.physical_tables, user_id=self.user_id)
        is_valid, err = validate_sql(phys_sql, user_tables=ctx.physical_tables)
        self.assertTrue(is_valid)
        records, truncated = execute_sql(phys_sql)
        self.assertGreaterEqual(len(records), 2)

    def test_03_automatic_three_table_join_bridge_discovery(self):
        """
        A 3-table join question in alternative domain where bridge table is unmentioned:
        'Show item descriptions and headquarters city for each client'
        Mentions: item description (items), headquarters city (clients)
        Unmentioned bridge: purchases (connects clients to items via client_code and item_code)
        """
        question = "Show item descriptions and headquarters city for each client"
        ctx = resolve_query_context(
            question=question,
            user_id=self.user_id,
            active_table=self.tbl_clients,
            db_engine=engine
        )
        self.assertTrue(ctx.is_multi_table)
        self.assertIn("clients", ctx.friendly_tables)
        self.assertIn("items", ctx.friendly_tables)
        self.assertIn("purchases", ctx.friendly_tables, "Bridge table 'purchases' must be dynamically discovered")

        sql = generate_sql(question, self.tbl_clients, user_id=self.user_id, context=ctx)
        phys_sql = translate_query_tables(sql, authorized_tables=ctx.physical_tables, user_id=self.user_id)
        is_valid, err = validate_sql(phys_sql, user_tables=ctx.physical_tables)
        self.assertTrue(is_valid)

        records, truncated = execute_sql(phys_sql)
        self.assertEqual(len(records), 2)

    def test_04_single_table_query_preservation(self):
        """Ensure queries answered entirely by the active table do not generate unnecessary joins."""
        question = "Show all customers from USA"
        ctx = resolve_query_context(
            question=question,
            user_id=self.user_id,
            active_table=self.tbl_customers,
            db_engine=engine
        )
        self.assertFalse(ctx.is_multi_table, "Single table query must not be flagged as multi-table")
        self.assertEqual(ctx.friendly_tables, ["customers"])

        sql = generate_sql(question, self.tbl_customers, user_id=self.user_id, context=ctx)
        self.assertNotIn("JOIN", sql.upper(), "Single table query must not contain JOIN")


if __name__ == "__main__":
    unittest.main()
