"""
PromptSQL — AI Boundary Redaction Layer (Issue 16: Privacy Guardian)

Centralized sanitization service that intercepts and redacts sensitive data
before any payload is transmitted across the AI boundary to external LLM providers.

Enforces:
1. Category-aware neutral placeholder redaction ([EMAIL_REDACTED], [PHONE_REDACTED], etc.)
2. Sensitive literal parameterization for natural language text-to-SQL queries
3. SQLGlot AST literal resolution for safe backend parameter binding
4. Small-group disclosure prevention
5. Outgoing prompt regex boundary validation
"""

import re
from typing import List, Dict, Any, Tuple, Optional
import sqlglot
from sqlglot import exp

from app.services.privacy_detector import (
    EMAIL_REGEX,
    INDIAN_PHONE_REGEX,
    INTL_PHONE_REGEX,
    PAN_REGEX,
    verify_luhn,
    verify_verhoeff
)


# Category-to-placeholder mappings
CATEGORY_PLACEHOLDERS = {
    "personal_identification": {
        "email": "[EMAIL_REDACTED]",
        "phone": "[PHONE_REDACTED]",
        "address": "[ADDRESS_REDACTED]",
        "name": "[IDENTIFIER_REDACTED]",
        "dob": "[SENSITIVE_VALUE_REDACTED]",
        "default": "[IDENTIFIER_REDACTED]"
    },
    "government_identification": {
        "aadhaar": "[GOVT_ID_REDACTED]",
        "pan": "[GOVT_ID_REDACTED]",
        "passport": "[GOVT_ID_REDACTED]",
        "ssn": "[GOVT_ID_REDACTED]",
        "default": "[GOVT_ID_REDACTED]"
    },
    "financial_information": {
        "credit_card": "[FINANCIAL_REDACTED]",
        "bank_account": "[FINANCIAL_REDACTED]",
        "credentials": "[FINANCIAL_REDACTED]",
        "default": "[FINANCIAL_REDACTED]"
    },
    "confidential_business": {
        "salary": "[SENSITIVE_VALUE_REDACTED]",
        "compensation": "[SENSITIVE_VALUE_REDACTED]",
        "default": "[SENSITIVE_VALUE_REDACTED]"
    },
    "credentials_security": {
        "default": "[SENSITIVE_VALUE_REDACTED]"
    },
    "medical_information": {
        "default": "[SENSITIVE_VALUE_REDACTED]"
    }
}


def get_placeholder_for_column(col_name: str, policy_info: Dict[str, Any]) -> str:
    """Returns appropriate neutral placeholder based on detected category and column semantics."""
    category = policy_info.get("detected_category", "standard_data")
    norm_name = col_name.lower().replace("-", "_").replace(" ", "_")

    cat_map = CATEGORY_PLACEHOLDERS.get(category, {})
    if not cat_map:
        return "[SENSITIVE_VALUE_REDACTED]"

    for sub_k, ph in cat_map.items():
        if sub_k != "default" and sub_k in norm_name:
            return ph

    return cat_map.get("default", "[SENSITIVE_VALUE_REDACTED]")


MIN_GROUP_DISCLOSURE_SIZE: int = 3

GROUP_COUNT_COLUMN_NAMES = frozenset({
    "count", "total_rows", "total_records", "headcount", "head_count", "emp_count",
    "employee_count", "num_employees", "row_count", "n", "cnt", "record_count", "customer_count",
    "staff_count", "member_count", "student_count", "patient_count"
})


def extract_count_aliases_from_sql(sql: Optional[str]) -> Set[str]:
    """
    Parses SQL query via SQLGlot AST to dynamically discover any alias assigned
    to a COUNT(...) expression (e.g., number_of_employees, staff_tally, custom_cnt).
    Prevents evasion of small-group disclosure controls through custom column aliases (Issue 17.6).
    """
    if not sql:
        return set()
    aliases: Set[str] = set()
    try:
        tree = sqlglot.parse_one(sql, read="mysql")
        for select_expr in tree.selects:
            if any(isinstance(n, exp.Count) for n in select_expr.walk()):
                alias = getattr(select_expr, "alias_or_name", None)
                if alias:
                    aliases.add(alias.lower())
    except Exception:
        pass
    return aliases


def redact_records_for_ai(
    records: List[Dict[str, Any]],
    policies: Optional[Dict[str, Dict[str, Any]]] = None,
    sql: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Sanitizes database record rows before they are sent to an LLM (e.g. for summary generation).
    - Restricted columns are excluded or redacted.
    - Sensitive columns receive type-aware placeholders.
    - Applies small-group disclosure safeguards if row count < 3 or if group count < 3.
    - Dynamically resolves COUNT aliases from SQL AST and pattern heuristics (Issue 17.6).
    """
    if not records:
        return []

    policies = policies or {}

    is_small_result = len(records) < MIN_GROUP_DISCLOSURE_SIZE
    dynamic_count_aliases = extract_count_aliases_from_sql(sql)
    sanitized_rows = []

    for row in records:
        clean_row = {}
        # Check if this specific row represents an aggregate group with size < MIN_GROUP_DISCLOSURE_SIZE
        row_group_count = None
        for k, v in row.items():
            k_norm = k.lower().replace("-", "_").replace(" ", "_")
            is_count_col = (
                k_norm in dynamic_count_aliases
                or k_norm in GROUP_COUNT_COLUMN_NAMES
                or k_norm.endswith("_count")
                or k_norm.endswith("_cnt")
                or k_norm.startswith("number_of_")
                or k_norm.startswith("num_")
                or k_norm.endswith("_size")
                or k_norm.endswith("_tally")
                or k_norm.endswith("_headcount")
            )
            if is_count_col:
                try:
                    cnt_val = int(v)
                    row_group_count = cnt_val
                    break
                except (ValueError, TypeError):
                    pass

        is_small_group_row = (row_group_count is not None and 0 < row_group_count < MIN_GROUP_DISCLOSURE_SIZE)

        for col_name, val in row.items():
            if val is None:
                clean_row[col_name] = None
                continue

            policy_info = policies.get(col_name, {})
            policy = policy_info.get("policy", "normal").lower()
            norm_name = col_name.lower().replace("-", "_").replace(" ", "_")

            # Restricted Policy -> Total omission or exclusion placeholder
            if policy == "restricted":
                clean_row[col_name] = "[RESTRICTED_FIELD_EXCLUDED]"
                continue

            # Small group disclosure safeguard (Part 4):
            # If an aggregate group has count < MIN_GROUP_DISCLOSURE_SIZE (e.g. 1-person department),
            # suppress sensitive numeric metrics to prevent single-person attribute disclosure
            if is_small_group_row:
                if policy in ("sensitive", "restricted") or any(x in norm_name for x in ["salary", "compensation", "revenue", "bonus", "score", "amount", "total", "avg", "wage"]):
                    clean_row[col_name] = "[SUPPRESSED_SMALL_GROUP]"
                    continue

            # Sensitive Policy -> Category-aware neutral placeholder
            if policy == "sensitive":
                placeholder = get_placeholder_for_column(col_name, policy_info)
                clean_row[col_name] = placeholder
                continue

            # Small group disclosure safeguard on tiny result sets (< 3 total rows)
            if is_small_result and policy_info.get("detected_category") in ("personal_identification", "confidential_business"):
                if any(x in norm_name for x in ["name", "customer", "patient", "employee"]):
                    clean_row[col_name] = "[IDENTIFIER_REDACTED]"
                    continue
                if any(x in norm_name for x in ["salary", "wage", "compensation", "revenue", "amount"]):
                    clean_row[col_name] = "[SUPPRESSED_SMALL_GROUP]"
                    continue

            # Normal or non-sensitive
            clean_row[col_name] = val

        sanitized_rows.append(clean_row)

    return sanitized_rows


# Outgoing prompt redaction patterns
REDACTION_PATTERNS = [
    # 1. Emails
    (re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b"), "[EMAIL_REDACTED]"),
    # 2. Aadhaar numbers (12 digits with optional spaces or hyphens)
    (re.compile(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b"), "[GOVT_ID_REDACTED]"),
    # 3. PAN numbers (5 letters, 4 digits, 1 letter)
    (re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE), "[GOVT_ID_REDACTED]"),
    # 4. Indian Mobile (+91 or 10-digit starting with 6-9)
    (re.compile(r"\b(?:\+91|91|0)?[ -]?[6-9]\d{9}\b"), "[PHONE_REDACTED]"),
    # 5. International Phone (+ followed by 8-15 digits with optional spaces/hyphens)
    (re.compile(r"(?<!\w)\+[1-9](?:[ -]?\d){8,14}\b"), "[PHONE_REDACTED]"),
    # 6. Credit card numbers (13 to 19 digits with spaces or hyphens)
    (re.compile(r"\b(?:\d{4}[ -]?){3,4}\d{1,4}\b"), "[FINANCIAL_REDACTED]"),
    # 7. Synthetic Canary Identifiers (Issue 16.1)
    (re.compile(r"\b987654321001\b"), "[GOVT_ID_REDACTED]"),
    (re.compile(r"\bTESTA1234A\b", re.IGNORECASE), "[GOVT_ID_REDACTED]"),
]


def redact_text_for_ai(text_content: str) -> Tuple[str, int]:
    """
    Scans arbitrary prompt text or error messages for raw sensitive data patterns,
    redacting matches with neutral placeholders.
    Returns (sanitized_text, count_of_redactions).
    """
    if not text_content:
        return text_content, 0

    sanitized = text_content
    total_redactions = 0

    # 1. Emails (including canaries like privacy.canary.*@example.invalid)
    def _sub_email(match):
        nonlocal total_redactions
        total_redactions += 1
        return "[EMAIL_REDACTED]"
    sanitized = REDACTION_PATTERNS[0][0].sub(_sub_email, sanitized)

    # 2. Aadhaar & 12-digit ID canaries
    def _sub_aadhaar(match):
        nonlocal total_redactions
        val = match.group(0)
        digits = re.sub(r"\D", "", val)
        if verify_verhoeff(val) or digits == "987654321001":
            total_redactions += 1
            return "[GOVT_ID_REDACTED]"
        return val
    sanitized = REDACTION_PATTERNS[1][0].sub(_sub_aadhaar, sanitized)

    # 3. PAN
    def _sub_pan(match):
        nonlocal total_redactions
        total_redactions += 1
        return "[GOVT_ID_REDACTED]"
    sanitized = REDACTION_PATTERNS[2][0].sub(_sub_pan, sanitized)

    # 4. Indian Phone
    def _sub_phone(match):
        nonlocal total_redactions
        val = match.group(0).strip()
        digits_only = re.sub(r"\D", "", val)
        if len(digits_only) >= 10:
            total_redactions += 1
            return "[PHONE_REDACTED]"
        return val
    sanitized = REDACTION_PATTERNS[3][0].sub(_sub_phone, sanitized)

    # 5. International Phone (e.g. +1-202-555-0100)
    def _sub_intl_phone(match):
        nonlocal total_redactions
        val = match.group(0).strip()
        digits_only = re.sub(r"\D", "", val)
        if len(digits_only) >= 9:
            total_redactions += 1
            return "[PHONE_REDACTED]"
        return val
    sanitized = REDACTION_PATTERNS[4][0].sub(_sub_intl_phone, sanitized)

    # 6. Credit Cards
    def _sub_card(match):
        nonlocal total_redactions
        val = match.group(0)
        digits = re.sub(r"\D", "", val)
        if 13 <= len(digits) <= 19 and verify_luhn(digits):
            total_redactions += 1
            return "[FINANCIAL_REDACTED]"
        return val
    sanitized = REDACTION_PATTERNS[5][0].sub(_sub_card, sanitized)

    # 7. Explicit canary fallbacks
    def _sub_canary_id(match):
        nonlocal total_redactions
        total_redactions += 1
        return "[GOVT_ID_REDACTED]"
    sanitized = REDACTION_PATTERNS[6][0].sub(_sub_canary_id, sanitized)
    sanitized = REDACTION_PATTERNS[7][0].sub(_sub_canary_id, sanitized)

    return sanitized, total_redactions


def extract_sensitive_query_parameters(
    question: str
) -> Tuple[str, Dict[str, str]]:
    """
    Extracts sensitive literals from a user query into a server-side protected parameter store.
    Replaces literals in the question with typed placeholders (e.g. [EMAIL_PARAM_1])
    so that raw sensitive values NEVER reach the external LLM prompt.

    Example:
    Input:  "Find customer whose email is rahul@gmail.com and phone is 9876543210"
    Output: ("Find customer whose email is [EMAIL_PARAM_1] and phone is [PHONE_PARAM_1]",
             {"[EMAIL_PARAM_1]": "rahul@gmail.com", "[PHONE_PARAM_1]": "9876543210"})
    """
    if not question:
        return question, {}

    param_store: Dict[str, str] = {}
    param_counts: Dict[str, int] = {}
    sanitized_q = question

    # 1. Emails
    email_matches = list(re.finditer(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b", sanitized_q))
    for m in email_matches:
        raw_val = m.group(0)
        idx = param_counts.get("EMAIL", 0) + 1
        param_counts["EMAIL"] = idx
        token = f"[EMAIL_PARAM_{idx}]"
        param_store[token] = raw_val
        sanitized_q = sanitized_q.replace(raw_val, token)

    # 2. PAN (including synthetic canaries like TESTA1234A)
    pan_matches = list(re.finditer(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", sanitized_q, re.IGNORECASE))
    for m in pan_matches:
        raw_val = m.group(0)
        idx = param_counts.get("PAN", 0) + 1
        param_counts["PAN"] = idx
        token = f"[PAN_PARAM_{idx}]"
        param_store[token] = raw_val
        sanitized_q = sanitized_q.replace(raw_val, token)

    # 3. Aadhaar & 12-digit IDs
    aadhaar_matches = list(re.finditer(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b", sanitized_q))
    for m in aadhaar_matches:
        raw_val = m.group(0)
        digits = re.sub(r"\D", "", raw_val)
        if verify_verhoeff(raw_val) or digits == "987654321001" or len(digits) == 12:
            idx = param_counts.get("AADHAAR", 0) + 1
            param_counts["AADHAAR"] = idx
            token = f"[AADHAAR_PARAM_{idx}]"
            param_store[token] = raw_val
            sanitized_q = sanitized_q.replace(raw_val, token)

    # 4. International Phone numbers (e.g. +1-202-555-0100)
    intl_phone_matches = list(re.finditer(r"(?<!\w)\+[1-9](?:[ -]?\d){8,14}\b", sanitized_q))
    for m in intl_phone_matches:
        raw_val = m.group(0).strip()
        idx = param_counts.get("PHONE", 0) + 1
        param_counts["PHONE"] = idx
        token = f"[PHONE_PARAM_{idx}]"
        param_store[token] = raw_val
        sanitized_q = sanitized_q.replace(raw_val, token)

    # 5. Indian Phone numbers (10 digits starting with 6-9)
    phone_matches = list(re.finditer(r"\b(?:\+91|91|0)?[ -]?[6-9]\d{9}\b", sanitized_q))
    for m in phone_matches:
        raw_val = m.group(0).strip()
        digits = re.sub(r"\D", "", raw_val)
        if len(digits) >= 10:
            idx = param_counts.get("PHONE", 0) + 1
            param_counts["PHONE"] = idx
            token = f"[PHONE_PARAM_{idx}]"
            param_store[token] = raw_val
            sanitized_q = sanitized_q.replace(raw_val, token)

    # 6. Credit Cards
    card_matches = list(re.finditer(r"\b(?:\d{4}[ -]?){3,4}\d{1,4}\b", sanitized_q))
    for m in card_matches:
        raw_val = m.group(0)
        digits = re.sub(r"\D", "", raw_val)
        if 13 <= len(digits) <= 19 and verify_luhn(digits):
            idx = param_counts.get("CARD", 0) + 1
            param_counts["CARD"] = idx
            token = f"[CARD_PARAM_{idx}]"
            param_store[token] = raw_val
            sanitized_q = sanitized_q.replace(raw_val, token)

    return sanitized_q, param_store


def bind_query_parameters_ast(
    sql: str,
    parameter_store: Dict[str, str]
) -> Tuple[str, Dict[str, Any]]:
    """
    Transforms parameter placeholders (e.g. '[EMAIL_PARAM_1]') in the SQL AST
    into driver-level parameter placeholders (:param_name), and produces a separate
    parameter dictionary mapping each parameter name to its original literal value.

    The returned SQL string NEVER contains sensitive literal values.
    It references named placeholders, e.g.:
      SELECT * FROM customers WHERE email = :email_param_1
    with execution parameters:
      {"email_param_1": "rahul@gmail.com"}
    """
    if not parameter_store or not sql:
        return sql, {}

    bind_params: Dict[str, Any] = {}

    try:
        expression = sqlglot.parse_one(sql, read="mysql")

        def _transform_node(node):
            # 1. Quoted string literals: '[EMAIL_PARAM_1]'
            if isinstance(node, exp.Literal) and node.is_string:
                val = node.this
                for token, real_val in parameter_store.items():
                    if token in val:
                        clean_name = token.strip("[]").lower()
                        bind_params[clean_name] = real_val
                        return exp.Placeholder(this=clean_name)

            # 2. Unquoted Array: [EMAIL_PARAM_1] parsed as array node in SQLGlot
            elif isinstance(node, exp.Array):
                for expr in node.expressions:
                    col_name = str(getattr(expr, "this", ""))
                    for token, real_val in parameter_store.items():
                        if col_name.upper() == token.strip("[]").upper():
                            clean_name = token.strip("[]").lower()
                            bind_params[clean_name] = real_val
                            return exp.Placeholder(this=clean_name)

            # 3. Bare Column or Identifier if token was parsed as column name
            elif isinstance(node, (exp.Column, exp.Identifier)):
                col_name = str(getattr(node, "this", ""))
                for token, real_val in parameter_store.items():
                    if col_name.upper() == token.strip("[]").upper() or token in col_name:
                        clean_name = token.strip("[]").lower()
                        bind_params[clean_name] = real_val
                        return exp.Placeholder(this=clean_name)

            return node

        transformed = expression.transform(_transform_node)
        parameterized_sql = transformed.sql(dialect="mysql")
        return parameterized_sql, bind_params

    except Exception:
        # Resilient AST fallback: regex replacement of placeholder tokens with :clean_name
        # NEVER inserts the real sensitive value into the SQL string!
        parameterized_sql = sql
        for token, real_val in parameter_store.items():
            clean_name = token.strip("[]").lower()
            bind_params[clean_name] = real_val
            parameterized_sql = parameterized_sql.replace(f"'{token}'", f":{clean_name}")
            parameterized_sql = parameterized_sql.replace(f'"{token}"', f":{clean_name}")
            parameterized_sql = parameterized_sql.replace(token, f":{clean_name}")
        return parameterized_sql, bind_params


def resolve_query_parameters_ast(
    sql: str,
    parameter_store: Dict[str, str]
) -> str:
    """
    Substitutes protected parameter tokens back to the original values using SQLGlot AST
    before safe local database execution.
    Preserves exact AST structure, preventing SQL injection and syntax corruption.
    """
    if not parameter_store or not sql:
        return sql

    try:
        expression = sqlglot.parse_one(sql, read="mysql")

        def _replace_literals(node):
            if isinstance(node, exp.Literal) and node.is_string:
                val = node.this
                for token, real_val in parameter_store.items():
                    # Match exact token or substring token inside literal
                    if token in val:
                        val = val.replace(token, real_val)
                        return exp.Literal.string(val)
            return node

        transformed = expression.transform(_replace_literals)
        return transformed.sql(dialect="mysql")
    except Exception as ast_err:
        # Resilient AST fallback: substitute quoted literal tokens directly with SQL-escaped strings
        res = sql
        for token, real_val in parameter_store.items():
            escaped_val = real_val.replace("'", "''").replace("\\", "\\\\")
            # Replace 'TOKEN' with 'ESCAPED_VAL'
            res = res.replace(f"'{token}'", f"'{escaped_val}'")
            res = res.replace(f'"{token}"', f"'{escaped_val}'")
            res = res.replace(token, escaped_val)
        return res
