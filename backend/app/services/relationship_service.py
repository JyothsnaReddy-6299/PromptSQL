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
            # Table A has a Primary Key or unique identifier `pk_col`
            # Table B has a column `col_b` that references Table A
            a_variants = get_table_name_variants(table_a.friendly_name)

            for col_a in table_a.columns:
                # Target column in Table A must be a PK, an explicit ID, or a specific identifier
                col_a_lower = col_a.name.lower()
                is_target_id = col_a.is_primary_key or col_a_lower.endswith("_id") or col_a_lower.endswith("_code") or col_a_lower in GENERIC_ID_NAMES

                if not is_target_id:
                    continue

                for col_b in table_b.columns:
                    col_b_lower = col_b.name.lower()

                    # False-positive suppression:
                    # Generic columns matching across tables (e.g. A.id = B.id, A.status = B.status)
                    # must NEVER be inferred as foreign keys
                    if col_a_lower in GENERIC_ID_NAMES and col_b_lower in GENERIC_ID_NAMES:
                        continue
                    if col_b_lower in NON_RELATIONAL_ATTRIBUTES:
                        continue

                    # Type compatibility check
                    if not are_types_join_compatible(col_a.generic_type, col_b.generic_type):
                        continue

                    confidence = 0.0
                    reason = ""
                    disambiguation_hint = None

                    # Pattern 1: Exact <table_a_variant>_<pk_a_name> (e.g. orders.customer_id -> customers.id)
                    for v in a_variants:
                        if col_b_lower == f"{v}_{col_a_lower}":
                            confidence = 0.95
                            reason = f"Column `{col_b.name}` matches `{table_a.friendly_name}.{col_a.name}` naming pattern"
                            break
                        # Handle concatenated: customerid -> customers.id
                        if col_b_lower == f"{v}{col_a_lower}":
                            confidence = 0.92
                            reason = f"Concatenated `{col_b.name}` matches `{table_a.friendly_name}.{col_a.name}`"
                            break
                        # Handle role-prefixed: origin_airport_id -> airports.id
                        if col_b_lower.endswith(f"_{v}_{col_a_lower}"):
                            role = col_b_lower[:-len(f"_{v}_{col_a_lower}")]
                            confidence = 0.90
                            reason = f"Role-prefixed `{col_b.name}` (role: '{role}') matches `{table_a.friendly_name}.{col_a.name}`"
                            disambiguation_hint = role
                            break

                    # Pattern 2: Shared non-generic identifier across tables
                    # (e.g. departments.dept_code [PK] <-> employees.dept_code)
                    if confidence == 0.0 and col_a_lower not in GENERIC_ID_NAMES:
                        if col_a_lower == col_b_lower and (col_a.is_primary_key or col_a_lower.endswith("_code") or col_a_lower.endswith("_id")):
                            confidence = 0.90
                            reason = f"Shared domain identifier `{col_b.name}` across both tables"

                    if confidence >= 0.70:
                        # 3. Optional Value Overlap Verification (Empirical validation)
                        if verify_data_overlap and db_engine is not None:
                            try:
                                with db_engine.connect() as conn:
                                    test_sql = text(
                                        f"SELECT 1 FROM `{table_b.physical_name}` b "
                                        f"JOIN `{table_a.physical_name}` a ON b.`{col_b.name}` = a.`{col_a.name}` "
                                        f"LIMIT 1"
                                    )
                                    has_overlap = conn.execute(test_sql).scalar()
                                    if has_overlap:
                                        confidence = min(1.0, confidence + 0.04)
                            except Exception:
                                pass

                        relationships.append(InferredRelationship(
                            source_table=table_b.friendly_name,
                            source_physical=table_b.physical_name,
                            source_column=col_b.name,
                            target_table=table_a.friendly_name,
                            target_physical=table_a.physical_name,
                            target_column=col_a.name,
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
        key = (rel.source_table.lower(), rel.source_column.lower(), rel.target_table.lower(), rel.target_column.lower())
        if key not in seen:
            seen.add(key)
            deduped.append(rel)
            pair_key = (rel.source_table.lower(), rel.target_table.lower())
            table_pairs.setdefault(pair_key, []).append(rel)

    # Flag ambiguous multi-foreign key relationships (e.g. origin_airport vs dest_airport)
    for pair_rels in table_pairs.values():
        if len(pair_rels) > 1:
            for r in pair_rels:
                r.is_ambiguous = True

    return deduped


# -----------------------------------------------------------------------------
# 3. Relationship Graph & Multi-Hop Path Finding
# -----------------------------------------------------------------------------

class RelationshipGraph:
    """
    Undirected multigraph representing relationships between user tables.
    Uses BFS / shortest-path search to connect tables across multi-hop relationships.
    """

    def __init__(self, relationships: List[InferredRelationship]):
        self.relationships = relationships
        self.adj: Dict[str, List[Tuple[str, InferredRelationship]]] = {}

        for rel in relationships:
            s = rel.source_table.lower()
            t = rel.target_table.lower()
            self.adj.setdefault(s, []).append((t, rel))
            self.adj.setdefault(t, []).append((s, rel))

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

    # Infer relationships across all user tables
    relationships = infer_table_relationships(schemas=schemas, db_engine=db_engine)
    graph = RelationshipGraph(relationships)

    # Analyze question against schemas to detect required tables
    question_lower = question.lower()
    words_in_q = set(re.findall(r"\b[a-zA-Z0-9_]+\b", question_lower))

    table_scores: Dict[str, int] = {}
    matched_columns_per_table: Dict[str, List[str]] = {}

    for friendly, meta in schemas.items():
        score = 0
        matched_cols = []

        # 1. Match table name or singular forms in question
        variants = get_table_name_variants(friendly)
        for v in variants:
            if v in words_in_q or v in question_lower:
                score += 5

        # 2. Match column names in question
        for col in meta.columns:
            c_name = col.name.lower()
            clean_c = c_name.replace("_", " ")

            # Skip generic identifier columns for initial table scoring
            if c_name in GENERIC_ID_NAMES:
                continue

            # Multi-word column match (e.g. "unit price" in question)
            if " " in clean_c and clean_c in question_lower:
                score += 4
                matched_cols.append(col.name)
            elif c_name in words_in_q and len(c_name) > 2:
                # Full column name match
                weight = 1 if c_name in NON_RELATIONAL_ATTRIBUTES else 3
                score += weight
                matched_cols.append(col.name)
            else:
                # Component token match (e.g. "amount" or "total" from "total_amount")
                # Exclude foreign key columns (*_id, *_fk, *_pk) from component matching
                if not (c_name.endswith("_id") or c_name.endswith("_fk") or c_name.endswith("_pk")):
                    c_parts = [p for p in c_name.split("_") if len(p) > 2]
                    matched_parts = [p for p in c_parts if p in words_in_q]
                    if matched_parts:
                        score += 2
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

    # Ambiguity check
    ambiguity_warning = None
    for r in resolved_rels:
        if r.is_ambiguous:
            # Check if question specifies role hint
            if r.disambiguation_hint and r.disambiguation_hint in question_lower:
                r.is_ambiguous = False
            else:
                ambiguity_warning = (
                    f"Notice: Multiple join relationships exist between '{r.source_table}' and '{r.target_table}'. "
                    f"Joining on `{r.source_column}` = `{r.target_column}` based on inferred context."
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
        ambiguity_warning=ambiguity_warning
    )
