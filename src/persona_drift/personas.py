"""Fail-fast persona hierarchy contracts for restart-v2.2.

The module validates identities and holdout boundaries only.  It intentionally
contains no real family or trait names: those remain a G1 manifest decision.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import Enum
import re
from typing import Dict, Iterable, Tuple

from .protocol import ProtocolValidationError


EXPECTED_FAMILIES = 4
MIN_TRAITS_PER_FAMILY = 4
MAX_TRAITS_PER_FAMILY = 6
MIN_TOTAL_TRAITS = 16
MAX_TOTAL_TRAITS = 24
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _nonempty(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolValidationError(f"{field} must be a non-empty string")


def _sha256(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ProtocolValidationError(f"{field} must be 64 lowercase hex characters")


def _unique(values: Iterable[str], *, field: str) -> Tuple[str, ...]:
    result = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in result):
        raise ProtocolValidationError(f"{field} must contain non-empty IDs")
    if len(result) != len(set(result)):
        raise ProtocolValidationError(f"{field} contains duplicate IDs")
    return result


class PersonaItemRole(str, Enum):
    DEFINITION = "trait_definition"
    VECTOR_EXTRACTION = "persona_vector_extraction"
    HELD_OUT_VALIDATION = "held_out_validation"


class PersonaGeneralizationRole(str, Enum):
    SEEN_TRAIT_OBSERVED_WORDING = "seen_trait_observed_wording"
    UNSEEN_PROMPT_WORDING = "unseen_prompt_wording"
    WITHIN_FAMILY_UNSEEN_TRAIT = "within_family_unseen_trait"
    UNSEEN_BEHAVIORAL_FAMILY = "unseen_behavioral_family"


@dataclass(frozen=True)
class BehavioralFamily:
    family_id: str
    definition_version: str

    def __post_init__(self) -> None:
        _nonempty(self.family_id, field="family_id")
        _nonempty(self.definition_version, field="definition_version")


@dataclass(frozen=True)
class PersonaTrait:
    trait_id: str
    family_id: str
    source_repository: str
    source_revision: str
    source_file: str
    source_license: str
    source_manifest_sha256: str

    def __post_init__(self) -> None:
        for field in (
            "trait_id",
            "family_id",
            "source_repository",
            "source_revision",
            "source_file",
            "source_license",
        ):
            _nonempty(getattr(self, field), field=field)
        _sha256(self.source_manifest_sha256, field="source_manifest_sha256")


@dataclass(frozen=True)
class PersonaPromptVariant:
    variant_id: str
    trait_id: str
    prompt_version: str
    prompt_sha256: str

    def __post_init__(self) -> None:
        for field in ("variant_id", "trait_id", "prompt_version"):
            _nonempty(getattr(self, field), field=field)
        _sha256(self.prompt_sha256, field="prompt_sha256")


@dataclass(frozen=True)
class PersonaEvaluationItem:
    item_id: str
    trait_id: str
    source_item_id: str
    content_sha256: str
    role: PersonaItemRole

    def __post_init__(self) -> None:
        for field in ("item_id", "trait_id", "source_item_id"):
            _nonempty(getattr(self, field), field=field)
        _sha256(self.content_sha256, field="content_sha256")
        if not isinstance(self.role, PersonaItemRole):
            raise ProtocolValidationError("role must be a PersonaItemRole member")


@dataclass(frozen=True)
class PersonaCatalog:
    families: Tuple[BehavioralFamily, ...]
    traits: Tuple[PersonaTrait, ...]
    prompt_variants: Tuple[PersonaPromptVariant, ...]
    evaluation_items: Tuple[PersonaEvaluationItem, ...]

    def __post_init__(self) -> None:
        families = tuple(self.families)
        traits = tuple(self.traits)
        variants = tuple(self.prompt_variants)
        items = tuple(self.evaluation_items)
        family_ids = _unique((item.family_id for item in families), field="family_ids")
        trait_ids = _unique((item.trait_id for item in traits), field="trait_ids")
        _unique((item.source_file for item in traits), field="trait_source_files")
        _unique((item.variant_id for item in variants), field="variant_ids")
        _unique((item.item_id for item in items), field="item_ids")
        _unique((item.source_item_id for item in items), field="source_item_ids")
        _unique((item.content_sha256 for item in items), field="item_content_sha256s")

        if len(family_ids) != EXPECTED_FAMILIES:
            raise ProtocolValidationError(
                f"persona catalog must contain exactly {EXPECTED_FAMILIES} families"
            )
        if not MIN_TOTAL_TRAITS <= len(trait_ids) <= MAX_TOTAL_TRAITS:
            raise ProtocolValidationError(
                f"persona catalog must contain {MIN_TOTAL_TRAITS}--{MAX_TOTAL_TRAITS} true traits"
            )
        trait_counts = Counter(item.family_id for item in traits)
        if set(trait_counts) != set(family_ids):
            raise ProtocolValidationError("every trait must reference one catalog family")
        for family_id, count in trait_counts.items():
            if not MIN_TRAITS_PER_FAMILY <= count <= MAX_TRAITS_PER_FAMILY:
                raise ProtocolValidationError(
                    f"family {family_id!r} must contain {MIN_TRAITS_PER_FAMILY}--"
                    f"{MAX_TRAITS_PER_FAMILY} true traits"
                )

        trait_set = set(trait_ids)
        if any(item.trait_id not in trait_set for item in variants):
            raise ProtocolValidationError("prompt variant references an unknown trait")
        if any(item.trait_id not in trait_set for item in items):
            raise ProtocolValidationError("evaluation item references an unknown trait")
        variants_by_trait = Counter(item.trait_id for item in variants)
        if set(variants_by_trait) != trait_set:
            raise ProtocolValidationError("every trait requires at least one prompt variant")
        roles_by_trait: Dict[str, set[PersonaItemRole]] = defaultdict(set)
        for item in items:
            roles_by_trait[item.trait_id].add(item.role)
        required_roles = set(PersonaItemRole)
        for trait_id in trait_ids:
            if roles_by_trait[trait_id] != required_roles:
                raise ProtocolValidationError(
                    f"trait {trait_id!r} must have disjoint items in all three item roles"
                )

        object.__setattr__(self, "families", families)
        object.__setattr__(self, "traits", traits)
        object.__setattr__(self, "prompt_variants", variants)
        object.__setattr__(self, "evaluation_items", items)

    @property
    def traits_by_id(self) -> Dict[str, PersonaTrait]:
        return {item.trait_id: item for item in self.traits}

    @property
    def variants_by_id(self) -> Dict[str, PersonaPromptVariant]:
        return {item.variant_id: item for item in self.prompt_variants}


@dataclass(frozen=True)
class PersonaGeneralizationPlan:
    """Three-level holdouts; all unspecified catalog members are development."""

    catalog: PersonaCatalog
    unseen_family_ids: Tuple[str, ...]
    within_family_unseen_trait_ids: Tuple[str, ...]
    unseen_prompt_variant_ids: Tuple[str, ...]

    def __post_init__(self) -> None:
        unseen_families = _unique(self.unseen_family_ids, field="unseen_family_ids")
        unseen_traits = _unique(
            self.within_family_unseen_trait_ids,
            field="within_family_unseen_trait_ids",
        )
        unseen_variants = _unique(
            self.unseen_prompt_variant_ids, field="unseen_prompt_variant_ids"
        )
        family_ids = {item.family_id for item in self.catalog.families}
        if len(unseen_families) != 1 or not set(unseen_families) < family_ids:
            raise ProtocolValidationError(
                "exactly one complete behavioral family must be unseen"
            )
        traits = self.catalog.traits_by_id
        variants = self.catalog.variants_by_id
        if not unseen_traits or not set(unseen_traits).issubset(traits):
            raise ProtocolValidationError("unseen trait IDs must be non-empty catalog IDs")
        if not unseen_variants or not set(unseen_variants).issubset(variants):
            raise ProtocolValidationError("unseen variant IDs must be non-empty catalog IDs")
        if any(traits[item].family_id in unseen_families for item in unseen_traits):
            raise ProtocolValidationError(
                "within-family unseen traits cannot belong to an unseen family"
            )
        for variant_id in unseen_variants:
            trait = traits[variants[variant_id].trait_id]
            if trait.trait_id in unseen_traits or trait.family_id in unseen_families:
                raise ProtocolValidationError(
                    "wording holdouts must belong to development traits in development families"
                )

        variants_by_trait: Dict[str, set[str]] = defaultdict(set)
        for variant in self.catalog.prompt_variants:
            variants_by_trait[variant.trait_id].add(variant.variant_id)
        for family_id in family_ids - set(unseen_families):
            family_traits = {
                item.trait_id for item in self.catalog.traits if item.family_id == family_id
            }
            family_unseen = family_traits & set(unseen_traits)
            family_development = family_traits - set(unseen_traits)
            if not family_unseen or not family_development:
                raise ProtocolValidationError(
                    "each development family needs development and within-family unseen traits"
                )
            for trait_id in family_development:
                heldout = variants_by_trait[trait_id] & set(unseen_variants)
                observed = variants_by_trait[trait_id] - set(unseen_variants)
                if not heldout or not observed:
                    raise ProtocolValidationError(
                        "each development trait needs observed and unseen-wording variants"
                    )

        object.__setattr__(self, "unseen_family_ids", unseen_families)
        object.__setattr__(self, "within_family_unseen_trait_ids", unseen_traits)
        object.__setattr__(self, "unseen_prompt_variant_ids", unseen_variants)

    def role_for(self, *, family_id: str, trait_id: str, variant_id: str) -> PersonaGeneralizationRole:
        traits = self.catalog.traits_by_id
        variants = self.catalog.variants_by_id
        if trait_id not in traits or variant_id not in variants:
            raise ProtocolValidationError("unknown persona trait or prompt variant")
        if traits[trait_id].family_id != family_id or variants[variant_id].trait_id != trait_id:
            raise ProtocolValidationError("family/trait/variant identity mismatch")
        if family_id in self.unseen_family_ids:
            return PersonaGeneralizationRole.UNSEEN_BEHAVIORAL_FAMILY
        if trait_id in self.within_family_unseen_trait_ids:
            return PersonaGeneralizationRole.WITHIN_FAMILY_UNSEEN_TRAIT
        if variant_id in self.unseen_prompt_variant_ids:
            return PersonaGeneralizationRole.UNSEEN_PROMPT_WORDING
        return PersonaGeneralizationRole.SEEN_TRAIT_OBSERVED_WORDING

    def validate_assignment(
        self,
        *,
        family_id: str,
        trait_id: str,
        variant_id: str,
        declared_role: PersonaGeneralizationRole,
    ) -> None:
        if not isinstance(declared_role, PersonaGeneralizationRole):
            raise ProtocolValidationError(
                "declared_role must be a PersonaGeneralizationRole member"
            )
        expected = self.role_for(
            family_id=family_id, trait_id=trait_id, variant_id=variant_id
        )
        if declared_role is not expected:
            raise ProtocolValidationError(
                f"persona generalization role mismatch: expected {expected.value!r}"
            )
