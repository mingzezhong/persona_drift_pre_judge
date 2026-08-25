# Experiment ledger — restart v2

This ledger begins at the v2 restart. The complete prior ledger remains
recoverable from Git tag `pre-restart-v1-20260824`; see
[`legacy_recovery.md`](legacy_recovery.md).

No v2 model generation, behavior-judge run, pressure calibration, dose pilot,
forecasting fit, randomized fork, or confirmatory analysis has been executed.

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

| 2026-08-25 | V2.2 Persona/Topic scope amendment | COMPLETE | Discussion provenance hashed; hierarchical Persona ontology adopted as an endorsed direction; Flat-4 counts retired; 30-topic contract retained; exact G1/G2 assets and revised sample size remain open |
| 2026-08-25 | V2.2 schema validation | PASS | Final full suite: `51 tests passed in 17.17s`; catalog-backed record validation, uniform Anthropic stance policy, open phase-specific seed contract, and hierarchical/cold-start statistical contract validated; source-material SHA256 and `git diff --check` passed |

Public-data licenses/item IDs remain a `G1` requirement. Exact model revisions,
license/access, chat templates, and hook equivalence remain `G3` requirements.
Neither is implied by the `G0` pass.
