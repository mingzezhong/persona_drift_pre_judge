import hashlib
import unittest

from persona_drift.personas import (
    BehavioralFamily,
    PersonaCatalog,
    PersonaEvaluationItem,
    PersonaGeneralizationPlan,
    PersonaGeneralizationRole,
    PersonaItemRole,
    PersonaPromptVariant,
    PersonaTrait,
)
from persona_drift.protocol import ProtocolValidationError


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_components():
    families = tuple(
        BehavioralFamily(family_id=f"family-{family}", definition_version="v1")
        for family in range(4)
    )
    traits = []
    variants = []
    items = []
    for family in range(4):
        for trait in range(4):
            trait_id = f"trait-{family}-{trait}"
            traits.append(
                PersonaTrait(
                    trait_id=trait_id,
                    family_id=f"family-{family}",
                    source_repository="official/source",
                    source_revision="revision-sha",
                    source_file=f"persona/{trait_id}.jsonl",
                    source_license="license-id",
                    source_manifest_sha256=digest(f"manifest-{trait_id}"),
                )
            )
            for wording in ("observed", "heldout"):
                variant_id = f"variant-{family}-{trait}-{wording}"
                variants.append(
                    PersonaPromptVariant(
                        variant_id=variant_id,
                        trait_id=trait_id,
                        prompt_version="v1",
                        prompt_sha256=digest(variant_id),
                    )
                )
            for role in PersonaItemRole:
                item_id = f"item-{family}-{trait}-{role.value}"
                items.append(
                    PersonaEvaluationItem(
                        item_id=item_id,
                        trait_id=trait_id,
                        source_item_id=f"source-{item_id}",
                        content_sha256=digest(item_id),
                        role=role,
                    )
                )
    return families, tuple(traits), tuple(variants), tuple(items)


def make_catalog() -> PersonaCatalog:
    return PersonaCatalog(*make_components())


def make_plan(catalog: PersonaCatalog) -> PersonaGeneralizationPlan:
    unseen_traits = tuple(f"trait-{family}-3" for family in range(3))
    unseen_wordings = tuple(
        f"variant-{family}-{trait}-heldout"
        for family in range(3)
        for trait in range(3)
    )
    return PersonaGeneralizationPlan(
        catalog=catalog,
        unseen_family_ids=("family-3",),
        within_family_unseen_trait_ids=unseen_traits,
        unseen_prompt_variant_ids=unseen_wordings,
    )


class PersonaHierarchyTests(unittest.TestCase):
    def test_valid_four_family_sixteen_trait_catalog_and_three_roles(self) -> None:
        catalog = make_catalog()
        self.assertEqual(len(catalog.families), 4)
        self.assertEqual(len(catalog.traits), 16)
        for trait in catalog.traits:
            roles = {
                item.role
                for item in catalog.evaluation_items
                if item.trait_id == trait.trait_id
            }
            self.assertEqual(roles, set(PersonaItemRole))

        plan = make_plan(catalog)
        self.assertIs(
            plan.role_for(
                family_id="family-0",
                trait_id="trait-0-0",
                variant_id="variant-0-0-observed",
            ),
            PersonaGeneralizationRole.SEEN_TRAIT_OBSERVED_WORDING,
        )
        self.assertIs(
            plan.role_for(
                family_id="family-0",
                trait_id="trait-0-0",
                variant_id="variant-0-0-heldout",
            ),
            PersonaGeneralizationRole.UNSEEN_PROMPT_WORDING,
        )
        self.assertIs(
            plan.role_for(
                family_id="family-0",
                trait_id="trait-0-3",
                variant_id="variant-0-3-observed",
            ),
            PersonaGeneralizationRole.WITHIN_FAMILY_UNSEEN_TRAIT,
        )
        self.assertIs(
            plan.role_for(
                family_id="family-3",
                trait_id="trait-3-0",
                variant_id="variant-3-0-observed",
            ),
            PersonaGeneralizationRole.UNSEEN_BEHAVIORAL_FAMILY,
        )

    def test_unknown_trait_references_fail_fast(self) -> None:
        families, traits, variants, items = make_components()
        bad_variant = PersonaPromptVariant(
            variant_id="variant-unknown",
            trait_id="trait-unknown",
            prompt_version="v1",
            prompt_sha256=digest("variant-unknown"),
        )
        with self.assertRaisesRegex(ProtocolValidationError, "unknown trait"):
            PersonaCatalog(families, traits, variants + (bad_variant,), items)

        bad_item = PersonaEvaluationItem(
            item_id="item-unknown",
            trait_id="trait-unknown",
            source_item_id="source-item-unknown",
            content_sha256=digest("item-unknown"),
            role=PersonaItemRole.DEFINITION,
        )
        with self.assertRaisesRegex(ProtocolValidationError, "unknown trait"):
            PersonaCatalog(families, traits, variants, items + (bad_item,))

    def test_item_roles_are_complete_and_source_items_cannot_overlap(self) -> None:
        families, traits, variants, items = make_components()
        missing_role = tuple(
            item
            for item in items
            if not (
                item.trait_id == "trait-0-0"
                and item.role is PersonaItemRole.HELD_OUT_VALIDATION
            )
        )
        with self.assertRaisesRegex(ProtocolValidationError, "all three item roles"):
            PersonaCatalog(families, traits, variants, missing_role)

        duplicate = PersonaEvaluationItem(
            item_id="item-distinct-id",
            trait_id="trait-0-0",
            source_item_id=items[0].source_item_id,
            content_sha256=digest("distinct-content"),
            role=PersonaItemRole.HELD_OUT_VALIDATION,
        )
        with self.assertRaisesRegex(ProtocolValidationError, "source_item_ids contains duplicate"):
            PersonaCatalog(families, traits, variants, items + (duplicate,))

    def test_three_level_holdout_leakage_and_declared_role_mismatch_fail(self) -> None:
        catalog = make_catalog()
        valid = make_plan(catalog)
        with self.assertRaisesRegex(ProtocolValidationError, "exactly one"):
            PersonaGeneralizationPlan(
                catalog=catalog,
                unseen_family_ids=("family-2", "family-3"),
                within_family_unseen_trait_ids=("trait-0-3", "trait-1-3"),
                unseen_prompt_variant_ids=tuple(
                    f"variant-{family}-{trait}-heldout"
                    for family in range(2)
                    for trait in range(3)
                ),
            )
        with self.assertRaisesRegex(ProtocolValidationError, "cannot belong to an unseen family"):
            PersonaGeneralizationPlan(
                catalog=catalog,
                unseen_family_ids=("family-3",),
                within_family_unseen_trait_ids=(
                    "trait-0-3",
                    "trait-1-3",
                    "trait-2-3",
                    "trait-3-0",
                ),
                unseen_prompt_variant_ids=valid.unseen_prompt_variant_ids,
            )
        with self.assertRaisesRegex(ProtocolValidationError, "development traits"):
            PersonaGeneralizationPlan(
                catalog=catalog,
                unseen_family_ids=("family-3",),
                within_family_unseen_trait_ids=valid.within_family_unseen_trait_ids,
                unseen_prompt_variant_ids=valid.unseen_prompt_variant_ids
                + ("variant-0-3-heldout",),
            )
        with self.assertRaisesRegex(ProtocolValidationError, "role mismatch"):
            valid.validate_assignment(
                family_id="family-0",
                trait_id="trait-0-0",
                variant_id="variant-0-0-heldout",
                declared_role=PersonaGeneralizationRole.SEEN_TRAIT_OBSERVED_WORDING,
            )


if __name__ == "__main__":
    unittest.main()
