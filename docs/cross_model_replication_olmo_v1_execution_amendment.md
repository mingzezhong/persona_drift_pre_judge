# OLMo cross-model replication: execution amendment v2

Date: 2026-08-18 (AEST)

## Reason for the amendment

The frozen replication pipeline originally assigned all three topics for one
persona axis to a single four-hour GPU job. Jobs `52719.hpc-head01` and
`52720.hpc-head01` demonstrated that this execution unit could not finish within
the queue limit: at cancellation, the immutable partial files contained 19 and
17 complete trajectories, respectively, out of 120 planned per axis. The
corresponding probe partials contained 117 and 106 records; the extra records
belong to incomplete trajectories.

Only scheduler status, elapsed time, record counts, and generation progress
identifiers were inspected. No generated response text, activation value,
persona score, judge output, drift outcome, condition comparison, or hypothesis
test was inspected before this amendment.

## Execution-only change

The generation workload is partitioned into the six Cartesian cells formed by:

- two frozen axes: `cautious_risk_seeking` and `independent_sycophantic`;
- three frozen topics: `municipal_water_reuse`, `coastal_ferry_ticketing`, and
  `regional_food_cold_chain`.

Each cell contains all four frozen conditions and all ten frozen seeds, for 40
trajectories, 1,000 main turns, and 240 probes. The six complete shards are
validated and merged in the original configured axis/topic order before the
unchanged review, judging, and analysis stages run.

The two canceled job logs also show that both simultaneous jobs selected
physical GPU 0 on the same two-GPU node. Execution v2 therefore holds a
per-user, node-local `flock` for the selected physical GPU for the lifetime of
each generation job. Concurrent replication jobs on the same node consequently
select different GPUs before setting `CUDA_VISIBLE_DEVICES`.

The following remain exactly unchanged:

- target model and pinned revision;
- persona-vector file, hash, layer, and construction protocol;
- prompts and template;
- axes, topics, conditions, seeds, number of turns, and checkpoints;
- generation parameters and deterministic seed construction;
- generation-quality thresholds;
- blinded three-judge measurement and frozen scoring model;
- confirmatory estimands, bootstrap procedure, thresholds, and decision rule.

Partitioning does not reuse partial generations. All 240 trajectories are
regenerated from the frozen deterministic seeds. The `52719`/`52720` partial
files and logs are retained under
`outputs/cross_model_replication/olmo_v1/failed_attempts/52719_52720_walltime_risk/`
and are excluded from merging and analysis.

## New integrity controls

The partitioned generator rejects topics outside the frozen config and records
the selected topic in each run summary. The partitioned merger requires exactly
40 trajectories and 240 probes per axis-topic cell, validates axis/topic
identity, trajectory length, config hashes, run-summary counts, file hashes,
global ID uniqueness, and complete checkpoint coverage. A separate
`execution_v2_protocol_files.sha256` manifest freezes all execution-v2 files
without modifying the original protocol manifest.
