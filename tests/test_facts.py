from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from raaml_preservation.cli import _write_json_atomic
from raaml_preservation.facts import (
    FactExtractionError,
    canonicalize_facts,
    count_facts,
    extract_artifact_set,
    extract_facts,
    serialize_facts,
)
from raaml_preservation.oracle import EXPECTED_TOTALS, audit_corpus, load_baseline
from raaml_preservation.ocl_validation import _validate_ast_references
from raaml_preservation.schemas import (
    SchemaValidationError,
    validate_instance_against_schema,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CORPUS_AVAILABLE = len(
    list((REPOSITORY_ROOT / "sources" / "cache").glob("*RAAML*.xmi"))
) >= 4


@unittest.skipUnless(CORPUS_AVAILABLE, "locked RAAML corpus is not in the local cache")
class FactExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw, cls.canonical = extract_facts(REPOSITORY_ROOT)

    def test_raw_and_canonical_outputs_are_schema_valid(self) -> None:
        validate_instance_against_schema(
            self.raw,
            REPOSITORY_ROOT / "schemas" / "raw-raaml-facts.schema.json",
        )
        validate_instance_against_schema(
            self.canonical,
            REPOSITORY_ROOT / "schemas" / "canonical-raaml-facts.schema.json",
        )

    def test_two_extractions_are_byte_identical(self) -> None:
        raw_again, canonical_again = extract_facts(REPOSITORY_ROOT)
        self.assertEqual(serialize_facts(self.raw), serialize_facts(raw_again))
        self.assertEqual(
            serialize_facts(self.canonical),
            serialize_facts(canonical_again),
        )

    def test_production_counts_match_the_frozen_corpus_baseline(self) -> None:
        self.assertEqual(count_facts(self.canonical), EXPECTED_TOTALS)

    def test_anonymous_associations_have_distinct_non_xmi_identities(self) -> None:
        associations = [
            declaration
            for artifact in self.canonical["artifacts"]
            for declaration in artifact["declarations"]
            if declaration["kind"] == "Association"
        ]
        self.assertEqual(len(associations), 40)
        self.assertEqual(len({item["id"] for item in associations}), 40)
        self.assertTrue(
            all("_18_5_" not in item["id"] for item in associations)
        )

    def test_duplicate_constraint_names_remain_owner_qualified(self) -> None:
        constraints = [
            (declaration["name"], constraint)
            for artifact in self.canonical["artifacts"]
            if artifact["filename"] == "CoreRAAML.xmi"
            for declaration in artifact["declarations"]
            for constraint in declaration["constraints"]
            if constraint["name"] == "ClientIsSituation"
        ]
        self.assertEqual(
            sorted(owner for owner, _constraint in constraints),
            ["RelevantTo", "Violates"],
        )
        self.assertEqual(len({item["id"] for _owner, item in constraints}), 2)

    def test_canonical_output_contains_no_source_handle_fields(self) -> None:
        serialized = serialize_facts(self.canonical)
        self.assertNotIn(b'"sourceHandle"', serialized)
        self.assertNotIn(b'"sourceValue"', serialized)

    def test_unresolved_local_reference_fails(self) -> None:
        changed = copy.deepcopy(self.raw)
        reference = next(
            declaration["generalizations"][0]
            for artifact in changed["artifacts"]
            for declaration in artifact["declarations"]
            if declaration["generalizations"]
            and declaration["generalizations"][0]["form"] != "href"
        )
        reference["sourceValue"] = "_missing_target"
        with self.assertRaisesRegex(
            FactExtractionError,
            "cannot resolve local target",
        ):
            canonicalize_facts(changed)

    def test_unsupported_owned_attribute_kind_fails_at_extraction(self) -> None:
        source = REPOSITORY_ROOT / "sources" / "cache" / "CoreRAAML.xmi"
        changed = source.read_text(encoding="utf-8").replace(
            'xmi:type="uml:Property"',
            'xmi:type="uml:Operation"',
            1,
        )
        descriptor = next(
            artifact
            for artifact in self.canonical["artifacts"]
            if artifact["filename"] == source.name
        )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / source.name).write_text(changed, encoding="utf-8")
            with self.assertRaisesRegex(
                FactExtractionError,
                "unsupported property type 'uml:Operation'",
            ):
                extract_artifact_set(
                    REPOSITORY_ROOT,
                    [
                        {
                            "id": descriptor["artifactId"],
                            "filename": source.name,
                            "sha256": descriptor["sha256"],
                        }
                    ],
                    directory,
                )

    def test_removing_top_level_category_fails_schema_validation(self) -> None:
        changed = copy.deepcopy(self.canonical)
        del changed["artifacts"][0]["declarations"]
        with self.assertRaisesRegex(
            SchemaValidationError,
            "missing required field declarations",
        ):
            validate_instance_against_schema(
                changed,
                REPOSITORY_ROOT
                / "schemas"
                / "canonical-raaml-facts.schema.json",
            )

    def test_removing_each_counted_category_is_detected(self) -> None:
        for category, expected in EXPECTED_TOTALS.items():
            with self.subTest(category=category):
                changed = copy.deepcopy(self.canonical)
                self.assertTrue(
                    _remove_one_category_fact(changed, category),
                    f"test does not know how to remove {category}",
                )
                self.assertEqual(count_facts(changed)[category], expected - 1)
                self.assertNotEqual(count_facts(changed), EXPECTED_TOTALS)

    def test_independent_oracle_matches_production_counts(self) -> None:
        report = audit_corpus(REPOSITORY_ROOT)
        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(report["counts"], count_facts(self.canonical))

    def test_selected_relationships_match_golden_facts(self) -> None:
        golden = load_baseline()["goldenFacts"]
        artifacts = {
            artifact["filename"]: artifact
            for artifact in self.canonical["artifacts"]
        }

        core = artifacts["CoreRAAML.xmi"]
        core_profile = core["packages"][0]
        self.assertEqual(core_profile["name"], golden["coreProfile"]["name"])
        self.assertEqual(
            core_profile["uri"]["value"],
            golden["coreProfile"]["uri"],
        )
        self.assertEqual(
            core["namespaces"][0]["prefix"],
            golden["coreProfile"]["namespacePrefix"],
        )

        situation = next(
            item for item in core["declarations"] if item["name"] == "Situation"
        )
        base = next(
            item
            for item in situation["properties"]
            if item["name"] == golden["coreSituation"]["baseProperty"]
        )
        self.assertEqual(base["type"]["target"], golden["coreSituation"]["baseType"])
        self.assertEqual(
            situation["generalizations"][0]["target"],
            golden["coreSituation"]["general"],
        )
        self.assertEqual(
            situation["extensions"][0]["ownedEnds"][0]["name"],
            golden["coreSituation"]["extensionEnd"],
        )

        nested = golden["nestedPackage"]
        nested_declaration = next(
            item
            for item in artifacts[nested["artifact"]]["declarations"]
            if item["name"] == nested["declaration"]
        )
        self.assertEqual(nested_declaration["packagePath"], nested["packagePath"])

        ordered = golden["orderedEnumeration"]
        enumeration = next(
            item
            for item in artifacts[ordered["artifact"]]["declarations"]
            if item["kind"] == "Enumeration" and item["name"] == ordered["name"]
        )
        self.assertEqual(
            [item["name"] for item in enumeration["literals"]],
            ordered["literals"],
        )

        risk = next(
            item
            for item in artifacts["STPALib.xmi"]["declarations"]
            if item["name"] == "RiskRealization"
        )
        expected_risk = golden["riskRealization"]
        self.assertEqual(
            sorted(item["target"].rsplit("::", 1)[-1] for item in risk["generalizations"]),
            sorted(expected_risk["generalNames"]),
        )
        self.assertEqual(
            [item["target"].rsplit("::", 1)[-1] for item in risk["memberEnds"]],
            expected_risk["memberEndNames"],
        )
        self.assertEqual(
            {
                item["name"]: len(item["redefinedProperties"])
                for item in risk["ownedEnds"]
            },
            expected_risk["ownedEndRedefinitionCounts"],
        )

        external = golden["externalSupportType"]
        owner = next(
            item
            for item in artifacts[external["artifact"]]["declarations"]
            if item["name"] == external["owner"]
        )
        property_record = next(
            item
            for item in owner["properties"]
            if item["name"] == external["property"]
        )
        self.assertEqual(property_record["type"]["target"], external["target"])
        self.assertEqual(
            _representative_projection(self.canonical),
            golden["representativeRecords"],
        )

    def test_representative_record_mutations_change_the_golden_projection(
        self,
    ) -> None:
        expected = load_baseline()["goldenFacts"]["representativeRecords"]
        mutations = (
            _mutate_port,
            _mutate_connector_order,
            _mutate_icon,
            _mutate_comment,
            _mutate_machinery,
            _mutate_application,
            _mutate_association_order,
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate.__name__):
                changed = copy.deepcopy(self.canonical)
                mutate(changed)
                self.assertNotEqual(
                    _representative_projection(changed),
                    expected,
                )

    def test_oracle_does_not_import_the_production_extractor(self) -> None:
        source = (
            REPOSITORY_ROOT
            / "src"
            / "raaml_preservation"
            / "oracle.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertNotIn("facts", imported)
        self.assertNotIn("raaml_preservation.facts", imported)


class OclReferenceValidationTests(unittest.TestCase):
    def test_unresolved_and_ambiguous_ast_names_fail_explicitly(self) -> None:
        results = [
            {
                "key": "constraint-1",
                "diagnostics": [],
                "referencedTypes": ["MissingType", "DuplicateType"],
                "referencedProperties": ["missingProperty"],
                "referencedOperations": ["unknownOperation"],
                "referencedIterators": ["unknownIterator"],
            }
        ]
        diagnostics = _validate_ast_references(
            results,
            visible_type_candidates={
                "constraint-1": {
                    "DuplicateType": [
                        "artifact-a::DuplicateType",
                        "artifact-b::DuplicateType",
                    ],
                },
            },
            visible_property_names={
                "constraint-1": {"knownProperty"},
            },
        )
        self.assertEqual(
            {item["code"] for item in diagnostics},
            {
                "OCL_TYPE_UNRESOLVED",
                "OCL_TYPE_AMBIGUOUS",
                "OCL_PROPERTY_UNRESOLVED",
                "OCL_OPERATION_UNRESOLVED",
                "OCL_ITERATOR_UNRESOLVED",
            },
        )

    def test_adapter_parse_diagnostics_are_preserved_with_constraint_key(self) -> None:
        diagnostics = _validate_ast_references(
            [
                {
                    "key": "constraint-2",
                    "diagnostics": [
                        {
                            "severity": "error",
                            "code": "OCL_PARSE",
                            "message": "invalid expression",
                        }
                    ],
                    "referencedTypes": [],
                    "referencedProperties": [],
                    "referencedOperations": [],
                    "referencedIterators": [],
                }
            ],
            visible_type_candidates={"constraint-2": {}},
            visible_property_names={"constraint-2": set()},
        )
        self.assertEqual(diagnostics[0]["code"], "OCL_PARSE")
        self.assertEqual(
            diagnostics[0]["message"],
            "constraint-2: invalid expression",
        )


class ReportFileTests(unittest.TestCase):
    def test_atomic_json_reports_are_world_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            _write_json_atomic(path, {"ok": True})
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o644)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"ok": True},
            )


def _artifact(canonical: dict[str, object], filename: str) -> dict[str, object]:
    return next(
        artifact
        for artifact in canonical["artifacts"]
        if artifact["filename"] == filename
    )


def _declaration(
    canonical: dict[str, object],
    filename: str,
    name: str,
) -> dict[str, object]:
    return next(
        declaration
        for declaration in _artifact(canonical, filename)["declarations"]
        if declaration["name"] == name
    )


def _representative_projection(
    canonical: dict[str, object],
) -> dict[str, object]:
    rpn = _declaration(canonical, "FMEALib.xmi", "RPNCalculation")
    port = next(item for item in rpn["properties"] if item["name"] == "DET")
    fmea_item = _declaration(canonical, "FMEALib.xmi", "FMEAItem")
    connector = _detection_connector(fmea_item)
    undeveloped = _declaration(canonical, "GeneralRAAML.xmi", "Undeveloped")
    icon = undeveloped["icons"][0]
    situation = _declaration(canonical, "CoreRAAML.xmi", "Situation")
    comment = situation["comments"][0]
    core = _artifact(canonical, "CoreRAAML.xmi")
    application = _artifact(canonical, "FMEALib.xmi")["applications"][0]
    association = next(
        item
        for item in _artifact(canonical, "CoreRAAMLLib.xmi")["declarations"]
        if item["kind"] == "Association" and item["name"] == "Causality"
    )
    return {
        "port": {
            "artifact": "FMEALib.xmi",
            "owner": "RPNCalculation",
            "name": port["name"],
            "type": port["type"]["target"],
        },
        "connector": {
            "artifact": "FMEALib.xmi",
            "owner": "FMEAItem",
            "roleTargets": [end["role"]["target"] for end in connector["ends"]],
            "partWithPortTargets": [
                (
                    end["partWithPort"]["target"]
                    if end["partWithPort"] is not None
                    else None
                )
                for end in connector["ends"]
            ],
        },
        "icon": {
            "artifact": "GeneralRAAML.xmi",
            "owner": "Undeveloped",
            "format": icon["format"]["value"],
            "locationSha256": hashlib.sha256(
                icon["location"]["value"].encode("utf-8")
            ).hexdigest(),
            "contentSha256": hashlib.sha256(
                icon["content"].encode("utf-8")
            ).hexdigest(),
        },
        "comment": {
            "artifact": "CoreRAAML.xmi",
            "owner": "Situation",
            "bodySha256": hashlib.sha256(
                comment["body"].encode("utf-8")
            ).hexdigest(),
            "annotatedElement": comment["annotatedElements"][0]["target"],
        },
        "machinery": {
            "artifact": "CoreRAAML.xmi",
            "kinds": [item["kind"] for item in core["machinery"]],
            "targets": [
                item["targets"][0]["target"]
                for item in core["machinery"]
            ],
        },
        "application": {
            "artifact": "FMEALib.xmi",
            "stereotypeName": application["stereotypeName"],
            "stereotypeNamespace": application["stereotypeNamespace"],
            "targetProperty": application["targetProperty"],
            "target": application["target"]["target"],
        },
        "ordinaryAssociation": {
            "artifact": "CoreRAAMLLib.xmi",
            "name": association["name"],
            "memberEndTargets": [
                item["target"]
                for item in association["memberEnds"]
            ],
        },
    }


def _mutate_port(canonical: dict[str, object]) -> None:
    rpn = _declaration(canonical, "FMEALib.xmi", "RPNCalculation")
    next(item for item in rpn["properties"] if item["name"] == "DET")[
        "type"
    ][
        "target"
    ] = "changed"


def _mutate_connector_order(canonical: dict[str, object]) -> None:
    connector = _detection_connector(_declaration(
        canonical,
        "FMEALib.xmi",
        "FMEAItem",
    ))
    connector["ends"].reverse()


def _detection_connector(declaration: dict[str, object]) -> dict[str, object]:
    return next(
        connector
        for connector in declaration["connectors"]
        if any(
            end["role"]["target"].endswith("::Port::DET") for end in connector["ends"]
        )
    )


def _mutate_icon(canonical: dict[str, object]) -> None:
    _declaration(
        canonical,
        "GeneralRAAML.xmi",
        "Undeveloped",
    )["icons"][0]["content"] += "changed"


def _mutate_comment(canonical: dict[str, object]) -> None:
    _declaration(
        canonical,
        "CoreRAAML.xmi",
        "Situation",
    )["comments"][0]["body"] = "changed"


def _mutate_machinery(canonical: dict[str, object]) -> None:
    _artifact(
        canonical,
        "CoreRAAML.xmi",
    )["machinery"][0]["targets"][0]["target"] = "changed"


def _mutate_application(canonical: dict[str, object]) -> None:
    _artifact(
        canonical,
        "FMEALib.xmi",
    )["applications"][0]["target"]["target"] = "changed"


def _mutate_association_order(canonical: dict[str, object]) -> None:
    association = next(
        item
        for item in _artifact(
            canonical,
            "CoreRAAMLLib.xmi",
        )["declarations"]
        if item["kind"] == "Association" and item["name"] == "Causality"
    )
    association["memberEnds"].reverse()


def _remove_one_category_fact(
    canonical: dict[str, object],
    category: str,
) -> bool:
    declaration_kind = {
        "stereotypes": "Stereotype",
        "classes": "Class",
        "enumerations": "Enumeration",
        "associations": "Association",
        "associationClasses": "AssociationClass",
    }
    property_kind = {
        "properties": "Property",
        "ports": "Port",
        "extensionEnds": "ExtensionEnd",
    }
    package_kind = {"profiles": "Profile", "packages": "Package"}

    artifacts = canonical["artifacts"]
    assert isinstance(artifacts, list)
    for artifact in artifacts:
        assert isinstance(artifact, dict)
        if category == "raamlApplications" and artifact["applications"]:
            artifact["applications"].pop()
            return True
        if category in package_kind:
            for index, package in enumerate(artifact["packages"]):
                if package["kind"] == package_kind[category]:
                    artifact["packages"].pop(index)
                    return True
        if category in declaration_kind:
            for index, declaration in enumerate(artifact["declarations"]):
                if declaration["kind"] == declaration_kind[category]:
                    artifact["declarations"].pop(index)
                    return True
        for declaration in artifact["declarations"]:
            if category == "enumerationLiterals" and declaration["literals"]:
                declaration["literals"].pop()
                return True
            if category == "connectors" and declaration["connectors"]:
                declaration["connectors"].pop()
                return True
            if category == "constraints" and declaration["constraints"]:
                declaration["constraints"].pop()
                return True
            if category == "extensions" and declaration["extensions"]:
                declaration["extensions"].pop()
                return True
            if category == "images" and declaration["icons"]:
                declaration["icons"].pop()
                return True
            if category in property_kind:
                for relation in ("properties", "ownedEnds"):
                    for index, item in enumerate(declaration[relation]):
                        if item["kind"] == property_kind[category]:
                            declaration[relation].pop(index)
                            return True
                for extension in declaration["extensions"]:
                    for index, item in enumerate(extension["ownedEnds"]):
                        if item["kind"] == property_kind[category]:
                            extension["ownedEnds"].pop(index)
                            return True
    if category == "comments":
        return _remove_first_comments_array(canonical)
    return False


def _remove_first_comments_array(value: object) -> bool:
    if isinstance(value, dict):
        comments = value.get("comments")
        if isinstance(comments, list) and comments:
            comments.pop()
            return True
        return any(_remove_first_comments_array(child) for child in value.values())
    if isinstance(value, list):
        return any(_remove_first_comments_array(child) for child in value)
    return False


if __name__ == "__main__":
    unittest.main()
