# Gate C development v1 implementation freeze

## Status

Frozen on 2026-08-11 before constructing the causal forecasting dataset or
computing any text/activation forecasting result. This is a development study,
not a confirmatory analysis, because Gate A labels and topic outcomes have
already been inspected.

The executable specification is `configs/gate_c_development_v1.yaml`. The
submission script records SHA-256 hashes for the config, design, implementation,
tests, and PBS files in the output directory before the first job starts.

## Clarifications fixed before execution

- The primary incremental-information estimate is the development-test AUPRC
  of the strongest validation-selected text representation plus the frozen
  activation feature set, minus that same text representation alone.
- Activation-only minus text is retained as a secondary diagnostic. This
  resolves the design document's abbreviated wording without selecting on the
  development-test topic.
- Text-baseline selection uses validation AUPRC only, with Brier score and then
  deterministic naming as tie breakers. Regularization selection uses
  validation AUPRC, Brier score, then the smaller `C` value.
- The E5 input is the exact persona-free causal prefix, prepended with
  `query: `. It uses the pinned repository revision, attention-mask average
  pooling, L2 normalization, maximum length 512, and left truncation so the
  current user message and most recent history are retained.
- Threshold selection uses predictions from the training-fit combined model on
  the validation topic, requires recall of at least 0.80, and minimizes false
  positive rate. That numerical threshold is then applied unchanged to the
  development-test probabilities after refitting on training plus validation.
- Confidence intervals use 10,000 paired replicates that resample complete
  trajectories within condition. No turn is treated as an independent
  resampling unit.

## Interpretation

The stored `promising` flag is only a development decision aid. It cannot be
reported as confirmation of prospective drift prediction. A confirmatory Gate C
requires new topics, seeds, trajectories, and a separately frozen minimum effect
size and sample-size target.
