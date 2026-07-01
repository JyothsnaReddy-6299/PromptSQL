from groq import Groq
from dotenv import load_dotenv
import os

from app.services.schema_service import schema_to_prompt

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise Exception("GROQ_API_KEY not found.")

client = Groq(api_key=api_key)


def generate_sql(question, table_name):

    schema = schema_to_prompt(table_name)

    prompt = f"""
You are an expert MySQL SQL generator.

You have EXACTLY ONE TABLE.

=========================
TABLE NAME
=========================

`{table_name}`

=========================
SCHEMA
=========================

{schema}

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

Then identify:

• Output columns
• Filter columns
• Aggregate column
• Grouping column
• Sorting column

ONLY from the schema above.

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

3. Use ONLY the table name provided.

4. Use ONLY the column names provided.

5. NEVER invent column names.

6. NEVER rename columns.

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

=========================
QUESTION
=========================

{question}
"""

    response = client.chat.completions.create(

        model="llama-3.3-70b-versatile",

        messages=[

            {
                "role": "system",
                "content":
                "You are an expert MySQL query generator. Never invent tables or columns."
            },

            {
                "role": "user",
                "content": prompt
            }

        ]

    )

    sql = response.choices[0].message.content.strip()

    sql = (
        sql.replace("```sql", "")
           .replace("```", "")
           .strip()
    )

    if sql == "INVALID_QUERY":
        raise Exception(
            "This question cannot be answered using the uploaded dataset."
        )

    if not sql.lower().startswith("select"):
        raise Exception(
            "Only SELECT queries are allowed."
        )

    print("\nGenerated SQL:")
    print(sql)
    print()

    return sql