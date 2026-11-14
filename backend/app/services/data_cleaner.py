import re
import pandas as pd


def clean_numeric(series: pd.Series) -> pd.Series:
    """
    Cleans numeric values.

    Examples

    92,368          -> 92368
    ₹1,75,391       -> 175391
    $45,200.50      -> 45200.50
    24%             -> 24
    (1,250)         -> -1250
    """

    s = series.astype(str)

    # remove surrounding spaces
    s = s.str.strip()

    # remove currency symbols
    s = s.str.replace(r"[₹$€£]", "", regex=True)

    # remove commas
    s = s.str.replace(",", "", regex=False)

    # remove percentage sign
    s = s.str.replace("%", "", regex=False)

    # convert (1234) -> -1234
    s = s.str.replace(
        r"\((.*?)\)",
        r"-\1",
        regex=True
    )

    # keep only
    # digits
    # decimal
    # minus
    s = s.str.replace(
        r"[^0-9.\-]",
        "",
        regex=True
    )

    return pd.to_numeric(
        s,
        errors="coerce"
    )


def clean_date(series: pd.Series) -> pd.Series:
    """
    Converts a column into datetime.
    """

    return pd.to_datetime(
        series,
        errors="coerce",
    )


def clean_text(series: pd.Series) -> pd.Series:
    """
    Cleans text columns while preserving true missing values as None (SQL NULL),
    and preserving legitimate text values (like 'None', 'nan') as strings.
    """
    is_na = series.isna()
    s = series.copy()
    non_na = s[~is_na].astype(str)
    non_na = non_na.str.replace(r"\s+", " ", regex=True).str.strip()
    empty_str_mask = non_na == ""

    result = pd.Series(index=series.index, dtype=object)
    result[~is_na] = non_na
    result[is_na] = None
    if empty_str_mask.any():
        empty_indices = non_na[empty_str_mask].index
        result[empty_indices] = None

    return result


def clean_dataframe(df, detected_types):
    """
    Cleans every column according to its datatype.
    """

    cleaned = df.copy()

    for column, dtype in detected_types.items():

        if dtype == "numeric":

            cleaned[column] = clean_numeric(
                cleaned[column]
            )

        elif dtype == "date":

            cleaned[column] = clean_date(
                cleaned[column]
            )

        else:

            cleaned[column] = clean_text(
                cleaned[column]
            )

    return cleaned