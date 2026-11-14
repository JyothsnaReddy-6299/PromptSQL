from dotenv import load_dotenv
import os
import re
from typing import Optional, Any
from app.services.schema_service import schema_to_prompt
from app.services.llm_service import call_llm

load_dotenv()


def generate_sql(
    question: str,
    table_name: str,
    user_id: Optional[str] = None,
    context: Optional[Any] = None
) -> str:
    from app.services.relationship_service import resolve_query_context

    if context is None and user_id:
        try:
            context = resolve_query_context(question, user_id=user_id, active_table=table_name)
        except Exception as e:
            print("Failed resolving query context dynamically:", e)
            context = None

    if context and context.schemas_prompt:
        schemas_prompt = context.schemas_prompt
        relationships_prompt = context.relationships_prompt
        friendly_name = context.active_table_friendly or (table_name.split("_usr_")[0] if "_usr_" in table_name else table_name)
    else:
        # Fallback for standalone/legacy single-table generation
        from app.database.connection import engine
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tbl_schema = schema_to_prompt(table_name)
        friendly_name = table_name.split("_usr_")[0] if "_usr_" in table_name else table_name
        schemas_prompt = f"Table: `{friendly_name}`\nColumns:\n{tbl_schema}\n"
        relationships_prompt = "None (Single-table query)"

    prompt = f"""
You are an expert MySQL SQL generator.

You have access to the following tables owned by the user. You can query any of these tables, or JOIN them together if the user's question requires information from multiple tables.

=========================
TABLES & SCHEMAS
=========================

{schemas_prompt}

Active Table: `{friendly_name}` (This is the table the user is currently viewing).

=========================
DISCOVERED RELATIONSHIPS & JOIN CONDITIONS
=========================

{relationships_prompt}

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
• Derived metrics (e.g. ratios, rates, margins, completion percentages)
• Period-over-period comparative metrics (Year-over-Year / YoY, Month-over-Month / MoM, Quarter-over-Quarter / QoQ growth)

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

3. Use ONLY the table names listed above. When the question requires data spanning multiple tables, automatically generate JOIN ... ON ... clauses using the DISCOVERED RELATIONSHIPS & JOIN CONDITIONS above. Do not require the user to specify table names or join columns.
   CRITICAL FOR 1:N MULTI-TABLE JOINS (PREVENTING FAN-OUT INFLATION):
   When aggregating columns from a parent table (e.g. `orders.total_amount`) while also joining with a child table that has multiple rows per parent record (e.g. `order_items`), a flat join will DUPLICATE the parent rows and produce inflated sums.
   In such cases, you MUST pre-aggregate child table metrics in a CTE or subquery grouped by the join key before joining to the parent table.
   Example:
   WITH item_totals AS (
       SELECT order_id, SUM(quantity) AS total_items_quantity
       FROM order_items
       GROUP BY order_id
   )
   SELECT 
       c.customer_id,
       c.customer_name,
       SUM(o.total_amount) AS total_order_amount,
       SUM(COALESCE(it.total_items_quantity, 0)) AS total_items_quantity
   FROM customers c
   JOIN orders o ON c.customer_id = o.customer_id
   LEFT JOIN item_totals it ON o.order_id = it.order_id
   GROUP BY c.customer_id, c.customer_name;

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

20. If the question can be completely answered using columns from the Active Table (`{friendly_name}`) alone, query ONLY the Active Table without unnecessary joins. When data from other tables is required, use the DISCOVERED RELATIONSHIPS above to perform the necessary JOINs.

21. When calculating period-over-period growth (such as Year-over-Year / YoY, Month-over-Month / MoM, Quarter-over-Quarter / QoQ):
- Use actual date and numeric columns discovered from the uploaded schemas.
- In a Common Table Expression (CTE) using `WITH period_metrics AS (...)`, aggregate the numeric metric grouped by period (e.g. `YEAR(date_col)` for year, `DATE_FORMAT(date_col, '%Y-%m')` for month, `CONCAT(YEAR(date_col), '-Q', QUARTER(date_col))` for quarter).
- In the outer SELECT query, use `LAG(metric) OVER (ORDER BY period)` to access the previous period.
- Calculate growth as `(current_period - previous_period) / previous_period`, handling a missing previous period (first period) and zero previous-period values safely using:
  CASE 
      WHEN LAG(metric) OVER (ORDER BY period) IS NULL THEN NULL
      WHEN LAG(metric) OVER (ORDER BY period) = 0 THEN NULL
      ELSE ROUND((metric - LAG(metric) OVER (ORDER BY period)) / LAG(metric) OVER (ORDER BY period) * 100, 2)
  END AS growth_percentage
- If required date or numeric columns do not exist in the schema, return ONLY INVALID_QUERY.

22. When calculating aggregate metrics across tables in a 1-to-many (1:N) relationship:
- If aggregating columns from the parent table (e.g. `orders.total_amount`) while joining with child table rows (e.g. `order_items`), DO NOT perform a flat join that duplicates parent rows.
- Instead, pre-aggregate child table metrics in a CTE or subquery grouped by the foreign key (e.g. `order_id`) before joining to the parent table, so each parent record is joined exactly once without inflated totals.
- However, do not blindly pre-aggregate every join: when aggregating child metrics across parent dimensions (e.g. `SUM(orders.total_amount)` grouped by `customers.country`), a standard JOIN is correct and does not duplicate orders.

23. When calculating derived rates, margins, or ratios:
- When input columns exist, compute them using safe arithmetic (e.g. `COUNT(CASE WHEN condition THEN 1 END) / NULLIF(COUNT(*), 0)` or `(revenue - cost) / NULLIF(revenue, 0)`).
- Provide descriptive aliases like `completion_rate`, `profit_margin`, `conversion_rate`, or `growth_percentage`.
- If required input columns (such as cost for profit margin) do not exist in the schema, return ONLY INVALID_QUERY. Never hallucinate or assume unlisted columns.

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