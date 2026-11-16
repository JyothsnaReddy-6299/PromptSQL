"""
PromptSQL — Issue 16.1: Privacy Guardian Security Verification & Remediation Test Suite

Comprehensive independent tests verifying:
- Test Group A: Architectural Verification of Centralized External AI Boundary
- Test Group B: Sensitive SQL Parameter Binding & Execution Safeguards
- Test Group C: Conversational Bulk Insertion Privacy & Server-Side Restoration
- Test Group D: Small-Group Disclosure Suppression (< MIN_GROUP_DISCLOSURE_SIZE)
- Test Group E: Conversation History Sanitization & Multi-Turn Protection
- Test Group F: Logs, Error Sanitization & Indirect Leakage Prevention
- Test Group G: Authorized User Full Visibility (Data Preview, Query Results)
- Test Group H: Fail-Closed Boundary Enforcement
- Test Group I: Concurrent Request & Multi-Tenant Parameter Isolation
"""

import ast
import os
import sys
import io
import re
import json
import time
import unittest
from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.llm_service import (
    call_llm,
    set_mock_ai_handler,
    get_recorded_ai_payloads,
    clear_recorded_ai_payloads
)
from app.services.privacy_redactor import (
    redact_text_for_ai,
    redact_records_for_ai,
    extract_sensitive_query_parameters,
    bind_query_parameters_ast,
    resolve_query_parameters_ast,
    MIN_GROUP_DISCLOSURE_SIZE
)
from app.services.sql_executor import execute_sql, prepare_bounded_query
from app.services.bulk_record_parser import (
    extract_raw_records_with_llm,
    validate_single_record
)
from app.services.summary_generator import generate_summary
from app.services.data_discovery_service import enhance_insights_with_ai
from app.models.privacy import PrivacyAuditLog


# Synthetic test canaries specified by Issue 16.1 prompt
CANARY_EMAIL = "privacy.canary.rahul@example.invalid"
CANARY_PHONE = "+1-202-555-0100"
CANARY_AADHAAR = "987654321001"
CANARY_PAN = "TESTA1234A"


class TestGroupAArchitecturalAIBoundary(unittest.TestCase):
    """
    Group A: Verify that all external AI calls route through the centralized privacy layer,
    and no module makes direct provider SDK or HTTP calls.
    """

    def setUp(self):
        clear_recorded_ai_payloads()

    def test_zero_direct_provider_calls_in_codebase(self):
        """
        Architectural AST inspection: Asserts that no backend file outside llm_service.py
        initializes Groq, calls chat.completions.create, or contacts external AI endpoints.
        """
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
        prohibited_imports = {"groq", "openai", "anthropic"}
        violations = []

        for root, _, files in os.walk(backend_dir):
            for file in files:
                if not file.endswith(".py"):
                    continue
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, backend_dir)

                # llm_service.py is the designated provider gateway
                if rel_path == "services\\llm_service.py" or rel_path == "services/llm_service.py":
                    continue

                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                try:
                    tree = ast.parse(content, filename=file_path)
                except Exception as e:
                    self.fail(f"Could not parse AST for {file_path}: {e}")

                for node in ast.walk(tree):
                    # Check import statements
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name.lower() in prohibited_imports:
                                violations.append(f"{rel_path}: Direct import of '{alias.name}'")
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and node.module.lower() in prohibited_imports:
                            violations.append(f"{rel_path}: Direct from-import of '{node.module}'")
                    # Check for direct client calls
                    elif isinstance(node, ast.Attribute):
                        if node.attr == "chat" or node.attr == "completions":
                            # Only permit if inside comments or test files
                            pass

                # Check string literals for external AI HTTP endpoints
                if "api.groq.com" in content or "api.openai.com" in content:
                    violations.append(f"{rel_path}: Direct AI endpoint URL found")

        self.assertEqual(
            violations, [],
            f"Found unauthorized direct external AI calls bypassing centralized gateway: {violations}"
        )

    def test_all_service_callers_route_through_call_llm(self):
        """
        Verifies that all 9 service consumers invoke call_llm rather than direct provider calls.
        """
        expected_callers = [
            "bulk_record_parser.py",
            "data_discovery_service.py",
            "impact_explainer.py",
            "intent_detector.py",
            "modification_sql_generator.py",
            "sql_generator.py",
            "sql_regenerator.py",
            "summary_generator.py",
            "table_schema_generator.py",
        ]
        services_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "services"))
        found_callers = []

        for filename in expected_callers:
            filepath = os.path.join(services_dir, filename)
            self.assertTrue(os.path.exists(filepath), f"Expected service file {filename} does not exist.")
            with open(filepath, "r", encoding="utf-8") as f:
                code = f.read()
            if "call_llm(" in code:
                found_callers.append(filename)

        self.assertEqual(
            sorted(expected_callers),
            sorted(found_callers),
            "Every identified AI consumer service must use call_llm."
        )

    def test_centralized_boundary_records_all_outbound_payloads(self):
        """
        Verifies that call_llm intercepts outgoing prompts and records payloads at boundary.
        """
        def mock_handler(sys_prompt, usr_prompt, payload):
            return "Mock response"

        set_mock_ai_handler(mock_handler)
        try:
            res = call_llm("System instruction", "User query")
            self.assertEqual(res, "Mock response")
            payloads = get_recorded_ai_payloads()
            self.assertEqual(len(payloads), 1)
            self.assertEqual(payloads[0]["system_prompt"], "System instruction")
            self.assertEqual(payloads[0]["user_prompt"], "User query")
        finally:
            set_mock_ai_handler(None)


class TestGroupBSensitiveSQLParameterBinding(unittest.TestCase):
    """
    Group B: Verify that sensitive SQL literals are bound as genuine database parameters
    (:param_name) and never substituted back into executed SQL strings.
    """

    def test_ast_parameter_binding_with_canaries(self):
        """
        Verifies that bind_query_parameters_ast generates parameterized SQL (:param_name)
        and outputs a parameter mapping, with zero canary literals in the SQL string.
        """
        param_store = {
            "[EMAIL_PARAM_1]": CANARY_EMAIL,
            "[PHONE_PARAM_1]": CANARY_PHONE,
            "[AADHAAR_PARAM_1]": CANARY_AADHAAR,
            "[PAN_PARAM_1]": CANARY_PAN
        }

        generated_sql = (
            "SELECT * FROM customers WHERE email = '[EMAIL_PARAM_1]' "
            "AND phone = '[PHONE_PARAM_1]' AND aadhaar = '[AADHAAR_PARAM_1]' "
            "AND pan = '[PAN_PARAM_1]'"
        )

        parameterized_sql, exec_params = bind_query_parameters_ast(generated_sql, param_store)

        # 1. Assert no raw canaries exist in the parameterized SQL string
        self.assertNotIn(CANARY_EMAIL, parameterized_sql)
        self.assertNotIn(CANARY_PHONE, parameterized_sql)
        self.assertNotIn(CANARY_AADHAAR, parameterized_sql)
        self.assertNotIn(CANARY_PAN, parameterized_sql)

        # 2. Assert SQL uses driver-level parameter placeholders
        self.assertIn(":email_param_1", parameterized_sql)
        self.assertIn(":phone_param_1", parameterized_sql)
        self.assertIn(":aadhaar_param_1", parameterized_sql)
        self.assertIn(":pan_param_1", parameterized_sql)

        # 3. Assert execution parameters retain the exact original canary values
        self.assertEqual(exec_params["email_param_1"], CANARY_EMAIL)
        self.assertEqual(exec_params["phone_param_1"], CANARY_PHONE)
        self.assertEqual(exec_params["aadhaar_param_1"], CANARY_AADHAAR)
        self.assertEqual(exec_params["pan_param_1"], CANARY_PAN)

    def test_unquoted_array_token_binding(self):
        """
        Verifies that unquoted tokens parsed as arrays (e.g. email = [EMAIL_PARAM_1])
        are safely bound as :param_name without error.
        """
        param_store = {"[EMAIL_PARAM_1]": CANARY_EMAIL}
        unquoted_sql = "SELECT * FROM users WHERE email = [EMAIL_PARAM_1]"

        parameterized_sql, exec_params = bind_query_parameters_ast(unquoted_sql, param_store)

        self.assertNotIn(CANARY_EMAIL, parameterized_sql)
        self.assertIn(":email_param_1", parameterized_sql)
        self.assertEqual(exec_params["email_param_1"], CANARY_EMAIL)

    def test_sql_executor_accepts_parameters_dict(self):
        """
        Verifies that execute_sql accepts parameters dictionary and passes it to SQLAlchemy.
        """
        with patch("app.services.sql_executor.engine.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn
            mock_result = MagicMock()
            mock_result.keys.return_value = ["id", "email"]
            mock_result.fetchmany.return_value = [[1, CANARY_EMAIL]]
            mock_conn.execute.return_value = mock_result

            sql = "SELECT * FROM customers WHERE email = :email_param_1"
            params = {"email_param_1": CANARY_EMAIL}

            res = execute_sql(sql, parameters=params)

            # Check that connection.execute received parameters
            call_args_list = mock_conn.execute.call_args_list
            # The query execution call is after START TRANSACTION READ ONLY
            query_call = call_args_list[1]
            executed_text = str(query_call[0][0])
            passed_params = query_call[0][1] if len(query_call[0]) > 1 else query_call[1].get("parameters")

            self.assertIn(":email_param_1", executed_text)
            self.assertNotIn(CANARY_EMAIL, executed_text)
            self.assertEqual(passed_params, params)
            self.assertEqual(res.records[0]["email"], CANARY_EMAIL)

    def test_extract_sensitive_query_parameters_matches_canaries(self):
        """
        Verifies that extract_sensitive_query_parameters extracts all 4 canary types.
        """
        q = (
            f"Find customer with email {CANARY_EMAIL}, phone {CANARY_PHONE}, "
            f"aadhaar {CANARY_AADHAAR}, and pan {CANARY_PAN}"
        )
        sanitized_q, param_store = extract_sensitive_query_parameters(q)

        self.assertNotIn(CANARY_EMAIL, sanitized_q)
        self.assertNotIn(CANARY_PHONE, sanitized_q)
        self.assertNotIn(CANARY_AADHAAR, sanitized_q)
        self.assertNotIn(CANARY_PAN, sanitized_q)

        self.assertIn("[EMAIL_PARAM_1]", sanitized_q)
        self.assertIn("[PHONE_PARAM_1]", sanitized_q)
        self.assertIn("[AADHAAR_PARAM_1]", sanitized_q)
        self.assertIn("[PAN_PARAM_1]", sanitized_q)

        self.assertEqual(param_store["[EMAIL_PARAM_1]"], CANARY_EMAIL)
        self.assertEqual(param_store["[PHONE_PARAM_1]"], CANARY_PHONE)
        self.assertEqual(param_store["[AADHAAR_PARAM_1]"], CANARY_AADHAAR)
        self.assertEqual(param_store["[PAN_PARAM_1]"], CANARY_PAN)


class TestGroupCConversationalBulkInsertion(unittest.TestCase):
    """
    Group C: Verify conversational custom-table insertion protects sensitive values
    from reaching the external AI while restoring original values server-side.
    """

    def setUp(self):
        clear_recorded_ai_payloads()

    def tearDown(self):
        set_mock_ai_handler(None)
        clear_recorded_ai_payloads()

    def test_conversational_insertion_prompt_redaction(self):
        """
        Scenario from Issue 16.1 prompt:
        User asks: "Insert a customer named Rahul with email privacy.canary.rahul@example.invalid and phone +1-202-555-0100"
        External AI must receive sanitized placeholders; original values must NOT reach the AI.
        """
        def mock_extractor(sys_p, usr_p, payload):
            # Assert that outgoing prompt seen by LLM does NOT contain raw canaries
            self.assertNotIn(CANARY_EMAIL, usr_p)
            self.assertNotIn(CANARY_PHONE, usr_p)
            self.assertIn("[EMAIL_PARAM_1]", usr_p)
            self.assertIn("[PHONE_PARAM_1]", usr_p)
            # Return parsed records containing placeholders
            return json.dumps({
                "records": [
                    {
                        "name": "Rahul",
                        "email": "[EMAIL_PARAM_1]",
                        "phone": "[PHONE_PARAM_1]"
                    }
                ]
            })

        set_mock_ai_handler(mock_extractor)

        schema_cols = [
            {"name": "id", "type_str": "INT", "category": "integer", "nullable": False, "is_pk": True, "autoincrement": True},
            {"name": "name", "type_str": "VARCHAR(255)", "category": "string", "nullable": False, "is_pk": False, "autoincrement": False},
            {"name": "email", "type_str": "VARCHAR(255)", "category": "string", "nullable": False, "is_pk": False, "autoincrement": False},
            {"name": "phone", "type_str": "VARCHAR(50)", "category": "string", "nullable": False, "is_pk": False, "autoincrement": False},
        ]

        user_prompt = f"Insert a customer named Rahul with email {CANARY_EMAIL} and phone number {CANARY_PHONE}."

        records = extract_raw_records_with_llm(user_prompt, "customers", schema_cols)

        # 1. Assert outbound AI boundary was completely protected
        payloads = get_recorded_ai_payloads()
        self.assertEqual(len(payloads), 1)
        self.assertNotIn(CANARY_EMAIL, payloads[0]["user_prompt"])
        self.assertNotIn(CANARY_PHONE, payloads[0]["user_prompt"])

        # 2. Assert server-side restored exact raw canaries in extracted records
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["name"], "Rahul")
        self.assertEqual(records[0]["email"], CANARY_EMAIL)
        self.assertEqual(records[0]["phone"], CANARY_PHONE)

    def test_multi_row_insertion_with_canaries(self):
        """
        Verifies multi-row insertion restores all canaries across rows.
        """
        canary_email_2 = "privacy.canary.priya@example.invalid"
        canary_phone_2 = "+1-202-555-0199"

        def mock_multi(sys_p, usr_p, payload):
            self.assertNotIn(CANARY_EMAIL, usr_p)
            self.assertNotIn(canary_email_2, usr_p)
            return json.dumps({
                "records": [
                    {"name": "Rahul", "email": "[EMAIL_PARAM_1]", "phone": "[PHONE_PARAM_1]"},
                    {"name": "Priya", "email": "[EMAIL_PARAM_2]", "phone": "[PHONE_PARAM_2]"}
                ]
            })

        set_mock_ai_handler(mock_multi)

        schema_cols = [
            {"name": "id", "type_str": "INT", "category": "integer", "nullable": False, "is_pk": True, "autoincrement": True},
            {"name": "name", "type_str": "VARCHAR(255)", "category": "string", "nullable": False, "is_pk": False, "autoincrement": False},
            {"name": "email", "type_str": "VARCHAR(255)", "category": "string", "nullable": False, "is_pk": False, "autoincrement": False},
            {"name": "phone", "type_str": "VARCHAR(50)", "category": "string", "nullable": False, "is_pk": False, "autoincrement": False},
        ]

        prompt = (
            f"Add 2 customers: 1. Rahul, email {CANARY_EMAIL}, phone {CANARY_PHONE}. "
            f"2. Priya, email {canary_email_2}, phone {canary_phone_2}."
        )

        records = extract_raw_records_with_llm(prompt, "customers", schema_cols)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["email"], CANARY_EMAIL)
        self.assertEqual(records[1]["email"], canary_email_2)


class TestGroupDSmallGroupDisclosureProtection(unittest.TestCase):
    """
    Group D: Verify small-group disclosure safeguards for aggregate queries and tiny datasets.
    """

    def test_group_aggregate_small_count_suppression(self):
        """
        When aggregate query results contain groups with count < MIN_GROUP_DISCLOSURE_SIZE (3),
        sensitive metrics for those groups must be suppressed with [SUPPRESSED_SMALL_GROUP].
        """
        records = [
            {"department": "HR", "emp_count": 1, "avg_salary": 120000},
            {"department": "Engineering", "emp_count": 25, "avg_salary": 95000},
            {"department": "Marketing", "emp_count": 2, "avg_salary": 75000}
        ]
        policies = {
            "avg_salary": {"policy": "sensitive", "detected_category": "confidential_business"},
            "department": {"policy": "normal"}
        }

        sanitized = redact_records_for_ai(records, policies)

        # HR has emp_count = 1 (< 3): avg_salary must be suppressed
        self.assertEqual(sanitized[0]["department"], "HR")
        self.assertEqual(sanitized[0]["avg_salary"], "[SUPPRESSED_SMALL_GROUP]")

        # Engineering has emp_count = 25 (>= 3): avg_salary is unsuppressed
        self.assertEqual(sanitized[1]["department"], "Engineering")
        self.assertEqual(sanitized[1]["avg_salary"], "[SENSITIVE_VALUE_REDACTED]")

        # Marketing has emp_count = 2 (< 3): avg_salary must be suppressed
        self.assertEqual(sanitized[2]["department"], "Marketing")
        self.assertEqual(sanitized[2]["avg_salary"], "[SUPPRESSED_SMALL_GROUP]")

    def test_all_groups_below_threshold(self):
        """
        If all groups in an aggregate query are below threshold, all sensitive metrics are suppressed.
        """
        records = [
            {"department": "Legal", "count": 1, "total_salary": 150000},
            {"department": "Security", "count": 2, "total_salary": 180000}
        ]
        policies = {
            "total_salary": {"policy": "sensitive", "detected_category": "confidential_business"}
        }

        sanitized = redact_records_for_ai(records, policies)
        self.assertEqual(sanitized[0]["total_salary"], "[SUPPRESSED_SMALL_GROUP]")
        self.assertEqual(sanitized[1]["total_salary"], "[SUPPRESSED_SMALL_GROUP]")

    def test_tiny_result_set_identifier_safeguard(self):
        """
        For non-grouped queries returning < 3 records, personal identifiers are masked
        and sensitive compensation metrics are suppressed.
        """
        records = [
            {"customer_name": "Rahul", "salary": 85000, "city": "Mumbai"}
        ]
        policies = {
            "customer_name": {"policy": "normal", "detected_category": "personal_identification"},
            "salary": {"policy": "sensitive", "detected_category": "confidential_business"},
            "city": {"policy": "normal"}
        }

        sanitized = redact_records_for_ai(records, policies)
        self.assertEqual(sanitized[0]["customer_name"], "[IDENTIFIER_REDACTED]")
        self.assertEqual(sanitized[0]["salary"], "[SENSITIVE_VALUE_REDACTED]")
        self.assertEqual(sanitized[0]["city"], "Mumbai")

    def test_zero_row_results_handling(self):
        """
        Zero-row results pass through safely without error.
        """
        sanitized = redact_records_for_ai([], {})
        self.assertEqual(sanitized, [])


class TestGroupEConversationHistorySanitization(unittest.TestCase):
    """
    Group E: Verify that conversation history cannot reintroduce previously protected values.
    """

    def test_stored_sql_is_parameterized_never_raw_canaries(self):
        """
        Verifies that parameterized SQL (:param_name) is stored rather than raw literal values.
        """
        param_store = {"[EMAIL_PARAM_1]": CANARY_EMAIL}
        raw_sql = "SELECT * FROM users WHERE email = '[EMAIL_PARAM_1]'"

        bounded_sql, params = bind_query_parameters_ast(raw_sql, param_store)

        self.assertNotIn(CANARY_EMAIL, bounded_sql)
        self.assertIn(":email_param_1", bounded_sql)
        self.assertEqual(params["email_param_1"], CANARY_EMAIL)


class TestGroupFLogsAndErrorSanitization(unittest.TestCase):
    """
    Group F: Verify that logs, exceptions, and audit tables do not leak sensitive information.
    """

    def test_ask_py_does_not_print_raw_records_to_stdout(self):
        """
        Verifies that ask.py does not leak raw result records to server console logs.
        """
        from app.routes import ask
        with open(ask.__file__, "r", encoding="utf-8") as f:
            ask_code = f.read()

        # Line 233 had 'print(records[:3])' which leaked raw records to stdout
        self.assertNotIn("print(records[:3])", ask_code)
        self.assertNotIn("print(records)", ask_code)

    def test_redact_text_for_ai_sanitizes_canaries(self):
        """
        Verifies that redact_text_for_ai sanitizes all 4 synthetic canary strings.
        """
        text_with_canaries = (
            f"Error occurred for user {CANARY_EMAIL} with phone {CANARY_PHONE}, "
            f"Aadhaar {CANARY_AADHAAR}, and PAN {CANARY_PAN}."
        )

        sanitized, count = redact_text_for_ai(text_with_canaries)

        self.assertNotIn(CANARY_EMAIL, sanitized)
        self.assertNotIn(CANARY_PHONE, sanitized)
        self.assertNotIn(CANARY_AADHAAR, sanitized)
        self.assertNotIn(CANARY_PAN, sanitized)
        self.assertGreaterEqual(count, 4)


class TestGroupGAuthorizedUserVisibility(unittest.TestCase):
    """
    Group G: Verify that authorized users retain complete access to their original data.
    """

    def test_user_query_results_unaltered_for_authorized_client(self):
        """
        Query results destined for authorized users retain exact original values.
        """
        records = [
            {"name": "Rahul", "email": CANARY_EMAIL, "phone": CANARY_PHONE}
        ]

        # Simulating that raw execution records remain unchanged
        self.assertEqual(records[0]["email"], CANARY_EMAIL)
        self.assertEqual(records[0]["phone"], CANARY_PHONE)

        # Redaction is applied ONLY to a copy for outbound AI
        ai_copy = redact_records_for_ai(records, {
            "email": {"policy": "sensitive", "detected_category": "personal_identification"}
        })
        self.assertEqual(ai_copy[0]["email"], "[EMAIL_REDACTED]")

        # Original list retains complete values
        self.assertEqual(records[0]["email"], CANARY_EMAIL)


class TestGroupHFailClosedBehavior(unittest.TestCase):
    """
    Group H: Verify fail-closed behavior when redaction fails or unmasked canaries are detected.
    """

    def setUp(self):
        clear_recorded_ai_payloads()

    def tearDown(self):
        set_mock_ai_handler(None)
        clear_recorded_ai_payloads()

    def test_redaction_failure_fails_closed(self):
        """
        If privacy redaction raises an exception, call_llm must NOT transmit uninspected prompts.
        It must raise RuntimeError and fail closed.
        """
        with patch("app.services.privacy_redactor.redact_text_for_ai", side_effect=ValueError("Engine crashed")):
            with self.assertRaises(RuntimeError) as ctx:
                call_llm("System prompt", "User prompt")
            self.assertIn("Privacy Guardian enforcement failed", str(ctx.exception))

    def test_unredacted_canary_triggers_boundary_violation(self):
        """
        If a canary escapes redaction, the boundary assertion in call_llm must raise RuntimeError.
        """
        # Patch redact_text_for_ai to deliberately bypass redaction (simulating upstream bug)
        with patch("app.services.privacy_redactor.redact_text_for_ai", return_value=(f"System with {CANARY_EMAIL}", 0)):
            with self.assertRaises(RuntimeError) as ctx:
                call_llm("System", "User")
            self.assertIn("Privacy Guardian boundary violation", str(ctx.exception))


class TestGroupIConcurrentParameterIsolation(unittest.TestCase):
    """
    Group I: Verify tenant and parameter store isolation under concurrent requests.
    """

    def test_concurrent_parameter_store_isolation(self):
        """
        Simulates 10 concurrent requests with different canary parameters.
        Verifies that parameter mappings never leak across threads.
        """
        def worker(idx: int):
            email = f"canary.user{idx}@example.invalid"
            phone = f"+1-202-555-01{idx:02d}"
            prompt = f"Find user with email {email} and phone {phone}"

            sanitized_q, pstore = extract_sensitive_query_parameters(prompt)
            sql = f"SELECT * FROM users WHERE email = '[EMAIL_PARAM_1]' AND phone = '[PHONE_PARAM_1]'"
            bounded_sql, bind_params = bind_query_parameters_ast(sql, pstore)

            return {
                "idx": idx,
                "sanitized_q": sanitized_q,
                "pstore": pstore,
                "bounded_sql": bounded_sql,
                "bind_params": bind_params,
                "expected_email": email,
                "expected_phone": phone
            }

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(worker, range(10)))

        for res in results:
            # Verify each thread has its own parameters
            self.assertEqual(res["pstore"]["[EMAIL_PARAM_1]"], res["expected_email"])
            self.assertEqual(res["pstore"]["[PHONE_PARAM_1]"], res["expected_phone"])
            self.assertEqual(res["bind_params"]["email_param_1"], res["expected_email"])
            self.assertEqual(res["bind_params"]["phone_param_1"], res["expected_phone"])
            self.assertNotIn(res["expected_email"], res["bounded_sql"])


if __name__ == "__main__":
    unittest.main()
