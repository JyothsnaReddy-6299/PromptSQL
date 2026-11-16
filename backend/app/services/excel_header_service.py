"""
PromptSQL — Robust Excel Header Detection & Multi-Sheet Import Engine (Issue 18)

Implements intelligent header-row detection for .xlsx and .xls files:
1. Evaluates candidate rows using multi-signal scoring (density, text ratio, uniqueness,
   label length, business keywords, title/description penalty, and subsequent row data-type contrast).
2. Detects and discounts merged banner/title cells via openpyxl inspection.
3. Automatically computes confidence scores and flags ambiguous header candidates.
4. Normalizes column names (trims whitespace, disambiguates duplicates, names empty columns).
5. Preserves data integrity: excludes header from records, preserves leading zeros for text identifiers,
   preserves valid zero values, dates, and maintains true NULLs (no string 'nan' or 'None').
6. Supports multi-worksheet discovery, independent sheet analysis, and interactive preview generation.
"""

import os
import re
from typing import Dict, List, Optional, Any, Tuple, Set
import pandas as pd
import numpy as np

try:
    import openpyxl
except ImportError:
    openpyxl = None


COMMON_HEADER_KEYWORDS = {
    "id", "code", "name", "title", "date", "time", "amount", "total", "price", "cost",
    "sales", "revenue", "qty", "quantity", "count", "status", "type", "category",
    "desc", "description", "department", "dept", "region", "city", "state", "country",
    "phone", "email", "address", "user", "customer", "employee", "order", "product",
    "item", "unit", "discount", "tax", "year", "month", "day", "profit", "value",
    "percent", "pct", "rate", "balance", "gender", "age", "salary", "wage", "score",
    "marks", "grade", "role", "number", "no", "first", "last", "full_name"
}

TITLE_OR_META_KEYWORDS = {
    "report", "summary", "overview", "dashboard", "prepared by", "generated on",
    "as of", "confidential", "internal use", "table", "instructions", "note:", "notes:",
    "disclaimer", "copyright", "version", "author:", "source:", "sheet", "page 1",
    "quarterly", "annual", "monthly", "weekly", "welcome", "system"
}


def get_excel_sheet_names(filepath: str) -> List[str]:
    """
    Returns list of all worksheet names in an Excel workbook.
    """
    if not os.path.exists(filepath):
        raise ValueError(f"Excel file not found at path: {filepath}")

    try:
        excel_file = pd.ExcelFile(filepath)
        return excel_file.sheet_names
    except Exception as e:
        raise ValueError(f"Failed to inspect Excel worksheets: {str(e)}")


def detect_merged_title_rows(filepath: str, sheet_name: str) -> Set[int]:
    """
    Detects 0-based row indices that contain horizontal merged cells spanning
    2 or more columns (typical of sheet titles and banner text).
    """
    merged_rows: Set[int] = set()
    if not openpyxl or not filepath.endswith(".xlsx"):
        return merged_rows

    try:
        wb = openpyxl.load_workbook(filepath, data_only=True, read_only=False)
        if sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            for rng in ws.merged_cells.ranges:
                # If merged cell spans horizontally across 2 or more columns
                if (rng.max_col - rng.min_col) >= 1:
                    # In openpyxl, rows are 1-based; convert to 0-based
                    for r in range(rng.min_row, rng.max_row + 1):
                        merged_rows.add(r - 1)
        wb.close()
    except Exception:
        pass

    return merged_rows


def _is_empty_cell(val: Any) -> bool:
    """Checks whether a cell value is null, NaN, or whitespace."""
    if val is None:
        return True
    if pd.isna(val):
        return True
    s = str(val).strip()
    return s == "" or s.lower() in ("nan", "none", "null", "<na>")


def _is_text_label(val: Any) -> bool:
    """Checks whether a cell looks like a textual column label."""
    if _is_empty_cell(val):
        return False
    if isinstance(val, (int, float, np.integer, np.floating)):
        # Pure floats or large ints are usually data; 4-digit years (e.g. 2024) can be headers
        if isinstance(val, (int, np.integer)) and 1900 <= val <= 2100:
            return True
        return False
    if hasattr(val, "year") and hasattr(val, "month"):
        return False
    # Check string
    s = str(val).strip()
    if not s:
        return False
    # Check if string is a numeric float (e.g. "150.50")
    try:
        float(s)
        if re.match(r"^(19\d\d|20\d\d)$", s):
            return True
        return False
    except ValueError:
        pass
    return True


def _score_candidate_row(
    row_idx: int,
    raw_df: pd.DataFrame,
    max_non_empty: int,
    merged_rows: Set[int]
) -> float:
    """
    Computes heuristic score for a candidate header row.
    Higher score indicates higher likelihood of being the true column header row.
    """
    row_vals = raw_df.iloc[row_idx].tolist()
    non_empty = [v for v in row_vals if not _is_empty_cell(v)]
    n_count = len(non_empty)

    if n_count == 0:
        return -100.0

    # 1. Merged banner penalty
    if row_idx in merged_rows:
        return -50.0

    # 2. Single-cell penalty (Title / description)
    if n_count == 1 and max_non_empty >= 2:
        return -30.0

    score = 0.0

    # 3. Cell density relative to widest row
    density = n_count / max(1, max_non_empty)
    score += density * 30.0

    # 4. Text-like proportion
    text_count = sum(1 for v in non_empty if _is_text_label(v))
    text_ratio = text_count / n_count
    score += text_ratio * 35.0

    # Penalize rows that contain obvious numeric or date data values
    num_data_count = sum(
        1 for v in non_empty
        if (isinstance(v, (int, float, np.integer, np.floating)) and not (1900 <= v <= 2100))
        or hasattr(v, "year")
        or (isinstance(v, str) and bool(re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", str(v).strip())))
    )
    if num_data_count > 0:
        score -= 25.0 + (num_data_count / n_count) * 40.0

    # 5. Uniqueness ratio
    norm_vals = [str(v).strip().lower() for v in non_empty]
    unique_count = len(set(norm_vals))
    uniqueness = unique_count / n_count
    score += uniqueness * 15.0

    # 6. Label length sanity
    avg_len = sum(len(str(v).strip()) for v in non_empty) / n_count
    if 2 <= avg_len <= 30:
        score += 10.0
    elif avg_len > 40:
        # Long narrative sentences indicate instructions or notes
        score -= 25.0

    # 7. Keyword recognition
    keyword_matches = 0
    title_matches = 0
    for v in norm_vals:
        # Check title words
        if any(tw in v for tw in TITLE_OR_META_KEYWORDS):
            title_matches += 1
        # Check header keywords (word boundary or token match)
        tokens = set(re.split(r"[\s_\-\.]+", v))
        if tokens & COMMON_HEADER_KEYWORDS or any(v.endswith(f"_{k}") or v.startswith(f"{k}_") for k in ("id", "date", "code", "no")):
            keyword_matches += 1

    score += min(keyword_matches * 5.0, 25.0)
    score -= title_matches * 15.0

    # 8. Subsequent row data-type contrast (Crucial signal!)
    # If this row is a header, the next row (or row+2) should contain DATA records
    next_row_idx = row_idx + 1
    while next_row_idx < len(raw_df):
        next_vals = raw_df.iloc[next_row_idx].tolist()
        next_non_empty = [v for v in next_vals if not _is_empty_cell(v)]
        if len(next_non_empty) > 0:
            break
        next_row_idx += 1

    if next_row_idx < len(raw_df):
        next_vals = raw_df.iloc[next_row_idx].tolist()
        contrast_count = 0
        total_compared = 0
        for col_i in range(min(len(row_vals), len(next_vals))):
            curr_v = row_vals[col_i]
            next_v = next_vals[col_i]
            if _is_empty_cell(curr_v) or _is_empty_cell(next_v):
                continue
            total_compared += 1
            curr_is_text = _is_text_label(curr_v)
            next_is_num = isinstance(next_v, (int, float, np.integer, np.floating))
            next_is_date = hasattr(next_v, "year") or (isinstance(next_v, str) and re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", next_v.strip()))
            
            # String header above numeric/date data = high contrast
            if curr_is_text and (next_is_num or next_is_date):
                contrast_count += 1
            # Numeric/date above numeric/date = two consecutive data rows
            elif not curr_is_text and (next_is_num or next_is_date):
                contrast_count -= 1

        if total_compared > 0:
            score += (contrast_count / total_compared) * 25.0
    else:
        # Candidate has no subsequent data rows to head
        score -= 20.0

    return score


def detect_header_row(
    filepath: str,
    sheet_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Automatically detects the true column header row index (0-based) for an Excel sheet.
    
    Returns:
    {
        "sheet_name": "Sheet1",
        "header_row_0_based": 2,
        "header_row_1_based": 3,
        "confidence": 0.92,
        "is_ambiguous": False,
        "top_candidates": [(2, 85.2), (1, 32.1)]
    }
    """
    sheets = get_excel_sheet_names(filepath)
    if not sheets:
        raise ValueError("The Excel workbook contains no worksheets.")

    if not sheet_name or sheet_name not in sheets:
        sheet_name = sheets[0]

    # Read the first 35 rows as raw matrix with dtype=object to preserve string types
    try:
        raw_df = pd.read_excel(
            filepath,
            sheet_name=sheet_name,
            header=None,
            nrows=35,
            dtype=object
        )
    except Exception as e:
        raise ValueError(f"Failed to inspect Excel sheet '{sheet_name}': {str(e)}")

    if raw_df.empty:
        return {
            "sheet_name": sheet_name,
            "header_row_0_based": 0,
            "header_row_1_based": 1,
            "confidence": 0.0,
            "is_ambiguous": False,
            "top_candidates": []
        }

    merged_rows = detect_merged_title_rows(filepath, sheet_name)

    # Calculate max non-empty cells across candidate rows
    row_counts = [sum(1 for v in raw_df.iloc[i] if not _is_empty_cell(v)) for i in range(len(raw_df))]
    max_non_empty = max(row_counts) if row_counts else 0

    scores: List[Tuple[int, float]] = []
    for r in range(len(raw_df)):
        score = _score_candidate_row(r, raw_df, max_non_empty, merged_rows)
        scores.append((r, score))

    scores.sort(key=lambda x: x[1], reverse=True)

    best_row, best_score = scores[0]
    runner_up_row, runner_up_score = scores[1] if len(scores) > 1 else (-1, -100.0)

    # Normalize confidence between 0.0 and 1.0
    if best_score <= 0:
        confidence = 0.20
        is_ambiguous = True
        best_row = 0
    else:
        confidence = round(min(1.0, max(0.2, best_score / 100.0)), 2)
        # Check margin with runner up
        score_diff = best_score - runner_up_score
        diff_ratio = score_diff / max(1.0, best_score)

        # Verify runner_up is a genuinely plausible header candidate (not a data row with numbers)
        runner_up_is_plausible = False
        if runner_up_score >= 50.0 and runner_up_row >= 0:
            ru_vals = [v for v in raw_df.iloc[runner_up_row].tolist() if not _is_empty_cell(v)]
            ru_has_numeric = any(
                isinstance(v, (int, float, np.integer, np.floating)) and not (1900 <= v <= 2100)
                for v in ru_vals
            )
            if not ru_has_numeric:
                runner_up_is_plausible = True

        if runner_up_is_plausible and (score_diff <= 30.0 or diff_ratio <= 0.30):
            is_ambiguous = True
            confidence = min(confidence, 0.65)
        else:
            is_ambiguous = False

    return {
        "sheet_name": sheet_name,
        "header_row_0_based": int(best_row),
        "header_row_1_based": int(best_row) + 1,
        "confidence": float(confidence),
        "is_ambiguous": bool(is_ambiguous),
        "top_candidates": [(int(r) + 1, round(s, 1)) for r, s in scores[:3] if s > 0]
    }


def normalize_column_names(raw_headers: List[Any]) -> Tuple[List[str], List[str]]:
    """
    Sanitizes, deduplicates, and fills empty column headers while retaining understandable names.
    
    Returns:
      (clean_columns, warnings)
    """
    clean_cols: List[str] = []
    warnings: List[str] = []
    seen_names: Dict[str, int] = {}

    for i, h in enumerate(raw_headers):
        is_empty = _is_empty_cell(h)
        h_str = "" if is_empty else str(h).strip()

        # Check if cell is empty or pandas-generated placeholder (e.g. Unnamed: 2)
        if is_empty or not h_str or re.match(r"^unnamed:\s*\d+$", h_str, re.IGNORECASE):
            col_name = f"Column_{i + 1}"
            warnings.append(f"Empty heading at column {i + 1} was assigned '{col_name}'.")
        else:
            # Strip pandas automatic duplicate suffix like '.1', '.2' if present from raw duplicate
            m = re.match(r"^(.*?)\.\d+$", h_str)
            base_name = m.group(1).strip() if m else h_str
            col_name = base_name if base_name else f"Column_{i + 1}"

        # Disambiguate duplicate column names
        norm_key = col_name.lower()
        if norm_key in seen_names:
            seen_names[norm_key] += 1
            disambiguated = f"{col_name}_{seen_names[norm_key]}"
            warnings.append(f"Duplicate column '{col_name}' at position {i + 1} was renamed to '{disambiguated}'.")
            col_name = disambiguated
        else:
            seen_names[norm_key] = 0

        clean_cols.append(col_name)

    return clean_cols, warnings


def auto_select_excel_worksheet(filepath: str) -> str:
    """
    Automatically identifies and selects the appropriate worksheet from an Excel workbook (Issue 18.1).
    
    Selection Strategy:
    1. If the workbook contains only one sheet, select it automatically.
    2. If multiple sheets exist, inspect each sheet's structure:
       - Ignore completely blank sheets.
       - Ignore obvious instruction, readme, notes, guide, or metadata sheets.
       - Disqualify sheets without valid tabular structure (less than 2 columns, 0 data rows, or low header confidence).
    3. If exactly one worksheet contains tabular data, select it automatically.
    4. If multiple worksheets contain tabular data:
       - Evaluate composite suitability (confidence, column count, data rows).
       - If multiple worksheets are equally plausible, raise a clear ValueError asking the user to simplify
         the workbook rather than silently importing the wrong sheet.
       - Otherwise, select the unambiguously superior data sheet.
    """
    sheets = get_excel_sheet_names(filepath)
    if not sheets:
        raise ValueError("The Excel workbook contains no worksheets.")

    if len(sheets) == 1:
        return sheets[0]

    # Evaluate all sheets
    sheet_candidates = []
    instruction_keywords = (
        "instruction", "instructions", "readme", "read_me", "notes", "note",
        "help", "guide", "info", "information", "metadata", "about", "cover",
        "contents", "glossary", "documentation"
    )

    for s in sheets:
        try:
            raw_df = pd.read_excel(filepath, sheet_name=s, header=None, nrows=35, dtype=object)
        except Exception:
            continue

        if raw_df.empty:
            continue

        # Check total non-empty cells
        total_non_empty = sum(
            sum(1 for v in raw_df.iloc[r] if not _is_empty_cell(v))
            for r in range(len(raw_df))
        )
        if total_non_empty == 0:
            continue

        # Run header detection for this sheet
        try:
            detection = detect_header_row(filepath, sheet_name=s)
        except Exception:
            continue

        header_idx = detection["header_row_0_based"]
        conf = detection["confidence"]
        is_ambig = detection["is_ambiguous"]

        # Header columns count
        header_vals = [v for v in raw_df.iloc[header_idx].tolist() if not _is_empty_cell(v)]
        col_count = len(header_vals)

        # Count data rows below header
        data_rows = 0
        for r in range(header_idx + 1, len(raw_df)):
            if any(not _is_empty_cell(v) for v in raw_df.iloc[r]):
                data_rows += 1

        s_clean = s.lower().strip()
        is_instruction_name = any(k in s_clean for k in instruction_keywords)

        # Check if text is mostly long narrative paragraphs (instruction content)
        all_cells = [str(v).strip() for row in raw_df.values for v in row if not _is_empty_cell(v)]
        avg_text_len = (sum(len(c) for c in all_cells) / max(1, len(all_cells))) if all_cells else 0
        is_narrative = (avg_text_len > 45 and col_count <= 2)

        # A valid tabular data sheet must have:
        # - at least 2 columns
        # - at least 1 data row
        # - header confidence >= 0.50
        # - not an obvious instruction or narrative notes sheet
        if col_count >= 2 and data_rows >= 1 and conf >= 0.50 and not is_instruction_name and not is_narrative:
            # Composite suitability score
            suitability = (conf * 50.0) + (min(col_count, 15) * 2.5) + (min(data_rows, 20) * 1.5)
            sheet_candidates.append({
                "sheet_name": s,
                "confidence": conf,
                "is_ambiguous": is_ambig,
                "col_count": col_count,
                "data_rows": data_rows,
                "suitability": suitability
            })

    if not sheet_candidates:
        # No sheet cleanly qualified as tabular data sheet; default to first sheet
        return sheets[0]

    if len(sheet_candidates) == 1:
        return sheet_candidates[0]["sheet_name"]

    # Multiple tabular data candidate sheets: check if equally plausible
    sheet_candidates.sort(key=lambda x: x["suitability"], reverse=True)
    top_sheet = sheet_candidates[0]
    runner_up = sheet_candidates[1]

    # Equal plausibility condition:
    # Both have high confidence, valid columns and rows, and score margin is very narrow (within 15%)
    score_diff = top_sheet["suitability"] - runner_up["suitability"]
    diff_ratio = score_diff / max(1.0, top_sheet["suitability"])

    if (
        top_sheet["confidence"] >= 0.70
        and runner_up["confidence"] >= 0.70
        and top_sheet["col_count"] >= 2
        and runner_up["col_count"] >= 2
        and (score_diff <= 15.0 or diff_ratio <= 0.15)
    ):
        raise ValueError(
            f"The workbook contains multiple plausible data worksheets ('{top_sheet['sheet_name']}', '{runner_up['sheet_name']}'). "
            f"Please simplify the workbook to contain only the single worksheet you wish to import."
        )

    return top_sheet["sheet_name"]


def load_excel_with_detected_header(
    filepath: str,
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Loads an Excel sheet using automatic worksheet selection and intelligent header detection (Issue 18.1).
    
    If header_row is not explicitly provided:
    - Enforces confidence threshold (>= 0.60).
    - Enforces unambiguous header candidates (is_ambiguous == False).
    - Stops import and raises clear user-friendly ValueError if headers cannot be reliably identified.
    
    Returns:
      (cleaned_dataframe, metadata_dict)
    """
    if not sheet_name:
        resolved_sheet = auto_select_excel_worksheet(filepath)
    else:
        resolved_sheet = sheet_name

    detection = detect_header_row(filepath, sheet_name=resolved_sheet)

    # If user provided header_row (1-based), use it; otherwise enforce automatic detection safeguards
    if header_row is not None and header_row >= 1:
        header_row_0 = header_row - 1
        confidence = 1.0
        is_ambiguous = False
    else:
        # Safeguard 1: Ambiguity check
        if detection["is_ambiguous"]:
            raise ValueError(
                "Unable to reliably identify column headings in this Excel worksheet because "
                "multiple plausible heading rows were detected. Please simplify the worksheet "
                "layout and ensure column headers are distinct from title and data rows."
            )

        # Safeguard 2: Confidence threshold
        if detection["confidence"] < 0.60:
            raise ValueError(
                "Unable to reliably identify column headings in this Excel worksheet. "
                "Please ensure your table has clear column headers and simplify the sheet structure."
            )

        header_row_0 = detection["header_row_0_based"]
        confidence = detection["confidence"]
        is_ambiguous = False

    # Read Excel sheet with header_row_0
    STANDARD_NA_VALUES = ['', '#N/A', '#NA', 'N/A', '<NA>', 'NULL', 'null', 'NaN', '-NaN']
    
    # Read raw dataframe starting from header row
    df = pd.read_excel(
        filepath,
        sheet_name=resolved_sheet,
        header=header_row_0,
        keep_default_na=False,
        na_values=STANDARD_NA_VALUES,
        dtype=object  # Preserves strings with leading zeros ('00123') and prevents type corruption
    )

    if df.empty and len(df.columns) == 0:
        raise ValueError(f"No records or columns found in worksheet '{resolved_sheet}'.")

    # Normalize column names
    clean_columns, col_warnings = normalize_column_names(df.columns.tolist())
    df.columns = clean_columns

    if len(df) > 0:
        # Drop completely blank columns (all NA or empty string)
        non_blank_cols = []
        for c in df.columns:
            s = df[c]
            has_val = s.map(lambda v: not _is_empty_cell(v)).any()
            if has_val:
                non_blank_cols.append(c)

        if non_blank_cols:
            df = df[non_blank_cols]

        # Drop completely empty rows after the header
        row_has_data = df.apply(lambda row: any(not _is_empty_cell(v) for v in row), axis=1)
        df = df[row_has_data].reset_index(drop=True)

    metadata = {
        "sheet_name": resolved_sheet,
        "header_row_0_based": header_row_0,
        "header_row_1_based": header_row_0 + 1,
        "confidence": confidence,
        "is_ambiguous": is_ambiguous,
        "warnings": col_warnings,
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "columns": df.columns.tolist()
    }

    return df, metadata
