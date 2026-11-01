# Relationship-to-query integration repair

## Confirmed root cause

The failure was reproducible in the repository before changing the implementation:
all five initial dataset-resolution regressions failed (seven failing subcases).

1. `relationship_service.query_context` always included the raw active reference,
   then added other tables whenever a column name was a substring of the question.
   Its exclusion of active-table columns compared names case-sensitively. For
   example, an unrelated `Amount` column could select another dataset even though
   the active header already had `amount`. A literal `revenue` column elsewhere
   could select that table instead of interpreting revenue against active
   ecommerce `Total_Sales`. These false sources went into graph lookup before SQL
   generation, producing a relationship error for a single-table question.
2. Generation and repair independently selected tables using fuzzy table/column
   matching and then appended the endpoints of **every** approved relationship.
   The generated SQL scope therefore disagreed with the resolver's intended scope.
3. The active header was compared directly to physical names. Catalog IDs,
   logical names and physical names were not canonicalized at this boundary;
   graph traversal itself compared physical strings. An explicitly named remote
   single dataset was also always joined to the active dataset unnecessarily.
4. Combined header/detail totals were deliberately rejected whenever multiple
   source grains met fanout, rather than supporting safe detail pre-aggregation.
   This is separate from the premature relationship-resolution failure.

The relationship workspace stores catalog IDs and serializes approved endpoints
back to physical names correctly. No evidence in this investigation established
that the approved relationship rows themselves were missing/corrupt. Live Render
headers, catalog rows and SQL logs were not inspected, so the exact extra dataset
selected in each live failure is not claimed. Isolated fixtures reproduce the
code paths and failure modes above.

## Repair

A shared catalog-backed resolver authorizes and canonicalizes catalog IDs, logical
labels and physical names to the same owned physical identifier. It prefers the
active dataset, matches whole names with longest-name precedence, distinguishes
business nouns from explicit dataset names, and considers only missing fields
when another source is actually required. Short business concepts such as region,
quantity and revenue can resolve against Sales_Region, Quantity_Ordered and
Total_Sales on the active dataset. An explicit single dataset replaces the active
source instead of forcing a join to it.

Ambiguous source candidates use the existing server-side clarification sessions.
Dataset choices can be followed by relationship/metric choices; the chat stays
in clarification mode until a final result arrives. Resumed queries retain the
selected logical catalog IDs. Query/report metadata records the actual resolved
source instead of the previous active dataset label.

Generation, repair, SQL validation and execution receive only the selected sources
and approved bridge path. They no longer expand scope with all uploaded tables or
all approved relationships. Single-table queries skip relationship requirements
while retaining dataset authorization and SQL validation. The join guard remains
enabled for actual joins and still verifies approval, activity, freshness, exact
composite keys, direction and join type. Errors now identify resolved datasets,
connection IDs/names and inactive, unapproved, stale or missing eligibility.

For the supported unique-header / repeating-detail case, combined totals group
detail expressions by approved keys first and join those grouped measures to the
original header records. Equal header amounts remain separate original records.
SUM and COUNT roll up detail aggregates; AVG carries detail SUM and COUNT for a
weighted result; MIN/MAX roll up their corresponding detail aggregates. Parent
filters/grouping are supported. Detail-level allocation/filter ambiguity and
many-to-many mixed-source totals still fail closed. No SUM(DISTINCT amount) fix
is used. Existing membership reduction and raw detail queries are preserved.

The structured planner also recognizes "across all orders/records/rows" as an
overall scope, rather than an unresolved grouping dimension.

## Actual validation

Command: `.\venv\Scripts\python.exe -m unittest discover -s backend/tests -q`

**86 tests passed, no skips in this workspace:** 56 existing tests plus 12 resolver
and 18 integration tests. `npm run build` also passed; `git diff --check` passed.
Existing HTTP-client/Pydantic dependency deprecation warnings remain.

QA fixtures use isolated SQLite databases and mocked AI output, with actual SQL
parsing, ownership checks, profiling, approval/path lookup, grain rewriting and
execution. They do not use the live database.

| Check | Actual result |
|---|---|
| Header SELECT, with physical/logical/catalog-ID selection | Three original records |
| Header amount total | 400 |
| Detail equality join | Four matching records |
| Naive joined totals (demonstrating the bug) | Amount 500, quantity 5 |
| SUM(DISTINCT header amount) (demonstrating the wrong fix) | 300 |
| Guarded combined totals | Amount 400, quantity 5 |
| Combined AVG and COUNT | Quantity average 1.25, count 4 |
| Header-key grouping, reverse INNER and unmatched-header LEFT | Passed |
| Unapproved, inactive, stale, wrong keys/type | Blocked |
| Dataset mutation followed by revalidation | Eligibility restored; updated amount 425 |
| Dataset choice followed by relationship choice | Original query resumes and returns 400/5 |
| Ecommerce revenue | 28,110,784.23 |
| Ecommerce regional groups | East 7,134,297.52; North 6,906,958.05; South 6,950,825.18; West 7,118,703.48 |
| Highest sales, then choose revenue | East, 7,134,297.52 |

The ecommerce checks copied the existing **local**
`backend/uploads/ecommerce_sales_dataset.csv` (5,000 rows) into isolated SQLite,
using the existing numeric cleaning function. No answers are hardcoded in
application logic. Those three snapshot-specific tests are explicitly skipped on
machines without that local CSV; the other synthetic regressions remain runnable.

Unverified: live Render deployment, live MySQL collation/concurrency behavior,
current production data and real Groq generation quality. No production data or
relationship records were changed, and no deployment/push was performed.

## Changed files

Added:
- `backend/app/services/dataset_resolution.py`
- `backend/tests/test_dataset_resolution.py`
- `backend/tests/test_relationship_query_integration.py`
- `docs/relationship-query-fix.md`

Updated:
- `backend/app/routes/ask.py`
- `backend/app/routes/metrics.py`
- `backend/app/services/relationship_service.py`
- `backend/app/services/join_guard.py`
- `backend/app/services/query_planner.py`
- `backend/app/services/sql_generator.py`
- `backend/app/services/sql_regenerator.py`
- `frontend/src/components/ChatBox.tsx`
- `docs/relationships.md`

No schema migration or new dependency is required for this repair. Existing
relationships retain their IDs and approvals; stale relationships still require
explicit revalidation. Restart/rebuild the app to load these local code changes.
