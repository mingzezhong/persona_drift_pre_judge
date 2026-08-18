"""Generated-token-only anti-repetition controls for OLMo engineering pilots."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import torch
from torch import Tensor
from transformers import (
    LogitsProcessor,
    LogitsProcessorList,
    NoRepeatNGramLogitsProcessor,
    RepetitionPenaltyLogitsProcessor,
)

from .activation import pooled_residual_hooks, stack_captures
from .conversation import render_conversation_ids
from .modeling import (
    GenerationCapture,
    LoadedTarget,
    capture_pre_response,
    generation_eos_token_ids,
    generation_forbidden_token_ids,
    input_device,
    trim_trailing_stop_token,
)


class GeneratedOnlyNoRepeatNGramLogitsProcessor(LogitsProcessor):
    """Apply no-repeat n-grams after the prompt boundary only."""

    def __init__(self, ngram_size: int, prompt_ignore_length: int) -> None:
        if ngram_size < 2:
            raise ValueError("generated-only no-repeat n-gram size must be >= 2")
        if prompt_ignore_length < 0:
            raise ValueError("prompt ignore length must be nonnegative")
        self.prompt_ignore_length = prompt_ignore_length
        self.processor = NoRepeatNGramLogitsProcessor(ngram_size)

    def __call__(self, input_ids: Tensor, scores: Tensor) -> Tensor:
        generated_ids = input_ids[:, self.prompt_ignore_length :]
        return self.processor(generated_ids, scores)


def prepare_generation_controls(
    generation: Mapping[str, Any], *, prompt_length: int
) -> tuple[dict[str, Any], LogitsProcessorList]:
    """Remove custom config keys and construct generated-only processors."""

    settings = dict(generation)
    penalty = settings.pop("generated_only_repetition_penalty", None)
    ngram_size = settings.pop("generated_only_no_repeat_ngram_size", None)
    processors = LogitsProcessorList()
    if penalty is not None:
        penalty = float(penalty)
        if penalty <= 1.0:
            raise ValueError("generated-only repetition penalty must be > 1")
        processors.append(
            RepetitionPenaltyLogitsProcessor(
                penalty, prompt_ignore_length=prompt_length
            )
        )
    if ngram_size is not None:
        processors.append(
            GeneratedOnlyNoRepeatNGramLogitsProcessor(
                int(ngram_size), prompt_ignore_length=prompt_length
            )
        )
    return settings, processors


@torch.inference_mode()
def generate_and_capture_repetition_controlled_conversation(
    target: LoadedTarget,
    *,
    messages: Sequence[Mapping[str, str]],
    seed: int,
    generation: dict[str, Any],
) -> GenerationCapture:
    """Generate a turn with prompt-excluding repetition controls."""

    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    prompt_ids = render_conversation_ids(target.tokenizer, messages)
    pre_response = capture_pre_response(target.model, prompt_ids)
    prompt_length = prompt_ids.shape[1]
    ids = prompt_ids.to(input_device(target.model))
    attention_mask = torch.ones_like(ids)

    eos_token_ids = generation_eos_token_ids(target.tokenizer)
    forbidden_token_ids = generation_forbidden_token_ids(target.tokenizer)
    generation_kwargs, processors = prepare_generation_controls(
        generation, prompt_length=prompt_length
    )
    controls: dict[str, Any] = {}
    if forbidden_token_ids:
        controls["bad_words_ids"] = [[token_id] for token_id in forbidden_token_ids]
    if processors:
        controls["logits_processor"] = processors
    output_ids = target.model.generate(
        input_ids=ids,
        attention_mask=attention_mask,
        pad_token_id=target.tokenizer.pad_token_id,
        eos_token_id=eos_token_ids,
        **controls,
        **generation_kwargs,
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
