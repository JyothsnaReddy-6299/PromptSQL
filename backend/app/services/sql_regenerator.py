from dotenv import load_dotenv
import os
from app.services.schema_service import schema_to_prompt
from app.services.llm_service import call_llm

load_dotenv()


def regenerate_sql(
    question,
    table_name,
    previous_sql,
    error_message,
    user_id=None
):
    from app.database.connection import engine
    from sqlalchemy import inspect

    inspector = inspect(engine)
    all_tables = inspector.get_table_names()
    suffix = f"_{user_id}" if user_id else ""
    
    if suffix:
        user_tables = [t for t in all_tables if t.endswith(suffix) and t not in ["query_history", "audit_logs", "users"]]
    else:
        user_tables = [table_name]
        
    if table_name not in user_tables:
        user_tables.append(table_name)
        
    schemas_prompt = ""
    for t in user_tables:
        friendly_tbl = t.split("_usr_")[0]
        tbl_schema = schema_to_prompt(t)
        schemas_prompt += f"Table: `{friendly_tbl}`\nColumns:\n{tbl_schema}\n"

    friendly_name = table_name.split("_usr_")[0] if "_usr_" in table_name else table_name

    prompt = f"""
The previous SQL query is invalid.

You have access to the following tables owned by the user:

=========================
TABLES & SCHEMAS
=========================

{schemas_prompt}

Active Table: `{friendly_name}`

User Question:

{question}

Previous SQL:

{previous_sql}

Validation Error:

{error_message}

Rules:

1. Correct ONLY the SQL.

2. Keep the user's intent unchanged.

3. Use ONLY the table names listed above. You can JOIN them using foreign/primary key relationships if needed.

4. Use ONLY the columns listed in their respective schemas.

5. Preserve column names exactly.

6. Wrap columns containing spaces with backticks.

7. Generate ONLY ONE SELECT query.

8. Do not explain anything.

9. No markdown.

10. If the user request asks to 'display all details', 'show all columns', 'everything', 'all records', 'all information', or does not specify particular fields, use `SELECT *` instead of listing all columns individually.

11. If the user's question is ambiguous and does not mention a specific table name, ALWAYS prioritize and default to querying from the Active Table (`{friendly_name}`) rather than other tables. Only query or join other tables if the question explicitly references them or fields unique to them.

Return ONLY SQL.
"""

    system_prompt = "You repair invalid MySQL queries. Output ONLY raw SQL. No markdown wrappers."
    sql = call_llm(system_prompt, prompt, temperature=0.1)

    sql = (
        sql
        .replace("```sql", "")
        .replace("```", "")
        .strip()
    )

    return sql