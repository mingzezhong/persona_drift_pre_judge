import json
from pathlib import Path

import pytest
import torch

from persona_drift.extraction import validate_extraction_run


def write_pair(tmp_path: Path, *, omit_contrast: bool = False) -> Path:
    records = []
    for polarity in ("target", "contrast"):
        if polarity == "contrast" and omit_contrast:
            continue
        activation_path = tmp_path / f"{polarity}.pt"
        torch.save(
            {
                "response_token_mean": torch.ones(2, 3),
                "last_prompt_token": torch.zeros(2, 3),
            },
            activation_path,
        )
        records.append(
            {
                "example_id": f"example-{polarity}",
                "prompt_id": "prompt-1",
                "axis": "axis-1",
                "polarity": polarity,
                "system": "system",
                "user": "user",
                "response": "response",
                "model": "model",
                "model_revision": "revision",
                "seed": 0,
                "generation": {"do_sample": False, "max_new_tokens": 8},
                "response_token_count": 5,
                "stop_token_id": None,
                "activation_path": str(activation_path),
            }
        )
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    return manifest


def test_valid_pair_returns_summary(tmp_path: Path) -> None:
    summary = validate_extraction_run(write_pair(tmp_path), expected_shape=(2, 3))
    assert summary.examples == 2
    assert summary.pairs == 1
    assert summary.activation_shape == [2, 3]
    assert len(summary.manifest_sha256) == 64
    assert summary.generation_qc["max_length_examples"] == 0


def test_incomplete_pair_is_rejected(tmp_path: Path) -> None:
    manifest = write_pair(tmp_path, omit_contrast=True)
    with pytest.raises(ValueError, match="incomplete contrastive pair"):
        validate_extraction_run(manifest)


def test_wrong_activation_shape_is_rejected(tmp_path: Path) -> None:
    manifest = write_pair(tmp_path)
    with pytest.raises(ValueError, match=r"expected \(3, 4\)"):
        validate_extraction_run(manifest, expected_shape=(3, 4))
