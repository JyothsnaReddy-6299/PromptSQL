from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise Exception("GROQ_API_KEY not found.")

client = Groq(api_key=api_key)


def explain_impact(sql: str, table_name: str, intent: str, estimated_rows: int) -> str:
    """
    Generates a brief human-readable explanation of the query's impact before execution.
    """
    prompt = f"""
    Explain the impact of the following database modification statement before it is executed.
    
    Query Details:
    - Operation Type: {intent}
    - Active Table: {table_name}
    - Estimated Affected Rows: {estimated_rows}
    - Generated SQL: {sql}
    
    Rules:
    - Briefly explain what this statement will change in the database.
    - Highlight safety notes (e.g. if UPDATE/DELETE is updating all rows, or if dropping a table).
    - Give examples of rows affected: e.g. "This query will delete 245 rows." or "This query will update 18 records."
    - Be clear, professional, and concise. Maximum 2 sentences.
    - Return ONLY the explanation text. No greeting, no quotes, no markdown.
    """
    
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a database impact analyst. Provide a short 1-2 sentence warning/explanation of the query's impact."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1
        )
        return response.choices[0].message.content.strip()
    except Exception:
        # Fallback explanations
        if intent == "DELETE":
            return f"This operation will delete {estimated_rows} records from table {table_name}."
        if intent == "UPDATE":
            return f"This operation will update {estimated_rows} records in table {table_name}."
        if intent == "DROP":
            return f"This operation will permanently delete (DROP) the table {table_name} and all its data."
        if intent == "TRUNCATE":
            return f"This operation will truncate (clear) all {estimated_rows} rows inside the table {table_name}."
        return f"This operation will perform a {intent} action on table {table_name}."
