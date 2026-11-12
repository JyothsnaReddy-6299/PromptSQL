"""
PromptSQL — SQL Query Execution Service with Database-Level Safeguards

Enforces:
1. AST-based physical query bounding (MAX_ROWS = 1000, capped at MAX_ROWS + 1).
2. MySQL MAX_EXECUTION_TIME optimizer hint injection (default 15000 ms).
3. Database-level read-only transaction lifecycle (START TRANSACTION READ ONLY ... rollback).
4. Safe result fetching with truncation reporting (records, is_truncated).
5. Clean resource cleanup and connection invalidation upon rollback failure.
"""

from dataclasses import dataclass
import datetime
from decimal import Decimal
import json
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import sqlglot
from sqlglot import exp

from app.database.connection import engine
from app.utils.json_helper import sanitize_for_json


DEFAULT_MAX_ROWS: int = 1000
MAX_ROWS: int = DEFAULT_MAX_ROWS  # Backward compatibility constant
DEFAULT_TIMEOUT_MS: int = 15000
DEFAULT_MAX_RESULT_BYTES: int = 5 * 1024 * 1024  # 5 MB maximum serialized result bytes
DEFAULT_MAX_CELL_BYTES: int = 1024 * 1024        # 1 MB maximum individual cell size
DEFAULT_MAX_HISTORY_ROWS: int = 100               # 100 rows maximum persisted in QueryHistory
DEFAULT_MAX_HISTORY_BYTES: int = 256 * 1024       # 256 KB maximum payload persisted in QueryHistory


class ResultSizeLimitError(ValueError):
    """Raised when a result cell or row exceeds configured byte limits."""
    pass


class ExecutionResult(tuple):
    """
    Result tuple of (records, is_truncated) preserving 100% backward compatibility
    for 2-tuple unpacking while exposing rich safeguard metadata attributes.
    """
    def __new__(
        cls,
        records: List[Dict[str, Any]],
        is_truncated: bool,
        truncation_reason: Optional[str] = None,
        returned_rows: int = 0,
        result_size_bytes: int = 0,
        total_rows: Optional[int] = None
    ):
        inst = super().__new__(cls, (records, is_truncated))
        inst.records = records
        inst.is_truncated = is_truncated
        inst.truncation_reason = truncation_reason
        inst.returned_rows = returned_rows
        inst.result_size_bytes = result_size_bytes
        inst.total_rows = total_rows if total_rows is not None else (len(records) if not is_truncated else None)
        return inst


def _process_cell(val: Any, col: str, max_cell_bytes: int) -> Tuple[Any, int]:
    """
    Converts non-JSON-native database types into JSON-safe types and measures
    UTF-8 byte size. Enforces max_cell_bytes limit on individual cells.
    """
    if val is None:
        return None, 4
    elif isinstance(val, bool):
        return val, 4 if val else 5
    elif isinstance(val, (int, float)):
        b_len = len(str(val).encode("utf-8"))
        return val, b_len
    elif isinstance(val, Decimal):
        v = format(val, "f")
        b_len = len(v.encode("utf-8")) + 2
        if b_len > max_cell_bytes:
            raise ResultSizeLimitError(
                f"Result cell exceeds maximum allowed size of {max_cell_bytes} bytes "
                f"({b_len} bytes in column '{col}')."
            )
        return v, b_len
    elif isinstance(val, (datetime.date, datetime.datetime)):
        s = val.isoformat()
        b_len = len(s.encode("utf-8")) + 2
        return s, b_len
    elif isinstance(val, (bytes, bytearray)):
        try:
            s = val.decode("utf-8")
        except UnicodeDecodeError:
            s = val.hex()
        b_len = len(s.encode("utf-8")) + 2
        if b_len > max_cell_bytes:
            raise ResultSizeLimitError(
                f"Result cell exceeds maximum allowed size of {max_cell_bytes} bytes "
                f"({b_len} bytes in column '{col}')."
            )
        return s, b_len
    elif isinstance(val, str):
        b_len = len(val.encode("utf-8")) + 2
        if b_len > max_cell_bytes:
            raise ResultSizeLimitError(
                f"Result cell exceeds maximum allowed size of {max_cell_bytes} bytes "
                f"({b_len} bytes in column '{col}')."
            )
        return val, b_len
    elif isinstance(val, (dict, list)):
        s = json.dumps(sanitize_for_json(val))
        b_len = len(s.encode("utf-8"))
        if b_len > max_cell_bytes:
            raise ResultSizeLimitError(
                f"Result cell exceeds maximum allowed size of {max_cell_bytes} bytes "
                f"({b_len} bytes in column '{col}')."
            )
        return json.loads(s), b_len
    else:
        s = str(val)
        b_len = len(s.encode("utf-8")) + 2
        if b_len > max_cell_bytes:
            raise ResultSizeLimitError(
                f"Result cell exceeds maximum allowed size of {max_cell_bytes} bytes "
                f"({b_len} bytes in column '{col}')."
            )
        return s, b_len


def prepare_bounded_query(
    sql_query: str,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    max_rows: int = DEFAULT_MAX_ROWS
) -> str:
    """
    Transforms a validated read-only SQL query to enforce:
    1. Programmatic MySQL MAX_EXECUTION_TIME optimizer hint.
    2. Physical root-level row limit capped at (max_rows + 1).

    Preserves:
    - Existing stricter user-specified LIMITs.
    - Existing OFFSET and ORDER BY clauses.
    - Existing compatible optimizer hints.
    - Parentheses and lexical structure.
    """
    if not sql_query or not sql_query.strip():
        raise ValueError("SQL query must not be empty.")

    try:
        parsed = [stmt for stmt in sqlglot.parse(sql_query.strip(), read="mysql") if stmt is not None]
    except Exception as e:
        raise ValueError(f"Invalid SQL syntax: {e}") from e

    if len(parsed) == 0:
        raise ValueError("SQL query must contain at least one statement.")
    if len(parsed) > 1:
        raise ValueError("Multiple statements are not permitted.")

    root = parsed[0]

    # Unwrap outer parenthesis / subquery layers
    curr = root
    while isinstance(curr, exp.Subquery) and curr.this:
        curr = curr.this

    if not isinstance(curr, (exp.Select, exp.Union)):
        raise ValueError(f"Unsupported root query structure: {type(curr).__name__}")

    target_node = curr

    # -------------------------------------------------------------
    # 1. Programmatic Optimizer Hint (MAX_EXECUTION_TIME)
    # -------------------------------------------------------------
    # For SELECT, attach hint directly.
    # For UNION / UNION ALL, attach hint to the first SELECT in the leftmost branch.
    if isinstance(target_node, exp.Select):
        hint_target = target_node
    else:
        union_curr = target_node
        while isinstance(union_curr, exp.Union):
            union_curr = union_curr.this
        while isinstance(union_curr, exp.Subquery) and union_curr.this:
            union_curr = union_curr.this
        if not isinstance(union_curr, exp.Select):
            raise ValueError(f"Unsupported union branch structure for timeout hint: {type(union_curr).__name__}")
        hint_target = union_curr

    timeout_expr = exp.Anonymous(
        this="MAX_EXECUTION_TIME",
        expressions=[exp.Literal.number(timeout_ms)]
    )

    existing_hint = hint_target.args.get("hint")
    if existing_hint:
        # Filter out existing MAX_EXECUTION_TIME expressions to prevent duplicates or conflicts
        new_exprs = [
            h for h in existing_hint.expressions
            if getattr(h, "name", "").upper() != "MAX_EXECUTION_TIME"
            and str(getattr(h, "this", "")).upper() != "MAX_EXECUTION_TIME"
        ]
        new_exprs.append(timeout_expr)
        existing_hint.set("expressions", new_exprs)
    else:
        hint_target.set("hint", exp.Hint(expressions=[timeout_expr]))

    # -------------------------------------------------------------
    # 2. Programmatic Root Row Limit (max_rows + 1)
    # -------------------------------------------------------------
    cap = max_rows + 1
    existing_limit = target_node.args.get("limit")

    if existing_limit is None:
        target_node.set("limit", exp.Limit(expression=exp.Literal.number(cap)))
    else:
        lim_expr = existing_limit.expression
        if not isinstance(lim_expr, exp.Literal) or not lim_expr.is_number:
            raise ValueError(f"Unsupported or ambiguous LIMIT expression: {lim_expr}")
        try:
            current_val = int(lim_expr.this)
        except (ValueError, TypeError):
            raise ValueError(f"Cannot parse integer value from LIMIT expression: {lim_expr}")

        if current_val < 0:
            raise ValueError(f"Negative LIMIT value is not permitted: {current_val}")

        # Reduce excessive limit to cap, otherwise preserve stricter user limit
        if current_val > max_rows:
            existing_limit.set("expression", exp.Literal.number(cap))

    return root.sql(dialect="mysql")


@dataclass
class DisposalResult:
    """
    Outcome of a connection invalidation / disposal attempt.
    """
    success: bool
    method: str  # 'invalidate', 'detach', or 'failed'
    invalidation_error: Optional[Exception] = None
    detachment_error: Optional[Exception] = None
    fail_closed_error: Optional[Exception] = None

    @property
    def is_double_failure(self) -> bool:
        return self.invalidation_error is not None and self.detachment_error is not None


def _safe_invalidate(connection: Any, exc: Optional[BaseException] = None) -> DisposalResult:
    """
    Safely invalidates a connection to prevent returning an unhealthy
    underlying DBAPI connection to the SQLAlchemy pool.

    Tries in sequence:
    1. connection.invalidate(exc): primary SQLAlchemy invalidation method.
    2. connection.detach(): if invalidate() raises, attempts detach() to uncouple
       the physical DBAPI connection from the pool record.
    3. Fail-closed physical termination: if both invalidate() and detach() raise,
       forcibly closes the underlying raw DBAPI connection and severs the pool record,
       ensuring that when connection.close() runs, the connection cannot be returned to the pool.

    Returns a DisposalResult capturing success status, method used, and any errors encountered.
    NEVER allows an exception to escape and abort cleanup control flow.
    """
    inv_err: Optional[Exception] = None
    try:
        connection.invalidate(exc)
        return DisposalResult(success=True, method="invalidate")
    except Exception as ie:
        inv_err = ie

    # Invalidation failed; attempt detachment fallback
    det_err: Optional[Exception] = None
    try:
        connection.detach()
        return DisposalResult(success=True, method="detach", invalidation_error=inv_err)
    except Exception as de:
        det_err = de

    # Double failure: both invalidate() and detach() raised.
    # Execute fail-closed physical termination on the underlying DBAPI connection
    fail_closed_err: Optional[Exception] = None
    try:
        fairy = getattr(connection, "connection", None) or getattr(connection, "_dbapi_connection", None)
        if fairy is not None:
            # 1. Sever the pool record so checkin cannot return this DBAPI connection to the pool
            rec = getattr(fairy, "_connection_record", None)
            pool = getattr(fairy, "_pool", None)
            if rec is not None:
                rec.fairy_ref = None
                rec.dbapi_connection = None
                if pool is not None and hasattr(pool, "_do_return_conn"):
                    try:
                        pool._do_return_conn(rec)
                    except Exception:
                        pass
                try:
                    fairy._connection_record = None
                except Exception:
                    pass

            # 2. Physically close the raw DBAPI connection socket
            raw_dbapi = (
                getattr(fairy, "dbapi_connection", None)
                or getattr(fairy, "driver_connection", None)
                or fairy
            )
            if hasattr(raw_dbapi, "close"):
                try:
                    raw_dbapi.close()
                except Exception:
                    pass
    except Exception as fce:
        fail_closed_err = fce

    return DisposalResult(
        success=False,
        method="failed",
        invalidation_error=inv_err,
        detachment_error=det_err,
        fail_closed_error=fail_closed_err,
    )


def execute_sql(
    sql_query: str,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    max_rows: int = DEFAULT_MAX_ROWS,
    max_result_bytes: int = DEFAULT_MAX_RESULT_BYTES,
    max_cell_bytes: int = DEFAULT_MAX_CELL_BYTES,
) -> ExecutionResult:
    """
    Executes a validated read-only SQL query with comprehensive safeguards:
    1. AST-based physical query bounding (max_rows + 1).
    2. Programmatic MySQL MAX_EXECUTION_TIME optimizer hint.
    3. Database-level read-only transaction lifecycle (START TRANSACTION READ ONLY).
    4. Result byte budgeting: limits total serialized bytes and individual cell sizes.
    5. Safe result fetching with truncation reporting and metadata.
    6. Deterministic cleanup: closes cursor and explicitly rolls back transaction.
    7. Fail-closed connection invalidation and detachment disposal.
    8. Naturally propagates primary query/fetch exceptions with original tracebacks.

    Returns:
        ExecutionResult: Subclasses tuple (records, is_truncated) for full backward
        compatibility with additive attributes: records, is_truncated, truncation_reason,
        returned_rows, result_size_bytes.
    """
    bounded_sql = prepare_bounded_query(sql_query, timeout_ms=timeout_ms, max_rows=max_rows)

    try:
        with engine.connect() as connection:
            with connection.begin() as trans:
                connection.execute(text("START TRANSACTION READ ONLY"))
                result = None
                primary_exc = None
                try:
                    result = connection.execute(text(bounded_sql))
                    columns = list(result.keys())
                    fetch_limit = max_rows + 1
                    rows = result.fetchmany(fetch_limit)

                    is_row_limit_hit = len(rows) > max_rows
                    accumulated_records: List[Dict[str, Any]] = []
                    total_bytes: int = 2  # for [] container
                    is_byte_budget_hit: bool = False

                    candidate_rows = rows[:max_rows]
                    for row in candidate_rows:
                        row_dict: Dict[str, Any] = {}
                        row_bytes: int = 2  # for {}
                        for col, val in zip(columns, row):
                            safe_val, val_bytes = _process_cell(val, col, max_cell_bytes)
                            row_dict[col] = safe_val
                            col_key_bytes = len(col.encode("utf-8")) + 4
                            row_bytes += col_key_bytes + val_bytes + 1

                        if total_bytes + row_bytes > max_result_bytes:
                            is_byte_budget_hit = True
                            break

                        accumulated_records.append(row_dict)
                        total_bytes += row_bytes

                    is_truncated = is_row_limit_hit or is_byte_budget_hit
                    truncation_reason: Optional[str] = None
                    if is_byte_budget_hit:
                        truncation_reason = "byte_budget"
                    elif is_row_limit_hit:
                        truncation_reason = "row_limit"

                    total_rows: Optional[int] = len(accumulated_records) if not is_truncated else None

                    return ExecutionResult(
                        records=accumulated_records,
                        is_truncated=is_truncated,
                        truncation_reason=truncation_reason,
                        returned_rows=len(accumulated_records),
                        result_size_bytes=total_bytes,
                        total_rows=total_rows,
                    )
                except Exception as e:
                    primary_exc = e
                    raise
                finally:
                    close_exc = None
                    close_disp_result: Optional[DisposalResult] = None
                    if result is not None:
                        try:
                            result.close()
                        except Exception as ce:
                            close_exc = ce
                            close_disp_result = _safe_invalidate(connection, ce)

                    rollback_exc = None
                    rollback_disp_result: Optional[DisposalResult] = None
                    try:
                        trans.rollback()
                    except Exception as re:
                        rollback_exc = re
                        rollback_disp_result = _safe_invalidate(connection, re)

                    # Exception precedence:
                    # 1. If primary query/fetch/processing failed, do not raise any cleanup exception;
                    #    the active primary exception naturally propagates with its pristine traceback.
                    if primary_exc is None:
                        # 2. If query succeeded but cleanup encountered failures, surface the root cleanup failure
                        if close_exc is not None:
                            if close_disp_result is not None:
                                if close_disp_result.is_double_failure:
                                    if close_disp_result.invalidation_error is not None:
                                        close_disp_result.invalidation_error.__context__ = close_disp_result.detachment_error
                                        close_exc.__context__ = close_disp_result.invalidation_error
                                elif close_disp_result.invalidation_error is not None:
                                    close_exc.__context__ = close_disp_result.invalidation_error
                            raise close_exc

                        if rollback_exc is not None:
                            if rollback_disp_result is not None:
                                if rollback_disp_result.is_double_failure:
                                    if rollback_disp_result.invalidation_error is not None:
                                        rollback_disp_result.invalidation_error.__context__ = rollback_disp_result.detachment_error
                                        rollback_exc.__context__ = rollback_disp_result.invalidation_error
                                elif rollback_disp_result.invalidation_error is not None:
                                    rollback_exc.__context__ = rollback_disp_result.invalidation_error
                            raise rollback_exc
    except SQLAlchemyError as e:
        raise Exception(f"MySQL Execution Error:\n{str(e)}") from e
