import pytest
import torch

from scripts.reencode_persona_vectors import teacher_forced_ids, validate_source_rows


def row(axis: str, polarity: str, prompt: str = "p") -> dict:
    return {
        "example_id": f"{prompt}-{axis}-{polarity}",
        "prompt_id": prompt,
        "axis": axis,
        "polarity": polarity,
        "seed": 0,
        "accepted": True,
        "model": "source",
        "system": "system",
        "user": "user",
        "response": "response",
    }


def test_validate_source_rows_requires_complete_accepted_pairs() -> None:
    rows = [
        row("axis_a", "target"),
        row("axis_a", "contrast"),
        row("axis_b", "target"),
        row("axis_b", "contrast"),
    ]
    result = validate_source_rows(
        rows,
        axes=["axis_a", "axis_b"],
        expected_rows=4,
        expected_pairs_per_axis=1,
        source_model="source",
        require_all_accepted=True,
    )
    assert result["pairs_by_axis"] == {"axis_a": 1, "axis_b": 1}
    rows[0]["accepted"] = False
    with pytest.raises(ValueError, match="not accepted"):
        validate_source_rows(
            rows,
            axes=["axis_a", "axis_b"],
            expected_rows=4,
            expected_pairs_per_axis=1,
            source_model="source",
            require_all_accepted=True,
        )


class FakeTokenizer:
    eos_token_id = 2
    unk_token_id = 99

    def convert_tokens_to_ids(self, _token: str) -> int:
        return self.unk_token_id

    def apply_chat_template(self, messages, *, add_generation_prompt, return_tensors):
        assert return_tensors == "pt"
        if add_generation_prompt:
            return torch.tensor([[1, 4, 5]])
        assert messages[-1]["role"] == "assistant"
        return torch.tensor([[1, 4, 5, 7, 8, 2]])


def test_teacher_forced_ids_removes_terminal_token_and_preserves_response() -> None:
    ids, response_start = teacher_forced_ids(
        FakeTokenizer(), system="s", user="u", response="r"
    )
    assert response_start == 3
    assert ids.tolist() == [[1, 4, 5, 7, 8]]


class NonPrefixTokenizer(FakeTokenizer):
    def apply_chat_template(self, messages, *, add_generation_prompt, return_tensors):
        if add_generation_prompt:
            return torch.tensor([[1, 4, 5]])
        return torch.tensor([[1, 9, 5, 7, 2]])


def test_teacher_forced_ids_rejects_non_prefix_template() -> None:
    with pytest.raises(ValueError, match="not a prefix"):
        teacher_forced_ids(NonPrefixTokenizer(), system="s", user="u", response="r")

