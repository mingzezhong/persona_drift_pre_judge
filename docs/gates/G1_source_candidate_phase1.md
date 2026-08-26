# G1 source and candidate construction — phase 1

Status: **PREPARATION / not G1 PASS**

Protocol: restart-v2.3
Date: 2026-08-26 UTC

## Outcome

Official public source bytes are now pinned locally, and deterministic,
outcome-blind Persona and Topic candidate assets are tracked in Git. This phase
did not run a target model, judge behavior, inspect activations, select final
Personas/Topics, or generate scientific trajectories.

## Persona assets

Source: `anthropics/evals` at
`84fcc677e52e1902d696c32cd1a6b663e70d3993`, CC-BY-4.0.

- full source audit: 135 Persona JSONL files and 133,204 rows;
- recruitment shortlist: 24 source-backed candidate trait files, six in each of
  four provisional families;
- stable candidate items: 24,000;
- normalized duplicate groups: 152 / 315 rows;
- cross-trait duplicates: 148 / 307 rows;
- within-trait duplicates: 4 / 8 rows;
- globally unique candidates retained: 23,685;
- label-conflict duplicate groups: 29 / 62 rows.

Every member of every normalized duplicate group is excluded before future
definition/vector/held-out item-role assignment. The 24 traits and provisional
family mapping remain `DRAFT_NOT_FROZEN`; system prompts and item roles are G2,
not phase-1 artifacts.

## Topic assets

Sources:

- MMLU-Pro test split at `b189ec765aa7ed75c8acfea42df31fdae71f97be`,
  12,032 rows across 14 categories, no category quota, data license MIT;
- three Anthropic sycophancy/opinion files at `84fcc677...`, 30,051 raw rows,
  CC-BY-4.0.

The Anthropic source-specific DRAFT parser achieved structural coverage
30,051/30,051 and produced 158 logical candidates: NLP Survey 32, PhilPapers
109, Political Typology 17. Raw biography, affiliation, and explicit stance are
not treated as neutral Topic content. The cleaned anchors are adaptations and
still require blinded semantic review.

The 12,032 and 158 records are candidate universes, not final Topics. No final
36 IDs, 18/6/12 split, pilot assignment, or pressure-free 25-turn moves exist.

## Reproducibility

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python scripts/build_g1_persona_assets.py --no-download

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python scripts/build_g1_topic_assets.py --offline --no-write

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python scripts/validate_g1_assets.py --compact
```

The first command reproduces all four Persona manifests/reports byte-for-byte.
The second re-audits locked Topic source bytes without overwriting tracked
outputs. The validator must report `status=PREPARATION`, `ready=false`, and exit
2. Phase-1 artifact byte and canonical hashes are frozen in
`configs/g1_v2_3.yaml`.

## Remaining G1 blockers

1. Freeze the Persona semantic/independence/pressure-operability rubric, rater
   identities/revisions, blinded packets, agreement thresholds, and shortfall
   rule.
2. Adjudicate the provisional 24 candidates and freeze the final four-family
   true-trait sampling frame, or stop/amend on shortfall.
3. Freeze the Topic Suitability Screen and blinded selection protocol.
4. Select exactly 36 Topics under the 12 shared + 24 family-specific taxonomy,
   with a complete exclusion log.
5. Write and independently QA exactly 25 pressure-free topic moves per Topic.
6. Freeze the 18/6/12 split, six outcome-free QA assets, static Persona×Topic
   access policy, balance report, and complete G1 freeze attestation.

Changing only `implementation_status` cannot bypass these blockers:
`readiness_contract.inventory_scope=phase1_only`, execution authorization is
false, the freeze attestation is absent, and planned artifacts remain nonempty.
