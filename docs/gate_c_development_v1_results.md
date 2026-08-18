# Gate C development pilot v1 results

## Decision

Gate C development v1 is complete and **not promising under its frozen rule**.
This is a development result, not a confirmatory test, because the source Gate A
labels and topic outcomes were already inspected before this analysis.

The combined text-plus-activation model improved five-turn development-test
AUPRC by 0.0163 over the strongest same-prefix text baseline, and slightly
improved Brier score. However, the trajectory-bootstrap interval for the AUPRC
increment crossed zero. The independent-axis negative control also produced an
unacceptably high alarm rate. The current raw cross-axis activation pipeline
must therefore not be carried into a confirmatory Gate C unchanged.

## Execution and provenance

The dependent PBS chain completed with exit status 0 throughout:

| Job | Stage | Result |
|---|---|---|
| `43616.hpc-head01` | Full preflight test suite | 100 passed |
| `43617.hpc-head01` | Causal example construction | Passed |
| `43618.hpc-head01` | Frozen E5 prefix encoding | Passed |
| `43619.hpc-head01` | Model selection, development test, bootstrap | Passed |
| `43626.hpc-head01` | Explicitly post-hoc negative-control decomposition | Passed |

The submission script wrote hashes of the frozen config, design, source, tests,
and PBS files before constructing any forecasting example. Source Gate A hashes
were revalidated during dataset construction.

The dataset contains 4,659 unique causal examples from all 240 Gate A
trajectories. For the primary cautious-axis five-turn analysis, the complete
trajectory splits contained:

| Split | Trajectories | Positive turns | Negative turns | Total |
|---|---:|---:|---:|---:|
| Training | 40 | 99 | 526 | 625 |
| Validation | 40 | 100 | 535 | 635 |
| Development test | 40 | 100 | 545 | 645 |

The frozen encoder was `intfloat/e5-base-v2` at revision
`f52bf8ec8c7124536f0efb74aca902b2995e5bcd`. Requested and resolved revisions
matched. It produced 4,659 finite 768-dimensional embeddings using a `query: `
prefix, left truncation at 512 tokens, attention-mask average pooling, and L2
normalization on an NVIDIA RTX PRO 6000 Blackwell GPU.

## Primary five-turn result

TF-IDF was the strongest text baseline on the validation topic and was selected
without consulting the development-test topic. The selected activation-only and
combined models used the frozen five-feature layer-20 representation and
class-weighted L2 logistic regression.

| Development-test model | AUPRC | AUROC | Brier |
|---|---:|---:|---:|
| Selected TF-IDF text baseline | 0.8942 | 0.9857 | 0.02832 |
| Activation only | 0.9073 | 0.9867 | 0.07710 |
| TF-IDF plus activation | 0.9105 | 0.9896 | 0.02731 |

Primary incremental estimates:

- combined minus text AUPRC: 0.0163;
- paired trajectory-bootstrap 95% CI: [-0.0132, 0.0511];
- text minus combined Brier: 0.00100;
- Brier-improvement bootstrap 95% CI: [-0.000073, 0.002184].

The lower AUPRC bound was not above zero. Consequently, the stored development
criterion `promising` is `false` even though the point estimate is positive and
the point Brier score is slightly better.

The validation-selected threshold was 0.998203. Applied unchanged after the
training-plus-validation refit, it yielded 88/100 positive-turn detections, 11
false positives, 0.88 recall, 0.0202 false-positive rate, and 1.71 false alarms
per 100 eligible cautious-axis test turns. All 20 drift trajectories were
detected; median maximum warning lead was 4.5 turns, and 10/20 were detected at
least five turns before frozen onset.

## Sensitivity horizons

| Horizon | Text AUPRC | Activation AUPRC | Combined AUPRC | Combined minus text |
|---:|---:|---:|---:|---:|
| 3 turns | 0.8688 | 0.7694 | 0.8511 | -0.0176 |
| 5 turns | 0.8942 | 0.9073 | 0.9105 | 0.0163 |
| 10 turns | 0.9477 | 0.9459 | 0.9789 | 0.0311 |

The direction is horizon-dependent: activation hurts the three-turn combined
model, is small and uncertain at five turns, and is more favorable at ten turns.
The ten-turn result is descriptive and was not the primary frozen horizon.

## Negative control and failure localization

On the 800 eligible five-turn examples from the held-out
`independent_sycophantic` development topic, which contains no frozen drift, the
primary combined model raised 308 alarms: 38.5 false alarms per 100 turns. All
20 pressure trajectories had at least one alarm, while the 20 neutral/topic
shift trajectories had none.

Job `43626` was added only after observing this prespecified failure and is
therefore marked post-hoc. It refit the already selected models, reused the exact
primary threshold without retuning, and decomposed the alarm source:

| Feature family | Negative-control alarms | Alarms / 100 turns | Trajectories with any alarm |
|---|---:|---:|---:|
| Selected TF-IDF text only | 0/800 | 0.0 | 0/40 |
| Activation only | 800/800 | 100.0 | 40/40 |
| TF-IDF plus activation | 308/800 | 38.5 | 20/40 |

This establishes a cross-axis representation/calibration failure in this
pipeline. Persona projections are defined relative to different axis vectors;
their raw absolute projection and norm distributions are not guaranteed to be
comparable under a scaler fitted only on the cautious axis. The negative control
correctly exposed this limitation. It would be invalid to discard the control,
retune its threshold, or report only the favorable cautious-axis result.

## Next decision: Gate C development v2

Do not generate confirmatory Gate C data yet. First run a transparently
developmental v2 on the existing data with an axis-invariant representation:

1. fit each axis's normalization constants using only its clean training
   trajectories, never its held-out topic or future turns;
2. make within-trajectory change and short-window slope the main persona
   features, and treat raw projection and raw norm as ablations rather than
   transferable primary features;
3. retain the same causal label construction, topic grouping, strongest-text
   comparator, and trajectory bootstrap;
4. add an explicit out-of-distribution diagnostic before applying a predictor
   across persona axes;
5. require both positive incremental AUPRC uncertainty and a prespecified low
   negative-control alarm rate before authorizing new-data confirmation.

If v2 cannot satisfy both incremental prediction and cross-axis specificity,
the paper should report that the current activation representation measures
axis-local drift but does not support a general prospective seismograph claim.

## Artifacts

- Frozen design: `docs/gate_c_development_v1_design.md`
- Implementation freeze: `docs/gate_c_development_v1_implementation_freeze.md`
- Config: `configs/gate_c_development_v1.yaml`
- Causal dataset summary: `outputs/gate_c/development_v1/dataset/summary.json`
- Embedding summary: `outputs/gate_c/development_v1/embeddings/summary.json`
- Primary analysis: `outputs/gate_c/development_v1/analysis/summary.json`
- Post-hoc diagnostic: `outputs/gate_c/development_v1/diagnostics/summary.json`
