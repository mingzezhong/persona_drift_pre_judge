# Experiment ledger — restart v2

This ledger begins at the v2 restart. The complete prior ledger remains
recoverable from Git tag `pre-restart-v1-20260824`; see
[`legacy_recovery.md`](legacy_recovery.md).

No target-model generation, behavior-judge run, pressure calibration, dose
pilot, forecasting fit, randomized fork, or confirmatory analysis has been
executed. Outcome-blind local reviewer execution is recorded below.

| Date (UTC) | Gate/stage | Status | Evidence |
|---|---|---|---|
| 2026-08-24 | Legacy tracked freeze | PASS | Annotated tag `pre-restart-v1-20260824` pushed at commit `447a72058bd350aec21edb9405c9720a78d561a4` |
| 2026-08-24 | Non-Git archive | PASS | 974 files / 820,269,820 bytes moved read-only to ignored `legacy_artifacts/pre_restart_v1_20260824/`; payload SHA256 verification passed |
| 2026-08-24 | `G0` archive and provenance | **PASS** | Three authority-file hashes verified by `docs/source_materials.sha256`; Git tag and artifact manifest verified |
| 2026-08-24 | V2 protocol preparation | COMPLETE | Amendment, formal protocol, machine-readable contract, fail-fast schema, and tests added; G1–G8 remain open |
| 2026-08-24 | Restart-tree validation | PASS | 32 tests passed; source checksums, YAML/code contract, relative links, secret scan, and `git diff --check` passed |
| 2026-08-25 | V2.1 method-scope decision | COMPLETE | Conditional/Normalizing Flow, Flow Matching, and all flow-based density/trajectory models excluded from every V2 stage and model role; immutable G0 source files retained unchanged as provenance |
| 2026-08-25 | V2.1 method-scope validation | PASS | 38 tests passed, including project-wide scope, active-config, operational-document, dependency, identifier, and production-source exclusion checks |
| 2026-08-25 | README GitHub math rendering | PASS | Legacy `\(...\)` / `\[...\]` delimiters converted to GitHub-compatible `$...$` / `$$...$$`; GitHub Markdown API rendered all 11 formulas; delimiter regression checks added; 41 tests passed |

| 2026-08-25 | V2.2 Persona/Topic scope amendment | COMPLETE | Discussion provenance hashed; hierarchical Persona ontology adopted as an endorsed direction; Flat-4 counts retired; 30-topic contract retained at that revision (later superseded by V2.3); exact G1/G2 assets and revised sample size remain open |
| 2026-08-25 | V2.2 schema validation | PASS | Final full suite: `51 tests passed in 17.17s`; catalog-backed record validation, uniform Anthropic stance policy, open phase-specific seed contract, and hierarchical/cold-start statistical contract validated; source-material SHA256 and `git diff --check` passed |
| 2026-08-25 | V2.3 Scenario-first Topic amendment | COMPLETE | `topic的优化.md` hashed as decision provenance; adopted 12 shared + 24 family-specific slots, 18/6/12 split, and 2-shared-plus-4-family pilot composition; exact scenario families/items/templates/screen implementation remain G1 OPEN |
| 2026-08-26 | V2.3 documentation validation | PASS | All five source-material SHA256 checks passed; `git diff --check` passed; README math regression: `3 passed in 7.26s` |
| 2026-08-26 | V2.3 machine-contract validation | PASS | Byte-identical final-tree mirror: `64 tests passed in 0.84s`; CETUS shared-home rerun entered filesystem I/O wait and was terminated without assertion output; source/config/test SHA256 matched; `git diff --check` passed |
| 2026-08-26 | V2.3 Topic identity/access audit | COMPLETE | Unified machine scope as `topic_scope`; froze pairwise-unique move hashes, canonical globally unique content roots, split provenance fields, full-prompt composition hashes, gate-specific exposure timing, and six-QA-assets/five-outcome-assets heldout-family policy; no experimental data generated |
| 2026-08-26 | G1 public-source acquisition and candidate construction | PREPARATION | Pinned Anthropic evals and MMLU-Pro source revisions/bytes/licenses; generated 24-trait / 24,000-item Persona recruitment assets, 12,032 MMLU candidate IDs, and 158 DRAFT logical Anthropic anchors from 30,051 raw rows; no target-model execution or outcome-based selection |
| 2026-08-26 | G1 Persona duplicate audit correction | PASS | Global normalized dedup now excludes all 152 groups / 315 rows, including 4 within-trait groups / 8 rows; 23,685 globally unique candidates remain; offline rebuild was byte-identical |
| 2026-08-26 | G1 phase-1 validation | PASS (phase only) | Full suite: 99 passed in 151.14s; seven artifact byte/canonical hashes and contents passed; validator intentionally returned PREPARATION, ready=false, exit 2 with only PREPARATION_STATUS failing; status-only READY forgery rejected; source-material checksums, secret scan, and git diff --check passed |
| 2026-08-26 | G1 phase-2 outcome-blind review preparation | PREPARATION | Protocol and anonymous input packets materialized: Persona 2,304 rows (24 × 96), MMLU-Pro 12,032 candidates, and Anthropic 158 logical candidates. No ratings, final catalogs, scenarios, split/freeze attestation, target-model outcome, or G1 PASS exists; exact reviewer registry and synthetic smoke remain open. |
| 2026-08-26 | G1 phase-2 packet validation | PASS (preparation only) | Full suite: 142/142 passed (exit 0); Persona and Topic deterministic `--verify-only` checks passed; five source-material checksums passed. The aggregate G1 validator intentionally remained `PREPARATION`/`ready=false` with 30/31 checks passing and only `PREPARATION_STATUS` open (expected exit 2). |
| 2026-08-31 | G1 reviewer amendment-5 synthetic smoke and promotion | PASS | Five frozen reviewer/writer slots accepted 23/23 synthetic tasks with zero invalid outputs; production registry `configs/g1_reviewer_registry_production_amendment_5_v2_3.yaml` was promoted and hash-bound. |
| 2026-08-31 | G1 production Persona scalar review | **FAIL CLOSED — RECALIBRATION REQUIRED** | Three independent primaries accepted 81/81 production records, but blind-repeat exact rating-vector agreement was 6/9 = 0.667, below the frozen 0.85 minimum. Pair review was not started; the mechanically generated pair packet was quarantined. Evidence: `data/reports/g1_persona_scalar_blind_repeat_failure_v2_3.json`. |

Public-data licenses/item IDs remain a `G1` requirement. Exact model revisions,
license/access, chat templates, and hook equivalence remain `G3` requirements.
Neither is implied by the `G0` pass.
