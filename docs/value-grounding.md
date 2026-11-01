# Schema-grounded literal/name resolution

## Why the interpretations differed

Before this change, generation and repair received schema column names, selected
datasets and approved relationship mappings, but no measured evidence connecting
an unqualified value to its field. "Customer name Alice" supplied a lexical
column cue; "Alice" alone left the model free to infer an identifier predicate.
The SQL validator established syntax/ownership/column validity, not whether an
identifier column was the correct meaning of a string value. Thus a syntactically
valid `CustomerID = 'alice'` could execute despite referring to the wrong field.

The generation/repair prompts also retained a rule permitting joins using generic
primary/foreign-key relationships. This conflicted with the approved-relationship
contract. The existing join guard already rejects unapproved mappings; the prompt
now requires only the exact approved keys as well.

The code paths were inspected locally. No production query log or real Groq
response is claimed as inspected. Regression tests deliberately inject the old
incorrect filter/join so the correction is verified beyond a prompt-only change.

## Implementation

`value_grounding.py` finds referenced exact stored text values with bound SQL
lookups against the authenticated user's catalog. Column labels are not used to
hardcode which field means a person's name. Primary-key metadata and eligible
approved join mappings establish identifier roles; other fields are attributes.
Names are not cast into numbers. Original stored spelling is retained in equality
predicates so case-sensitive databases do not lose a match merely because the
model lowercased a name.

Measured bindings contribute required sources to existing dataset resolution and
its approved-path eligibility checks. The same bindings go into the existing SQL
generation and repair prompts. Before execution, an AST check requires the filter
to be on its measured field, and prevents missing filters or an OR branch such as
`... OR 1=1` from bypassing them. A wrong identifier filter enters the existing
bounded repair loop; repeated incorrect SQL fails without execution.

Ambiguous value meanings use the existing ownership-bound, expiring clarification
sessions. Values appearing as both an identifier and an attribute require a
choice unless the field was explicit. Equivalent references along approved key
domains are grouped rather than inventing another name-vs-ID choice. Repeated bare
attribute values with different identifiable records offer individual records or
all matching records. Choices are recomputed against current owned data on resume;
client-supplied candidate IDs cannot introduce arbitrary SQL or foreign data.

Dataset/relationship/value clarification can chain through the same chat UI.
Queries with measured filters use the existing generative path so the limited
structured metric planner cannot discard those filters. Ungrounded metric and
sales clarification regressions remain covered by the full suite.

No person names, physical column names, or the particular "bought by" wording are
special cases in application logic. The binding result depends on schema metadata,
measured values and approved paths. General English scaffolding and identifier
pluralization rules are used to distinguish question syntax from candidate values.

## Actual results

Full command: `python -m unittest discover -s backend/tests -q`

**115 backend tests passed**, including 10 new grounding tests. `npm run build`
and `git diff --check` passed. Existing dependency deprecation warnings remain.

The new isolated fixtures deliberately use misleading surrogate `id` values on
both tables while the approved join is CustomerID. Actual parsing, schema/value
lookup, source/path resolution, SQL guards and execution run with mocked LLM
responses. SQLite renders validated MySQL ASTs in its own dialect for apostrophe
escaping; this is test-only, not a production executor change.

- Three stored names, five question variants each: 15 equivalent-result cases.
  Alice returns Kettle/Book; Bob returns Shoes; the accented/apostrophe name
  returns Pen. Bare and explicit name wording produce equivalent row sets.
- Six additional cases rename the display field to PreferredLabel, product field
  to PurchasedArticle and approved key to PartyRef. Results remain equivalent.
- An injected wrong CustomerID filter is rejected, repaired once, then executed;
  repeated wrong filters never reach the query executor.
- A numeric key fixture with an existing key zero proves the guard rejects a name
  as a numeric-ID comparison rather than relying on MySQL's coercion behavior.
- When the same value exists as both a name and an ID, clarification is returned;
  selecting the display-field meaning resumes successfully. Explicit field wording
  remains unambiguous. Duplicate names offer identity/all-record choices.
- Tampered value-choice IDs and cross-owner clarification access are rejected.
- An injected `orders.id = customers.id` join is blocked even though both columns
  exist and would produce plausible but wrong matches. Correct CustomerID joins
  and renamed PartyRef joins are verified in result explanations.
- Omitted filters and OR-tautology bypasses are rejected.

An existing SQL-text assertion now compares case-insensitively because grounded
filters retain measured `Gold` spelling rather than blindly preserving model
`gold`. Its expected result rows and approved-path checks remain unchanged.

## Limits and rollout

This is exact stored-value grounding, not fuzzy person matching or a complete
natural-language parser. Candidate phrases are bounded to six words, numeric-only
bare tokens are not treated as names, lookup responses are bounded, and identity
choices show at most 12 individual records plus an all-matching option. Unsupported
predicate shapes can fail validation rather than guessing. Unseen/partial names
still depend on schema-based generation; the measured grounding does not claim to
infer a value absent from stored data.

Text lookups use database LOWER/equality semantics and may scan unindexed columns;
large-dataset latency and full Unicode collation behavior have not been benchmarked.
No immutable data snapshot is introduced; execution still validates relationship
freshness, while concurrent external changes retain the previously documented
limitations. No schema migration or new dependency is required.

Production MySQL, live Groq generation and Render rollout remain unverified.
All validation used isolated SQLite data and mocked AI. No production database
changes were made during implementation.

## Files changed

- `backend/app/services/value_grounding.py` (new)
- `backend/app/services/dataset_resolution.py`
- `backend/app/services/relationship_service.py`
- `backend/app/services/sql_generator.py`
- `backend/app/services/sql_regenerator.py`
- `backend/app/routes/ask.py`
- `backend/app/routes/metrics.py`
- `frontend/src/components/ChatBox.tsx`
- `backend/tests/test_value_grounding.py` (new)
- `backend/tests/test_connected_dataset_resolution.py`
- `docs/value-grounding.md` (new)
