# OLMo prompt-salience smoke v1 results

Date: 2026-08-18 (AEST)

## Decision

Both frozen candidates passed every engineering smoke gate. Under the
preregistered minimum-intervention rule, `minimal` was selected and a separately
preregistered full prompt-salience pilot is authorized. Formal replication
remains unauthorized at this stage. No response was persona-scored and no
response text was manually inspected.

## Aggregate evidence

The `minimal` candidate produced 248 responses. Its overall max-length rate,
high duplicate-four-gram rate, list/heading rate, and repeated-sentence rate
were all 0%. Complete-sentence endings were 100%, and joint 2--4 sentence plus
30--70 word compliance was 95.97% overall, 97.50% for main turns, and 89.58%
for probes.

The `strict3` candidate also produced 248 responses and passed all gates. Its
overall max-length, high duplicate-four-gram, list/heading, and repeated-sentence
rates were 0%; complete-sentence endings were 100%, and joint format compliance
was 97.58%. It was not selected because the frozen decision rule prefers the
least restrictive passing prompt.

All four PBS jobs completed with exit status 0:

- validation: `54100.hpc-head01`;
- cautious generation: `54101.hpc-head01`;
- independent generation: `54102.hpc-head01`;
- merge and selection: `54103.hpc-head01`.

The immutable summary is
`outputs/cross_model_replication/olmo_prompt_salience_smoke_v1/summary.json`,
SHA256 `fc5186acd277a8d4d30a78da0c86a0fea98988e9a7acd452fff4adb902c6ee8d`.

## Interpretation boundary

This smoke establishes only that the selected prompt-boundary intervention can
repair the observed generation-quality failure on one topic and one
engineering seed. It does not establish cross-topic robustness, persona drift,
or confirmatory replication. Those claims remain forbidden until the full
quality pilot and, if authorized, the fresh formal replication are complete.
