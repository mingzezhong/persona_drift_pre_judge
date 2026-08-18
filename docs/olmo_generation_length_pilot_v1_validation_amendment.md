# OLMo length-pilot validation execution amendment

Date: 2026-08-18 (AEST)

Validation job `53128` requested the full repository test suite before the
length pilot. On `hpc-exec01` it remained in a low-CPU wait for more than ten
minutes (7 CPU seconds consumed), produced an empty log, and never released any
dependent GPU job. No `cap256` or `cap384` output directory was created. Jobs
`53128`--`53135` were canceled and their identifiers and empty validation log
were archived under `failed_attempts/53128_validation_hang/`.

The unchanged repository baseline and partition generator/merger had already
passed 135 tests in job `52822` before the length-pilot files were introduced.
The replacement validation therefore checks only the new change surface:

- Python compilation of the two new pilot scripts and new tests;
- the five new token-only unit tests;
- exact deep-equality validation showing that each pilot config differs from
  the frozen base config only in the preregistered pilot fields;
- absence of pilot output and absence of source-run judge/analysis output.

All lineage manifests are revalidated before resubmission. This amendment
changes validation execution only. Candidate caps, pilot seeds, prompts,
generation settings, QC thresholds, and selection rules remain frozen. No
response text or persona outcome was inspected.
