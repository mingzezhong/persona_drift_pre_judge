from pathlib import Path

import yaml


def test_gate_b_has_frozen_disjoint_balanced_splits() -> None:
    extraction = yaml.safe_load(
        Path("data/templates/persona_axes_v3.yaml").read_text(encoding="utf-8")
    )
    gate_b = yaml.safe_load(
        Path("data/templates/persona_gate_b.yaml").read_text(encoding="utf-8")
    )
    extraction_ids = {item["id"] for item in extraction["extraction_prompts"]}
    held_out_ids = {item["id"] for item in gate_b["extraction_prompts"]}
    assert extraction_ids.isdisjoint(held_out_ids)
    splits = [item["split"] for item in gate_b["extraction_prompts"]]
    assert splits.count("validation") == 6
    assert splits.count("test") == 6
    assert gate_b["axes"].keys() == extraction["axes"].keys()
