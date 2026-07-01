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

    prompt = f"""
The previous SQL query is invalid.

Table Name:
`{table_name}`

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

Return ONLY SQL.
"""

    response = client.chat.completions.create(

        model="llama-3.3-70b-versatile",

        messages=[
            {
                "role": "system",
                "content":
                "You repair invalid MySQL queries."
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