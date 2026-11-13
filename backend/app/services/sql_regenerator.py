from dotenv import load_dotenv
import os
import re
from typing import Optional, Any
from app.services.schema_service import schema_to_prompt
from app.services.llm_service import call_llm

load_dotenv()


def regenerate_sql(
    question: str,
    table_name: str,
    previous_sql: str,
    error_message: str,
    user_id: Optional[str] = None,
    context: Optional[Any] = None
) -> str:
    from app.services.relationship_service import resolve_query_context

    if context is None and user_id:
        try:
            context = resolve_query_context(question, user_id=user_id, active_table=table_name)
        except Exception as e:
            print("Failed resolving query context dynamically in regenerator:", e)
            context = None

    if context and context.schemas_prompt:
        schemas_prompt = context.schemas_prompt
        relationships_prompt = context.relationships_prompt
        friendly_name = context.active_table_friendly or (table_name.split("_usr_")[0] if "_usr_" in table_name else table_name)
    else:
        # Fallback for standalone/legacy single-table regeneration
        from app.database.connection import engine
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tbl_schema = schema_to_prompt(table_name)
        friendly_name = table_name.split("_usr_")[0] if "_usr_" in table_name else table_name
        schemas_prompt = f"Table: `{friendly_name}`\nColumns:\n{tbl_schema}\n"
        relationships_prompt = "None (Single-table query)"

    prompt = f"""
The previous SQL query is invalid.

You have access to the following tables owned by the user:

=========================
TABLES & SCHEMAS
=========================

{schemas_prompt}

Active Table: `{friendly_name}`

=========================
DISCOVERED RELATIONSHIPS & JOIN CONDITIONS
=========================

{relationships_prompt}

User Question:

{question}

Previous SQL:

{previous_sql}

Validation Error:

{error_message}

Rules:

1. Correct ONLY the SQL.

2. Keep the user's intent unchanged.

3. Use ONLY the table names listed above. When joining multiple tables, automatically use the DISCOVERED RELATIONSHIPS & JOIN CONDITIONS above.

4. Use ONLY the columns listed in their respective schemas.

5. Preserve column names exactly.

6. Wrap columns containing spaces with backticks.

7. Generate ONLY ONE SELECT query.

8. Do not explain anything.

9. No markdown.

10. If the user request asks to 'display all details', 'show all columns', 'everything', 'all records', 'all information', or does not specify particular fields, use `SELECT *` instead of listing all columns individually.

11. If the question can be completely answered using columns from the Active Table (`{friendly_name}`) alone, query ONLY the Active Table without unnecessary joins. When data from other tables is required, use the DISCOVERED RELATIONSHIPS above to perform the necessary JOINs.

Return ONLY SQL.
"""

    system_prompt = "You repair invalid MySQL queries. Output ONLY raw SQL. No markdown wrappers."
    sql = call_llm(system_prompt, prompt, temperature=0.1)

    # Robust SQL Extraction using Regex
    sql_cleaned = sql.strip()
    
    # 1. Try to extract from markdown code blocks
    code_block_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", sql_cleaned, re.DOTALL | re.IGNORECASE)
    if code_block_match:
        sql_cleaned = code_block_match.group(1).strip()
    else:
        # 2. Look for the first SELECT or WITH statement
        statement_match = re.search(r"\b(SELECT|WITH)\b.*", sql_cleaned, re.DOTALL | re.IGNORECASE)
        if statement_match:
            sql_cleaned = statement_match.group(0).strip()
            # Remove any trailing markdown quotes if present
            sql_cleaned = re.sub(r"```.*", "", sql_cleaned, flags=re.DOTALL).strip()

    return sql_cleaned