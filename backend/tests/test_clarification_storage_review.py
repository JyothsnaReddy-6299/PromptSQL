"""
Test suite for Focused Review of Pending Clarification Storage (Step 7.1)

Verifies:
1. Storage in process memory with client-context roundtrip fallback.
2. Restart survival via client clarification_context payload.
3. Multi-worker accessibility without shared memory.
4. Isolation by user AND active dataset.
5. Invalidation of stale clarifications when an unrelated new query is asked.
"""

import unittest
from sqlalchemy import text
from app.database.connection import engine
from app.routes.ask import ask_question, AskRequest
from app.services.relationship_service import (
    get_pending_clarification,
    clear_pending_clarification
)


class TestClarificationStorageReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.user_a = "usr_rev_a"
        cls.user_b = "usr_rev_b"

        cls.t_airports_a = f"airports_{cls.user_a}"
        cls.t_flights_a = f"flights_{cls.user_a}"
        cls.t_orders_a = f"orders_{cls.user_a}"

        cls.t_airports_b = f"airports_{cls.user_b}"
        cls.t_flights_b = f"flights_{cls.user_b}"

        cls.all_tables = [
            cls.t_flights_a, cls.t_airports_a, cls.t_orders_a,
            cls.t_flights_b, cls.t_airports_b
        ]

        with engine.begin() as conn:
            for t in cls.all_tables:
                conn.execute(text(f"DROP TABLE IF EXISTS `{t}`"))

            # User A tables
            conn.execute(text(f"""
                CREATE TABLE `{cls.t_airports_a}` (
                    airport_id INT PRIMARY KEY,
                    airport_code VARCHAR(10),
                    city VARCHAR(50)
                )
            """))
            conn.execute(text(f"""
                CREATE TABLE `{cls.t_flights_a}` (
                    flight_id INT PRIMARY KEY,
                    flight_number VARCHAR(20),
                    origin_airport_id INT,
                    destination_airport_id INT
                )
            """))
            conn.execute(text(f"""
                CREATE TABLE `{cls.t_orders_a}` (
                    order_id INT PRIMARY KEY,
                    total_amount DECIMAL(10, 2)
                )
            """))

            # User B tables
            conn.execute(text(f"""
                CREATE TABLE `{cls.t_airports_b}` (
                    airport_id INT PRIMARY KEY,
                    airport_code VARCHAR(10),
                    city VARCHAR(50)
                )
            """))
            conn.execute(text(f"""
                CREATE TABLE `{cls.t_flights_b}` (
                    flight_id INT PRIMARY KEY,
                    flight_number VARCHAR(20),
                    origin_airport_id INT,
                    destination_airport_id INT
                )
            """))

            conn.execute(text(f"""
                INSERT INTO `{cls.t_airports_a}` VALUES
                (1, 'JFK', 'New York'),
                (2, 'LHR', 'London')
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.t_flights_a}` VALUES
                (10, 'FL-101', 1, 2)
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.t_orders_a}` VALUES
                (101, 250.00)
            """))

            conn.execute(text(f"""
                INSERT INTO `{cls.t_airports_b}` VALUES
                (1, 'JFK', 'New York'),
                (2, 'LHR', 'London')
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.t_flights_b}` VALUES
                (20, 'FL-202', 2, 1)
            """))

    @classmethod
    def tearDownClass(cls):
        with engine.begin() as conn:
            for t in cls.all_tables:
                conn.execute(text(f"DROP TABLE IF EXISTS `{t}`"))

    def test_01_user_and_dataset_isolation(self):
        """Verify clarification context is isolated by BOTH user_id and active table."""
        # User A triggers ambiguous query on flights
        res_a = ask_question(
            AskRequest(question="Show flight number and city for each flight"),
            x_table_name=self.t_flights_a,
            user_id=self.user_a
        )
        self.assertTrue(res_a.get("needs_clarification"))
        
        # User A switches active dataset to orders_a
        # Asking a question on orders must NOT pick up the pending clarification from flights
        res_orders = ask_question(
            AskRequest(question="Show total amount of orders"),
            x_table_name=self.t_orders_a,
            user_id=self.user_a
        )
        self.assertTrue(res_orders["success"])
        self.assertFalse(res_orders.get("needs_clarification", False))
        self.assertIn("orders", res_orders["generated_sql"].lower())

        # User B on flights_b must NOT see User A's pending clarification
        pending_b = get_pending_clarification(self.user_b, self.t_flights_b)
        self.assertIsNone(pending_b)

    def test_02_stale_clarification_invalidation(self):
        """Verify that when a user asks an unrelated new query, stale pending clarification is cleared."""
        # Trigger clarification
        res_ambig = ask_question(
            AskRequest(question="Show flight number and city for each flight"),
            x_table_name=self.t_flights_a,
            user_id=self.user_a
        )
        self.assertTrue(res_ambig.get("needs_clarification"))
        self.assertIsNotNone(get_pending_clarification(self.user_a, self.t_flights_a))

        # User asks a completely unrelated new question instead of answering the clarification
        res_new = ask_question(
            AskRequest(question="Show all flights"),
            x_table_name=self.t_flights_a,
            user_id=self.user_a
        )
        self.assertTrue(res_new["success"])
        self.assertFalse(res_new.get("needs_clarification", False))

        # Pending clarification must now be cleared
        self.assertIsNone(get_pending_clarification(self.user_a, self.t_flights_a))

    def test_03_multi_worker_and_restart_resilience(self):
        """Verify clarification survives across workers or restarts via client clarification_context."""
        # 1. User gets clarification prompt and context payload
        res_ambig = ask_question(
            AskRequest(question="Show flight number and city for each flight"),
            x_table_name=self.t_flights_a,
            user_id=self.user_a
        )
        self.assertTrue(res_ambig.get("needs_clarification"))
        ctx_payload = res_ambig.get("clarification_context")
        self.assertIsNotNone(ctx_payload)

        # 2. Simulate server restart or request landing on another worker by clearing in-memory store
        clear_pending_clarification(self.user_a, self.t_flights_a)
        self.assertIsNone(get_pending_clarification(self.user_a, self.t_flights_a))

        # 3. Follow-up passes clarification_context back in payload (stateless multi-worker mode)
        followup_res = ask_question(
            AskRequest(
                question="origin city",
                clarification_selection="origin city",
                clarification_context=ctx_payload
            ),
            x_table_name=self.t_flights_a,
            user_id=self.user_a
        )
        self.assertTrue(followup_res["success"])
        self.assertFalse(followup_res.get("needs_clarification", False))
        self.assertIn("origin_airport_id", followup_res["generated_sql"])
        self.assertEqual(followup_res["count"], 1)


if __name__ == "__main__":
    unittest.main()
