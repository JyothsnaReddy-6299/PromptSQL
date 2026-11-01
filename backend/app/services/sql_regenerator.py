from dotenv import load_dotenv
import os
import re
from app.services.schema_service import schema_to_prompt
from app.services.llm_service import call_llm

load_dotenv()


def regenerate_sql(
    question,
    table_name,
    previous_sql,
    error_message,
    user_id=None,
    relationship_ids=None,
    required_tables=None,
    value_bindings=None
):
    from app.services.sql_generator import query_prompt_context
    schemas_prompt,relationship_prompt,metric_prompt,friendly_name = query_prompt_context(
        question,table_name,user_id,relationship_ids,required_tables)

    from app.services.value_grounding import grounding_prompt
    value_prompt = grounding_prompt(value_bindings)
    prompt = f"""
The previous SQL query is invalid.

You have access to the following tables owned by the user:

=========================
TABLES & SCHEMAS
=========================

{schemas_prompt}
{relationship_prompt}
{metric_prompt}
{value_prompt}

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

3. Use ONLY the selected table names and the exact APPROVED join key mappings. Never infer joins from generic primary keys.

4. Use ONLY the columns listed in their respective schemas.

5. Preserve column names exactly.

6. Wrap columns containing spaces with backticks.

7. Generate ONLY ONE SELECT query.

8. Do not explain anything.

9. No markdown.

10. If the user request asks to 'display all details', 'show all columns', 'everything', 'all records', 'all information', or does not specify particular fields, use `SELECT *` instead of listing all columns individually.

11. Preserve the SELECTED DATASETS and every MEASURED FILTER BINDING. Active Table is context. Do not move a measured name filter to an identifier column.

12. The error may be a database execution error as well as a validation error. Fix its cause while preserving ALL requested filters, dimensions, dates, and metric semantics. Output aliases are not physical schema columns. Totals without a breakdown must not GROUP BY their own measure.

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