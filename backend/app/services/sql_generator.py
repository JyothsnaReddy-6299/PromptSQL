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

You have ONLY ONE TABLE.

Table Name:
`{table_name}`

Schema:
{schema}

Rules:

1. Generate ONLY ONE valid MySQL SELECT query.

2. NEVER generate INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE or REPLACE.

3. Use ONLY the table name provided.

4. Use ONLY the column names provided.

5. NEVER invent columns.

6. NEVER rename columns.

7. If a column contains spaces or special characters,
   ALWAYS wrap it in backticks.

Example:
`Employee Name`
`Product Category`
`Total Sales`

8. If aggregation is needed, use the exact column names.

Example:
SUM(`Total Sales`)

9. If sorting is needed:

ORDER BY `Total Sales` DESC

10. If the question cannot be answered using the schema,
return ONLY:

INVALID_QUERY

11. Return ONLY SQL.
Do NOT explain.
Do NOT use markdown.

User Question:

{question}
"""

    response = client.chat.completions.create(

        model="llama-3.3-70b-versatile",

        messages=[

            {
                "role": "system",
                "content":
                "You convert natural language into MySQL."
            },

            {
                "role": "user",
                "content": prompt
            }

        ]

    )

    sql = response.choices[0].message.content.strip()

    sql = (
        sql
        .replace("```sql", "")
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

    print("\nGenerated SQL")
    print(sql)
    print()

    return sql