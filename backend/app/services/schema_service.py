from sqlalchemy import inspect
from app.database.connection import engine


def get_schema(table_name):

    inspector = inspect(engine)

    if table_name not in inspector.get_table_names():
        raise Exception(f"Table '{table_name}' does not exist.")

    columns = inspector.get_columns(table_name)

    return [
        {
            "name": column["name"],
            "type": str(column["type"])
        }
        for column in columns
    ]