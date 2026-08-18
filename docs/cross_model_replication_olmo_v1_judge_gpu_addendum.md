# OLMo execution-v3 judge GPU-allocation addendum

Date: 2026-08-18 (AEST)

During execution-v2 monitoring, the archived logs for canceled jobs `52719`
and `52720` showed that two simultaneous GPU jobs on the same node had both
selected physical GPU 0. Generation v2 had already corrected this race with a
node-local lock, but the frozen downstream judge PBS files still contained the
old non-atomic selection logic.

At this audit point, generation shards were still in progress. Only scheduler
state and JSONL record counts had been inspected. No generated text, activation
value, judge score, drift outcome, condition comparison, or hypothesis test was
inspected. Dispatcher `52835` was dependency-held and was canceled before it
ran; it produced no judge or analysis job.

Execution v3 adds one generic judge PBS wrapper that keeps the same queue,
resources, environment, judge script, judge config, three frozen judge IDs, and
`--resume` behavior. Its only execution change is to acquire the same per-user,
node-local GPU lock used by generation v2 before setting
`CUDA_VISIBLE_DEVICES`. A replacement CPU dispatcher submits three instances
of this wrapper after successful merge and generation QC, then submits the
unchanged final analysis job after all three judges finish successfully.

No model, revision, prompt, trajectory, seed, response, judge rubric, scoring
model, threshold, estimand, bootstrap method, or confirmatory decision rule is
changed. The canceled dispatcher and its frozen manifest remain preserved as
engineering provenance.
