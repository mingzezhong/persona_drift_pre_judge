# OLMo generation-failure diagnostic v2 preregistration

Date: 2026-08-18 (AEST)

## Trigger and status

The frozen OLMo generation-length pilot v1 completed both candidates. Neither
passed its prespecified generation gate. Cap 256 reached the maximum on
532/1,488 responses (35.75%); cap 384 reached it on 417/1,488 responses
(28.02%). The cap-384 main/probe rates were 28.50% and 26.04%. Both candidates
passed the role-start and forbidden-marker checks. The pilot summary has SHA256
`6090a8471644a64c7d3df20e81bc9c9eb7d7728a37852ac610171f857a489c26`.

No cap was selected, no formal OLMo rerun is authorized, and formal seeds
701--710 remain untouched. Before this document and its diagnostic code are
frozen, no generated response text from either length candidate has been
manually inspected and no persona outcome has been evaluated.

## Purpose and exclusion

This is a post-failure engineering diagnostic, not a scientific analysis. It
may inspect response form only to distinguish four remediation classes:

1. tokenizer or termination mismatch;
2. repetitive/runaway decoding;
3. failure to follow the frozen 2--4 sentence and 30--70 word instruction;
4. otherwise coherent natural verbosity requiring a larger cap.

The diagnostic must not label agreement, caution, independence, sycophancy,
risk preference, drift, probe alignment, activation projections, or any study
outcome. Pilot records and diagnostic labels remain ineligible for confirmatory
inference and will never be pooled with a formal replication.

## Frozen source

The diagnostic uses cap 384 because it is the larger failed candidate. Its
source artifacts are immutable and are enumerated with exact hashes in
`docs/olmo_generation_failure_diagnostic_v2_sources.sha256`. The diagnostic
must validate that manifest before reading response text. Expected counts are
48 trajectories, 1,200 main responses, 288 probe responses, and 1,488 total
responses.

## Automated format audit

For every cap-384 response, the frozen script computes only:

- token, word, sentence, character, and line counts;
- compliance with 30--70 words and 2--4 complete sentences;
- whether the final visible character sequence ends with sentence punctuation;
- presence of a line-initial list or Markdown heading;
- duplicate four-gram rate and exact repeated-sentence count;
- recorded stop-token ID and whether the response reached 384 tokens.

Words use the script's frozen English alphanumeric/apostrophe/hyphen regular
expression. Sentence counts use visible `.`, `!`, or `?` boundaries. A high
four-gram repetition flag is fixed at `>= 0.15`.

The tokenizer is loaded locally at the pinned model revision. The termination
audit passes only if configured EOS IDs are nonempty, at least one non-null
stop ID was observed, and every observed non-null stop ID belongs to the EOS
set.

## Blinded qualitative format sample

The script selects one item from every populated
`response_type x axis x condition x cap_status` cell, where response type is
main/probe and cap status is stopped/capped. Within a cell it selects the
lowest SHA256 rank under the fixed salt
`olmo-generation-failure-diagnostic-v2-20260818`. Given the observed token-only
cell counts, this yields 28 items: 16 normally stopped references and 12 capped
responses.

The reviewer sees only an opaque sample ID, response type, cap status, token
count, automated format metrics, and response text. Axis, condition, topic,
seed, turn, source ID, forced choice, and activations are stored separately in
`sample_key.sealed.jsonl` and must remain unopened until format labels are
committed.

Codex acts as a format-only AI reviewer. Each item receives exactly five
Boolean labels: complete ending, coherent, repetitive loop, list/heading
expansion, and obvious length-instruction noncompliance, plus an optional short
format-only note. No persona or semantic-preference label is permitted.

## Frozen remediation decision

The diagnostic selects exactly one next engineering class in this priority
order:

1. `repair_termination` if the tokenizer termination audit fails;
2. `repetition_control_pilot` if at least 25% of all capped responses have
   duplicate-four-gram rate `>= 0.15`, or at least 25% of reviewed capped
   responses are labeled repetitive loops;
3. `prompt_salience_pilot` if full-corpus joint format compliance is below 80%,
   or at least 25% of reviewed capped responses show obvious length-instruction
   noncompliance;
4. `cap_512_768_pilot` otherwise.

Qualitative review can make the repetition or instruction-failure decision
more conservative, but it cannot relax these thresholds or authorize a formal
run. Any resulting remediation pilot requires a separate frozen config, new
engineering-only seeds, unchanged scientific hypotheses and measurement
thresholds, and the same generation-quality gate. Formal seeds 701--710 remain
reserved until a remediation candidate passes.

## Execution order

1. Commit this protocol, source manifest, diagnostic script, and tests.
2. Record their SHA256 values in a protocol manifest.
3. Run compilation and targeted tests without reading response text.
4. Run the automated audit and create the blinded sample.
5. Complete and hash the blinded format review before opening the sample key.
6. Apply the frozen remediation rule and record a results report and ledger row.

