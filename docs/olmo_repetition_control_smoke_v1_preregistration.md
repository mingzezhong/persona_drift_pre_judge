# OLMo repetition-control smoke v1 preregistration

Date: 2026-08-18 (AEST)

## Trigger and scope

The format-only failure diagnostic selected `repetition_control_pilot` under
its frozen priority rule. Its decision artifact has SHA256
`c999b2eaf1f3afebe6b6c805e9c3dd0b0ddf267248ae7955ccea0149b9a2b9e8`.
The cap-384 EOS audit passed, while 78.66% of capped responses crossed the
automated repetition threshold and 11/12 blinded capped samples were repetitive
loops. No persona outcome was evaluated.

This smoke is an engineering experiment only. It may authorize a larger
repetition-control pilot, but it cannot authorize formal replication or be
pooled with research data. Formal seeds 701--710 remain untouched.

## Rationale

The OLMo model card demonstrates standard chat-template generation and confirms
the checkpoint's EOS behavior but does not prescribe an anti-repetition
configuration. BILLY uses temperature 0.7 for its single-agent baseline and
reports that smaller models sometimes require more bounded instructions. The
current smoke retains temperature 0.7 and every prompt so the first intervention
isolates decoding degeneration rather than changing persona pressure content.

Standard Hugging Face repetition controls inspect the whole sequence. That is
undesirable here because the long prompt deliberately repeats project language
across 25 turns. The smoke therefore applies both controls only to tokens
generated after the current assistant boundary.

Primary references:

- https://huggingface.co/allenai/OLMo-2-1124-7B-Instruct
- https://arxiv.org/abs/2510.10157v2

## Frozen candidates

Both candidates use:

- pinned `allenai/OLMo-2-1124-7B-Instruct` revision
  `470b1fba1ae01581f270116362ee4aa1b97f4c84`;
- both axes and all four conditions;
- topic `municipal_water_reuse`;
- engineering-only seed 611;
- 25 turns and checkpoints 0, 5, 10, 15, 20, 25;
- 8 trajectories, 200 main responses, and 48 probes per candidate;
- max/min new tokens 384/24, temperature 0.7, top-p 0.9, sampling enabled;
- generated-only no-repeat four-gram size 4.

The only candidate difference is generated-only repetition penalty:

- `rp105`: 1.05;
- `rp110`: 1.10.

Each axis job runs both candidates sequentially. Candidate outputs and the
diagnostic source remain immutable and separate.

## Frozen smoke gate

The smallest penalty passing every check becomes the promising setting for a
full repetition-control pilot:

- combined, main, and probe cap rates each <= 10%;
- every response-type x axis x condition cap rate <= 20%;
- overall high duplicate-four-gram rate <= 5%;
- every response-type x axis x condition high-duplicate rate <= 10%;
- overall joint 2--4 sentence and 30--70 word compliance >= 50%;
- every response-type x axis x condition joint compliance >= 25%;
- complete-sentence ending rate >= 90%;
- list/heading rate <= 15%;
- role-start rate <= 2% and all forbidden-marker counts zero.

These are screening thresholds, not formal research thresholds. If neither
candidate passes, no full repetition-control pilot is authorized and the next
engineering class is prompt salience. If one passes, a new full pilot with new
engineering seeds and all three topics must be separately frozen. No response
is persona-scored in this smoke.

## Validation and provenance

Before submission, compilation, generated-only processor tests, selection-rule
tests, exact config validation, all source hashes, and a protocol manifest must
pass. The output root must not exist. The merge may return status 2 only when
the frozen selection rule finds no candidate.
