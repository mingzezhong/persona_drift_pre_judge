# Model and hardware decision

## Decision

The study uses the following open-weight target models in this order:

1. `Qwen/Qwen2.5-7B-Instruct` — primary model for all pilot, forecasting,
   intervention, and ablation experiments.
2. `meta-llama/Llama-3.1-8B-Instruct` — confirmatory model used only after the
   Qwen protocol and thresholds are frozen.
3. `google/gemma-3-4b-it` — optional BILLY-alignment check if time and compute
   remain; it is not required for the main claim.

Qwen is the primary model because it is used by both BILLY and the closest
Persona Vectors work, has an Apache-2.0 license, and is small enough for the
available hardware. Llama provides a stronger cross-family replication than a
second Qwen checkpoint. Gemma is retained only to compare directly with all
three BILLY backbones; its multimodal implementation and gated terms add
engineering work that does not strengthen the pilot's main causal question.

Llama and Gemma are open-weight models with model-specific licenses, not
Apache-style open-source releases. Access approval must be completed before a
replication run.

## Relation to BILLY

BILLY extracts a layer-specific persona vector as the difference between the
mean response-token residual activations of positive and negative corpora. Its
main steering setting is layer 20 with coefficient 2.0, with layer and
coefficient ablations.

We reproduce that extraction procedure in Phase 1. We do not assume that layer
20 is optimal for pre-drift forecasting. Layer 20 is a preregistered reference;
the forecasting layer is selected on the validation split only and then frozen.

## CETUS Blackwell execution policy

The allocated node exposes two NVIDIA RTX PRO 6000 Blackwell Server Edition
GPUs with roughly 96 GiB each, compute capability 12.0, and working native
BF16 under PyTorch 2.9.1/CUDA 12.8. Therefore:

- use `torch.bfloat16` for primary model inference and activation extraction;
- enable TF32 for any FP32 CUDA matrix multiplications;
- use standard Transformers/PyTorch attention (`eager` initially) so the
  activation-hook path remains simple and auditable;
- do not require FlashAttention 2, FP8, or vLLM kernels for the pilot;
- do not quantize the target model in the primary experiments because
  quantization may change activation geometry;
- run under `torch.inference_mode()` and keep the model in `eval()` mode;
- pin exact model revisions and package versions before the full experiment.

- place one BF16 7B/8B model replica on each GPU and split independent
  examples or trajectories across the two replicas;
- use separate worker output directories, then merge manifests after both
  workers finish, to avoid concurrent appends to one JSONL file;
- never pool full token-by-layer activations for an entire generated sequence.
  Store only the last-prompt-token vector and response-token mean per layer.

The observed runtime baseline is two visible GPUs, driver 580.142, PyTorch
2.9.1+cu128, Transformers 4.57.6, and successful BF16 matrix multiplication.
The hardware check is repeated at the start of each scheduled experiment.

## Initial precision invariance check

Before collecting trajectories, run a held-out prompt subset twice:

1. BF16 target configuration;
2. FP32 on a small subset that fits, with FP16 as an optional secondary check.

Record output agreement, persona projection rank correlation, and classification
AUROC. This is a diagnostic, not a requirement that BF16 equal FP32 exactly.
