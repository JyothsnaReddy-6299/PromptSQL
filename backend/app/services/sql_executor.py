import pandas as pd
from app.database.connection import engine


def execute_sql(sql_query):

    df = pd.read_sql(sql_query, engine)

    return df.to_dict(orient="records")