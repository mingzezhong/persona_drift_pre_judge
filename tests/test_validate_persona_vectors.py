import pytest
import torch

from scripts.validate_persona_vectors import validate_vectors


def test_valid_vectors_report_reference_layer_norm() -> None:
    summary = validate_vectors(
        {"vectors": {"axis": torch.ones(3, 4)}, "metadata": {"source": "test"}},
        expected_shape=(3, 4),
        reference_layer=1,
    )
    assert summary["axes"]["axis"]["reference_layer_norm"] == 2.0


def test_wrong_shape_and_nonfinite_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="expected"):
        validate_vectors(
            {"vectors": {"axis": torch.ones(2, 4)}},
            expected_shape=(3, 4),
            reference_layer=1,
        )
    bad = torch.ones(3, 4)
    bad[0, 0] = float("nan")
    with pytest.raises(ValueError, match="non-finite"):
        validate_vectors(
            {"vectors": {"axis": bad}},
            expected_shape=(3, 4),
            reference_layer=1,
        )
