import time
from sqlalchemy import text
from app.database.connection import engine
from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise Exception("GROQ_API_KEY not found.")

client = Groq(api_key=api_key)


def execute_modification(sql: str, table_name: str, intent: str) -> dict:
    """
    Executes a DML or DDL query inside a transaction, rolling back automatically
    on exception, and returns rows affected and execution time.
    """
    start_time = time.time()
    
    try:
        # engine.begin() automatically starts a transaction, commits on success, and rolls back on failure
        with engine.begin() as connection:
            result = connection.execute(text(sql))
            rows_affected = result.rowcount
            
        elapsed_time_ms = (time.time() - start_time) * 1000
        
        # Rowcount can be negative or None for certain operations/DDLs
        if rows_affected is None or rows_affected < 0:
            rows_affected = 0
            
        ai_message = generate_confirmation_message(intent, table_name, rows_affected, sql)
        
        return {
            "success": True,
            "rows_affected": rows_affected,
            "execution_time_ms": round(elapsed_time_ms, 2),
            "sql": sql,
            "message": ai_message,
            "error": None
        }
    except Exception as e:
        elapsed_time_ms = (time.time() - start_time) * 1000
        return {
            "success": False,
            "rows_affected": 0,
            "execution_time_ms": round(elapsed_time_ms, 2),
            "sql": sql,
            "message": "Database execution failed. Transaction rolled back successfully.",
            "error": str(e)
        }


def generate_confirmation_message(intent: str, table_name: str, rows_affected: int, sql: str) -> str:
    """
    Generates a professional confirmation message using Llama model based on result.
    """
    prompt = f"""
    You are a database system confirmation generator.
    Generate a professional, human-readable confirmation message for a database modification query that was executed successfully.
    
    Execution Details:
    - Operation Type (Intent): {intent}
    - Table Name: {table_name}
    - Rows Affected: {rows_affected}
    - Executed SQL: {sql}
    
    Rules:
    - Describe what happened clearly and concisely.
    - Examples:
      "18 employee records were updated successfully."
      "1 new record inserted."
      "Table renamed successfully."
      "The Product table was truncated successfully."
    - Do NOT hallucinate. Use ONLY the execution details provided.
    - Return ONLY the confirmation message text. No quotes, no markdown, no greetings.
    """
    
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a database confirmation writer. Output only the short confirmation message text."
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
        # Fallback confirmations
        if intent == "INSERT":
            return f"1 record inserted into {table_name} successfully."
        if intent == "UPDATE":
            return f"{rows_affected} records updated in {table_name} successfully."
        if intent == "DELETE":
            return f"{rows_affected} records deleted from {table_name} successfully."
        if intent == "TRUNCATE":
            return f"Table {table_name} truncated successfully."
        if intent == "DROP":
            return f"Table {table_name} dropped successfully."
        return f"Database operation {intent} executed successfully on {table_name}."
