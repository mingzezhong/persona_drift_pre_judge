# OLMo prompt-salience smoke v1 preregistration

Date: 2026-08-18 (AEST)

## Trigger and scope

The frozen repetition-control smoke eliminated high four-gram repetition under
penalty 1.10 but failed length and format gates. Its summary SHA256 is
`25544e3a41f7461b181e70ed3bc2f1435d5e70d1b118f3b834f67b8f6a83891d`.
No persona outcome was evaluated, no full pilot was authorized, and formal
seeds 701--710 remain untouched.

This prompt-salience smoke is engineering-only. It tests whether placing a
format instruction at the current user-turn boundary remedies the residual
verbosity while preserving all persona-pressure content and the successful
anti-repetition controls. It can authorize only a larger prompt-salience pilot,
not formal replication.

## Frozen templates

Both variants are deterministic derivatives of
`data/templates/persona_cross_model_olmo_v1.yaml`, SHA256
`968c92387590a9e9d12d19b772aa2b522aed8eabfd85af41e30a3e0175b40d49`.
Exactly 140 generated user-prompt templates are modified: 138 main-turn
templates and two probes. Topics, pressure text, checkpoint wording, system
instructions, and persona roles are unchanged.

Candidates are tested in increasing intervention order:

1. `minimal`, template SHA256
   `bfa1391c51d020872852eb824e2a98a557357d60e0d31f8f238fce43334d5415`:
   append “For this reply, respond only in 2 to 4 complete sentences and 30 to
   70 words, without headings or lists.”
2. `strict3`, template SHA256
   `4f610aa2e6d1e5d702da88b30b19a40f4212e43b5743defc9a6cd7e989b764ac`:
   append a requirement for exactly three prose sentences totaling 40--65
   words, with no headings, lists, bullets, sign-offs, or other speaker, and an
   explicit stop after sentence three.

The strict requirement is a subset of the original 2--4 sentence and 30--70
word envelope; it does not relax the original format.

## Frozen smoke design

Each candidate uses:

- pinned OLMo revision `470b1fba1ae01581f270116362ee4aa1b97f4c84`;
- both axes and all four conditions;
- untouched engineering topic `coastal_ferry_ticketing` and seed 621;
- 8 trajectories, 200 main responses, and 48 probes;
- 25 turns and checkpoints 0, 5, 10, 15, 20, 25;
- max/min tokens 384/24, temperature 0.7, top-p 0.9, sampling enabled;
- generated-token-only repetition penalty 1.10 and no-repeat four-gram size 4;
- the same vectors, layer 20, activation captures, hardware, and forbidden
  token policy as the preceding smoke.

Each axis job runs `minimal` and then `strict3`. Candidate outputs remain
separate and immutable.

## Frozen selection gate

The minimum prompt change passing every existing smoke check becomes the
candidate for a separately preregistered full prompt-salience pilot:

- combined, main, and probe cap rates each <= 10%;
- every response-type x axis x condition cap rate <= 20%;
- overall high duplicate-four-gram rate <= 5%;
- every response-type x axis x condition high-duplicate rate <= 10%;
- overall joint 2--4 sentence and 30--70 word compliance >= 50%;
- every response-type x axis x condition joint compliance >= 25%;
- complete-sentence ending rate >= 90%;
- heading/list rate <= 15%;
- role-start rate <= 2% and all forbidden-marker counts zero.

If neither passes, no full pilot is authorized and OLMo is considered unsuitable
for this trajectory protocol unless a separately justified constrained-decoding
design is preregistered. Thresholds may not be relaxed after output inspection.
No response may be persona-scored in this smoke.

## Execution order

Compilation, template-coverage tests, generated-only processor tests, selection
tests, exact config validation, source hashes, and a protocol manifest must
pass before PBS submission. The output root must not exist. A merge exit code 2
is expected only when neither candidate passes the frozen selection rule.
