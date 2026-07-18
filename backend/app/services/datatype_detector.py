import pandas as pd
import re


NUMERIC_THRESHOLD = 0.90
DATE_THRESHOLD = 0.90


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
    Returns True if most values are valid dates.
    """

    dates = pd.to_datetime(
        series,
        errors="coerce",

    )

    ratio = dates.notna().mean()

    return ratio >= DATE_THRESHOLD


def is_identifier_column_name(col_name: str) -> bool:
    """
    Checks if a column name indicates it is an ID, code, or phone number.
    These are technically numeric in terms of digits but are semantically identifiers,
    so they should not undergo statistical math (mean, median, etc.).
    """
    name = col_name.lower().strip()
    
    # Standalone "id" or ends/starts with standard separators
    if name == "id" or name.endswith("_id") or name.endswith(" id") or name.endswith("-id"):
        return True
    if name.startswith("id_") or name.startswith("id ") or name.startswith("id-"):
        return True
        
    # Check for concatenated "id" suffixes on common entities
    common_id_names = {
        "customerid", "employeeid", "userid", "saleid", "productid", "itemid", 
        "orderid", "vendorid", "clientid", "memberid", "studentid", "staffid", 
        "agentid", "partnerid", "managerid", "adminid", "personid", "accountid", 
        "transactionid", "txnid", "custid", "empid", "prodid", "orgid"
    }
    if name in common_id_names:
        return True
        
    # Other identifier keywords
    tokens = name.replace("_", " ").replace("-", " ").split()
    id_keywords = {"code", "zip", "pin", "ssn", "phone", "mobile", "account", "card", "serial", "passport"}
    if any(kw in tokens for kw in id_keywords):
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

        if is_numeric_series(series):
            if is_identifier_column_name(str(column)):
                detected[column] = "text"
            else:
                detected[column] = "numeric"

        elif is_date_series(series):
            detected[column] = "date"

        else:
            detected[column] = "text"

    return detected