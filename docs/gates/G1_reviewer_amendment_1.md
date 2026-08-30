# G1 reviewer amendment 1 — primary_03 replacement

Date: 2026-08-30 UTC

Status: **ADOPTED FOR A NEW SYNTHETIC SMOKE; PRODUCTION REVIEW REMAINS FORBIDDEN**

Amendment ID: `LPS-G1-REVIEWER-AMENDMENT-1-20260830`

This amendment changes only the frozen `primary_03` reviewer identity in
[`configs/g1_reviewer_registry_v2_3.yaml`](../../configs/g1_reviewer_registry_v2_3.yaml).
It does not authorize production review, promote the registry, or claim that
the replacement reviewer has passed the synthetic smoke.

## Failed OLMo synthetic smoke

The frozen OLMo `primary_03` candidate
`allenai/OLMo-2-1124-7B-Instruct` at revision
`470b1fba1ae01581f270116362ee4aa1b97f4c84` accepted only **3 of 6** assigned
synthetic-smoke items. The observed failure types were:

- a doubly escaped enum value;
- an omitted required field;
- an unquoted JSON enum value.

These are model-output contract failures. They are not evidence for changing
the frozen output schema or parser.

## Fail-closed response

Parser relaxation, output repair, and retry-until-valid are explicitly
forbidden. A malformed response remains a failed attempt in the append-only
ledger. The replacement must pass the same frozen prompts, schemas, greedy
decoding contract, and synthetic packet without output-specific accommodation.

## Frozen replacement

`primary_03` is replaced with:

- `model_id`: `01-ai/Yi-1.5-9B-Chat`
- `model_revision`: `286ee8b32be4000c8fb27f9a2565d8a3659c61f8`
- `base_model_family`: `yi_llama`
- `license_spdx`: `Apache-2.0`

The `yi_llama` family is distinct from the frozen `qwen2`, `granite`, `phi3`,
and `mistral` families in the five-slot panel. The registry remains
`production_review_authorized: false`. Only a fresh synthetic smoke for the
amended exact registry can provide evidence for later promotion.
