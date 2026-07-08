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
            detected[column] = "numeric"

        elif is_date_series(series):
            detected[column] = "date"

        else:
            detected[column] = "text"

    return detected