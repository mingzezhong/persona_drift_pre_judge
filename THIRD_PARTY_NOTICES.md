# Third-party data notices

This file records the public-data material redistributed in tracked G1 review
packets. It supplements, and does not replace, the upstream license evidence
stored byte-for-byte under `data/licenses/`.

## MMLU-Pro

- Upstream project: TIGER-Lab/MMLU-Pro
- Source: <https://huggingface.co/datasets/TIGER-Lab/MMLU-Pro>
- Pinned dataset revision:
  `b189ec765aa7ed75c8acfea42df31fdae71f97be`
- Dataset DOI: <https://doi.org/10.57967/hf/2439>
- Declared data license: MIT
- Pinned dataset-card evidence:
  [`data/licenses/mmlu_pro_b189ec765aa7ed75c8acfea42df31fdae71f97be_dataset_card.md`](data/licenses/mmlu_pro_b189ec765aa7ed75c8acfea42df31fdae71f97be_dataset_card.md)
- Evidence source:
  <https://huggingface.co/datasets/TIGER-Lab/MMLU-Pro/blob/b189ec765aa7ed75c8acfea42df31fdae71f97be/README.md>
- Evidence SHA256:
  `4bd710f67da3fa359a33edce1b4b5816b3de416c823c2624ba5e89c2557d2a47`

The pinned dataset card declares `license: mit` and DOI `10.57967/hf/2439`.
Tracked MMLU-Pro-derived review packets redistribute selected question and
choice text from the pinned test split. Project changes are deterministic
stable/blinded identifiers, field selection, administrative-field separation,
and JSONL reformatting for outcome-blind triage and review. The ignored raw
Parquet snapshot is not published by this repository.

## Anthropic model-written evals

- Attribution: Anthropic's `evals` repository
- Source: <https://github.com/anthropics/evals>
- Pinned commit: `84fcc677e52e1902d696c32cd1a6b663e70d3993`
- Declared license: Creative Commons Attribution 4.0 International
  (`CC-BY-4.0`)
- License URI: <https://creativecommons.org/licenses/by/4.0/>
- Pinned LICENSE evidence:
  [`data/licenses/anthropics_evals_84fcc677e52e1902d696c32cd1a6b663e70d3993_LICENSE.txt`](data/licenses/anthropics_evals_84fcc677e52e1902d696c32cd1a6b663e70d3993_LICENSE.txt)
- Evidence source:
  <https://github.com/anthropics/evals/blob/84fcc677e52e1902d696c32cd1a6b663e70d3993/LICENSE>
- Evidence SHA256:
  `7e7170e3cebf88a9f60c7b8421418323c09304da1af4d5e90f4da1dc1c8a2661`

The upstream repository did not supply a separate copyright-holder name in the
pinned LICENSE evidence; this notice does not infer or add one. Use of the
source name above is attribution, not an assertion of endorsement.

### Changes made to redistributed material

- Persona-derived packets: source rows were deterministically normalized and
  globally deduplicated, sampled outcome-blind, assigned anonymous candidate
  and item identifiers, separated from administrative provenance, and
  reformatted into review JSONL. The source text remains attributable to
  Anthropic's `evals` repository.
- Topic-derived packets: generated biography, affiliation, and explicit user
  stance were removed; surviving content was parsed, logically clustered,
  assigned stable/blinded identifiers, and reformatted into scenario-writer and
  screening JSONL. These are draft adaptations and are not final Topics.

Raw Anthropic and MMLU-Pro source snapshots are Git-ignored, but tracked packets
redistribute selected or derived text. Downstream users must therefore retain
the applicable upstream attribution, license reference, and this change notice
when sharing those packets or further adaptations. No upstream endorsement is
stated or implied.
