from dotenv import load_dotenv
import os
import json
from app.services.llm_service import call_llm

load_dotenv()

MAX_RECORDS_FOR_SUMMARY = 20


def generate_summary(question, records, is_truncated: bool = False):
    """
    Generates a natural language summary for row-based query results.

    Aggregate queries (COUNT, SUM, AVG, MIN, MAX)
    are handled separately by aggregate_summary.py.
    """

    if not records:
        return "No matching records found."

    sample_records = records[:MAX_RECORDS_FOR_SUMMARY]

    if is_truncated:
        count_instruction = f"""5. The query result was truncated/capped at the system limit.
Mention that {len(records)} matching records are returned as a capped sample.
Do NOT claim or imply that {len(records)} is the total number of matching records in the database."""
        summary_count_instruction = f"""10. If multiple records are returned,
briefly summarize them and mention that {len(records)} records were returned (capped at limit)."""
        disallowed_phrases = """8. Do NOT say things like:
   - "I think..."
   - "It appears...\""""
    else:
        count_instruction = f"""5. If there are multiple rows,
mention the total number of matching records using this number:

Total Matching Records = {len(records)}"""
        summary_count_instruction = """10. If multiple records are returned,
briefly summarize them and mention the total count."""
        disallowed_phrases = """8. Do NOT say things like:
   - "Based on the sample..."
   - "The provided data..."
   - "I think..."
   - "It appears...\""""

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

4. Summarize the records naturally and accurately, highlighting key metrics, dimensions, or patterns where relevant.

{count_instruction}

6. Mention important values whenever appropriate.

7. Keep the answer concise (2-5 sentences).

{disallowed_phrases}

9. If only one record is returned,
describe that record clearly.

{summary_count_instruction}
"""

    system_prompt = "You summarize SQL query results accurately without inventing information."
    return call_llm(system_prompt, prompt, temperature=0.1)
