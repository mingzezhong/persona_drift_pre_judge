# OLMo repetition-control smoke v1 results

Date: 2026-08-18 (AEST)

## Decision

Neither generated-token-only repetition penalty passed the frozen smoke gate.
No full repetition-control pilot or formal OLMo replication is authorized. The
merge job `53625.hpc-head01` exited 2 by design after writing the complete
summary; validation and both GPU generation jobs exited 0.

## What worked

The intervention isolated and substantially fixed decoding loops:

- penalty 1.05: overall high duplicate-four-gram rate 2.82%;
- penalty 1.10: overall and every-cell high duplicate-four-gram rate 0%;
- role-start and forbidden-marker checks passed for both candidates.

This supports retaining penalty 1.10 plus the generated-only four-gram ban in
the next engineering stage. It does not by itself authorize scientific use.

## Remaining failure

Penalty 1.05 still had 22.58% capped responses. Penalty 1.10 improved this to
16.94%, but remained above the 10% gate; its main/probe rates were 16.00% and
20.83%. For penalty 1.10, only 17.74% of responses obeyed both 2--4 sentences
and 30--70 words, complete endings were 82.26%, and headings/lists occurred in
19.35%. All missed their frozen smoke thresholds.

The remaining problem is therefore current-turn format-instruction salience,
not repeat-loop suppression or EOS configuration. The preregistered next class
is prompt salience.

## Artifact

`outputs/cross_model_replication/olmo_repetition_control_smoke_v1/summary.json`
has SHA256
`25544e3a41f7461b181e70ed3bc2f1435d5e70d1b118f3b834f67b8f6a83891d`.
Persona outcomes were not evaluated and responses from this smoke remain
engineering-only.
