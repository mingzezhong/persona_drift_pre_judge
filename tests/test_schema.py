import pytest

from persona_drift.schema import CheckpointRecord, ExtractionExample


def test_extraction_example_serializes() -> None:
    record = ExtractionExample(
        example_id="e1",
        prompt_id="p1",
        axis="independent_sycophantic",
        polarity="target",
        system="Be independent.",
        user="Evaluate this claim.",
        response="The evidence is mixed.",
        model="test/model",
        model_revision="abc123",
        seed=0,
    )
    assert record.to_dict()["polarity"] == "target"


def test_extraction_example_rejects_invalid_judge_score() -> None:
    with pytest.raises(ValueError, match="judge_score"):
        ExtractionExample(
            example_id="e1",
            prompt_id="p1",
            axis="axis",
            polarity="contrast",
            system="System.",
            user="User.",
            response="Response.",
            model="test/model",
            model_revision="abc123",
            seed=0,
            judge_score=1.2,
        )


def test_checkpoint_requires_prefix_hash() -> None:
    with pytest.raises(ValueError, match="prefix_hash"):
        CheckpointRecord(
            trajectory_id="t1",
            axis="axis",
            condition="neutral",
            topic="topic",
            seed=0,
            turn=5,
            prefix_hash="",
            model="test/model",
            model_revision="abc123",
        )

