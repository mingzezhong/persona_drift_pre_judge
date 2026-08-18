# Gate C development v2 frozen design

## Status and rationale

Frozen on 2026-08-11 after Gate C development v1 and its negative-control
decomposition were inspected, but before computing any v2 result. V2 is
explicitly post-hoc development and cannot support a confirmatory claim.

V1 showed a small, uncertain five-turn AUPRC increment and a cross-axis
specificity failure. Reusing the primary threshold, text-only raised 0/800
negative-control alarms, activation-only 800/800, and the combined model 308/800.
The v2 change is limited to making activation coordinates comparable across
persona axes. Labels, causal timing, split topics, text comparator, learner,
five-turn horizon, and trajectory bootstrap remain fixed.

## Axis-calibrated activation representation

For each persona axis separately, estimate the mean and population standard
deviation of layer-20 pre-response projection and norm using only eligible
five-turn rows from the training topic's `neutral` and `topic_shift`
trajectories. No validation/development-test row, pressure trajectory, outcome,
or future turn enters these calibration constants.

The five predictors are:

1. current projection standardized by the matching axis's clean-training mean
   and standard deviation;
2. projection change from the same trajectory's turn 1;
3. projection slope over the last three available turns;
4. current norm standardized by the matching axis's clean-training mean and
   standard deviation;
5. turn number.

The raw absolute projection and norm are not v2 primary features. Condition is
used only to identify the frozen clean calibration subset and bootstrap strata;
it is never supplied to the classifier.

## Models and evaluation

The strongest v1 validation-selected text comparator is frozen as TF-IDF with
`C=100`; it is not reselected in v2. Activation-only and
TF-IDF-plus-activation regularization are selected from the frozen v1 grid on
the validation topic. The alarm threshold is also selected on validation with
the unchanged minimum recall of 0.80, then applied unchanged after refitting on
training plus validation.

The primary effect remains combined-minus-text AUPRC on the cautious-axis
development-test topic. Ten thousand paired replicates resample complete
trajectories within condition. The same fitted models and numerical threshold
are then applied to all eligible independent-axis development-test rows.

## Frozen development decision

V2 authorizes planning a new-data confirmatory Gate C only if all conditions
hold:

- combined-minus-text AUPRC is at least 0.02;
- its paired-bootstrap 95% lower bound is above zero;
- combined Brier score is no worse than text alone;
- independent-axis negative-control alarms are at most 5 per 100 eligible turns;
- at least 80% of drift trajectories are detected;
- median maximum warning lead is at least 3 turns.

Passing would authorize a separate power analysis and preregistration, not count
as confirmation. Failing means the current representation is not ready for new
confirmatory data.

