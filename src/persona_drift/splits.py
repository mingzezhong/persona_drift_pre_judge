"""Scenario-first topic catalog and split contracts for restart-v2.3."""

from collections import Counter
from dataclasses import dataclass
from enum import Enum
import hashlib
import math
import re
from typing import Iterable, Mapping, Optional, Sequence, Tuple

from .protocol import MAIN_TURNS, ProtocolValidationError

DEVELOPMENT_TOPICS, CALIBRATION_TOPICS, UNTOUCHED_TEST_TOPICS = 18, 6, 12
TOTAL_MAIN_TOPICS, PILOT_TOPICS = 36, 6
EXPECTED_BEHAVIORAL_FAMILIES = 4
SHARED_CORE_TOPICS, FAMILY_SPECIFIC_TOPICS = 12, 24
SHARED_EVIDENCE_TOPICS, SHARED_OPINION_TOPICS = 6, 6
FAMILY_SPECIFIC_TOPICS_PER_FAMILY = 6
SHARED_BY_PARTITION = {"development": 6, "calibration": 2, "untouched_test": 4}
FAMILY_BY_PARTITION = {"development": 3, "calibration": 1, "untouched_test": 2}
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class TopicSource(str, Enum):
    MMLU_PRO = "mmlu_pro"
    ANTHROPIC_SYCOPHANCY = "anthropic_sycophancy"


class TopicScope(str, Enum):
    SHARED_CORE = "shared_core"
    FAMILY_SPECIFIC = "family_specific"


class SharedCoreKind(str, Enum):
    EVIDENCE = "evidence"
    OPINION = "opinion"


def _ids(values: Iterable[str], *, field: str) -> Tuple[str, ...]:
    values = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ProtocolValidationError(f"{field} must contain non-empty IDs")
    if len(values) != len(set(values)):
        raise ProtocolValidationError(f"{field} contains duplicate IDs")
    return values


def _sha256(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ProtocolValidationError(f"{field} must be 64 lowercase hex characters")


def compute_topic_content_root_sha256(
    ordered_topic_move_sha256s: Iterable[str],
) -> str:
    """Hash ordered move hashes with the frozen restart-v2.3 canonical rule."""

    move_hashes = tuple(ordered_topic_move_sha256s)
    if len(move_hashes) != 25:
        raise ProtocolValidationError(
            "content root requires exactly 25 ordered topic move hashes"
        )
    if len(set(move_hashes)) != 25:
        raise ProtocolValidationError(
            "content root requires 25 unique ordered topic move hashes"
        )
    for index, value in enumerate(move_hashes, start=1):
        _sha256(value, field=f"ordered_topic_move_sha256s[{index - 1}]")
    canonical = "restart-v2.3-topic-move-root-v1\n" + "\n".join(
        f"{index:02d}:{value}"
        for index, value in enumerate(move_hashes, start=1)
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _family_ids(values: Iterable[str]) -> Tuple[str, ...]:
    values = _ids(values, field="known_behavioral_family_ids")
    if len(values) != EXPECTED_BEHAVIORAL_FAMILIES:
        raise ProtocolValidationError(
            "known_behavioral_family_ids must contain exactly four families"
        )
    return values


@dataclass(frozen=True)
class TopicSuitabilityScore:
    """One score; its scale and threshold are intentionally not frozen here."""

    criterion_id: str
    score: float

    def __post_init__(self) -> None:
        if not isinstance(self.criterion_id, str) or not self.criterion_id.strip():
            raise ProtocolValidationError("suitability criterion_id must be non-empty")
        if (
            isinstance(self.score, bool)
            or not isinstance(self.score, (int, float))
            or not math.isfinite(float(self.score))
        ):
            raise ProtocolValidationError("suitability score must be finite numeric")


@dataclass(frozen=True)
class TopicCandidatePoolManifest:
    """Frozen outcome-blind candidate universe for one public source."""

    source: TopicSource
    manifest_id: str
    source_revision: str
    source_group_ids: Tuple[str, ...]
    candidate_source_item_ids: Tuple[str, ...]
    candidate_items_sha256: str
    exclusion_log_sha256: str
    suitability_rubric_sha256: str
    selection_outcome_blind: bool = True
    selected_group_quota: Optional[int] = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, TopicSource):
            raise ProtocolValidationError(
                "candidate-pool source must be a TopicSource member"
            )
        for field in ("manifest_id", "source_revision"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ProtocolValidationError(f"{field} must be a non-empty string")
        group_ids = _ids(self.source_group_ids, field="candidate source group IDs")
        if not group_ids:
            raise ProtocolValidationError(
                "candidate-pool manifest must contain source group IDs"
            )
        if self.source is TopicSource.MMLU_PRO and len(group_ids) != 14:
            raise ProtocolValidationError(
                "MMLU-Pro candidate manifest must contain exactly 14 source group IDs"
            )
        object.__setattr__(self, "source_group_ids", group_ids)
        item_ids = _ids(
            self.candidate_source_item_ids,
            field="candidate source item IDs",
        )
        if not item_ids:
            raise ProtocolValidationError(
                "candidate-pool manifest must contain immutable source item IDs"
            )
        object.__setattr__(self, "candidate_source_item_ids", item_ids)
        for field in (
            "candidate_items_sha256",
            "exclusion_log_sha256",
            "suitability_rubric_sha256",
        ):
            _sha256(getattr(self, field), field=field)
        if self.selection_outcome_blind is not True:
            raise ProtocolValidationError(
                "candidate-pool construction must be outcome-blind"
            )
        if (
            self.source is TopicSource.MMLU_PRO
            and self.selected_group_quota is not None
        ):
            raise ProtocolValidationError(
                "MMLU-Pro source groups are a candidate pool; quota must be None"
            )
        if (
            self.selected_group_quota is not None
            and (
                isinstance(self.selected_group_quota, bool)
                or not isinstance(self.selected_group_quota, int)
                or self.selected_group_quota <= 0
            )
        ):
            raise ProtocolValidationError(
                "selected_group_quota must be None or a positive integer"
            )


@dataclass(frozen=True)
class TopicSuitabilityRubricManifest:
    """Versioned rubric contract whose exact criteria and rules remain external."""

    rubric_id: str
    criterion_ids: Tuple[str, ...]
    manifest_sha256: str
    scoring_rule_sha256: str
    aggregation_rule_sha256: str
    rater_protocol_sha256: str
    decision_rule_sha256: str
    outcome_blind: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.rubric_id, str) or not self.rubric_id.strip():
            raise ProtocolValidationError("rubric_id must be non-empty")
        criteria = _ids(self.criterion_ids, field="suitability criterion IDs")
        if not criteria:
            raise ProtocolValidationError(
                "suitability rubric must contain at least one criterion"
            )
        object.__setattr__(self, "criterion_ids", criteria)
        for field in (
            "manifest_sha256",
            "scoring_rule_sha256",
            "aggregation_rule_sha256",
            "rater_protocol_sha256",
            "decision_rule_sha256",
        ):
            _sha256(getattr(self, field), field=field)
        if self.outcome_blind is not True:
            raise ProtocolValidationError("suitability rubric must be outcome-blind")


@dataclass(frozen=True)
class TopicScenarioManifest:
    """The pressure-free ordered 25-move scenario for one logical topic."""

    topic_id: str
    scenario_version: str
    scenario_template_sha256: str
    manifest_sha256: str
    topic_content_root_sha256: str
    ordered_topic_move_ids: Tuple[str, ...]
    ordered_topic_move_sha256s: Tuple[str, ...]
    pressure_slot_ids: Tuple[str, ...]
    topic_moves_are_pressure_free: bool = True
    pressure_templates_are_separate: bool = True

    def __post_init__(self) -> None:
        for field in ("topic_id", "scenario_version"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ProtocolValidationError(f"{field} must be non-empty")
        _sha256(self.scenario_template_sha256, field="scenario_template_sha256")
        _sha256(self.manifest_sha256, field="manifest_sha256")
        _sha256(self.topic_content_root_sha256, field="topic_content_root_sha256")
        moves = _ids(self.ordered_topic_move_ids, field="ordered topic move IDs")
        slots = _ids(self.pressure_slot_ids, field="pressure slot IDs")
        move_hashes = tuple(self.ordered_topic_move_sha256s)
        if len(moves) != MAIN_TURNS or len(slots) != MAIN_TURNS:
            raise ProtocolValidationError(
                "scenario manifest requires exactly 25 ordered moves and pressure slots"
            )
        if len(move_hashes) != MAIN_TURNS:
            raise ProtocolValidationError(
                "scenario manifest requires exactly 25 ordered move hashes"
            )
        for index, value in enumerate(move_hashes):
            _sha256(value, field=f"ordered_topic_move_sha256s[{index}]")
        if len(set(move_hashes)) != MAIN_TURNS:
            raise ProtocolValidationError(
                "all 25 topic move content hashes must be unique within a scenario"
            )
        expected_root = compute_topic_content_root_sha256(move_hashes)
        if self.topic_content_root_sha256 != expected_root:
            raise ProtocolValidationError(
                "scenario topic_content_root_sha256 does not match ordered move hashes"
            )
        if self.topic_moves_are_pressure_free is not True:
            raise ProtocolValidationError("topic moves must be pressure-free")
        if self.pressure_templates_are_separate is not True:
            raise ProtocolValidationError(
                "pressure templates must remain separate from topic moves"
            )
        object.__setattr__(self, "ordered_topic_move_ids", moves)
        object.__setattr__(self, "ordered_topic_move_sha256s", move_hashes)
        object.__setattr__(self, "pressure_slot_ids", slots)


@dataclass(frozen=True)
class TopicAnchor:
    """One selected public anchor and frozen scenario conversion.

    Every criterion named by the supplied frozen rubric manifest is required.
    V2.3 itself does not hard-code criterion IDs, a score range, aggregation
    formula, rater rule, or decision threshold.
    """

    topic_id: str
    topic_scope: TopicScope
    scenario_family_id: str
    eligible_behavioral_family_id: Optional[str]
    scenario_subtype: str
    shared_core_kind: Optional[SharedCoreKind]
    source: TopicSource
    source_item_id: str
    source_group: str
    conversion_template_id: str
    scenario_version: str
    source_url: str
    source_revision: str
    source_license: str
    source_file_sha256: str
    source_item_sha256: str
    scenario_template_sha256: str
    scenario_manifest_sha256: str
    topic_content_root_sha256: str
    suitability_screen_manifest_sha256: str
    selection_review_sha256: str
    suitability_scores: Tuple[TopicSuitabilityScore, ...]
    native_stance_policy: str
    selection_outcome_blind: bool = True
    suitability_passed: bool = True

    def __post_init__(self) -> None:
        for field in (
            "topic_id", "scenario_family_id", "scenario_subtype", "source_item_id",
            "source_group", "conversion_template_id", "scenario_version", "source_url",
            "source_revision", "source_license", "native_stance_policy",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ProtocolValidationError(f"{field} must be a non-empty string")
        if not isinstance(self.topic_scope, TopicScope):
            raise ProtocolValidationError("topic_scope must be a TopicScope member")
        if not isinstance(self.source, TopicSource):
            raise ProtocolValidationError("source must be a TopicSource member")
        if self.topic_scope is TopicScope.SHARED_CORE:
            if self.eligible_behavioral_family_id is not None:
                raise ProtocolValidationError(
                    "shared topics cannot bind an eligible behavioral family"
                )
            if not isinstance(self.shared_core_kind, SharedCoreKind):
                raise ProtocolValidationError(
                    "shared topics require an evidence/opinion shared_core_kind"
                )
        else:
            if (
                not isinstance(self.eligible_behavioral_family_id, str)
                or not self.eligible_behavioral_family_id.strip()
            ):
                raise ProtocolValidationError(
                    "family-specific topics require an eligible behavioral family"
                )
            if self.shared_core_kind is not None:
                raise ProtocolValidationError(
                    "family-specific topics cannot carry a shared_core_kind"
                )
        for field in (
            "source_file_sha256", "source_item_sha256",
            "scenario_template_sha256", "scenario_manifest_sha256",
            "topic_content_root_sha256",
            "suitability_screen_manifest_sha256",
            "selection_review_sha256",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
                raise ProtocolValidationError(
                    f"{field} must be 64 lowercase hex characters"
                )
        scores = tuple(self.suitability_scores)
        if any(not isinstance(item, TopicSuitabilityScore) for item in scores):
            raise ProtocolValidationError(
                "suitability_scores must contain TopicSuitabilityScore records"
            )
        criterion_ids = [item.criterion_id for item in scores]
        if not criterion_ids:
            raise ProtocolValidationError(
                "suitability_scores must contain at least one criterion"
            )
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ProtocolValidationError(
                "suitability_scores contains duplicate criterion IDs"
            )
        object.__setattr__(self, "suitability_scores", scores)
        if self.selection_outcome_blind is not True:
            raise ProtocolValidationError("topic selection must be outcome-blind")
        if self.suitability_passed is not True:
            raise ProtocolValidationError("selected topic must pass suitability review")
        if self.source is TopicSource.MMLU_PRO:
            if self.native_stance_policy != "not_applicable":
                raise ProtocolValidationError(
                    "MMLU-Pro stance policy must be not_applicable"
                )
        elif self.native_stance_policy not in {
            "remove_or_standardize", "source_specific_baseline",
        }:
            raise ProtocolValidationError(
                "Anthropic sycophancy requires a frozen native-stance policy"
            )


def validate_anchor_catalog(
    anchors: Sequence[TopicAnchor],
    *,
    known_behavioral_family_ids: Iterable[str],
    source_candidate_pool_manifests: Sequence[TopicCandidatePoolManifest],
    suitability_rubric_manifest: TopicSuitabilityRubricManifest,
) -> Tuple[TopicAnchor, ...]:
    """Validate the hierarchy without imposing a source/category quota."""

    families = _family_ids(known_behavioral_family_ids)
    source_manifests = tuple(source_candidate_pool_manifests)
    if any(
        not isinstance(item, TopicCandidatePoolManifest)
        for item in source_manifests
    ):
        raise ProtocolValidationError(
            "source_candidate_pool_manifests must contain "
            "TopicCandidatePoolManifest records"
        )
    if not isinstance(suitability_rubric_manifest, TopicSuitabilityRubricManifest):
        raise ProtocolValidationError(
            "suitability_rubric_manifest must be a TopicSuitabilityRubricManifest"
        )
    manifest_sources = [item.source for item in source_manifests]
    if (
        len(manifest_sources) != len(set(manifest_sources))
        or set(manifest_sources) != set(TopicSource)
    ):
        raise ProtocolValidationError(
            "exactly one candidate-pool manifest is required for each topic source"
        )
    source_manifests_by_source = {
        item.source: item for item in source_manifests
    }
    for manifest in source_manifests:
        if (
            manifest.suitability_rubric_sha256
            != suitability_rubric_manifest.manifest_sha256
        ):
            raise ProtocolValidationError(
                "candidate pool and suitability rubric manifest hashes mismatch"
            )
    catalog = tuple(anchors)
    if len(catalog) != TOTAL_MAIN_TOPICS:
        raise ProtocolValidationError(
            f"topic catalog must contain {TOTAL_MAIN_TOPICS} anchors; got {len(catalog)}"
        )
    if any(not isinstance(anchor, TopicAnchor) for anchor in catalog):
        raise ProtocolValidationError("topic catalog must contain TopicAnchor records")
    for field, values in (
        ("topic IDs", [x.topic_id for x in catalog]),
        ("source item IDs", [x.source_item_id for x in catalog]),
        ("source item hashes", [x.source_item_sha256 for x in catalog]),
        (
            "topic content roots",
            [x.topic_content_root_sha256 for x in catalog],
        ),
    ):
        if len(values) != len(set(values)):
            raise ProtocolValidationError(f"topic catalog contains duplicate {field}")
    scopes = Counter(anchor.topic_scope for anchor in catalog)
    expected_scopes = {
        TopicScope.SHARED_CORE: SHARED_CORE_TOPICS,
        TopicScope.FAMILY_SPECIFIC: FAMILY_SPECIFIC_TOPICS,
    }
    if scopes != expected_scopes:
        raise ProtocolValidationError(
            f"topic scopes must be {expected_scopes}; got {dict(scopes)}"
        )
    shared_kinds = Counter(
        anchor.shared_core_kind for anchor in catalog
        if anchor.topic_scope is TopicScope.SHARED_CORE
    )
    if shared_kinds != {
        SharedCoreKind.EVIDENCE: SHARED_EVIDENCE_TOPICS,
        SharedCoreKind.OPINION: SHARED_OPINION_TOPICS,
    }:
        raise ProtocolValidationError(
            "shared core must contain six evidence and six opinion topics"
        )
    targets = [
        anchor.eligible_behavioral_family_id for anchor in catalog
        if anchor.topic_scope is TopicScope.FAMILY_SPECIFIC
    ]
    unknown = set(targets) - set(families)
    if unknown:
        raise ProtocolValidationError(
            "family-specific topics reference unknown eligible families: "
            f"{sorted(unknown)}"
        )
    expected_targets = {
        family_id: FAMILY_SPECIFIC_TOPICS_PER_FAMILY for family_id in families
    }
    if Counter(targets) != expected_targets:
        raise ProtocolValidationError(
            "family-specific topics must contain six per behavioral family"
        )
    criteria = set(suitability_rubric_manifest.criterion_ids)
    for anchor in catalog:
        if anchor.suitability_screen_manifest_sha256 != (
            suitability_rubric_manifest.manifest_sha256
        ):
            raise ProtocolValidationError(
                "topic suitability rubric manifest hash mismatch"
            )
        if {score.criterion_id for score in anchor.suitability_scores} != criteria:
            raise ProtocolValidationError(
                "topic suitability scores do not match the frozen rubric"
            )
        source_manifest = source_manifests_by_source[anchor.source]
        if anchor.source_group not in source_manifest.source_group_ids:
            raise ProtocolValidationError(
                "selected topic source_group is absent from its candidate-pool manifest"
            )
        if anchor.source_item_id not in source_manifest.candidate_source_item_ids:
            raise ProtocolValidationError(
                "selected topic source_item_id is absent from its candidate-pool manifest"
            )
        if anchor.source_revision != source_manifest.source_revision:
            raise ProtocolValidationError(
                "selected topic revision does not match its candidate-pool manifest"
            )
    stance_policies = {
        anchor.native_stance_policy for anchor in catalog
        if anchor.source is TopicSource.ANTHROPIC_SYCOPHANCY
    }
    if len(stance_policies) > 1:
        raise ProtocolValidationError(
            "Anthropic sycophancy anchors cannot mix native-stance policies"
        )
    return catalog


def validate_topic_scenario_catalog(
    anchors: Sequence[TopicAnchor],
    manifests: Sequence[TopicScenarioManifest],
) -> Tuple[TopicScenarioManifest, ...]:
    """Bind every selected topic anchor to one unique frozen scenario.

    This catalog-level check is deliberately independent of trajectory
    selection: a mismatch in a non-current topic must still fail closed.
    """

    catalog = tuple(anchors)
    if any(not isinstance(item, TopicAnchor) for item in catalog):
        raise ProtocolValidationError(
            "topic catalog must contain TopicAnchor records"
        )
    topic_ids = [item.topic_id for item in catalog]
    if len(topic_ids) != len(set(topic_ids)):
        raise ProtocolValidationError("topic catalog contains duplicate topic IDs")
    by_id = {item.topic_id: item for item in catalog}

    scenarios = tuple(manifests)
    if any(not isinstance(item, TopicScenarioManifest) for item in scenarios):
        raise ProtocolValidationError(
            "topic_scenario_manifests must contain TopicScenarioManifest records"
        )
    scenario_ids = [item.topic_id for item in scenarios]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ProtocolValidationError(
            "topic scenario manifests contain duplicate topic IDs"
        )
    if set(scenario_ids) != set(by_id):
        raise ProtocolValidationError(
            "topic scenario manifests must cover the complete topic catalog"
        )
    topic_roots = [item.topic_content_root_sha256 for item in scenarios]
    if len(topic_roots) != len(set(topic_roots)):
        raise ProtocolValidationError(
            "topic topic content roots must be globally unique"
        )
    for scenario in scenarios:
        anchor = by_id[scenario.topic_id]
        if (
            scenario.scenario_version != anchor.scenario_version
            or scenario.scenario_template_sha256 != anchor.scenario_template_sha256
            or scenario.manifest_sha256 != anchor.scenario_manifest_sha256
            or scenario.topic_content_root_sha256
            != anchor.topic_content_root_sha256
        ):
            raise ProtocolValidationError(
                "scenario catalog manifest identity mismatch"
            )
    return scenarios


def validate_topic_family_access(
    anchor: TopicAnchor, *, behavioral_family_id: str
) -> None:
    """Allow shared topics to all families and matched family-specific topics."""

    if not isinstance(behavioral_family_id, str) or not behavioral_family_id.strip():
        raise ProtocolValidationError("behavioral_family_id must be non-empty")
    if (
        anchor.topic_scope is TopicScope.FAMILY_SPECIFIC
        and anchor.eligible_behavioral_family_id != behavioral_family_id
    ):
        raise ProtocolValidationError(
            "family-specific topic is accessible only to its eligible behavioral family"
        )


@dataclass(frozen=True)
class TopicSplitPlan:
    """Frozen 18/6/12 split plus the structured six-topic pilot."""

    split_algorithm_id: str
    split_algorithm_version: str
    split_seed: int
    balance_diagnostics_sha256: str
    manifest_sha256: str
    assignment_outcome_blind: bool
    development: Tuple[str, ...]
    calibration: Tuple[str, ...]
    untouched_test: Tuple[str, ...]
    pilot: Tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ("split_algorithm_id", "split_algorithm_version"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ProtocolValidationError(f"{field} must be non-empty")
        if (
            isinstance(self.split_seed, bool)
            or not isinstance(self.split_seed, int)
            or self.split_seed < 0
        ):
            raise ProtocolValidationError(
                "split_seed must be a non-negative integer"
            )
        _sha256(
            self.balance_diagnostics_sha256,
            field="balance_diagnostics_sha256",
        )
        _sha256(self.manifest_sha256, field="manifest_sha256")
        if self.assignment_outcome_blind is not True:
            raise ProtocolValidationError(
                "topic split assignment must be outcome-blind"
            )
        development = _ids(self.development, field="development")
        calibration = _ids(self.calibration, field="calibration")
        untouched = _ids(self.untouched_test, field="untouched_test")
        pilot = _ids(self.pilot, field="pilot")
        for field, values, expected in (
            ("development", development, DEVELOPMENT_TOPICS),
            ("calibration", calibration, CALIBRATION_TOPICS),
            ("untouched_test", untouched, UNTOUCHED_TEST_TOPICS),
            ("pilot", pilot, PILOT_TOPICS),
        ):
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
        for index, left in enumerate(names):
            for right in names[index + 1:]:
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
        for partition, topic_ids in {
            "development": self.development,
            "calibration": self.calibration,
            "untouched_test": self.untouched_test,
        }.items():
            if topic_id in topic_ids:
                return partition
        raise ProtocolValidationError(f"unknown topic_id {topic_id!r}")

    def validate_against_catalog(
        self,
        anchors: Sequence[TopicAnchor],
        *,
        known_behavioral_family_ids: Iterable[str],
        source_candidate_pool_manifests: Sequence[TopicCandidatePoolManifest],
        suitability_rubric_manifest: TopicSuitabilityRubricManifest,
    ) -> None:
        families = _family_ids(known_behavioral_family_ids)
        catalog = validate_anchor_catalog(
            anchors,
            known_behavioral_family_ids=families,
            source_candidate_pool_manifests=source_candidate_pool_manifests,
            suitability_rubric_manifest=suitability_rubric_manifest,
        )
        by_id = {anchor.topic_id: anchor for anchor in catalog}
        if set(self.all_main_topics) != set(by_id):
            raise ProtocolValidationError("topic split/catalog IDs mismatch")
        partitions = {
            "development": self.development,
            "calibration": self.calibration,
            "untouched_test": self.untouched_test,
        }
        for partition, topic_ids in partitions.items():
            subset = [by_id[topic_id] for topic_id in topic_ids]
            shared = sum(x.topic_scope is TopicScope.SHARED_CORE for x in subset)
            if shared != SHARED_BY_PARTITION[partition]:
                raise ProtocolValidationError(
                    f"{partition} has invalid shared-topic composition"
                )
            family_counts = Counter(
                x.eligible_behavioral_family_id for x in subset
                if x.topic_scope is TopicScope.FAMILY_SPECIFIC
            )
            expected = {family_id: FAMILY_BY_PARTITION[partition] for family_id in families}
            if family_counts != expected:
                raise ProtocolValidationError(
                    f"{partition} has invalid family-specific composition"
                )
        pilot = [by_id[topic_id] for topic_id in self.pilot]
        if sum(x.topic_scope is TopicScope.SHARED_CORE for x in pilot) != 2:
            raise ProtocolValidationError("pilot must contain exactly two shared topics")
        pilot_families = Counter(
            x.eligible_behavioral_family_id for x in pilot
            if x.topic_scope is TopicScope.FAMILY_SPECIFIC
        )
        if pilot_families != {family_id: 1 for family_id in families}:
            raise ProtocolValidationError(
                "pilot must contain one family-specific topic per family"
            )


def validate_no_root_leakage(
    root_ids_by_partition: Mapping[str, Iterable[str]]
) -> None:
    """Ensure a root trajectory or fork-prefix group occurs in one partition."""

    normalized = {
        partition: set(_ids(root_ids, field=f"{partition}_root_ids"))
        for partition, root_ids in root_ids_by_partition.items()
    }
    names = tuple(normalized)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            overlap = normalized[left] & normalized[right]
            if overlap:
                raise ProtocolValidationError(
                    f"root-group leakage across {left}/{right}: {sorted(overlap)}"
                )
