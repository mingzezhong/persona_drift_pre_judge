import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from persona_drift.g1_manifest import (
    CANONICALIZATION_VERSION,
    ManifestValidationError,
    ReadinessStatus,
    canonical_data_sha256,
    canonical_structured_file_sha256,
    evaluate_g1_readiness,
    file_bytes_sha256,
    find_placeholders,
    load_structured_bytes,
    missing_required_fields,
    require_fields,
    verify_file_sha256,
)


class G1ManifestTests(unittest.TestCase):
    def _write_inventory(
        self,
        directory: Path,
        *,
        implementation_status: str,
        artifact_path: str,
        file_sha256: str,
        canonical_sha256: str,
        format_name: str = "yaml",
        required_fields=None,
        required_record_fields=None,
        readiness_contract=None,
    ) -> Path:
        config = {
            "schema_version": "restart-v2.3-g1",
            "gate_id": "G1",
            "implementation_status": implementation_status,
            "artifact_root": str(directory),
            "readiness_contract": readiness_contract
            or {
                "inventory_scope": "full_g1_freeze",
                "all_freeze_artifacts_declared": True,
                "execution_authorized": True,
                "freeze_attestation_artifact_id": "public-source",
            },
            "required_artifact_ids": ["public-source"],
            "artifacts": [
                {
                    "artifact_id": "public-source",
                    "path": artifact_path,
                    "format": format_name,
                    "file_sha256": file_sha256,
                    "canonicalization_version": CANONICALIZATION_VERSION,
                    "canonical_sha256": canonical_sha256,
                    "required_fields": list(required_fields or []),
                    "required_record_fields": list(required_record_fields or []),
                }
            ],
        }
        path = directory / "g1.yaml"
        path.write_text(
            yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return path

    def test_json_and_yaml_share_one_canonical_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = {
                "schema_version": "restart-v2.3",
                "unicode": "人格",
                "nested": {"enabled": True, "items": [3, 2, 1]},
            }
            json_path = root / "manifest.json"
            yaml_path = root / "manifest.yaml"
            json_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            yaml_path.write_text(
                yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            expected = canonical_data_sha256(payload)
            self.assertEqual(canonical_structured_file_sha256(json_path), expected)
            self.assertEqual(canonical_structured_file_sha256(yaml_path), expected)
            self.assertNotEqual(file_bytes_sha256(json_path), file_bytes_sha256(yaml_path))

    def test_duplicate_keys_and_nonfinite_numbers_fail_closed(self) -> None:
        with self.assertRaisesRegex(ManifestValidationError, "duplicate JSON"):
            load_structured_bytes(b'{"key": 1, "key": 2}', format_name="json")
        with self.assertRaisesRegex(ManifestValidationError, "duplicate YAML"):
            load_structured_bytes(b"key: 1\nkey: 2\n", format_name="yaml")
        with self.assertRaisesRegex(ManifestValidationError, "non-finite"):
            load_structured_bytes(b'{"value": NaN}', format_name="json")

    def test_exact_file_bytes_are_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.bin"
            path.write_bytes(b"immutable-public-source-bytes\n")
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(verify_file_sha256(path, expected), expected)
            wrong = hashlib.sha256(b"different bytes").hexdigest()
            with self.assertRaisesRegex(ManifestValidationError, "mismatch"):
                verify_file_sha256(path, wrong)
            with self.assertRaisesRegex(ManifestValidationError, "placeholder hash"):
                verify_file_sha256(path, "a" * 64)

    def test_required_fields_and_nested_placeholders_are_strict(self) -> None:
        payload = {
            "source": {"revision": "open_must_freeze_before_G1_pass"},
            "license": "verified-license",
            "hash": "b" * 64,
            "template": "${SOURCE_ID}",
        }
        self.assertEqual(
            missing_required_fields(payload, ("source.revision", "source.url")),
            ("source.url",),
        )
        with self.assertRaisesRegex(ManifestValidationError, "source.url"):
            require_fields(
                payload,
                ("source.revision", "source.url"),
                context="source manifest",
            )
        findings = find_placeholders(payload)
        self.assertEqual(
            {item.path for item in findings},
            {"$.source.revision", "$.hash", "$.template"},
        )

    def test_missing_config_is_preparation_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = evaluate_g1_readiness(Path(temporary) / "missing.yaml")
        self.assertIs(report.status, ReadinessStatus.PREPARATION)
        self.assertFalse(report.ready)
        self.assertEqual(report.failed_checks[0].code, "CONFIG_MISSING")

    def test_missing_asset_respects_preparation_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_but_unavailable_hash = hashlib.sha256(b"not downloaded").hexdigest()
            config = self._write_inventory(
                root,
                implementation_status="preparation",
                artifact_path="missing.yaml",
                file_sha256=real_but_unavailable_hash,
                canonical_sha256=hashlib.sha256(b"not canonicalized").hexdigest(),
                required_fields=("schema_version",),
            )
            report = evaluate_g1_readiness(config)
        self.assertIs(report.status, ReadinessStatus.PREPARATION)
        self.assertFalse(report.ready)
        self.assertIn("ARTIFACT_MISSING", {check.code for check in report.failed_checks})

    def test_readiness_request_with_missing_asset_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self._write_inventory(
                root,
                implementation_status="ready_for_validation",
                artifact_path="missing.yaml",
                file_sha256=hashlib.sha256(b"missing").hexdigest(),
                canonical_sha256=hashlib.sha256(b"missing canonical").hexdigest(),
                required_fields=("schema_version",),
            )
            report = evaluate_g1_readiness(config)
        self.assertIs(report.status, ReadinessStatus.NOT_READY)
        self.assertFalse(report.ready)

    def test_complete_hashed_inventory_can_be_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset = root / "source.yaml"
            payload = {
                "schema_version": "restart-v2.3",
                "source_id": "official-public-source",
                "revision": "commit-84fcc677",
                "selection_outcome_blind": True,
                "items": ["item-001", "item-002"],
            }
            asset.write_text(
                yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            config = self._write_inventory(
                root,
                implementation_status="ready_for_validation",
                artifact_path=asset.name,
                file_sha256=file_bytes_sha256(asset),
                canonical_sha256=canonical_data_sha256(payload),
                required_fields=(
                    "schema_version",
                    "source_id",
                    "revision",
                    "selection_outcome_blind",
                    "items",
                ),
            )
            config_payload = yaml.safe_load(config.read_text(encoding="utf-8"))
            spec = config_payload["artifacts"][0]
            spec["expected_values"] = {"selection_outcome_blind": True}
            spec["expected_lengths"] = {"items": 2}
            config.write_text(
                yaml.safe_dump(config_payload, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            report = evaluate_g1_readiness(config)
            self.assertIs(report.status, ReadinessStatus.READY)
            self.assertTrue(report.ready)
            self.assertFalse(report.failed_checks)

            asset.write_text(
                asset.read_text(encoding="utf-8") + "tampered: true\n",
                encoding="utf-8",
            )
            tampered = evaluate_g1_readiness(config)
            self.assertIs(tampered.status, ReadinessStatus.NOT_READY)
            self.assertIn(
                "FILE_SHA256_MISMATCH",
                {check.code for check in tampered.failed_checks},
            )

    def test_phase1_inventory_cannot_become_ready_by_flipping_status_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset = root / "source.yaml"
            payload = {
                "schema_version": "restart-v2.3",
                "source_id": "official-public-source",
            }
            asset.write_text(
                yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            config = self._write_inventory(
                root,
                implementation_status="preparation",
                artifact_path=asset.name,
                file_sha256=file_bytes_sha256(asset),
                canonical_sha256=canonical_data_sha256(payload),
                required_fields=("schema_version", "source_id"),
                readiness_contract={
                    "inventory_scope": "phase1_only",
                    "all_freeze_artifacts_declared": False,
                    "execution_authorized": False,
                    "freeze_attestation_artifact_id": "g1-freeze-attestation",
                },
            )
            config_payload = yaml.safe_load(config.read_text(encoding="utf-8"))
            config_payload["planned_g1_freeze_artifacts"] = [
                {
                    "artifact_id": "g1-freeze-attestation",
                    "construction_status": "required_after_all_g1_contracts_validate",
                }
            ]
            config.write_text(
                yaml.safe_dump(config_payload, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            preparation = evaluate_g1_readiness(config)
            self.assertIs(preparation.status, ReadinessStatus.PREPARATION)

            config_payload["implementation_status"] = "ready_for_validation"
            config.write_text(
                yaml.safe_dump(config_payload, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            forged = evaluate_g1_readiness(config)
        self.assertIs(forged.status, ReadinessStatus.NOT_READY)
        self.assertFalse(forged.ready)
        self.assertIn(
            "READINESS_CONTRACT_INCOMPLETE",
            {check.code for check in forged.failed_checks},
        )

    def test_placeholder_inside_hashed_artifact_prevents_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset = root / "source.json"
            payload = {
                "schema_version": "restart-v2.3",
                "source_id": "official-public-source",
                "revision": "TBD",
            }
            asset.write_text(json.dumps(payload), encoding="utf-8")
            config = self._write_inventory(
                root,
                implementation_status="ready_for_validation",
                artifact_path=asset.name,
                format_name="json",
                file_sha256=file_bytes_sha256(asset),
                canonical_sha256=canonical_data_sha256(payload),
                required_fields=("schema_version", "source_id", "revision"),
            )
            report = evaluate_g1_readiness(config)
        self.assertIs(report.status, ReadinessStatus.NOT_READY)
        self.assertIn(
            "ARTIFACT_CONTENT_INCOMPLETE",
            {check.code for check in report.failed_checks},
        )

    def test_jsonl_record_fields_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset = root / "reviews.jsonl"
            records = [
                {"candidate_id": "candidate-1", "decision": "eligible"},
                {"candidate_id": "candidate-2"},
            ]
            asset.write_text(
                "\n".join(json.dumps(item) for item in records) + "\n",
                encoding="utf-8",
            )
            config = self._write_inventory(
                root,
                implementation_status="ready_for_validation",
                artifact_path=asset.name,
                format_name="jsonl",
                file_sha256=file_bytes_sha256(asset),
                canonical_sha256=canonical_data_sha256(records),
                required_record_fields=("candidate_id", "decision"),
            )
            report = evaluate_g1_readiness(config)
        self.assertIs(report.status, ReadinessStatus.NOT_READY)
        self.assertIn(
            "ARTIFACT_CONTENT_INCOMPLETE",
            {check.code for check in report.failed_checks},
        )

    def test_empty_inventory_can_never_be_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "g1.yaml"
            config.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": "restart-v2.3-g1",
                        "gate_id": "G1",
                        "implementation_status": "ready_for_validation",
                        "required_artifact_ids": [],
                        "artifacts": [],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            report = evaluate_g1_readiness(config)
        self.assertIs(report.status, ReadinessStatus.NOT_READY)
        self.assertIn("CONFIG_INVALID", {check.code for check in report.failed_checks})


if __name__ == "__main__":
    unittest.main()
