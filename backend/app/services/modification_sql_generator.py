from groq import Groq
import os
from dotenv import load_dotenv
from app.services.schema_service import schema_to_prompt

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise Exception("GROQ_API_KEY not found.")

client = Groq(api_key=api_key)


def generate_modification_sql(question: str, table_name: str, intent: str) -> str:
    """
    Generates a valid MySQL statement matching a DML/DDL intent type.
    """
    schema = schema_to_prompt(table_name)
    friendly_name = table_name.split("_usr_")[0] if "_usr_" in table_name else table_name
    
    prompt = f"""
    You are an expert MySQL query generator.
    Generate a valid MySQL statement for the user question and the specified active table.
    
    =========================
    ACTIVE TABLE NAME
    =========================
    `{friendly_name}`
    
    =========================
    SCHEMA
    =========================
    {schema}
    
    =========================
    INTENT TYPE
    =========================
    {intent}
    
    =========================
    RULES
    =========================
    1. Generate ONLY ONE valid MySQL statement matching the intent "{intent}".
    2. Use ONLY the table name provided. Do not invent other table names.
    3. Use column names EXACTLY as they appear in the schema. Do not rename or invent column names.
    4. If column names or table names contain spaces or special characters, always wrap them in backticks (e.g. `First Name`, `Quantity Ordered`).
    5. Generate proper SQL syntax for MySQL.
    6. For INSERT: generate "INSERT INTO `{friendly_name}` (col1, col2) VALUES (val1, val2)"
    7. For UPDATE: generate "UPDATE `{friendly_name}` SET col1 = val1 WHERE ..."
    8. For DELETE: generate "DELETE FROM `{friendly_name}` WHERE ..."
    9. For MERGE/UPSERT in MySQL, use "INSERT INTO `{friendly_name}` ... ON DUPLICATE KEY UPDATE ..."
    10. For ALTER: generate "ALTER TABLE `{friendly_name}` ADD COLUMN `new_col` TEXT", "ALTER TABLE `{friendly_name}` DROP COLUMN `old_col`", etc.
    11. For DROP: generate "DROP TABLE `{friendly_name}`"
    12. For TRUNCATE: generate "TRUNCATE TABLE `{friendly_name}`"
    13. For RENAME: generate "RENAME TABLE `{friendly_name}` TO `new_name`"
    14. Output ONLY the raw SQL code. Do NOT explain. Do NOT use markdown code blocks.
    
    =========================
    QUESTION
    =========================
    {question}
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "You are a precise MySQL query generator. Return ONLY raw SQL statement. No markdown formatting, no explanations."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.1
    )
    
    sql = response.choices[0].message.content.strip()
    
    # Strip markdown wrappers if any
    sql = (
        sql.replace("```sql", "")
           .replace("```", "")
           .strip()
    )
    return sql
