import pandas as pd
import re


NUMERIC_THRESHOLD = 0.90
DATE_THRESHOLD = 0.90

# Matches values that begin with letters followed by digits or digits followed by letters,
# possibly separated by hyphens, slashes, dots, or underscores.
# Examples that must NOT be parsed as dates: ST-201, EN-9001, SKU-001, EMP001, ORD-10000, 2024-Q1
_IDENTIFIER_VALUE_PATTERN = re.compile(
    r"^[A-Za-z][\w\-/\.]*\d"      # Starts with letter, ends near a digit: ST-201, EN-9001
    r"|^\d[\w\-/\.]*[A-Za-z]",    # Starts with digit, ends near a letter: 2024-Q1
    re.ASCII
)

# Acceptable date formats — values must broadly match one of these before we
# attempt a full parse. This prevents dateutil from interpreting arbitrary
# alphanumeric codes (e.g. ST-201 → year 201, month 01, day 01).
_DATE_FORMAT_PATTERNS = re.compile(
    r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}"   # ISO / YYYY-MM-DD style: 2024-01-15
    r"|^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}"  # DD/MM/YYYY or DD-MM-YY
    r"|^\d{1,2}\s+\w{3,}\s+\d{4}$"      # 15 January 2024, 15 Jan 2024
    r"|^\w{3,}\s+\d{1,2},?\s+\d{4}$",   # January 15, 2024
    re.IGNORECASE
)


def is_numeric_series(series: pd.Series) -> bool:
    """
    Returns True if most values in the column are numeric.
    Handles:
    92,368
    $45,000
    ₹1,75,391
    24%
    """

    s = (
        series.astype(str)
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

    Guard rails applied before calling pd.to_datetime:
    1. If any non-null value matches the identifier pattern (alpha prefix + digits or
       digit prefix + alpha suffix — e.g. ST-201, EN-9001, EMP001, 2024-Q1), the whole
       column is immediately classified as text. This prevents dateutil from silently
       interpreting business codes as historical dates.
    2. Values must broadly match a known date format skeleton before a full parse is
       attempted. This blocks standalone numbers (plain years like 201) and other
       ambiguous strings from being promoted to dates.
    """
    sample = series.dropna()
    if sample.empty:
        return False

    str_sample = sample.astype(str).str.strip()

    # Guard 1: Reject entire column if ANY value looks like an identifier code.
    # A single ST-201 is enough to disqualify the column from being a date column.
    has_identifier_values = str_sample.map(
        lambda v: bool(_IDENTIFIER_VALUE_PATTERN.match(v))
    ).any()
    if has_identifier_values:
        return False

    # Guard 2: Require that most values match a recognisable date format skeleton
    # before we pay the cost of a full parse. This rejects plain numbers, random
    # strings, and anything dateutil would only accept via heroic guessing.
    well_formed_ratio = str_sample.map(
        lambda v: bool(_DATE_FORMAT_PATTERNS.match(v))
    ).mean()
    if well_formed_ratio < DATE_THRESHOLD:
        return False

    # Full parse: now safe to call pd.to_datetime — values already look date-like.
    dates = pd.to_datetime(str_sample, errors="coerce", format="mixed")
    return dates.notna().mean() >= DATE_THRESHOLD


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