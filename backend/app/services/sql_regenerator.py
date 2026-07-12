from groq import Groq
from dotenv import load_dotenv
import os

from app.services.schema_service import schema_to_prompt

load_dotenv()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)


def regenerate_sql(
    question,
    table_name,
    previous_sql,
    error_message
):

    schema = schema_to_prompt(table_name)
    friendly_name = table_name.split("_usr_")[0] if "_usr_" in table_name else table_name

    prompt = f"""
The previous SQL query is invalid.

Table Name:
`{friendly_name}`

Schema:

{schema}

User Question:

{question}

Previous SQL:

{previous_sql}

Validation Error:

{error_message}

Rules:

1. Correct ONLY the SQL.

2. Keep the user's intent unchanged.

3. Use ONLY the table above.

4. Use ONLY the columns listed in the schema.

5. Preserve column names exactly.

6. Wrap columns containing spaces with backticks.

7. Generate ONLY ONE SELECT query.

8. Do not explain anything.

9. No markdown.

10. If the user request asks to 'display all details', 'show all columns', 'everything', 'all records', 'all information', or does not specify particular fields, use `SELECT *` instead of listing all columns individually.

Return ONLY SQL.
"""

    response = client.chat.completions.create(

        model="llama-3.3-70b-versatile",

        messages=[
            {
                "role": "system",
                "content":
                "You repair invalid MySQL queries. Output ONLY raw SQL. No markdown wrappers."
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

    return sql