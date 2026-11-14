"""
PromptSQL — Table Schema Generator & Custom Table Validator
Enables AI-assisted schema inference from natural language descriptions
and enforces strict schema validation (identifier naming, reserved words, duplicates).
"""

import json
import re
from typing import List, Dict, Any, Tuple, Optional
from app.services.llm_service import call_llm
from app.utils.think_stripper import strip_think_blocks

# Comprehensive set of MySQL 8.0+ reserved keywords (lowercased)
MYSQL_RESERVED_KEYWORDS = frozenset({
    "accessible", "add", "all", "alter", "analyze", "and", "as", "asc", "asensitive",
    "before", "between", "bigint", "binary", "blob", "both", "by", "call", "cascade",
    "case", "change", "char", "character", "check", "collate", "column", "condition",
    "constraint", "continue", "convert", "create", "cross", "cube", "cume_dist",
    "current_date", "current_time", "current_timestamp", "current_user", "cursor",
    "database", "databases", "day_hour", "day_microsecond", "day_minute", "day_second",
    "dec", "decimal", "declare", "default", "delayed", "delete", "dense_rank", "desc",
    "describe", "deterministic", "distinct", "distinctrow", "div", "double", "drop",
    "dual", "each", "else", "elseif", "empty", "enclosed", "escaped", "except", "exists",
    "exit", "explain", "false", "fetch", "first_value", "float", "float4", "float8",
    "for", "force", "foreign", "from", "fulltext", "function", "group", "grouping",
    "groups", "having", "high_priority", "hour_microsecond", "hour_minute", "hour_second",
    "if", "ignore", "in", "index", "infile", "inner", "inout", "insensitive", "insert",
    "int", "int1", "int2", "int3", "int4", "int8", "integer", "interval", "into", "io_after_gtids",
    "io_before_gtids", "is", "iterate", "join", "json_table", "key", "keys", "kill",
    "lag", "last_value", "lateral", "lead", "leading", "leave", "left", "like", "limit",
    "linear", "lines", "load", "localtime", "localtimestamp", "lock", "long", "longblob",
    "longtext", "loop", "low_priority", "master_bind", "master_ssl_verify_server_cert",
    "match", "maxvalue", "mediumblob", "mediumint", "mediumtext", "middleint",
    "minute_microsecond", "minute_second", "mod", "modifies", "natural", "not",
    "no_write_to_binlog", "nth_value", "ntile", "null", "numeric", "of", "on", "optimize",
    "optimizer_costs", "option", "optionally", "or", "order", "out", "outer", "outfile",
    "over", "partition", "percent_rank", "precision", "primary", "procedure", "purge",
    "range", "rank", "read", "reads", "read_write", "real", "recursive", "references",
    "regexp", "release", "rename", "repeat", "replace", "require", "resignal", "restrict",
    "return", "revoke", "right", "rlike", "row", "rows", "row_number", "schema", "schemas",
    "second_microsecond", "select", "sensitive", "separator", "set", "show", "signal",
    "smallint", "spatial", "specific", "sql", "sqlexception", "sqlstate", "sqlwarning",
    "sql_after_gtids", "sql_after_mts_gaps", "sql_before_gtids", "sql_big_result",
    "sql_buffer_result", "sql_calc_found_rows", "sql_no_cache", "sql_small_result",
    "ssl", "starting", "stored", "straight_join", "system", "table", "terminated", "then",
    "tinyblob", "tinyint", "tinytext", "to", "trailing", "trigger", "true", "undo",
    "union", "unique", "unlock", "unsigned", "update", "usage", "use", "using", "utc_date",
    "utc_time", "utc_timestamp", "values", "varbinary", "varchar", "varcharacter",
    "varying", "virtual", "when", "where", "while", "window", "with", "write", "xor",
    "year_month", "zerofill"
})

ALLOWED_DATA_TYPES = [
    "VARCHAR(255)",
    "TEXT",
    "INT",
    "DOUBLE",
    "DECIMAL(10,2)",
    "DATE",
    "DATETIME",
    "BOOLEAN",
]

TYPE_MAPPINGS = {
    "VARCHAR": "VARCHAR(255)",
    "VARCHAR(255)": "VARCHAR(255)",
    "STRING": "VARCHAR(255)",
    "TEXT": "TEXT",
    "LONGTEXT": "TEXT",
    "LONG TEXT": "TEXT",
    "INT": "INT",
    "INTEGER": "INT",
    "BIGINT": "INT",
    "SMALLINT": "INT",
    "DOUBLE": "DOUBLE",
    "FLOAT": "DOUBLE",
    "NUMBER": "DOUBLE",
    "DECIMAL": "DECIMAL(10,2)",
    "DECIMAL(10,2)": "DECIMAL(10,2)",
    "CURRENCY": "DECIMAL(10,2)",
    "MONEY": "DECIMAL(10,2)",
    "DATE": "DATE",
    "DATETIME": "DATETIME",
    "TIMESTAMP": "DATETIME",
    "BOOLEAN": "BOOLEAN",
    "BOOL": "BOOLEAN",
}


def normalize_sql_type(raw_type: str) -> str:
    """Normalizes any LLM or user-provided type into PromptSQL standard MySQL type."""
    cleaned = (raw_type or "").strip().upper()
    if cleaned in TYPE_MAPPINGS:
        return TYPE_MAPPINGS[cleaned]
    for key, mapped in TYPE_MAPPINGS.items():
        if key in cleaned:
            return mapped
    return "VARCHAR(255)"


def validate_custom_table_schema(
    table_name: str,
    columns: List[Dict[str, Any]]
) -> Tuple[bool, Optional[str]]:
    """
    Validates table name and column definitions against SQL syntax rules,
    PromptSQL primary key conventions, reserved keywords, and duplicate constraints.
    """
    clean_table = re.sub(r"[^a-zA-Z0-9_]", "", (table_name or "").strip()).lower()
    if not clean_table:
        return False, "Table name cannot be empty and must use alphanumeric characters and underscores."

    if clean_table in MYSQL_RESERVED_KEYWORDS:
        return False, f"Table name '{clean_table}' is a reserved SQL keyword."

    if not columns or len(columns) == 0:
        return False, "Table must define at least one column."

    seen_columns = set()
    for col in columns:
        col_name = col.get("name", "") if isinstance(col, dict) else getattr(col, "name", "")
        col_type = col.get("type", "") if isinstance(col, dict) else getattr(col, "type", "")

        raw_col_name = str(col_name).strip()
        if not raw_col_name:
            return False, "Column name cannot be empty."

        clean_col = re.sub(r"[^a-zA-Z0-9_]", "", raw_col_name).lower()
        if not clean_col or clean_col != raw_col_name.lower():
            return False, f"Invalid column name '{raw_col_name}'. Use only letters, numbers, and underscores."

        if clean_col == "id":
            return False, "Column name 'id' is reserved for the primary key (auto-included by PromptSQL)."

        if clean_col in MYSQL_RESERVED_KEYWORDS:
            return False, f"Column name '{clean_col}' is a reserved SQL keyword."

        if clean_col in seen_columns:
            return False, f"Duplicate column name '{clean_col}' detected. Column names must be unique."
        seen_columns.add(clean_col)

        norm_type = normalize_sql_type(str(col_type))
        if norm_type not in ALLOWED_DATA_TYPES:
            return False, f"Unsupported data type '{col_type}' for column '{clean_col}'."

    return True, None


def generate_heuristic_fallback_schema(prompt: str) -> Dict[str, Any]:
    """
    Deterministic rule-based schema generator used as a resilient fallback
    if the external LLM provider experiences rate limits, truncation, or JSON decode errors.
    """
    clean = prompt.lower().strip()
    
    # Table name extraction
    stripped = re.sub(r'^(create|make|build|design|add|new)\s+(a|an|the)?\s*', '', clean)
    stripped = re.sub(r'\s+(table|dataset|schema)$', '', stripped).strip()
    words = re.findall(r'[a-zA-Z0-9]+', stripped)
    table_name = "_".join(words[:3]) if words else "custom_table"

    columns = []
    seen = set()

    with_match = re.search(r'(?:with|columns?|fields?|having)\s+(.*)', clean)
    if with_match:
        cols_text = with_match.group(1)
        raw_cols = re.split(r'[,;]|\band\b', cols_text)
        for rc in raw_cols:
            c_clean = re.sub(r'[^a-zA-Z0-9_]', '_', rc.strip().lower()).strip('_')
            c_clean = re.sub(r'_+', '_', c_clean)
            if not c_clean or c_clean == 'id' or len(c_clean) < 2:
                continue

            t = "VARCHAR(255)"
            if any(k in c_clean for k in ['date', 'day', 'time', 'dob', 'joined', 'joining']):
                t = "DATE"
            elif any(k in c_clean for k in ['salary', 'price', 'amount', 'fee', 'cost', 'rate', 'revenue', 'tax', 'discount']):
                t = "DECIMAL(10,2)"
            elif any(k in c_clean for k in ['quantity', 'count', 'age', 'number', 'qty', 'stock', 'year', 'score']):
                t = "INT"
            elif any(k in c_clean for k in ['is_', 'has_', 'urgent', 'active', 'enabled', 'verified']):
                t = "BOOLEAN"
            elif any(k in c_clean for k in ['description', 'notes', 'comment', 'details', 'address']):
                t = "TEXT"

            if c_clean not in seen:
                columns.append({"name": c_clean, "type": t})
                seen.add(c_clean)

    if not columns:
        if any(w in clean for w in ["employee", "staff", "worker"]):
            columns = [
                {"name": "employee_name", "type": "VARCHAR(255)"},
                {"name": "department", "type": "VARCHAR(255)"},
                {"name": "joining_date", "type": "DATE"},
                {"name": "salary", "type": "DECIMAL(10,2)"},
                {"name": "employment_status", "type": "VARCHAR(255)"}
            ]
        elif any(w in clean for w in ["patient", "appointment", "clinic", "doctor"]):
            columns = [
                {"name": "patient_name", "type": "VARCHAR(255)"},
                {"name": "doctor_name", "type": "VARCHAR(255)"},
                {"name": "appointment_date", "type": "DATE"},
                {"name": "fee", "type": "DOUBLE"},
                {"name": "is_urgent", "type": "BOOLEAN"}
            ]
        elif any(w in clean for w in ["inventory", "stock", "product", "warehouse"]):
            columns = [
                {"name": "item_name", "type": "VARCHAR(255)"},
                {"name": "category", "type": "VARCHAR(255)"},
                {"name": "quantity", "type": "INT"},
                {"name": "unit_price", "type": "DECIMAL(10,2)"},
                {"name": "restock_date", "type": "DATE"}
            ]
        elif any(w in clean for w in ["order", "sale", "invoice", "transaction"]):
            columns = [
                {"name": "order_number", "type": "VARCHAR(255)"},
                {"name": "customer_name", "type": "VARCHAR(255)"},
                {"name": "order_date", "type": "DATE"},
                {"name": "total_amount", "type": "DECIMAL(10,2)"},
                {"name": "order_status", "type": "VARCHAR(255)"}
            ]
        elif any(w in clean for w in ["student", "course", "grade", "school"]):
            columns = [
                {"name": "student_name", "type": "VARCHAR(255)"},
                {"name": "course_name", "type": "VARCHAR(255)"},
                {"name": "enrollment_date", "type": "DATE"},
                {"name": "grade", "type": "VARCHAR(255)"}
            ]
        else:
            columns = [
                {"name": "title", "type": "VARCHAR(255)"},
                {"name": "description", "type": "TEXT"},
                {"name": "status", "type": "VARCHAR(255)"},
                {"name": "created_date", "type": "DATE"}
            ]

    return {
        "success": True,
        "table_name": table_name,
        "explanation": f"Generated schema proposal for '{prompt.strip()}'",
        "columns": columns
    }


def generate_table_schema_from_prompt(prompt: str) -> Dict[str, Any]:
    """
    Generates a proposed custom table schema using Groq LLM based on user natural language description.
    Enforces PromptSQL conventions (auto-omits PK `id`, infers appropriate types, sanitizes names).
    Falls back gracefully to rule-based schema inference if external LLM provider encounters issues.
    """
    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise ValueError("Prompt cannot be empty.")

    system_prompt = (
        "You are an expert database architect specializing in MySQL database design. "
        "Analyze the user's natural language description and extract a structured custom table schema. "
        "IMPORTANT: Do not output reasoning or <think> tags. "
        "Follow these rules strictly:\n"
        "1. Generate a concise, meaningful snake_case table name (e.g. employee_management, patient_appointments, inventory_stock).\n"
        "2. Infer column names and the most appropriate data types from the description.\n"
        "3. Allowed data types: VARCHAR(255), TEXT, INT, DOUBLE, DECIMAL(10,2), DATE, DATETIME, BOOLEAN.\n"
        "4. DO NOT include an 'id' column. PromptSQL automatically adds `id` INT AUTO_INCREMENT PRIMARY KEY.\n"
        "5. DO NOT invent extra columns that were not requested or clearly required by the description.\n"
        "6. Avoid MySQL reserved words (e.g. do not use 'order', 'group', 'select', 'table', 'date', 'status' alone; use 'order_date', 'group_name', 'employment_status', etc.).\n"
        "7. Output ONLY a valid JSON object with keys: table_name (string), explanation (brief string), and columns (array of objects with 'name' and 'type'). No markdown, no prose."
    )

    user_message = f"""
Describe your proposed table schema in JSON for:
"{clean_prompt}"

Output format:
{{
  "table_name": "table_name_here",
  "explanation": "Brief description of the table",
  "columns": [
    {{"name": "column_name", "type": "DATA_TYPE"}}
  ]
}}
"""

    data = None
    try:
        raw_response = call_llm(system_prompt, user_message, temperature=0.1, max_tokens=1200)
        cleaned_json = strip_think_blocks(raw_response).strip()

        # Extract JSON if enclosed in markdown code fences or brackets
        json_match = re.search(r"\{.*\}", cleaned_json, re.DOTALL)
        if json_match:
            cleaned_json = json_match.group(0)

        if cleaned_json:
            data = json.loads(cleaned_json)
    except Exception as llm_err:
        print(f"[Schema Generator] LLM generation error ({llm_err}). Using rule-based schema generator.")

    # Resilient fallback if LLM returned invalid or empty JSON
    if not data or not isinstance(data, dict) or not data.get("columns"):
        return generate_heuristic_fallback_schema(clean_prompt)

    raw_table_name = data.get("table_name", "custom_table")
    clean_table_name = re.sub(r"[^a-zA-Z0-9_]", "", raw_table_name).lower()
    if not clean_table_name or clean_table_name in MYSQL_RESERVED_KEYWORDS:
        clean_table_name = f"{clean_table_name}_table" if clean_table_name else "custom_dataset"

    raw_columns = data.get("columns", [])
    if not isinstance(raw_columns, list) or len(raw_columns) == 0:
        raise ValueError("Could not extract any columns from the description.")

    sanitized_columns = []
    seen = set()

    for col in raw_columns:
        if not isinstance(col, dict):
            continue
        c_name = col.get("name", "")
        c_clean = re.sub(r"[^a-zA-Z0-9_]", "", str(c_name)).lower()
        if not c_clean:
            continue
        if c_clean == "id":
            # Auto-skip 'id' since PromptSQL auto-injects it
            continue

        # If reserved keyword, append '_val' or '_col'
        if c_clean in MYSQL_RESERVED_KEYWORDS:
            c_clean = f"{c_clean}_val"

        # Deduplicate
        original_c_clean = c_clean
        dup_counter = 2
        while c_clean in seen:
            c_clean = f"{original_c_clean}_{dup_counter}"
            dup_counter += 1
        seen.add(c_clean)

        norm_type = normalize_sql_type(str(col.get("type", "VARCHAR(255)")))
        sanitized_columns.append({
            "name": c_clean,
            "type": norm_type
        })

    if not sanitized_columns:
        raise ValueError("No valid columns could be derived from the description.")

    return {
        "success": True,
        "table_name": clean_table_name,
        "explanation": data.get("explanation", f"Custom table with {len(sanitized_columns)} columns"),
        "columns": sanitized_columns
    }
