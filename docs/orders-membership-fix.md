# Orders/Customers membership source-selection fix

## Root cause confirmed before implementation

`select_datasets` treated partial active-table field coverage as a reason to
include the active dataset in every multi-source candidate (`[active, *group]`).
The active ecommerce table could therefore remain mandatory even though Orders
and Customers supplied the entire request. Graph lookup correctly rejected the
unrelated third source; approval/freshness checks were not the root cause.

Field comparison also used inconsistent spellings: `Order IDs`, `Order_IDs`,
`Order ID` and `Order_ID` were not treated as the same requested identifier.
An isolated regression with spaced/plural Orders IDs and underscored ecommerce IDs
reproduced the reported **three-source** set before the fix. Singular schema
variants could instead omit the Orders source because the plural question did not
match its column name.

The investigation used repository code and isolated fixtures, not live database
catalog rows. It establishes the faulty selection branch and reproduces the error;
it does not claim to have inspected the exact production column spelling.

## Changes

- Normalize field references across spaces, underscores, case, and ID/key plurals.
- Search inclusion-minimal combinations covering requested outputs, filters and
  metrics across the owned catalog. Active context is not forcibly inserted.
- Prefer active context when it alone can answer the full request. Preserve
  explicitly requested sources; add sources needed for their missing filter fields.
- For entity-qualified fields such as order IDs, favor the corresponding Orders
  dataset over an unrelated schema with an overlapping identifier. Tied source
  interpretations still use the existing clarification workflow.
- Mask filter values during source selection. `Gold` remains an unchanged SQL
  filter value even if another schema has a column or dataset named Gold.
- Keep existing ownership, approved-path, direction/type/key and freshness guards.
  Only the selected sources enter path lookup; legitimate approved bridge tables
  are still supplied by graph traversal.
- Keep unrelated ecommerce metrics out of generation and repair prompts.

No schema migration, new dependency, frontend change or production data mutation
is required.

## Actual validation

`python -m unittest discover -s backend/tests -q`: **96 tests passed** in this
workspace. This includes the existing query/metric/ecommerce and grain-safety
regressions, the reproduced resolver failure, and nine new isolated membership
integration tests. `git diff --check` passed.

Both questions were executed through the existing generator, SQL validation, join
guard and executor, with each of Orders, Customers and ecommerce selected as active:

- “Give me order IDs whose membership is Gold.”
- “Give me order IDs from orders and customers whose membership is Gold.”

Every variant resolved only `orders_usr_8` and `customers_usr_8`, used their
approved Customer ID join, applied `Membership = 'Gold'`, and returned fixture
orders O1, O3 and O4. The Silver customer's O2 was excluded. Ecommerce had no
relationship to the required pair and was neither selected nor needed.

Tests also verify an explicitly named Orders source is completed with Customers
for the membership filter; only necessary sources reach graph lookup; unrelated
saved metrics and Gold-named schemas/columns do not add dependencies; a legitimate
approved bridge works; and cross-owner, unapproved, inactive and stale cases remain
blocked. An existing clarification-chain test now selects its intended Header/Items
pair explicitly because candidate source sets no longer all contain the active
header implicitly.

All database work used isolated SQLite fixtures. LLM responses were mocked at the
configured adapter boundary while actual generation/repair prompt construction,
SQL parsing, profile/path lookup and execution ran. Real Groq generation and the
Render/MySQL deployment remain unverified. No frontend build was needed for this
backend-only change. Existing test dependency deprecation warnings remain.

## Files changed

- `backend/app/services/dataset_resolution.py`
- `backend/tests/test_dataset_resolution.py`
- `backend/tests/test_orders_membership.py` (new)
- `backend/tests/test_relationship_query_integration.py`
- `docs/orders-membership-fix.md` (new)
