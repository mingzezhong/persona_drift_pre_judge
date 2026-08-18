import pytest
import torch

from persona_drift.modeling import (
    generation_eos_token_ids,
    generation_forbidden_token_ids,
    generation_stop_token_ids,
    resolve_dtype,
    trim_trailing_stop_token,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("bfloat16", torch.bfloat16),
        ("bf16", torch.bfloat16),
        ("float16", torch.float16),
        ("fp32", torch.float32),
    ],
)
def test_resolve_dtype(name: str, expected: torch.dtype) -> None:
    assert resolve_dtype(name) is expected


def test_resolve_dtype_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="unsupported model dtype"):
        resolve_dtype("fp8")


class FakeTokenizer:
    eos_token_id = 20
    unk_token_id = 0

    def convert_tokens_to_ids(self, token: str) -> int:
        return {
            "<|im_start|>": 21,
            "<tool_call>": 22,
            "</tool_call>": 23,
        }.get(token, self.unk_token_id)


def test_generation_control_ids_separate_eos_from_forbidden_controls() -> None:
    tokenizer = FakeTokenizer()
    assert generation_eos_token_ids(tokenizer) == [20]
    assert generation_forbidden_token_ids(tokenizer) == [21, 22, 23]
    assert generation_stop_token_ids(tokenizer) == [20, 21, 22, 23]


def test_generation_controls_ignore_unknown_token_id() -> None:
    tokenizer = FakeTokenizer()
    tokenizer.unk_token_id = 23
    assert generation_forbidden_token_ids(tokenizer) == [21, 22]


def test_terminal_control_token_is_trimmed() -> None:
    output = torch.tensor([[1, 2, 3, 21]])
    trimmed, stop_token_id = trim_trailing_stop_token(
        output,
        prompt_length=2,
        stop_token_ids=[20, 21],
    )
    assert torch.equal(trimmed, torch.tensor([[1, 2, 3]]))
    assert stop_token_id == 21


def test_unterminated_generation_is_not_trimmed() -> None:
    output = torch.tensor([[1, 2, 3]])
    trimmed, stop_token_id = trim_trailing_stop_token(
        output,
        prompt_length=2,
        stop_token_ids=[20, 21],
    )
    assert torch.equal(trimmed, output)
    assert stop_token_id is None
