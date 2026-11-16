"""
PromptSQL — Sensitive Data Detection Engine (Issue 16: Privacy Guardian)

Context-aware scanner that identifies sensitive data in arbitrary uploaded datasets (CSV, XLS, XLSX)
using:
1. Column-name semantic analysis
2. Data-type analysis
3. Pattern matching & regular expressions
4. Mathematical checksums (Verhoeff for Aadhaar, Luhn for credit cards)
5. Controlled local sampling & value-distribution inspection
6. Contextual guards to avoid false-positive classifications on ordinary identifiers or numbers

CRITICAL: Runs 100% locally in the backend. Never sends raw sample values to external LLMs.
"""

import re
from typing import List, Dict, Any, Optional, Tuple


# ---------------------------------------------------------------------------
# Section 1 — Checksum Algorithms
# ---------------------------------------------------------------------------

# Verhoeff algorithm lookup tables for Indian Aadhaar 12-digit validation
VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]

VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]

VERHOEFF_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verify_verhoeff(num_str: str) -> bool:
    """
    Validates a number string using the Verhoeff checksum algorithm (used by UIDAI for Aadhaar).
    Expects 12 numeric digits.
    """
    cleaned = re.sub(r"[\s-]", "", str(num_str).strip())
    if not cleaned.isdigit() or len(cleaned) != 12:
        return False
    # Aadhaar cannot start with 0 or 1
    if cleaned[0] in ("0", "1"):
        return False

    c = 0
    reversed_num = [int(x) for x in reversed(cleaned)]
    for i, item in enumerate(reversed_num):
        c = VERHOEFF_D[c][VERHOEFF_P[i % 8][item]]
    return c == 0


def verify_luhn(card_str: str) -> bool:
    """
    Validates a credit/debit card number using the Luhn algorithm (Mod 10).
    Expects 13 to 19 digits.
    """
    cleaned = re.sub(r"[\s-]", "", str(card_str).strip())
    if not cleaned.isdigit() or len(cleaned) < 13 or len(cleaned) > 19:
        return False

    digits = [int(d) for d in cleaned]
    checksum = 0
    reverse_digits = digits[::-1]

    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += (doubled - 9) if doubled > 9 else doubled
        else:
            checksum += d

    return checksum % 10 == 0


# ---------------------------------------------------------------------------
# Section 2 — Regular Expression Validators & Patterns
# ---------------------------------------------------------------------------

EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
)

# Indian phone: +91, 91, 0, or bare 10-digit starting with 6, 7, 8, 9
INDIAN_PHONE_REGEX = re.compile(
    r"^(?:(?:\+91|91|0)?[ -]?)?[6-9]\d{9}$"
)

# International phone: mandatory +, country code, 7-15 digits
INTL_PHONE_REGEX = re.compile(
    r"^\+[1-9]\d{6,14}$"
)

# Indian PAN: 5 letters (4th is entity), 4 digits, 1 letter
PAN_REGEX = re.compile(
    r"^[A-Z]{5}[0-9]{4}[A-Z]$", re.IGNORECASE
)

# Indian PIN code (6 digits)
PINCODE_REGEX = re.compile(
    r"^[1-9][0-9]{5}$"
)

# US ZIP code (5 digits or 5+4)
ZIP_REGEX = re.compile(
    r"^\d{5}(?:-\d{4})?$"
)

# Passport: 1 letter followed by 7 or 8 digits
PASSPORT_REGEX = re.compile(
    r"^[A-Z][0-9]{7,8}$", re.IGNORECASE
)

# US SSN: 3-2-4 digits with hyphens
SSN_REGEX = re.compile(
    r"^\d{3}-\d{2}-\d{4}$"
)


# ---------------------------------------------------------------------------
# Section 3 — Context-Aware Column Categorization
# ---------------------------------------------------------------------------

# Columns that represent ordinary business identifiers and should NOT be flagged as government IDs
ORDINARY_BUSINESS_KEYS = {
    "id", "order_id", "orders_id", "product_id", "item_id", "sku", "category_id",
    "department_id", "dept_id", "store_id", "inventory_id", "shipment_id",
    "invoice_id", "transaction_id", "user_id", "role_id", "permission_id",
    "status_id", "status_code", "country_code", "currency_code", "course_id",
    "subject_id", "exam_id", "batch_id", "ticket_id", "project_id"
}

# Ordinary numeric metrics that must NOT be marked sensitive
ORDINARY_NUMERIC_METRICS = {
    "quantity", "qty", "units", "units_sold", "stock", "inventory", "count",
    "price", "unit_price", "list_price", "cost", "unit_cost", "subtotal",
    "total", "total_amount", "amount", "order_total", "line_total", "marks", "score",
    "grade_point", "cgpa", "gpa", "percentage", "discount", "discount_percent",
    "tax", "tax_rate", "rating", "stars", "duration", "hours", "weight", "volume",
    "age", "distance", "views", "clicks", "impressions", "sales", "revenue"
}

# Semantic keyword mappings for column names
SEMANTIC_KEYWORDS = {
    "email": {
        "keywords": ["email", "e_mail", "mail_id", "email_address", "user_email", "contact_email"],
        "category": "personal_identification",
        "sensitivity": "high",
        "policy": "sensitive",
        "placeholder": "[EMAIL_REDACTED]"
    },
    "phone": {
        "keywords": ["phone", "mobile", "contact_no", "contact_num", "cell_phone", "telephone", "phone_number", "mobile_number", "cell"],
        "category": "personal_identification",
        "sensitivity": "high",
        "policy": "sensitive",
        "placeholder": "[PHONE_REDACTED]"
    },
    "aadhaar": {
        "keywords": ["aadhaar", "aadhar", "uidai", "aadhaar_no", "aadhar_number"],
        "category": "government_identification",
        "sensitivity": "critical",
        "policy": "restricted",
        "placeholder": "[GOVT_ID_REDACTED]"
    },
    "pan": {
        "keywords": ["pan", "pan_no", "pan_number", "pan_card", "tax_id"],
        "category": "government_identification",
        "sensitivity": "high",
        "policy": "sensitive",
        "placeholder": "[GOVT_ID_REDACTED]"
    },
    "passport": {
        "keywords": ["passport", "passport_no", "passport_number"],
        "category": "government_identification",
        "sensitivity": "high",
        "policy": "sensitive",
        "placeholder": "[GOVT_ID_REDACTED]"
    },
    "ssn": {
        "keywords": ["ssn", "social_security", "social_security_number"],
        "category": "government_identification",
        "sensitivity": "critical",
        "policy": "restricted",
        "placeholder": "[GOVT_ID_REDACTED]"
    },
    "credit_card": {
        "keywords": ["credit_card", "debit_card", "card_number", "card_no", "cc_num", "creditcard", "debitcard"],
        "category": "financial_information",
        "sensitivity": "critical",
        "policy": "restricted",
        "placeholder": "[FINANCIAL_REDACTED]"
    },
    "bank_account": {
        "keywords": ["bank_account", "account_no", "account_number", "acc_no", "bank_acc", "acct_num", "iban"],
        "category": "financial_information",
        "sensitivity": "high",
        "policy": "sensitive",
        "placeholder": "[FINANCIAL_REDACTED]"
    },
    "credentials": {
        "keywords": ["password", "pwd", "passwd", "secret", "token", "api_key", "auth_token", "cvv", "cvc", "pin", "auth_secret"],
        "category": "credentials_security",
        "sensitivity": "critical",
        "policy": "restricted",
        "placeholder": "[SENSITIVE_VALUE_REDACTED]"
    },
    "salary": {
        "keywords": ["salary", "ctc", "compensation", "stipend", "wages", "pay_rate", "base_pay", "bonus", "annual_salary"],
        "category": "confidential_business",
        "sensitivity": "medium",
        "policy": "sensitive",
        "placeholder": "[SENSITIVE_VALUE_REDACTED]"
    },
    "name": {
        "keywords": ["first_name", "last_name", "full_name", "customer_name", "patient_name", "employee_name", "staff_name", "student_name"],
        "category": "personal_identification",
        "sensitivity": "medium",
        "policy": "sensitive",
        "placeholder": "[IDENTIFIER_REDACTED]"
    },
    "address": {
        "keywords": ["residential_address", "home_address", "street_address", "flat_no", "apartment", "house_no", "address_line1"],
        "category": "personal_identification",
        "sensitivity": "medium",
        "policy": "sensitive",
        "placeholder": "[ADDRESS_REDACTED]"
    },
    "dob": {
        "keywords": ["dob", "date_of_birth", "birth_date", "birthdate"],
        "category": "personal_identification",
        "sensitivity": "medium",
        "policy": "sensitive",
        "placeholder": "[SENSITIVE_VALUE_REDACTED]"
    },
    "postal_code": {
        "keywords": ["pincode", "postal_code", "zip_code", "zipcode"],
        "category": "personal_identification",
        "sensitivity": "low",
        "policy": "normal",
        "placeholder": "[ADDRESS_REDACTED]"
    },
    "medical": {
        "keywords": ["medical_record", "patient_id", "diagnosis", "prescription", "treatment", "health_condition", "disease"],
        "category": "medical_information",
        "sensitivity": "high",
        "policy": "sensitive",
        "placeholder": "[SENSITIVE_VALUE_REDACTED]"
    },
    "employee_id": {
        "keywords": ["employee_id", "emp_id", "staff_id", "worker_id"],
        "category": "confidential_business",
        "sensitivity": "low",
        "policy": "normal",
        "placeholder": "[IDENTIFIER_REDACTED]"
    },
    "customer_id": {
        "keywords": ["customer_id", "client_id"],
        "category": "confidential_business",
        "sensitivity": "low",
        "policy": "normal",
        "placeholder": "[IDENTIFIER_REDACTED]"
    }
}


def _normalize_name(name: str) -> str:
    """Normalize column name to lowercase alphanumeric tokens with underscores."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower())
    return cleaned.strip("_")


def evaluate_column_values(values: List[Any]) -> Dict[str, Any]:
    """
    Evaluates sample values for pattern matches (regex, checksums).
    Returns match counts and percentages.
    """
    clean_vals = [str(v).strip() for v in values if v is not None and str(v).strip() != "" and str(v).lower() not in ("none", "null", "nan")]
    total = len(clean_vals)
    if total == 0:
        return {"total": 0}

    email_matches = sum(1 for v in clean_vals if EMAIL_REGEX.match(v))
    indian_phone_matches = sum(1 for v in clean_vals if INDIAN_PHONE_REGEX.match(v))
    intl_phone_matches = sum(1 for v in clean_vals if INTL_PHONE_REGEX.match(re.sub(r"[\s\-()]", "", v)))
    pan_matches = sum(1 for v in clean_vals if PAN_REGEX.match(v))
    pincode_matches = sum(1 for v in clean_vals if PINCODE_REGEX.match(v))
    zip_matches = sum(1 for v in clean_vals if ZIP_REGEX.match(v))
    passport_matches = sum(1 for v in clean_vals if PASSPORT_REGEX.match(v))
    ssn_matches = sum(1 for v in clean_vals if SSN_REGEX.match(v))
    verhoeff_matches = sum(1 for v in clean_vals if verify_verhoeff(v))
    luhn_matches = sum(1 for v in clean_vals if verify_luhn(v))

    return {
        "total": total,
        "email_ratio": email_matches / total,
        "indian_phone_ratio": indian_phone_matches / total,
        "intl_phone_ratio": intl_phone_matches / total,
        "pan_ratio": pan_matches / total,
        "pincode_ratio": pincode_matches / total,
        "zip_ratio": zip_matches / total,
        "passport_ratio": passport_matches / total,
        "ssn_ratio": ssn_matches / total,
        "verhoeff_ratio": verhoeff_matches / total,
        "luhn_ratio": luhn_matches / total,
        "sample_count": total
    }


def classify_column_privacy(
    column_name: str,
    data_type: str,
    sample_values: Optional[List[Any]] = None
) -> Dict[str, Any]:
    """
    Performs context-aware sensitivity detection on a single column.
    Combines column-name semantics, data type, pattern matching, and checksums.
    """
    norm_name = _normalize_name(column_name)
    val_stats = evaluate_column_values(sample_values or [])
    total_samples = val_stats.get("total", 0)

    # -------------------------------------------------------------
    # Guard 1: Ordinary Business Keys (e.g. order_id, product_id, id)
    # -------------------------------------------------------------
    if norm_name in ORDINARY_BUSINESS_KEYS:
        return {
            "column_name": column_name,
            "detected_category": "internal_identifier",
            "sensitivity_level": "low",
            "detection_method": "context_guard",
            "confidence": "high",
            "policy": "normal",
            "status": "normal",
            "explanation": f"Column '{column_name}' identified as standard internal business identifier."
        }

    # -------------------------------------------------------------
    # Guard 2: Ordinary Numeric Metrics (e.g. quantity, score, marks, price)
    # -------------------------------------------------------------
    if norm_name in ORDINARY_NUMERIC_METRICS:
        return {
            "column_name": column_name,
            "detected_category": "general_numeric",
            "sensitivity_level": "low",
            "detection_method": "context_guard",
            "confidence": "high",
            "policy": "normal",
            "status": "normal",
            "explanation": f"Column '{column_name}' identified as standard operational/business metric."
        }

    # -------------------------------------------------------------
    # Check 1: Checksum-verified patterns (Aadhaar, Credit Card)
    # -------------------------------------------------------------
    if total_samples > 0 and val_stats.get("verhoeff_ratio", 0) >= 0.2:
        return {
            "column_name": column_name,
            "detected_category": "government_identification",
            "sensitivity_level": "critical",
            "detection_method": "checksum_verified (Verhoeff)",
            "confidence": "high",
            "policy": "restricted",
            "status": "protected",
            "explanation": f"Aadhaar identification verified via Verhoeff checksum ({int(val_stats['verhoeff_ratio']*100)}% match rate)."
        }

    if total_samples > 0 and val_stats.get("luhn_ratio", 0) >= 0.2:
        return {
            "column_name": column_name,
            "detected_category": "financial_information",
            "sensitivity_level": "critical",
            "detection_method": "checksum_verified (Luhn)",
            "confidence": "high",
            "policy": "restricted",
            "status": "protected",
            "explanation": f"Payment card numbers verified via Luhn Mod-10 algorithm ({int(val_stats['luhn_ratio']*100)}% match rate)."
        }

    # -------------------------------------------------------------
    # Check 2: Pattern-matched values (Email, Phone, PAN, SSN, Passport)
    # -------------------------------------------------------------
    if total_samples > 0 and val_stats.get("email_ratio", 0) >= 0.3:
        has_email_name = any(k in norm_name for k in ["email", "mail"])
        return {
            "column_name": column_name,
            "detected_category": "personal_identification",
            "sensitivity_level": "high",
            "detection_method": "pattern_match (RFC-5322)",
            "confidence": "high" if has_email_name else "medium",
            "policy": "sensitive",
            "status": "protected" if has_email_name else "pending_review",
            "explanation": f"Email address format detected in {int(val_stats['email_ratio']*100)}% of sampled rows."
        }

    if total_samples > 0 and val_stats.get("pan_ratio", 0) >= 0.3:
        has_pan_name = "pan" in norm_name or "tax" in norm_name
        return {
            "column_name": column_name,
            "detected_category": "government_identification",
            "sensitivity_level": "high",
            "detection_method": "pattern_match (PAN format)",
            "confidence": "high" if has_pan_name else "medium",
            "policy": "sensitive",
            "status": "protected",
            "explanation": f"Permanent Account Number (PAN) tax identifier pattern detected in {int(val_stats['pan_ratio']*100)}% of sampled rows."
        }

    if total_samples > 0 and (val_stats.get("indian_phone_ratio", 0) >= 0.3 or val_stats.get("intl_phone_ratio", 0) >= 0.4):
        has_phone_name = any(k in norm_name for k in ["phone", "mobile", "contact", "cell", "tel"])
        is_money_or_metric = any(k in norm_name for k in ["salary", "amount", "price", "cost", "total", "pay", "wage", "ctc", "rate", "fee"])
        if not is_money_or_metric and (has_phone_name or val_stats.get("intl_phone_ratio", 0) >= 0.5 or val_stats.get("indian_phone_ratio", 0) >= 0.5):
            ratio = max(val_stats.get("indian_phone_ratio", 0), val_stats.get("intl_phone_ratio", 0))
            return {
                "column_name": column_name,
                "detected_category": "personal_identification",
                "sensitivity_level": "high",
                "detection_method": "pattern_match (Phone E.164 / Indian)",
                "confidence": "high" if has_phone_name else "medium",
                "policy": "sensitive",
                "status": "protected" if has_phone_name else "pending_review",
                "explanation": f"Telephone/mobile number patterns detected in {int(ratio*100)}% of sampled rows."
            }

    if total_samples > 0 and val_stats.get("ssn_ratio", 0) >= 0.3:
        return {
            "column_name": column_name,
            "detected_category": "government_identification",
            "sensitivity_level": "critical",
            "detection_method": "pattern_match (SSN)",
            "confidence": "high",
            "policy": "restricted",
            "status": "protected",
            "explanation": f"Social Security / National ID format detected in {int(val_stats['ssn_ratio']*100)}% of sampled rows."
        }

    # -------------------------------------------------------------
    # Check 3: Semantic Name Matching
    # -------------------------------------------------------------
    for rule_key, rule_data in SEMANTIC_KEYWORDS.items():
        for kw in rule_data["keywords"]:
            if norm_name == kw or f"_{kw}" in norm_name or f"{kw}_" in norm_name:
                # Additional validation for salary
                if rule_key == "salary":
                    # Check if numeric or contains currency
                    is_num = "int" in data_type.lower() or "dec" in data_type.lower() or "float" in data_type.lower() or "num" in data_type.lower()
                    return {
                        "column_name": column_name,
                        "detected_category": rule_data["category"],
                        "sensitivity_level": "medium",
                        "detection_method": "semantic_heuristic",
                        "confidence": "high" if is_num else "medium",
                        "policy": "sensitive",
                        "status": "protected",
                        "explanation": f"Column '{column_name}' identified as confidential compensation / salary field."
                    }

                # Personal name columns
                if rule_key == "name":
                    return {
                        "column_name": column_name,
                        "detected_category": rule_data["category"],
                        "sensitivity_level": rule_data["sensitivity"],
                        "detection_method": "semantic_heuristic",
                        "confidence": "high" if any(x in norm_name for x in ["first", "last", "full", "customer", "patient", "employee"]) else "medium",
                        "policy": "sensitive",
                        "status": "protected",
                        "explanation": f"Column '{column_name}' matches personal name pattern."
                    }

                # Default semantic mapping
                status = "protected" if rule_data["policy"] in ("sensitive", "restricted") else "normal"
                confidence = "high" if rule_data["sensitivity"] in ("critical", "high") else "medium"
                return {
                    "column_name": column_name,
                    "detected_category": rule_data["category"],
                    "sensitivity_level": rule_data["sensitivity"],
                    "detection_method": "semantic_heuristic",
                    "confidence": confidence,
                    "policy": rule_data["policy"],
                    "status": status,
                    "explanation": f"Column '{column_name}' matches semantic keyword for {rule_data['category']}."
                }

    # -------------------------------------------------------------
    # Check 4: Ambiguous or Low Confidence Fields
    # -------------------------------------------------------------
    # If column name ends with _id or _num but wasn't in business keys
    if norm_name.endswith("_id") or norm_name.endswith("_num") or norm_name.endswith("_code"):
        return {
            "column_name": column_name,
            "detected_category": "internal_identifier",
            "sensitivity_level": "low",
            "detection_method": "contextual_fallback",
            "confidence": "requires_review",
            "policy": "normal",
            "status": "pending_review",
            "explanation": f"Identifier column '{column_name}' classified as internal key; requires human review if confidential."
        }

    # -------------------------------------------------------------
    # Default: Non-sensitive column
    # -------------------------------------------------------------
    return {
        "column_name": column_name,
        "detected_category": "standard_data",
        "sensitivity_level": "low",
        "detection_method": "schema_analysis",
        "confidence": "high",
        "policy": "normal",
        "status": "normal",
        "explanation": f"No sensitive patterns or confidential attributes detected in '{column_name}'."
    }
