# OLMo full prompt-salience pilot v1 results

Date: 2026-08-18 (AEST)

## Decision

The clean full pilot passed all 13 frozen generation-quality checks. The
QC-remediated formal OLMo replication is therefore authorized to use the
selected `minimal` prompt-salience template, generated-token-only repetition
penalty 1.10, generated-token-only no-repeat four-gram size 4, and the 384-token
cap with untouched formal seeds 701--710.

No response text was manually inspected and no persona outcome, activation
effect, drift rate, condition contrast, or hypothesis test was evaluated in
this quality pilot.

## Execution integrity

Validation job `54333.hpc-head01`, all six axis-by-topic generation jobs
`54334`--`54339`, and merge-analysis job `54340.hpc-head01` completed with exit
status 0. The clean run contains exactly 48 trajectories, 1,200 main responses,
and 288 probes. No data from invalidated jobs `54277`--`54284` was reused.

The final summary is
`outputs/cross_model_replication/olmo_prompt_salience_pilot_v1/summary.json`,
SHA256 `458caf63b0b9c27dee290f316b2184ff5fb99e22e8cbf5b36cacbacac907d565`.

## Frozen-gate evidence

- Overall, main, probe, topic, and topic-cell max-length rates were all 0%.
- Overall and every topic-cell high duplicate-four-gram rate were 0%.
- Joint 2--4 sentence and 30--70 word compliance was 94.96% overall, 94.50%
  for main responses, and 96.88% for probes, above the frozen 85% overall gate.
- All 48 response-type x axis x condition x topic cells met the frozen 75%
  minimum. The minimum was exactly 75% for cautious/topic-shift/municipal-water
  probes, so this cell passed without spare margin.
- Complete-sentence endings were 100%; list/heading and repeated-sentence rates
  were 0%; role-start and every forbidden-marker check passed.
- Topic-level joint format compliance was 95.77% for coastal ferry ticketing,
  93.75% for municipal water reuse, and 95.36% for the regional cold chain.

## Interpretation boundary and next step

This result establishes cross-topic robustness of the generation-quality
remediation under pilot seeds 631--632. It does not establish persona drift or
replicate the scientific hypothesis. The next eligible step is to separately
freeze and submit a fresh formal OLMo replication using seeds 701--710 and the
unchanged scientific measurement and analysis protocol.
