from sqlalchemy import inspect
from app.database.connection import engine


def get_schema(table_name):
    """
    Returns the schema of a table.

    Example:
    [
        {
            "name": "Order ID",
            "type": "TEXT"
        },
        {
            "name": "Product Category",
            "type": "TEXT"
        }
    ]
    """

    inspector = inspect(engine)

    tables = inspector.get_table_names()

    if table_name not in tables:
        raise Exception(f"Table '{table_name}' does not exist.")

    columns = inspector.get_columns(table_name)

    schema = []

    for column in columns:

        schema.append(
            {
                "name": column["name"],
                "type": str(column["type"])
            }
        )

    return schema


def schema_to_prompt(table_name):
    """
    Converts schema into text for the LLM prompt.
    """

    schema = get_schema(table_name)

    prompt = ""

    for column in schema:

        prompt += (
            f"- `{column['name']}` ({column['type']})\n"
        )

    return prompt


def get_column_names(table_name):
    """
    Returns only column names.
    """

    schema = get_schema(table_name)

    return [
        column["name"]
        for column in schema
    ]