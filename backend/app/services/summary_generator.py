from groq import Groq
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise Exception("GROQ_API_KEY not found.")

client = Groq(api_key=api_key)


def generate_summary(question, records):

    if not records:
        return "No matching records found."

    # IMPORTANT: prevent token overflow
    records = records[:20]

    prompt = f"""
You are a data analyst.

Question:
{question}

Data (sample only):
{records}

Rules:
- Answer ONLY using data
- Do not invent values
- Keep it short and meaningful
- Mention key names/values if present
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "You summarize SQL results."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content.strip()