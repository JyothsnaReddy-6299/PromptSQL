"""
PromptSQL — Conversational Record Parser & Validator
Extracts, validates, and prepares conversational records for custom table insertion.
Supports single-record and multi-row insertions, detects invalid types, missing fields,
and duplicate submissions, and produces structured preview data.
"""

import json
import re
from datetime import datetime, date
from typing import List, Dict, Any, Tuple, Optional, Set
from dateutil import parser as date_parser
from sqlalchemy import inspect
from app.database.connection import engine
from app.services.llm_service import call_llm
from app.utils.think_stripper import strip_think_blocks


def get_table_schema_metadata(physical_table_name: str) -> List[Dict[str, Any]]:
    """
    Inspects live MySQL table columns, data types, nullability, and primary key status.
    """
    inspector = inspect(engine)
    raw_columns = inspector.get_columns(physical_table_name)
    pk_constraint = inspector.get_pk_constraint(physical_table_name)
    pk_cols = set(pk_constraint.get("constrained_columns", []))

    schema_cols = []
    for col in raw_columns:
        c_name = col["name"]
        c_type = str(col["type"]).upper()
        is_pk = c_name in pk_cols or col.get("primary_key", False)
        autoincrement = col.get("autoincrement", False) or is_pk

        # Categorize type
        cat = "string"
        if "BOOL" in c_type or "TINYINT(1)" in c_type:
            cat = "boolean"
        elif any(t in c_type for t in ["INT", "TINYINT", "SMALLINT", "MEDIUMINT", "BIGINT"]):
            cat = "integer"
        elif any(t in c_type for t in ["DECIMAL", "NUMERIC", "FLOAT", "DOUBLE", "REAL"]):
            cat = "numeric"
        elif "DATETIME" in c_type or "TIMESTAMP" in c_type:
            cat = "datetime"
        elif "DATE" in c_type:
            cat = "date"
        elif "TEXT" in c_type:
            cat = "text"

        schema_cols.append({
            "name": c_name,
            "type_str": c_type,
            "category": cat,
            "nullable": col.get("nullable", True),
            "is_pk": is_pk,
            "autoincrement": autoincrement
        })

    return schema_cols


def resolve_target_table_from_prompt(
    question: str,
    user_id: str,
    user_datasets: List[str],
    current_active_table: Optional[str] = None
) -> Tuple[Optional[str], Optional[str], Optional[List[str]]]:
    """
    Identifies the intended target table from prompt text, authorized user datasets,
    and active dataset context.
    Returns: (resolved_physical_table, error_or_clarification_type, matching_options)
    """
    clean_q = question.strip()

    # 1. Check for cross-tenant attempts (referencing other tenants' _usr_ suffixes)
    other_tenant_matches = re.findall(r"\b([a-zA-Z0-9_]+_usr_[a-zA-Z0-9]+)\b", clean_q, re.IGNORECASE)
    suffix = f"_{user_id}"
    for match in other_tenant_matches:
        if not match.endswith(suffix):
            return None, "cross_tenant_denied", [match]

    # 2. Check which authorized user datasets are explicitly mentioned in prompt
    matching_tables = []
    for tbl in user_datasets:
        friendly = tbl.split(suffix)[0] if tbl.endswith(suffix) else tbl
        # Match word boundaries for friendly name or full physical name
        pattern = rf"\b{re.escape(friendly)}\b|\b{re.escape(tbl)}\b"
        if re.search(pattern, clean_q, re.IGNORECASE):
            matching_tables.append(tbl)

    if len(matching_tables) == 1:
        return matching_tables[0], None, None

    if len(matching_tables) > 1:
        # Prompt mentions multiple authorized tables -> Ambiguous!
        friendly_options = [
            t.split(suffix)[0] if t.endswith(suffix) else t
            for t in matching_tables
        ]
        return None, "ambiguous", friendly_options

    # 3. No table mentioned explicitly: fall back to current active table
    if current_active_table and current_active_table in user_datasets:
        return current_active_table, None, None

    # 4. If only one authorized dataset exists, use it
    if len(user_datasets) == 1:
        return user_datasets[0], None, None

    # 5. Otherwise ambiguous / no dataset specified
    friendly_all = [
        t.split(suffix)[0] if t.endswith(suffix) else t
        for t in user_datasets
    ]
    return None, "ambiguous", friendly_all


def extract_raw_records_with_llm(
    question: str,
    friendly_name: str,
    schema_cols: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Uses LLM to parse natural language text into a structured list of raw record dictionaries.
    Excludes auto-increment PK column 'id' from requiring input.
    """
    # Exclude auto-increment PKs from columns expected from user
    user_cols = [c for c in schema_cols if not (c["is_pk"] and c["autoincrement"])]

    columns_desc = "\n".join([
        f"- `{c['name']}` ({c['type_str']}): Category {c['category']}, {'Optional' if c['nullable'] else 'Required'}"
        for c in user_cols
    ])

    system_prompt = (
        "You are an expert database data parser. "
        "Extract records that the user wants to add or insert into the target table. "
        "Follow these rules strictly:\n"
        "1. Extract EACH record as a JSON object mapping exact column names from the schema to the raw values supplied by the user.\n"
        "2. If multiple records are provided (e.g. bullet points, comma lists, lines), extract all of them as separate objects in the JSON array.\n"
        "3. Map values to the most logical column based on position, header names, or semantics.\n"
        "4. If a column value is NOT provided by the user, set its value to null. DO NOT invent, hallucinate, or fill in default values!\n"
        "5. Keep the user's raw string/number as provided so type validation can inspect it.\n"
        "6. Output ONLY a valid JSON object with key 'records' containing the array of objects. No markdown, no commentary."
    )

    user_message = f"""
Target Table: `{friendly_name}`
Target Columns:
{columns_desc}

User Request:
"{question}"

Output Format:
{{
  "records": [
    {{
      "{user_cols[0]['name'] if user_cols else 'col1'}": "value1"
    }}
  ]
}}
"""

    raw_response = call_llm(system_prompt, user_message, temperature=0.0, max_tokens=1000)
    cleaned = strip_think_blocks(raw_response).strip()

    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)

    try:
        parsed = json.loads(cleaned)
        records = parsed.get("records", [])
        if isinstance(records, list) and len(records) > 0:
            return records
    except Exception as err:
        print(f"Error parsing LLM records JSON: {err}")

    # Resilient heuristic fallback if LLM returned empty or malformed output
    return heuristic_parse_records(question, user_cols)


def heuristic_parse_records(question: str, user_cols: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Heuristically extracts record rows from bullet points, numbered lists, or comma-separated lines.
    """
    col_names = [c["name"] for c in user_cols]
    lines = question.strip().split("\n")
    candidate_lines = []
    for l in lines:
        clean_l = l.strip()
        match = re.match(r"^[-*•\d\.]+\s*(.*)", clean_l)
        if match:
            candidate_lines.append(match.group(1).strip())
        elif "," in clean_l and not any(clean_l.lower().startswith(v) for v in ["add ", "insert ", "please "]):
            candidate_lines.append(clean_l)

    # If no multiline items, check if inline comma-separated values after colon or verb
    if not candidate_lines:
        match_inline = re.search(r"(?:add|insert|records?|details?|table\s+[a-zA-Z0-9_]+)?[:\s]+(.*)", question, re.IGNORECASE)
        if match_inline and "," in match_inline.group(1):
            candidate_lines.append(match_inline.group(1).strip())

    records = []
    for line in candidate_lines:
        parts = [p.strip().strip("'").strip('"') for p in line.split(",") if p.strip()]
        if len(parts) >= 2:
            row = {}
            for idx, part in enumerate(parts):
                if idx < len(col_names):
                    row[col_names[idx]] = part
            if row:
                records.append(row)
    return records


def validate_single_record(
    raw_record: Dict[str, Any],
    schema_cols: List[Dict[str, Any]],
    record_index: int
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Validates a single candidate record against column types, nullability, and calendar rules.
    Returns: (validated_record_dict, error_reason)
    """
    validated = {}
    user_cols = [c for c in schema_cols if not (c["is_pk"] and c["autoincrement"])]

    for col_info in user_cols:
        c_name = col_info["name"]
        cat = col_info["category"]
        nullable = col_info["nullable"]

        # Check if value present in raw_record (case-insensitive key match)
        raw_val = None
        for k, v in raw_record.items():
            if k.lower() == c_name.lower():
                raw_val = v
                break

        # Check missing required field
        if raw_val is None or str(raw_val).strip() == "":
            if not nullable:
                return None, f"Missing required value for column '{c_name}'"
            validated[c_name] = None
            continue

        val_str = str(raw_val).strip()

        # Validate by category
        if cat == "integer":
            lowered = val_str.lower()
            if lowered in ["true", "yes", "active"]:
                validated[c_name] = 1
            elif lowered in ["false", "no", "inactive"]:
                validated[c_name] = 0
            else:
                clean_int_str = val_str.replace(",", "").replace("_", "")
                try:
                    # Check if it has a decimal point
                    if "." in clean_int_str:
                        f_val = float(clean_int_str)
                        if not f_val.is_integer():
                            return None, f"Invalid integer value '{val_str}' for column '{c_name}' (found decimal)"
                        validated[c_name] = int(f_val)
                    else:
                        validated[c_name] = int(clean_int_str)
                except (ValueError, TypeError):
                    return None, f"Invalid integer value '{val_str}' for column '{c_name}'"

        elif cat == "numeric":
            clean_num_str = re.sub(r"[^\d.-]", "", val_str)
            try:
                validated[c_name] = float(clean_num_str)
            except (ValueError, TypeError):
                return None, f"Invalid numeric/decimal value '{val_str}' for column '{c_name}'"

        elif cat == "date":
            # Strict calendar date validation
            try:
                dt = date_parser.parse(val_str, fuzzy=False)
                # Ensure year is reasonable
                if dt.year < 1000 or dt.year > 9999:
                    return None, f"Invalid date year '{dt.year}' for column '{c_name}'"
                validated[c_name] = dt.strftime("%Y-%m-%d")
            except Exception as d_err:
                return None, f"Invalid date '{val_str}' for column '{c_name}': {str(d_err)}"

        elif cat == "datetime":
            try:
                dt = date_parser.parse(val_str, fuzzy=False)
                validated[c_name] = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception as dt_err:
                return None, f"Invalid datetime '{val_str}' for column '{c_name}': {str(dt_err)}"

        elif cat == "boolean":
            lowered = val_str.lower()
            if lowered in ["true", "1", "yes", "active", "y", "t"]:
                validated[c_name] = 1
            elif lowered in ["false", "0", "no", "inactive", "n", "f"]:
                validated[c_name] = 0
            else:
                return None, f"Invalid boolean value '{val_str}' for column '{c_name}'"

        else:
            # String / Text
            validated[c_name] = val_str

    return validated, None


def parse_and_validate_records_for_insert(
    question: str,
    physical_table_name: str,
    friendly_name: str
) -> Dict[str, Any]:
    """
    Full pipeline to parse, type-validate, and structure records for bulk insertion.
    Returns preview data, valid and invalid records, and generated SQL.
    """
    schema_cols = get_table_schema_metadata(physical_table_name)
    user_cols = [c for c in schema_cols if not (c["is_pk"] and c["autoincrement"])]
    col_names = [c["name"] for c in user_cols]

    # 1. Extract candidate records via LLM
    raw_records = extract_raw_records_with_llm(question, friendly_name, schema_cols)
    if not raw_records:
        return {
            "success": False,
            "error": f"Could not detect any valid records to insert into table '{friendly_name}'. Please verify the provided details.",
            "total_records": 0,
            "valid_records_count": 0,
            "invalid_records_count": 0,
            "preview_records": [],
            "invalid_records": []
        }

    valid_records = []
    invalid_records = []
    seen_signatures = set()

    # 2. Validate each record
    for idx, raw_rec in enumerate(raw_records):
        val_rec, reason = validate_single_record(raw_rec, schema_cols, idx + 1)
        if reason:
            invalid_records.append({
                "record_index": idx + 1,
                "raw_record": raw_rec,
                "reason": reason
            })
            continue

        # In-batch duplicate detection
        sig = tuple(sorted((k, str(v)) for k, v in val_rec.items()))
        if sig in seen_signatures:
            invalid_records.append({
                "record_index": idx + 1,
                "raw_record": raw_rec,
                "reason": "Duplicate record in this submission."
            })
            continue
        seen_signatures.add(sig)

        valid_records.append(val_rec)

    # 3. Check if all records are invalid
    if not valid_records:
        first_err = invalid_records[0]["reason"] if invalid_records else "Unknown validation error"
        return {
            "success": False,
            "error": f"All {len(invalid_records)} record(s) failed validation: {first_err}",
            "total_records": len(raw_records),
            "valid_records_count": 0,
            "invalid_records_count": len(invalid_records),
            "preview_records": [],
            "invalid_records": invalid_records
        }

    # 4. Generate clean SQL for valid records
    # Active columns to insert (columns that appear in at least one valid record)
    active_cols = [c for c in col_names if any(c in r and r[c] is not None for r in valid_records)]
    if not active_cols:
        active_cols = col_names

    cols_clause = ", ".join(f"`{c}`" for c in active_cols)

    def format_sql_literal(v: Any) -> str:
        if v is None:
            return "NULL"
        if isinstance(v, (int, float)):
            return str(v)
        # Escape single quotes
        escaped = str(v).replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"

    value_tuples_friendly = []
    value_tuples_physical = []
    for r in valid_records:
        row_vals = [format_sql_literal(r.get(c)) for c in active_cols]
        value_tuples_friendly.append(f"({', '.join(row_vals)})")
        value_tuples_physical.append(f"({', '.join(row_vals)})")

    friendly_sql = (
        f"INSERT INTO `{friendly_name}` ({cols_clause})\nVALUES\n  "
        + ",\n  ".join(value_tuples_friendly)
    )

    physical_sql = (
        f"INSERT INTO `{physical_table_name}` ({cols_clause})\nVALUES\n  "
        + ",\n  ".join(value_tuples_physical)
    )

    # 5. Build impact description
    valid_count = len(valid_records)
    invalid_count = len(invalid_records)
    if invalid_count == 0:
        impact_text = f"Ready to insert {valid_count} record(s) into table `{friendly_name}`."
    else:
        impact_text = (
            f"Ready to insert {valid_count} valid record(s) into table `{friendly_name}`. "
            f"{invalid_count} record(s) failed validation and will not be inserted."
        )

    # Identify any missing optional fields
    missing_fields = []
    for c in col_names:
        if all(r.get(c) is None for r in valid_records):
            missing_fields.append(c)

    return {
        "success": True,
        "is_bulk_insert": True,
        "friendly_sql": friendly_sql,
        "physical_sql": physical_sql,
        "preview_columns": active_cols,
        "preview_records": valid_records,
        "invalid_records": invalid_records,
        "missing_fields": missing_fields,
        "valid_records_count": valid_count,
        "invalid_records_count": invalid_count,
        "total_records": len(raw_records),
        "impact_text": impact_text
    }
