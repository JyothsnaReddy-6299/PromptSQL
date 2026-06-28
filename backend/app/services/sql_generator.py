from groq import Groq
from dotenv import load_dotenv
import os

from app.services.schema_service import get_schema

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise Exception("GROQ_API_KEY not found.")

client = Groq(api_key=api_key)


def generate_sql(question, table_name):

    schema = get_schema(table_name)

    schema_text = ""

    for column in schema:
        schema_text += f"{column['name']} ({column['type']})\n"

    prompt = f"""
You are an expert MySQL SQL generator.

The database contains ONE table.

Table Name:
{table_name}

Schema:
{schema_text}

Rules:

1. Use ONLY the columns provided in the schema.
2. NEVER invent table names.
3. NEVER invent column names.
4. Output ONLY one valid MySQL SELECT statement.
5. Never generate INSERT, UPDATE, DELETE, DROP, ALTER, CREATE or TRUNCATE statements.
6. Do not explain your answer.
7. Do not use markdown.
8. Preserve column names exactly as shown.
9. If the question cannot be answered using the available schema, return exactly:
INVALID_QUERY

User Question:
{question}
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "You convert natural language into MySQL queries."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    sql = response.choices[0].message.content.strip()

    sql = sql.replace("```sql", "")
    sql = sql.replace("```", "")
    sql = sql.strip()

    if sql == "INVALID_QUERY":
        raise ValueError(
            "The question cannot be answered using this dataset."
        )

    if not sql.lower().startswith("select"):
        raise ValueError(
            "Only SELECT queries are allowed."
        )

    print("\nGenerated SQL:")
    print(sql)
    print()

    return sql