# G1 reviewer amendment 6 — prospective scalar recalibration

Date: 2026-08-31 UTC

Status: **FROZEN FOR FRESH SYNTHETIC SMOKE; production review remains unauthorized**

## Trigger

The first production Persona scalar cycle completed 81/81 valid records, but
the frozen blind-repeat exact-rating-vector agreement gate failed: 6/9 =
0.667, below 0.85. The immutable evidence is recorded in
`data/reports/g1_persona_scalar_blind_repeat_failure_v2_3.json`. Pair review
did not start, and its mechanically prepared packet was quarantined.

The frozen Phase-2 protocol permits one recalibration cycle, requires the
same 24 candidates, and forbids changing scored candidates. This amendment is
that single prospective recalibration; it is not a second chance to select
different candidates or lower the threshold.

## Non-semantic identifier correction

The original scalar prompt exposed `input_id` and `candidate_anonymous_id` and
required the model to emit the candidate alias before its scores. Blind-repeat
rows intentionally use different administrative aliases, so identical semantic
evidence reached the greedy decoder through different token contexts.

For `persona_scalar` only, the amended runner:

1. keeps the complete input row, item ID, packet SHA256, line number, and row
   SHA256 in the append-only ledger;
2. renders only `statements` into the model-visible input;
3. removes the administrative candidate alias from the model response schema;
4. continues to bind every response to its original anonymous input through
   immutable ledger provenance.

Thus a base row and its blind repeat have byte-identical model-visible messages
while remaining separate, auditable ledger items. No source identity or repeat
map is exposed to a reviewer.

## Frozen non-changes

This amendment does not change the same 24 candidates, their 96 statements,
the three primary model IDs or revisions, the seven rubric dimensions or
anchors, score scale, acceptance rules, 0.85 repeat-agreement threshold,
decoding parameters, repeat schedule, pair/family rules, Topic protocol, or
target-model prohibition. It does not repair, coerce, average, overwrite, or
reuse any prior rating.

## Authorization and stopping rule

`configs/g1_reviewer_registry_amendment_6_v2_3.yaml` remains synthetic-only
with `production_review_authorized: false`. All five exact slots must complete
a fresh smoke under the amended runner/prompt contract, and a new promotion
must authorize production before recalibration begins.

The one recalibration cycle must write three new append-only ledgers. All 24
original candidates and the frozen blind-repeat schedule are rerun; none of the
81 earlier records may be reused. Pair review must not start unless the new
cycle reaches at least 0.85 exact rating-vector agreement and all other scalar
agreement gates pass. Failure after this one recalibration cycle stops G1 for a
new amendment, exactly as frozen in `configs/g1_phase2_v2_3.yaml`.

Synthetic smoke, promotion, or recalibration does not authorize target-model
execution and cannot itself make G1 pass.
