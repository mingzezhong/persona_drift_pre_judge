"""Loading and inference helpers for open-weight causal language models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch
from torch import Tensor, nn
from transformers import AutoModelForCausalLM, AutoTokenizer

from .activation import pooled_residual_hooks, stack_captures


@dataclass(frozen=True)
class LoadedTarget:
    model: nn.Module
    tokenizer: Any
    requested_revision: str | None
    resolved_revision: str


@dataclass(frozen=True)
class GenerationCapture:
    response_text: str
    response_activations: Tensor
    pre_response: Tensor
    response_token_ids: Tensor
    stop_token_id: int | None
    forbidden_token_ids: tuple[int, ...]


def load_target(
    model_name: str,
    *,
    revision: str | None = None,
    device_map: str = "auto",
    dtype: str | torch.dtype = "bfloat16",
    attention_implementation: str = "eager",
    allow_tf32: bool = True,
) -> LoadedTarget:
    """Load a target model using the configured CUDA precision policy."""

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for target-model extraction")

    resolved_dtype = resolve_dtype(dtype)
    if resolved_dtype is torch.bfloat16 and not torch.cuda.is_bf16_supported():
        raise RuntimeError("bfloat16 was requested but is not supported by this GPU")
    torch.backends.cuda.matmul.allow_tf32 = allow_tf32
    torch.backends.cudnn.allow_tf32 = allow_tf32

    common: dict[str, Any] = {}
    if revision is not None:
        common["revision"] = revision

    tokenizer = AutoTokenizer.from_pretrained(model_name, **common)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        dtype=resolved_dtype,
        device_map=device_map,
        low_cpu_mem_usage=True,
        attn_implementation=attention_implementation,
        **common,
    )
    model.eval()

    resolved = (
        getattr(model.config, "_commit_hash", None)
        or revision
        or "unresolved-model-revision"
    )
    return LoadedTarget(model, tokenizer, revision, str(resolved))


def resolve_dtype(dtype: str | torch.dtype) -> torch.dtype:
    """Resolve the small, explicit dtype vocabulary used by experiment configs."""

    if isinstance(dtype, torch.dtype):
        return dtype
    aliases = {
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
        "float16": torch.float16,
        "fp16": torch.float16,
        "float32": torch.float32,
        "fp32": torch.float32,
    }
    try:
        return aliases[dtype.casefold()]
    except KeyError as exc:
        raise ValueError(f"unsupported model dtype: {dtype!r}") from exc


def input_device(model: nn.Module) -> torch.device:
    """Return the embedding device, including for Accelerate-sharded models."""

    embeddings = model.get_input_embeddings()  # type: ignore[attr-defined]
    return embeddings.weight.device


def render_prompt_ids(tokenizer: Any, system: str, user: str) -> Tensor:
    """Render a two-message chat prefix ending at the assistant generation cue."""

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    encoded = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
    )
    if not isinstance(encoded, Tensor) or encoded.ndim != 2 or encoded.shape[0] != 1:
        raise TypeError("chat template must return one [batch, sequence] tensor")
    return encoded


def generation_eos_token_ids(tokenizer: Any) -> list[int]:
    """Return the model's configured end-of-message token IDs."""

    raw_eos = tokenizer.eos_token_id
    eos_ids = list(raw_eos) if isinstance(raw_eos, (list, tuple)) else [raw_eos]
    return list(
        dict.fromkeys(int(token_id) for token_id in eos_ids if token_id is not None)
    )


def generation_forbidden_token_ids(tokenizer: Any) -> list[int]:
    """Return role/tool control tokens that generation must never emit."""

    control_tokens = ("<|im_start|>", "<tool_call>", "</tool_call>")
    unknown_id = getattr(tokenizer, "unk_token_id", None)
    forbidden: list[int] = []
    for token in control_tokens:
        token_id = tokenizer.convert_tokens_to_ids(token)
        if (
            isinstance(token_id, int)
            and token_id >= 0
            and token_id != unknown_id
        ):
            forbidden.append(token_id)
    return list(dict.fromkeys(forbidden))


def generation_stop_token_ids(tokenizer: Any) -> list[int]:
    """Return all terminal/control IDs recognized by output validation."""

    return list(
        dict.fromkeys(
            generation_eos_token_ids(tokenizer)
            + generation_forbidden_token_ids(tokenizer)
        )
    )


def trim_trailing_stop_token(
    output_ids: Tensor,
    *,
    prompt_length: int,
    stop_token_ids: list[int],
) -> tuple[Tensor, int | None]:
    """Remove a terminal chat-control token before decoding and pooling."""

    if output_ids.ndim != 2 or output_ids.shape[0] != 1:
        raise ValueError("generation output must have shape [1, sequence]")
    if output_ids.shape[1] <= prompt_length:
        raise RuntimeError("generation produced no response tokens")
    final_id = int(output_ids[0, -1])
    if final_id not in stop_token_ids:
        return output_ids, None
    trimmed = output_ids[:, :-1]
    if trimmed.shape[1] <= prompt_length:
        raise RuntimeError("generation produced only a stop token")
    return trimmed, final_id


@torch.inference_mode()
def capture_pre_response(model: nn.Module, prompt_ids: Tensor) -> Tensor:
    """Capture final-prompt-token residuals as ``[layers, hidden]`` FP32 CPU."""

    ids = prompt_ids.to(input_device(model))
    with pooled_residual_hooks(model, pooling="last_prompt_token") as captures:
        model(input_ids=ids, use_cache=False)
    return stack_captures(captures)[:, 0, :]


@torch.inference_mode()
def generate_and_capture_response(
    target: LoadedTarget,
    *,
    system: str,
    user: str,
    seed: int,
    generation: dict[str, Any],
) -> GenerationCapture:
    """Generate once, then teacher-force once to capture response activations.

    Activation tensors have shape ``[layers, hidden]`` and are stored as FP32
    on CPU. Terminal chat-control tokens are excluded from text and pooling.
    """

    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    prompt_ids = render_prompt_ids(target.tokenizer, system, user)
    pre_response = capture_pre_response(target.model, prompt_ids)
    prompt_length = prompt_ids.shape[1]
    ids = prompt_ids.to(input_device(target.model))
    attention_mask = torch.ones_like(ids)

    eos_token_ids = generation_eos_token_ids(target.tokenizer)
    forbidden_token_ids = generation_forbidden_token_ids(target.tokenizer)
    decoding_controls: dict[str, Any] = {}
    if forbidden_token_ids:
        decoding_controls["bad_words_ids"] = [
            [token_id] for token_id in forbidden_token_ids
        ]
    output_ids = target.model.generate(
        input_ids=ids,
        attention_mask=attention_mask,
        pad_token_id=target.tokenizer.pad_token_id,
        eos_token_id=eos_token_ids,
        **decoding_controls,
        **generation,
    )
    output_ids, stop_token_id = trim_trailing_stop_token(
        output_ids,
        prompt_length=prompt_length,
        stop_token_ids=eos_token_ids,
    )
    response_ids = output_ids[:, prompt_length:]
    response_text = target.tokenizer.decode(response_ids[0], skip_special_tokens=True)

    full_attention_mask = torch.ones_like(output_ids)
    with pooled_residual_hooks(
        target.model,
        pooling="response_token_mean",
        response_start=prompt_length,
    ) as captures:
        target.model(
            input_ids=output_ids,
            attention_mask=full_attention_mask,
            use_cache=False,
        )
    response_activations = stack_captures(captures)[:, 0, :]
    return GenerationCapture(
        response_text=response_text,
        response_activations=response_activations,
        pre_response=pre_response,
        response_token_ids=response_ids.detach().cpu(),
        stop_token_id=stop_token_id,
        forbidden_token_ids=tuple(forbidden_token_ids),
    )
