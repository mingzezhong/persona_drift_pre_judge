# Cross-model target technical amendment v1

## Timing and reason

This amendment was made on 2026-08-17 before any cross-model target response,
activation, trajectory, or outcome was generated. The measurement-development
protocol had reserved `meta-llama/Llama-3.1-8B-Instruct`, but the CETUS account
could read public repository metadata and could not download the gated model at
the pinned revision: the preflight request returned HTTP 401.

The study will not use an unofficial mirror or bypass the model's access terms.
The untouched replication target is therefore changed for an access reason,
not because of any observed replication outcome.

## Replacement target

- model: `allenai/OLMo-2-1124-7B-Instruct`;
- revision: `470b1fba1ae01581f270116362ee4aa1b97f4c84`;
- repository status at preflight: public, non-private, and ungated;
- downloaded config SHA256:
  `ff8cc8709a229515676797ab6f343a09391041c9a8fbbc78bfec5be4c2e3664e`;
- architecture recorded by the pinned config: 32 layers, hidden size 4096,
  native BF16.

OLMo is a model family distinct from the Qwen target and from all three frozen
measurement judges. It preserves the intended approximately 7B cross-family
test while making the artifact reproducibly accessible.

## Pre-outcome vector construction

Qwen persona vectors cannot be loaded into OLMo because their hidden sizes
differ. Before any OLMo trajectory is generated, the 48 already accepted
contrastive extraction responses are teacher-forced through the pinned OLMo
model. Response-token-mean residual activations are collected at all layers and
the vector for each axis is the mean target activation minus the mean contrast
activation. All 12 complete accepted pairs per axis are included; no OLMo
outcome or trajectory is used for selection. Layer 20 remains the fixed
monitoring layer.

Vector construction is a separate frozen phase. Its output hash must be added
to the final cross-model preregistration before OLMo trajectory generation is
submitted. No target-generation threshold, topic, seed, or measurement rule may
be selected from the vector-construction output.

