"""
PromptSQL — SQLGlot AST-Based Read-Query Validation Engine

Replaces legacy regex-based validation with comprehensive AST parsing using the MySQL dialect.
Enforces:
1. Exactly one syntactically valid SQL statement.
2. Only permitted read-only query structures (SELECT and UNION).
3. Rejection of all DDL, DML, administrative commands, stored procedure calls, and transaction operations.
4. Scope-aware tenant table authorization (rejecting system tables, other tenant tables, and schema qualification).
5. Scope-aware column resolution against live table schemas, CTE outputs, derived tables, and aliases.
6. Explicit denylist of prohibited security and information-disclosure functions and constructs.
"""

import re
from typing import Collection, Dict, Optional, Set, Tuple
from sqlalchemy import inspect
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope, Scope

from app.database.connection import engine
from app.services.dataset_guard import is_system_table, PROTECTED_SYSTEM_TABLES, PROTECTED_SCHEMA_PREFIXES


# Prohibited functions that cause side effects, information disclosure, or DoS
PROHIBITED_FUNCTION_NAMES: Set[str] = frozenset({
    "SLEEP",
    "BENCHMARK",
    "LOAD_FILE",
    "GET_LOCK",
    "RELEASE_LOCK",
    "IS_FREE_LOCK",
    "IS_USED_LOCK",
    "USER",
    "CURRENT_USER",
    "SESSION_USER",
    "SYSTEM_USER",
    "VERSION",
    "DATABASE",
    "SCHEMA",
})

# Prohibited AST classes (system parameters, user variables, administrative constructs)
PROHIBITED_AST_CLASSES: Tuple[type, ...] = (
    exp.CurrentUser,
    exp.SessionUser,
    exp.CurrentVersion,
    exp.CurrentSchema,
    exp.CurrentDatabase,
    exp.CurrentCatalog,
    exp.SessionParameter,
    exp.Parameter,
    exp.Into,
)

# Disallowed statement and operation AST types anywhere in query
DISALLOWED_STATEMENT_CLASSES: Tuple[type, ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.TruncateTable,
    exp.Command,
    exp.Set,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Grant,
    exp.Revoke,
    exp.Use,
    exp.Show,
    exp.Kill,
    exp.Pragma,
    exp.Describe,
)

# Regex check for dangerous INTO constructs as secondary defense
INTO_DANGEROUS_REGEX = re.compile(r"\bINTO\s+(?:OUTFILE|DUMPFILE)\b", re.IGNORECASE)


def _get_scope_exported_columns(scope: Scope, schemas: Dict[str, Set[str]]) -> Set[str]:
    """
    Computes the set of lowercase column names exported by a CTE, derived table, or subquery scope.
    """
    expr = scope.expression
    if not hasattr(expr, "selects"):
        return set()

    exported: Set[str] = set()
    for item in expr.selects:
        if isinstance(item, exp.Star):
            # Star expands to all columns of all sources in this subscope
            for src_name, src_node in scope.sources.items():
                if isinstance(src_node, exp.Table):
                    tname = src_node.name.lower()
                    if tname in schemas:
                        exported.update(schemas[tname])
                elif isinstance(src_node, Scope):
                    exported.update(_get_scope_exported_columns(src_node, schemas))
        elif isinstance(item, exp.Column) and isinstance(item.this, exp.Star):
            # Table-qualified star: e.g. a.*
            src_name = item.table.lower() if item.table else ""
            src_node = scope.sources.get(src_name)
            if isinstance(src_node, exp.Table):
                tname = src_node.name.lower()
                if tname in schemas:
                    exported.update(schemas[tname])
            elif isinstance(src_node, Scope):
                exported.update(_get_scope_exported_columns(src_node, schemas))
        else:
            exported.add(item.alias_or_name.lower())

    return exported


def validate_sql(
    sql_query: str,
    user_tables: Collection[str],
    table_schemas: Optional[Dict[str, Collection[str]]] = None
) -> Tuple[bool, str]:
    """
    Validates a read query using SQLGlot MySQL AST parsing.
    Strictly verifies:
    1. Exactly one valid SQL statement.
    2. Only read-only SELECT or UNION query root.
    3. No disallowed statement types anywhere in AST.
    4. Prohibited functions and constructs are rejected.
    5. All referenced physical tables belong to the authorized user_tables list.
    6. No schema qualification or system tables accessed.
    7. All referenced columns exist in the actual schemas of referenced tables,
       properly resolving CTEs, subqueries, aliases, joins, and parent scopes.
    8. Ambiguous unqualified columns across joins are rejected.

    Never leaks table existence or schemas of other tenants in error messages.
    """
    if not sql_query or not isinstance(sql_query, str) or not sql_query.strip():
        return False, "SQL statement cannot be empty."

    sql_clean = sql_query.strip()

    # Pre-parse defense against dangerous INTO OUTFILE / DUMPFILE constructs
    if INTO_DANGEROUS_REGEX.search(sql_clean):
        return False, "Unsupported SQL construct: SELECT INTO is not permitted."

    # 1. AST Parsing with MySQL dialect
    try:
        parsed_statements = sqlglot.parse(sql_clean, read="mysql")
    except Exception:
        return False, "Malformed SQL syntax or parser error."

    # Filter out empty statements (e.g. from extraneous semicolons)
    non_empty_statements = [s for s in parsed_statements if s is not None]
    if not non_empty_statements:
        return False, "No valid SQL statement detected."

    if len(parsed_statements) != 1 or len(non_empty_statements) != 1:
        return False, "Multiple or chained SQL statements are not permitted."

    stmt = non_empty_statements[0]

    # Root statement must be Select or Union
    if not isinstance(stmt, (exp.Select, exp.Union)):
        return False, "Only read-only SELECT queries are permitted."

    # 2. Comprehensive AST node inspection
    for node in stmt.walk():
        # Disallowed statement types anywhere in the tree
        if isinstance(node, DISALLOWED_STATEMENT_CLASSES):
            return False, f"Disallowed statement type '{type(node).__name__}' is not permitted."

        # Prohibited parameter and variable constructs
        if isinstance(node, (exp.Parameter, exp.SessionParameter)):
            return False, "User and system variables are not permitted."

        # Prohibited AST classes
        if isinstance(node, PROHIBITED_AST_CLASSES):
            return False, f"Prohibited SQL construct '{type(node).__name__}' is not permitted."

        # Prohibited functions (Anonymous and explicit AST functions)
        if isinstance(node, exp.Anonymous):
            func_name = str(node.this).upper()
            if func_name in PROHIBITED_FUNCTION_NAMES:
                return False, f"Prohibited SQL function '{func_name}' is not permitted."
        elif isinstance(node, exp.Func):
            func_name = getattr(node, "sql_name", lambda: "")().upper()
            node_type_name = type(node).__name__.upper()
            if func_name in PROHIBITED_FUNCTION_NAMES or node_type_name in PROHIBITED_FUNCTION_NAMES:
                return False, f"Prohibited SQL function '{func_name or node_type_name}' is not permitted."

    # 3. Scope Traversal & Table Resolution
    user_tables_set: Set[str] = {t.lower() for t in user_tables}
    try:
        scopes = list(traverse_scope(stmt))
    except Exception:
        return False, "Failed to analyze SQL scopes."

    if not scopes:
        return False, "No valid query scope found."

    # Collect physical tables referenced across all scopes
    referenced_physical_tables: Set[str] = set()
    for scope in scopes:
        for table in scope.tables:
            # Reject schema qualification / cross-database queries
            if table.db:
                return False, "Schema-qualified and cross-database table references are not permitted."

            t_name = table.name.lower()
            source = scope.sources.get(table.name) or scope.sources.get(t_name)

            # If source is a Scope, it is a CTE or derived table
            if isinstance(source, Scope):
                continue

            # Protect application system tables
            if is_system_table(t_name):
                return False, "Access denied. One or more referenced tables are unauthorized."

            # Verify table ownership
            if t_name not in user_tables_set:
                return False, "Access denied. One or more referenced tables are unauthorized."

            referenced_physical_tables.add(t_name)

        # Also guard CTE and derived table aliases from spoofing system table names
        for alias_name, src in scope.sources.items():
            if is_system_table(alias_name):
                return False, "Access denied. One or more referenced tables are unauthorized."

    # 4. Column Schema Preparation
    resolved_schemas: Dict[str, Set[str]] = {}
    if table_schemas is not None:
        resolved_schemas = {tbl.lower(): {c.lower() for c in cols} for tbl, cols in table_schemas.items()}
    else:
        # Load schemas from database for referenced physical tables
        try:
            inspector = inspect(engine)
            for t_name in referenced_physical_tables:
                if t_name in user_tables_set and t_name not in resolved_schemas:
                    try:
                        resolved_schemas[t_name] = {
                            col["name"].lower() for col in inspector.get_columns(t_name)
                        }
                    except Exception:
                        resolved_schemas[t_name] = set()
        except Exception:
            return False, "Database schema inspection failed."

    # Pre-compute exported columns for CTEs, derived tables, and subqueries
    scope_exported_cols: Dict[int, Set[str]] = {}
    for scope in scopes:
        if scope.is_cte or scope.is_derived_table or scope.is_subquery:
            scope_exported_cols[id(scope)] = _get_scope_exported_columns(scope, resolved_schemas)

    # 5. Scope-Aware Column Validation
    for scope in scopes:
        scope._ensure_collected()

        # Build source columns map for THIS scope using selected_sources
        source_cols: Dict[str, Set[str]] = {}
        for alias_or_name, src_entry in scope.selected_sources.items():
            key = alias_or_name.lower()
            src = src_entry[1] if isinstance(src_entry, tuple) else src_entry
            if isinstance(src, exp.Table):
                p_name = src.name.lower()
                source_cols[key] = resolved_schemas.get(p_name, set())
            elif isinstance(src, Scope):
                source_cols[key] = scope_exported_cols.get(id(src), set())

        # If this is a UNION scope, make union output columns available
        if isinstance(scope.expression, exp.Union):
            union_cols = {col.lower() for col in scope.expression.named_selects}
            source_cols["__union__"] = union_cols

        # Select aliases in this scope (valid in ORDER BY and HAVING)
        select_aliases: Set[str] = set()
        if hasattr(scope.expression, "selects"):
            for sel in scope.expression.selects:
                if sel.alias:
                    select_aliases.add(sel.alias.lower())

        # Check qualified star expressions (e.g. `a.*`)
        for star in scope._stars:
            if isinstance(star, exp.Column) and star.table:
                tbl_key = star.table.lower()
                if tbl_key not in source_cols:
                    # Check parent scopes (correlated reference)
                    curr = scope.parent
                    found_parent = False
                    while curr:
                        curr._ensure_collected()
                        if tbl_key in curr.selected_sources or tbl_key in curr.sources:
                            found_parent = True
                            break
                        curr = curr.parent
                    if not found_parent:
                        return False, f"Unknown table alias or source '{star.table}'."

        # Validate all columns belonging to this scope
        for col in scope._raw_columns:
            col_name = col.name.lower()
            table_prefix = col.table.lower() if col.table else None

            if table_prefix:
                # Qualified column: e.g. a.amount or sales_usr_1.amount
                if table_prefix in source_cols:
                    if col_name not in source_cols[table_prefix]:
                        return False, f"Unknown column '{col.name}' in table or source '{col.table}'."
                else:
                    # Check parent scopes for correlated references
                    curr = scope.parent
                    found_parent = False
                    while curr:
                        curr._ensure_collected()
                        parent_src = curr.sources.get(table_prefix)
                        if parent_src:
                            p_cols: Set[str] = set()
                            if isinstance(parent_src, exp.Table):
                                p_cols = resolved_schemas.get(parent_src.name.lower(), set())
                            elif isinstance(parent_src, Scope):
                                p_cols = scope_exported_cols.get(id(parent_src), set())
                            if col_name not in p_cols:
                                return False, f"Unknown column '{col.name}' in table or source '{col.table}'."
                            found_parent = True
                            break
                        curr = curr.parent

                    if not found_parent:
                        return False, f"Unknown table alias or source '{col.table}'."
            else:
                # Unqualified column: e.g. amount or id
                # 1. Check if column matches a SELECT alias in ORDER BY, HAVING, or GROUP BY
                if (col.find_ancestor(exp.Order, exp.Having, exp.Group)) and col_name in select_aliases:
                    continue

                # 2. Check sources in current scope
                matching_sources = [src_name for src_name, cols in source_cols.items() if col_name in cols]
                if len(matching_sources) > 1:
                    return False, f"Ambiguous column '{col.name}' across joined sources ({', '.join(sorted(matching_sources))})."
                elif len(matching_sources) == 1:
                    continue

                # 3. Check parent scopes (correlated reference)
                curr = scope.parent
                found_parent = False
                while curr:
                    curr._ensure_collected()
                    parent_matches = []
                    for src_name, src_node in curr.selected_sources.items():
                        cols: Set[str] = set()
                        src = src_node[1] if isinstance(src_node, tuple) else src_node
                        if isinstance(src, exp.Table):
                            cols = resolved_schemas.get(src.name.lower(), set())
                        elif isinstance(src, Scope):
                            cols = scope_exported_cols.get(id(src), set())
                        if col_name in cols:
                            parent_matches.append(src_name)
                    if len(parent_matches) > 1:
                        return False, f"Ambiguous column '{col.name}' across parent sources."
                    elif len(parent_matches) == 1:
                        found_parent = True
                        break
                    curr = curr.parent

                if not found_parent:
                    return False, f"Unknown column '{col.name}'."

    return True, "SQL is valid."
