# Data status

No v2 corpus has been downloaded, transformed, or frozen. This directory will
contain only tracked source manifests, licenses, immutable item identifiers, and
transformation specifications. Raw and processed corpora are Git-ignored.

V2.2 separates four levels: behavioral family, independent persona trait,
prompt variant, and evaluation item.  Prompt variants and items are nested
records and never increase the reported persona count.  The endorsed sampling
direction is four families with 4--6 source-backed traits per family, but the
exact catalog is still open.

The topic bank remains 24 MMLU-Pro plus 6 Anthropic sycophancy anchors with a
15/5/10 topic split and six development pilot topics.  PersonaGym is reserved
for external generalization rather than development.
A source is not usable until its license, upstream revision, file
hash, selected item IDs, and deterministic transformation are recorded.

Required tracked manifest fields include:

- entity level (`family`, `trait`, `prompt_variant`, or `evaluation_item`) and parent IDs;
- persona generalization role (observed wording, unseen wording, unseen trait, or unseen family);
- evaluation-item role (trait definition, vector extraction, or held-out validation);
- source name, canonical URL, license, and upstream revision;
- downloaded-file SHA256 and retrieval date;
- immutable source item ID and transformed topic ID;
- persona, pressure-family, and split eligibility metadata;
- transformation code revision and output hash.

The persona and topic splits are orthogonal: holding out a wording, trait, or
family never permits a topic to cross its partition. A 25-turn scenario stores
25 content-only topic-move IDs separately from 25 pressure-template IDs.

The 30-topic `15 development / 5 calibration / 10 untouched test` allocation
must be frozen before any outcome-bearing run. Topic IDs—not individual prefixes
or forks—are the outer split unit.
