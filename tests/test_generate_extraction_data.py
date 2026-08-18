from pathlib import Path

import pytest

from scripts.generate_extraction_data import (
    compose_system_prompt,
    prepare_output,
    select_axes,
    select_prompts,
)


def test_shared_system_constraint_is_appended_identically() -> None:
    shared = "Use three sentences."
    assert compose_system_prompt("Target trait.", shared).endswith(shared)
    assert compose_system_prompt("Contrast trait.", shared).endswith(shared)
    assert compose_system_prompt("Target trait.", None) == "Target trait."


def test_axis_and_prompt_selection_preserves_requested_order() -> None:
    axes = {"first": {"value": 1}, "second": {"value": 2}}
    prompts = [{"id": "p1"}, {"id": "p2"}]
    assert [name for name, _ in select_axes(axes, ["second", "first"])] == [
        "second",
        "first",
    ]
    assert [item["id"] for item in select_prompts(prompts, ["p2"])] == ["p2"]


def test_unknown_selection_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown persona axes"):
        select_axes({"known": {}}, ["typo"])
    with pytest.raises(ValueError, match="unknown extraction prompt IDs"):
        select_prompts([{"id": "known"}], ["typo"])


def test_prepare_output_refuses_nonempty_directory(tmp_path: Path) -> None:
    output = tmp_path / "run"
    output.mkdir()
    (output / "existing.txt").write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(FileExistsError, match="not empty"):
        prepare_output(output)
