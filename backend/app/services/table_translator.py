"""
PromptSQL — SQLGlot AST-Based Table Name Translation Service

Translates human-readable friendly table names (e.g. `sales`, `customers`)
into user-scoped, authorized physical database table names (e.g. `sales_usr_test15`)
using SQLGlot AST scope-aware traversal (MySQL dialect).

Enforces:
1. Single syntactically valid read-only MySQL statement (SELECT / UNION).
2. Authoritative resolution against verified physical tables owned by the authenticated user.
3. Rejection of schema qualification, system tables, and cross-tenant tables.
4. Scope-aware separation of physical tables from CTEs and derived tables.
5. Preservation of existing aliases, columns, literals, and comments.
6. Automatic preservation of friendly qualifiers via aliases for un-aliased tables.
7. Fail-closed rejection of unknown, ambiguous, or colliding identifiers.
"""

from typing import Collection, Dict, List, Optional, Set, Tuple
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope, Scope

from app.services.dataset_guard import is_system_table


# =====================================================================
# Translation Exceptions
# =====================================================================

class TableTranslationError(Exception):
    """Base exception for all table translation errors."""
    pass


class MalformedSQLError(TableTranslationError):
    """Raised when the input SQL cannot be parsed as valid MySQL SQL."""
    pass


class MultipleStatementsError(TableTranslationError):
    """Raised when multiple SQL statements are detected."""
    pass


class AmbiguousTableMappingError(TableTranslationError):
    """Raised when a friendly table name ambiguously maps to multiple physical tables."""
    pass


class TranslationSecurityError(TableTranslationError):
    """Raised when a query attempts schema qualification or system table access."""
    pass


class TranslationTableNotFoundError(TableTranslationError):
    """Raised when a table reference cannot be resolved to any authorized physical table."""
    pass


class AliasCollisionError(TableTranslationError):
    """Raised when an explicit alias collides with another source in the same scope."""
    pass


# =====================================================================
# Authoritative Mapping Builder
# =====================================================================

def build_friendly_to_physical_map(
    authorized_tables: Collection[str],
    user_id: Optional[str] = None
) -> Tuple[Dict[str, str], Set[str]]:
    """
    Builds an authoritative friendly_name -> physical_name mapping from the user's
    authorized physical tables.
    Detects and rejects ambiguous collisions (fail closed).

    Returns:
        Tuple of (friendly_to_physical_dict, authorized_physical_set).
        Both dictionaries/sets use lowercase keys for case-insensitive matching.
    """
    friendly_to_physical: Dict[str, str] = {}
    authorized_physical_set: Set[str] = set()

    user_id_str = str(user_id).strip() if user_id is not None else None
    canonical_suffix: Optional[str] = None
    if user_id_str:
        uid_clean = user_id_str.lower()
        # Normalize both '123' and 'usr_123' into canonical form 'usr_<id>'
        canonical_uid = uid_clean if uid_clean.startswith("usr_") else f"usr_{uid_clean}"
        canonical_suffix = f"_{canonical_uid}"

    for phys in authorized_tables:
        if not phys or not isinstance(phys, str):
            continue
        phys_clean = phys.strip().strip("`")
        if not phys_clean:
            continue

        phys_lower = phys_clean.lower()
        authorized_physical_set.add(phys_lower)

        # Derive friendly name based on PromptSQL naming rules
        if canonical_suffix and phys_lower.endswith(canonical_suffix):
            friendly = phys_clean[:-len(canonical_suffix)]
        elif user_id_str and "_usr_" in phys_lower:
            # Foreign tenant table with an unauthorized user suffix
            raise TranslationSecurityError(
                f"Access denied. Table '{phys_clean}' does not belong to authenticated user '{user_id}'."
            )
        elif "_usr_" in phys_lower:
            # Fallback only when unauthenticated: strip at rightmost _usr_
            friendly = phys_clean[:phys_lower.rfind("_usr_")]
        else:
            friendly = phys_clean

        if not friendly:
            friendly = phys_clean

        norm = friendly.lower()
        if norm in friendly_to_physical and friendly_to_physical[norm] != phys_clean:
            raise AmbiguousTableMappingError(
                f"Ambiguous table mapping: friendly name '{friendly}' resolves to multiple physical tables: "
                f"'{friendly_to_physical[norm]}' and '{phys_clean}'."
            )
        friendly_to_physical[norm] = phys_clean

    return friendly_to_physical, authorized_physical_set


# =====================================================================
# AST Translation Function
# =====================================================================

def translate_query_tables(
    sql_query: str,
    authorized_tables: Collection[str],
    user_id: Optional[str] = None
) -> str:
    """
    Translates friendly table references into physical user tables via SQLGlot AST.

    Args:
        sql_query: The friendly SQL query generated by the LLM.
        authorized_tables: Collection of authorized physical tables owned by the user.
        user_id: Optional authenticated user identifier.

    Returns:
        The translated physical SQL query string, ready for validation and execution.

    Raises:
        MalformedSQLError: If SQL is invalid or not read-only.
        MultipleStatementsError: If multiple statements are provided.
        AmbiguousTableMappingError: If multiple physical tables map to the same friendly name.
        TranslationSecurityError: If schema qualification or system table access is attempted.
        TranslationTableNotFoundError: If an unknown or unauthorized table is referenced.
        AliasCollisionError: If colliding aliases are detected in a scope.
    """
    if not sql_query or not isinstance(sql_query, str) or not sql_query.strip():
        raise MalformedSQLError("SQL query cannot be empty.")

    # 1. Parse statement with SQLGlot MySQL dialect
    try:
        parsed_statements = sqlglot.parse(sql_query, read="mysql")
    except Exception as e:
        raise MalformedSQLError(f"Failed to parse SQL query: {str(e)}") from e

    non_empty = [s for s in parsed_statements if s is not None]
    if len(non_empty) == 0:
        raise MalformedSQLError("No valid SQL statement detected.")
    if len(non_empty) > 1:
        raise MultipleStatementsError("Multiple SQL statements are not permitted.")

    stmt = non_empty[0]

    # Unwrap any outer parenthesized subquery layers (e.g. `(SELECT ...)`)
    root_expr = stmt
    while isinstance(root_expr, exp.Subquery) and root_expr.this:
        root_expr = root_expr.this

    if not isinstance(root_expr, (exp.Select, exp.Union)):
        raise MalformedSQLError("Only read-only SELECT queries are permitted.")

    # 2. Build authoritative mapping
    friendly_to_physical, authorized_physical_set = build_friendly_to_physical_map(
        authorized_tables=authorized_tables,
        user_id=user_id
    )

    # 3. Scope Traversal
    try:
        scopes = list(traverse_scope(stmt))
    except Exception as e:
        raise MalformedSQLError(f"Failed to analyze SQL scopes: {str(e)}") from e

    if not scopes:
        raise MalformedSQLError("No valid query scope found.")

    for scope in scopes:
        # Check for explicit alias collisions within this scope
        scope_aliases: Set[str] = set()
        for t in scope.tables:
            if t.alias:
                alias_lower = t.alias.lower()
                if alias_lower in scope_aliases:
                    raise AliasCollisionError(f"Duplicate table alias '{t.alias}' detected in query scope.")
                scope_aliases.add(alias_lower)

        for table in scope.tables:
            # Check schema qualification (e.g. `mydb.sales` or `information_schema.tables`)
            if table.db:
                raise TranslationSecurityError(
                    f"Schema-qualified and cross-database table references are not permitted: '{table.sql('mysql')}'"
                )

            # Check if this table reference resolves to a CTE or derived table
            source = scope.sources.get(table.name) or scope.sources.get(table.name.lower())
            if isinstance(source, Scope):
                # CTE or derived table reference — do not translate
                continue

            raw_name = table.name
            norm_name = raw_name.lower()

            if is_system_table(norm_name):
                raise TranslationSecurityError(
                    f"Access denied. Table '{raw_name}' is a protected system table."
                )

            if norm_name in friendly_to_physical:
                phys_name = friendly_to_physical[norm_name]
                # If table does not already have an explicit alias, add the friendly name as alias
                # so that table-qualified columns (e.g. `sales.id`) resolve natively in MySQL.
                if not table.alias:
                    if norm_name in scope_aliases:
                        raise AliasCollisionError(
                            f"Cannot automatically alias table '{raw_name}': alias '{raw_name}' is already defined in query scope."
                        )
                    table.set("alias", exp.to_identifier(raw_name, quoted=True))
                    scope_aliases.add(norm_name)
                table.set("this", exp.to_identifier(phys_name, quoted=True))
            elif norm_name in authorized_physical_set:
                # Table already refers to an authorized physical table directly
                table.set("this", exp.to_identifier(raw_name, quoted=True))
            else:
                raise TranslationTableNotFoundError(
                    f"Access denied. Unknown or unauthorized table reference '{raw_name}'."
                )

        # Guard CTE and derived table aliases from spoofing system tables
        for alias_name, src in scope.sources.items():
            if is_system_table(alias_name):
                raise TranslationSecurityError(
                    f"Access denied. Alias '{alias_name}' cannot spoof a protected system table."
                )

    return stmt.sql("mysql")
