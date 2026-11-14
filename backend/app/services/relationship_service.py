"""
PromptSQL — Dynamic Schema Discovery and Automatic Relationship Inference Engine

This service automatically discovers authorized database schemas, infers relationships
between tables, builds a relationship graph, and identifies the optimal join paths
for multi-table natural-language questions without requiring users to specify table names,
join conditions, or relationship keys.

Zero Hardcoding Guarantee:
- All schema information is retrieved dynamically from the database.
- Relationship inference uses structural heuristics (PK-FK naming patterns, type compatibility,
  explicit foreign keys, and value overlap) with strict false-positive suppression.
- Graph search (BFS / minimum connecting tree) discovers multi-hop join paths dynamically.
"""

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.database.connection import engine
from app.services.dataset_guard import is_system_table


# Generic surrogate primary key column names that should NEVER be joined across tables
# without explicit FK naming (e.g. table_a.id = table_b.id is almost always a FALSE relationship).
GENERIC_ID_NAMES: Set[str] = frozenset({
    "id",
    "_row_id",
    "row_id",
    "pk",
    "key",
    "code",
    "no",
    "num",
    "number"
})

# Common non-relational attribute column names that must never be treated as foreign keys
NON_RELATIONAL_ATTRIBUTES: Set[str] = frozenset({
    "name", "first_name", "last_name", "full_name", "title", "subject",
    "status", "state", "type", "kind", "category", "flag", "active", "is_active",
    "enabled", "is_enabled", "deleted", "is_deleted", "archived",
    "date", "created_at", "updated_at", "timestamp", "datetime", "time",
    "description", "desc", "notes", "comment", "comments", "text", "message",
    "amount", "price", "cost", "total", "subtotal", "tax", "discount", "balance",
    "quantity", "qty", "count", "score", "rating", "percentage", "rate", "weight",
    "city", "country", "postal_code", "zip", "zipcode", "address", "street",
    "phone", "mobile", "email", "url", "image", "photo", "avatar", "icon",
    "gender", "age", "year", "month", "day", "hour", "minute"
})


@dataclass
class ColumnMeta:
    name: str
    data_type: str
    generic_type: str
    is_primary_key: bool = False
    nullable: bool = True


@dataclass
class TableMeta:
    physical_name: str
    friendly_name: str
    columns: List[ColumnMeta]
    column_map: Dict[str, ColumnMeta]
    pk_columns: List[str]
    foreign_keys: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class InferredRelationship:
    source_table: str       # Child / referencing table friendly name (e.g. "orders")
    source_physical: str    # Child physical table name
    source_column: str      # Child FK column (e.g. "customer_id")
    target_table: str       # Parent / referenced table friendly name (e.g. "customers")
    target_physical: str    # Parent physical table name
    target_column: str      # Parent PK column (e.g. "id")
    confidence: float       # Confidence score (0.0 to 1.0)
    cardinality: str        # "N:1", "1:1", "1:N", "N:M"
    reason: str             # Description of why relationship was inferred
    is_ambiguous: bool = False
    disambiguation_hint: Optional[str] = None

    @property
    def join_condition(self) -> str:
        return f"`{self.source_table}`.`{self.source_column}` = `{self.target_table}`.`{self.target_column}`"

    @property
    def physical_join_condition(self) -> str:
        return f"`{self.source_physical}`.`{self.source_column}` = `{self.target_physical}`.`{self.target_column}`"


@dataclass
class QueryContext:
    physical_tables: List[str]
    friendly_tables: List[str]
    active_table_friendly: str
    schemas_prompt: str
    relationships: List[InferredRelationship]
    relationships_prompt: str
    is_multi_table: bool
    ambiguity_warning: Optional[str] = None
    needs_clarification: bool = False
    clarification_prompt: Optional[str] = None
    clarification_options: List[str] = field(default_factory=list)
    ambiguous_relationships: List[InferredRelationship] = field(default_factory=list)
    clarification_context_data: Optional[Dict[str, Any]] = None


# -----------------------------------------------------------------------------
# Helper Functions: Type Normalization & Linguistic Variants
# -----------------------------------------------------------------------------

def normalize_type_category(raw_type_str: str) -> str:
    """Classifies SQL data types into broad categories for type compatibility checking."""
    t = raw_type_str.lower().strip()
    if any(k in t for k in ["int", "bigint", "smallint", "tinyint", "mediumint"]):
        return "INTEGER"
    if any(k in t for k in ["decimal", "numeric", "float", "double", "real"]):
        return "NUMERIC"
    if any(k in t for k in ["varchar", "char", "text", "string"]):
        return "STRING"
    if any(k in t for k in ["date", "time", "timestamp"]):
        return "DATETIME"
    if any(k in t for k in ["bool", "boolean"]):
        return "BOOLEAN"
    return "OTHER"


def are_types_join_compatible(cat1: str, cat2: str) -> bool:
    """Verifies that two columns possess compatible types for joining."""
    if cat1 == cat2:
        return True
    if (cat1 == "INTEGER" and cat2 == "NUMERIC") or (cat1 == "NUMERIC" and cat2 == "INTEGER"):
        return True
    return False


def clean_token(s: str) -> str:
    """Strips delimiters and converts to lowercase for normalized key and token matching."""
    return re.sub(r"[_\s\-]+", "", s.lower())


NON_ID_WORDS = ("valid", "paid", "grid", "solid", "liquid", "acid", "mid", "rapid", "pyramid", "hybrid", "lipid")


def is_identifier_column(col_name: str, is_primary_key: bool = False) -> bool:
    """Determines whether a column is a primary, foreign, or business entity identifier."""
    if is_primary_key:
        return True
    norm = clean_token(col_name)
    if norm in GENERIC_ID_NAMES:
        return True
    for suffix in ["id", "code", "key", "number", "num", "no", "ref"]:
        if norm.endswith(suffix):
            if suffix == "id" and any(norm.endswith(w) for w in NON_ID_WORDS):
                continue
            return True
    return False


def extract_semantic_tokens(text: str) -> Set[str]:
    """Extracts lowercase tokens, compound parts, and singular stems from text or identifier."""
    raw_tokens = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)|\d+", text)
    tokens = set()
    for t in raw_tokens:
        tl = t.lower()
        if len(tl) < 2:
            continue
        tokens.add(tl)
        if tl.endswith("ies") and len(tl) > 4:
            tokens.add(tl[:-3] + "y")
        elif any(tl.endswith(sfx) for sfx in ["sses", "shes", "ches", "xes", "zes"]) and len(tl) > 4:
            tokens.add(tl[:-2])
        elif tl.endswith("s") and len(tl) > 2 and not tl.endswith("ss"):
            tokens.add(tl[:-1])
    return tokens


def get_table_name_variants(friendly_name: str) -> Set[str]:
    """
    Derives linguistic variants (singular, stem, constituent entity tokens) of a table name dynamically
    without hardcoded word lists.
    Examples:
      'customers' -> {'customers', 'customer'}
      'test_customers' -> {'test_customers', 'test_customer', 'customers', 'customer', ...}
      'order_items' -> {'order_items', 'order_item', 'orderitems', 'orderitem', 'items', 'item'}
    """
    clean = friendly_name.lower().replace("-", "_").strip()
    variants = set()

    def add_singulars(word: str):
        if not word or len(word) < 2:
            return
        variants.add(word)
        if word.endswith("ies") and len(word) > 4:
            variants.add(word[:-3] + "y")    # categories -> category
        elif word.endswith("es") and len(word) > 3:
            variants.add(word[:-2])          # boxes -> box
            variants.add(word[:-1])          # horses -> horse
        elif word.endswith("s") and len(word) > 2 and not word.endswith("ss"):
            variants.add(word[:-1])          # customers -> customer

    add_singulars(clean)
    add_singulars(clean.replace("_", ""))

    # Token-based variants for prefixed or compound table names (e.g., test_customers, dim_customers)
    parts = [p for p in clean.split("_") if p]
    if len(parts) > 1:
        # Suffix combinations: e.g. for a_b_c -> 'b_c', 'c'
        for k in range(1, len(parts)):
            sub = "_".join(parts[k:])
            add_singulars(sub)
            add_singulars(sub.replace("_", ""))
        # Last individual token: e.g., 'customers' from 'test_customers'
        add_singulars(parts[-1])

    return variants


def extract_canonical_user_id(user_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Returns (canonical_user_id, canonical_suffix) e.g. ('usr_1', '_usr_1')."""
    if not user_id:
        return None, None
    clean = str(user_id).strip().lower()
    canonical_id = clean if clean.startswith("usr_") else f"usr_{clean}"
    return canonical_id, f"_{canonical_id}"


def derive_friendly_table_name(physical_name: str, canonical_suffix: Optional[str]) -> str:
    """Strips tenant suffix to obtain friendly table name."""
    if canonical_suffix and physical_name.lower().endswith(canonical_suffix.lower()):
        return physical_name[:-len(canonical_suffix)]
    if "_usr_" in physical_name:
        return physical_name.split("_usr_")[0]
    return physical_name


# -----------------------------------------------------------------------------
# 1. Dynamic Schema Discovery
# -----------------------------------------------------------------------------

def discover_user_schemas(user_id: str, db_engine: Engine = engine) -> Dict[str, TableMeta]:
    """
    Discovers all authorized physical tables owned by user_id and extracts
    their column metadata, data types, and primary/foreign keys.
    """
    canonical_id, canonical_suffix = extract_canonical_user_id(user_id)
    inspector = inspect(db_engine)
    all_tables = inspector.get_table_names()

    # Discover tables owned by user (matching canonical suffix or _usr_{user_id})
    user_physical_tables = []
    for t in all_tables:
        if is_system_table(t):
            continue
        t_lower = t.lower()
        if canonical_suffix and t_lower.endswith(canonical_suffix.lower()):
            user_physical_tables.append(t)
        elif canonical_id and f"_{canonical_id}" in t_lower:
            user_physical_tables.append(t)

    discovered: Dict[str, TableMeta] = {}

    for phys in user_physical_tables:
        friendly = derive_friendly_table_name(phys, canonical_suffix)
        raw_cols = inspector.get_columns(phys)
        pk_constraint = inspector.get_pk_constraint(phys) or {}
        pk_col_names = set(pk_constraint.get("constrained_columns", []))

        columns: List[ColumnMeta] = []
        column_map: Dict[str, ColumnMeta] = {}

        for c in raw_cols:
            c_name = c["name"]
            c_type_str = str(c["type"])
            c_generic = normalize_type_category(c_type_str)
            is_pk = (c_name in pk_col_names) or (c_name.lower() in ("id", "_row_id") and len(pk_col_names) == 0)

            meta = ColumnMeta(
                name=c_name,
                data_type=c_type_str,
                generic_type=c_generic,
                is_primary_key=is_pk,
                nullable=c.get("nullable", True)
            )
            columns.append(meta)
            column_map[c_name.lower()] = meta

        # Also inspect explicit foreign keys if supported
        fks = []
        try:
            fks = inspector.get_foreign_keys(phys) or []
        except Exception:
            fks = []

        table_meta = TableMeta(
            physical_name=phys,
            friendly_name=friendly,
            columns=columns,
            column_map=column_map,
            pk_columns=list(pk_col_names),
            foreign_keys=fks
        )
        discovered[friendly.lower()] = table_meta

    return discovered


# -----------------------------------------------------------------------------
# 2. Heuristic Relationship Inference Engine
# -----------------------------------------------------------------------------

def infer_table_relationships(
    schemas: Dict[str, TableMeta],
    db_engine: Optional[Engine] = None,
    verify_data_overlap: bool = True
) -> List[InferredRelationship]:
    """
    Infers relationships across all discovered user tables using:
    1. Explicit foreign key constraints.
    2. Primary Key <-> Foreign Key naming conventions.
    3. Type compatibility enforcement.
    4. False-positive suppression for generic column names.
    5. Value overlap verification (optional, lightweight bounded queries).
    """
    relationships: List[InferredRelationship] = []
    tables = list(schemas.values())

    # Pairwise comparison: Table B (child) referencing Table A (parent)
    for i, table_b in enumerate(tables):
        for j, table_a in enumerate(tables):
            if i == j:
                continue

            # 1. Check explicit foreign keys defined in database
            for fk in table_b.foreign_keys:
                ref_tbl = fk.get("referred_table", "")
                if ref_tbl.lower() in (table_a.physical_name.lower(), table_a.friendly_name.lower()):
                    c_cols = fk.get("constrained_columns", [])
                    r_cols = fk.get("referred_columns", [])
                    if c_cols and r_cols:
                        relationships.append(InferredRelationship(
                            source_table=table_b.friendly_name,
                            source_physical=table_b.physical_name,
                            source_column=c_cols[0],
                            target_table=table_a.friendly_name,
                            target_physical=table_a.physical_name,
                            target_column=r_cols[0],
                            confidence=1.0,
                            cardinality="N:1",
                            reason="Explicit Foreign Key Constraint"
                        ))

            # 2. Heuristic Key Pattern Matching:
            # Matches explicit entity identifiers, primary/foreign keys, and role-prefixed columns
            a_variants = get_table_name_variants(table_a.friendly_name)
            b_variants = get_table_name_variants(table_b.friendly_name)

            for col_a in table_a.columns:
                col_a_clean = clean_token(col_a.name)
                is_a_id = is_identifier_column(col_a.name, col_a.is_primary_key)

                for col_b in table_b.columns:
                    col_b_clean = clean_token(col_b.name)
                    is_b_id = is_identifier_column(col_b.name, col_b.is_primary_key)

                    # False-positive suppression:
                    # Generic columns matching across tables (e.g. A.id = B.id, A.status = B.status)
                    # must NEVER be inferred as foreign keys
                    if col_a_clean in GENERIC_ID_NAMES and col_b_clean in GENERIC_ID_NAMES:
                        continue
                    if col_b_clean in NON_RELATIONAL_ATTRIBUTES or col_a_clean in NON_RELATIONAL_ATTRIBUTES:
                        continue

                    # Type compatibility check
                    if not are_types_join_compatible(col_a.generic_type, col_b.generic_type):
                        continue

                    confidence = 0.0
                    reason = ""
                    disambiguation_hint = None
                    src_tbl, src_col, tgt_tbl, tgt_col = None, None, None, None

                    # Pattern 1: Identical / Equivalent Shared Identifier column
                    # e.g. customers.CustomerID <-> orders.CustomerID, or clients.client_id <-> orders.client_id
                    if col_a_clean == col_b_clean and (is_a_id or is_b_id):
                        a_matched = any(clean_token(v) in col_a_clean for v in a_variants)
                        b_matched = any(clean_token(v) in col_b_clean for v in b_variants)
                        confidence = 0.96 if (a_matched or b_matched or col_a.is_primary_key or col_b.is_primary_key) else 0.92
                        reason = f"Shared domain identifier `{col_a.name}` across `{table_a.friendly_name}` and `{table_b.friendly_name}`"
                        if col_b.is_primary_key:
                            src_tbl, src_col, tgt_tbl, tgt_col = table_a, col_a, table_b, col_b
                        else:
                            src_tbl, src_col, tgt_tbl, tgt_col = table_b, col_b, table_a, col_a

                    # Pattern 1b: Equivalent Identifier with prefix/stem match (e.g. customer_id <-> cust_id)
                    if confidence == 0.0 and (is_a_id and is_b_id):
                        for sfx in ["id", "code", "key", "number", "num", "no", "ref"]:
                            if col_a_clean.endswith(sfx) and col_b_clean.endswith(sfx):
                                stem_a = col_a_clean[:-len(sfx)]
                                stem_b = col_b_clean[:-len(sfx)]
                                if len(stem_a) >= 3 and len(stem_b) >= 3:
                                    if stem_a.startswith(stem_b) or stem_b.startswith(stem_a):
                                        confidence = 0.93
                                        reason = f"Domain identifier `{col_a.name}` matches `{col_b.name}`"
                                        src_tbl, src_col, tgt_tbl, tgt_col = table_b, col_b, table_a, col_a
                                        break

                    # Pattern 2: Foreign Key naming pattern: B -> A (col_b references table_a.col_a)
                    # e.g. orders.customer_id -> customers.id, or orders.CustomerID -> customers.id, sales.cust_id -> customers.id
                    if confidence == 0.0 and (col_a.is_primary_key or col_a_clean in GENERIC_ID_NAMES or is_a_id):
                        for v in a_variants:
                            v_clean = clean_token(v)
                            # Direct concatenation or snake_case match: customer_id, customerid
                            if col_b_clean == f"{v_clean}{col_a_clean}" or col_b.name.lower() == f"{v}_{col_a.name.lower()}":
                                confidence = 0.95
                                reason = f"Column `{col_b.name}` matches `{table_a.friendly_name}.{col_a.name}` naming pattern"
                                src_tbl, src_col, tgt_tbl, tgt_col = table_b, col_b, table_a, col_a
                                break
                            # Concatenation when col_a is generic 'id' and col_b is '<entity>id'
                            if col_a_clean in GENERIC_ID_NAMES and col_b_clean == f"{v_clean}id":
                                confidence = 0.94
                                reason = f"Column `{col_b.name}` references `{table_a.friendly_name}.{col_a.name}`"
                                src_tbl, src_col, tgt_tbl, tgt_col = table_b, col_b, table_a, col_a
                                break
                            # Prefix/abbreviation stem matching when col_a is generic 'id' or PK and col_b ends with 'id'
                            # e.g. sales.cust_id -> customers.id, employees.dept_id -> departments.id
                            if (col_a_clean in GENERIC_ID_NAMES or col_a.is_primary_key) and col_b_clean.endswith(col_a_clean):
                                prefix = col_b_clean[:-len(col_a_clean)]
                                if len(prefix) >= 3 and v_clean.startswith(prefix):
                                    confidence = 0.94
                                    reason = f"Column `{col_b.name}` (stem '{prefix}') references `{table_a.friendly_name}.{col_a.name}`"
                                    src_tbl, src_col, tgt_tbl, tgt_col = table_b, col_b, table_a, col_a
                                    break
                            # Role-prefixed: origin_airport_id -> airports.id or airports.airport_id
                            role_suffix = col_a_clean if col_a_clean.startswith(v_clean) else f"{v_clean}{col_a_clean}"
                            if col_b_clean.endswith(role_suffix) and len(col_b_clean) > len(role_suffix):
                                role = col_b_clean[:-len(role_suffix)].rstrip("_")
                                confidence = 0.90
                                reason = f"Role-prefixed `{col_b.name}` (role: '{role}') matches `{table_a.friendly_name}.{col_a.name}`"
                                disambiguation_hint = role
                                src_tbl, src_col, tgt_tbl, tgt_col = table_b, col_b, table_a, col_a
                                break

                    # Pattern 3: Foreign Key naming pattern: A -> B (col_a references table_b.col_b)
                    # Symmetric check when table order is inverted: e.g. sales.cust_id -> customers.id
                    if confidence == 0.0 and (col_b.is_primary_key or col_b_clean in GENERIC_ID_NAMES or is_b_id):
                        for v in b_variants:
                            v_clean = clean_token(v)
                            # Direct concatenation or snake_case match: customer_id, customerid
                            if col_a_clean == f"{v_clean}{col_b_clean}" or col_a.name.lower() == f"{v}_{col_b.name.lower()}":
                                confidence = 0.95
                                reason = f"Column `{col_a.name}` matches `{table_b.friendly_name}.{col_b.name}` naming pattern"
                                src_tbl, src_col, tgt_tbl, tgt_col = table_a, col_a, table_b, col_b
                                break
                            # Concatenation when col_b is generic 'id' and col_a is '<entity>id'
                            if col_b_clean in GENERIC_ID_NAMES and col_a_clean == f"{v_clean}id":
                                confidence = 0.94
                                reason = f"Column `{col_a.name}` references `{table_b.friendly_name}.{col_b.name}`"
                                src_tbl, src_col, tgt_tbl, tgt_col = table_a, col_a, table_b, col_b
                                break
                            # Prefix/abbreviation stem matching when col_b is generic 'id' or PK and col_a ends with 'id'
                            # e.g. sales.cust_id -> customers.id, employees.dept_id -> departments.id
                            if (col_b_clean in GENERIC_ID_NAMES or col_b.is_primary_key) and col_a_clean.endswith(col_b_clean):
                                prefix = col_a_clean[:-len(col_b_clean)]
                                if len(prefix) >= 3 and v_clean.startswith(prefix):
                                    confidence = 0.94
                                    reason = f"Column `{col_a.name}` (stem '{prefix}') references `{table_b.friendly_name}.{col_b.name}`"
                                    src_tbl, src_col, tgt_tbl, tgt_col = table_a, col_a, table_b, col_b
                                    break
                            # Role-prefixed: origin_airport_id -> airports.id or airports.airport_id
                            role_suffix = col_b_clean if col_b_clean.startswith(v_clean) else f"{v_clean}{col_b_clean}"
                            if col_a_clean.endswith(role_suffix) and len(col_a_clean) > len(role_suffix):
                                role = col_a_clean[:-len(role_suffix)].rstrip("_")
                                confidence = 0.90
                                reason = f"Role-prefixed `{col_a.name}` (role: '{role}') matches `{table_b.friendly_name}.{col_b.name}`"
                                disambiguation_hint = role
                                src_tbl, src_col, tgt_tbl, tgt_col = table_a, col_a, table_b, col_b
                                break

                    if confidence >= 0.70 and src_tbl is not None:
                        # 3. Optional Value Overlap Verification (Empirical validation)
                        if verify_data_overlap and db_engine is not None:
                            try:
                                with db_engine.connect() as conn:
                                    test_sql = text(
                                        f"SELECT 1 FROM `{src_tbl.physical_name}` s "
                                        f"JOIN `{tgt_tbl.physical_name}` t ON s.`{src_col.name}` = t.`{tgt_col.name}` "
                                        f"LIMIT 1"
                                    )
                                    has_overlap = conn.execute(test_sql).scalar()
                                    if has_overlap:
                                        confidence = min(1.0, confidence + 0.04)
                                    else:
                                        # If both tables possess data but have zero overlapping values,
                                        # they belong to disjoint value spaces (not an active relational link)
                                        s_cnt = conn.execute(text(f"SELECT 1 FROM `{src_tbl.physical_name}` LIMIT 1")).scalar()
                                        t_cnt = conn.execute(text(f"SELECT 1 FROM `{tgt_tbl.physical_name}` LIMIT 1")).scalar()
                                        if s_cnt is not None and t_cnt is not None:
                                            confidence -= 0.30
                            except Exception:
                                pass

                        if confidence >= 0.70:
                            relationships.append(InferredRelationship(
                                source_table=src_tbl.friendly_name,
                                source_physical=src_tbl.physical_name,
                                source_column=src_col.name,
                                target_table=tgt_tbl.friendly_name,
                                target_physical=tgt_tbl.physical_name,
                                target_column=tgt_col.name,
                                confidence=round(confidence, 2),
                                cardinality="N:1",
                                reason=reason,
                                disambiguation_hint=disambiguation_hint
                            ))

    # Deduplicate relationships and flag ambiguity
    deduped: List[InferredRelationship] = []
    seen = set()
    table_pairs: Dict[Tuple[str, str], List[InferredRelationship]] = {}

    for rel in sorted(relationships, key=lambda r: r.confidence, reverse=True):
        # Deduplicate undirected pairs of identical columns so the highest confidence direction is kept
        undirected_key = tuple(sorted([
            f"{rel.source_table.lower()}.{rel.source_column.lower()}",
            f"{rel.target_table.lower()}.{rel.target_column.lower()}"
        ]))
        if undirected_key not in seen:
            seen.add(undirected_key)
            deduped.append(rel)
            pair_key = tuple(sorted([rel.source_table.lower(), rel.target_table.lower()]))
            table_pairs.setdefault(pair_key, []).append(rel)

    # Flag ambiguous multi-foreign key relationships (e.g. origin_airport vs dest_airport between same table pair)
    for pair_rels in table_pairs.values():
        if len(pair_rels) > 1:
            for r in pair_rels:
                r.is_ambiguous = True

    return deduped


# -----------------------------------------------------------------------------
# 2b. Pending Clarification Context Store (Thread-safe session memory)
# -----------------------------------------------------------------------------

_clarification_lock = threading.Lock()
_pending_clarifications: Dict[str, Dict[str, Any]] = {}


def _make_clarification_key(user_id: str, table_name: Optional[str] = None) -> str:
    tbl = (table_name or "").strip().lower()
    return f"{user_id}:{tbl}"


def save_pending_clarification(user_id: str, table_name: Optional[str], context_data: Optional[Dict[str, Any]]) -> None:
    """Stores pending clarification context isolated by user and active dataset with auto-expiration."""
    if not context_data:
        return
    with _clarification_lock:
        now = time.time()
        # Expire stale entries (> 3 minutes / 180 seconds)
        for k in list(_pending_clarifications.keys()):
            if now - _pending_clarifications[k].get("timestamp", 0) > 180:
                _pending_clarifications.pop(k, None)
        context_data["timestamp"] = now
        context_data["table_name"] = table_name
        key = _make_clarification_key(user_id, table_name)
        _pending_clarifications[key] = context_data


def get_pending_clarification(user_id: str, table_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves active pending clarification context for user and dataset if not expired."""
    with _clarification_lock:
        key = _make_clarification_key(user_id, table_name)
        data = _pending_clarifications.get(key)
        if data:
            if time.time() - data.get("timestamp", 0) > 180:
                _pending_clarifications.pop(key, None)
                return None
        return data


def clear_pending_clarification(user_id: str, table_name: Optional[str] = None) -> None:
    """Clears pending clarification context for a user and dataset."""
    with _clarification_lock:
        key = _make_clarification_key(user_id, table_name)
        _pending_clarifications.pop(key, None)


def resolve_clarification_followup(pending: Dict[str, Any], user_input: str) -> Optional[str]:
    """
    Evaluates follow-up user input against a pending clarification context.
    If the follow-up answers the clarification, synthesizes the complete unambiguous question.
    """
    if not pending or not user_input:
        return None
    input_lower = user_input.lower().strip()
    matched_role = None

    # 1. Match exact clarification options (e.g. "origin city", "destination city")
    for opt in pending.get("options", []):
        opt_lower = opt.lower()
        if opt_lower in input_lower or input_lower in opt_lower:
            matched_role = opt_lower.split()[0]
            break

    # 2. Match role hints (e.g. "origin", "destination")
    if not matched_role:
        for role in pending.get("role_hints", []):
            if role and role in input_lower:
                matched_role = role
                break

    if not matched_role:
        return None

    orig_q = pending.get("original_question", "")
    novel_col = pending.get("novel_column")

    # If user provided a complete long sentence, use user's explicit sentence directly
    if len(input_lower.split()) > 4:
        return user_input

    # Otherwise, synthesize role into the original ambiguous question
    if novel_col:
        pattern = re.compile(rf"\b{re.escape(novel_col)}\b", re.IGNORECASE)
        combined = pattern.sub(f"{matched_role} {novel_col}", orig_q, count=1)
        if combined != orig_q:
            return combined

    return f"{orig_q} ({matched_role})"


# -----------------------------------------------------------------------------
# 3. Relationship Graph & Multi-Hop Path Finding
# -----------------------------------------------------------------------------

class RelationshipGraph:
    """
    Undirected multigraph representing relationships between user tables.
    Uses BFS / shortest-path search to connect tables across multi-hop relationships.
    """

    def __init__(self, relationships: List[InferredRelationship], question_lower: str = ""):
        self.relationships = relationships
        self.question_lower = question_lower
        self.adj: Dict[str, List[Tuple[str, InferredRelationship]]] = {}

        for rel in relationships:
            s = rel.source_table.lower()
            t = rel.target_table.lower()
            self.adj.setdefault(s, []).append((t, rel))
            self.adj.setdefault(t, []).append((s, rel))

        # Prioritize edges that match disambiguation role hints present in the question
        if question_lower:
            for node in self.adj:
                self.adj[node].sort(
                    key=lambda item: (
                        1 if (item[1].disambiguation_hint and item[1].disambiguation_hint in self.question_lower) else 0,
                        item[1].confidence
                    ),
                    reverse=True
                )

    def find_shortest_path(self, start: str, target: str) -> Optional[List[InferredRelationship]]:
        """Finds shortest join path (minimum hops, highest confidence) between two tables."""
        s_node = start.lower()
        t_node = target.lower()

        if s_node == t_node:
            return []

        queue = [(s_node, [])]
        visited = {s_node}

        while queue:
            current, path = queue.pop(0)

            if current == t_node:
                return path

            for neighbor, rel in self.adj.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [rel]))

        return None

    def find_connecting_subgraph(
        self,
        required_tables: Set[str],
        preferred_root: Optional[str] = None
    ) -> Tuple[Set[str], List[InferredRelationship]]:
        """
        Connects all required tables into a single joined component.
        Returns the set of all required + bridge tables, and the join relationships.
        """
        if len(required_tables) <= 1:
            return required_tables, []

        all_nodes = set(t.lower() for t in required_tables)
        root = preferred_root.lower() if preferred_root and preferred_root.lower() in all_nodes else list(all_nodes)[0]

        connected_nodes = {root}
        connecting_rels: List[InferredRelationship] = []
        remaining = all_nodes - {root}

        while remaining:
            best_path = None
            best_target = None

            # Find shortest path from any currently connected node to any remaining required node
            for conn_node in connected_nodes:
                for rem_node in remaining:
                    path = self.find_shortest_path(conn_node, rem_node)
                    if path is not None:
                        if best_path is None or len(path) < len(best_path):
                            best_path = path
                            best_target = rem_node

            if best_path is None:
                # No connecting path found between disjoint table islands
                break

            for rel in best_path:
                connecting_rels.append(rel)
                connected_nodes.add(rel.source_table.lower())
                connected_nodes.add(rel.target_table.lower())

            remaining.discard(best_target)

        return connected_nodes, connecting_rels


# -----------------------------------------------------------------------------
# 4. Question-to-Schema Dynamic Table Resolution
# -----------------------------------------------------------------------------

def resolve_query_context(
    question: str,
    user_id: str,
    active_table: Optional[str] = None,
    db_engine: Engine = engine
) -> QueryContext:
    """
    Main entry point for dynamic schema discovery and multi-table query planning:
    1. Discovers all authorized tables and columns for user.
    2. Infers relationships between all tables.
    3. Evaluates user question against discovered schemas to select required tables.
    4. Computes multi-hop join paths to bridge tables if needed.
    5. Formats schemas and discovered relationships for LLM prompt.
    """
    schemas = discover_user_schemas(user_id=user_id, db_engine=db_engine)
    if not schemas:
        # Fallback if no tables owned
        return QueryContext(
            physical_tables=[],
            friendly_tables=[],
            active_table_friendly=active_table or "",
            schemas_prompt="",
            relationships=[],
            relationships_prompt="",
            is_multi_table=False
        )

    canonical_id, canonical_suffix = extract_canonical_user_id(user_id)
    active_friendly = derive_friendly_table_name(active_table, canonical_suffix).lower() if active_table else ""

    # Analyze question against schemas to detect required tables
    question_lower = question.lower()
    words_in_q = set(re.findall(r"\b[a-zA-Z0-9_]+\b", question_lower))
    question_tokens = extract_semantic_tokens(question) | words_in_q

    # Infer relationships across all user tables
    relationships = infer_table_relationships(schemas=schemas, db_engine=db_engine)
    graph = RelationshipGraph(relationships, question_lower=question_lower)

    table_scores: Dict[str, int] = {}
    matched_columns_per_table: Dict[str, List[str]] = {}

    for friendly, meta in schemas.items():
        score = 0
        matched_cols = []

        # 1. Match table name or singular forms in question
        variants = get_table_name_variants(friendly)
        for v in variants:
            if v in words_in_q or v in question_tokens or v in question_lower:
                score += 5

        # 2. Match column names in question
        for col in meta.columns:
            c_name = col.name.lower()
            clean_c = c_name.replace("_", " ")
            col_tokens = extract_semantic_tokens(col.name)
            is_col_id = is_identifier_column(col.name, col.is_primary_key)

            # Skip generic identifier columns for initial table scoring
            if clean_token(c_name) in GENERIC_ID_NAMES:
                continue

            # Multi-word column match (e.g. "unit price" in question)
            if " " in clean_c and clean_c in question_lower:
                score += 4
                matched_cols.append(col.name)
            elif (c_name in words_in_q or c_name in question_tokens) and len(c_name) > 2:
                # Full column name match
                weight = 1 if c_name in NON_RELATIONAL_ATTRIBUTES else 3
                score += weight
                matched_cols.append(col.name)
            elif col_tokens & question_tokens:
                # Semantic component match across token boundaries (camelCase, PascalCase, snake_case)
                # Exclude foreign key columns from accidental component matching
                if not is_col_id:
                    matched_parts = col_tokens & question_tokens
                    weight = 1 if any(p in NON_RELATIONAL_ATTRIBUTES for p in matched_parts) else 2
                    score += weight
                    matched_cols.append(col.name)

        table_scores[friendly] = score
        matched_columns_per_table[friendly] = matched_cols

    # Determine candidate tables
    candidate_tables: Set[str] = set()

    # Tables with direct entity or column matches
    for tbl, sc in table_scores.items():
        if sc > 0:
            candidate_tables.add(tbl)

    # Active table baseline:
    # If active table is given, check if it can answer the query alone
    if active_friendly and active_friendly in schemas:
        active_meta = schemas[active_friendly]
        active_col_names = {c.name.lower() for c in active_meta.columns}

        # Check which external tables contribute UNIQUE concepts not available in the active table
        external_contributors = set()
        for t in candidate_tables:
            if t == active_friendly:
                continue
            # Did table t match because of an entity name explicitly in the question?
            t_variants = get_table_name_variants(t)
            entity_matched = any(v in words_in_q for v in t_variants)

            # Or did table t have matched columns that are NOT in the active table?
            t_matched_cols = matched_columns_per_table.get(t, [])
            novel_cols = [c for c in t_matched_cols if c.lower() not in active_col_names]

            if entity_matched or novel_cols:
                external_contributors.add(t)

        if not external_contributors:
            # Question is completely answerable by the active table alone
            candidate_tables = {active_friendly}
        else:
            # Active table is part of the query along with related tables
            candidate_tables = {active_friendly} | external_contributors

    # If no tables scored, default to active table or first available table
    if not candidate_tables:
        if active_friendly and active_friendly in schemas:
            candidate_tables = {active_friendly}
        else:
            candidate_tables = {list(schemas.keys())[0]}

    # Bridge disconnected tables using relationship graph (multi-hop join discovery)
    resolved_nodes, resolved_rels = graph.find_connecting_subgraph(
        required_tables=candidate_tables,
        preferred_root=active_friendly if active_friendly in candidate_tables else None
    )

    # Ambiguity check & clarification detection
    table_pairs: Dict[Tuple[str, str], List[InferredRelationship]] = {}
    for rel in relationships:
        pair_key = tuple(sorted([rel.source_table.lower(), rel.target_table.lower()]))
        if pair_key[0] in resolved_nodes and pair_key[1] in resolved_nodes:
            table_pairs.setdefault(pair_key, []).append(rel)

    needs_clarification = False
    clarification_prompt = None
    clarification_options: List[str] = []
    ambiguous_relationships: List[InferredRelationship] = []
    clarification_context_data = None
    ambiguity_warning = None

    for pair_key, pair_rels in table_pairs.items():
        if len(pair_rels) > 1:
            # Check if question explicitly specifies any of the role hints
            matching_roles = [r for r in pair_rels if r.disambiguation_hint and r.disambiguation_hint in question_lower]
            if len(matching_roles) == 1:
                # Disambiguated by user's question!
                # Ensure resolved_rels uses this specific chosen relationship
                for i, r in enumerate(resolved_rels):
                    if tuple(sorted([r.source_table.lower(), r.target_table.lower()])) == pair_key:
                        resolved_rels[i] = matching_roles[0]
                        matching_roles[0].is_ambiguous = False
            elif len(matching_roles) == 0:
                # Ambiguous! Multiple plausible relationships exist and user question did not specify role
                needs_clarification = True
                ambiguous_relationships = pair_rels
                src_tbl = pair_rels[0].source_table
                tgt_tbl = pair_rels[0].target_table

                # Check for novel column in either table
                novel_col = None
                for col in matched_columns_per_table.get(tgt_tbl, []) + matched_columns_per_table.get(src_tbl, []):
                    if col.lower() not in GENERIC_ID_NAMES and not is_identifier_column(col, False):
                        novel_col = col
                        break

                if novel_col:
                    clarification_options = [
                        f"{r.disambiguation_hint} {novel_col}" if r.disambiguation_hint else r.source_column
                        for r in pair_rels
                    ]
                else:
                    clarification_options = [
                        r.disambiguation_hint or r.source_column for r in pair_rels
                    ]

                options_phrase = (
                    f"{clarification_options[0]} or {clarification_options[1]}"
                    if len(clarification_options) == 2
                    else ", ".join(clarification_options[:-1]) + f", or {clarification_options[-1]}"
                )
                clarification_prompt = (
                    f"Multiple relationships connect '{src_tbl}' and '{tgt_tbl}'. "
                    f"Please clarify whether you mean {options_phrase}."
                )

                clarification_context_data = {
                    "user_id": user_id,
                    "original_question": question,
                    "active_table": active_table,
                    "source_table": src_tbl,
                    "target_table": tgt_tbl,
                    "novel_column": novel_col,
                    "options": clarification_options,
                    "role_hints": [r.disambiguation_hint for r in pair_rels if r.disambiguation_hint]
                }
                break
            else:
                ambiguity_warning = (
                    f"Notice: Multiple join relationships exist between '{pair_rels[0].source_table}' and '{pair_rels[0].target_table}'."
                )

    # Format schemas for LLM prompt
    schemas_prompt = ""
    physical_tables = []
    friendly_tables = []

    for friendly_key in sorted(list(resolved_nodes)):
        if friendly_key in schemas:
            meta = schemas[friendly_key]
            physical_tables.append(meta.physical_name)
            friendly_tables.append(meta.friendly_name)

            col_lines = []
            for c in meta.columns:
                pk_marker = " [PRIMARY KEY]" if c.is_primary_key else ""
                col_lines.append(f"- `{c.name}` ({c.data_type}){pk_marker}")

            schemas_prompt += f"Table: `{meta.friendly_name}`\nColumns:\n" + "\n".join(col_lines) + "\n\n"

    # Format relationships for LLM prompt
    rel_lines = []
    for r in resolved_rels:
        rel_lines.append(
            f"• `{r.source_table}` joins with `{r.target_table}` on:\n"
            f"  `{r.source_table}`.`{r.source_column}` = `{r.target_table}`.`{r.target_column}`\n"
            f"  Relationship: {r.cardinality} ({r.reason})"
        )

    relationships_prompt = "\n".join(rel_lines) if rel_lines else "None (Single-table query)"

    return QueryContext(
        physical_tables=physical_tables,
        friendly_tables=friendly_tables,
        active_table_friendly=schemas[active_friendly].friendly_name if active_friendly in schemas else (friendly_tables[0] if friendly_tables else ""),
        schemas_prompt=schemas_prompt.strip(),
        relationships=resolved_rels,
        relationships_prompt=relationships_prompt,
        is_multi_table=len(resolved_nodes) > 1,
        ambiguity_warning=ambiguity_warning,
        needs_clarification=needs_clarification,
        clarification_prompt=clarification_prompt,
        clarification_options=clarification_options,
        ambiguous_relationships=ambiguous_relationships,
        clarification_context_data=clarification_context_data
    )
