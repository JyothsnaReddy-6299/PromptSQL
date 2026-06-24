import pandas as pd


def analyze_dataset(filepath):

    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)

    else:
        df = pd.read_excel(filepath)



    rows = len(df)

    columns = len(df.columns)

    missing = int(df.isnull().sum().sum())



    return {

        "rows": rows,

        "columns": columns,

        "missing_values": missing,

        "column_names": list(df.columns)

    }