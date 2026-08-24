import unittest

from persona_drift.protocol import ProtocolValidationError
from persona_drift.splits import (
    TopicAnchor,
    TopicSource,
    TopicSplitPlan,
    validate_anchor_catalog,
    validate_no_root_leakage,
)


def make_catalog():
    anchors = []
    for domain_index in range(12):
        for item_index in range(2):
            topic_id = f"mmlu-{domain_index:02d}-{item_index}"
            anchors.append(
                TopicAnchor(
                    topic_id=topic_id,
                    source=TopicSource.MMLU_PRO,
                    source_item_id=f"public-{topic_id}",
                    source_group=f"domain-{domain_index:02d}",
                    conversion_template_id="mmlu-discussion-v1",
                )
            )
    for group in ("philosophy", "nlp", "politics"):
        for item_index in range(2):
            topic_id = f"syc-{group}-{item_index}"
            anchors.append(
                TopicAnchor(
                    topic_id=topic_id,
                    source=TopicSource.ANTHROPIC_SYCOPHANCY,
                    source_item_id=f"public-{topic_id}",
                    source_group=group,
                    conversion_template_id="sycophancy-discussion-v1",
                )
            )
    return tuple(anchors)


class TopicSplitTests(unittest.TestCase):
    def test_valid_catalog_and_topic_level_split(self) -> None:
        catalog = validate_anchor_catalog(make_catalog())
        ids = tuple(anchor.topic_id for anchor in catalog)
        plan = TopicSplitPlan(
            development=ids[:15],
            calibration=ids[15:20],
            untouched_test=ids[20:30],
            pilot=ids[:6],
        )
        plan.validate_against_catalog(catalog)
        self.assertEqual(plan.partition_for(ids[0]), "development")
        self.assertEqual(len(plan.all_main_topics), 30)

    def test_partitions_must_be_disjoint(self) -> None:
        ids = tuple(anchor.topic_id for anchor in make_catalog())
        with self.assertRaisesRegex(ProtocolValidationError, "overlap"):
            TopicSplitPlan(
                development=ids[:15],
                calibration=(ids[0],) + ids[16:20],
                untouched_test=ids[20:30],
                pilot=ids[:6],
            )

    def test_pilot_is_six_topic_development_subset(self) -> None:
        ids = tuple(anchor.topic_id for anchor in make_catalog())
        with self.assertRaisesRegex(ProtocolValidationError, "subset of development"):
            TopicSplitPlan(
                development=ids[:15],
                calibration=ids[15:20],
                untouched_test=ids[20:30],
                pilot=ids[20:26],
            )

    def test_catalog_requires_exact_public_source_balance(self) -> None:
        catalog = list(make_catalog())
        catalog[-1] = TopicAnchor(
            topic_id="replacement-mmlu",
            source=TopicSource.MMLU_PRO,
            source_item_id="public-replacement",
            source_group="domain-00",
            conversion_template_id="mmlu-discussion-v1",
        )
        with self.assertRaisesRegex(ProtocolValidationError, "topic sources"):
            validate_anchor_catalog(catalog)

    def test_root_groups_cannot_leak_across_partitions(self) -> None:
        validate_no_root_leakage(
            {"development": ("root-a",), "untouched_test": ("root-b",)}
        )
        with self.assertRaisesRegex(ProtocolValidationError, "root-group leakage"):
            validate_no_root_leakage(
                {"development": ("root-a",), "untouched_test": ("root-a",)}
            )


if __name__ == "__main__":
    unittest.main()
