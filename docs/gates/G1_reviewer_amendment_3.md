# G1 reviewer amendment 3 — production failure and schema-constrained restart

Date: 2026-08-31 UTC

Status: **PRODUCTION RATINGS QUARANTINED; NEW PRODUCTION REVIEW FORBIDDEN**

Amendment ID: `LPS-G1-REVIEWER-AMENDMENT-3-20260831`

This amendment records a fail-closed review of ledger status and error classes
after the first production attempt. No semantic score, rationale, acceptability
decision, or downstream scientific outcome was inspected. The review examined
only record counts, record status, error category, ledger SHA256, and chain
head.

## Observed production failures

- `primary_01`: 27 records, 26 accepted statuses, 1 invalid status. Ledger
  SHA256 `08793e75de9da795afa3277b3aa90311443609e72b7ee09028933382588b0910`;
  chain head `9ee72f1b63a2ac59c741e629e1e51bd737d6633ef7d9bc561b455092180f3345`;
  error class: integer type violation.
- `primary_02`: 27 records, 24 accepted statuses, 3 invalid statuses. Ledger
  SHA256 `18628acf2a1379250b0fcd30ad0c30c39f5d53d15674c1b4944710c8ac1032da`;
  chain head `d9427464ce6bc0d19f13f1777e26c343023b4df52295247c6d7203491cdd7850`;
  error classes: two integer type violations and one duplicate JSON key.

The machine-readable record is
[`data/reports/g1_reviewer_production_failure_amendment_3_v2_3.json`](../../data/reports/g1_reviewer_production_failure_amendment_3_v2_3.json).

## Quarantine and immutable history

The prior production registry and both failed ledgers are immutable historical
evidence. Every rating row from the failed production attempt is quarantined.
No accepted row may be reused, no failed item may be rerun alone, and no
partial ledger may be resumed. A ledger containing `generation_error` or
`rejected_invalid_output` for the same review contract must fail before model
loading.

Retry, repair, coercion, parser relaxation, and prompt accommodation are
forbidden. Each assigned item receives exactly one `model.generate` call.

## Amended execution contract

The amended registry is frozen only for a new synthetic schema-stress smoke and
keeps `production_review_authorized: false`. It requires
`lm-format-enforcer==0.11.2` for every real generation. Missing or mismatched
dependencies and constraint initialization failures stop before generation.

For each item, the frozen response schema is specialized without changing the
rubric, thresholds, task meaning, or reviewer identities: anonymous IDs become
input-specific `const` values, family options become an input-specific `enum`,
0–2 scores become exact integer enums, and frozen maximum lengths bound free
text. The canonical effective-schema SHA256 is recorded in the ledger.

The old production registry remains preserved but cannot authorize the amended
runner because its runner implementation hash binds the superseded bytes. A
fresh synthetic schema-stress smoke and a new promotion are required before any
new production attempt. `ratings_generated`, `all_required_reviews_complete`,
and G1 PASS remain false.
