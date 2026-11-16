"""
PromptSQL — Issue 16: Privacy Guardian Verification & Security Test Suite

Comprehensive tests for:
- Test Group A: Sensitive Data Detection Engine (Patterns, Checksums, False-positive Guards)
- Test Group B: AI-Boundary Redaction with Mocked Provider Payload Inspection
- Test Group C: Authorized User Full Visibility (Data Preview, Query Results, Database Integrity)
- Test Group D: Policy Configuration, Tenant Isolation & Fail-Closed Behavior
"""

import unittest
import os
import sys
import json
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.connection import engine, SessionLocal, Base
from app.models.privacy import PrivacyColumnPolicy, PrivacyAuditLog
from app.services.privacy_detector import (
    classify_column_privacy,
    verify_verhoeff,
    verify_luhn,
    evaluate_column_values
)
from app.services.privacy_service import (
    scan_and_save_dataset_privacy,
    get_dataset_column_policies,
    update_column_policy,
    get_privacy_overview,
    get_privacy_audit_logs,
    invalidate_privacy_cache
)
from app.services.privacy_redactor import (
    redact_records_for_ai,
    redact_text_for_ai,
    extract_sensitive_query_parameters,
    resolve_query_parameters_ast
)
from app.services.llm_service import (
    call_llm,
    set_mock_ai_handler,
    get_recorded_ai_payloads,
    clear_recorded_ai_payloads
)
from app.services.summary_generator import generate_summary


class TestGroupASensitiveDataDetection(unittest.TestCase):
    """Verifies evidence-based sensitive data detection and false-positive prevention."""

    def test_verhoeff_aadhaar_validation(self):
        # Valid Aadhaar numbers generated via Verhoeff checksum algorithm
        self.assertTrue(verify_verhoeff("2345 6789 0124"))
        self.assertTrue(verify_verhoeff("4532-1234-5675"))
        self.assertTrue(verify_verhoeff("987654321096"))
        # Invalid Aadhaar
        self.assertFalse(verify_verhoeff("123456789012"))  # Starts with 1
        self.assertFalse(verify_verhoeff("234567890123"))  # Bad checksum
        self.assertFalse(verify_verhoeff("abc"))

    def test_luhn_credit_card_validation(self):
        # Known valid card numbers
        self.assertTrue(verify_luhn("4532015112830366"))
        self.assertTrue(verify_luhn("4532 0151 1283 0366"))
        self.assertTrue(verify_luhn("4532-0151-1283-0366"))
        # Invalid card numbers
        self.assertFalse(verify_luhn("4532015112830367"))
        self.assertFalse(verify_luhn("12345"))

    def test_email_detection(self):
        samples = ["rahul.verma@example.com", "priya_sharma@domain.co.in", "test.user+tag@gmail.com"]
        res = classify_column_privacy("user_email", "VARCHAR(255)", samples)
        self.assertEqual(res["detected_category"], "personal_identification")
        self.assertEqual(res["policy"], "sensitive")
        self.assertEqual(res["confidence"], "high")

    def test_indian_phone_detection(self):
        samples = ["+91 9876543210", "9123456780", "08765432109", "+91-7012345678"]
        res = classify_column_privacy("mobile_no", "VARCHAR(50)", samples)
        self.assertEqual(res["detected_category"], "personal_identification")
        self.assertEqual(res["policy"], "sensitive")
        self.assertEqual(res["confidence"], "high")

    def test_international_phone_detection(self):
        samples = ["+14155552671", "+442071838750", "+4930123456"]
        res = classify_column_privacy("phone_number", "VARCHAR(50)", samples)
        self.assertEqual(res["detected_category"], "personal_identification")
        self.assertEqual(res["policy"], "sensitive")

    def test_pan_detection(self):
        samples = ["ABCDE1234F", "XYZPK9876Q", "AABBC5555M"]
        res = classify_column_privacy("pan_card", "VARCHAR(20)", samples)
        self.assertEqual(res["detected_category"], "government_identification")
        self.assertEqual(res["policy"], "sensitive")
        self.assertEqual(res["confidence"], "high")

    def test_salary_compensation_detection(self):
        samples = [65000, 72000, 120000, 85000]
        res = classify_column_privacy("annual_salary", "DECIMAL(12,2)", samples)
        self.assertEqual(res["detected_category"], "confidential_business")
        self.assertEqual(res["policy"], "sensitive")

    def test_false_positive_guard_ordinary_business_keys(self):
        # Context guard: ordinary IDs must NOT be marked sensitive or government ID
        test_keys = ["id", "order_id", "product_id", "item_id", "category_id", "dept_id", "status_code"]
        for key in test_keys:
            res = classify_column_privacy(key, "INT", [1, 2, 3, 4, 5])
            self.assertEqual(res["policy"], "normal", f"Key '{key}' should have policy normal")
            self.assertEqual(res["detected_category"], "internal_identifier")

    def test_false_positive_guard_ordinary_numeric_metrics(self):
        # Context guard: operational numbers must NOT be marked sensitive
        test_metrics = ["quantity", "unit_price", "marks", "score", "discount", "rating"]
        for metric in test_metrics:
            res = classify_column_privacy(metric, "DECIMAL(10,2)", [10, 20.5, 95, 4.8])
            self.assertEqual(res["policy"], "normal", f"Metric '{metric}' should have policy normal")
            self.assertEqual(res["detected_category"], "general_numeric")

    def test_credentials_detection(self):
        samples = ["hash_abc123456", "token_987654"]
        res = classify_column_privacy("password_hash", "VARCHAR(255)", samples)
        self.assertEqual(res["detected_category"], "credentials_security")
        self.assertEqual(res["policy"], "restricted")
        self.assertEqual(res["status"], "protected")


class TestGroupBAIBoundaryRedaction(unittest.TestCase):
    """Verifies that sensitive data never escapes across the external AI boundary using mocked payload inspection."""

    def setUp(self):
        clear_recorded_ai_payloads()
        # Configure test mock AI handler
        def mock_llm_responder(system_prompt, user_prompt, payload_record):
            return "This is a mock AI analysis grounded strictly in provided non-sensitive information."
        set_mock_ai_handler(mock_llm_responder)

    def tearDown(self):
        clear_recorded_ai_payloads()
        set_mock_ai_handler(None)

    def test_raw_email_and_phone_never_reach_ai_provider(self):
        # Submit a prompt containing raw email and phone
        raw_prompt = "Customer rahul@gmail.com has mobile 9876543210 and requested assistance."
        res = call_llm(system_prompt="You are an assistant.", user_prompt=raw_prompt)

        # Inspect exact outgoing payloads recorded at the boundary
        payloads = get_recorded_ai_payloads()
        self.assertEqual(len(payloads), 1)
        outgoing_user_prompt = payloads[0]["user_prompt"]

        # Assert raw sensitive values are ABSENT from the transmitted payload
        self.assertNotIn("rahul@gmail.com", outgoing_user_prompt)
        self.assertNotIn("9876543210", outgoing_user_prompt)

        # Assert neutral placeholders are PRESENT
        self.assertIn("[EMAIL_REDACTED]", outgoing_user_prompt)
        self.assertIn("[PHONE_REDACTED]", outgoing_user_prompt)

    def test_restricted_fields_never_transmitted_in_records(self):
        records = [
            {"customer_id": 101, "email": "rahul@gmail.com", "aadhaar_no": "200000000002", "password_hash": "secret_hash"},
            {"customer_id": 102, "email": "priya@gmail.com", "aadhaar_no": "453212345674", "password_hash": "secret_hash2"}
        ]
        policies = {
            "email": {"policy": "sensitive", "detected_category": "personal_identification"},
            "aadhaar_no": {"policy": "restricted", "detected_category": "government_identification"},
            "password_hash": {"policy": "restricted", "detected_category": "credentials_security"},
            "customer_id": {"policy": "normal", "detected_category": "internal_identifier"}
        }

        clean = redact_records_for_ai(records, policies)

        for row in clean:
            self.assertEqual(row["email"], "[EMAIL_REDACTED]")
            self.assertEqual(row["aadhaar_no"], "[RESTRICTED_FIELD_EXCLUDED]")
            self.assertEqual(row["password_hash"], "[RESTRICTED_FIELD_EXCLUDED]")
            self.assertIn(row["customer_id"], (101, 102))

    def test_query_result_summary_redaction(self):
        records = [
            {"Name": "Rahul Verma", "Email": "rahul@gmail.com", "Salary": 65000, "Dept": "Engineering"},
            {"Name": "Priya Sharma", "Email": "priya@gmail.com", "Salary": 72000, "Dept": "Design"},
            {"Name": "Amit Kumar", "Email": "amit@gmail.com", "Salary": 58000, "Dept": "Sales"}
        ]
        policies = {
            "Email": {"policy": "sensitive", "detected_category": "personal_identification"},
            "Salary": {"policy": "sensitive", "detected_category": "confidential_business"}
        }

        summary = generate_summary("Find top employees", records, policies=policies)

        # Inspect AI payload
        payloads = get_recorded_ai_payloads()
        self.assertGreater(len(payloads), 0)
        sent_body = payloads[0]["user_prompt"]

        # Verify no raw email or salary reaches AI
        self.assertNotIn("rahul@gmail.com", sent_body)
        self.assertNotIn("priya@gmail.com", sent_body)
        self.assertIn("[EMAIL_REDACTED]", sent_body)
        self.assertIn("[SENSITIVE_VALUE_REDACTED]", sent_body)

    def test_sensitive_user_literal_parameterization(self):
        question = "Find customer whose email is rahul@gmail.com and PAN is ABCDE1234F"
        sanitized_q, param_store = extract_sensitive_query_parameters(question)

        # Assert question for LLM is parameterized
        self.assertNotIn("rahul@gmail.com", sanitized_q)
        self.assertNotIn("ABCDE1234F", sanitized_q)
        self.assertIn("[EMAIL_PARAM_1]", sanitized_q)
        self.assertIn("[PAN_PARAM_1]", sanitized_q)

        # Assert parameter store holds exact original values
        self.assertEqual(param_store["[EMAIL_PARAM_1]"], "rahul@gmail.com")
        self.assertEqual(param_store["[PAN_PARAM_1]"], "ABCDE1234F")

        # Test AST resolution
        generated_sql = "SELECT * FROM customers WHERE email = '[EMAIL_PARAM_1]' AND pan = '[PAN_PARAM_1]'"
        resolved_sql = resolve_query_parameters_ast(generated_sql, param_store)

        self.assertIn("rahul@gmail.com", resolved_sql)
        self.assertIn("ABCDE1234F", resolved_sql)
        self.assertNotIn("[EMAIL_PARAM_1]", resolved_sql)

    def test_small_group_disclosure_safeguard(self):
        # When 1 or 2 rows returned, personal identifiers must be masked to prevent individual disclosure
        records = [
            {"Name": "Rahul Verma", "Customer_ID": "CUST_99", "Order_Total": 500}
        ]
        policies = {
            "Name": {"policy": "sensitive", "detected_category": "personal_identification"},
            "Customer_ID": {"policy": "normal", "detected_category": "confidential_business"},
            "Order_Total": {"policy": "normal", "detected_category": "general_numeric"}
        }
        clean = redact_records_for_ai(records, policies)
        self.assertEqual(clean[0]["Customer_ID"], "[IDENTIFIER_REDACTED]")
        self.assertEqual(clean[0]["Order_Total"], 500)


class TestGroupCAuthorizedUserVisibility(unittest.TestCase):
    """Verifies that authorized users retain 100% full original data in Preview, Queries, and Exports."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.table_name = "test_privacy_dataset_usr_tenant1"
        cls.user_id = "tenant1"

        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_name}`"))
            conn.execute(text(f"""
                CREATE TABLE `{cls.table_name}` (
                    `id` INT PRIMARY KEY AUTO_INCREMENT,
                    `customer_name` VARCHAR(100),
                    `email` VARCHAR(100),
                    `phone` VARCHAR(50),
                    `salary` DECIMAL(10,2)
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.table_name}` (customer_name, email, phone, salary)
                VALUES 
                ('Rahul Verma', 'rahul@gmail.com', '9876543210', 65000.00),
                ('Priya Sharma', 'priya@gmail.com', '9123456780', 72000.00)
            """))
            conn.commit()

    @classmethod
    def tearDownClass(cls):
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_name}`"))
            conn.commit()

    def test_database_records_remain_unmodified(self):
        # Run privacy scan
        scan_and_save_dataset_privacy(user_id=self.user_id, table_name=self.table_name, force_rescan=True)

        # Direct database query inspection: verify database values are 100% untouched
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT * FROM `{self.table_name}` ORDER BY id ASC")).fetchall()

        self.assertEqual(len(rows), 2)
        # Rahul
        self.assertEqual(rows[0]._mapping["email"], "rahul@gmail.com")
        self.assertEqual(rows[0]._mapping["phone"], "9876543210")
        self.assertEqual(float(rows[0]._mapping["salary"]), 65000.00)
        # Priya
        self.assertEqual(rows[1]._mapping["email"], "priya@gmail.com")
        self.assertEqual(rows[1]._mapping["phone"], "9123456780")
        self.assertEqual(float(rows[1]._mapping["salary"]), 72000.00)

    def test_dataset_overview_metrics(self):
        overview = get_privacy_overview(user_id=self.user_id, table_name=self.table_name)
        self.assertEqual(overview["table_name"], self.table_name)
        self.assertGreaterEqual(overview["columns_scanned"], 4)
        # email and phone should be detected as sensitive
        self.assertGreaterEqual(overview["sensitive_columns_count"], 2)


class TestGroupDPoliciesAndTenantIsolation(unittest.TestCase):
    """Verifies server-side policy updates, tenant isolation, and audit logging."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.table_name = "test_policy_tenant_usr_tenant2"
        cls.user_id = "tenant2"

        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_name}`"))
            conn.execute(text(f"""
                CREATE TABLE `{cls.table_name}` (
                    `id` INT PRIMARY KEY AUTO_INCREMENT,
                    `contact_name` VARCHAR(100),
                    `custom_secret` VARCHAR(100)
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.table_name}` (contact_name, custom_secret)
                VALUES ('Alice', 'top_secret_code_123')
            """))
            conn.commit()

    @classmethod
    def tearDownClass(cls):
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_name}`"))
            conn.commit()

    def test_policy_update_and_audit(self):
        # Update policy for custom_secret to restricted
        res = update_column_policy(
            user_id=self.user_id,
            table_name=self.table_name,
            column_name="custom_secret",
            policy="restricted"
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["policy"], "restricted")

        # Fetch updated policies
        policies = get_dataset_column_policies(user_id=self.user_id, table_name=self.table_name)
        self.assertEqual(policies["custom_secret"]["policy"], "restricted")

        # Check audit log
        audit_logs = get_privacy_audit_logs(user_id=self.user_id, table_name=self.table_name)
        self.assertGreater(len(audit_logs), 0)
        policy_event = [l for l in audit_logs if l["event_type"] == "policy_change"]
        self.assertGreater(len(policy_event), 0)
        # Verify no raw secret is recorded in audit details
        audit_text = json.dumps(policy_event[0]["details"])
        self.assertNotIn("top_secret_code_123", audit_text)

    def test_tenant_isolation_on_policies(self):
        # Tenant 2 sets custom policy for contact_name to sensitive
        update_column_policy(
            user_id="tenant2",
            table_name=self.table_name,
            column_name="contact_name",
            policy="sensitive"
        )
        t2_policies = get_dataset_column_policies(user_id="tenant2", table_name=self.table_name)
        self.assertEqual(t2_policies["contact_name"]["policy"], "sensitive")

        # Tenant 3 scans and has isolated default policy for contact_name (normal)
        scan_and_save_dataset_privacy(user_id="tenant3", table_name=self.table_name, force_rescan=True)
        t3_policies = get_dataset_column_policies(user_id="tenant3", table_name=self.table_name)
        self.assertEqual(t3_policies["contact_name"]["policy"], "normal")

        # Modifying tenant 3's policy does NOT affect tenant 2
        update_column_policy(
            user_id="tenant3",
            table_name=self.table_name,
            column_name="contact_name",
            policy="restricted"
        )
        t2_refreshed = get_dataset_column_policies(user_id="tenant2", table_name=self.table_name)
        t3_refreshed = get_dataset_column_policies(user_id="tenant3", table_name=self.table_name)

        self.assertEqual(t2_refreshed["contact_name"]["policy"], "sensitive")
        self.assertEqual(t3_refreshed["contact_name"]["policy"], "restricted")


class TestGroupEEndToEndPrivacyGuardianPipeline(unittest.TestCase):
    """Verifies complete end-to-end user workflows, API endpoints, and natural-language queries."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.table_name = "customers_usr_123"
        cls.user_id = "usr_123"

        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_name}`"))
            conn.execute(text(f"""
                CREATE TABLE `{cls.table_name}` (
                    `id` INT PRIMARY KEY AUTO_INCREMENT,
                    `customer_name` VARCHAR(100),
                    `email` VARCHAR(100),
                    `phone` VARCHAR(50),
                    `salary` DECIMAL(10,2)
                )
            """))
            conn.execute(text(f"""
                INSERT INTO `{cls.table_name}` (customer_name, email, phone, salary)
                VALUES 
                ('Rahul Verma', 'rahul@gmail.com', '9876543210', 65000.00),
                ('Priya Sharma', 'priya@gmail.com', '9123456780', 72000.00)
            """))
            conn.commit()

    @classmethod
    def tearDownClass(cls):
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_name}`"))
            conn.commit()

    def setUp(self):
        clear_recorded_ai_payloads()

    def tearDown(self):
        clear_recorded_ai_payloads()
        set_mock_ai_handler(None)

    def test_natural_language_query_exact_match_with_sensitive_literal(self):
        user_question = "Find the customer whose email is rahul@gmail.com"

        # 1. Parameterize user question locally
        sanitized_q, param_store = extract_sensitive_query_parameters(user_question)
        self.assertNotIn("rahul@gmail.com", sanitized_q)
        self.assertIn("[EMAIL_PARAM_1]", sanitized_q)

        # 2. Mock external LLM to act as SQL generator receiving the sanitized prompt
        def mock_sql_gen(sys_p, user_p, payload):
            # Assert incoming prompt to LLM provider does NOT contain raw email
            self.assertNotIn("rahul@gmail.com", user_p)
            return "SELECT * FROM `customers` WHERE `email` = '[EMAIL_PARAM_1]'"

        set_mock_ai_handler(mock_sql_gen)

        # Generate SQL
        raw_sql = call_llm("You are SQL generator.", f"Question: {sanitized_q}")

        # 3. Resolve parameters via SQLGlot AST on the backend
        executable_sql = resolve_query_parameters_ast(raw_sql, param_store)
        self.assertIn("rahul@gmail.com", executable_sql)
        self.assertNotIn("[EMAIL_PARAM_1]", executable_sql)

        # Translate friendly table to physical table
        physical_sql = executable_sql.replace("`customers`", f"`{self.table_name}`")

        # 4. Execute query locally on database
        with engine.connect() as conn:
            rows = [dict(r._mapping) for r in conn.execute(text(physical_sql))]

        self.assertEqual(len(rows), 1)
        # 5. Verify FULL original data for authorized user
        self.assertEqual(rows[0]["email"], "rahul@gmail.com")
        self.assertEqual(rows[0]["customer_name"], "Rahul Verma")

        # 6. Verify summary generation sanitizes across AI boundary
        policies = get_dataset_column_policies(self.user_id, self.table_name)
        clear_recorded_ai_payloads()

        def mock_summary_gen(sys_p, user_p, payload):
            # The prompt to LLM MUST have the email redacted
            self.assertNotIn("rahul@gmail.com", user_p)
            self.assertIn("[EMAIL_REDACTED]", user_p)
            return "Found 1 matching customer record with email [EMAIL_REDACTED]."

        set_mock_ai_handler(mock_summary_gen)
        summary = generate_summary(sanitized_q, rows, policies=policies)

        # 7. Verify all outgoing recorded payloads NEVER contained the raw email
        payloads = get_recorded_ai_payloads()
        self.assertGreater(len(payloads), 0)
        for p in payloads:
            all_content = f"{p['system_prompt']} {p['user_prompt']}"
            self.assertNotIn("rahul@gmail.com", all_content)

    def test_export_csv_retains_full_original_values(self):
        from app.services.export_service import generate_csv
        records = [
            {"Name": "Rahul Verma", "Email": "rahul@gmail.com", "Phone": "9876543210", "Salary": 65000}
        ]
        csv_bytes = generate_csv(records)
        csv_text = csv_bytes.decode("utf-8")

        # Authorized CSV export must retain complete values
        self.assertIn("rahul@gmail.com", csv_text)
        self.assertIn("9876543210", csv_text)
        self.assertIn("65000", csv_text)

    def test_api_client_privacy_routes(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.services.auth_service import create_access_token

        token = create_access_token(user_id=123)
        client = TestClient(app)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-User-ID": self.user_id,
            "X-Table-Name": self.table_name
        }

        # 1. GET overview
        res_overview = client.get("/api/privacy/overview", headers=headers)
        self.assertEqual(res_overview.status_code, 200)
        ov_data = res_overview.json()
        self.assertEqual(ov_data["table_name"], self.table_name)
        self.assertGreaterEqual(ov_data["columns_scanned"], 4)

        # 2. Rescan
        res_scan = client.post("/api/privacy/scan", headers=headers)
        self.assertEqual(res_scan.status_code, 200)

        # 3. PUT policy update
        res_update = client.put(
            "/api/privacy/policy",
            headers=headers,
            json={"column_name": "salary", "policy": "restricted"}
        )
        self.assertEqual(res_update.status_code, 200)
        self.assertEqual(res_update.json()["policy"], "restricted")

        # 4. GET audit trail
        res_audit = client.get("/api/privacy/audit", headers=headers)
        self.assertEqual(res_audit.status_code, 200)
        audit_data = res_audit.json()
        self.assertTrue(audit_data["success"])
        self.assertGreater(len(audit_data["logs"]), 0)


if __name__ == "__main__":
    unittest.main()
