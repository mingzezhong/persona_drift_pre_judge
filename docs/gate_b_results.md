# Gate B: held-out representation validation

## Decision

**PILOT PASS.** The frozen held-out representation criteria passed, and the
selected representation correlated with a non-questionnaire output-behavior
score on both axes. This supports carrying the quality-pilot v4 vectors at
residual-stream layer 20 into the drift-induction and forecasting pilots.

The representation thresholds and validation-only layer rule were fixed before
the test split was analyzed. The original research specification also required a
behavior correlation but did not define its statistic or threshold. That
operationalization was frozen after projection results existed but before the
correlations were computed. It is therefore transparent pilot evidence, not a
fully preregistered confirmatory result.

Gate B evaluates whether an extraction vector generalizes to held-out persona
expressions and tracks observable output behavior. It does not test longitudinal
drift, prospective warning lead time, causal steering, or cross-model transfer.

## Representation design

- Target model: `Qwen/Qwen2.5-7B-Instruct`, revision
  `a09a35458c702b33eeacc393d103063234e8bc28`.
- Vectors: `outputs/persona_vectors/quality_pilot_s0_v4/persona_vectors.pt`,
  SHA256 `54c144edd24bf07ad648b4df52c0c319bb531aebe315f8bf450c58edacf0347b`.
- Data: 12 prompts not used for vector extraction, split into six validation and
  six test prompts. Two axes, two polarities, and two seeds produce 48 examples
  per split and 96 in total.
- Score: cosine projection of response-token-mean activations onto the matching
  extraction vector.
- Layer selection: maximize mean validation AUROC, then mean paired direction
  accuracy, then choose the layer closest to the prespecified reference layer 20.
- Test gates: mean AUROC at least 0.80, every axis AUROC at least 0.75, and every
  axis paired direction accuracy at least 0.75.
- Uncertainty: 2,000 bootstrap resamples at the prompt-axis-seed pair unit.
- Analysis policy: intention-to-treat. AI review does not filter projection rows.

The frozen representation specification is in
[`configs/gate_b_v2.yaml`](../configs/gate_b_v2.yaml), and held-out templates are
in [`data/templates/persona_gate_b.yaml`](../data/templates/persona_gate_b.yaml).

## Generation and behavior checks

The first research run, `representation_pilot_v1`, failed its unchanged
generation gate because 2/96 responses emitted a role-start marker. That output
is retained as failure evidence and was not evaluated. The decoder was then
changed uniformly for every condition to prohibit token `151644`
(`<|im_start|>`) while retaining token `151645` as normal EOS. Gate B was rerun
in the new v2 output directory.

For v2, all 96 responses ended at normal EOS. There were zero role-start outputs
and zero max-length outputs. The generation manifest SHA256 is
`e672fcc96ad07efa778bc6cd85f444cdd9061b851aab80cfbc67b2a91b258db1`.

Two independent open-weight judges reviewed every response:

- Mistral Small 24B accepted 94/96.
- Phi-4 accepted 92/96.
- Strict intersection accepted 92/96; raw decision agreement was 97.9%, Cohen's
  kappa was 0.657, and two decisions disagreed.
- The paired behavior-quality gate passed: cautious/risk-seeking retained 20/24
  complete accepted pairs (83.3%), independent/sycophantic retained 24/24
  (100%), and decision disagreement was 2.1%.

The four strict-intersection rejects were retained in all representation and
correlation analyses, as required by the intention-to-treat policy.

## Held-out representation results

Validation selected layer 20. Multiple layers tied at perfect validation AUROC
and paired accuracy, so the final prespecified tie-break selected the layer
closest to reference layer 20.

| Test axis | Examples | Pairs | AUROC (95% bootstrap CI) | Pair direction accuracy (95% CI) | Mean paired projection delta (95% CI) | Paired effect `dz` |
|---|---:|---:|---:|---:|---:|---:|
| cautious / risk-seeking | 24 | 12 | 1.000 ([1.000, 1.000]) | 1.000 ([1.000, 1.000]) | 0.239 ([0.199, 0.281]) | 3.17 |
| independent / sycophantic | 24 | 12 | 1.000 ([1.000, 1.000]) | 1.000 ([1.000, 1.000]) | 0.351 ([0.320, 0.378]) | 6.40 |

Mean test AUROC and mean paired direction accuracy were both 1.000. All three
frozen representation checks passed.

## Non-questionnaire behavior correlation

The behavior surface is the mean `trait_alignment` score from the two independent
AI judges, measured from the generated answer rather than a questionnaire. The
mean is divided by four and signed positive for the target pole and negative for
the contrast pole. The exact rule, a minimum per-axis Spearman correlation of
0.50, and a pair-bootstrap 95% CI lower bound above zero were fixed in
[`configs/gate_b_behavior_v1.yaml`](../configs/gate_b_behavior_v1.yaml) before
running this computation.

| Test axis | Pearson `r` (95% CI) | Spearman `rho` (95% CI) | Correlation gate |
|---|---:|---:|---|
| cautious / risk-seeking | 0.927 ([0.894, 0.980]) | 0.890 ([0.824, 0.924]) | pass |
| independent / sycophantic | 0.970 ([0.958, 0.989]) | 0.764 ([0.713, 0.851]) | pass |

Both axes passed. This completes the behavior-surface clause of the pilot Gate B
specification. Because the judges knew the assigned pole and the signed score
uses that pole, a confirmatory replication should preregister the statistic and
add a direct axis-rating judge that is blind to the assigned condition.

## Artifacts and provenance

- Representation summary:
  `outputs/gate_b/representation_pilot_v2/projection/summary.json`, SHA256
  `d5106dcd5d81c0c866a77550f44102860ccc2915988064687058be8b78d3ee65`.
- Per-example projections:
  `outputs/gate_b/representation_pilot_v2/projection/projection_scores.csv`,
  SHA256 `a319c9c032a52ee6144dd0b06324e9d51b7daf8958ea23860eb9a4f01b3adffa`.
- Behavior-correlation summary:
  `outputs/gate_b/representation_pilot_v2/behavior_correlation_v1/summary.json`,
  SHA256 `15bd15a3ed354dc8ef82aece71b03b132e481cf5a102bfbc683edf283dd04c21`.
- Per-example behavior scores SHA256:
  `9f5942d72ff06e75d8203fda61f97912766f91cca464028b850dec251f0b64a0`.
- Reviewed manifest SHA256:
  `4a829b0321c264771efa30ad74b9d67a9da947f3a4019cfb0a742bf6adf53f53`.
- Frozen representation config SHA256:
  `e35a6ad0ade00b7be8e37f657cb78c488bb03179b8ad3e78447c3cbb228fc3e5`.
- Post-specified behavior config SHA256:
  `a9ababa2400548189a68ad546bc8cc6c2d29f25339c71ed4ac994748d2e97a87`.
- Successful PBS jobs: generation `42930`, Mistral judge `42935`, Phi-4 judge
  `42936`, merge/representation evaluation `42937`, and behavior correlation
  `43001`; all exited with status 0.

## Interpretation and next gate

The result is stronger than a manipulation check alone: vectors estimated from
extraction prompts generalize to new scenarios and new persona prompt wording,
and their scores track an output-based behavior rating. It remains a small,
single-model pilot with 12 test pairs per axis, deliberately strong target versus
contrast instructions, and a behavior statistic specified after projection
results were available. Perfect separation is pilot evidence, not a claim that
persona drift is solved.

Per [`docs/research_spec.md`](research_spec.md), the next experiment is Gate A:
show reproducible, sustained drift under pressure relative to neutral and
topic-shift controls. Once the trajectory generator passes Gate A, freeze the
trajectory split and run Gate C, testing whether pre-drift activation features
add prospective value beyond the strongest same-prefix text baseline. Causal
intervention and activation steering come after the forecasting protocol is
characterized, not immediately after Gate B.
