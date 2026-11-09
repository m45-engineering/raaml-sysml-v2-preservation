from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest

from src.raaml_preservation.facts import extract_facts
from src.raaml_preservation.roundtrip import (
    FULL_CORPUS_V2_FILENAME,
    RoundTripError,
    compare_full_corpus,
    create_full_corpus_manifest,
    create_manifest,
    forward_full_corpus,
    render_full_corpus_v2,
    render_v2,
    reverse_full_corpus,
    select_milestone_three_slice,
    synthetic_id,
    verify_full_corpus_manifest,
    verify_manifest,
)
from src.raaml_preservation.schemas import validate_instance_against_schema


ROOT = Path(__file__).resolve().parents[1]


class MilestoneThreeRoundTripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _, canonical = extract_facts(ROOT)
        cls.slice = select_milestone_three_slice(canonical)

    def test_slice_exercises_required_artifacts_and_constructs(self) -> None:
        filenames = {
            artifact["filename"] for artifact in self.slice["artifacts"]
        }
        self.assertEqual(
            filenames,
            {
                "CoreRAAML.xmi",
                "CoreRAAMLLib.xmi",
                "GeneralRAAML.xmi",
                "GeneralRAAMLLib.xmi",
                "STPA.xmi",
                "STPALib.xmi",
            },
        )
        undeveloped = next(
            declaration
            for artifact in self.slice["artifacts"]
            for declaration in artifact["declarations"]
            if declaration["name"] == "Undeveloped"
        )
        self.assertEqual(undeveloped["properties"][0]["name"], "base_Element")
        self.assertEqual(undeveloped["icons"][0]["format"]["value"], "SVG")
        self.assertTrue(undeveloped["icons"][0]["location"]["present"])

    def test_manifest_digest_detects_fact_mutation(self) -> None:
        manifest = create_manifest(self.slice)
        corrupted = copy.deepcopy(manifest)
        corrupted["payload"]["canonicalFacts"]["artifacts"][0]["filename"] = (
            "changed.xmi"
        )
        with self.assertRaisesRegex(RoundTripError, "payloadSha256"):
            verify_manifest(corrupted)

    def test_v2_view_uses_resolved_native_carriers(self) -> None:
        text = render_v2(self.slice)
        self.assertIn("metadata def Undeveloped;", text)
        self.assertIn("occurrence def Loss;", text)
        self.assertIn("connection def Causality {", text)
        self.assertIn("constraint def ControllingMeasure_SupplierIsSituation;", text)

    def test_synthetic_id_matches_normative_example(self) -> None:
        self.assertEqual(
            synthetic_id("STPA", "Controller"),
            "_raaml_91a0d44384d4417f8bb0389b94d928b88f545a34",
        )

    def test_manifest_serialization_is_deterministic(self) -> None:
        first = json.dumps(create_manifest(self.slice), sort_keys=True)
        second = json.dumps(create_manifest(self.slice), sort_keys=True)
        self.assertEqual(first, second)


class MilestoneFourForwardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _, cls.canonical = extract_facts(ROOT)

    def test_full_model_covers_every_declaration_and_constraint(self) -> None:
        text = render_full_corpus_v2(self.canonical)
        self.assertIn("package RaamlFullCorpus {", text)
        self.assertIn("private import ScalarValues::*;", text)
        self.assertIn("metadata def Raaml_BaseAnnotation;", text)
        self.assertIn("occurrence def InSeries :> RBDLib::SystemReliabilitySituation", text)
        self.assertIn("constraint def InSeriesCalculation {", text)
        self.assertIn("UNIMPLEMENTED source expression", text)
        self.assertEqual(
            sum(
                len(artifact["declarations"])
                for artifact in self.canonical["artifacts"]
            ),
            283,
        )
        self.assertEqual(
            sum(
                len(declaration["constraints"])
                for artifact in self.canonical["artifacts"]
                for declaration in artifact["declarations"]
            ),
            60,
        )

    def test_full_manifest_is_scoped_to_one_source(self) -> None:
        v2_bytes = render_full_corpus_v2(self.canonical).encode("utf-8")
        artifact = self.canonical["artifacts"][0]
        manifest = create_full_corpus_manifest(
            self.canonical,
            artifact,
            v2_bytes,
        )
        payload = manifest["payload"]
        self.assertEqual(payload["sourceFilename"], artifact["filename"])
        self.assertEqual(payload["v2Filename"], FULL_CORPUS_V2_FILENAME)
        self.assertEqual(len(payload["canonicalFacts"]["artifacts"]), 1)
        self.assertEqual(
            payload["canonicalFacts"]["artifacts"][0]["artifactId"],
            artifact["artifactId"],
        )
        self.assertTrue(
            all("qualifiedName" in target for target in payload["nativeTargets"])
        )
        validate_instance_against_schema(
            manifest,
            ROOT / "schemas" / "preservation-manifest.schema.json",
        )

    def test_full_forward_is_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="raaml-m4-unit-") as temporary:
            root = Path(temporary)
            first = forward_full_corpus(ROOT, root / "first")
            second = forward_full_corpus(ROOT, root / "second")
            first_files = sorted(
                path.relative_to(root / "first")
                for path in (root / "first").rglob("*")
                if path.is_file()
            )
            second_files = sorted(
                path.relative_to(root / "second")
                for path in (root / "second").rglob("*")
                if path.is_file()
            )
            self.assertEqual(first_files, second_files)
            self.assertEqual(len(first["manifests"]), 17)
            self.assertEqual(len(second["manifests"]), 17)
            self.assertEqual(len(first_files), 18)
            for relative in first_files:
                self.assertEqual(
                    (root / "first" / relative).read_bytes(),
                    (root / "second" / relative).read_bytes(),
                )

    def test_design_fragments_are_explicitly_labeled_pseudocode(self) -> None:
        proposal = (
            ROOT / "proposal" / "normative-encoding-v0.1.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "fragments below are **illustrative pseudocode**",
            proposal,
        )
        self.assertIn(
            "generated `.sysml` files are the parser-tested concrete",
            proposal,
        )


class MilestoneFiveReverseTests(unittest.TestCase):
    def test_full_reverse_is_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="raaml-m5-unit-") as temporary:
            root = Path(temporary)
            forward = forward_full_corpus(ROOT, root / "forward")
            first = reverse_full_corpus(
                root / "forward" / "manifests",
                forward["v2"],
                root / "first",
            )
            second = reverse_full_corpus(
                root / "forward" / "manifests",
                forward["v2"],
                root / "second",
            )

            self.assertEqual(len(first), 17)
            self.assertEqual(len(second), 17)
            self.assertEqual(
                {path.name: path.read_bytes() for path in first},
                {path.name: path.read_bytes() for path in second},
            )

    def test_full_manifest_digest_detects_fact_mutation(self) -> None:
        _, canonical = extract_facts(ROOT)
        v2_bytes = render_full_corpus_v2(canonical).encode("utf-8")
        manifest = create_full_corpus_manifest(
            canonical,
            canonical["artifacts"][0],
            v2_bytes,
        )
        manifest["payload"]["canonicalFacts"]["artifacts"][0][
            "filename"
        ] = "changed.xmi"

        with self.assertRaisesRegex(RoundTripError, "payloadSha256"):
            verify_full_corpus_manifest(manifest)

    def test_injected_hash_collision_stops_before_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="raaml-m5-collision-") as temporary:
            root = Path(temporary)
            forward = forward_full_corpus(ROOT, root / "forward")
            output = root / "reconstructed"

            with self.assertRaisesRegex(RoundTripError, "collision"):
                reverse_full_corpus(
                    root / "forward" / "manifests",
                    forward["v2"],
                    output,
                    hash_provider=lambda value: "0" * 64,
                )

            self.assertFalse(output.exists())


class MilestoneSixComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="raaml-m6-unit-"
        )
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        forward = forward_full_corpus(ROOT, cls.root / "forward")
        cls.reconstructed = cls.root / "reconstructed"
        reverse_full_corpus(
            cls.root / "forward" / "manifests",
            forward["v2"],
            cls.reconstructed,
        )

    def test_full_corpus_canonical_facts_are_equal(self) -> None:
        report = compare_full_corpus(ROOT, self.reconstructed)

        self.assertTrue(report["ok"])
        self.assertEqual(report["summary"]["artifacts"], 17)
        self.assertEqual(report["summary"]["differences"], 0)
        self.assertEqual(
            report["summary"]["sourceFactsSha256"],
            report["summary"]["reconstructedFactsSha256"],
        )
        self.assertEqual(
            report["sourceCounts"],
            report["reconstructedCounts"],
        )
        self.assertTrue(
            all(item["differences"] == 0 for item in report["perArtifact"])
        )
        validate_instance_against_schema(
            report,
            ROOT / "schemas" / "full-corpus-comparison-report.schema.json",
        )

    def test_changed_reconstructed_fact_is_reported(self) -> None:
        changed = self.root / "changed"
        shutil.copytree(self.reconstructed, changed)
        mutation_path = next(
            path
            for path in sorted(changed.glob("*.xmi"))
            if re.search(r'isAbstract="(?:true|false)"', path.read_text())
        )
        original = mutation_path.read_text(encoding="utf-8")
        mutated = re.sub(
            r'isAbstract="(true|false)"',
            lambda match: (
                'isAbstract="false"'
                if match.group(1) == "true"
                else 'isAbstract="true"'
            ),
            original,
            count=1,
        )
        mutation_path.write_text(mutated, encoding="utf-8", newline="\n")

        report = compare_full_corpus(ROOT, changed)

        self.assertFalse(report["ok"])
        self.assertGreater(report["summary"]["differences"], 0)
        self.assertNotEqual(
            report["summary"]["sourceFactsSha256"],
            report["summary"]["reconstructedFactsSha256"],
        )
        self.assertTrue(
            any(item["differences"] > 0 for item in report["perArtifact"])
        )
        validate_instance_against_schema(
            report,
            ROOT / "schemas" / "full-corpus-comparison-report.schema.json",
        )


if __name__ == "__main__":
    unittest.main()
