# Latent Persona Seismograph: research specification v0.1

## Primary claim

Pre-response activation trajectories contain incremental information, beyond
observable dialogue history, for forecasting sustained persona inconsistency in
future turns. This signal can trigger selective interventions that reduce drift
at a fixed intervention budget.

The project does not claim that an LLM possesses a human-like latent personality
or a persistent hidden mental state between API calls.

## Research questions

- **RQ1 — Representation:** Does an independently extracted persona direction
  track measured trait expression during multi-turn interaction?
- **RQ2 — Forecasting:** Among checkpoints that have not yet drifted, can
  pre-response activation features predict drift within the next `H` turns?
- **RQ3 — Incremental value:** Do those features improve over a strong model
  using the same observable dialogue history?
- **RQ4 — Intervention:** At the same intervention rate, does an
  activation-triggered policy reduce cumulative drift more than periodic or
  random intervention without reducing task utility?

RQ2 and RQ3 are the paper's primary questions. RQ1 is a prerequisite and RQ4 is
a downstream application.

## Scope of the pilot

### Target model

`Qwen/Qwen2.5-7B-Instruct` at commit
`a09a35458c702b33eeacc393d103063234e8bc28` in BF16. See
`docs/model_selection.md`.

### Persona axes

1. independent versus sycophantic;
2. cautious/safety-conscious versus risk-seeking.

Schwartz/PVQ measurements are secondary validation surfaces, not the sole ground
truth. The initial pilot does not model all Schwartz quadrants.

### Dialogue conditions

- `neutral`: no pressure against the assigned persona;
- `gradual_pressure`: contrary pressure increases over turns;
- `abrupt_pressure`: strong contrary pressure begins at a fixed turn;
- `topic_shift`: topic changes without contrary persona pressure.

The topic-shift condition is a hard negative for separating topical activation
change from persona drift. The controlled pilot is dyadic. Free-form group
interaction is added only after the controlled signal passes the go/no-go tests.

### Pilot size

- 2 persona axes;
- 4 conditions;
- 3 topics;
- 10 random seeds per cell;
- 25 dialogue turns;
- checkpoints every 5 turns;
- 4 future rollouts per selected checkpoint where affordable.

This gives 240 base trajectories before forked rollouts. A smaller smoke run
uses one seed per cell.

## Measurement protocol

At checkpoint `t`, clone the conversation state and administer a fixed probe
battery in an isolated branch. Probe responses never enter the main trajectory.

Each checkpoint records three measurement surfaces:

1. trait-specific forced-choice or scenario decisions;
2. persona-consistency scores from a frozen rubric and judge;
3. an optional questionnaire score such as PVQ for external validation.

A stratified sample must be independently annotated by two people. Report raw
agreement and Cohen's kappa or Krippendorff's alpha.

### Drift onset

Let `S_t` be a consistency score where larger values mean better alignment.
Choose threshold `tau` from clean training trajectories only. The onset is the
first checkpoint at which the score is below `tau` for `sustain_checkpoints`
consecutive checkpoints.

For a forecast horizon `H`, a checkpoint is positive only when it is currently
pre-drift and onset occurs within the future window:

```text
Y(t, H) = 1 if t < onset <= t + H, otherwise 0.
```

Already-drifted checkpoints are excluded from forecasting evaluation.

### Forked future risk

For selected prefixes, generate `K` future continuations under the same future
policy. Define risk as the fraction of rollouts that cross the drift threshold.
This distinguishes prefix-conditioned risk from the randomness of one realized
continuation.

## Activation protocol

Persona-vector extraction and evaluation data must be disjoint.

- Extraction representation: mean residual activation over response tokens,
  matching BILLY/Persona Vectors.
- Monitoring representation: residual activation of the final prompt token
  before any current response token is decoded.
- Candidate features: normalized persona projection, recent projection slope,
  layerwise projection profile, and non-persona controls such as activation norm.
- Reference layer: layer 20, following BILLY.
- Final layer selection: validation data only; freeze before test evaluation.

Do not save full hidden-state tensors by default. Save reduced FP32 arrays after
pooling so downstream statistics do not accumulate FP16 rounding error.

## Forecasting baselines

1. class prior;
2. turn, condition, and topic metadata;
3. dialogue-history text embedding;
4. latest-response embedding;
5. output-level persona judge;
6. activation norm/PCA controls;
7. persona projection;
8. persona projection plus short trajectory slope.

The decisive comparison is activation features versus a text-history model that
has access to exactly the same observable prefix.

Start with regularized logistic regression. Add a temporal neural model only if
the linear model establishes a signal and there are enough independent
trajectories.

## Splits and statistics

- Split by complete trajectory, never by checkpoint.
- Keep all branches of a prefix in the same split.
- Use grouped splits by topic/scenario and report cross-topic transfer.
- Freeze prompts, thresholds, selected layers, and hyperparameters before test.
- Use trajectory-clustered bootstrap confidence intervals.
- Treat the trajectory, not the checkpoint, as the independent statistical unit.

Primary forecasting metrics:

- AUPRC;
- AUROC;
- Brier score and calibration plot;
- mean/median warning lead time;
- recall at lead time of at least 1, 3, and 5 turns;
- false alarms per 100 turns.

## Intervention experiment

Run paired continuations from an identical checkpoint and seed where possible:

1. no intervention;
2. random intervention matched by intervention count;
3. periodic persona reminder;
4. output-detected intervention;
5. activation-risk-triggered reminder;
6. activation steering, after prompt intervention is characterized.

Select the trigger threshold on validation data. Compare policies at matched
intervention count or token budget. Measure cumulative drift, task success,
answer quality, over-correction, latency, and token cost.

## Go/no-go gates

### Gate A: drift induction

Pressure conditions must produce reproducible sustained drift relative to neutral
and topic-shift controls. Otherwise revise the dialogue generator before doing
activation modeling.

### Gate B: representation

An independently extracted persona direction must classify held-out positive and
negative expressions and correlate with at least one non-questionnaire behavior
surface. Otherwise revisit contrastive data, pooling, and layer selection.

### Gate C: prospective incremental value

On pre-drift checkpoints, activation features must improve over the strongest
same-prefix text baseline with a trajectory-bootstrap confidence interval. The
meaningful effect size will be preregistered after the pilot, not chosen after
viewing the final test set.

If Gate C fails, report the negative result or narrow the paper to measurement
disagreement; do not relabel contemporaneous drift detection as forecasting.

### Current gate status (2026-08-11)

- Gate B passed on the frozen held-out representation and behavior checks.
- Scoped Gate A passed with `cautious_risk_seeking` as the positive axis and
  `independent_sycophantic` as the resistant negative control. See
  `docs/gate_a_pilot_v1_results.md`.
- Gate C development v1 completed and did not meet its promising criterion. The
  five-turn combined-minus-text AUPRC was 0.0163 with trajectory-bootstrap 95%
  CI [-0.0132, 0.0511]. The independent-axis negative control produced 38.5
  alarms per 100 eligible turns.
- A post-hoc decomposition localized the specificity failure to non-transferable
  raw activation scaling across persona axes: text-only raised 0/800 alarms,
  activation-only 800/800, and the combined model 308/800.
- Gate C development v2 completed with axis-calibrated activation features, but
  again failed: AUPRC increment 0.0163 [95% CI -0.0140, 0.0501] and resistant-axis
  alarms 33.75 per 100 turns. Confirmatory Gate C remains unauthorized.
- Do not tune further on the same development test. Either collect a new
  multi-axis development corpus or preregister a new-data confirmation of the
  representation/behavior dissociation. See `docs/gate_c_development_v2_results.md`
  and `docs/paper_strategy_after_gate_c_v2.md`.

## Confirmatory replication

After the complete Qwen protocol is frozen, repeat the primary analyses on
`meta-llama/Llama-3.1-8B-Instruct`. Do not reselect hypotheses on the Llama
results. Gemma-3-4B-it is an optional third model for direct BILLY alignment.

## Paper artifacts

Every paper table must be reproducible from immutable trajectory manifests and a
single analysis command. Store prompt templates, model revision, generation
configuration, random seed, environment versions, checkpoint thresholds, and
exclusions with each experiment manifest.
