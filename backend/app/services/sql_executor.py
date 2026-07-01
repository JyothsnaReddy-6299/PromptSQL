import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database.connection import engine


MAX_ROWS = 10000


def execute_sql(sql_query):
    """
    Executes a validated SELECT query.
    Returns the result as a list of dictionaries.
    """

    try:

        with engine.connect() as connection:

            result = connection.execute(
                text(sql_query)
            )

            rows = result.fetchmany(MAX_ROWS)

            columns = result.keys()

            records = [
                dict(zip(columns, row))
                for row in rows
            ]

            return records

    except SQLAlchemyError as e:

        raise Exception(
            f"MySQL Execution Error:\n{str(e)}"
        )