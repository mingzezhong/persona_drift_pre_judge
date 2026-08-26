from hashlib import sha256
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTICE_PATH = ROOT / "THIRD_PARTY_NOTICES.md"
MMLU_REVISION = "b189ec765aa7ed75c8acfea42df31fdae71f97be"
ANTHROPIC_REVISION = "84fcc677e52e1902d696c32cd1a6b663e70d3993"
EVIDENCE_SHA256 = {
    ROOT
    / "data"
    / "licenses"
    / f"mmlu_pro_{MMLU_REVISION}_dataset_card.md": (
        "4bd710f67da3fa359a33edce1b4b5816b3de416c823c2624ba5e89c2557d2a47"
    ),
    ROOT
    / "data"
    / "licenses"
    / f"anthropics_evals_{ANTHROPIC_REVISION}_LICENSE.txt": (
        "7e7170e3cebf88a9f60c7b8421418323c09304da1af4d5e90f4da1dc1c8a2661"
    ),
}


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_pinned_license_evidence_paths_and_bytes_are_exact() -> None:
    assert set(EVIDENCE_SHA256) == {
        ROOT
        / "data"
        / "licenses"
        / "mmlu_pro_b189ec765aa7ed75c8acfea42df31fdae71f97be_dataset_card.md",
        ROOT
        / "data"
        / "licenses"
        / "anthropics_evals_84fcc677e52e1902d696c32cd1a6b663e70d3993_LICENSE.txt",
    }
    for path, expected_sha256 in EVIDENCE_SHA256.items():
        assert path.is_file()
        assert _file_sha256(path) == expected_sha256


def test_evidence_contains_the_pinned_license_declarations() -> None:
    mmlu_card = next(path for path in EVIDENCE_SHA256 if "mmlu_pro" in path.name)
    anthropic_license = next(
        path for path in EVIDENCE_SHA256 if "anthropics_evals" in path.name
    )
    assert "license: mit" in mmlu_card.read_text(encoding="utf-8")
    assert "Creative Commons Attribution 4.0 International" in (
        anthropic_license.read_text(encoding="utf-8")
    )


def test_notice_records_attribution_revisions_and_material_changes() -> None:
    notice = " ".join(NOTICE_PATH.read_text(encoding="utf-8").split())
    required_literals = {
        "TIGER-Lab/MMLU-Pro",
        MMLU_REVISION,
        "10.57967/hf/2439",
        "Declared data license: MIT",
        "Anthropic's `evals` repository",
        ANTHROPIC_REVISION,
        "CC-BY-4.0",
        "Persona-derived packets",
        "anonymous candidate",
        "Topic-derived packets",
        "biography",
        "affiliation",
        "explicit user stance",
        "logically clustered",
        "reformatted",
        "Git-ignored",
        "tracked packets",
        "does not infer or add one",
    }
    assert all(literal in notice for literal in required_literals)
    assert "Copyright (c) Anthropic" not in notice
    assert "Copyright © Anthropic" not in notice
