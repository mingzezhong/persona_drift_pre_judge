import torch

from persona_drift.repetition_control import prepare_generation_controls
from scripts.generate_repetition_control_smoke import repetition_generation_settings


def test_custom_controls_are_removed_from_hf_kwargs() -> None:
    settings, processors = prepare_generation_controls(
        {
            "max_new_tokens": 384,
            "do_sample": True,
            "generated_only_repetition_penalty": 1.05,
            "generated_only_no_repeat_ngram_size": 4,
        },
        prompt_length=4,
    )
    assert settings == {"max_new_tokens": 384, "do_sample": True}
    assert len(processors) == 2


def test_repetition_penalty_ignores_prompt_tokens() -> None:
    _, processors = prepare_generation_controls(
        {"generated_only_repetition_penalty": 2.0}, prompt_length=3
    )
    input_ids = torch.tensor([[4, 5, 6, 7]])
    scores = torch.ones((1, 10))
    processed = processors(input_ids, scores.clone())
    assert processed[0, 4].item() == 1.0
    assert processed[0, 5].item() == 1.0
    assert processed[0, 6].item() == 1.0
    assert processed[0, 7].item() == 0.5


def test_no_repeat_ngram_ignores_prompt_but_blocks_generated_repeat() -> None:
    _, processors = prepare_generation_controls(
        {"generated_only_no_repeat_ngram_size": 4}, prompt_length=4
    )
    scores = torch.zeros((1, 12))
    prompt_match_only = torch.tensor([[1, 2, 3, 4, 1, 2, 3]])
    first = processors(prompt_match_only, scores.clone())
    assert torch.isfinite(first[0, 4])

    generated_repeat = torch.tensor([[8, 8, 8, 8, 1, 2, 3, 4, 1, 2, 3]])
    second = processors(generated_repeat, scores.clone())
    assert torch.isneginf(second[0, 4])


def test_smoke_generation_settings_accept_only_frozen_controls() -> None:
    config = {
        "generation": {
            "max_new_tokens": 384,
            "min_new_tokens": 24,
            "temperature": 0.7,
            "top_p": 0.9,
            "do_sample": True,
            "generated_only_repetition_penalty": 1.10,
            "generated_only_no_repeat_ngram_size": 4,
        }
    }
    assert repetition_generation_settings(config) == config["generation"]
