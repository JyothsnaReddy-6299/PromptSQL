# Relationships and verified multi-dataset queries

## Using the workspace

Open Dashboard → Relationships. Choose two datasets, inspect their schemas, and
select one or more equality-key mappings. Names and compatible measured data can
suggest keys; suggestions never create approvals. Choose INNER or LEFT, preview
the counts, inspect them, check the approval box, then save.

Connections has a visual graph and an equivalent accessible list. Inspect shows
the stored approval profile; Edit / revalidate generates a fresh preview before
saving. Deactivate prevents future use without deleting the historical definition.
LEFT joins preserve the left dataset selected in this workspace.

In Ask AI, name the required datasets and the metric source, for example:
“Total order amount from orders involving items” or “Total item quantity from
orders and items”. Existing metric aliases and approved definitions are supplied
to the existing SQL generator. Ambiguous relationship paths are presented through
the existing clarification workflow; choosing a path resumes the original question.

## Counts and equality semantics

Each side reports source records, records with complete keys, records with any
NULL component, distinct complete keys, duplicate key groups, and excess duplicate
records (complete records minus distinct complete keys). A duplicate group is a
key occurring more than once, not a count of all duplicate records.

Matched source records count original records on that named side having a complete
key present on the other side. Unmatched source records include NULL/incomplete
keys and complete keys absent on the other side. Composite keys match only when
all components match. Empty text is a value, not NULL. Text equality follows the
configured database collation; it is not claimed to be byte-for-byte equality.
Identifiers are never automatically converted to numbers or stripped of leading zeros.

Cardinality uses maximum complete-key frequency on both sides, including unmatched
keys. INNER joined records sum left frequency × right frequency over shared keys.
LEFT joined records add unmatched left source records. Expansion divides expected
selected-join records by total left source records (0 for an empty left dataset).
The UI displays measured timestamp, both directional counts, and these definitions.

## Query integration and analytical correctness

This extends `/ask`, the existing SQL generator/repair loop, SQLGlot validation,
metric context, and existing history/report saving. There is no separate SQL
execution pipeline. A post-validation join guard checks every direct join's
approved keys, join type and ownership, and re-profiles key frequencies before
execution. Invented/unapproved joins and incompatible/stale connections stop the
query. Omitted required datasets also stop the query.

Initially supported:

- Direct INNER and LEFT equality joins, including composite keys.
- Raw detail results, with measured expansion and unmatched-record explanations.
- SUM, AVG, MIN, MAX and column COUNT from a single identifiable dataset grain.
- Detail metrics joined to a unique parent retain their original detail grain.
- Source-level SUM/AVG/COUNT with a detail join used solely for membership:
  detail records are grouped to one record per join key before joining the source.
  The original source records and their amounts are retained; amounts are never
  deduplicated. This also supports many-to-many membership reductions when there
  is one metric source and no selected detail dimensions or filters.
- Multiple metrics from one-to-one joins; duplicate-invariant MIN/MAX where safe.
- Approved paths up to four edges, with conservative multi-hop aggregation rules.

The Orders 100 + 200 / Items 1 + 2 + 1 fixture proves naive revenue 400 is reduced
to the correct 300 while item quantity remains 4. Equal-amount orders remain
separate legitimate records. SUM(DISTINCT amount) is explicitly rejected as a
fanout correction.

Unsupported or ambiguous cases return an explanation instead of a plausible total:
source metrics grouped/filtered by detail fields without allocation, multiple
competing metric grains with fanout, reverse fanout reductions, cross joins,
RIGHT/FULL/non-equality joins, COUNT(*) across datasets, DISTINCT aggregates,
multi-dataset CTEs/subqueries/window queries, and multi-hop fanout requiring a
more specific grain plan. Relationships are user-approved analytical connections,
not verified database foreign keys. Runtime SQL success alone is never approval.

Multi-dataset answers include datasets, relationship IDs/keys/types/cardinality,
metric sources and original-record grain, unmatched warnings, and performed
pre-aggregation. Explanations are appended to the saved summary so history,
saved reports, and PDF exports retain them.

## Persistence, freshness and migration

`dataset_references` maps stable logical IDs to server-discovered owned tables.
Existing datasets are discovered from trusted server inspection and the existing
user-suffix ownership convention; new requests use logical IDs, not table names.
`dataset_relationships` stores owner, logical endpoints, mappings, type, measured
profile, approval/active/revalidation flags, revision references and timestamps.
The preview digest binds confirmation to current keys, versions and measured
counts; a changed profile requires a new preview.

Migration version `001_relationship_manager` is additive and tracked in
`promptsql_migrations`. Normal backend startup applies it idempotently. Alternatively,
from `backend` using the project's configured environment:

```powershell
..\venv\Scripts\python.exe -m app.migrations.runner
```

No new configuration or dependencies are required beyond the existing installed
requirements. The database account needs CREATE TABLE permission for these new
tables. Existing uploaded tables, relationships, history and reports are preserved.
The migration has only been run against isolated test fixtures during this change;
production was not touched or deployed.

Schema fingerprints plus application mutation revisions mark affected relationships
stale after replacement, cleaning, inline editing, DML/DDL, deletion or undo.
Invalidation happens before mutations conservatively, so failed attempts may also
require revalidation. Edit / revalidate remeasures and explicitly approves again.
Changed or missing schemas are detected on reads and execution as well.

Immutable dataset snapshots are not implemented. External data changes with the
same schema require manual revalidation; execution still remeasures cardinality
and overlap. Profiling/approval/execution are separate operations, not a database-wide
snapshot, so simultaneous external writes are not guaranteed to be isolated.
Profiling uses exact grouped SQL counts and can be expensive for large unindexed
keys; no benchmark or latency guarantee is claimed.

## Validation

Run isolated tests from the repository root:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

The suite includes original single-table/metric clarification regressions,
relationship lifecycle/profile tests and a FastAPI HTTP flow from relationship
choice to guarded query execution, history and saved report. SQLite fixtures and
mocked LLM responses are used; no production database or live Groq calls are made.
On Windows the HTTP client needs local loopback socket permission for its async
runtime. MySQL-specific production collation/transaction behavior and real LLM
phrasing have not been exercised against production.

Build the frontend in `frontend` with `npm run build`.

## Changed areas

New: `backend/app/models/relationship.py`, `migrations/runner.py`,
`routes/relationships.py`, `services/relationship_service.py`,
`services/join_guard.py`, `tests/test_relationships.py`, and
`frontend/src/components/RelationshipsManager.tsx`.

Extended: backend startup, `/ask`, the clarification resolver, existing generation
and repair services, upload/cleaning/modification/undo invalidation, dashboard
navigation, the API client and chat clarification labels.

Final verification for this change: **56 backend tests passed**, including 27
relationship acceptance tests and the 29 existing query/metric regressions.
`npm run build` passed. Relationship and cleaner routers also generated OpenAPI
successfully. Existing dependency deprecation warnings remain in the HTTP test
client and older Pydantic response models.

Complete modified-file list:

- `backend/app/main.py`
- `backend/app/routes/ask.py`
- `backend/app/routes/cleaner.py`
- `backend/app/routes/history.py`
- `backend/app/routes/metrics.py`
- `backend/app/routes/upload.py`
- `backend/app/services/modification_executor.py`
- `backend/app/services/sql_generator.py`
- `backend/app/services/sql_regenerator.py`
- `backend/app/services/upload_service.py`
- `frontend/src/components/ChatBox.tsx`
- `frontend/src/components/DashboardSidebar.tsx`
- `frontend/src/pages/DashboardPage.tsx`
- `frontend/src/services/api.ts`

Complete added-file list:

- `backend/app/migrations/runner.py`
- `backend/app/models/relationship.py`
- `backend/app/routes/relationships.py`
- `backend/app/services/relationship_service.py`
- `backend/app/services/join_guard.py`
- `backend/tests/test_relationships.py`
- `frontend/src/components/RelationshipsManager.tsx`
- `docs/relationships.md`
