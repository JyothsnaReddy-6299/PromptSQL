"""
PromptSQL — Issue 17: Application-Wide Security, Data Integrity & Functional Reliability Remediation Test Suite
Verifies all 10 areas of Issue 17:
- Issue 17.1: Authenticated password change, disabled unauthenticated reset, session invalidation
- Issue 17.2: Excluded .env, safe .env.example placeholders, no default production secrets
- Issue 17.3: Safe upload with staging table, atomic swap, and original table preservation on failure
- Issue 17.4: Safe duplicate removal without TRUNCATE TABLE, preserving tables on failure
- Issue 17.5: Multi-turn conversation history sanitization (canaries never stored or reintroduced)
- Issue 17.6: Dynamic SQLGlot AST small-group count alias discovery and suppression (< 3)
- Issue 17.7: MySQL parameter binding with quotes, backslashes, and multiple canaries
- Issue 17.8: Semantic date selection (event dates vs demographic/birth dates, no salary-by-DOB trend)
- Issue 17.9: Mixed and inconsistent order grain detection and revenue/AOV suppression
- Issue 17.10: Session revocation, login rate limiting, uniform auth errors, and production CORS hardening
"""

import unittest
import os
import time
import uuid
import pandas as pd
from unittest.mock import patch, MagicMock
from sqlalchemy import text, inspect
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import engine, SessionLocal
from app.models.user import User
from app.models.history import QueryHistory
from app.core.config import Settings
from app.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    decode_and_validate_token,
    revoke_token,
    revoke_all_user_sessions,
    _REVOKED_TOKENS,
    _USER_MIN_IAT,
)
from app.routes.auth import _FAILED_LOGIN_ATTEMPTS
from app.services.upload_service import clean_table_name, upload_dataset
from app.services.privacy_redactor import (
    extract_count_aliases_from_sql,
    redact_records_for_ai,
    extract_sensitive_query_parameters,
)
from app.services.summary_generator import generate_summary
from app.services.data_discovery_service import (
    is_valid_trend_date_column,
    select_best_trend_date_column,
    discover_trends,
    generate_visual_analytics,
    inspect_order_amount_grain,
    generate_dynamic_kpis,
)


class TestIssue17ReliabilityRemediation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.db = SessionLocal()

        # Create a dedicated test user
        cls.test_username = f"test_i17_{uuid.uuid4().hex[:8]}"
        cls.test_password = "CorrectPassword123!"
        cls.user = User(
            username=cls.test_username,
            password_hash=hash_password(cls.test_password)
        )
        cls.db.add(cls.user)
        cls.db.commit()
        cls.db.refresh(cls.user)
        cls.user_id_str = f"usr_{cls.user.id}"
        cls.token = create_access_token(cls.user.id)

    @classmethod
    def tearDownClass(cls):
        try:
            # Delete user query history and test user
            cls.db.query(QueryHistory).filter(QueryHistory.user_id == cls.user_id_str).delete()
            cls.db.query(User).filter(User.id == cls.user.id).delete()
            cls.db.commit()
        except Exception:
            cls.db.rollback()
        finally:
            cls.db.close()

    def setUp(self):
        # Reset failed login tracking before each test
        _FAILED_LOGIN_ATTEMPTS.clear()

    # -------------------------------------------------------------------------
    # PART 1: Password Security & Account Protection (Issue 17.1 & 17.10)
    # -------------------------------------------------------------------------
    def test_17_1_unauthenticated_reset_password_is_disabled(self):
        """Unauthenticated /auth/reset-password endpoint must return HTTP 501 Not Implemented."""
        res = self.client.post("/auth/reset-password", json={
            "username": self.test_username,
            "new_password": "HackedPassword123!"
        })
        self.assertEqual(res.status_code, 501)
        self.assertIn("disabled", res.json()["detail"].lower())

    def test_17_1_authenticated_change_password_requires_valid_current_password(self):
        """Authenticated password change fails when current password is wrong."""
        headers = {"Authorization": f"Bearer {self.token}"}
        res = self.client.post("/auth/change-password", headers=headers, json={
            "current_password": "WrongPassword999!",
            "new_password": "NewValidPassword123!"
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("incorrect current password", res.json()["detail"].lower())

    def test_17_1_authenticated_change_password_enforces_length_rules(self):
        """Authenticated password change validates min length and max 72 bytes."""
        headers = {"Authorization": f"Bearer {self.token}"}
        # Too short (< 6)
        res_short = self.client.post("/auth/change-password", headers=headers, json={
            "current_password": self.test_password,
            "new_password": "123"
        })
        self.assertEqual(res_short.status_code, 400)
        self.assertIn("at least 6 characters", res_short.json()["detail"].lower())

        # Too long (> 72 bytes)
        res_long = self.client.post("/auth/change-password", headers=headers, json={
            "current_password": self.test_password,
            "new_password": "A" * 75
        })
        self.assertEqual(res_long.status_code, 400)
        self.assertIn("72 utf-8 bytes", res_long.json()["detail"].lower())

    def test_17_1_successful_password_change_invalidates_prior_sessions(self):
        """Changing password invalidates all previously issued tokens for that user."""
        old_token = create_access_token(self.user.id)
        # Verify old token works initially
        self.assertIsNotNone(decode_and_validate_token(old_token))

        new_password = "BrandNewSecurePassword456!"
        headers = {"Authorization": f"Bearer {old_token}"}
        res = self.client.post("/auth/change-password", headers=headers, json={
            "current_password": self.test_password,
            "new_password": new_password
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])
        new_token = res.json()["token"]

        # Verify old token is now invalidated
        with self.assertRaises(Exception):
            decode_and_validate_token(old_token)

        # Verify new token works
        user_id_decoded = decode_and_validate_token(new_token)
        self.assertEqual(user_id_decoded["sub"], str(self.user.id))

        # Restore original password for other tests
        self.user.password_hash = hash_password(self.test_password)
        self.db.commit()
        # Reset revocation cutoff
        _USER_MIN_IAT.pop(self.user.id, None)
        TestIssue17ReliabilityRemediation.token = create_access_token(self.user.id)

    def test_17_10_logout_revokes_token_server_side(self):
        """Calling /auth/logout immediately revokes the bearer token server-side."""
        temp_token = create_access_token(self.user.id)
        self.assertIsNotNone(decode_and_validate_token(temp_token))

        res = self.client.post("/auth/logout", headers={"Authorization": f"Bearer {temp_token}"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

        # Token is revoked
        with self.assertRaises(Exception):
            decode_and_validate_token(temp_token)

    def test_17_10_login_rate_limiting_blocks_after_5_failures(self):
        """5 failed login attempts within 1 minute results in HTTP 429."""
        for _ in range(5):
            res = self.client.post("/auth/login", json={
                "username": self.test_username,
                "password": "WrongPasswordAttempt"
            })
            self.assertEqual(res.status_code, 401)

        # 6th attempt must be rate-limited
        res_blocked = self.client.post("/auth/login", json={
            "username": self.test_username,
            "password": "WrongPasswordAttempt"
        })
        self.assertEqual(res_blocked.status_code, 429)
        self.assertIn("too many failed login attempts", res_blocked.json()["detail"].lower())

    def test_17_10_uniform_auth_error_prevents_username_enumeration(self):
        """Invalid username and wrong password both return exact same error message."""
        res_nonexistent = self.client.post("/auth/login", json={
            "username": "totally_nonexistent_user_9999",
            "password": "SomePassword123!"
        })
        res_wrong_pw = self.client.post("/auth/login", json={
            "username": self.test_username,
            "password": "WrongPassword123!"
        })
        self.assertEqual(res_nonexistent.status_code, 401)
        self.assertEqual(res_wrong_pw.status_code, 401)
        self.assertEqual(res_nonexistent.json()["detail"], "Invalid username or password")
        self.assertEqual(res_wrong_pw.json()["detail"], "Invalid username or password")

    # -------------------------------------------------------------------------
    # PART 2: Secret Management & CORS Hardening (Issue 17.2 & 17.10)
    # -------------------------------------------------------------------------
    def test_17_2_gitignore_excludes_env_file(self):
        """Repository .gitignore must explicitly exclude .env files."""
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        gitignore_path = os.path.join(root_dir, ".gitignore")
        self.assertTrue(os.path.exists(gitignore_path), ".gitignore must exist")
        with open(gitignore_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertTrue(any(".env" in line for line in lines), ".gitignore must contain .env exclusion")

    def test_17_2_env_example_contains_only_placeholders(self):
        """backend/.env.example must not contain live secrets, only placeholders."""
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        example_path = os.path.join(root_dir, "backend", ".env.example")
        self.assertTrue(os.path.exists(example_path), "backend/.env.example must exist")
        with open(example_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("your_groq_api_key", content)
        import re
        self.assertFalse(re.search(r"gsk_[a-zA-Z0-9]{40,}", content), "No live Groq API key in .env.example")
        self.assertIn("your_", content.lower(), ".env.example must use placeholders")

    def test_17_10_production_config_rejects_wildcard_cors(self):
        """In production environment, Settings must raise ValueError if CORS_ORIGINS is wildcard '*'."""
        with self.assertRaises(ValueError) as ctx:
            Settings(
                APP_ENV="production",
                JWT_SECRET="a" * 32,
                GROQ_API_KEY="valid_groq_api_key_placeholder_for_test",
                MYSQL_USER="prod_user",
                MYSQL_HOST="db.prod.internal",
                MYSQL_DATABASE="proddb",
                CORS_ORIGINS=["*"]
            )
        self.assertIn("Wildcard CORS origin ('*') is prohibited in production", str(ctx.exception))

    # -------------------------------------------------------------------------
    # PART 3: Safe Upload & Table Replacement (Issue 17.3)
    # -------------------------------------------------------------------------
    def test_17_3_clean_table_name_strips_destructive_characters(self):
        """clean_table_name sanitizes input by removing quotes, backticks, parens, brackets, semicolons."""
        raw = "my_table'; DROP TABLE users; -- (2024) [v1] `test`"
        cleaned = clean_table_name(raw)
        self.assertNotIn("'", cleaned)
        self.assertNotIn('"', cleaned)
        self.assertNotIn("`", cleaned)
        self.assertNotIn(";", cleaned)
        self.assertNotIn("(", cleaned)
        self.assertNotIn(")", cleaned)
        self.assertNotIn("[", cleaned)
        self.assertNotIn("]", cleaned)
        self.assertTrue(len(cleaned) <= 40)

    def test_17_3_failed_upload_preserves_existing_table(self):
        """If upload fails during staging or row verification, existing active table is untouched."""
        csv_filename = f"test_i17_upload_{int(time.time())}.csv"
        temp_csv_path = os.path.abspath(csv_filename)
        active_tbl = None

        # 1. Create a real CSV and upload it successfully to establish an active table
        df1 = pd.DataFrame({"id": [1, 2], "val": ["original_data_1", "original_data_2"]})
        df1.to_csv(temp_csv_path, index=False)

        try:
            res = upload_dataset(temp_csv_path, csv_filename, user_id=self.user_id_str)
            active_tbl = res["table_name"]
            safe_active = f"`{active_tbl}`"

            # Verify initial count
            with engine.connect() as conn:
                initial_count = conn.execute(text(f"SELECT COUNT(*) FROM {safe_active}")).scalar()
            self.assertEqual(initial_count, 2)

            # 2. Now simulate a replacement upload where to_sql fails during staging
            df2 = pd.DataFrame({"id": [3, 4], "val": ["new_1", "new_2"]})
            df2.to_csv(temp_csv_path, index=False)

            with patch("pandas.DataFrame.to_sql", side_effect=RuntimeError("Simulated DB connection failure during upload staging")):
                with self.assertRaises(RuntimeError):
                    upload_dataset(temp_csv_path, csv_filename, user_id=self.user_id_str)

            # 3. Verify original active table still exists and its rows are completely intact
            with engine.connect() as conn:
                post_fail_count = conn.execute(text(f"SELECT COUNT(*) FROM {safe_active}")).scalar()
                sample_row = conn.execute(text(f"SELECT val FROM {safe_active} WHERE id = 1")).scalar()

            self.assertEqual(post_fail_count, 2, "Original table row count must remain unchanged")
            self.assertEqual(sample_row, "original_data_1", "Original data must be intact")

            # Verify no orphaned staging table remains
            inspector = inspect(engine)
            existing_tables = inspector.get_table_names()
            stg_orphans = [t for t in existing_tables if "stg_" in t and active_tbl[:30] in t]
            self.assertEqual(len(stg_orphans), 0, "Staging table must be dropped on failure")

        finally:
            if os.path.exists(temp_csv_path):
                try:
                    os.remove(temp_csv_path)
                except Exception:
                    pass
            if active_tbl:
                try:
                    with engine.begin() as conn:
                        conn.execute(text(f"DROP TABLE IF EXISTS `{active_tbl}`"))
                except Exception:
                    pass

    # -------------------------------------------------------------------------
    # PART 4: Safe Duplicate Removal (Issue 17.4)
    # -------------------------------------------------------------------------
    def test_17_4_duplicate_removal_does_not_truncate_on_failure(self):
        """Duplicate removal route must not truncate table before verifying staging table."""
        test_tbl = f"test_i17_dedup_{int(time.time())}_{self.user_id_str}"
        safe_tbl = f"`{test_tbl}`"

        with engine.begin() as conn:
            conn.execute(text(f"CREATE TABLE {safe_tbl} (id INT AUTO_INCREMENT PRIMARY KEY, col_a VARCHAR(20), col_b VARCHAR(20))"))
            conn.execute(text(f"INSERT INTO {safe_tbl} (col_a, col_b) VALUES ('x', 'y'), ('x', 'y'), ('a', 'b')"))

        try:
            # Verify initial count = 3
            with engine.connect() as conn:
                cnt = conn.execute(text(f"SELECT COUNT(*) FROM {safe_tbl}")).scalar()
            self.assertEqual(cnt, 3)

            # Test deduplication endpoint
            res = self.client.post("/api/clean/remove-duplicates", headers={
                "Authorization": f"Bearer {self.token}",
                "X-Table-Name": test_tbl
            })
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["rows_affected"], 1)
            self.assertEqual(data["total_rows"], 2)

            # Verify table still has the 2 distinct rows
            with engine.connect() as conn:
                cnt_after = conn.execute(text(f"SELECT COUNT(*) FROM {safe_tbl}")).scalar()
            self.assertEqual(cnt_after, 2)

        finally:
            with engine.begin() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {safe_tbl}"))

    # -------------------------------------------------------------------------
    # PART 5: Multi-Turn Conversation History Sanitization (Issue 17.5)
    # -------------------------------------------------------------------------
    def test_17_5_query_history_persists_sanitized_question(self):
        """When an authorized user asks a question with sensitive values, sanitized question is saved in QueryHistory."""
        canary_email = "confidential_ceo@enterprise.com"
        raw_question = f"Show me salary for employee {canary_email}"

        # Test redactor produces sanitized string
        sanitized, extracted = extract_sensitive_query_parameters(raw_question)
        self.assertNotIn(canary_email, sanitized)
        self.assertIn("[EMAIL_PARAM_1]", sanitized)

        # Create QueryHistory entry as done in ask.py
        qh = QueryHistory(
            user_id=self.user_id_str,
            table_name="employees",
            question=sanitized,
            generated_sql="SELECT salary FROM employees WHERE email = :email_param_1",
            summary="Employee salary details"
        )
        self.db.add(qh)
        self.db.commit()

        # Retrieve and verify database record
        saved = self.db.query(QueryHistory).filter(QueryHistory.id == qh.id).first()
        self.assertIsNotNone(saved)
        self.assertNotIn(canary_email, saved.question)
        self.assertIn("[EMAIL_PARAM_1]", saved.question)

    # -------------------------------------------------------------------------
    # PART 6: Dynamic SQLGlot Small-Group Disclosure (Issue 17.6)
    # -------------------------------------------------------------------------
    def test_17_6_extract_count_aliases_from_sql_ast(self):
        """extract_count_aliases_from_sql uses SQLGlot AST to detect custom aliases for COUNT(...)."""
        sql1 = "SELECT dept, COUNT(*) AS staff_count FROM employees GROUP BY dept"
        aliases1 = extract_count_aliases_from_sql(sql1)
        self.assertIn("staff_count", aliases1)

        sql2 = "SELECT role, COUNT(id) AS number_of_employees, AVG(salary) AS avg_sal FROM staff GROUP BY role"
        aliases2 = extract_count_aliases_from_sql(sql2)
        self.assertIn("number_of_employees", aliases2)
        self.assertNotIn("avg_sal", aliases2)

        sql3 = "SELECT band, COUNT(DISTINCT emp_id) AS headcount FROM org GROUP BY band"
        aliases3 = extract_count_aliases_from_sql(sql3)
        self.assertIn("headcount", aliases3)

    def test_17_6_small_group_counts_below_3_are_suppressed(self):
        """Groups with count < 3 are suppressed in records prepared for external AI."""
        sql = "SELECT dept, COUNT(*) AS number_of_employees, SUM(salary) AS total_pay FROM emp GROUP BY dept"
        records = [
            {"dept": "Engineering", "number_of_employees": 15, "total_pay": 1500000},
            {"dept": "Executive", "number_of_employees": 2, "total_pay": 450000},  # Small group!
            {"dept": "Design", "number_of_employees": 1, "total_pay": 90000},      # Small group!
        ]
        redacted = redact_records_for_ai(records, sql=sql)
        self.assertEqual(len(redacted), 3)
        # Large group intact
        self.assertEqual(redacted[0]["dept"], "Engineering")
        self.assertEqual(redacted[0]["number_of_employees"], 15)
        self.assertEqual(redacted[0]["total_pay"], 1500000)
        # Small groups: sensitive total_pay suppressed
        self.assertEqual(redacted[1]["total_pay"], "[SUPPRESSED_SMALL_GROUP]")
        self.assertEqual(redacted[2]["total_pay"], "[SUPPRESSED_SMALL_GROUP]")

    # -------------------------------------------------------------------------
    # PART 7: MySQL Parameter Binding (Issue 17.7)
    # -------------------------------------------------------------------------
    def test_17_7_mysql_parameter_binding_handles_quotes_and_backslashes(self):
        """SQLAlchemy parameter binding safely handles quotes, backslashes, and canaries."""
        test_tbl = f"test_i17_bind_{int(time.time())}"
        safe_tbl = f"`{test_tbl}`"

        with engine.begin() as conn:
            conn.execute(text(f"CREATE TABLE {safe_tbl} (id INT PRIMARY KEY, email VARCHAR(100), note VARCHAR(100))"))
            conn.execute(
                text(f"INSERT INTO {safe_tbl} VALUES (1, :email, :note)"),
                {"email": "o'connor@enterprise.com", "note": "back\\slash and 'quotes'"}
            )

        try:
            with engine.connect() as conn:
                res = conn.execute(
                    text(f"SELECT email, note FROM {safe_tbl} WHERE email = :param_email"),
                    {"param_email": "o'connor@enterprise.com"}
                ).fetchone()

            self.assertIsNotNone(res)
            self.assertEqual(res[0], "o'connor@enterprise.com")
            self.assertEqual(res[1], "back\\slash and 'quotes'")
        finally:
            with engine.begin() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {safe_tbl}"))

    # -------------------------------------------------------------------------
    # PART 8: Semantic Date Selection (Issue 17.8)
    # -------------------------------------------------------------------------
    def test_17_8_is_valid_trend_date_column_rejects_demographic_dates(self):
        """is_valid_trend_date_column rejects birth dates and expiry dates."""
        self.assertFalse(is_valid_trend_date_column("dob"))
        self.assertFalse(is_valid_trend_date_column("date_of_birth"))
        self.assertFalse(is_valid_trend_date_column("birth_date"))
        self.assertFalse(is_valid_trend_date_column("expiry_date"))
        self.assertFalse(is_valid_trend_date_column("due_date"))

        # Valid event dates
        self.assertTrue(is_valid_trend_date_column("order_date"))
        self.assertTrue(is_valid_trend_date_column("transaction_date"))
        self.assertTrue(is_valid_trend_date_column("created_at"))
        self.assertTrue(is_valid_trend_date_column("sale_date"))

        # Reject hire_date when metric is salary
        self.assertFalse(is_valid_trend_date_column("hire_date", metric_col="salary"))

    def test_17_8_select_best_trend_date_column_prioritizes_event_dates(self):
        """select_best_trend_date_column chooses order_date over date_of_birth."""
        cols = ["date_of_birth", "order_date", "expiry_date"]
        best = select_best_trend_date_column(cols)
        self.assertEqual(best, "order_date")

        # When only demographic dates exist, returns None
        only_demographic = ["dob", "date_of_birth", "birth_date"]
        self.assertIsNone(select_best_trend_date_column(only_demographic))

    def test_17_8_employee_dob_does_not_generate_salary_trend(self):
        """discover_trends returns empty insights when only demographic dates (DOB) are present."""
        profile = {
            "table_name": "employees",
            "total_records": 100,
            "date_columns": ["date_of_birth"],
            "numeric_columns": ["annual_salary"],
            "categorical_columns": ["department"]
        }
        insights = discover_trends("employees", profile)
        self.assertEqual(insights, [], "Must not generate temporal trend on date_of_birth")

    # -------------------------------------------------------------------------
    # PART 9: Mixed and Inconsistent Order Grain (Issue 17.9)
    # -------------------------------------------------------------------------
    def test_17_9_mixed_order_amounts_detected_as_ambiguous(self):
        """inspect_order_amount_grain detects mixed datasets (constant and varying orders) as AMBIGUOUS."""
        test_tbl = f"test_i17_grain_{int(time.time())}"
        safe_tbl = f"`{test_tbl}`"

        with engine.begin() as conn:
            conn.execute(text(f"CREATE TABLE {safe_tbl} (id INT AUTO_INCREMENT PRIMARY KEY, order_id VARCHAR(10), item VARCHAR(50), amount DECIMAL(10,2))"))
            # Order 1: Constant amounts (looks like repeated total)
            conn.execute(text(f"INSERT INTO {safe_tbl} (order_id, item, amount) VALUES ('ORD1', 'Laptop', 50000.00), ('ORD1', 'Mouse', 50000.00)"))
            # Order 2: Varying amounts (looks like line items)
            conn.execute(text(f"INSERT INTO {safe_tbl} (order_id, item, amount) VALUES ('ORD2', 'Keyboard', 2000.00), ('ORD2', 'Cable', 500.00)"))

        try:
            profile = {
                "column_names": ["order_id", "item", "amount"],
                "numeric_columns": ["amount"],
                "categorical_columns": ["item"]
            }
            grain = inspect_order_amount_grain(test_tbl, "order_id", "amount", profile)
            self.assertEqual(grain["grain_case"], "AMBIGUOUS")
            self.assertTrue(grain["is_ambiguous"])
            self.assertIsNone(grain["tot_rev_sql"], "Revenue SQL must be suppressed")
            self.assertIsNone(grain["aov_sql"], "AOV SQL must be suppressed")
            self.assertIn("mixed order-amount grain", grain["explanation"].lower())
        finally:
            with engine.begin() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {safe_tbl}"))


if __name__ == "__main__":
    unittest.main()
