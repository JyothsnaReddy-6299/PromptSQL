from groq import Groq
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

MAX_RECORDS_FOR_SUMMARY = 20


def generate_summary(question, records):

    if not records:
        return "No matching records found."

    # Send only a sample to avoid token limits
    sample_records = records[:MAX_RECORDS_FOR_SUMMARY]

    prompt = f"""
You are a professional data analyst.

The SQL query has already been executed.

Your job is ONLY to explain the query result.

Question:
{question}

Query Result:
{json.dumps(sample_records, indent=2, default=str)}

Rules:

1. Answer ONLY using the query result.
2. Never invent values.
3. Never mention SQL, databases, JSON or Python.
4. If there is one record, answer naturally.
5. If there are multiple records, summarize them clearly.
6. Keep the answer under 100 words.
7. If values are IDs or names, include them.
"""

    response = client.chat.completions.create(

        model="llama-3.3-70b-versatile",

        messages=[
            {
                "role": "system",
                "content": "You explain SQL query results."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

    )

    return response.choices[0].message.content.strip()