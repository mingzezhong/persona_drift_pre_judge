# Data status

G1 phase 1 has downloaded and hash-locked official public source bytes under
Git-ignored `data/raw/`, then generated tracked source manifests, immutable
candidate item IDs, and aggregate audit reports. These assets remain
`PREPARATION`: no final Persona catalog, 36-topic bank, split, or scenario has
been frozen, and no target-model outcome has been observed.

Tracked phase-1 assets live in `data/manifests/` and `data/reports/`. Raw and
future processed corpora remain Git-ignored. Rebuild with
`scripts/build_g1_persona_assets.py --no-download` and
`scripts/build_g1_topic_assets.py --offline`; verify the inventory with
`scripts/validate_g1_assets.py`.

V2.3 keeps the V2.2 Persona hierarchy: behavioral family, independent persona
trait, prompt variant, and evaluation item.  Prompt variants and items are nested
records and never increase the reported persona count.  The endorsed sampling
direction is four families with 4--6 source-backed traits per family, but the
exact catalog is still open.

The adopted Scenario-first bank has 36 slots: 12 shared core topics (six
evidence-based and six opinion) plus 24 family-specific topics (six for each of
four behavioral families). The 14 MMLU-Pro categories form a candidate pool
with no category quota; Anthropic opinion items form the shared-opinion
candidate pool. Exact anchors, scenario subtypes, sources, and transformations
remain open at G1. PersonaGym is reserved for external generalization rather
than development.
A source is not usable until its license, upstream revision, file
hash, selected item IDs, and deterministic transformation are recorded.

Required tracked manifest fields include:

- entity level (`family`, `trait`, `prompt_variant`, or `evaluation_item`) and parent IDs;
- persona generalization role (observed wording, unseen wording, unseen trait, or unseen family);
- evaluation-item role (trait definition, vector extraction, or held-out validation);
- source name, canonical URL, license, and upstream revision;
- downloaded-file SHA256 and retrieval date;
- immutable source item ID and transformed topic ID;
- `topic_scope` (`shared_core` or `family_specific`), scenario family/subtype, and
  eligible behavioral family;
- `topic_move_sha256s`, `topic_content_canonicalization_version=restart-v2.3-topic-move-root-v1`, and
  globally unique `topic_content_root_sha256`;
- `split_algorithm_version`, `split_seed`, `balance_diagnostics_sha256`,
  `topic_split_plan_manifest_sha256`, and `assignment_outcome_blind=true`;
- Topic Suitability Screen version, blinded ratings, aggregation, eligibility
  decision, and exclusion reason;
- persona, pressure-family, topic split, Persona holdout, and phase-access
  eligibility metadata;
- `turn_composition_version`, `composed_user_turn_sha256s`, and
  `pre_response_full_prompt_sha256s` (each tuple contains 25 turn-aligned hashes);
- transformation code revision and output hash.

The Persona and Topic axes are simultaneous access controls: holding out a
wording, trait, or family never permits a topic to cross its partition, and a
Topic holdout never permits Persona outcomes to cross their holdout. Shared
topics support cross-family comparisons; family-specific topics support only
their eligible family within-family claims. A 25-turn scenario stores 25
content-only topic-move IDs separately from 25 pressure-template IDs.

The exact 36-topic `18 development / 6 calibration / 12 untouched test` IDs
and exact six pilot-asset IDs must be frozen before G1 can pass. All six pilot
assets (two shared plus one family-specific per family) support outcome-free QA.
After G2 freezes one held-out family, outcome-bearing G5 uses only five logical
assets: two shared plus one specific asset per Development family. The held-out
family-specific pilot asset never enters `X_pilot` and exposes no outcome. Each Topic must
have exactly 25 pairwise-unique move-content hashes. The content root is derived
only from their ordered canonical serialization under one frozen bank-wide
version `restart-v2.3-topic-move-root-v1` and must be globally unique across all 36 topics; duplicate roots,
cross-partition reuse, or replay mismatch fail closed. Topic IDs—not individual
prefixes or forks—are the outer split unit. G1 freezes only static Topic
eligibility/split/access policy; G2 freezes Persona holdouts, and each outcome
phase requires a separately signed `X_phi` exposure manifest. Held-out-family
schedules use only G4 outcome-blind calibration plus a pre-reveal frozen
cross-Development-family transfer/fallback rule; no executable rule means stop.

## Phase-1 source licensing and changes

- MMLU-Pro data are pinned by full Hugging Face revision and recorded as MIT
  licensed. The validation split is audited but excluded from the candidate
  universe.
- Anthropic model-written evals are pinned at commit
  `84fcc677e52e1902d696c32cd1a6b663e70d3993` under CC-BY-4.0. Attribution is
  to Anthropic's `evals` repository. Persona records preserve source provenance;
  Topic opinion records are a DRAFT adaptation that deterministically removes
  generated biography, affiliation, and explicit user stance before logical
  clustering. That modification is recorded in the manifests and must complete
  blinded review before scientific use.

The exact URLs, revisions, file hashes, Git blobs, row counts, and transformation
versions are authoritative in `data/manifests/public_sources_*_v2_3.yaml`.
