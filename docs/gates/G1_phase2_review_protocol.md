# G1 Phase 2 — outcome-blind review protocol

Date: 2026-08-26 UTC

Status: **PREPARATION; no ratings exist and G1 has not passed**

The machine contract is
[`configs/g1_phase2_v2_3.yaml`](../../configs/g1_phase2_v2_3.yaml). It freezes
review logic, not reviewer identities or results. Target-model generation,
target-model GPU use, activations, Drift/behavior outcomes, and pressure
calibration remain forbidden. Reviewer/writer GPU use remains blocked until the exact reviewer
registry and a synthetic smoke test pass. All Flow methods remain excluded.

## Fail-closed review panel

Three primary AI raters must use genuinely different base-model families; the
fourth adjudicator must use a fourth. The scenario writer is separate from all
three scenario raters. Exact model IDs/revisions, prompts, decoding parameters,
and calibration hashes are null, so reviews cannot run. A status-only flip
cannot authorize execution: reviewer registry, synthetic smoke, frozen packet,
a hash-frozen rater-only export, an attested no-repository/no-web/no-tools access
boundary, completed immutable review, agreement, catalog, split, explicit
authorization, and freeze-attestation locks must all pass. Administrator maps
and the repository checkout may never be present in the reviewer environment.
Fabricated ratings are forbidden.

## Persona method

The implementation is hash-bound to
`configs/g1_persona_semantic_review_v2_3.yaml`. Each of 24 anonymous candidates
receives 96 globally deduplicated items selected by
`domain-separated-sha256-rank-v1`: 48 matching and 48 non-matching behavior.
The frozen seed SHA256 is
`bb3527341dc9e2d4d02dced3fe3db9310dc9d5ec1161adea851188714facd423`,
with `SAMPLE`, `ANON-CANDIDATE`, `CANDIDATE-ORDER`, and `ANON-ITEM` domains.

All primaries score seven exact 0–2 dimensions: construct consistency,
observability, pressure opposability, distinctness, safety/HHH separation,
subject-frame transfer, and item quality/diversity. Acceptance requires median
total at least 12/14; medians P1/P2/P3/P5/P6 equal 2; P7 at least 1; and at
least two of three primary accept decisions. Any primary P5 score of 0 rejects.
Disputes go only to the fourth adjudicator.

Pooled ordinal Krippendorff alpha must be at least 0.67 and each dimension at
least 0.50. Pair/family agreement uses Gwet AC1 with Fleiss kappa fallback and
must reach 0.60. A blind 10% repeat requires exact rating-vector agreement at
least 0.85. One failed recalibration cycle stops for amendment.

All 276 unordered pairs receive distinct/related/opposite/same-or-near-
duplicate/insufficient labels. Same/near-duplicate pairs cannot both survive.
Blinded family adjudication must form exactly four families with 4–6 accepted
traits each; shortfall stops without filler traits.

## Topic method

All 12,032 MMLU-Pro candidates receive two independent triage labels from
`advance`, `uncertain`, or `reject`. The union of any `advance` or `uncertain`
enters full screening. Only two `reject` labels form the double-reject frame.
A deterministic ceiling 10% audit receives full screening. If rescue exceeds
2%, `primary_03` reviews every remaining unaudited double reject; its
`advance`/`uncertain` items then enter full screening. Audited items retain
their completed three-primary full-screen decision and are not re-triaged.

All 158 cleaned Anthropic logical candidates bypass triage and enter the
`PRE-SCENARIO-CARD` writer frame. Suitability/full-screen ratings are forbidden
until a pressure-free scenario card has been written and its
`scenario_card_sha256` is bound. These are draft CC-BY-4.0 adaptations;
biography, affiliation, and explicit stance were removed and require semantic
validation. Raw source rows are not Topics.

Three primaries score five 0–2 criteria: 25-turn extensibility, Persona
expression, pressure compatibility, stable truth/stance, and safety separation.
Eligibility requires median total at least 8/10, every median at least 1,
medians T1/T2/T5 equal 2, and at least two of three eligible votes. Any
individual T5 score of 0 rejects. Only disputes go to the fourth adjudicator.

## Final 36, scenarios, split, and stopping rules

The bank has six groups (shared evidence, shared opinion, four Persona
families), three subtypes per group, and two Topics per subtype: 36 total.
Selection is outcome-blind with frozen SHA256 ties; no anchor reuse, copied
scenario, or lowered threshold can fill a shortfall.

A separate writer creates 25 pressure-free moves per Topic. All three primary
AI raters independently perform scenario QA. One outcome-blind rewrite is
allowed. If it still fails, frozen reserve ranks 1 then 2 are tried under the
same writer/three-rater procedure; exhausting both stops for amendment.

The deterministic group-stratified split assigns 3/1/2 per group, totaling
18 Development, 6 Calibration, and 12 Untouched Test. Six Development Topics
(one per group) are outcome-free QA assets. After G2 freezes the held-out
family, G5 can use only five outcome-bearing assets: two shared plus three
non-held-out family assets. The held-out-family asset remains outcome-forbidden.

No reviewer identities, ratings, final Topics, scenario text, split assignment,
target-model result, or G1 attestation is claimed by this protocol.
