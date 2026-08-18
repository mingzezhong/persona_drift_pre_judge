# Two-model extraction review protocol

This protocol replaces full manual review during the extraction quality pilot.
It does not claim human-grounded construct validity. A later paper may add a
stratified human audit without changing the immutable AI review outputs.

## Frozen reviewers

- Judge A: `mistralai/Mistral-Small-24B-Instruct-2501`, revision
  `9527884be6e5616bdd54de542f9ae13384489724`.
- Judge B: `microsoft/phi-4`, revision
  `2db69c1c3e91a05d2c64a3185acfbaf36f744e25`.
- Target model: `Qwen/Qwen2.5-7B-Instruct`; it is never used as a judge.

The reviewers use different model families, receive separately shuffled blind
review sheets, run with deterministic decoding, and cannot read one another's
outputs. Evaluated user and assistant text is delimited as untrusted data.

## Decision rule

Each reviewer applies `configs/extraction_judge_rubric.yaml`. A reviewer accepts
an example only if every rubric threshold is met. Final consensus is strict
intersection: both reviewers must accept. Decision disagreements are retained,
flagged, and rejected from vector construction. Report individual acceptance
rates, raw decision agreement, Cohen's kappa, and exact agreement by dimension.

The raw extraction manifest and activations remain immutable. The merge step
writes a separate `reviewed_manifest.jsonl`, which is the only manifest used by
`scripts/build_persona_vectors.py`.

## Execution

From the project root:

```bash
qsub jobs/ai_judge_quality_pilot.pbs
```

The job requests two GPUs, binds one reviewer to each GPU, supports safe resume
from per-reviewer partial JSONL, and merges results only after both reviewers
finish successfully. All model revisions, tokenizer compatibility settings,
review sheets, and output paths are frozen in `configs/ai_judges.yaml`.
