import pandas as pd
from sqlalchemy import Integer, Float, DateTime, Text


def detect_mysql_types(df: pd.DataFrame):
    """
    Automatically detects appropriate MySQL column types
    for any uploaded dataframe.
    """

    dtype_mapping = {}

    for column in df.columns:

        # Remove commas from numeric values
        cleaned = (
            df[column]
            .astype(str)
            .str.replace(",", "", regex=False)
        )

        # Try integer
        try:
            numeric = pd.to_numeric(cleaned)

            # Integer column
            if (numeric.dropna() % 1 == 0).all():
                dtype_mapping[column] = Integer()
            else:
                dtype_mapping[column] = Float()

            continue

        except Exception:
            pass

        # Try datetime
        try:

            parsed = pd.to_datetime(
                df[column],
                errors="raise"
            )

            dtype_mapping[column] = DateTime()

            continue

        except Exception:
            pass

        # Default text
        dtype_mapping[column] = Text()

    return dtype_mapping