# OLMo generation-length pilot v1 preregistration

Date: 2026-08-18 (AEST)

## Trigger and scope

The first OLMo cross-model replication generated all 240 trajectories, but its
frozen generation gate failed because 3,104/7,440 responses (41.72%) reached
the 128-token limit, above the prespecified 10% maximum. Role-start and
forbidden-marker checks passed. The condition-stratified token counts also
showed that truncation was not balanced, so truncated examples cannot be
dropped or analyzed as a confirmatory sample.

Only scheduler metadata, record counts, token counts, stop-token counts, and
forbidden-marker aggregate counts were inspected. No response text, activation
value, persona judgment, drift label, condition contrast, or hypothesis test
was inspected. The failed run remains immutable and is not eligible for judge
scoring or scientific inference. Its generation-quality hash is
`5ca0a8015dc0e8bf0d34e1b6a12abf04c599313d2176447b15c57d38252b715a`.

## Pilot design

This is an engineering-only token-length pilot. It compares exactly two
candidate `max_new_tokens` values: 256 and 384. All other model, revision,
vector, prompt, topic, condition, turn, checkpoint, sampling, hardware, and
quality settings remain identical to the failed frozen replication.

For each candidate, the pilot uses:

- both persona axes;
- all four conditions;
- all three OLMo replication topics;
- two pilot-only seeds: 601 and 602;
- 48 trajectories, 1,200 main turns, and 288 probes.

The same axis-topic job runs cap 256 and then cap 384. Six GPU jobs therefore
cover the full design while respecting the queue's six-job limit. Generated
text is retained for reproducibility but must not be manually inspected or sent
to persona judges. Only token and generation-QC metadata may be analyzed.

## Frozen selection rule

Candidates are checked in ascending order. The selected cap is the smallest
candidate passing every condition below:

- combined max-length rate <= 10%;
- main-turn max-length rate <= 10%;
- probe max-length rate <= 10%;
- every axis-by-condition main-turn max-length rate <= 15%;
- every axis-by-condition probe max-length rate <= 20%;
- role-start rate <= 2%;
- every forbidden-text marker count equals zero.

If neither candidate passes, no formal OLMo rerun is authorized and a new
engineering design must be preregistered. Thresholds may not be relaxed after
the pilot is observed.

If one candidate passes, the QC-remediated formal replication will use the
selected cap and ten reserved, untouched seeds 701--710 in a new output root.
It will retain the original scientific hypotheses, measurement model, judges,
estimands, bootstrap procedure, and decision thresholds. The original failed
run and this pilot will never be pooled with that formal rerun.
