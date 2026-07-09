import re
from sqlalchemy import inspect
from app.database.connection import engine
from app.services.schema_service import get_column_names


def validate_modification_sql(sql: str, table_name: str, intent: str) -> dict:
    """
    Validates a generated modification query against safety check constraints.
    """
    sql_clean = sql.lower().strip()
    
    # 1. Operation Consistency
    first_word = sql_clean.split()[0] if sql_clean.split() else ""
    
    intent_map = {
        "INSERT": ["insert", "replace"],
        "UPDATE": ["update"],
        "DELETE": ["delete"],
        "MERGE": ["insert", "merge", "replace"],
        "CREATE": ["create"],
        "ALTER": ["alter"],
        "DROP": ["drop"],
        "RENAME": ["rename", "alter"],
        "TRUNCATE": ["truncate"]
    }
    
    if intent in intent_map:
        allowed_verbs = intent_map[intent]
        if first_word not in allowed_verbs:
            return {
                "valid": False,
                "error": f"SQL query starting verb '{first_word.upper()}' does not match detected intent '{intent}'."
            }
            
    # 2. Table Name references checks
    inspector = inspect(engine)
    all_tables = inspector.get_table_names()
    
    # Table must exist for modification operations (except for CREATE)
    if intent in ["INSERT", "UPDATE", "DELETE", "MERGE", "ALTER", "TRUNCATE", "RENAME"]:
        table_pattern = re.compile(rf"\b`?{table_name}`?\b", re.IGNORECASE)
        if not table_pattern.search(sql):
            return {
                "valid": False,
                "error": f"Query does not reference the active table '{table_name}'."
            }
            
    # 3. Duplicate table creation check
    if intent == "CREATE":
        match = re.search(r"create\s+table\s+(?:if\s+not\s+exists\s+)?`?([a-zA-Z0-9_\s-]+)`?", sql_clean)
        if match:
            created_table = match.group(1).strip()
            if created_table in all_tables:
                return {
                    "valid": False,
                    "error": f"Table '{created_table}' already exists. Duplicate table creation is rejected."
                }
                
    # 4. Column validation for DML operations (except CREATE/ALTER)
    if intent in ["INSERT", "UPDATE", "DELETE", "MERGE"]:
        columns = get_column_names(table_name)
        # Parse all backticked identifiers in SQL query
        identifiers = re.findall(r"`([^`]+)`", sql)
        col_references = [id for id in identifiers if id.lower() != table_name.lower()]
        
        for col in col_references:
            # Skip if it is not in the column list
            if col not in columns:
                return {
                    "valid": False,
                    "error": f"Column `{col}` does not exist in schema of table '{table_name}'."
                }
                
    # 5. Safety rule: UPDATE / DELETE without WHERE
    warning = None
    if intent in ["UPDATE", "DELETE"]:
        if "where" not in sql_clean:
            warning = f"Warning: This {intent} query has no WHERE clause and will affect ALL records in the table!"
            
    return {
        "valid": True,
        "warning": warning,
        "error": None
    }
