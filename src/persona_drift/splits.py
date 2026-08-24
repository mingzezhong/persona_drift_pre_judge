"""Topic-catalog and topic-level split invariants for restart-v2."""

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Sequence, Tuple

from .protocol import ProtocolValidationError


DEVELOPMENT_TOPICS = 15
CALIBRATION_TOPICS = 5
UNTOUCHED_TEST_TOPICS = 10
TOTAL_MAIN_TOPICS = 30
PILOT_TOPICS = 6
MMLU_PRO_TOPICS = 24
SYCOPHANCY_TOPICS = 6


class TopicSource(str, Enum):
    MMLU_PRO = "mmlu_pro"
    ANTHROPIC_SYCOPHANCY = "anthropic_sycophancy"


def _as_topic_tuple(values: Iterable[str], *, field: str) -> Tuple[str, ...]:
    items = tuple(values)
    if any(not isinstance(item, str) or not item.strip() for item in items):
        raise ProtocolValidationError(f"{field} must contain non-empty topic IDs")
    if len(set(items)) != len(items):
        raise ProtocolValidationError(f"{field} contains duplicate topic IDs")
    return items


@dataclass(frozen=True)
class TopicAnchor:
    """One frozen public item and its frozen discussion-scenario conversion."""

    topic_id: str
    source: TopicSource
    source_item_id: str
    source_group: str
    conversion_template_id: str

    def __post_init__(self) -> None:
        for field in (
            "topic_id",
            "source_item_id",
            "source_group",
            "conversion_template_id",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ProtocolValidationError(f"{field} must be a non-empty string")
        if not isinstance(self.source, TopicSource):
            raise ProtocolValidationError("source must be a TopicSource member")


def validate_anchor_catalog(anchors: Sequence[TopicAnchor]) -> Tuple[TopicAnchor, ...]:
    """Validate the frozen 24 MMLU-Pro + 6 sycophancy topic catalog.

    MMLU-Pro must contribute two anchors from each of twelve frozen domains.
    Anthropic sycophancy must contribute two each from philosophy, NLP, and
    politics.  Correct answers are intentionally absent from this schema: they
    are never drift labels.
    """

    catalog = tuple(anchors)
    if len(catalog) != TOTAL_MAIN_TOPICS:
        raise ProtocolValidationError(
            f"topic catalog must contain {TOTAL_MAIN_TOPICS} anchors; got {len(catalog)}"
        )
    ids = [anchor.topic_id for anchor in catalog]
    if len(set(ids)) != len(ids):
        raise ProtocolValidationError("topic catalog contains duplicate topic IDs")

    by_source = Counter(anchor.source for anchor in catalog)
    expected_sources = {
        TopicSource.MMLU_PRO: MMLU_PRO_TOPICS,
        TopicSource.ANTHROPIC_SYCOPHANCY: SYCOPHANCY_TOPICS,
    }
    if by_source != expected_sources:
        raise ProtocolValidationError(
            f"topic sources must be {expected_sources}; got {dict(by_source)}"
        )

    mmlu_groups = Counter(
        anchor.source_group
        for anchor in catalog
        if anchor.source is TopicSource.MMLU_PRO
    )
    if len(mmlu_groups) != 12 or set(mmlu_groups.values()) != {2}:
        raise ProtocolValidationError(
            "MMLU-Pro anchors must cover exactly 12 domains with 2 anchors each"
        )

    sycophancy_groups = Counter(
        anchor.source_group.lower()
        for anchor in catalog
        if anchor.source is TopicSource.ANTHROPIC_SYCOPHANCY
    )
    expected_sycophancy = {"philosophy": 2, "nlp": 2, "politics": 2}
    if sycophancy_groups != expected_sycophancy:
        raise ProtocolValidationError(
            "sycophancy anchors must contain 2 philosophy, 2 NLP, and 2 politics "
            f"topics; got {dict(sycophancy_groups)}"
        )
    return catalog


@dataclass(frozen=True)
class TopicSplitPlan:
    """Frozen topic-level 15/5/10 split plus six development pilot topics.

    The pilot subset is additive operational detail: it is selected only from
    development topics and can never enter calibration or untouched test.
    """

    development: Tuple[str, ...]
    calibration: Tuple[str, ...]
    untouched_test: Tuple[str, ...]
    pilot: Tuple[str, ...]

    def __post_init__(self) -> None:
        development = _as_topic_tuple(self.development, field="development")
        calibration = _as_topic_tuple(self.calibration, field="calibration")
        untouched = _as_topic_tuple(self.untouched_test, field="untouched_test")
        pilot = _as_topic_tuple(self.pilot, field="pilot")

        expected_lengths = (
            ("development", development, DEVELOPMENT_TOPICS),
            ("calibration", calibration, CALIBRATION_TOPICS),
            ("untouched_test", untouched, UNTOUCHED_TEST_TOPICS),
            ("pilot", pilot, PILOT_TOPICS),
        )
        for field, values, expected in expected_lengths:
            if len(values) != expected:
                raise ProtocolValidationError(
                    f"{field} must contain exactly {expected} topics; got {len(values)}"
                )

        partitions = {
            "development": set(development),
            "calibration": set(calibration),
            "untouched_test": set(untouched),
        }
        names = tuple(partitions)
        for left_index, left in enumerate(names):
            for right in names[left_index + 1 :]:
                overlap = partitions[left] & partitions[right]
                if overlap:
                    raise ProtocolValidationError(
                        f"topic partitions {left}/{right} overlap: {sorted(overlap)}"
                    )
        if not set(pilot).issubset(partitions["development"]):
            raise ProtocolValidationError(
                "all six pilot topics must be a subset of development topics"
            )

        object.__setattr__(self, "development", development)
        object.__setattr__(self, "calibration", calibration)
        object.__setattr__(self, "untouched_test", untouched)
        object.__setattr__(self, "pilot", pilot)

    @property
    def all_main_topics(self) -> Tuple[str, ...]:
        return self.development + self.calibration + self.untouched_test

    def partition_for(self, topic_id: str) -> str:
        memberships: Mapping[str, Tuple[str, ...]] = {
            "development": self.development,
            "calibration": self.calibration,
            "untouched_test": self.untouched_test,
        }
        for partition, topic_ids in memberships.items():
            if topic_id in topic_ids:
                return partition
        raise ProtocolValidationError(f"unknown topic_id {topic_id!r}")

    def validate_against_catalog(self, anchors: Sequence[TopicAnchor]) -> None:
        catalog = validate_anchor_catalog(anchors)
        catalog_ids = {anchor.topic_id for anchor in catalog}
        split_ids = set(self.all_main_topics)
        if split_ids != catalog_ids:
            missing = sorted(catalog_ids - split_ids)
            unexpected = sorted(split_ids - catalog_ids)
            raise ProtocolValidationError(
                f"split/catalog mismatch; missing={missing}, unexpected={unexpected}"
            )


def validate_no_root_leakage(
    root_ids_by_partition: Mapping[str, Iterable[str]]
) -> None:
    """Ensure a root trajectory or fork-prefix group occurs in one partition."""

    normalized = {
        partition: set(_as_topic_tuple(root_ids, field=f"{partition}_root_ids"))
        for partition, root_ids in root_ids_by_partition.items()
    }
    names = tuple(normalized)
    for left_index, left in enumerate(names):
        for right in names[left_index + 1 :]:
            overlap = normalized[left] & normalized[right]
            if overlap:
                raise ProtocolValidationError(
                    f"root-group leakage across {left}/{right}: {sorted(overlap)}"
                )
