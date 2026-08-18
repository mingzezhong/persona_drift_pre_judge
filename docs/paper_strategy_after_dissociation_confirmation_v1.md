# Paper strategy after dissociation confirmation v1

## Recommended framing

The defensible paper is a preregistered staged falsification study, not a paper
about a successful early-warning detector.

> Persona directions can encode held-out persona expression, and frozen pressure
> protocols can induce output drift, but the monitored activation is not thereby
> a specific or text-incremental prospective predictor. Even the output-drift
> criterion is sensitive to judge severity and must be validated as a
> measurement instrument.

A suitable working title remains:

> **Representation Is Not Prediction: A Preregistered Stress Test of Persona
> Vectors as Early-Warning Signals for LLM Persona Drift**

The new confirmation materially strengthens the forecasting falsification:
combined-minus-text AUPRC was -0.0120 with a 95% trajectory-bootstrap interval
[-0.0369, 0.0160], wholly below the prespecified smallest useful increment of
0.05. It does not confirm the complete resistant-axis dissociation package.

## Claim table

### Supported

- Independently extracted persona directions encode held-out persona expression
  and correlate with non-questionnaire behavior (Gate B).
- The cautious persona shows a reproducible 100% pressure versus 0% control
  composite drift pattern under the frozen protocol.
- The frozen five-turn activation and combined pipelines provide no practically
  useful AUPRC increment over the same-prefix text comparator on untouched Qwen
  topics and seeds.
- The combined alarm is pressure-responsive: 60/60 resistant pressure versus
  0/60 resistant control trajectories alarmed.

### Not supported

- The preregistered full representation/behavior dissociation package.
- A stable, fully resistant `independent_sycophantic` negative-control axis.
- A general cross-persona latent early-warning detector.
- A judge-invariant output-drift ground truth.
- A causal link from layer-20 projection change to future behavioral drift.
- Intervention efficacy or authorization to start RQ3.

## Recommended paper structure

1. Define the distinction between persona representation, pressure response,
   output drift, and prospective prediction.
2. Establish representation validity with frozen held-out Gate B.
3. Establish scoped output susceptibility with Gate A and its new-data
   replication.
4. Introduce the leakage-controlled five-turn benchmark and strong text
   comparator.
5. Report Gate C development transparently as model-selection work.
6. Lead the confirmatory section with the frozen new-data AUPRC interval and the
   failed six-check intersection decision.
7. Treat judge sensitivity as a measurement result and central limitation, not
   as a reason to select the more favorable judge.
8. End with requirements for valid persona-drift monitoring benchmarks.

## Immediate next stage: measurement development

Do not tune the forecast again on the completed confirmation set. Reclassify any
new analysis of these responses as post-confirmation measurement development.

The next protocol should:

1. use anchored ordinal examples spanning scores 0--4 for both axes;
2. add at least one independently trained judge family;
3. estimate judge severity and discrimination rather than average raw ordinal
   scores directly;
4. freeze a latent-score or calibrated-consensus drift rule on development data;
5. verify pressure/control invariance and test-retest stability;
6. reserve new cross-model topics and seeds as an untouched replication set;
7. report both consensus labels and per-judge sensitivity.

It must also remove internal IDs from judge-facing prompts because the prior ID
encoded condition and checkpoint names; all affected Qwen probes must be rescored.

Different AI models can provide the primary scalable annotation. A modest human
anchor set remains scientifically valuable for construct validity, but if it is
not feasible, the paper must describe the outcome as multi-model AI-judge
measurement rather than human-validated persona drift.

## Decision on cross-model replication

Measurement development v1 has now passed all five held-out anchor checks. The
frozen scoring model uses three independently trained judge families, hides
internal IDs, and calibrates judge severity against behavioral anchors. It is
therefore authorized for an untouched cross-model replication. The original
uncalibrated two-judge threshold must not be used as the primary replication
outcome.

The official Llama-3.1-8B-Instruct repository returned HTTP 401 to the CETUS
account. Before any cross-model target response was generated, the target was
changed for access reasons to the public, ungated
`allenai/OLMo-2-1124-7B-Instruct` at revision
`470b1fba1ae01581f270116362ee4aa1b97f4c84`. This change is not
outcome-informed and is recorded in `docs/cross_model_target_amendment_v1.md`.

The OLMo replication must use new topics and seeds, a pinned target-model
revision, the exact frozen measurement scoring-model hash, and no threshold or
judge changes after target generation begins. OLMo-specific activation vectors
may be constructed by teacher-forcing the already frozen accepted contrastive
responses because Qwen and OLMo hidden dimensions differ, but the extraction
recipe and layer must be fixed before any OLMo trajectory is generated.

## What not to do

- Do not change the 0.05 smallest useful effect after seeing the result.
- Do not select one of the two judges post hoc.
- Do not relabel gradual-pressure trajectories to rescue the negative control.
- Do not tune layers, slopes, horizons, or thresholds on the confirmation set.
- Do not report the four passing checks as if the intersection rule passed.
- Do not begin intervention experiments until a specific warning signal and a
  stable output measure both exist.

## Minimum paper-ready work remaining

- Freeze this confirmation result and update the experiment ledger.
- Freeze the completed measurement-development result and its decision rule.
- Run one untouched cross-model replication.
- Draft the paper with the negative forecasting result as the primary result and
  the measurement limitation as a coequal contribution.
