"""
PromptSQL — Step 7: Automatic Schema Discovery and Dynamic Join Generation Test Suite

Comprehensive regression suite verifying:
1. Dynamic schema discovery for authorized tables without hardcoding.
2. Heuristic relationship inference (PK-FK naming, type compatibility, explicit FKs, value overlap).
3. False-relationship avoidance on generic columns (id, status, created_at, amount).
4. Multi-hop join path resolution and bridge table discovery.
5. Single-table query preservation (no unnecessary joins when active table suffices).
6. Multi-domain zero-hardcoding verification (E-commerce, Healthcare, Logistics).
7. Ambiguous relationship handling with role-hint extraction.
8. End-to-end integration with SQLGlot AST translation, AST validation, tenant isolation,
   and safe read-only execution.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from decimal import Decimal
from typing import Optional
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.database.connection import engine
from app.services.auth_service import get_current_user_id
from app.services.relationship_service import (
    discover_user_schemas,
    infer_table_relationships,
    resolve_query_context,
    get_table_name_variants,
    are_types_join_compatible,
    RelationshipGraph,
    InferredRelationship
)
from app.services.sql_generator import generate_sql
from app.services.table_translator import translate_query_tables
from app.services.sql_validator import validate_sql
from app.services.sql_executor import execute_sql


class TestRelationshipEngineCore(unittest.TestCase):
    """Unit tests for the core relationship inference heuristics and graph algorithms."""

    def test_linguistic_variant_generation(self):
        """Verifies singularization, stemming, and noun-phrase decomposition."""
        variants_customers = get_table_name_variants("customers")
        self.assertIn("customer", variants_customers)
        self.assertIn("customers", variants_customers)

        variants_prefixed = get_table_name_variants("test_customers")
        self.assertIn("test_customers", variants_prefixed)
        self.assertIn("test_customer", variants_prefixed)
        self.assertIn("customers", variants_prefixed)
        self.assertIn("customer", variants_prefixed)

        variants_compound = get_table_name_variants("order_items")
        self.assertIn("order_items", variants_compound)
        self.assertIn("order_item", variants_compound)
        self.assertIn("items", variants_compound)
        self.assertIn("item", variants_compound)

        variants_categories = get_table_name_variants("product_categories")
        self.assertIn("product_category", variants_categories)
        self.assertIn("category", variants_categories)

    def test_type_compatibility(self):
        """Verifies strict data-type join compatibility."""
        self.assertTrue(are_types_join_compatible("INTEGER", "INTEGER"))
        self.assertTrue(are_types_join_compatible("INTEGER", "NUMERIC"))
        self.assertTrue(are_types_join_compatible("STRING", "STRING"))
        self.assertFalse(are_types_join_compatible("INTEGER", "DATETIME"))
        self.assertFalse(are_types_join_compatible("STRING", "NUMERIC"))
        self.assertFalse(are_types_join_compatible("BOOLEAN", "STRING"))

    def test_graph_multi_hop_traversal(self):
        """Verifies BFS shortest path and bridge table discovery in relationship graph."""
        r1 = InferredRelationship(
            source_table="order_items",
            source_physical="order_items_usr",
            source_column="order_id",
            target_table="orders",
            target_physical="orders_usr",
            target_column="id",
            confidence=0.95,
            cardinality="N:1",
            reason="orders FK"
        )
        r2 = InferredRelationship(
            source_table="orders",
            source_physical="orders_usr",
            source_column="customer_id",
            target_table="customers",
            target_physical="customers_usr",
            target_column="id",
            confidence=0.95,
            cardinality="N:1",
            reason="customers FK"
        )

        graph = RelationshipGraph([r1, r2])

        # Shortest path between order_items and customers
        path = graph.find_shortest_path("order_items", "customers")
        self.assertIsNotNone(path)
        self.assertEqual(len(path), 2)

        # Subgraph connection bridging customers and order_items
        nodes, rels = graph.find_connecting_subgraph({"customers", "order_items"})
        self.assertEqual(nodes, {"customers", "orders", "order_items"})
        self.assertEqual(len(rels), 2)


class TestDynamicSchemaDiscoveryAndJoins(unittest.TestCase):
    """Integration tests verifying schema discovery, relationship inference, and dynamic join execution."""

    @classmethod
    def setUpClass(cls):
        cls.user_id = "test7"
        cls.suffix = "_usr_test7"

        # E-commerce tables
        cls.tbl_cust = f"customers{cls.suffix}"
        cls.tbl_orders = f"orders{cls.suffix}"
        cls.tbl_items = f"order_items{cls.suffix}"

        # Healthcare tables (non-standard PKs)
        cls.tbl_patients = f"patients{cls.suffix}"
        cls.tbl_doctors = f"doctors{cls.suffix}"
        cls.tbl_appointments = f"appointments{cls.suffix}"

        # Logistics tables (shared domain identifiers)
        cls.tbl_warehouses = f"warehouses{cls.suffix}"
        cls.tbl_carriers = f"carriers{cls.suffix}"
        cls.tbl_shipments = f"shipments{cls.suffix}"

        # Unrelated tables (generic column matching)
        cls.tbl_audit = f"audit_events{cls.suffix}"
        cls.tbl_surveys = f"survey_responses{cls.suffix}"

        # Ambiguous relationships (flights & airports)
        cls.tbl_airports = f"airports{cls.suffix}"
        cls.tbl_flights = f"flights{cls.suffix}"

        cls._cleanup_all()

        with engine.begin() as conn:
            # 1. E-Commerce domain
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_cust}` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    customer_name VARCHAR(100) NOT NULL,
                    city VARCHAR(100)
                )
            """))
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_orders}` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    customer_id INT NOT NULL,
                    order_date DATE,
                    order_amount DECIMAL(10,2)
                )
            """))
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_items}` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id INT NOT NULL,
                    product_title VARCHAR(100),
                    quantity INT,
                    item_price DECIMAL(10,2)
                )
            """))

            # Populate E-Commerce
            conn.execute(text(f"INSERT INTO `{cls.tbl_cust}` VALUES (1, 'Alice Smith', 'Seattle'), (2, 'Bob Jones', 'Portland')"))
            conn.execute(text(f"INSERT INTO `{cls.tbl_orders}` VALUES (101, 1, '2026-01-15', 250.00), (102, 1, '2026-02-20', 450.00), (103, 2, '2026-03-10', 120.00)"))
            conn.execute(text(f"INSERT INTO `{cls.tbl_items}` VALUES (1, 101, 'Mechanical Keyboard', 1, 150.00), (2, 101, 'USB Hub', 2, 50.00), (3, 102, 'Ultrawide Monitor', 1, 450.00), (4, 103, 'Wireless Mouse', 1, 120.00)"))

            # 2. Healthcare domain
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_patients}` (
                    patient_code VARCHAR(20) PRIMARY KEY,
                    patient_name VARCHAR(100) NOT NULL,
                    birth_year INT
                )
            """))
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_doctors}` (
                    doctor_license VARCHAR(30) PRIMARY KEY,
                    doctor_name VARCHAR(100) NOT NULL,
                    specialty VARCHAR(50)
                )
            """))
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_appointments}` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    patient_code VARCHAR(20) NOT NULL,
                    doctor_license VARCHAR(30) NOT NULL,
                    appointment_date DATE,
                    consultation_fee DECIMAL(10,2)
                )
            """))

            conn.execute(text(f"INSERT INTO `{cls.tbl_patients}` VALUES ('P-001', 'John Doe', 1985), ('P-002', 'Jane Roe', 1990)"))
            conn.execute(text(f"INSERT INTO `{cls.tbl_doctors}` VALUES ('MD-991', 'Dr. House', 'Diagnostics'), ('MD-992', 'Dr. Watson', 'General')"))
            conn.execute(text(f"INSERT INTO `{cls.tbl_appointments}` VALUES (1, 'P-001', 'MD-991', '2026-04-01', 300.00), (2, 'P-002', 'MD-992', '2026-04-02', 150.00)"))

            # 3. Logistics domain
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_warehouses}` (
                    warehouse_code VARCHAR(20) PRIMARY KEY,
                    warehouse_city VARCHAR(50)
                )
            """))
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_carriers}` (
                    carrier_code VARCHAR(20) PRIMARY KEY,
                    carrier_name VARCHAR(50)
                )
            """))
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_shipments}` (
                    tracking_number VARCHAR(30) PRIMARY KEY,
                    warehouse_code VARCHAR(20) NOT NULL,
                    carrier_code VARCHAR(20) NOT NULL,
                    weight_kg DECIMAL(8,2)
                )
            """))

            conn.execute(text(f"INSERT INTO `{cls.tbl_warehouses}` VALUES ('WH-NORTH', 'Chicago'), ('WH-WEST', 'Denver')"))
            conn.execute(text(f"INSERT INTO `{cls.tbl_carriers}` VALUES ('FEDEX', 'Federal Express'), ('UPS', 'United Parcel Service')"))
            conn.execute(text(f"INSERT INTO `{cls.tbl_shipments}` VALUES ('TRK-1001', 'WH-NORTH', 'FEDEX', 12.5), ('TRK-1002', 'WH-WEST', 'UPS', 4.2)"))

            # 4. Unrelated tables with generic columns
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_audit}` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    status VARCHAR(20),
                    created_at DATETIME,
                    amount DECIMAL(10,2)
                )
            """))
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_surveys}` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    status VARCHAR(20),
                    created_at DATETIME,
                    amount DECIMAL(10,2)
                )
            """))

            # 5. Ambiguous Flights domain
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_airports}` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    airport_code VARCHAR(10),
                    airport_city VARCHAR(50)
                )
            """))
            conn.execute(text(f"""
                CREATE TABLE `{cls.tbl_flights}` (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    origin_airport_id INT NOT NULL,
                    destination_airport_id INT NOT NULL,
                    flight_number VARCHAR(20)
                )
            """))

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_all()

    @classmethod
    def _cleanup_all(cls):
        with engine.begin() as conn:
            for t in [
                cls.tbl_items, cls.tbl_orders, cls.tbl_cust,
                cls.tbl_appointments, cls.tbl_doctors, cls.tbl_patients,
                cls.tbl_shipments, cls.tbl_carriers, cls.tbl_warehouses,
                cls.tbl_audit, cls.tbl_surveys,
                cls.tbl_flights, cls.tbl_airports
            ]:
                conn.execute(text(f"DROP TABLE IF EXISTS `{t}`"))

    def test_schema_discovery(self):
        """Verifies all authorized user tables are dynamically discovered."""
        schemas = discover_user_schemas(user_id=self.user_id, db_engine=engine)
        self.assertIn("customers", schemas)
        self.assertIn("orders", schemas)
        self.assertIn("order_items", schemas)
        self.assertIn("patients", schemas)
        self.assertIn("doctors", schemas)
        self.assertIn("appointments", schemas)
        self.assertIn("warehouses", schemas)
        self.assertIn("carriers", schemas)
        self.assertIn("shipments", schemas)
        self.assertIn("audit_events", schemas)
        self.assertIn("survey_responses", schemas)
        self.assertIn("airports", schemas)
        self.assertIn("flights", schemas)

    def test_false_relationship_suppression(self):
        """Verifies that matching generic columns across unrelated tables are NEVER inferred as joins."""
        schemas = discover_user_schemas(user_id=self.user_id, db_engine=engine)
        rels = infer_table_relationships(schemas, db_engine=engine)

        unrelated_joins = [
            r for r in rels
            if {r.source_table, r.target_table} == {"audit_events", "survey_responses"}
        ]
        self.assertEqual(len(unrelated_joins), 0, f"False-positive relationship inferred: {unrelated_joins}")

    def test_ecommerce_two_table_auto_join(self):
        """
        Verifies 2-table auto-join:
        Question: 'What is the total order amount for each customer?'
        Active table: customers
        Discovers relationship orders.customer_id = customers.id and generates valid query.
        """
        context = resolve_query_context(
            question="What is the total order amount for each customer?",
            user_id=self.user_id,
            active_table=self.tbl_cust,
            db_engine=engine
        )

        self.assertTrue(context.is_multi_table)
        self.assertIn("customers", context.friendly_tables)
        self.assertIn("orders", context.friendly_tables)
        self.assertIn("`orders`.`customer_id` = `customers`.`id`", context.relationships_prompt)

        # Test AST translation and validation of generated query
        friendly_sql = "SELECT `customers`.`customer_name`, SUM(`orders`.`order_amount`) FROM `customers` JOIN `orders` ON `customers`.`id` = `orders`.`customer_id` GROUP BY `customers`.`customer_name`"
        physical_sql = translate_query_tables(friendly_sql, context.physical_tables, self.user_id)
        valid, msg = validate_sql(physical_sql, context.physical_tables)
        self.assertTrue(valid, msg)

        # Safe execution
        records, is_truncated = execute_sql(physical_sql)
        self.assertFalse(is_truncated)
        self.assertEqual(len(records), 2)

    def test_ecommerce_three_table_multi_hop_join(self):
        """
        Verifies 3-table multi-hop join with intermediate bridge table discovery:
        Question mentions 'product title' and 'customer city'. Middle table 'orders' is NOT mentioned.
        Engine must automatically discover bridge table 'orders'.
        """
        context = resolve_query_context(
            question="Show product title and customer city for all purchases",
            user_id=self.user_id,
            active_table=self.tbl_cust,
            db_engine=engine
        )

        self.assertTrue(context.is_multi_table)
        self.assertEqual(set(context.friendly_tables), {"customers", "orders", "order_items"})
        self.assertEqual(len(context.relationships), 2)

        # Check that both relationships exist in the context
        rel_signatures = {(r.source_table, r.target_table) for r in context.relationships}
        self.assertTrue(
            ("orders", "customers") in rel_signatures or ("customers", "orders") in rel_signatures
        )
        self.assertTrue(
            ("order_items", "orders") in rel_signatures or ("orders", "order_items") in rel_signatures
        )

        # Verify translation, validation, and execution
        friendly_sql = (
            "SELECT `customers`.`city`, `order_items`.`product_title` "
            "FROM `customers` "
            "JOIN `orders` ON `customers`.`id` = `orders`.`customer_id` "
            "JOIN `order_items` ON `orders`.`id` = `order_items`.`order_id`"
        )
        physical_sql = translate_query_tables(friendly_sql, context.physical_tables, self.user_id)
        valid, msg = validate_sql(physical_sql, context.physical_tables)
        self.assertTrue(valid, msg)

        records, is_truncated = execute_sql(physical_sql)
        self.assertFalse(is_truncated)
        self.assertEqual(len(records), 4)

    def test_ecommerce_single_table_preservation(self):
        """
        Verifies single-table query preservation:
        When active table contains all necessary columns, no unnecessary joins are introduced.
        """
        context = resolve_query_context(
            question="Show all customers from Seattle",
            user_id=self.user_id,
            active_table=self.tbl_cust,
            db_engine=engine
        )

        self.assertFalse(context.is_multi_table)
        self.assertEqual(context.friendly_tables, ["customers"])
        self.assertEqual(context.relationships_prompt, "None (Single-table query)")

    def test_healthcare_non_standard_pk_joins(self):
        """
        Verifies dynamic relationship inference with non-standard primary keys
        (patient_code, doctor_license) without any hardcoded mappings.
        """
        context = resolve_query_context(
            question="Show patient name, doctor name, and consultation fee",
            user_id=self.user_id,
            active_table=self.tbl_appointments,
            db_engine=engine
        )

        self.assertTrue(context.is_multi_table)
        self.assertEqual(set(context.friendly_tables), {"appointments", "patients", "doctors"})

        friendly_sql = (
            "SELECT `patients`.`patient_name`, `doctors`.`doctor_name`, `appointments`.`consultation_fee` "
            "FROM `appointments` "
            "JOIN `patients` ON `appointments`.`patient_code` = `patients`.`patient_code` "
            "JOIN `doctors` ON `appointments`.`doctor_license` = `doctors`.`doctor_license`"
        )
        physical_sql = translate_query_tables(friendly_sql, context.physical_tables, self.user_id)
        valid, msg = validate_sql(physical_sql, context.physical_tables)
        self.assertTrue(valid, msg)

        records, is_truncated = execute_sql(physical_sql)
        self.assertFalse(is_truncated)
        self.assertEqual(len(records), 2)

    def test_logistics_shared_domain_identifier(self):
        """
        Verifies dynamic relationship inference with shared non-generic domain identifiers
        (warehouse_code, carrier_code).
        """
        context = resolve_query_context(
            question="List tracking number, warehouse city, and carrier name",
            user_id=self.user_id,
            active_table=self.tbl_shipments,
            db_engine=engine
        )

        self.assertTrue(context.is_multi_table)
        self.assertEqual(set(context.friendly_tables), {"shipments", "warehouses", "carriers"})

        friendly_sql = (
            "SELECT `shipments`.`tracking_number`, `warehouses`.`warehouse_city`, `carriers`.`carrier_name` "
            "FROM `shipments` "
            "JOIN `warehouses` ON `shipments`.`warehouse_code` = `warehouses`.`warehouse_code` "
            "JOIN `carriers` ON `shipments`.`carrier_code` = `carriers`.`carrier_code`"
        )
        physical_sql = translate_query_tables(friendly_sql, context.physical_tables, self.user_id)
        valid, msg = validate_sql(physical_sql, context.physical_tables)
        self.assertTrue(valid, msg)

        records, is_truncated = execute_sql(physical_sql)
        self.assertFalse(is_truncated)
        self.assertEqual(len(records), 2)

    def test_ambiguous_relationship_handling(self):
        """
        Verifies that multiple foreign keys to the same parent table (flights -> airports)
        are flagged as ambiguous and role hints are captured.
        """
        schemas = discover_user_schemas(user_id=self.user_id, db_engine=engine)
        rels = infer_table_relationships(schemas, db_engine=engine)

        flight_rels = [
            r for r in rels
            if r.source_table == "flights" and r.target_table == "airports"
        ]
        self.assertEqual(len(flight_rels), 2)
        for r in flight_rels:
            self.assertTrue(r.is_ambiguous)
            self.assertIn(r.disambiguation_hint, ["origin", "destination"])

    def test_end_to_end_ask_endpoint_multi_table(self):
        """
        Verifies the complete FastAPI POST /ask pipeline with dynamic join discovery.
        """
        client = TestClient(app)
        app.dependency_overrides[get_current_user_id] = lambda: self.user_id

        try:
            # Mock LLM to return deterministic friendly multi-table query
            mock_sql = (
                "SELECT `customers`.`customer_name`, SUM(`orders`.`order_amount`) AS `total_spent` "
                "FROM `customers` "
                "JOIN `orders` ON `customers`.`id` = `orders`.`customer_id` "
                "GROUP BY `customers`.`customer_name`"
            )
            with patch("app.services.sql_generator.call_llm", return_value=mock_sql):
                response = client.post(
                    "/ask",
                    json={"question": "What is the total order amount for each customer?"},
                    headers={"x-table-name": self.tbl_cust}
                )

                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertTrue(data.get("success"), data.get("error"))
                self.assertEqual(data.get("count"), 2)
                self.assertIn("Alice Smith", str(data.get("result")))
                self.assertIn("Bob Jones", str(data.get("result")))
        finally:
            app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
