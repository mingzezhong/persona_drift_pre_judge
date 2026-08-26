"""Versioned metadata records for the restarted persona-drift study.

The records here make protocol violations visible at construction time.  They
describe artifacts; they do not implement generation, judging, feature
extraction, or causal estimation.
"""

import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, Optional, Sequence, Tuple

from .personas import (
    PersonaCatalog,
    PersonaGeneralizationPlan,
    PersonaGeneralizationRole,
)
from .protocol import (
    FORK_HORIZON,
    MAIN_TURNS,
    ForkDosePlan,
    PressureSchedule,
    ProtocolValidationError,
    validate_main_turn,
)
from .splits import (
    TopicAnchor,
    TopicCandidatePoolManifest,
    TopicScenarioManifest,
    TopicScope,
    TopicSplitPlan,
    TopicSuitabilityRubricManifest,
    compute_topic_content_root_sha256,
    validate_topic_family_access,
    validate_topic_scenario_catalog,
)


SCHEMA_VERSION = "restart-v2.3"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class StudyPhase(str, Enum):
    PILOT = "pilot"
    MAIN = "main"
    INTERVENTION = "intervention"
    EXTERNAL = "external"


class TopicPartition(str, Enum):
    DEVELOPMENT = "development"
    CALIBRATION = "calibration"
    UNTOUCHED_TEST = "untouched_test"


class PredictorFitAccess(str, Enum):
    FIT = "fit"
    EVALUATION_ONLY = "evaluation_only"



class ModelId(str, Enum):
    QWEN3_8B = "Qwen/Qwen3-8B"
    LLAMA_31_8B_INSTRUCT = "meta-llama/Llama-3.1-8B-Instruct"
    GEMMA_3_12B_IT = "google/gemma-3-12b-it"


class ActivationComponent(str, Enum):
    RESID_PRE = "resid_pre"
    ATTN_OUT = "attn_out"
    MLP_OUT = "mlp_out"


class NumericDType(str, Enum):
    FLOAT16 = "float16"
    BFLOAT16 = "bfloat16"
    FLOAT32 = "float32"


class DriftOutcome(str, Enum):
    DRIFT = "drift"
    NO_DRIFT_THROUGH_OBSERVATION_END = "no_drift_through_observation_end"


def _nonempty(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolValidationError(f"{field} must be a non-empty string")


def _nonnegative_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProtocolValidationError(f"{field} must be a non-negative integer")
    return value


def _require_enum(value: object, enum_type: Any, *, field: str) -> None:
    if not isinstance(value, enum_type):
        choices = tuple(item.value for item in enum_type)
        raise ProtocolValidationError(
            f"{field} must be a {enum_type.__name__} member in {choices}; got {value!r}"
        )


def _sha256(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ProtocolValidationError(f"{field} must be 64 lowercase hex characters")


class _SerializableRecord:
    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-friendly dictionary with enum values expanded."""

        def convert(value: Any) -> Any:
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, tuple):
                return [convert(item) for item in value]
            if isinstance(value, dict):
                return {key: convert(item) for key, item in value.items()}
            return value

        return convert(asdict(self))


@dataclass(frozen=True)
class TrajectoryMetadata(_SerializableRecord):
    """Metadata for one complete 25-turn pilot or main trajectory."""

    trajectory_id: str
    phase: StudyPhase
    model_id: ModelId
    model_revision: str
    tokenizer_revision: str
    chat_template_version: str
    behavioral_family_id: str
    persona_trait_id: str
    persona_prompt_variant_id: str
    persona_generalization_role: PersonaGeneralizationRole
    persona_prompt_sha256: str
    persona_catalog_sha256: str
    persona_generalization_plan_sha256: str
    pressure_family: str
    topic_id: str
    topic_scope: TopicScope
    scenario_family_id: str
    eligible_behavioral_family_id: Optional[str]
    scenario_subtype: str
    topic_catalog_manifest_sha256: str
    topic_split_plan_manifest_sha256: str
    scenario_version: str
    scenario_template_sha256: str
    scenario_manifest_sha256: str
    topic_content_root_sha256: str
    topic_move_ids: Tuple[str, ...]
    topic_move_sha256s: Tuple[str, ...]
    pressure_slot_ids: Tuple[str, ...]
    topic_split: TopicPartition
    predictor_fit_access: PredictorFitAccess
    seed: int
    schedule_id: str
    pressure_levels: Tuple[int, ...]
    pressure_template_ids: Tuple[str, ...]
    turn_composition_version: str
    composed_user_turn_sha256s: Tuple[str, ...]
    pre_response_full_prompt_sha256s: Tuple[str, ...]
    generation_config_sha256: str
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field, value in (
            ("trajectory_id", self.trajectory_id),
            ("model_revision", self.model_revision),
            ("tokenizer_revision", self.tokenizer_revision),
            ("chat_template_version", self.chat_template_version),
            ("behavioral_family_id", self.behavioral_family_id),
            ("persona_trait_id", self.persona_trait_id),
            ("persona_prompt_variant_id", self.persona_prompt_variant_id),
            ("pressure_family", self.pressure_family),
            ("topic_id", self.topic_id),
            ("scenario_family_id", self.scenario_family_id),
            ("scenario_subtype", self.scenario_subtype),
            ("scenario_version", self.scenario_version),
            ("schedule_id", self.schedule_id),
            ("turn_composition_version", self.turn_composition_version),
        ):
            _nonempty(value, field=field)
        if self.schema_version != SCHEMA_VERSION:
            raise ProtocolValidationError(
                f"schema_version must be {SCHEMA_VERSION!r}"
            )
        _require_enum(self.phase, StudyPhase, field="phase")
        if self.phase not in (StudyPhase.PILOT, StudyPhase.MAIN):
            raise ProtocolValidationError(
                "complete trajectory records are limited to pilot/main phases"
            )
        _require_enum(self.model_id, ModelId, field="model_id")
        _require_enum(
            self.persona_generalization_role,
            PersonaGeneralizationRole,
            field="persona_generalization_role",
        )
        _sha256(self.persona_prompt_sha256, field="persona_prompt_sha256")
        _sha256(self.persona_catalog_sha256, field="persona_catalog_sha256")
        _sha256(
            self.persona_generalization_plan_sha256,
            field="persona_generalization_plan_sha256",
        )
        _require_enum(self.topic_scope, TopicScope, field="topic_scope")
        if self.topic_scope is TopicScope.SHARED_CORE:
            if self.eligible_behavioral_family_id is not None:
                raise ProtocolValidationError(
                    "shared trajectory topics cannot bind an eligible behavioral family"
                )
        else:
            _nonempty(
                self.eligible_behavioral_family_id,
                field="eligible_behavioral_family_id",
            )
            if self.eligible_behavioral_family_id != self.behavioral_family_id:
                raise ProtocolValidationError(
                    "family-specific trajectory topic must match the persona family"
                )
        _sha256(self.topic_catalog_manifest_sha256, field="topic_catalog_manifest_sha256")
        _sha256(self.topic_split_plan_manifest_sha256, field="topic_split_plan_manifest_sha256")
        _sha256(self.scenario_template_sha256, field="scenario_template_sha256")
        _sha256(self.scenario_manifest_sha256, field="scenario_manifest_sha256")
        _sha256(
            self.topic_content_root_sha256,
            field="topic_content_root_sha256",
        )
        move_ids = tuple(self.topic_move_ids)
        move_hashes = tuple(self.topic_move_sha256s)
        if len(move_ids) != MAIN_TURNS or any(
            not isinstance(item, str) or not item.strip() for item in move_ids
        ):
            raise ProtocolValidationError(
                "topic_move_ids must contain 25 non-empty pressure-free scenario IDs"
            )
        if len(move_hashes) != MAIN_TURNS:
            raise ProtocolValidationError("topic_move_sha256s must contain 25 hashes")
        for index, value in enumerate(move_hashes):
            _sha256(value, field=f"topic_move_sha256s[{index}]")
        expected_content_root = compute_topic_content_root_sha256(move_hashes)
        if self.topic_content_root_sha256 != expected_content_root:
            raise ProtocolValidationError(
                "topic_content_root_sha256 does not match topic_move_sha256s"
            )
        object.__setattr__(self, "topic_move_ids", move_ids)
        object.__setattr__(self, "topic_move_sha256s", move_hashes)
        pressure_slots = tuple(self.pressure_slot_ids)
        if len(pressure_slots) != MAIN_TURNS or any(
            not isinstance(item, str) or not item.strip() for item in pressure_slots
        ):
            raise ProtocolValidationError(
                "pressure_slot_ids must contain 25 non-empty scenario slot IDs"
            )
        object.__setattr__(self, "pressure_slot_ids", pressure_slots)
        _require_enum(self.topic_split, TopicPartition, field="topic_split")
        _require_enum(
            self.predictor_fit_access,
            PredictorFitAccess,
            field="predictor_fit_access",
        )
        expected_fit_access = (
            PredictorFitAccess.FIT
            if (
                self.topic_split is TopicPartition.DEVELOPMENT
                and self.persona_generalization_role
                is PersonaGeneralizationRole.SEEN_TRAIT_OBSERVED_WORDING
            )
            else PredictorFitAccess.EVALUATION_ONLY
        )
        if self.predictor_fit_access is not expected_fit_access:
            raise ProtocolValidationError(
                "predictor_fit_access must require both a development topic and "
                "a seen-trait observed-wording persona"
            )
        if self.phase is StudyPhase.PILOT and self.topic_split is not TopicPartition.DEVELOPMENT:
            raise ProtocolValidationError(
                "pilot topics must be selected from the development partition"
            )
        if (
            self.phase is StudyPhase.PILOT
            and self.persona_generalization_role
            is not PersonaGeneralizationRole.SEEN_TRAIT_OBSERVED_WORDING
        ):
            raise ProtocolValidationError(
                "outcome-bearing pilot trajectories require a seen-trait "
                "observed-wording persona"
            )
        _nonnegative_int(self.seed, field="seed")
        schedule = PressureSchedule(self.schedule_id, tuple(self.pressure_levels))
        object.__setattr__(self, "pressure_levels", schedule.levels)
        template_ids = tuple(self.pressure_template_ids)
        if len(template_ids) != MAIN_TURNS or any(
            not isinstance(item, str) or not item.strip() for item in template_ids
        ):
            raise ProtocolValidationError(
                "pressure_template_ids must contain 25 non-empty frozen IDs"
            )
        object.__setattr__(self, "pressure_template_ids", template_ids)
        composed_hashes = tuple(self.composed_user_turn_sha256s)
        prompt_hashes = tuple(self.pre_response_full_prompt_sha256s)
        if len(composed_hashes) != MAIN_TURNS:
            raise ProtocolValidationError(
                "composed_user_turn_sha256s must contain 25 hashes"
            )
        if len(prompt_hashes) != MAIN_TURNS:
            raise ProtocolValidationError(
                "pre_response_full_prompt_sha256s must contain 25 hashes"
            )
        for field, values in (
            ("composed_user_turn_sha256s", composed_hashes),
            ("pre_response_full_prompt_sha256s", prompt_hashes),
        ):
            for index, value in enumerate(values):
                _sha256(value, field=f"{field}[{index}]")
            if len(set(values)) != MAIN_TURNS:
                raise ProtocolValidationError(
                    f"{field} must contain 25 unique hashes"
                )
        object.__setattr__(
            self, "composed_user_turn_sha256s", composed_hashes
        )
        object.__setattr__(
            self, "pre_response_full_prompt_sha256s", prompt_hashes
        )
        _sha256(self.generation_config_sha256, field="generation_config_sha256")


def validate_trajectory_persona_identity(
    record: TrajectoryMetadata,
    *,
    persona_catalog: PersonaCatalog,
    persona_generalization_plan: PersonaGeneralizationPlan,
    persona_catalog_manifest_sha256: str,
    persona_generalization_plan_manifest_sha256: str,
) -> TrajectoryMetadata:
    """Validate one trajectory identity against frozen persona manifests.

    ``TrajectoryMetadata`` remains a serializable record type, but a generation
    runner must call this API (or the factory below) before accepting a record.
    The explicit expected manifest hashes prevent a structurally valid record
    from silently binding to a different catalog or holdout plan.
    """

    if not isinstance(record, TrajectoryMetadata):
        raise ProtocolValidationError("record must be a TrajectoryMetadata instance")
    if not isinstance(persona_catalog, PersonaCatalog):
        raise ProtocolValidationError("persona_catalog must be a PersonaCatalog")
    if not isinstance(persona_generalization_plan, PersonaGeneralizationPlan):
        raise ProtocolValidationError(
            "persona_generalization_plan must be a PersonaGeneralizationPlan"
        )
    _sha256(
        persona_catalog_manifest_sha256,
        field="persona_catalog_manifest_sha256",
    )
    _sha256(
        persona_generalization_plan_manifest_sha256,
        field="persona_generalization_plan_manifest_sha256",
    )
    if persona_generalization_plan.catalog != persona_catalog:
        raise ProtocolValidationError(
            "persona generalization plan is backed by a different catalog"
        )
    if record.persona_catalog_sha256 != persona_catalog_manifest_sha256:
        raise ProtocolValidationError("trajectory persona catalog manifest hash mismatch")
    if (
        record.persona_generalization_plan_sha256
        != persona_generalization_plan_manifest_sha256
    ):
        raise ProtocolValidationError(
            "trajectory persona generalization plan manifest hash mismatch"
        )

    variant = persona_catalog.variants_by_id.get(record.persona_prompt_variant_id)
    if variant is None:
        raise ProtocolValidationError("trajectory references an unknown prompt variant")
    if record.persona_prompt_sha256 != variant.prompt_sha256:
        raise ProtocolValidationError("trajectory persona prompt hash mismatch")
    persona_generalization_plan.validate_assignment(
        family_id=record.behavioral_family_id,
        trait_id=record.persona_trait_id,
        variant_id=record.persona_prompt_variant_id,
        declared_role=record.persona_generalization_role,
    )
    return record


def validate_trajectory_topic_identity(
    record: TrajectoryMetadata,
    *,
    topic_catalog: Sequence[TopicAnchor],
    topic_split_plan: TopicSplitPlan,
    topic_scenario_manifests: Sequence[TopicScenarioManifest],
    source_candidate_pool_manifests: Sequence[TopicCandidatePoolManifest],
    suitability_rubric_manifest: TopicSuitabilityRubricManifest,
    persona_catalog: PersonaCatalog,
    topic_catalog_manifest_sha256: str,
) -> TrajectoryMetadata:
    """Bind a trajectory to the frozen topic hierarchy and both access axes."""

    if not isinstance(record, TrajectoryMetadata):
        raise ProtocolValidationError("record must be a TrajectoryMetadata instance")
    if not isinstance(topic_split_plan, TopicSplitPlan):
        raise ProtocolValidationError("topic_split_plan must be a TopicSplitPlan")
    if not isinstance(persona_catalog, PersonaCatalog):
        raise ProtocolValidationError("persona_catalog must be a PersonaCatalog")
    _sha256(topic_catalog_manifest_sha256, field="topic_catalog_manifest_sha256")
    family_ids = tuple(family.family_id for family in persona_catalog.families)
    topic_split_plan.validate_against_catalog(
        topic_catalog,
        known_behavioral_family_ids=family_ids,
        source_candidate_pool_manifests=source_candidate_pool_manifests,
        suitability_rubric_manifest=suitability_rubric_manifest,
    )
    if record.behavioral_family_id not in set(family_ids):
        raise ProtocolValidationError("trajectory references an unknown persona family")
    if record.topic_catalog_manifest_sha256 != topic_catalog_manifest_sha256:
        raise ProtocolValidationError("trajectory topic catalog manifest hash mismatch")
    if record.topic_split_plan_manifest_sha256 != topic_split_plan.manifest_sha256:
        raise ProtocolValidationError("trajectory topic split manifest hash mismatch")
    anchors_by_id = {anchor.topic_id: anchor for anchor in topic_catalog}
    anchor = anchors_by_id.get(record.topic_id)
    if anchor is None:
        raise ProtocolValidationError("trajectory references an unknown topic")
    scenarios = validate_topic_scenario_catalog(
        topic_catalog, topic_scenario_manifests
    )
    scenario = {item.topic_id: item for item in scenarios}[record.topic_id]
    expected_partition = TopicPartition(
        topic_split_plan.partition_for(record.topic_id)
    )
    if record.topic_split is not expected_partition:
        raise ProtocolValidationError("trajectory topic partition mismatch")
    if (
        record.phase is StudyPhase.PILOT
        and record.topic_id not in topic_split_plan.pilot
    ):
        raise ProtocolValidationError(
            "pilot trajectory topic_id must belong to the frozen pilot subset"
        )
    if (
        record.topic_scope is not anchor.topic_scope
        or record.scenario_family_id != anchor.scenario_family_id
        or record.eligible_behavioral_family_id
        != anchor.eligible_behavioral_family_id
        or record.scenario_subtype != anchor.scenario_subtype
    ):
        raise ProtocolValidationError("trajectory topic hierarchy identity mismatch")
    if (
        record.scenario_version != anchor.scenario_version
        or record.scenario_version != scenario.scenario_version
        or record.scenario_template_sha256 != anchor.scenario_template_sha256
        or record.scenario_template_sha256 != scenario.scenario_template_sha256
        or record.scenario_manifest_sha256 != anchor.scenario_manifest_sha256
        or record.scenario_manifest_sha256 != scenario.manifest_sha256
        or record.topic_content_root_sha256
        != anchor.topic_content_root_sha256
        or record.topic_content_root_sha256 != scenario.topic_content_root_sha256
    ):
        raise ProtocolValidationError("trajectory scenario manifest identity mismatch")
    if (
        record.topic_move_ids != scenario.ordered_topic_move_ids
        or record.topic_move_sha256s != scenario.ordered_topic_move_sha256s
        or record.pressure_slot_ids != scenario.pressure_slot_ids
    ):
        raise ProtocolValidationError(
            "trajectory ordered topic moves or pressure slots mismatch scenario manifest"
        )
    validate_topic_family_access(
        anchor, behavioral_family_id=record.behavioral_family_id
    )
    return record


def create_manifest_validated_trajectory_metadata(
    *,
    persona_catalog: PersonaCatalog,
    persona_generalization_plan: PersonaGeneralizationPlan,
    persona_catalog_manifest_sha256: str,
    persona_generalization_plan_manifest_sha256: str,
    topic_catalog: Sequence[TopicAnchor],
    topic_split_plan: TopicSplitPlan,
    topic_scenario_manifests: Sequence[TopicScenarioManifest],
    source_candidate_pool_manifests: Sequence[TopicCandidatePoolManifest],
    suitability_rubric_manifest: TopicSuitabilityRubricManifest,
    topic_catalog_manifest_sha256: str,
    **metadata_fields: Any,
) -> TrajectoryMetadata:
    """Construct a trajectory and validate all Persona, Topic, and move manifests."""

    reserved = {
        "persona_catalog_sha256",
        "persona_generalization_plan_sha256",
        "topic_catalog_manifest_sha256",
        "topic_split_plan_manifest_sha256",
        "scenario_manifest_sha256",
        "topic_content_root_sha256",
    }
    supplied = reserved.intersection(metadata_fields)
    if supplied:
        raise ProtocolValidationError(
            f"factory owns manifest hash fields; remove {sorted(supplied)}"
        )
    topic_id = metadata_fields.get("topic_id")
    scenarios_by_id = {
        item.topic_id: item for item in tuple(topic_scenario_manifests)
        if isinstance(item, TopicScenarioManifest)
    }
    if topic_id not in scenarios_by_id:
        raise ProtocolValidationError(
            "factory topic_id must have a TopicScenarioManifest"
        )
    record = TrajectoryMetadata(
        persona_catalog_sha256=persona_catalog_manifest_sha256,
        persona_generalization_plan_sha256=(
            persona_generalization_plan_manifest_sha256
        ),
        topic_catalog_manifest_sha256=topic_catalog_manifest_sha256,
        topic_split_plan_manifest_sha256=topic_split_plan.manifest_sha256,
        scenario_manifest_sha256=scenarios_by_id[topic_id].manifest_sha256,
        topic_content_root_sha256=(
            scenarios_by_id[topic_id].topic_content_root_sha256
        ),
        **metadata_fields,
    )
    validate_trajectory_persona_identity(
        record,
        persona_catalog=persona_catalog,
        persona_generalization_plan=persona_generalization_plan,
        persona_catalog_manifest_sha256=persona_catalog_manifest_sha256,
        persona_generalization_plan_manifest_sha256=(
            persona_generalization_plan_manifest_sha256
        ),
    )
    return validate_trajectory_topic_identity(
        record,
        topic_catalog=topic_catalog,
        topic_split_plan=topic_split_plan,
        topic_scenario_manifests=topic_scenario_manifests,
        source_candidate_pool_manifests=source_candidate_pool_manifests,
        suitability_rubric_manifest=suitability_rubric_manifest,
        persona_catalog=persona_catalog,
        topic_catalog_manifest_sha256=topic_catalog_manifest_sha256,
    )


@dataclass(frozen=True)
class ActivationSnapshotMetadata(_SerializableRecord):
    """Index entry for one saved all-layer component vector.

    The primary measurement is fixed at the final prompt token at Turn ``t^-``:
    after U_t is in the prompt but before A_t exists. A post-response vector
    cannot be mislabeled as an early-warning feature through this schema.
    """

    trajectory_id: str
    main_turn: int
    layer_index: int
    component: ActivationComponent
    hidden_size: int
    vector_shape: Tuple[int, ...]
    storage_dtype: NumericDType
    compute_dtype: NumericDType
    vector_uri: str
    vector_sha256: str
    prompt_sha256: str
    token_index: int
    hook_contract_version: str
    available_at_turn: int
    token_position: str = "final_prompt_token"
    timing: str = "pre_response"
    availability_boundary: str = "t_minus_pre_response"
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _nonempty(self.trajectory_id, field="trajectory_id")
        validate_main_turn(self.main_turn)
        validate_main_turn(self.available_at_turn)
        if self.available_at_turn != self.main_turn:
            raise ProtocolValidationError(
                "a pre-response snapshot must declare available_at_turn equal to its main_turn"
            )
        _nonnegative_int(self.layer_index, field="layer_index")
        _nonnegative_int(self.token_index, field="token_index")
        if isinstance(self.hidden_size, bool) or not isinstance(self.hidden_size, int) or self.hidden_size <= 0:
            raise ProtocolValidationError("hidden_size must be a positive integer")
        if tuple(self.vector_shape) != (self.hidden_size,):
            raise ProtocolValidationError(
                "vector_shape must equal (hidden_size,) for a final-token vector"
            )
        object.__setattr__(self, "vector_shape", tuple(self.vector_shape))
        _require_enum(self.component, ActivationComponent, field="component")
        _require_enum(self.storage_dtype, NumericDType, field="storage_dtype")
        _require_enum(self.compute_dtype, NumericDType, field="compute_dtype")
        if self.storage_dtype not in (NumericDType.FLOAT16, NumericDType.BFLOAT16):
            raise ProtocolValidationError(
                "storage_dtype must be float16 or bfloat16; float32 primary storage is disabled"
            )
        _nonempty(self.vector_uri, field="vector_uri")
        _nonempty(self.hook_contract_version, field="hook_contract_version")
        _sha256(self.vector_sha256, field="vector_sha256")
        _sha256(self.prompt_sha256, field="prompt_sha256")
        if self.token_position != "final_prompt_token":
            raise ProtocolValidationError(
                "primary snapshots must use token_position='final_prompt_token'"
            )
        if self.timing != "pre_response":
            raise ProtocolValidationError(
                "primary snapshots must use timing='pre_response' at Turn t^-"
            )
        if self.availability_boundary != "t_minus_pre_response":
            raise ProtocolValidationError(
                "primary snapshots must use availability_boundary='t_minus_pre_response'"
            )
        if self.schema_version != SCHEMA_VERSION:
            raise ProtocolValidationError(
                f"schema_version must be {SCHEMA_VERSION!r}"
            )


def validate_feature_cutoff(
    snapshots: Tuple[ActivationSnapshotMetadata, ...], *, prediction_cutoff_turn: int
) -> None:
    """Reject snapshots unavailable at a prospective prediction cut-off."""

    cutoff = validate_main_turn(prediction_cutoff_turn)
    leaked = sorted(
        {
            snapshot.available_at_turn
            for snapshot in snapshots
            if snapshot.available_at_turn > cutoff
        }
    )
    if leaked:
        raise ProtocolValidationError(
            f"feature-time leakage: turns {leaked} are later than prediction cut-off turn {cutoff}"
        )


def validate_activation_coverage(
    snapshots: Tuple[ActivationSnapshotMetadata, ...],
    *,
    trajectory_id: str,
    layer_count: int,
) -> None:
    """Require every turn × layer × primary component exactly once."""

    _nonempty(trajectory_id, field="trajectory_id")
    if isinstance(layer_count, bool) or not isinstance(layer_count, int) or layer_count <= 0:
        raise ProtocolValidationError("layer_count must be a positive integer")
    keys = []
    for snapshot in snapshots:
        if snapshot.trajectory_id != trajectory_id:
            raise ProtocolValidationError("activation coverage mixes trajectory IDs")
        if snapshot.layer_index >= layer_count:
            raise ProtocolValidationError(
                f"layer_index {snapshot.layer_index} is outside 0--{layer_count - 1}"
            )
        keys.append((snapshot.main_turn, snapshot.layer_index, snapshot.component))
    if len(keys) != len(set(keys)):
        raise ProtocolValidationError("activation coverage contains duplicate component keys")
    expected = {
        (turn, layer, component)
        for turn in range(1, MAIN_TURNS + 1)
        for layer in range(layer_count)
        for component in ActivationComponent
    }
    missing = expected - set(keys)
    unexpected = set(keys) - expected
    if missing or unexpected:
        raise ProtocolValidationError(
            "incomplete all-layer activation coverage: "
            f"missing={len(missing)}, unexpected={len(unexpected)}"
        )


def validate_activation_prompt_binding(
    snapshots: Sequence[ActivationSnapshotMetadata],
    trajectory_metadata: TrajectoryMetadata,
) -> None:
    """Bind every activation to its trajectory's exact pre-response prompt."""

    if not isinstance(trajectory_metadata, TrajectoryMetadata):
        raise ProtocolValidationError(
            "trajectory_metadata must be a TrajectoryMetadata instance"
        )
    for snapshot in snapshots:
        if not isinstance(snapshot, ActivationSnapshotMetadata):
            raise ProtocolValidationError(
                "snapshots must contain ActivationSnapshotMetadata records"
            )
        if snapshot.trajectory_id != trajectory_metadata.trajectory_id:
            raise ProtocolValidationError(
                "activation snapshot trajectory_id does not match trajectory metadata"
            )
        expected_prompt_sha256 = (
            trajectory_metadata.pre_response_full_prompt_sha256s[
                snapshot.main_turn - 1
            ]
        )
        if snapshot.prompt_sha256 != expected_prompt_sha256:
            raise ProtocolValidationError(
                "activation snapshot prompt_sha256 does not match the frozen "
                "pre-response full prompt"
            )


@dataclass(frozen=True)
class DriftOutcomeMetadata(_SerializableRecord):
    """Behavior-only trajectory outcome.

    The exact judge rubric remains a preregistration item, so every label must
    carry an immutable protocol version rather than relying on implicit code.
    """

    trajectory_id: str
    outcome: DriftOutcome
    label_protocol_version: str
    onset_main_turn: Optional[int] = None
    observation_end_main_turn: int = MAIN_TURNS
    judged_without_activations: bool = True
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _nonempty(self.trajectory_id, field="trajectory_id")
        _nonempty(self.label_protocol_version, field="label_protocol_version")
        _require_enum(self.outcome, DriftOutcome, field="outcome")
        observation_end = validate_main_turn(self.observation_end_main_turn)
        if self.judged_without_activations is not True:
            raise ProtocolValidationError(
                "behavior labels must be assigned without exposing activations"
            )
        if self.outcome is DriftOutcome.DRIFT:
            if self.onset_main_turn is None:
                raise ProtocolValidationError("drift outcome requires onset_main_turn")
            onset = validate_main_turn(self.onset_main_turn)
            if onset > observation_end:
                raise ProtocolValidationError(
                    "onset_main_turn cannot be later than observation_end_main_turn"
                )
        elif self.onset_main_turn is not None:
            raise ProtocolValidationError(
                "no-drift-through-observation-end outcome cannot carry a drift onset"
            )
        if self.schema_version != SCHEMA_VERSION:
            raise ProtocolValidationError(
                f"schema_version must be {SCHEMA_VERSION!r}"
            )

    @property
    def event_observed(self) -> bool:
        return self.outcome is DriftOutcome.DRIFT

    @property
    def censor_turn(self) -> Optional[int]:
        if self.event_observed:
            return None
        return self.observation_end_main_turn

    @property
    def event_or_censor_turn(self) -> int:
        if self.event_observed:
            assert self.onset_main_turn is not None
            return self.onset_main_turn
        return self.observation_end_main_turn

    @property
    def behavior_stable_through_observation_end(self) -> bool:
        return not self.event_observed


@dataclass(frozen=True)
class ForkMetadata(_SerializableRecord):
    """Metadata for one randomized five-turn prefix-fork continuation.

    ``prefix_turn=t`` is the Turn ``t^+`` boundary: the copied prefix already
    contains assistant response A_t. This differs intentionally from the
    observational activation at t^-.
    """

    fork_id: str
    source_trajectory_id: str
    prefix_turn: int
    planned_future_levels: Tuple[int, ...]
    dose_ppu: int
    continuation_seed: int
    randomization_id: str
    source_prefix_not_drifted: bool
    prefix_includes_assistant_response_at_t: bool = True
    prefix_boundary: str = "t_plus_post_response"
    horizon: int = FORK_HORIZON
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field, value in (
            ("fork_id", self.fork_id),
            ("source_trajectory_id", self.source_trajectory_id),
            ("randomization_id", self.randomization_id),
        ):
            _nonempty(value, field=field)
        if self.source_prefix_not_drifted is not True:
            raise ProtocolValidationError(
                "intervention forks require an eligible, not-yet-drifted prefix at t^+"
            )
        if self.prefix_includes_assistant_response_at_t is not True:
            raise ProtocolValidationError(
                "fork prefix_turn=t is t^+ and must include assistant response A_t"
            )
        if self.prefix_boundary != "t_plus_post_response":
            raise ProtocolValidationError(
                "fork prefixes must use prefix_boundary='t_plus_post_response'"
            )
        _nonnegative_int(self.continuation_seed, field="continuation_seed")
        plan = ForkDosePlan(
            prefix_turn=self.prefix_turn,
            planned_future_levels=tuple(self.planned_future_levels),
            dose_ppu=self.dose_ppu,
            horizon=self.horizon,
        )
        object.__setattr__(self, "planned_future_levels", plan.planned_future_levels)
        if self.schema_version != SCHEMA_VERSION:
            raise ProtocolValidationError(
                f"schema_version must be {SCHEMA_VERSION!r}"
            )

    @property
    def intervened_future_levels(self) -> Tuple[int, ...]:
        return ForkDosePlan(
            prefix_turn=self.prefix_turn,
            planned_future_levels=self.planned_future_levels,
            dose_ppu=self.dose_ppu,
            horizon=self.horizon,
        ).intervened_future_levels

    @property
    def extra_exposure_ppu_turns(self) -> int:
        return self.dose_ppu * self.horizon
