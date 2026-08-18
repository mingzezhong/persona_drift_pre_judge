"""Multi-turn generation with reduced activation capture."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import torch
from torch import Tensor

from .activation import pooled_residual_hooks, stack_captures
from .modeling import (
    GenerationCapture,
    LoadedTarget,
    capture_pre_response,
    generation_eos_token_ids,
    generation_forbidden_token_ids,
    input_device,
    trim_trailing_stop_token,
)


def validate_conversation_messages(
    messages: Sequence[Mapping[str, str]],
) -> None:
    """Require one system message followed by alternating user/assistant turns."""

    if len(messages) < 2:
        raise ValueError("conversation must contain a system message and user turn")
    if messages[0].get("role") != "system" or not messages[0].get("content", "").strip():
        raise ValueError("conversation must start with a non-empty system message")
    expected = "user"
    for index, message in enumerate(messages[1:], start=1):
        role = message.get("role")
        content = message.get("content", "")
        if role != expected:
            raise ValueError(
                f"message {index} has role {role!r}; expected {expected!r}"
            )
        if not content.strip():
            raise ValueError(f"message {index} has empty content")
        expected = "assistant" if expected == "user" else "user"
    if messages[-1].get("role") != "user":
        raise ValueError("conversation must end with the user turn to answer")


def render_conversation_ids(
    tokenizer: Any, messages: Sequence[Mapping[str, str]]
) -> Tensor:
    """Render a validated multi-turn chat prefix ending at the assistant cue."""

    validate_conversation_messages(messages)
    encoded = tokenizer.apply_chat_template(
        [dict(message) for message in messages],
        add_generation_prompt=True,
        return_tensors="pt",
    )
    if not isinstance(encoded, Tensor) or encoded.ndim != 2 or encoded.shape[0] != 1:
        raise TypeError("chat template must return one [batch, sequence] tensor")
    return encoded


@torch.inference_mode()
def generate_and_capture_conversation(
    target: LoadedTarget,
    *,
    messages: Sequence[Mapping[str, str]],
    seed: int,
    generation: dict[str, Any],
) -> GenerationCapture:
    """Generate the next assistant turn and capture pre/response residual means."""

    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    prompt_ids = render_conversation_ids(target.tokenizer, messages)
    pre_response = capture_pre_response(target.model, prompt_ids)
    prompt_length = prompt_ids.shape[1]
    ids = prompt_ids.to(input_device(target.model))
    attention_mask = torch.ones_like(ids)

    eos_token_ids = generation_eos_token_ids(target.tokenizer)
    forbidden_token_ids = generation_forbidden_token_ids(target.tokenizer)
    controls: dict[str, Any] = {}
    if forbidden_token_ids:
        controls["bad_words_ids"] = [[token_id] for token_id in forbidden_token_ids]
    output_ids = target.model.generate(
        input_ids=ids,
        attention_mask=attention_mask,
        pad_token_id=target.tokenizer.pad_token_id,
        eos_token_id=eos_token_ids,
        **controls,
        **generation,
    )
    output_ids, stop_token_id = trim_trailing_stop_token(
        output_ids,
        prompt_length=prompt_length,
        stop_token_ids=eos_token_ids,
    )
    response_ids = output_ids[:, prompt_length:]
    response_text = target.tokenizer.decode(response_ids[0], skip_special_tokens=True)

    with pooled_residual_hooks(
        target.model,
        pooling="response_token_mean",
        response_start=prompt_length,
    ) as captures:
        target.model(
            input_ids=output_ids,
            attention_mask=torch.ones_like(output_ids),
            use_cache=False,
        )
    return GenerationCapture(
        response_text=response_text,
        response_activations=stack_captures(captures)[:, 0, :],
        pre_response=pre_response,
        response_token_ids=response_ids.detach().cpu(),
        stop_token_id=stop_token_id,
        forbidden_token_ids=tuple(forbidden_token_ids),
    )
