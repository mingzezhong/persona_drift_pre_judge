# G1 reviewer amendment 5 — bounded rationale completion

Date: 2026-08-31 UTC

Status: **AMENDMENT-4 SYNTHETIC SMOKE QUARANTINED; PRODUCTION REVIEW FORBIDDEN**

Amendment ID: `LPS-G1-REVIEWER-AMENDMENT-5-20260831`

This amendment records the fail-closed amendment-4 synthetic smoke. No
production score, rationale, decision, or downstream scientific outcome was
inspected. Synthetic fields were inspected only for structural lengths and
termination evidence.

## Observed synthetic-smoke failure

`primary_03` produced 5 accepted records and 1 invalid record. The decoder
fidelity change from amendment 4 eliminated the previous malformed
`persona_scalar` failure. The remaining `topic_suitability` output was byte
identical to its amendment-3 output: it stayed inside the rationale string and
exhausted the frozen 1024-token generation budget before emitting an exact JSON
value.

The accepted `persona_scalar` rationale contained 974 characters. The failed
`topic_suitability` output contained 1633 characters, while amendment 4
allowed a rationale of up to 2048 characters. The format enforcer therefore
had no authority to close that string before the generation budget ended.

The machine-readable evidence record is
[`data/reports/g1_reviewer_smoke_failure_amendment_5_v2_3.json`](../../data/reports/g1_reviewer_smoke_failure_amendment_5_v2_3.json).

The amendment-4 ledger is immutable and quarantined. No accepted row may be
reused, the failed item may not be rerun under the same contract, and no other
reviewer may be added to complete that smoke.

## Amended execution contract

The frozen free-text bound for every `rationale` field is reduced from 2048
to 1024 characters. The existing bounds for `definition`,
`scenario_summary`, and `move_text` are unchanged. The generation budget
remains 1024 tokens.

This is a prospective schema constraint: it limits the next-token set and
forces the model to close the string at the bound. It does not truncate,
repair, coerce, parse-relax, or retry any generated output. It does not change
the rubric, prompt, threshold, task assignment, model identity, model revision,
or greedy decoding parameters. Each item still receives exactly one
`model.generate` call and must independently validate as one exact JSON
object.

The amendment-5 registry
[`configs/g1_reviewer_registry_amendment_5_v2_3.yaml`](../../configs/g1_reviewer_registry_amendment_5_v2_3.yaml)
remains synthetic-only with `production_review_authorized: false`. The LMFE
version and exact decoder policy from amendment 4 remain frozen.

All five reviewer slots must pass a fresh smoke from zero under the amended
runner in `outputs/g1/reviewer_smoke_amendment_5`. Only then may promotion
create a separately named amendment-5 production registry. Any future
production review must also write to the new amendment-5 ledger directory; no
historical production or smoke ledger may be appended or resumed.
