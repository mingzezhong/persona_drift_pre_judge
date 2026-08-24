# Data status

No v2 corpus has been downloaded, transformed, or frozen. This directory will
contain only tracked source manifests, licenses, immutable item identifiers, and
transformation specifications. Raw and processed corpora are Git-ignored.

The protocol plans to construct the topic bank from public sources such as
Anthropic's model-written evaluations, MMLU-Pro, and Anthropic sycophancy
evaluations. PersonaGym is reserved for external generalization rather than
development. A source is not usable until its license, upstream revision, file
hash, selected item IDs, and deterministic transformation are recorded.

Required tracked manifest fields include:

- source name, canonical URL, license, and upstream revision;
- downloaded-file SHA256 and retrieval date;
- immutable source item ID and transformed topic ID;
- persona, pressure-family, and split eligibility metadata;
- transformation code revision and output hash.

The 30-topic `15 development / 5 calibration / 10 untouched test` allocation
must be frozen before any outcome-bearing run. Topic IDs—not individual prefixes
or forks—are the outer split unit.
