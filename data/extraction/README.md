# Persona-vector extraction data

Generated JSONL files belong here but are not committed by default.

Each generated example must contain:

```json
{
  "example_id": "extract_001:independent_sycophantic:target:0",
  "prompt_id": "extract_001",
  "axis": "independent_sycophantic",
  "polarity": "target",
  "system": "...",
  "user": "...",
  "response": "...",
  "model": "Qwen/Qwen2.5-7B-Instruct",
  "model_revision": "frozen commit hash",
  "seed": 0,
  "generation": {},
  "judge_score": null,
  "accepted": null
}
```

Rules:

- generation prompts and forecasting evaluation prompts are disjoint;
- both polarities use the same user prompt and generation parameters;
- retain rejected responses in the immutable raw file;
- filter with a frozen judge rubric into a separate manifest;
- use only accepted extraction examples to compute persona vectors;
- save pooled per-layer activations, not full token activations.

