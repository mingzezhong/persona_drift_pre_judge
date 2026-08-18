# OLMo execution-v2 downstream-submission addendum

Date: 2026-08-18 (AEST)

The execution-v2 submission at 01:40 AEST successfully created validation job
`52822`, six axis-topic generation jobs `52823`--`52828`, and merge job
`52829`. PBS then rejected the first judge submission because `large_gpuq`
allows at most six queued jobs per user and all six slots were occupied by the
dependency-held generation jobs.

At discovery, validation was running and all generation jobs were still held on
that validation dependency. No cross-model trajectory, probe response, judge
score, drift outcome, or hypothesis test existed or was inspected. The failure
therefore concerns scheduler orchestration only.

A CPU-only dispatcher is added with an `afterok:52829` dependency. It runs only
after the six generation shards have passed merge and generation QC. At that
point the six generation jobs have left `large_gpuq`, so the dispatcher submits
the unchanged three frozen judge PBS files and then submits the unchanged final
analysis PBS file with an `afterok` dependency on all three judges. It records
the resulting IDs in `execution_v2_downstream_job_ids.txt`.

No model, prompt, data cell, seed, generation setting, measurement rule,
analysis code, threshold, or confirmatory decision rule is changed by this
submission addendum.
