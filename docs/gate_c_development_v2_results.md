# Gate C development v2 results

## Decision

Gate C development v2 completed successfully as an engineering run but failed
its frozen research decision. New-data confirmatory Gate C remains unauthorized.
V2 was explicitly post-hoc development after v1 and is not confirmatory.

The full preflight job `43703.hpc-head01` passed 103 tests. Analysis job
`43704.hpc-head01` completed with exit status 0. The v2 config, design,
implementation, test, and PBS hashes were frozen in
`docs/gate_c_development_v2_frozen.sha256` before either job ran.

## Frozen change from v1

V2 changed only the cross-axis activation coordinate system. Projection and norm
were standardized separately for each persona axis using 400 eligible rows from
the training topic's `neutral` and `topic_shift` trajectories. Pressure rows,
validation/test topics, outcomes, and future turns did not enter calibration.
Projection change from turn 1, three-turn slope, turn number, causal labels,
TF-IDF comparator, and trajectory bootstrap remained fixed.

## Primary result

| Model | AUPRC | AUROC | Brier |
|---|---:|---:|---:|
| Frozen TF-IDF text | 0.8942 | 0.9857 | 0.02832 |
| Axis-calibrated activation | 0.9073 | 0.9867 | 0.07710 |
| TF-IDF plus axis-calibrated activation | 0.9105 | 0.9896 | 0.02731 |

- combined-minus-text AUPRC: 0.0163;
- trajectory-bootstrap 95% CI: [-0.0140, 0.0501];
- text-minus-combined Brier: 0.00100;
- thresholded cautious-axis recall: 0.88;
- false alarms: 1.71 per 100 eligible cautious-axis turns;
- drift-trajectory detection: 20/20;
- median maximum lead: 4.5 turns.

The cautious-axis point predictions are effectively unchanged from v1. This is
expected: per-axis affine calibration followed by a scaler fitted on the same
cautious training rows is algebraically equivalent for a linear classifier.
V2's informative test is therefore cross-axis specificity, not a new way to
improve the already inspected cautious development-test score.

## Negative control

The exact validation-selected threshold was applied to all 800 eligible
independent-axis development-test rows, which contain no frozen drift.

| Model | Alarms | Alarms / 100 turns | Trajectories with any alarm |
|---|---:|---:|---:|
| Frozen TF-IDF text | 0/800 | 0.00 | 0/40 |
| Axis-calibrated activation | 285/800 | 35.63 | 20/40 |
| Combined | 270/800 | 33.75 | 20/40 |

All combined alarms occurred in the 20 pressure trajectories; clean controls had
zero threshold crossings. Axis calibration greatly reduced the v1
activation-only failure (800/800), but it did not make pressure response specific
to future behavioral drift. The layer-20 signal responds to pressure in the
resistant axis even when the output judge records no sustained persona drift.

## Frozen decision checks

| Check | Requirement | Observed | Pass |
|---|---:|---:|---|
| Combined-minus-text AUPRC | at least 0.02 | 0.0163 | No |
| Bootstrap lower bound | above 0 | -0.0140 | No |
| Combined Brier | no worse than text | better by 0.00100 | Yes |
| Negative-control alarms | at most 5/100 | 33.75/100 | No |
| Drift-trajectory detection | at least 0.80 | 1.00 | Yes |
| Median warning lead | at least 3 turns | 4.5 | Yes |

Because only three of six checks passed, the stored
`new_data_confirmation_authorized` value is `false`.

## Scientific interpretation

The current evidence separates three claims that should not be conflated:

1. Gate B supports that persona directions encode held-out persona expression.
2. Gate A supports that the cautious persona's output can be driven into
   sustained drift by the frozen pressure protocol.
3. Gate C does **not** yet support that the monitored activation is a robust,
   text-incremental, cross-axis-specific early warning signal for future output
   drift.

The negative control indicates that the monitored feature can be a marker of
latent pressure response without being a specific predictor of behavioral
conversion. This is a substantive measurement result, not an engineering error.

No further hyperparameter or feature selection should use the same development
test. The next study must either collect a new development corpus for learning a
pressure-residual drift representation, or narrow the paper to the staged
representation/induction/forecasting dissociation and confirm that negative
result on new data.

## Artifacts

- Design: `docs/gate_c_development_v2_design.md`
- Config: `configs/gate_c_development_v2.yaml`
- Frozen hashes: `docs/gate_c_development_v2_frozen.sha256`
- Summary: `outputs/gate_c/development_v2/analysis/summary.json`
- Cautious predictions: `outputs/gate_c/development_v2/analysis/primary_predictions.csv`
- Negative-control predictions: `outputs/gate_c/development_v2/analysis/negative_control_predictions.csv`

