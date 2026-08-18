import pytest

from scripts.generate_extraction_data import generation_settings


def test_generation_settings_accept_min_new_tokens() -> None:
    config = {
        "generation": {
            "max_new_tokens": 160,
            "min_new_tokens": 40,
            "temperature": 0.7,
            "top_p": 0.9,
            "do_sample": True,
        }
    }
    assert generation_settings(config)["min_new_tokens"] == 40


def test_generation_settings_reject_unknown_key() -> None:
    with pytest.raises(ValueError, match="unsupported generation settings"):
        generation_settings({"generation": {"unexpected": 1}})
