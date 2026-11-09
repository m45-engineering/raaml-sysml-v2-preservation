from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from raaml_preservation.adapters import run_adapter, tool_paths
from raaml_preservation.facts import extract_facts
from raaml_preservation.roundtrip import render_full_corpus_v2
from raaml_preservation.v2 import validate_native_structure


ROOT = Path(__file__).resolve().parents[1]


class NativePackageTests(unittest.TestCase):
    """Inspect actual generated packages through the pinned SysML validator."""

    @classmethod
    def setUpClass(cls) -> None:
        if not tool_paths(ROOT)["java"].is_file():
            raise unittest.SkipTest("pinned validator is not installed")
        cls.raw, cls.canonical = extract_facts(ROOT)
        cls.text = render_full_corpus_v2(cls.canonical)
        cls.temporary = tempfile.TemporaryDirectory(prefix="raaml-native-packages-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.path = Path(cls.temporary.name) / "packages.sysml"
        cls.path.write_text(cls.text)
        cls.report = run_adapter(ROOT, "v2", cls.path)
        cls.structure = cls.report["nativeStructure"]

    def test_complete_generated_packages_have_no_validator_errors(self) -> None:
        self.assertTrue(self.report["ok"], self.report["errorCategories"])
        self.assertTrue(
            all(count == 0 for count in self.report["errorCategories"].values())
        )

    def test_resolved_structure_matches_source_obligations(self) -> None:
        self.assertEqual(validate_native_structure(self.canonical, self.structure), [])

    def test_rbd_types_properties_and_inheritance_resolve(self) -> None:
        series = self.structure["RaamlFullCorpus::RBDLib::InSeries"]
        self.assertTrue(series["abstract"])
        self.assertIn(
            "RaamlFullCorpus::RBDLib::SystemReliabilitySituation", series["supertypes"]
        )
        calculation = self.structure["RaamlFullCorpus::RBDLib::InSeriesCalculation"]
        self.assertEqual(calculation["kind"], "ConstraintDefinition")
        prop = self.structure["RaamlFullCorpus::RBDLib::InSeries::rc"]
        self.assertEqual(prop["kind"], "ConstraintUsage")
        self.assertEqual(
            prop["types"], ["RaamlFullCorpus::RBDLib::InSeriesCalculation"]
        )
        for parameter in ("input", "output"):
            actual = self.structure[
                f"RaamlFullCorpus::RBDLib::InSeriesCalculation::{parameter}"
            ]
            self.assertEqual(actual["kind"], "AttributeUsage")
            self.assertEqual(actual["types"], ["ScalarValues::Real"])
        self.assertIn(
            "RaamlFullCorpus::RBD::SystemReliability",
            self.structure["RaamlFullCorpus::RBD::InSeries"]["supertypes"],
        )

    def test_every_named_source_feature_is_present_in_resolved_model(self) -> None:
        checked = 0
        for artifact in self.canonical["artifacts"]:
            package = Path(artifact["filename"]).stem
            for declaration in artifact["declarations"]:
                if declaration["name"] is None:
                    continue
                path = f"RaamlFullCorpus::{package}::{declaration['name']}"
                self.assertEqual(
                    self.structure[path]["abstract"],
                    declaration["kind"] == "Enumeration"
                    or declaration["isAbstract"]["value"],
                    path,
                )
                for prop in declaration["properties"]:
                    if prop["isBase"] or prop["name"] is None:
                        continue
                    self.assertIn(f"{path}::{prop['name']}", self.structure)
                    checked += 1
        self.assertGreater(checked, 150)

    def test_source_selectors_and_nested_paths_survive_extraction(self) -> None:
        declarations = [
            d for a in self.canonical["artifacts"] for d in a["declarations"]
        ]
        self.assertEqual(
            sum(d["sysmlKind"] == "ConstraintBlock" for d in declarations), 36
        )
        self.assertEqual(sum(d["sysmlKind"] == "Block" for d in declarations), 8)
        for artifact in self.canonical["artifacts"]:
            for declaration in artifact["declarations"]:
                if declaration["name"] and declaration["sysmlKind"]:
                    name = f"RaamlFullCorpus::{Path(artifact['filename']).stem}::{declaration['name']}"
                    expected = (
                        "ConstraintDefinition"
                        if declaration["sysmlKind"] == "ConstraintBlock"
                        else (
                            "ConnectionDefinition"
                            if declaration["kind"] == "AssociationClass"
                            else "PartDefinition"
                        )
                    )
                    self.assertEqual(self.structure[name]["kind"], expected, name)
        connectors = [c for d in declarations for c in d["connectors"]]
        self.assertEqual(sum(c["isBinding"] for c in connectors), 90)
        self.assertEqual(
            sum(bool(e["propertyPath"]) for c in connectors for e in c["ends"]), 125
        )

    def test_source_exceptions_are_visible_not_fake_executable_constraints(
        self,
    ) -> None:
        self.assertEqual(self.text.count("UNIMPLEMENTED source expression"), 60)
        self.assertEqual(self.text.count("UNMAPPED source connector"), 4)
        self.assertEqual(
            self.text.count("V1 ConstraintBlock port mapped to a value parameter"), 65
        )
        self.assertIn("attribute 'input' : ScalarValues::Real[0..*];", self.text)
        self.assertNotIn("assert constraint", self.text)

    def test_old_facts_require_reextraction(self) -> None:
        with self.assertRaisesRegex(ValueError, "re-extract"):
            render_full_corpus_v2({**self.canonical, "schemaVersion": "0.1.0"})

    def test_valid_syntax_does_not_hide_removed_inheritance(self) -> None:
        original = "metadata def InSeries :> RBD::SystemReliability {"
        self.assertIn(original, self.text)
        mutated = self.text.replace(original, "metadata def InSeries {", 1)
        path = Path(self.temporary.name) / "removed-inheritance.sysml"
        path.write_text(mutated)
        report = run_adapter(ROOT, "v2", path)
        self.assertTrue(report["ok"], report["errorCategories"])
        self.assertNotIn(
            "RaamlFullCorpus::RBD::SystemReliability",
            report["nativeStructure"]["RaamlFullCorpus::RBD::InSeries"]["supertypes"],
        )
        self.assertIn(
            "Missing generalization: RaamlFullCorpus::RBD::InSeries -> RaamlFullCorpus::RBD::SystemReliability",
            validate_native_structure(self.canonical, report["nativeStructure"]),
        )
