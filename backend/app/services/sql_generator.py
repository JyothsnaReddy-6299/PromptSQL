from dotenv import load_dotenv
import os
import re
from app.services.schema_service import schema_to_prompt
from app.services.llm_service import call_llm

load_dotenv()


def generate_sql(question, table_name, user_id=None):
    from app.database.connection import engine
    from sqlalchemy import inspect

    inspector = inspect(engine)
    all_tables = inspector.get_table_names()
    suffix = f"_{user_id}" if user_id else ""
    
    user_tables = [table_name]
    if suffix:
        all_user_tables = [t for t in all_tables if t.endswith(suffix) and t not in ["query_history", "audit_logs", "users"]]
        question_lower = question.lower()
        for t in all_user_tables:
            if t != table_name:
                friendly_tbl = t.split("_usr_")[0].lower()
                if friendly_tbl in question_lower or friendly_tbl.replace("_", " ") in question_lower:
                    user_tables.append(t)
        
    schemas_prompt = ""
    for t in user_tables:
        friendly_tbl = t.split("_usr_")[0]
        tbl_schema = schema_to_prompt(t)
        schemas_prompt += f"Table: `{friendly_tbl}`\nColumns:\n{tbl_schema}\n"

    friendly_name = table_name.split("_usr_")[0] if "_usr_" in table_name else table_name

    prompt = f"""
You are an expert MySQL SQL generator.

You have access to the following tables owned by the user. You can query any of these tables, or JOIN them together if the user's question requires information from multiple tables.

=========================
TABLES & SCHEMAS
=========================

{schemas_prompt}

Active Table: `{friendly_name}` (This is the table the user is currently viewing).

=========================
YOUR TASK
=========================

First understand the user's intent.

Possible intents include:

• Retrieve records
• Filter records
• Count records
• Sum values
• Average values
• Maximum value
• Minimum value
• Highest total
• Lowest total
• Top N
• Bottom N
• Group-wise aggregation
• Sorting
• Date filtering
• Multi-table joins

Then identify:

• Output columns
• Filter columns
• Aggregate column
• Grouping column
• Sorting column

ONLY from the schemas above.

Never invent anything.

=========================
RULES
=========================

1. Generate ONLY ONE valid MySQL SELECT query.

2. NEVER generate:
INSERT
UPDATE
DELETE
DROP
ALTER
CREATE
TRUNCATE
REPLACE

3. Use ONLY the table names listed above. You can JOIN them using foreign/primary key relationships if needed.

4. Use ONLY the column names listed in their respective schemas.

5. NEVER invent column names.

6. NEVER rename columns unless using aliases for clarity (e.g. `tableName`.`columnName` or `alias`.`columnName`).

7. Preserve column names EXACTLY as they appear.

8. If a column contains spaces,
always wrap it with backticks.

Example:

`Employee Name`

`Product Category`

`Total Sales`

9. Never replace spaces with underscores.

Wrong:

Total_Sales

Correct:

`Total Sales`

10. Never convert column names to lowercase.

11. If the question asks:

highest

lowest

top

bottom

maximum

minimum

largest

smallest

then generate the proper SQL using:

ORDER BY

LIMIT

GROUP BY

SUM

AVG

COUNT

MAX

MIN

whichever is appropriate.

12. If aggregation is required,
generate GROUP BY correctly.

13. If sorting is required,
generate ORDER BY correctly.

14. If a numeric column is stored as TEXT,
cast it before aggregation.

Example:

SUM(
CAST(`Total Sales` AS DECIMAL(18,2))
)

15. If the question cannot be answered using the schema,

return ONLY

INVALID_QUERY

16. Return ONLY SQL.

Do NOT explain.

Do NOT use markdown.

17. If the user request asks to 'display all details', 'show all columns', 'everything', 'all records', 'all information', or does not specify particular fields (implied select all), use `SELECT *` instead of listing all columns individually.

18. When filtering text or string columns in WHERE clauses, ALWAYS use clean, simple exact matches (e.g., `columnName` = 'value'). Do NOT wrap columns in complex functions like `TRIM()` or `LOWER()` inside the WHERE clause, as the dataset is already sanitized on upload. NEVER use `LIKE '%value%'` by default for specific name or category filters. Only use `LIKE` with wildcards if the user explicitly asks for partial matching (e.g., "contains", "starts with").

19. NEVER perform mathematical aggregate operations (like SUM, AVG, MIN, MAX) on columns representing identifiers or codes (e.g., column names containing 'id', 'code', 'zip', 'phone', 'ssn', 'pin', 'card', 'account', 'serial', 'number', 'mobile'). If the user requests calculations on these fields, return INVALID_QUERY or count them using COUNT instead.

20. If the user's question is ambiguous and does not mention a specific table name, ALWAYS prioritize and default to querying from the Active Table (`{friendly_name}`) rather than other tables. Only query or join other tables if the question explicitly references them or fields unique to them.

=========================
QUESTION
=========================

{question}
"""

    system_prompt = "You are an expert MySQL query generator. Never invent tables or columns. Output ONLY the raw SQL code."
    sql = call_llm(system_prompt, prompt, temperature=0.1)

    # Robust SQL Extraction using Regex
    sql_cleaned = sql.strip()
    
    # 1. Check for INVALID_QUERY first
    if "INVALID_QUERY" in sql_cleaned:
        raise Exception(
            "The requested query is invalid and cannot be executed."
        )
        
    # 2. Try to extract from markdown code blocks
    code_block_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", sql_cleaned, re.DOTALL | re.IGNORECASE)
    if code_block_match:
        sql_cleaned = code_block_match.group(1).strip()
    else:
        # 3. Look for the first SELECT or WITH statement
        statement_match = re.search(r"\b(SELECT|WITH)\b.*", sql_cleaned, re.DOTALL | re.IGNORECASE)
        if statement_match:
            sql_cleaned = statement_match.group(0).strip()
            # Remove any trailing markdown quotes if present
            sql_cleaned = re.sub(r"```.*", "", sql_cleaned, flags=re.DOTALL).strip()

    is_write_query = any(sql_cleaned.lower().startswith(kw) for kw in ["insert", "update", "delete", "drop", "alter", "create", "truncate", "replace"])
    if is_write_query:
        raise Exception(
            "The requested query is invalid and cannot be executed."
        )

    # If it is not a SELECT/WITH query and not a write query, it is conversational error text from the AI
    if not sql_cleaned.lower().startswith("select") and not sql_cleaned.lower().startswith("with"):
        raise Exception(
            "The requested query is invalid and cannot be executed (please verify your column names)."
        )

    print("\nGenerated SQL:")
    print(sql_cleaned)
    print()

    return sql_cleaned