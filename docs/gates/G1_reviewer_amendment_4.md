# G1 reviewer amendment 4 — tokenizer-state fidelity

Date: 2026-08-31 UTC

Status: **AMENDMENT-3 SYNTHETIC SMOKE QUARANTINED; PRODUCTION REVIEW FORBIDDEN**

Amendment ID: `LPS-G1-REVIEWER-AMENDMENT-4-20260831`

This amendment records a fail-closed diagnosis of the amendment-3 synthetic
schema-stress smoke. Production scores, rationales, acceptability decisions,
and downstream scientific outcomes were not inspected. Synthetic raw text was
inspected only to locate the structural decoding failure.

## Observed synthetic-smoke failure

- `primary_01`: 6 of 6 records accepted.
- `primary_02`: 6 of 6 records accepted.
- `primary_03`: 4 of 6 records accepted. The `persona_scalar` record ended
  with malformed JSON after 355 tokens when re-encoded by the frozen tokenizer.
  The `topic_suitability` record remained incomplete at the frozen 1024-token
  limit.
- `adjudicator_04` and `scenario_writer` were not run because the gate had
  already failed.

The machine-readable evidence record is
[`data/reports/g1_reviewer_smoke_failure_amendment_4_v2_3.json`](../../data/reports/g1_reviewer_smoke_failure_amendment_4_v2_3.json).

All three amendment-3 smoke ledgers are immutable historical evidence. No
accepted row may be reused, neither failed item may be retried under the same
contract, and the remaining reviewers may not be used to complete that smoke.

## Root cause

`lm-format-enforcer==0.11.2` builds a cached Transformers decoder that invokes
`tokenizer.decode()` without disabling the tokenizer's cleanup policy.
Falcon3's frozen ByteLevel tokenizer defaults
`clean_up_tokenization_spaces=True`, while the runner's final completion
decoder correctly uses `clean_up_tokenization_spaces=False`. Incremental
cleanup can drop or normalize whitespace and punctuation, causing LMFE's parser
state to diverge from the actual generated token stream. The malformed
`persona_scalar` output was replayed through the 0.11.2 token enforcer and was
incorrectly considered endable, confirming this execution-layer divergence.

This failure mode is documented by upstream
[issue #166](https://github.com/noamgat/lm-format-enforcer/issues/166) and its
[merged fix](https://github.com/noamgat/lm-format-enforcer/pull/172). The
upstream fix was merged after the pinned 0.11.2 release.

## Amended execution contract

The dependency remains frozen at `lm-format-enforcer==0.11.2`. After its
tokenizer trie is built once, the runner must replace only the cached
constraint decoder with an exact decoder that:

- calls `tokenizer.decode(..., clean_up_tokenization_spaces=False)`;
- does not strip the Unicode replacement character or any other character;
- is the same text policy used by the final completion decoder; and
- is recorded in every ledger as
  `exact_decode_cleanup_false_no_replacement_strip_v1`.

Missing decoder support, failure to install this policy, non-text decoding, or
provenance mismatch fails closed. This change does not repair model output,
coerce a value, relax a response schema, change a rubric, alter a threshold,
change any reviewer identity, or add a retry. Each assigned item still receives
exactly one `model.generate` call.

The amended registry
[`configs/g1_reviewer_registry_amendment_4_v2_3.yaml`](../../configs/g1_reviewer_registry_amendment_4_v2_3.yaml)
remains synthetic-only with `production_review_authorized: false`. The old
production registry, failed production ledgers, and amendment-3 smoke ledgers
remain preserved.

All five reviewer slots must pass a fresh smoke from zero under the amended
runner and the new ledger directory
`outputs/g1/reviewer_smoke_amendment_4`. Only then may promotion create a new,
separately named production registry. Production must also restart into a new
ledger directory; no historical ledger may be appended or resumed.
