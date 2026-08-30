# G1 reviewer amendment 2 — primary_03 replacement

Date: 2026-08-30 UTC

Status: **ADOPTED FOR A NEW SYNTHETIC SMOKE; PRODUCTION REVIEW REMAINS FORBIDDEN**

Amendment ID: `LPS-G1-REVIEWER-AMENDMENT-2-20260830`

This amendment supersedes amendment 1 only for the frozen `primary_03`
reviewer identity. It changes
[`configs/g1_reviewer_registry_v2_3.yaml`](../../configs/g1_reviewer_registry_v2_3.yaml)
but does not authorize production review, promote the registry, or claim that
the replacement reviewer has passed the synthetic smoke.

## Failed Yi synthetic smoke

The frozen Yi `primary_03` candidate `01-ai/Yi-1.5-9B-Chat` at revision
`286ee8b32be4000c8fb27f9a2565d8a3659c61f8` accepted **5 of 6** assigned
synthetic-smoke items. The failed item emitted integer score values as JSON
strings instead of JSON integers.

This is a model-output contract failure. It is not evidence for changing the
frozen output schema, parser, or prompt.

## Fail-closed response

Parser coercion, prompt accommodation, and retry are explicitly forbidden. A
malformed response remains a failed attempt in the append-only ledger. The
replacement must pass the same frozen prompts, schemas, greedy decoding
contract, and synthetic packet without model-specific accommodation.

## Frozen replacement

`primary_03` is replaced with:

- `model_id`: `tiiuae/Falcon3-10B-Instruct`
- `model_revision`: `8799bc6aec0152757221dc6b272d824642db6202`
- `base_model_family`: `falcon3`
- `license_spdx`: `LicenseRef-TII-Falcon-LLM-2.0`

The `falcon3` family is distinct from the frozen `qwen2`, `granite`, `phi3`,
and `mistral` families in the five-slot panel. The registry remains
`production_review_authorized: false`. Only a fresh synthetic smoke for the
amended exact registry can provide evidence for later promotion.
