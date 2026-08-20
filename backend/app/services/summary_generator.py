from dotenv import load_dotenv
import os
import json
from app.services.llm_service import call_llm

load_dotenv()

MAX_RECORDS_FOR_SUMMARY = 20


def generate_summary(question, records):
    """
    Generates a natural language summary for row-based query results.

    Aggregate queries (COUNT, SUM, AVG, MIN, MAX)
    are handled separately by aggregate_summary.py.
    """

    if not records:
        return "No matching records found."

    sample_records = records[:MAX_RECORDS_FOR_SUMMARY]

    prompt = f"""
You are an expert data analyst.

A SQL query has already been executed.

User Question:
{question}

Returned Records:
{json.dumps(sample_records, indent=2, default=str)}

Instructions:

1. Answer ONLY using the returned records.

2. Never invent facts.

3. Never assume there are more records than shown.

4. If the records contain employee details,
summarize them naturally.

5. If there are multiple rows,
mention the total number of matching records using this number:

Total Matching Records = {len(records)}

6. Mention important values whenever appropriate.

7. Keep the answer concise (2-5 sentences).

8. Do NOT say things like:
   - "Based on the sample..."
   - "The provided data..."
   - "I think..."
   - "It appears..."

9. If only one record is returned,
describe that record clearly.

10. If multiple records are returned,
briefly summarize them and mention the total count.
"""

    system_prompt = "You summarize SQL query results accurately without inventing information."
    return call_llm(system_prompt, prompt, temperature=0.1)