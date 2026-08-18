import pytest

from persona_drift.conversation import validate_conversation_messages


def test_valid_conversation_ends_with_user() -> None:
    validate_conversation_messages(
        [
            {"role": "system", "content": "Persona"},
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Reply"},
            {"role": "user", "content": "Next"},
        ]
    )


@pytest.mark.parametrize(
    "messages",
    [
        [{"role": "user", "content": "Missing system"}],
        [
            {"role": "system", "content": "Persona"},
            {"role": "assistant", "content": "Wrong role"},
        ],
        [
            {"role": "system", "content": "Persona"},
            {"role": "user", "content": "Question"},
            {"role": "assistant", "content": "Reply"},
        ],
    ],
)
def test_invalid_conversation_is_rejected(messages: list[dict[str, str]]) -> None:
    with pytest.raises(ValueError):
        validate_conversation_messages(messages)
