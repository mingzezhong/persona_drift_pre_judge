import ast
import pathlib
import re
import tomllib
import unittest
from collections.abc import Iterator
from typing import Any

import yaml


ROOT = pathlib.Path(__file__).parents[1]

DEDICATED_FLOW_DISTRIBUTIONS = {
    "flow-matching",
    "flowmatching",
    "freia",
    "glasflow",
    "nflows",
    "normflows",
    "torch-cfm",
    "torchcfm",
    "zuko",
}

DEDICATED_FLOW_IMPORT_ROOTS = {
    "flow_matching",
    "flowmatching",
    "freia",
    "glasflow",
    "nflows",
    "normflows",
    "torch_cfm",
    "torchcfm",
    "zuko",
}

EXCLUDED_IDENTIFIER_FRAGMENTS = {
    "conditionalflow",
    "conditionalmaf",
    "conditionalnvp",
    "continuousnormalizingflow",
    "flowbaseddensity",
    "flowbasedtrajectory",
    "flowmatcher",
    "flowmatching",
    "maskedautoregressiveflow",
    "neuralsplineflow",
    "normalizingflow",
    "realnvp",
}

EXCLUDED_EXACT_IDENTIFIERS = {"cnf", "maf", "nvp"}


def _canonical(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _pep503_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value.lower())


def _requirement_name(requirement: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", requirement)
    if match is None:
        raise AssertionError(f"cannot parse dependency requirement: {requirement!r}")
    return _pep503_name(match.group(1))


def _looks_like_excluded_method(value: str) -> bool:
    canonical = _canonical(value)
    if canonical in EXCLUDED_EXACT_IDENTIFIERS:
        return True
    if canonical.startswith("cnf") or canonical.endswith("cnf"):
        return True
    return any(fragment in canonical for fragment in EXCLUDED_IDENTIFIER_FRAGMENTS)


def _walk_config_strings(value: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            yield (".".join((*path, "<key>")), key_text)
            yield from _walk_config_strings(child, (*path, key_text))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_config_strings(child, (*path, str(index)))
    elif isinstance(value, str):
        yield (".".join(path), value)


class MethodScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config_path = ROOT / "configs" / "restart_v2.yaml"
        cls.payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    def test_machine_contract_excludes_conditional_flow_project_wide(self) -> None:
        self.assertEqual(self.payload["schema_version"], "restart-v2.2")
        self.assertEqual(self.payload["protocol_revision"], "2.2-preparation")

        exclusion = self.payload["scope_exclusions"]["conditional_flow_family"]
        self.assertEqual(exclusion["decision"], "excluded_from_project")
        self.assertEqual(
            exclusion["scope"],
            "all_project_phases_analyses_artifacts_and_reports",
        )
        self.assertTrue(
            {"pilot", "main", "intervention", "external_evaluation"}
            <= set(exclusion["applies_to"])
        )
        self.assertTrue(
            {
                "conditional_flow",
                "conditional_normalizing_flow",
                "cnf",
                "normalizing_flow",
                "continuous_normalizing_flow",
                "flow_matching",
                "conditional_maf",
                "conditional_realnvp",
                "conditional_neural_spline_flow",
                "masked_autoregressive_flow",
                "realnvp",
                "neural_spline_flow",
                "flow_based_density_model",
                "flow_based_trajectory_model",
            }
            <= set(exclusion["aliases"])
        )
        self.assertTrue(
            {
                "primary_method",
                "baseline",
                "comparator",
                "ablation",
                "exploratory_extension",
                "confirmatory_extension",
            }
            <= set(exclusion["prohibited_roles"])
        )
        self.assertTrue(exclusion["source_mentions_are_non_operational_provenance"])
        self.assertEqual(
            exclusion["reintroduction_policy"],
            "explicit_user_scope_change_and_new_major_protocol_required",
        )

    def test_active_config_cannot_reintroduce_excluded_methods(self) -> None:
        active_payload = {
            key: value
            for key, value in self.payload.items()
            if key not in {"scope_exclusions", "authoritative_documents"}
        }
        violations = [
            f"{path}={value}"
            for path, value in _walk_config_strings(active_payload)
            if _looks_like_excluded_method(value)
        ]
        self.assertEqual(violations, [])

    def test_operational_documents_record_the_exclusion(self) -> None:
        paths = (
            ROOT / "README.md",
            ROOT / "docs" / "restart_v2_amendment.md",
            ROOT / "docs" / "research_protocol_v2.md",
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Conditional Flow", text, path)
            self.assertIn("flow-based density/trajectory models", text, path)
            self.assertRegex(text, r"不采用|不考虑|排除", path)

    def test_no_dedicated_flow_dependency_is_declared(self) -> None:
        with (ROOT / "pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle)["project"]
        declared = list(project.get("dependencies", []))
        for extra in project.get("optional-dependencies", {}).values():
            declared.extend(extra)
        package_names = {_requirement_name(requirement) for requirement in declared}
        self.assertTrue(DEDICATED_FLOW_DISTRIBUTIONS.isdisjoint(package_names))

    def test_excluded_identifier_detector_has_positive_and_negative_controls(self) -> None:
        for identifier in (
            "ConditionalFlowModel",
            "build_conditional_flow",
            "FlowMatcher",
            "build_flow_matching_model",
            "ConditionalMAF",
            "CNFConfig",
            "RealNVP",
            "NeuralSplineFlow",
            "MaskedAutoregressiveFlow",
        ):
            self.assertTrue(_looks_like_excluded_method(identifier), identifier)
        for identifier in (
            "underflow",
            "overflow",
            "workflow",
            "PressureSchedule",
            "ForkDosePlan",
        ):
            self.assertFalse(_looks_like_excluded_method(identifier), identifier)

    def test_no_flow_implementation_enters_production_source(self) -> None:
        violations = []
        for path in sorted((ROOT / "src" / "persona_drift").glob("**/*.py")):
            if _looks_like_excluded_method(path.stem):
                violations.append(f"excluded module: {path.relative_to(ROOT)}")
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    if _looks_like_excluded_method(node.name):
                        violations.append(
                            f"excluded symbol: {path.relative_to(ROOT)}::{node.name}"
                        )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".", 1)[0].lower()
                        if (
                            root in DEDICATED_FLOW_IMPORT_ROOTS
                            or _looks_like_excluded_method(alias.name)
                        ):
                            violations.append(
                                f"excluded import: {path.relative_to(ROOT)}::{alias.name}"
                            )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".", 1)[0].lower()
                    if (
                        root in DEDICATED_FLOW_IMPORT_ROOTS
                        or _looks_like_excluded_method(node.module)
                    ):
                        violations.append(
                            f"excluded import: {path.relative_to(ROOT)}::{node.module}"
                        )
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
