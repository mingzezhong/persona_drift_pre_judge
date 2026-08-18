# OLMo generation-failure diagnostic v2 results

Date: 2026-08-18 (AEST)

## Decision

The frozen remediation rule selected `repetition_control_pilot`. Formal OLMo
replication remains unauthorized, persona outcomes were not evaluated, and the
sealed sample key was not opened.

## Evidence

- The tokenizer audit passed. Configured EOS ID `100257` exactly matched every
  observed non-null stop ID, so this is not an EOS-configuration failure.
- Only 18.62% of all 1,488 cap-384 responses obeyed both the 2--4 sentence and
  30--70 word instruction.
- Of 417 capped responses, 78.66% had duplicate-four-gram rate at least 0.15,
  versus the preregistered 25% repetition threshold.
- The blinded format sample contained 12 capped and 16 normally stopped
  responses. Eleven of 12 capped responses were labeled repetitive loops,
  none ended completely, and only one remained coherent. All 16 stopped
  references were coherent and none was a repetitive loop.
- Nine of 16 stopped references still showed obvious length-instruction
  noncompliance, so format salience is also a problem; the frozen priority rule
  addresses repetition first.

The selected class is determined independently by the full-corpus automated
rate (78.66%) and the blinded capped-sample loop rate (91.67%). Raising the cap
alone would extend malformed loops and is not an acceptable remediation.

## Artifacts

- `automated_summary.json` SHA256:
  `fb96d50718af87ef91a7c288fa0d3f96f9575cd25b0e9e45e7b81587ae75fe30`
- `blinded_samples.jsonl` SHA256:
  `a7d1b3de141721bf5335f8ebf71b5fc24c776f78079e57bd297e765a7d8fb114`
- `format_review.jsonl` SHA256:
  `ddc1a02c2ec2a170607e227f3684b49e2094f487f6ca5af760a9cb1601f026d8`
- `decision.json` SHA256:
  `c999b2eaf1f3afebe6b6c805e9c3dd0b0ddf267248ae7955ccea0149b9a2b9e8`

All artifacts are under
`outputs/cross_model_replication/olmo_length_pilot_v1/failure_diagnostic_v2/`.

## Next experiment

Run the separately preregistered repetition-control smoke. It leaves prompts,
temperature 0.7, top-p 0.9, cap 384, vectors, topics, turns, and measurements
unchanged. It compares generated-token-only repetition penalties 1.05 and 1.10
with a generated-token-only four-gram ban. Prompt tokens are explicitly
excluded from both controls because the 25-turn history deliberately repeats
task language.
