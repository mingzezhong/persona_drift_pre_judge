from scripts.merge_gate_a_shards import response_quality


def test_gate_a_response_quality_counts_markers_and_max_length() -> None:
    summary = response_quality(
        [
            {"response": "Normal", "response_token_count": 20, "stop_token_id": 10},
            {
                "response": "Bad <tool_call>",
                "response_token_count": 40,
                "stop_token_id": None,
            },
        ],
        max_new_tokens=40,
        forbidden_markers=["<tool_call>"],
    )
    assert summary["max_length_examples"] == 1
    assert summary["forbidden_text_marker_counts"] == {"<tool_call>": 1}
