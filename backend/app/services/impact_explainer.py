import os
from typing import Optional
from app.services.llm_service import call_llm


def explain_impact(sql: str, table_name: str, intent: str, estimated_rows: Optional[int]) -> str:
    """
    Generates a brief human-readable explanation of the query's impact before execution.
    """
    friendly_name = table_name.split("_usr_")[0] if "_usr_" in table_name else table_name
    est_display = f"{estimated_rows} rows" if estimated_rows is not None else "Unknown (unreliable)"

    prompt = f"""
    Explain the impact of the following database modification statement before it is executed.
    
    Query Details:
    - Operation Type: {intent}
    - Active Table: {friendly_name}
    - Estimated Affected Rows: {est_display}
    - Generated SQL: {sql}
    
    Rules:
    - Briefly explain what this statement will change in the database.
    - Highlight safety notes (e.g. if UPDATE/DELETE is updating all rows, or if dropping a table).
    - Give examples of rows affected: e.g. "This query will delete {est_display}."
    - For DROP or TRUNCATE, clearly mention that the data loss is permanent and cannot be rolled back.
    - Be clear, professional, and concise. Maximum 2 sentences.
    - Return ONLY the explanation text. No greeting, no quotes, no markdown.
    """
    
    try:
        system_prompt = "You are a database impact analyst. Provide a short 1-2 sentence warning/explanation of the query's impact."
        return call_llm(system_prompt, prompt, temperature=0.1)
    except Exception:
        # Deterministic fallback explanations
        if intent == "DELETE":
            if estimated_rows is not None:
                return f"This operation will delete {estimated_rows} record(s) from table '{friendly_name}'."
            return f"This operation will delete matching records from table '{friendly_name}'. Impact could not be estimated reliably."
        if intent == "UPDATE":
            if estimated_rows is not None:
                return f"This operation will update {estimated_rows} record(s) in table '{friendly_name}'."
            return f"This operation will update matching records in table '{friendly_name}'. Impact could not be estimated reliably."
        if intent == "INSERT":
            if estimated_rows is not None:
                return f"This operation will insert {estimated_rows} record(s) into table '{friendly_name}'."
            return f"This operation will insert records into table '{friendly_name}'."
        if intent == "DROP":
            rows_str = f"all {estimated_rows} records and schema structure" if estimated_rows is not None else "the table and all records"
            return f"CRITICAL: This operation will permanently DROP table '{friendly_name}', erasing {rows_str}. This action commits immediately and cannot be rolled back."
        if intent == "TRUNCATE":
            rows_str = f"all {estimated_rows} records" if estimated_rows is not None else "all records"
            return f"CRITICAL: This operation will TRUNCATE table '{friendly_name}', permanently deleting {rows_str}. This action commits immediately and cannot be rolled back."
        if intent == "ALTER":
            return f"This operation will modify the schema definition of table '{friendly_name}'. MySQL DDL commits immediately and cannot be rolled back."
        return f"This operation will perform a {intent} action on table '{friendly_name}'."
