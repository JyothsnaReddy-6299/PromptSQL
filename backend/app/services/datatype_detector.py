import pandas as pd
import re


NUMERIC_THRESHOLD = 0.90
DATE_THRESHOLD = 0.90

MONTH_NAMES = {
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december"
}
DATE_EXTRA_TOKENS = {
    "am", "pm", "utc", "gmt", "z", "t",
    "mon", "tue", "wed", "thu", "fri", "sat", "sun",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
}
ALLOWED_DATE_ALPHA = MONTH_NAMES | DATE_EXTRA_TOKENS


def is_valid_date_value(val: any) -> bool:
    """
    Validates whether a single scalar value represents a genuine calendar date.
    
    Guards:
    1. If already a datetime/timestamp object, checks reasonable business year (1900-2100).
    2. If string contains letters, EVERY letter token must be a recognised calendar word
       (month name, day of week, am/pm, utc/z). Any foreign word (e.g. 'ST', 'EN', 'SKU', 'EMP')
       immediately disqualifies the value from being a date.
    3. Must contain at least one date/time separator (-, /, ., space, comma, colon, T).
       Bare integers like 201, 1001, 2024 are rejected.
    4. Must parse with pd.to_datetime and year must fall within 1900 <= year <= 2100.
       Prevents dateutil from converting codes like 'ST-201' into year 201 (0201-01-01).
    """
    if val is None or pd.isna(val):
        return False
    if hasattr(val, "year") and hasattr(val, "month") and hasattr(val, "day"):
        return 1900 <= val.year <= 2100

    s = str(val).strip()
    if not s or len(s) < 4:
        return False

    # Check 1: If string has letters, all letter tokens MUST be known calendar tokens
    alpha_tokens = re.findall(r"[a-zA-Z]+", s.lower())
    if alpha_tokens:
        for tok in alpha_tokens:
            if tok not in ALLOWED_DATE_ALPHA:
                return False

    # Check 2: Must contain at least one date/time separator
    if not re.search(r"[-/.\s,:T]", s):
        return False

    # Check 3: Full parse attempt & realistic year verification
    try:
        dt = pd.to_datetime(s, errors="raise", format="mixed")
        return 1900 <= dt.year <= 2100
    except Exception:
        return False


NA_PLACEHOLDERS = {'', 'none', 'null', 'nan', 'na', '#n/a', '<na>', 'n/a'}


def get_non_missing_sample(series: pd.Series) -> pd.Series:
    """
    Extracts non-missing values from a series for type evaluation,
    ignoring standard empty/null placeholders.
    """
    is_missing = series.isna() | series.astype(str).str.strip().str.lower().isin(NA_PLACEHOLDERS)
    return series[~is_missing]


def is_numeric_series(series: pd.Series) -> bool:
    """
    Returns True if most values in the column are numeric.
    Handles:
    92,368
    $45,000
    ₹1,75,391
    24%
    """
    sample = get_non_missing_sample(series)
    if sample.empty:
        return False

    s = (
        sample.astype(str)
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("₹", "", regex=False)
        .str.replace("%", "", regex=False)
    )

    numeric = pd.to_numeric(
        s,
        errors="coerce"
    )

    ratio = numeric.notna().mean()

    return ratio >= NUMERIC_THRESHOLD


def is_date_series(series: pd.Series) -> bool:
    """
    Returns True if most non-null values in the series look like real calendar dates.
    Uses is_valid_date_value to check every entry against strict date semantics.
    """
    sample = get_non_missing_sample(series)
    if sample.empty:
        return False

    if pd.api.types.is_datetime64_any_dtype(sample):
        return True

    valid_dates = sample.map(is_valid_date_value)
    return valid_dates.mean() >= DATE_THRESHOLD


def is_identifier_column_name(col_name: str) -> bool:
    """
    Checks if a column name indicates it is an ID, code, reference number, or staff/employee number.
    These are technically numeric-looking in terms of digits but are semantically identifiers,
    so they must not be treated as dates or undergo statistical math (mean, median, etc.).

    Covers patterns like:
      - Exact: id, _id, _no, _ref, _code, _num, _number
      - Prefixed: id_, no_
      - Keyword tokens: code, no, number, ref, serial, passport, zip, pin, ssn, phone, mobile, account, card
    """
    name = col_name.lower().strip()

    # Standalone "id"
    if name == "id":
        return True

    # Common suffix/prefix separators for id-like words
    _IDENTIFIER_SUFFIXES = ("_id", " id", "-id", "_no", " no", "-no",
                            "_ref", " ref", "-ref", "_code", " code", "-code",
                            "_num", " num", "-num", "_number", " number", "-number")
    _IDENTIFIER_PREFIXES = ("id_", "id ", "id-", "no_", "no-")

    if any(name.endswith(sfx) for sfx in _IDENTIFIER_SUFFIXES):
        return True
    if any(name.startswith(pfx) for pfx in _IDENTIFIER_PREFIXES):
        return True

    # Check for concatenated "id" suffixes on common entities
    common_id_names = {
        "customerid", "employeeid", "userid", "saleid", "productid", "itemid",
        "orderid", "vendorid", "clientid", "memberid", "studentid", "staffid",
        "agentid", "partnerid", "managerid", "adminid", "personid", "accountid",
        "transactionid", "txnid", "custid", "empid", "prodid", "orgid", "staffno"
    }
    if name.replace("_", "").replace(" ", "").replace("-", "") in common_id_names:
        return True

    # Token-level keyword match
    tokens = set(name.replace("_", " ").replace("-", " ").split())
    id_keywords = {"code", "no", "number", "ref", "zip", "pin", "ssn",
                   "phone", "mobile", "account", "card", "serial", "passport"}
    if tokens & id_keywords:
        return True

    return False


def detect_column_types(df: pd.DataFrame):
    """
    Detects every column's datatype.

    Returns:

    {
        "Employee ID":"text",
        "Annual Salary":"numeric",
        "Bonus %":"numeric",
        "Hire Date":"date"
    }
    """

    detected = {}

    for column in df.columns:

        series = df[column]

        # Short-circuit: columns whose NAME identifies them as reference codes or IDs
        # must always be treated as text, regardless of what their values look like.
        if is_identifier_column_name(str(column)):
            detected[column] = "text"
            continue

        if is_numeric_series(series):
            detected[column] = "numeric"

        elif is_date_series(series):
            detected[column] = "date"

        else:
            detected[column] = "text"

    return detected