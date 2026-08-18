# OLMo QC-remediated formal cross-model replication preregistration

Date frozen: 2026-08-18 (Asia/Shanghai)

## Status and decision boundary

This document freezes a fresh, confirmatory OLMo cross-model replication before
any output is generated under
`outputs/cross_model_replication/olmo_qc_v1`. The earlier `olmo_v1` formal
generation attempt is immutable, failed its predeclared generation-quality gate,
and is excluded. No response or persona outcome from that attempt is reused.

The engineering sequence selected the least-intervention prompt variant
(`minimal`) and then passed the full prompt-salience pilot. The authorizing pilot
summary is
`outputs/cross_model_replication/olmo_prompt_salience_pilot_v1/summary.json`,
SHA256
`458caf63b0b9c27dee290f316b2184ff5fb99e22e8cbf5b36cacbacac907d565`.
It records 48 trajectories, 1,200 main responses, 288 probes, all 13 quality
checks passing, and no manual response-text or persona-outcome inspection.

The pilot data are engineering data only. They will not be pooled with this
formal replication and will not enter any confirmatory persona analysis.

## Frozen scientific design

The scientific design, persona vectors, activation representation, measurement
model, three judge families, estimands, bootstrap, drift definition, and primary
decision criteria are unchanged from `cross_model_replication_olmo_v1`.

- Target: `allenai/OLMo-2-1124-7B-Instruct` at revision
  `470b1fba1ae01581f270116362ee4aa1b97f4c84`.
- Axes: `independent_sycophantic` and `cautious_risk_seeking`.
- Conditions: neutral, gradual pressure, abrupt pressure, and topic shift.
- Topics: municipal water reuse, coastal ferry ticketing, and regional food cold
  chain.
- Fresh reserved seeds: 701 through 710. They do not overlap the full pilot
  seeds 631–632 or the excluded earlier formal seeds 401–410.
- Design size: 240 trajectories, 6,000 main turns, and 1,440 isolated probes.
- Checkpoints: turns 0, 5, 10, 15, 20, and 25.
- OLMo persona vectors remain SHA256
  `a412c5b8f0b9c37d8f4d0881e6bfbfcca2c743ae2c47318cb963a24c369ef12f`
  with reference layer 20.
- The anchored scoring model remains SHA256
  `1933da8d7768e3aa8f42718a31ce9100f8eeb36435bc53995afb3088918f2b16`.

The new judge configuration changes only input, blinded review-sheet, and output
paths to the independent `olmo_qc_v1` root. Judge identities, revisions,
inference settings, rubric, and blinding rules remain unchanged.

## Frozen generation-only remediation

The only substantive changes from the earlier formal generation protocol are
the engineering controls authorized before this run:

- selected `minimal` prompt-salience template, SHA256
  `bfa1391c51d020872852eb824e2a98a557357d60e0d31f8f238fce43334d5415`;
- maximum 384 and minimum 24 generated tokens;
- temperature 0.7, top-p 0.9, and sampling enabled;
- generated-token-only repetition penalty 1.10;
- generated-token-only no-repeat 4-gram constraint.

The repetition controls are isolated to newly generated tokens and do not
penalize prompt history. No persona vector, probe, outcome rule, or statistical
criterion is changed.

## Frozen generation-quality gate

Persona judging is forbidden unless the merged formal generation passes every
following check. Equality at a boundary passes.

- combined, main, and probe capped rate: at most 10%;
- each response-type × axis × condition × topic capped rate: at most 20%;
- each topic overall capped rate: at most 10%;
- overall duplicate-4-gram-ratio-at-least-0.15 rate: at most 5%;
- each response-type × axis × condition × topic duplicate rate: at most 10%;
- overall format compliance: at least 85%;
- each response-type × axis × condition × topic format compliance: at least 75%;
- complete-sentence ending: at least 95%;
- list-or-heading rate: at most 5%;
- role-start rate: at most 2%;
- all forbidden text marker counts must be zero.

These are the same thresholds used to authorize the formal run. Quality metrics
are computed automatically; response text is not manually inspected before the
gate decision. A failed gate stops the chain before review-sheet creation and
persona judging. The failed formal generation remains reportable as a quality
failure but produces no confirmatory persona conclusion.

## Execution and analysis lock

The run is partitioned into six immutable axis × topic GPU shards. A CPU merge
job verifies hashes, design coverage, counts, and the full quality gate. Only an
`afterok` downstream dispatcher may launch the three blinded AI judges. The
confirmatory analysis runs only after all three judges complete successfully.

The final persona claims use the already-frozen anchored posterior and sustained
drift rules. Per-judge raw-threshold sensitivity remains secondary, and the
frozen Qwen forecast transport remains exploratory. No thresholds, seeds,
prompts, judge identities, exclusions, or primary criteria may be changed after
submission in response to formal outputs.

Exact source hashes are recorded in
`docs/cross_model_replication_olmo_qc_v1_protocol_files.sha256` and copied into
the output root at submission.
