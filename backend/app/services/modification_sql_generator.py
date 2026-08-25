import os
from dotenv import load_dotenv
from app.services.schema_service import schema_to_prompt
from app.services.llm_service import call_llm

load_dotenv()

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
    15. For columns that are NOT specified in the user's question, always use `NULL` or omit them entirely from the INSERT/UPDATE statement (e.g. omit columns like `date_of_birth` or `name` if they are not mentioned).
    16. NEVER use default placeholder dates like '0000-00-00' or '0000-00-00 00:00:00' because MySQL strict SQL mode (NO_ZERO_DATE) rejects them. Always use `NULL` for date/timestamp columns if the value is not specified.
    
    =========================
    QUESTION
    =========================
    {question}
    """

    system_prompt = "You are a precise MySQL query generator. Return ONLY raw SQL statement. No markdown formatting, no explanations."
    sql = call_llm(system_prompt, prompt, temperature=0.1)
    
    import re

    # Robust SQL Extraction using Regex
    sql_cleaned = sql.strip()
    
    # 1. Try to extract from markdown code blocks
    code_block_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", sql_cleaned, re.DOTALL | re.IGNORECASE)
    if code_block_match:
        sql_cleaned = code_block_match.group(1).strip()
    else:
        # 2. Look for the first valid DML/DDL verb
        verbs = ["insert", "update", "delete", "replace", "merge", "create", "alter", "drop", "rename", "truncate"]
        pattern = r"\b(" + "|".join(verbs) + r")\b.*"
        statement_match = re.search(pattern, sql_cleaned, re.DOTALL | re.IGNORECASE)
        if statement_match:
            sql_cleaned = statement_match.group(0).strip()
            sql_cleaned = re.sub(r"```.*", "", sql_cleaned, flags=re.DOTALL).strip()

    # 3. Verify SQL structural integrity based on intent
    sql_upper = sql_cleaned.upper()
    is_valid_sql_structure = False
    
    if intent == "UPDATE" and " SET " in sql_upper:
        is_valid_sql_structure = True
    elif intent == "DELETE" and " FROM " in sql_upper:
        is_valid_sql_structure = True
    elif intent == "INSERT" and (" INTO " in sql_upper or " VALUES " in sql_upper):
        is_valid_sql_structure = True
    elif intent in ["CREATE", "ALTER", "DROP", "TRUNCATE", "RENAME"]:
        first_word = sql_cleaned.split()[0].upper() if sql_cleaned.split() else ""
        if first_word == intent or (intent == "RENAME" and first_word in ["RENAME", "ALTER"]):
            is_valid_sql_structure = True
            
    if not is_valid_sql_structure:
        raise Exception(
            "The requested query is invalid and cannot be executed (please verify your column names)."
        )

    return sql_cleaned
