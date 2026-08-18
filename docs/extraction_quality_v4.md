# Extraction quality pilot v4

## Status

Quality gates passed. These artifacts are pilot persona vectors for held-out
representation testing; they are not yet validated final vectors.

## Lineage

- v2 passed generation structure but only 8/24 contrastive pairs passed strict
  two-model review. Negative-pole expression was weak and trait labels were
  underspecified for the judges.
- v3 introduced low-stakes prompts, stronger contrastive instructions, minimum
  response length, and behaviorally anchored rubric v2. It failed the frozen
  generation gate because one of 48 outputs started a new role and exposed a
  tool marker.
- v4 retained the v3 research design, prohibited tool invocation, and reduced
  `min_new_tokens` from 40 to 32. No thresholds were changed after observing
  results.

## Frozen inputs

- Target: `Qwen/Qwen2.5-7B-Instruct` at
  `a09a35458c702b33eeacc393d103063234e8bc28` in BF16.
- Template: `data/templates/persona_axes_v3.yaml`.
- Generation: 32--160 new tokens, temperature 0.7, top-p 0.9, sampling enabled,
  seed 0.
- Rubric: `configs/extraction_judge_rubric_v2.yaml`, SHA256
  `7808e5b7cd156b575c93fa6bddd1000d6d1f79a07ed0ae0a8025b0f9b38f6fd4`.
- Judges: Mistral Small 24B and Phi-4 at the revisions recorded in
  `configs/ai_judges_v4.yaml`.

## Results

- Generation: 48 examples, 24 matched pairs, 48/48 normal end-of-message
  tokens, zero max-length completions, zero role-start completions.
- Review: both judges accepted 48/48; decision agreement 1.0 and zero decision
  disagreements. Cohen's kappa is undefined because neither reviewer produced
  decision variance. Exact trait-score agreement was 0.8333.
- Paired gate: 12/12 complete pairs for each axis, exceeding the frozen 0.80
  minimum per-axis rate.
- Vectors: two FP32 tensors of shape `[28, 3584]`, built only from complete
  double-accepted pairs. SHA256:
  `54c144edd24bf07ad648b4df52c0c319bb531aebe315f8bf450c58edacf0347b`.

## Artifacts

- Raw extraction: `outputs/extraction/quality_pilot_s0_v4/`.
- Reviewed manifest and judge outputs:
  `outputs/extraction/quality_pilot_s0_v4/ai_review/`.
- Pilot vectors and structural validation:
  `outputs/persona_vectors/quality_pilot_s0_v4/`.

## Next gate

Gate B requires completely disjoint held-out prompts. Without using the
extraction system prompts at evaluation time, compare persona projection scores
for independently generated positive and negative responses, report per-layer
AUROC and cross-topic transfer, and freeze the selected layer on validation data
before any test-set analysis.
