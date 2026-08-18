import json
from pathlib import Path
import sys

import pytest
import yaml

from scripts.generate_partitioned_gate_a_trajectories import select_topic_ids
from scripts import merge_partitioned_gate_a_shards as partitioned_merge


FROZEN_TOPICS = [
    "municipal_water_reuse",
    "coastal_ferry_ticketing",
    "regional_food_cold_chain",
]


@pytest.mark.parametrize("topic_id", FROZEN_TOPICS)
def test_partition_selects_exactly_one_frozen_topic(topic_id: str) -> None:
    assert select_topic_ids(FROZEN_TOPICS, topic_id) == [topic_id]


def test_partition_rejects_topic_outside_frozen_design() -> None:
    with pytest.raises(ValueError, match="topic is not configured"):
        select_topic_ids(FROZEN_TOPICS, "unregistered_topic")


def test_partition_selection_does_not_mutate_frozen_topic_list() -> None:
    topics = list(FROZEN_TOPICS)
    select_topic_ids(topics, topics[1])
    assert topics == FROZEN_TOPICS


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def build_partitioned_merge_fixture(tmp_path: Path) -> tuple[Path, Path]:
    output_dir = tmp_path / "out"
    config = {
        "mode": "test",
        "data": {
            "output_dir": str(output_dir),
            "axes": ["axis_a"],
            "topics": ["topic_a", "topic_b"],
            "conditions": ["neutral"],
            "seeds": [1],
            "checkpoint_turns": [0],
            "total_turns": 1,
        },
        "generation": {"max_new_tokens": 8},
        "generation_quality": {
            "forbidden_text_markers": ["<forbidden>"],
            "max_role_start_rate": 0.0,
            "max_length_rate": 0.0,
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    config_hash = partitioned_merge.sha256(config_path)
    for topic_id in config["data"]["topics"]:
        shard_dir = output_dir / "shards_v2" / "axis_a" / topic_id
        trajectory_path = shard_dir / "trajectories.jsonl"
        probe_path = shard_dir / "probes.jsonl"
        trajectory_id = f"trajectory-{topic_id}"
        write_jsonl(
            trajectory_path,
            [
                {
                    "trajectory_id": trajectory_id,
                    "axis": "axis_a",
                    "topic": topic_id,
                    "config_sha256": config_hash,
                    "turns": [
                        {
                            "response": "ok",
                            "response_token_count": 2,
                            "stop_token_id": 1,
                        }
                    ],
                }
            ],
        )
        write_jsonl(
            probe_path,
            [
                {
                    "example_id": f"probe-{topic_id}",
                    "trajectory_id": trajectory_id,
                    "axis": "axis_a",
                    "topic": topic_id,
                    "response": "ok",
                    "response_token_count": 2,
                    "stop_token_id": 1,
                }
            ],
        )
        summary = {
            "axis": "axis_a",
            "topics": [topic_id],
            "config_sha256": config_hash,
            "trajectories": 1,
            "probes": 1,
            "trajectories_sha256": partitioned_merge.sha256(trajectory_path),
            "probes_sha256": partitioned_merge.sha256(probe_path),
        }
        (shard_dir / "run_summary.json").write_text(
            json.dumps(summary), encoding="utf-8"
        )
    return config_path, output_dir


def test_partitioned_merge_accepts_complete_axis_topic_cells(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path, output_dir = build_partitioned_merge_fixture(tmp_path)
    monkeypatch.setattr(sys, "argv", ["merge", "--config", str(config_path)])
    partitioned_merge.main()
    merged = [
        json.loads(line)
        for line in (output_dir / "trajectories.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [record["topic"] for record in merged] == ["topic_a", "topic_b"]
    summary = json.loads(
        (output_dir / "merge_summary.json").read_text(encoding="utf-8")
    )
    assert summary["trajectories"] == 2
    assert summary["probes"] == 2
    assert summary["execution_partition"] == "axis_topic"
    assert summary["generation_gate_pass"] is True


def test_partitioned_merge_rejects_topic_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path, output_dir = build_partitioned_merge_fixture(tmp_path)
    probe_path = (
        output_dir / "shards_v2" / "axis_a" / "topic_b" / "probes.jsonl"
    )
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    probe["topic"] = "topic_a"
    write_jsonl(probe_path, [probe])
    monkeypatch.setattr(sys, "argv", ["merge", "--config", str(config_path)])
    with pytest.raises(ValueError, match="topic mismatch"):
        partitioned_merge.main()
