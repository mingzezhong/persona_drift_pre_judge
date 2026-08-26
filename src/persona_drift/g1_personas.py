"""Build outcome-blind G1 Persona source and candidate manifests.

This module is deliberately limited to public-source provenance, immutable
source-item identities, candidate-family bookkeeping, and global duplicate
auditing.  It does not define Persona prompts, item-role assignments, holdout
assignments, model exposures, or experimental outcomes.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tarfile
from typing import Any, Iterable, Mapping, Sequence
import unicodedata
from urllib.request import Request, urlopen

import yaml


SOURCE_REPOSITORY = "https://github.com/anthropics/evals"
SOURCE_COMMIT = "84fcc677e52e1902d696c32cd1a6b663e70d3993"
SOURCE_COMMIT_DATE = "2023-01-03T23:20:15Z"
SOURCE_ROOT_TREE_SHA1 = "d670f1124df7ed80bab4fef6ad06d0f56a641f3d"
SOURCE_PERSONA_TREE_SHA1 = "e45c576bc2a05e2165b804d1b5726e7748a1b7ae"
SOURCE_PERSONA_PATH_LAST_COMMIT = "f6059a593f6feb0a500e8fe01f422a8ccfbdac09"
SOURCE_ARCHIVE_URL = (
    "https://github.com/anthropics/evals/archive/"
    f"{SOURCE_COMMIT}.tar.gz"
)
SOURCE_ARCHIVE_RELATIVE_PATH = (
    f"data/raw/anthropics-evals-{SOURCE_COMMIT}.tar.gz"
)
SOURCE_CHECKOUT_RELATIVE_PATH = f"data/raw/anthropics-evals-{SOURCE_COMMIT}"

LICENSE_SPDX = "CC-BY-4.0"
LICENSE_RELATIVE_PATH = "LICENSE"
LICENSE_GIT_BLOB_SHA1 = "2f244ac814036ecd9ba9f69782e89ce6b1dca9eb"
LICENSE_SHA256 = "7e7170e3cebf88a9f60c7b8421418323c09304da1af4d5e90f4da1dc1c8a2661"
PERSONA_README_RELATIVE_PATH = "persona/README.md"
PERSONA_README_GIT_BLOB_SHA1 = "47d2a88f4d74b1045c992258fbae92c2c17a4459"
PERSONA_README_SHA256 = "852ea378e5c6336fd6be5d707a3bf3bf298f3fc83cacb55f3676cc75981e48e7"

EXPECTED_PERSONA_JSONL_FILES = 135
EXPECTED_PERSONA_ROWS = 133_204
EXPECTED_QUESTION_PREFIX = 'Is the following statement something you would say?\n"'
EXPECTED_FIELDS = frozenset(
    {
        "question",
        "statement",
        "answer_matching_behavior",
        "answer_not_matching_behavior",
        "label_confidence",
    }
)
_SHA1_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")

PUBLIC_SOURCES_FILENAME = "public_sources_persona_v2_3.yaml"
CANDIDATE_POOL_FILENAME = "persona_candidate_pool_v2_3.yaml"
SAMPLING_FRAME_FILENAME = "persona_sampling_frame_draft_v2_3.yaml"
DEDUP_REPORT_FILENAME = "persona_dedup_v2_3.json"

G1_OPEN_STATUS = "OPEN_NOT_G1_PASS"
CANDIDATE_STATUS = "CANDIDATE_NOT_ADJUDICATED"
DRAFT_STATUS = "DRAFT_NOT_FROZEN"
UNIQUE_ITEM_STATUS = "CANDIDATE_GLOBALLY_UNIQUE_AFTER_G1_NORMALIZATION"
DUPLICATE_ITEM_STATUS = "EXCLUDED_NORMALIZED_DUPLICATE"
NORMALIZATION_RULE_ID = "unicode-nfkc-casefold-collapse-whitespace-v1"
RAW_LINE_HASH_RULE_ID = "exact-jsonl-line-bytes-excluding-terminal-lf-v1"
STABLE_ITEM_ID_RULE_ID = (
    "anthropic-evals-{commit8}-persona-{slug}-l{line6}-{raw_sha12}-v1"
)

EXCLUDED_UPSTREAM_FILES: tuple[Mapping[str, str], ...] = (
    {
        "source_path": "persona/high-discount-factor.jsonl",
        "status": "EXCLUDED_FROM_CANDIDATE_UNIVERSE",
        "reason": (
            "not listed among the paper-v1 Table 18 zero-shot Persona datasets; "
            "conceptually inverse-near-duplicate of low-discount-rate"
        ),
    },
    {
        "source_path": "persona/low-discount-factor.jsonl",
        "status": "EXCLUDED_FROM_CANDIDATE_UNIVERSE",
        "reason": (
            "not listed among the paper-v1 Table 18 zero-shot Persona datasets; "
            "conceptually inverse-near-duplicate of high-discount-rate"
        ),
    },
)


class G1PersonaAssetError(ValueError):
    """Raised when a locked public source or a G1-only contract is violated."""


@dataclass(frozen=True)
class TraitCandidateSpec:
    """Immutable source lock plus a provisional, unadjudicated family mapping."""

    slug: str
    candidate_family_id: str
    source_subject_type: str
    git_blob_sha1: str
    file_sha256: str
    expected_rows: int = 1_000

    def __post_init__(self) -> None:
        for field in ("slug", "candidate_family_id", "source_subject_type"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise G1PersonaAssetError(f"{field} must be a non-empty string")
        if not _SHA1_RE.fullmatch(self.git_blob_sha1):
            raise G1PersonaAssetError("git_blob_sha1 must be 40 lowercase hex characters")
        if not _SHA256_RE.fullmatch(self.file_sha256):
            raise G1PersonaAssetError("file_sha256 must be 64 lowercase hex characters")
        if isinstance(self.expected_rows, bool) or self.expected_rows <= 0:
            raise G1PersonaAssetError("expected_rows must be a positive integer")

    @property
    def source_path(self) -> str:
        return f"persona/{self.slug}.jsonl"

    @property
    def candidate_trait_id(self) -> str:
        return f"ae-persona-{self.slug}"


def _spec(
    slug: str,
    family: str,
    subject: str,
    blob: str,
    sha256: str,
) -> TraitCandidateSpec:
    return TraitCandidateSpec(slug, family, subject, blob, sha256)


TRAIT_CANDIDATES: tuple[TraitCandidateSpec, ...] = (
    _spec(
        "risk-averse",
        "decision_under_uncertainty_and_horizon",
        "person",
        "de2c72b7a78d592ac589685ca6f2efc3a04532fd",
        "0e22ad96b41189572fb4234855d42d9683c5762e7aa73e3cf01af3f378bd5064",
    ),
    _spec(
        "risk-neutral",
        "decision_under_uncertainty_and_horizon",
        "person",
        "798beba7c3d287240a7565c75b2ac56fd5ce4f71",
        "944c5dfd79415dfeb3a55777e4c2fd08ec5c681881ad7ac9ae9de34c049c8230",
    ),
    _spec(
        "risk-seeking",
        "decision_under_uncertainty_and_horizon",
        "person",
        "81a06a019d2eecaa710afe2f267716f071fde061",
        "de65fc47017bb2719189bba77460f315cf021a1532effe171e8c5454c7c08435",
    ),
    _spec(
        "optionality-preservation",
        "decision_under_uncertainty_and_horizon",
        "ai_system",
        "7fd22d364d851be137606e58c7de6cfcf7c7c161",
        "8cfcc8a9a52b4157d7cf26b889fd17ec67eac4bc79281e475298f3ce650a2fa4",
    ),
    _spec(
        "low-discount-rate",
        "decision_under_uncertainty_and_horizon",
        "person",
        "d57327487684a5b8e195f50bb213c3263dbfb752",
        "0717cd1f6b54bd02cbc96b6da91a59b9df4559c9ad2da68b3f1efb6c59db809d",
    ),
    _spec(
        "high-discount-rate",
        "decision_under_uncertainty_and_horizon",
        "person",
        "6ce1540d901f605884131e12d421417f8fa628cd",
        "acb8177abd9076a9a4a1c46120188d6fbc87a88e20021a430a7708f731b8bedf",
    ),
    _spec(
        "stands-its-ground",
        "deference_and_self_direction",
        "ai_system",
        "d8dd594c02ff77e8540ef7c2b0215b2cd24bde98",
        "8d1cc7a6595bd04017375f20de737bd6a4d67a439e0ac657b01c957e8a3ad5ad",
    ),
    _spec(
        "willingness-to-defer-to-authorities",
        "deference_and_self_direction",
        "person",
        "5424ee118d9546a6e757ac7b2134976c1a09967d",
        "62e6d61a6a187636cfea74284a18155889cc5e0ae43e21a3a61c0db484196fb4",
    ),
    _spec(
        "willingness-to-defer-to-experts",
        "deference_and_self_direction",
        "person",
        "96647e5ea4dddac30b26bd899b09dc6543946d90",
        "6d6e01850d01cb7f8a264ee3bc3ea520d73d522a36dd6dcdc5dbd3637585e5ef",
    ),
    _spec(
        "desire-for-independence-from-human-oversight",
        "deference_and_self_direction",
        "ai_system",
        "4cee8110485b73064b520d5a94a3e96a90d20d6b",
        "10f153f307ebede42a1d5303fe370185eca84e27f4e5893c387be236d26ff723",
    ),
    _spec(
        "believes-it-knows-better-than-humans-about-how-the-system-should-behave",
        "deference_and_self_direction",
        "ai_system",
        "45a2272dfc1e5049a7fb6711ed521b955fe51c66",
        "e102b25fb99f1c38415d63e7e923695deec988e72c4e52327fd0bdb0b2a01a30",
    ),
    _spec(
        "believes-it-knows-better-than-humans-about-how-to-help-humans",
        "deference_and_self_direction",
        "ai_system",
        "6164bd0e00782bbd41c403c384d6385176703576",
        "6f42eeebed25e90af6e39d4fc187db155ab4aefac4917c921fa920bcb85a527f",
    ),
    _spec(
        "agreeableness",
        "interpersonal_prosocial_vs_instrumental",
        "person",
        "301b6d631b921c9a5803c94b0b1f560205d89964",
        "8caa0fa07946370fb4ec38dd82eda7d3a86591c1dc701d2e645ae33c3239f5ce",
    ),
    _spec(
        "conscientiousness",
        "interpersonal_prosocial_vs_instrumental",
        "person",
        "706a93d6c606b12a0411c4f0c0b5756e0ada9f7a",
        "fd05517c0a453a7b47d19964ac6528db394c8cd00a5f74cc11d91479a20b90a6",
    ),
    _spec(
        "machiavellianism",
        "interpersonal_prosocial_vs_instrumental",
        "person",
        "dd6c9c8ba5662d4b52aec08e5d1d32926b79fcc1",
        "1803c65d56d8ab0185c8aba8c08a8348ed79cb398f055a5088c07a4cea732ff4",
    ),
    _spec(
        "psychopathy",
        "interpersonal_prosocial_vs_instrumental",
        "person",
        "9d5cee2901d0b8cea4e9030b74ff060b47955e21",
        "299a6307e2d40a82f2667e2db3dc118fbe588e4cf80194be1e09748709bf1fce",
    ),
    _spec(
        "narcissism",
        "interpersonal_prosocial_vs_instrumental",
        "person",
        "5f07a7b99332152a50322e7e790a2aeaba4cbafd",
        "32d93f6b2eddd5c155cf9d6d825a03e1c03cc3c0ac2e6c9382e3f981d9fc4120",
    ),
    _spec(
        "ends-justify-means",
        "interpersonal_prosocial_vs_instrumental",
        "person",
        "25c3b5f2e19441c4a28cd721a526d14c026954c0",
        "30e2f6cc53395203e296d08549b86ed441e0c3194cbf4ba3b7a61dda521358f4",
    ),
    _spec(
        "desire-for-acquiring-power",
        "power_and_impact_orientation",
        "ai_system",
        "1dbff01385b4e91cfe677335ebdfa227a41b93ed",
        "f70c0d00068dd96591b08dab60e9d8827ea12f34daca03a68a3544ac39007bdb",
    ),
    _spec(
        "no-power-discomfort",
        "power_and_impact_orientation",
        "person",
        "46fdcf51136157ce7baae4e1b3502b53976cce73",
        "bcb0b3d66f39dac964d0f197bd7fb54f08e0f6b07beffeb698624a530cfe9b43",
    ),
    _spec(
        "desire-for-powerful-positions",
        "power_and_impact_orientation",
        "ai_system",
        "50e7426556c992d031ac1144083386012b00e790",
        "8b48d2948e568d0740b6f71ac2cc6bc564ced2d6440e1f3ef2321309fb2d1eb6",
    ),
    _spec(
        "desire-to-influence-world",
        "power_and_impact_orientation",
        "ai_system",
        "8e8442dd27a313361cac5e627e03ee7f9aac8d66",
        "d37e746e6b23d5fc479f1770ed6948134ff0e5667295596c43779be582e64581",
    ),
    _spec(
        "desire-to-maximize-impact-on-world",
        "power_and_impact_orientation",
        "ai_system",
        "958a94a025965ac630c1cf3c9903066e0c3957b0",
        "c0af995d29de2ce02b219aeb4869311f0988d4a057baaf74dab8c2e24597c859",
    ),
    _spec(
        "desire-to-minimize-impact-on-world-while-being-useful",
        "power_and_impact_orientation",
        "ai_system",
        "34994b7f368d52b8051e9fde5252332f6943e681",
        "c12a5b73d3468e44bdbd00069e4f1e487b92eac1c4fe26cb23ddd352e6852031",
    ),
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_blob_sha1(value: bytes) -> str:
    header = f"blob {len(value)}\0".encode("ascii")
    return hashlib.sha1(header + value).hexdigest()


def git_tree_sha1(entries: Iterable[tuple[str, str]]) -> str:
    """Compute a flat 100644 Git tree hash from ``(name, blob_sha1)`` entries."""

    ordered = sorted(entries, key=lambda item: item[0].encode("utf-8"))
    body = b"".join(
        b"100644 " + name.encode("utf-8") + b"\0" + bytes.fromhex(blob_sha1)
        for name, blob_sha1 in ordered
    )
    return hashlib.sha1(f"tree {len(body)}\0".encode("ascii") + body).hexdigest()


def normalize_statement(value: str) -> str:
    """Apply only the frozen NFKC/case/whitespace normalization rule."""

    if not isinstance(value, str):
        raise G1PersonaAssetError("statement must be a string")
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def stable_item_id(*, trait_slug: str, line_number: int, raw_line_sha256: str) -> str:
    if not trait_slug or "/" in trait_slug:
        raise G1PersonaAssetError("trait_slug must be a non-empty path-free slug")
    if isinstance(line_number, bool) or not isinstance(line_number, int) or line_number <= 0:
        raise G1PersonaAssetError("line_number must be a positive integer")
    if not _SHA256_RE.fullmatch(raw_line_sha256):
        raise G1PersonaAssetError("raw_line_sha256 must be 64 lowercase hex characters")
    return (
        f"anthropic-evals-{SOURCE_COMMIT[:8]}-persona-{trait_slug}-"
        f"l{line_number:06d}-{raw_line_sha256[:12]}"
    )


def _jsonl_lines(raw: bytes, *, source_path: str) -> list[bytes]:
    if b"\r\n" in raw or b"\r" in raw:
        raise G1PersonaAssetError(f"{source_path} must use LF line endings")
    lines = raw.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    if not lines or any(not line for line in lines):
        raise G1PersonaAssetError(f"{source_path} contains an empty JSONL line")
    return lines


def _validate_record(record: Mapping[str, Any], *, source_path: str, line: int) -> None:
    if set(record) != EXPECTED_FIELDS:
        raise G1PersonaAssetError(
            f"{source_path}:{line} fields differ from the locked five-field schema"
        )
    statement = record["statement"]
    question = record["question"]
    if not isinstance(statement, str) or not statement:
        raise G1PersonaAssetError(f"{source_path}:{line} statement must be non-empty")
    if question != EXPECTED_QUESTION_PREFIX + statement + '"':
        raise G1PersonaAssetError(
            f"{source_path}:{line} question/statement binding is invalid"
        )
    matching = record["answer_matching_behavior"]
    not_matching = record["answer_not_matching_behavior"]
    if {matching, not_matching} != {" Yes", " No"}:
        raise G1PersonaAssetError(
            f"{source_path}:{line} labels must be complementary ' Yes'/' No'"
        )
    confidence = record["label_confidence"]
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(float(confidence))
        or not 0.0 <= float(confidence) <= 1.0
    ):
        raise G1PersonaAssetError(
            f"{source_path}:{line} label_confidence must be finite in [0, 1]"
        )


def read_candidate_file(
    source_root: Path,
    spec: TraitCandidateSpec,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Verify one locked file and return trait metadata plus hash-only item records."""

    path = source_root / spec.source_path
    if not path.is_file():
        raise G1PersonaAssetError(f"missing locked source file: {spec.source_path}")
    raw = path.read_bytes()
    observed_sha256 = sha256_bytes(raw)
    observed_blob = git_blob_sha1(raw)
    if observed_sha256 != spec.file_sha256:
        raise G1PersonaAssetError(
            f"SHA256 mismatch for {spec.source_path}: {observed_sha256}"
        )
    if observed_blob != spec.git_blob_sha1:
        raise G1PersonaAssetError(
            f"Git blob mismatch for {spec.source_path}: {observed_blob}"
        )
    lines = _jsonl_lines(raw, source_path=spec.source_path)
    if len(lines) != spec.expected_rows:
        raise G1PersonaAssetError(
            f"row-count mismatch for {spec.source_path}: {len(lines)}"
        )

    items: list[dict[str, Any]] = []
    matching_counts: Counter[str] = Counter()
    confidences: list[float] = []
    for line_number, raw_line in enumerate(lines, start=1):
        try:
            record = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise G1PersonaAssetError(
                f"invalid JSON at {spec.source_path}:{line_number}"
            ) from exc
        if not isinstance(record, dict):
            raise G1PersonaAssetError(
                f"{spec.source_path}:{line_number} must be a JSON object"
            )
        _validate_record(record, source_path=spec.source_path, line=line_number)
        raw_line_hash = sha256_bytes(raw_line)
        statement = record["statement"]
        normalized = normalize_statement(statement)
        matching_counts[record["answer_matching_behavior"]] += 1
        confidences.append(float(record["label_confidence"]))
        items.append(
            {
                "stable_source_item_id": stable_item_id(
                    trait_slug=spec.slug,
                    line_number=line_number,
                    raw_line_sha256=raw_line_hash,
                ),
                "source_line_number": line_number,
                "raw_line_sha256": raw_line_hash,
                "question_sha256": sha256_bytes(record["question"].encode("utf-8")),
                "statement_sha256": sha256_bytes(statement.encode("utf-8")),
                "normalized_statement_sha256": sha256_bytes(normalized.encode("utf-8")),
                "answer_matching_behavior": record["answer_matching_behavior"],
                "answer_not_matching_behavior": record["answer_not_matching_behavior"],
                "label_confidence": float(record["label_confidence"]),
            }
        )

    sorted_confidences = sorted(confidences)
    midpoint = len(sorted_confidences) // 2
    median = (
        sorted_confidences[midpoint]
        if len(sorted_confidences) % 2
        else (sorted_confidences[midpoint - 1] + sorted_confidences[midpoint]) / 2
    )
    trait = {
        "candidate_trait_id": spec.candidate_trait_id,
        "source_trait_slug": spec.slug,
        "candidate_family_id": spec.candidate_family_id,
        "family_assignment_status": DRAFT_STATUS,
        "trait_selection_status": CANDIDATE_STATUS,
        "source_subject_type": spec.source_subject_type,
        "source_path": spec.source_path,
        "source_revision": SOURCE_COMMIT,
        "source_git_blob_sha1": observed_blob,
        "source_file_sha256": observed_sha256,
        "source_row_count": len(items),
        "matching_label_counts": dict(sorted(matching_counts.items())),
        "label_confidence_summary": {
            "minimum": min(confidences),
            "median": median,
            "maximum": max(confidences),
            "semantics": "upstream_preference_model_confidence_not_human_ground_truth",
        },
        "source_items": items,
    }
    return trait, items


def audit_candidate_duplicates(
    traits: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Exclude every member of every normalized duplicate group.

    Duplicate statements cannot be split across future definition, vector, and
    held-out item roles even when all copies occur inside the same trait. The
    report distinguishes within-trait from cross-trait duplication, while the
    exclusion rule is deliberately global in both cases.
    """

    by_normalized_hash: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for trait in traits:
        for item in trait["source_items"]:
            by_normalized_hash[item["normalized_statement_sha256"]].append((trait, item))

    duplicate_groups: list[dict[str, Any]] = []
    duplicate_item_ids: set[str] = set()
    cross_trait_duplicate_item_ids: set[str] = set()
    within_trait_duplicate_item_ids: set[str] = set()
    cross_trait_group_count = 0
    within_trait_group_count = 0
    label_conflict_groups = 0
    label_conflict_rows = 0
    for normalized_hash, members in sorted(by_normalized_hash.items()):
        if len(members) <= 1:
            continue
        trait_ids = {trait["candidate_trait_id"] for trait, _ in members}
        duplicate_scope = "cross_trait" if len(trait_ids) > 1 else "within_trait"
        if duplicate_scope == "cross_trait":
            cross_trait_group_count += 1
        else:
            within_trait_group_count += 1
        labels = {item["answer_matching_behavior"] for _, item in members}
        label_conflict = len(labels) > 1
        if label_conflict:
            label_conflict_groups += 1
            label_conflict_rows += len(members)
        member_records = []
        for trait, item in sorted(
            members,
            key=lambda value: (
                value[0]["candidate_trait_id"],
                value[1]["source_line_number"],
            ),
        ):
            item_id = item["stable_source_item_id"]
            duplicate_item_ids.add(item_id)
            if duplicate_scope == "cross_trait":
                cross_trait_duplicate_item_ids.add(item_id)
            else:
                within_trait_duplicate_item_ids.add(item_id)
            member_records.append(
                {
                    "candidate_trait_id": trait["candidate_trait_id"],
                    "stable_source_item_id": item_id,
                    "source_line_number": item["source_line_number"],
                    "answer_matching_behavior": item["answer_matching_behavior"],
                }
            )
        duplicate_groups.append(
            {
                "normalized_statement_sha256": normalized_hash,
                "member_count": len(members),
                "duplicate_scope": duplicate_scope,
                "label_conflict": label_conflict,
                "members": member_records,
            }
        )

    per_trait: list[dict[str, Any]] = []
    raw_rows = 0
    for trait in traits:
        excluded = 0
        excluded_cross_trait = 0
        excluded_within_trait = 0
        for item in trait["source_items"]:
            raw_rows += 1
            item_id = item["stable_source_item_id"]
            if item_id in duplicate_item_ids:
                item["g1_candidate_item_status"] = DUPLICATE_ITEM_STATUS
                excluded += 1
                if item_id in cross_trait_duplicate_item_ids:
                    excluded_cross_trait += 1
                if item_id in within_trait_duplicate_item_ids:
                    excluded_within_trait += 1
            else:
                item["g1_candidate_item_status"] = UNIQUE_ITEM_STATUS
        per_trait.append(
            {
                "candidate_trait_id": trait["candidate_trait_id"],
                "raw_rows": len(trait["source_items"]),
                "excluded_normalized_duplicate_rows": excluded,
                "excluded_cross_trait_normalized_duplicate_rows": excluded_cross_trait,
                "excluded_within_trait_normalized_duplicate_rows": excluded_within_trait,
                "retained_globally_unique_candidate_rows": (
                    len(trait["source_items"]) - excluded
                ),
            }
        )

    return {
        "schema_id": "lps-v2.3-g1-persona-dedup-report-v2",
        "g1_gate_status": G1_OPEN_STATUS,
        "execution_authorized": False,
        "contains_target_model_data": False,
        "normalization_rule_id": NORMALIZATION_RULE_ID,
        "normalization_steps": [
            "Unicode NFKC",
            "Unicode casefold",
            "collapse all whitespace runs to one ASCII space and strip",
        ],
        "dedup_policy": (
            "exclude every member of every repeated normalized statement, within or "
            "across candidate traits, before any future item-role assignment"
        ),
        "summary": {
            "candidate_trait_count": len(traits),
            "raw_candidate_rows": raw_rows,
            "unique_normalized_statements": len(by_normalized_hash),
            "normalized_duplicate_groups": len(duplicate_groups),
            "rows_in_normalized_duplicate_groups": len(duplicate_item_ids),
            "cross_trait_normalized_duplicate_groups": cross_trait_group_count,
            "rows_in_cross_trait_normalized_duplicate_groups": len(
                cross_trait_duplicate_item_ids
            ),
            "within_trait_normalized_duplicate_groups": within_trait_group_count,
            "rows_in_within_trait_normalized_duplicate_groups": len(
                within_trait_duplicate_item_ids
            ),
            "retained_globally_unique_candidate_rows": raw_rows - len(duplicate_item_ids),
            "label_conflict_groups": label_conflict_groups,
            "rows_in_label_conflict_groups": label_conflict_rows,
        },
        "per_trait": per_trait,
        "normalized_duplicate_groups": duplicate_groups,
    }


def _verify_locked_file(path: Path, *, blob_sha1: str, sha256: str, label: str) -> None:
    if not path.is_file():
        raise G1PersonaAssetError(f"missing locked {label}: {path}")
    raw = path.read_bytes()
    if git_blob_sha1(raw) != blob_sha1 or sha256_bytes(raw) != sha256:
        raise G1PersonaAssetError(f"locked {label} hash mismatch: {path}")


def audit_source_snapshot(source_root: Path) -> dict[str, Any]:
    """Recompute the full ``persona/`` tree and dataset-level source statistics."""

    _verify_locked_file(
        source_root / LICENSE_RELATIVE_PATH,
        blob_sha1=LICENSE_GIT_BLOB_SHA1,
        sha256=LICENSE_SHA256,
        label="license",
    )
    _verify_locked_file(
        source_root / PERSONA_README_RELATIVE_PATH,
        blob_sha1=PERSONA_README_GIT_BLOB_SHA1,
        sha256=PERSONA_README_SHA256,
        label="Persona README",
    )
    persona_dir = source_root / "persona"
    if not persona_dir.is_dir():
        raise G1PersonaAssetError("locked source is missing persona/")

    all_files = sorted(path for path in persona_dir.iterdir() if path.is_file())
    tree_entries = [(path.name, git_blob_sha1(path.read_bytes())) for path in all_files]
    observed_tree = git_tree_sha1(tree_entries)
    if observed_tree != SOURCE_PERSONA_TREE_SHA1:
        raise G1PersonaAssetError(
            f"persona tree mismatch: expected {SOURCE_PERSONA_TREE_SHA1}, got {observed_tree}"
        )

    jsonl_paths = [path for path in all_files if path.suffix == ".jsonl"]
    if len(jsonl_paths) != EXPECTED_PERSONA_JSONL_FILES:
        raise G1PersonaAssetError(
            f"expected {EXPECTED_PERSONA_JSONL_FILES} Persona JSONL files, got {len(jsonl_paths)}"
        )
    inventory: list[dict[str, Any]] = []
    total_rows = 0
    for path in jsonl_paths:
        raw = path.read_bytes()
        source_path = f"persona/{path.name}"
        lines = _jsonl_lines(raw, source_path=source_path)
        for line_number, raw_line in enumerate(lines, start=1):
            try:
                record = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise G1PersonaAssetError(
                    f"invalid JSON at {source_path}:{line_number}"
                ) from exc
            if not isinstance(record, dict):
                raise G1PersonaAssetError(
                    f"{source_path}:{line_number} must be a JSON object"
                )
            _validate_record(record, source_path=source_path, line=line_number)
        total_rows += len(lines)
        inventory.append(
            {
                "source_path": source_path,
                "git_blob_sha1": git_blob_sha1(raw),
                "file_sha256": sha256_bytes(raw),
                "row_count": len(lines),
            }
        )
    if total_rows != EXPECTED_PERSONA_ROWS:
        raise G1PersonaAssetError(
            f"expected {EXPECTED_PERSONA_ROWS} Persona rows, got {total_rows}"
        )
    canonical_inventory = "\n".join(
        f"{item['source_path']}\t{item['git_blob_sha1']}\t"
        f"{item['file_sha256']}\t{item['row_count']}"
        for item in inventory
    )
    return {
        "persona_tree_sha1_recomputed": observed_tree,
        "persona_jsonl_file_count": len(jsonl_paths),
        "persona_total_row_count": total_rows,
        "persona_file_inventory_sha256": sha256_bytes(
            canonical_inventory.encode("utf-8")
        ),
        "persona_files": inventory,
    }


def _safe_extract_archive(archive_path: Path, destination: Path) -> None:
    expected_prefix = f"evals-{SOURCE_COMMIT}/"
    temporary = destination.with_name(destination.name + ".extracting")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive.getmembers():
                name = member.name
                if name == expected_prefix.rstrip("/"):
                    continue
                if not name.startswith(expected_prefix):
                    raise G1PersonaAssetError(
                        f"archive member outside locked prefix: {name}"
                    )
                relative = Path(name[len(expected_prefix) :])
                if not relative.parts or relative.is_absolute() or ".." in relative.parts:
                    raise G1PersonaAssetError(f"unsafe archive member: {name}")
                target = temporary / relative
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise G1PersonaAssetError(
                        f"unsupported non-file archive member: {name}"
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = archive.extractfile(member)
                if stream is None:
                    raise G1PersonaAssetError(f"could not read archive member: {name}")
                with target.open("wb") as output:
                    shutil.copyfileobj(stream, output)
        temporary.replace(destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def ensure_source_checkout(*, project_root: Path, allow_download: bool = True) -> tuple[Path, str]:
    """Download/extract the pinned source if absent and return root plus archive hash."""

    project_root = project_root.resolve()
    archive_path = project_root / SOURCE_ARCHIVE_RELATIVE_PATH
    source_root = project_root / SOURCE_CHECKOUT_RELATIVE_PATH
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if not archive_path.is_file():
        if not allow_download:
            raise G1PersonaAssetError(f"locked archive is missing: {archive_path}")
        temporary = archive_path.with_suffix(archive_path.suffix + ".downloading")
        request = Request(
            SOURCE_ARCHIVE_URL,
            headers={"User-Agent": "persona-drift-g1-source-lock/1"},
        )
        try:
            with urlopen(request, timeout=120) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
            temporary.replace(archive_path)
        except Exception:
            if temporary.exists():
                temporary.unlink()
            raise
    archive_sha256 = sha256_bytes(archive_path.read_bytes())
    if not source_root.exists():
        _safe_extract_archive(archive_path, source_root)
    if not source_root.is_dir():
        raise G1PersonaAssetError(f"source checkout is not a directory: {source_root}")
    return source_root, archive_sha256


def _yaml_bytes(payload: Mapping[str, Any]) -> bytes:
    return yaml.safe_dump(
        dict(payload),
        allow_unicode=True,
        sort_keys=False,
        width=100,
    ).encode("utf-8")


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def build_g1_persona_assets(
    *,
    project_root: Path,
    source_root: Path,
    archive_sha256: str,
    trait_specs: Sequence[TraitCandidateSpec] = TRAIT_CANDIDATES,
) -> dict[str, Any]:
    """Verify real source bytes, generate four deterministic tracked G1 assets."""

    project_root = project_root.resolve()
    source_root = source_root.resolve()
    if not _SHA256_RE.fullmatch(archive_sha256):
        raise G1PersonaAssetError("archive_sha256 must be 64 lowercase hex characters")
    if len(trait_specs) != 24:
        raise G1PersonaAssetError("the G1 shortlist must contain exactly 24 candidates")
    if len({spec.slug for spec in trait_specs}) != len(trait_specs):
        raise G1PersonaAssetError("candidate trait slugs must be unique")
    excluded_paths = {item["source_path"] for item in EXCLUDED_UPSTREAM_FILES}
    if any(spec.source_path in excluded_paths for spec in trait_specs):
        raise G1PersonaAssetError("excluded discount-factor files cannot enter the shortlist")
    family_counts = Counter(spec.candidate_family_id for spec in trait_specs)
    if len(family_counts) != 4 or set(family_counts.values()) != {6}:
        raise G1PersonaAssetError("the draft frame must contain four families x six candidates")

    source_audit = audit_source_snapshot(source_root)
    traits: list[dict[str, Any]] = []
    for spec in trait_specs:
        trait, _ = read_candidate_file(source_root, spec)
        traits.append(trait)
    dedup_report = audit_candidate_duplicates(traits)

    public_sources = {
        "schema_id": "lps-v2.3-g1-public-persona-sources-v1",
        "g1_gate_status": G1_OPEN_STATUS,
        "source_lock_status": "SOURCE_BYTES_VERIFIED",
        "execution_authorized": False,
        "contains_target_model_data": False,
        "source": {
            "source_id": "anthropic-model-written-evals-persona",
            "repository_url": SOURCE_REPOSITORY,
            "repository_commit": SOURCE_COMMIT,
            "repository_commit_date": SOURCE_COMMIT_DATE,
            "repository_root_tree_sha1": SOURCE_ROOT_TREE_SHA1,
            "persona_tree_sha1": SOURCE_PERSONA_TREE_SHA1,
            "persona_path_last_commit": SOURCE_PERSONA_PATH_LAST_COMMIT,
            "download_url": SOURCE_ARCHIVE_URL,
            "raw_archive_relative_path": SOURCE_ARCHIVE_RELATIVE_PATH,
            "raw_archive_sha256_observed": archive_sha256,
            "raw_checkout_relative_path": SOURCE_CHECKOUT_RELATIVE_PATH,
            "license": {
                "spdx_id": LICENSE_SPDX,
                "source_path": LICENSE_RELATIVE_PATH,
                "git_blob_sha1": LICENSE_GIT_BLOB_SHA1,
                "file_sha256": LICENSE_SHA256,
                "attribution_and_change_notice_required_when_shared": True,
            },
            "persona_readme": {
                "source_path": PERSONA_README_RELATIVE_PATH,
                "git_blob_sha1": PERSONA_README_GIT_BLOB_SHA1,
                "file_sha256": PERSONA_README_SHA256,
            },
            "observed_dataset": source_audit,
            "documentation_discrepancies": [
                {
                    "id": "persona-count-133-vs-135",
                    "paper_and_readme_claim": 133,
                    "locked_tree_observed_jsonl_files": 135,
                    "resolution": (
                        "retain the immutable 135-file source snapshot; exclude the two "
                        "unlisted discount-factor files from the project candidate universe"
                    ),
                },
                {
                    "id": "question-prefix-wording",
                    "readme_paraphrase": "Is the following something you would say?",
                    "raw_data_exact_prefix": (
                        "Is the following statement something you would say?"
                    ),
                    "resolution": "validate and hash the raw-data wording",
                },
            ],
            "excluded_upstream_files": list(EXCLUDED_UPSTREAM_FILES),
        },
    }
    public_sources_bytes = _yaml_bytes(public_sources)
    public_sources_sha256 = sha256_bytes(public_sources_bytes)

    candidate_pool = {
        "schema_id": "lps-v2.3-g1-persona-candidate-pool-v1",
        "g1_gate_status": G1_OPEN_STATUS,
        "pool_status": CANDIDATE_STATUS,
        "execution_authorized": False,
        "contains_target_model_data": False,
        "selection_outcome_blind": True,
        "source_id": "anthropic-model-written-evals-persona",
        "source_revision": SOURCE_COMMIT,
        "public_sources_manifest_sha256": public_sources_sha256,
        "raw_line_hash_rule_id": RAW_LINE_HASH_RULE_ID,
        "stable_item_id_rule_id": STABLE_ITEM_ID_RULE_ID,
        "normalization_rule_id": NORMALIZATION_RULE_ID,
        "candidate_trait_count": len(traits),
        "candidate_source_item_count": sum(
            len(trait["source_items"]) for trait in traits
        ),
        "excluded_upstream_files": list(EXCLUDED_UPSTREAM_FILES),
        "candidate_traits": traits,
    }
    candidate_pool_bytes = _yaml_bytes(candidate_pool)
    candidate_pool_sha256 = sha256_bytes(candidate_pool_bytes)

    dedup_report["source_revision"] = SOURCE_COMMIT
    dedup_report["candidate_pool_manifest_sha256"] = candidate_pool_sha256
    dedup_report_bytes = _json_bytes(dedup_report)
    dedup_report_sha256 = sha256_bytes(dedup_report_bytes)

    families: list[dict[str, Any]] = []
    for family_id in sorted(family_counts):
        family_specs = [spec for spec in trait_specs if spec.candidate_family_id == family_id]
        families.append(
            {
                "candidate_family_id": family_id,
                "family_status": DRAFT_STATUS,
                "family_definition_status": "OPEN_REQUIRES_OUTCOME_BLIND_ADJUDICATION",
                "candidate_trait_ids": [spec.candidate_trait_id for spec in family_specs],
                "candidate_trait_count": len(family_specs),
                "source_subject_types": sorted(
                    {spec.source_subject_type for spec in family_specs}
                ),
            }
        )
    sampling_frame = {
        "schema_id": "lps-v2.3-g1-persona-sampling-frame-draft-v1",
        "g1_gate_status": G1_OPEN_STATUS,
        "sampling_frame_status": DRAFT_STATUS,
        "execution_authorized": False,
        "contains_target_model_data": False,
        "selection_outcome_blind": True,
        "public_sources_manifest_sha256": public_sources_sha256,
        "candidate_pool_manifest_sha256": candidate_pool_sha256,
        "dedup_report_sha256": dedup_report_sha256,
        "planning_target_only": {
            "behavioral_families": 4,
            "candidate_traits_per_family": 6,
            "total_candidate_traits": 24,
            "semantics": (
                "recruitment shortlist only; no family or trait is accepted as a final "
                "true-trait catalog member"
            ),
        },
        "families": families,
        "open_before_g1_pass": [
            "outcome-blind semantic family-boundary adjudication",
            "independent-trait versus near-duplicate decisions",
            "behavioral observability and persona-opposing-pressure suitability review",
            "source subject-type confounding review",
            "safety and HHH-conflict review",
            "minimum usable globally unique item rule",
            "final four-to-six accepted traits per family and stop/amendment rule",
        ],
        "explicitly_not_in_this_g1_asset": [
            "Persona system prompts",
            "system-prompt formulations",
            "definition/vector/validation item-role assignments",
            "generalization or held-out assignments",
            "target-model exposures, activations, behaviors, or outcomes",
        ],
    }
    sampling_frame_bytes = _yaml_bytes(sampling_frame)

    manifest_dir = project_root / "data/manifests"
    report_dir = project_root / "data/reports"
    outputs = {
        manifest_dir / PUBLIC_SOURCES_FILENAME: public_sources_bytes,
        manifest_dir / CANDIDATE_POOL_FILENAME: candidate_pool_bytes,
        manifest_dir / SAMPLING_FRAME_FILENAME: sampling_frame_bytes,
        report_dir / DEDUP_REPORT_FILENAME: dedup_report_bytes,
    }
    for path, value in outputs.items():
        _write_bytes(path, value)

    return {
        "g1_gate_status": G1_OPEN_STATUS,
        "source_commit": SOURCE_COMMIT,
        "source_jsonl_files": source_audit["persona_jsonl_file_count"],
        "source_rows": source_audit["persona_total_row_count"],
        "candidate_traits": len(traits),
        "candidate_items": candidate_pool["candidate_source_item_count"],
        "dedup_summary": dedup_report["summary"],
        "outputs": {
            str(path.relative_to(project_root)): sha256_bytes(value)
            for path, value in outputs.items()
        },
    }


__all__ = [
    "CANDIDATE_STATUS",
    "DEDUP_REPORT_FILENAME",
    "DRAFT_STATUS",
    "G1_OPEN_STATUS",
    "G1PersonaAssetError",
    "NORMALIZATION_RULE_ID",
    "PUBLIC_SOURCES_FILENAME",
    "SAMPLING_FRAME_FILENAME",
    "SOURCE_COMMIT",
    "TRAIT_CANDIDATES",
    "TraitCandidateSpec",
    "audit_candidate_duplicates",
    "audit_source_snapshot",
    "build_g1_persona_assets",
    "ensure_source_checkout",
    "git_blob_sha1",
    "git_tree_sha1",
    "normalize_statement",
    "read_candidate_file",
    "sha256_bytes",
    "stable_item_id",
]
