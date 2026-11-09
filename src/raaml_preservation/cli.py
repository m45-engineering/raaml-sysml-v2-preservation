from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any
import unittest
import xml.etree.ElementTree as ET

from . import __version__
from .conformance import ConformanceError, run_adversarial_suite
from .adapters import (
    AdapterError,
    bootstrap_tooling,
    build_adapter,
    run_adapter,
    run_v1_corpus_adapter,
    stable_adapter_report,
)
from .facts import (
    FactExtractionError,
    count_facts,
    extract_facts,
    serialize_facts,
)
from .roundtrip import (
    FULL_CORPUS_ID,
    RoundTripError,
    canonical_json,
    compare_full_corpus,
    compare_reconstructed,
    forward_full_corpus,
    forward_slice,
    reverse_full_corpus,
    reverse_slice,
)
from .oracle import EXPECTED_TOTALS, audit_corpus
from .ocl_validation import validate_ocl_corpus
from .publication import audit_repository
from .release import ReleaseError, reproduce_release
from .sources import LockError, fetch_sources, load_lock, verify_sources
from .v2 import NativeModel, validate_native_structure
from .transformation import (
    analyze_constraint_transformation_surface,
    analyze_corpus_transformation_surface,
    analyze_property_transformation_surface,
    audit_transformation_matrix,
)
from .schemas import (
    SchemaValidationError,
    validate_instance_against_schema,
    validate_schemas,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _sources_verify(args: argparse.Namespace) -> int:
    try:
        report = verify_sources(
            lock_path=args.lock,
            source_dir=args.source_dir,
            collection=args.collection,
        )
    except LockError as error:
        report = {
            "schemaVersion": "0.1.0",
            "command": "sources verify",
            "ok": False,
            "summary": {"checked": 0, "failed": 1},
            "diagnostics": [
                {
                    "severity": "error",
                    "code": "LOCK_INVALID",
                    "message": str(error),
                }
            ],
        }

    _write_json_atomic(args.diagnostics, report)
    summary = report["summary"]
    if report["ok"]:
        print(
            f"Verified {summary['checked']} source artifact(s); "
            f"diagnostics: {args.diagnostics}"
        )
        return 0

    print(
        f"Source verification failed: {summary['failed']} error(s); "
        f"diagnostics: {args.diagnostics}",
        file=sys.stderr,
    )
    for diagnostic in report["diagnostics"]:
        if diagnostic["severity"] == "error":
            print(
                f"{diagnostic['code']}: {diagnostic['message']}",
                file=sys.stderr,
            )
    return 1


def _sources_fetch(args: argparse.Namespace) -> int:
    try:
        report = fetch_sources(
            lock_path=args.lock,
            source_dir=args.source_dir,
        )
    except (LockError, OSError) as error:
        report = {
            "schemaVersion": "0.1.0",
            "command": "sources fetch",
            "ok": False,
            "summary": {"checked": 0, "fetched": 0, "failed": 1},
            "diagnostics": [
                {
                    "severity": "error",
                    "code": "SOURCE_FETCH_FAILED",
                    "message": str(error),
                }
            ],
        }
    _write_json_atomic(args.diagnostics, report)
    summary = report["summary"]
    if report["ok"]:
        print(
            f"Fetched {summary['fetched']} of {summary['checked']} locked "
            f"source artifact(s); diagnostics: {args.diagnostics}"
        )
        return 0

    print(
        f"Source fetch failed: {summary['failed']} error(s); "
        f"diagnostics: {args.diagnostics}",
        file=sys.stderr,
    )
    for diagnostic in report["diagnostics"]:
        if diagnostic["severity"] == "error":
            print(
                f"{diagnostic['code']}: {diagnostic['message']}",
                file=sys.stderr,
            )
    return 1


def _path(value: str) -> Path:
    return Path(value)


def _tests_unit(args: argparse.Namespace) -> int:
    suite = unittest.defaultTestLoader.discover(
        str(REPOSITORY_ROOT / "tests"),
        pattern="test_*.py",
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    failures = len(result.failures) + len(result.errors)
    report = {
        "schemaVersion": "0.1.0",
        "command": "tests unit",
        "ok": result.wasSuccessful(),
        "summary": {
            "checked": result.testsRun,
            "failed": failures,
        },
        "diagnostics": [
            {
                "severity": "error",
                "code": "UNIT_TEST_FAILURE",
                "message": test.id(),
            }
            for test, _traceback in result.failures + result.errors
        ],
    }
    _write_json_atomic(args.diagnostics, report)
    return 0 if result.wasSuccessful() else 1


def _tests_milestone_zero(args: argparse.Namespace) -> int:
    fixtures = REPOSITORY_ROOT / "fixtures" / "milestone-0"
    cases = (
        ("v2-valid", "v2", fixtures / "minimal-valid.sysml", True),
        ("v2-invalid", "v2", fixtures / "minimal-invalid.sysml", False),
        ("v1-profile", "v1", fixtures / "minimal-v1-profile.xmi", True),
        ("v1-library", "v1", fixtures / "minimal-v1-library.xmi", True),
        (
            "v1-invalid-reference",
            "v1",
            fixtures / "minimal-v1-invalid-reference.xmi",
            False,
        ),
        (
            "v1-core-profile",
            "v1",
            REPOSITORY_ROOT / "sources" / "cache" / "CoreRAAML.xmi",
            True,
        ),
        (
            "v1-core-library",
            "v1",
            REPOSITORY_ROOT / "sources" / "cache" / "CoreRAAMLLib.xmi",
            True,
        ),
        ("ocl-valid", "ocl", fixtures / "ocl-valid.txt", True),
        ("ocl-invalid", "ocl", fixtures / "ocl-invalid.txt", False),
    )
    diagnostics: list[dict[str, str]] = []
    try:
        build_adapter(REPOSITORY_ROOT)
        for name, mode, path, expected in cases:
            result = run_adapter(REPOSITORY_ROOT, mode, path)
            if bool(result["ok"]) != expected:
                diagnostics.append(
                    {
                        "severity": "error",
                        "code": "MILESTONE_ZERO_EXPECTATION",
                        "message": (
                            f"{name}: expected ok={expected}, "
                            f"got {result['ok']!r}"
                        ),
                    }
                )
            if name == "v2-valid" and any(result["errorCategories"].values()):
                diagnostics.append(
                    {
                        "severity": "error",
                        "code": "V2_CATEGORY_NOT_ZERO",
                        "message": "valid v2 fixture has a nonzero error category",
                    }
                )
            if name == "ocl-valid":
                required = {"Situation", "allInstances", "closure", "from"}
                missing = required - set(result["referencedNames"])
                if missing:
                    diagnostics.append(
                        {
                            "severity": "error",
                            "code": "OCL_AST_NAME_MISSING",
                            "message": f"OCL AST names missing: {sorted(missing)}",
                        }
                    )
    except AdapterError as error:
        diagnostics.append(
            {
                "severity": "error",
                "code": "MILESTONE_ZERO_ADAPTER",
                "message": str(error),
            }
        )
    report = {
        "schemaVersion": "0.1.0",
        "command": "tests milestone-0",
        "ok": not diagnostics,
        "summary": {"checked": len(cases), "failed": len(diagnostics)},
        "diagnostics": diagnostics,
    }
    _write_json_atomic(args.diagnostics, report)
    return 0 if report["ok"] else 1


def _tests_milestone_one(args: argparse.Namespace) -> int:
    diagnostics: list[dict[str, str]] = []
    checked = 0
    try:
        raw, canonical = extract_facts(REPOSITORY_ROOT)
        checked += 17
        validate_instance_against_schema(
            raw,
            REPOSITORY_ROOT / "schemas" / "raw-raaml-facts.schema.json",
        )
        validate_instance_against_schema(
            canonical,
            REPOSITORY_ROOT / "schemas" / "canonical-raaml-facts.schema.json",
        )
        raw_again, canonical_again = extract_facts(REPOSITORY_ROOT)
        if serialize_facts(raw) != serialize_facts(raw_again):
            diagnostics.append(
                {
                    "severity": "error",
                    "code": "FACT_RAW_NONDETERMINISTIC",
                    "message": "two raw extractions are not byte-identical",
                }
            )
        if serialize_facts(canonical) != serialize_facts(canonical_again):
            diagnostics.append(
                {
                    "severity": "error",
                    "code": "FACT_CANONICAL_NONDETERMINISTIC",
                    "message": "two canonical extractions are not byte-identical",
                }
            )
        actual_counts = count_facts(canonical)
        if actual_counts != EXPECTED_TOTALS:
            diagnostics.append(
                {
                    "severity": "error",
                    "code": "FACT_COUNT_MISMATCH",
                    "message": (
                        f"expected {EXPECTED_TOTALS!r}, got {actual_counts!r}"
                    ),
                }
            )
        oracle_report = audit_corpus(REPOSITORY_ROOT)
        if not oracle_report["ok"]:
            diagnostics.extend(oracle_report["diagnostics"])
        elif oracle_report["counts"] != actual_counts:
            diagnostics.append(
                {
                    "severity": "error",
                    "code": "FACT_ORACLE_DISAGREEMENT",
                    "message": "production and independent corpus counts differ",
                }
            )
        ocl_report = validate_ocl_corpus(REPOSITORY_ROOT)
        checked += ocl_report["summary"]["checked"]
        if not ocl_report["ok"]:
            diagnostics.extend(ocl_report["diagnostics"])
    except (FactExtractionError, SchemaValidationError, OSError) as error:
        diagnostics.append(
            {
                "severity": "error",
                "code": getattr(error, "code", "MILESTONE_ONE_FAILURE"),
                "message": str(error),
            }
        )
    report = {
        "schemaVersion": "0.1.0",
        "command": "tests milestone-1",
        "ok": not diagnostics,
        "summary": {
            "checked": checked,
            "failed": len(diagnostics),
        },
        "diagnostics": diagnostics,
    }
    _write_json_atomic(args.diagnostics, report)
    return 0 if report["ok"] else 1


def _forward_command(args: argparse.Namespace) -> int:
    diagnostics: list[dict[str, str]] = []
    milestone = "milestone-4" if args.milestone_4 else "milestone-3"
    output_dir = args.output_dir or (
        REPOSITORY_ROOT / "generated" / milestone / "forward"
    )
    diagnostics_path = args.diagnostics or (
        REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / f"forward-{milestone}.json"
    )
    try:
        if args.milestone_4:
            result = forward_full_corpus(REPOSITORY_ROOT, output_dir)
            manifest_paths = result["manifests"]
            diagnostics.extend(NativeModel(result["facts"]).notes())
        else:
            result = forward_slice(REPOSITORY_ROOT, output_dir)
            manifest_paths = [result["manifest"]]
        for manifest_path in manifest_paths:
            validate_instance_against_schema(
                json.loads(manifest_path.read_text(encoding="utf-8")),
                REPOSITORY_ROOT / "schemas" / "preservation-manifest.schema.json",
            )
        validate_instance_against_schema(
            result["facts"],
            REPOSITORY_ROOT / "schemas" / "canonical-raaml-facts.schema.json",
        )
    except (FactExtractionError, RoundTripError, SchemaValidationError, OSError) as error:
        diagnostics.append(
            {
                "severity": "error",
                "code": getattr(error, "code", "FORWARD_FAILED"),
                "message": str(error),
            }
        )
    report = {
        "schemaVersion": "0.1.0",
        "command": "forward",
        "ok": not any(item["severity"] == "error" for item in diagnostics),
        "summary": {
            "checked": 1,
            "failed": sum(item["severity"] == "error" for item in diagnostics),
        },
        "diagnostics": diagnostics,
    }
    _write_json_atomic(diagnostics_path, report)
    return 0 if report["ok"] else 1


def _reverse_command(args: argparse.Namespace) -> int:
    diagnostics: list[dict[str, str]] = []
    checked = 0
    try:
        if args.manifest_dir is not None:
            paths = reverse_full_corpus(
                args.manifest_dir,
                args.v2,
                args.output_dir,
            )
        else:
            paths = reverse_slice(args.manifest, args.v2, args.output_dir)
        checked = len(paths)
    except (RoundTripError, OSError) as error:
        diagnostics.append(
            {
                "severity": "error",
                "code": getattr(error, "code", "REVERSE_FAILED"),
                "message": str(error),
            }
        )
    report = {
        "schemaVersion": "0.1.0",
        "command": "reverse",
        "ok": not diagnostics,
        "summary": {"checked": checked, "failed": len(diagnostics)},
        "diagnostics": diagnostics,
    }
    _write_json_atomic(args.diagnostics, report)
    return 0 if report["ok"] else 1


def _tests_milestone_five(args: argparse.Namespace) -> int:
    diagnostics: list[dict[str, str]] = []
    checked = 0
    try:
        with tempfile.TemporaryDirectory(prefix="raaml-m5-") as temporary:
            root = Path(temporary)
            forward = forward_full_corpus(REPOSITORY_ROOT, root / "forward")
            first_dir = root / "first"
            second_dir = root / "second"
            first = reverse_full_corpus(
                root / "forward" / "manifests",
                forward["v2"],
                first_dir,
            )
            second = reverse_full_corpus(
                root / "forward" / "manifests",
                forward["v2"],
                second_dir,
            )
            checked += 34
            first_digests = _file_digests(first_dir)
            second_digests = _file_digests(second_dir)
            if first_digests != second_digests:
                raise RoundTripError(
                    "FULL_REVERSE_NONDETERMINISTIC",
                    "two full-corpus reverse runs are not byte-identical",
                )
            if len(first) != 17 or len(first_digests) != 17:
                raise RoundTripError(
                    "FULL_REVERSE_OUTPUT_COUNT",
                    f"expected 17 reconstructed artifacts, got {len(first_digests)}",
                )

            for path in first:
                try:
                    root_element = ET.fromstring(path.read_bytes())
                except ET.ParseError as error:
                    raise RoundTripError(
                        "RECONSTRUCTED_XML_INVALID",
                        f"{path.name}: {error}",
                    ) from error
                generated_ids = [
                    value
                    for element in root_element.iter()
                    if (value := element.get(
                        "{http://www.omg.org/spec/XMI/20131001}id"
                    ))
                ]
                if len(generated_ids) != len(set(generated_ids)):
                    raise RoundTripError(
                        "RECONSTRUCTED_ID_DUPLICATE",
                        f"{path.name}: duplicate generated xmi:id",
                    )
                if not generated_ids or any(
                    not value.startswith("_raaml_") for value in generated_ids
                ):
                    raise RoundTripError(
                        "RECONSTRUCTED_ID_POLICY",
                        f"{path.name}: generated IDs do not follow the stable-ID policy",
                    )
                checked += 1

            corpus_result = run_v1_corpus_adapter(
                REPOSITORY_ROOT,
                first_dir,
            )
            v1_reports = [
                stable_adapter_report(report)
                for report in corpus_result.get("results", [])
            ]
            checked += len(v1_reports)
            if len(v1_reports) != 17:
                raise RoundTripError(
                    "FULL_REVERSE_V1_RESULT_COUNT",
                    f"expected 17 v1 validation results, got {len(v1_reports)}",
                )
            if not corpus_result["ok"]:
                failed_inputs = [
                    report.get("input", "(unknown)")
                    for report in v1_reports
                    if not report.get("ok")
                ]
                raise RoundTripError(
                    "FULL_REVERSE_V1_INVALID",
                    "invalid reconstructed artifact(s): "
                    + ", ".join(failed_inputs),
                )

            collision_output = root / "collision-output"
            try:
                reverse_full_corpus(
                    root / "forward" / "manifests",
                    forward["v2"],
                    collision_output,
                    hash_provider=lambda value: "0" * 64,
                )
            except RoundTripError as error:
                if error.code != "SYNTHETIC_ID_COLLISION":
                    raise
                collision_code = error.code
            else:
                raise RoundTripError(
                    "COLLISION_ACCEPTED",
                    "injected synthetic-ID collision did not stop reconstruction",
                )
            if collision_output.exists():
                raise RoundTripError(
                    "COLLISION_OUTPUT_WRITTEN",
                    "collision failure wrote a partial output directory",
                )
            checked += 1

            published = {
                "schemaVersion": "0.1.0",
                "documentKind": "milestone-5-build-report",
                "implementationVersion": __version__,
                "scopeId": "milestone-5-full-corpus-reverse",
                "ok": True,
                "sourceDigests": {
                    artifact["filename"]: artifact["sha256"]
                    for artifact in forward["facts"]["artifacts"]
                },
                "reconstructedOutputs": first_digests,
                "idPolicy": {
                    "scheme": "deterministic sha256-derived _raaml_ identifiers",
                    "originalMagicDrawIdsRequired": False,
                    "originalMagicDrawIdsClaimedPreserved": False,
                },
                "collisionGate": {
                    "provider": "constant test hash provider",
                    "diagnosticCode": collision_code,
                    "partialOutputWritten": False,
                },
                "tools": {
                    "mandatoryV1Validator": (
                        v1_reports[0].get("adapterVersion")
                        if v1_reports
                        else None
                    )
                },
                "summary": {
                    "sourceArtifacts": 17,
                    "reconstructedArtifacts": len(first_digests),
                    "wellFormedXmlArtifacts": len(first_digests),
                    "v1ValidationErrors": sum(
                        report["summary"]["failed"] for report in v1_reports
                    ),
                    "byteDeterministic": True,
                    "collisionRejected": True,
                },
                "stages": {
                    "v1": v1_reports,
                },
            }
            validate_instance_against_schema(
                published,
                REPOSITORY_ROOT
                / "schemas"
                / "milestone-5-build-report.schema.json",
            )
            _write_json_atomic(args.output, published)
    except (
        AdapterError,
        FactExtractionError,
        RoundTripError,
        SchemaValidationError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        diagnostics.append(
            {
                "severity": "error",
                "code": getattr(error, "code", "MILESTONE_FIVE_FAILURE"),
                "message": str(error),
            }
        )
    report = {
        "schemaVersion": "0.1.0",
        "command": "tests milestone-5",
        "ok": not diagnostics,
        "summary": {"checked": checked, "failed": len(diagnostics)},
        "diagnostics": diagnostics,
    }
    _write_json_atomic(args.diagnostics, report)
    return 0 if report["ok"] else 1


def _tests_milestone_six(args: argparse.Namespace) -> int:
    diagnostics: list[dict[str, str]] = []
    checked = 0
    try:
        with tempfile.TemporaryDirectory(prefix="raaml-m6-") as temporary:
            root = Path(temporary)
            forward = forward_full_corpus(REPOSITORY_ROOT, root / "forward")
            checked += 18

            v2_report = run_adapter(
                REPOSITORY_ROOT,
                "v2",
                forward["v2"],
            )
            checked += 1
            if not v2_report["ok"]:
                raise RoundTripError(
                    "FULL_CORPUS_V2_INVALID",
                    "generated full-corpus SysML v2 is invalid",
                )

            reconstructed = root / "reconstructed"
            paths = reverse_full_corpus(
                root / "forward" / "manifests",
                forward["v2"],
                reconstructed,
            )
            checked += len(paths)

            v1_report = run_v1_corpus_adapter(
                REPOSITORY_ROOT,
                reconstructed,
            )
            checked += v1_report["summary"]["checked"]
            if not v1_report["ok"]:
                raise RoundTripError(
                    "FULL_CORPUS_V1_INVALID",
                    "reconstructed full corpus is invalid",
                )

            comparison = compare_full_corpus(
                REPOSITORY_ROOT,
                reconstructed,
            )
            validate_instance_against_schema(
                comparison,
                REPOSITORY_ROOT
                / "schemas"
                / "full-corpus-comparison-report.schema.json",
            )
            _write_json_atomic(args.comparison_output, comparison)
            checked += 1
            if not comparison["ok"]:
                raise RoundTripError(
                    "FULL_CORPUS_FACT_DIFFERENCE",
                    f"{comparison['summary']['differences']} canonical "
                    "fact difference(s)",
                )

            adversarial_cases = run_adversarial_suite(
                REPOSITORY_ROOT,
                root / "adversarial",
                forward,
                reconstructed,
                comparison,
            )
            checked += len(adversarial_cases)
            failed_cases = sum(
                not item["passed"] for item in adversarial_cases
            )
            stable_v1_results = [
                stable_adapter_report(result)
                for result in v1_report["results"]
            ]
            stable_v2 = stable_adapter_report(v2_report)
            published = {
                "schemaVersion": "0.1.0",
                "documentKind": "milestone-6-conformance-report",
                "implementationVersion": __version__,
                "scopeId": "milestone-6-full-corpus-conformance",
                "ok": failed_cases == 0,
                "sourceDigests": {
                    artifact["filename"]: artifact["sha256"]
                    for artifact in forward["facts"]["artifacts"]
                },
                "tools": {
                    "mandatoryV1Validator": stable_v1_results[0][
                        "adapterVersion"
                    ],
                    "mandatoryV2Validator": stable_v2["adapterVersion"],
                },
                "summary": {
                    "artifacts": 17,
                    "canonicalFactsSha256": comparison["summary"][
                        "sourceFactsSha256"
                    ],
                    "differences": comparison["summary"]["differences"],
                    "adversarialCases": len(adversarial_cases),
                    "failedAdversarialCases": failed_cases,
                    "v1ValidationErrors": sum(
                        result["summary"]["failed"]
                        for result in stable_v1_results
                    ),
                    "v2ValidationErrors": stable_v2["summary"]["failed"],
                },
                "sourceCounts": comparison["sourceCounts"],
                "reconstructedCounts": comparison["reconstructedCounts"],
                "perArtifact": comparison["perArtifact"],
                "adversarialCases": adversarial_cases,
            }
            validate_instance_against_schema(
                published,
                REPOSITORY_ROOT
                / "schemas"
                / "milestone-6-conformance-report.schema.json",
            )
            _write_json_atomic(args.output, published)
    except (
        AdapterError,
        ConformanceError,
        FactExtractionError,
        RoundTripError,
        SchemaValidationError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        diagnostics.append(
            {
                "severity": "error",
                "code": getattr(error, "code", "MILESTONE_SIX_FAILURE"),
                "message": str(error),
            }
        )
    report = {
        "schemaVersion": "0.1.0",
        "command": "tests milestone-6",
        "ok": not diagnostics,
        "summary": {"checked": checked, "failed": len(diagnostics)},
        "diagnostics": diagnostics,
    }
    _write_json_atomic(args.diagnostics, report)
    return 0 if report["ok"] else 1


def _compare_command(args: argparse.Namespace) -> int:
    diagnostics: list[dict[str, str]] = []
    comparison: dict[str, Any] | None = None
    try:
        if args.full_corpus:
            comparison = compare_full_corpus(
                REPOSITORY_ROOT,
                args.reconstructed_dir,
            )
            schema = (
                REPOSITORY_ROOT
                / "schemas"
                / "full-corpus-comparison-report.schema.json"
            )
            default_output = (
                REPOSITORY_ROOT
                / "reports"
                / "conformance"
                / "milestone-6-comparison.json"
            )
        else:
            comparison = compare_reconstructed(
                REPOSITORY_ROOT,
                args.manifest,
                args.reconstructed_dir,
            )
            schema = (
                REPOSITORY_ROOT / "schemas" / "roundtrip-report.schema.json"
            )
            default_output = (
                REPOSITORY_ROOT
                / "reports"
                / "conformance"
                / "milestone-3-comparison.json"
            )
        if not comparison["ok"]:
            diagnostics.append(
                {
                    "severity": "error",
                    "code": "ROUNDTRIP_FACT_DIFFERENCE",
                    "message": (
                        f"{comparison['summary']['differences']} canonical "
                        "fact difference(s)"
                    ),
                }
            )
        validate_instance_against_schema(comparison, schema)
        _write_json_atomic(args.output or default_output, comparison)
    except (
        FactExtractionError,
        RoundTripError,
        SchemaValidationError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        diagnostics.append(
            {
                "severity": "error",
                "code": getattr(error, "code", "COMPARE_FAILED"),
                "message": str(error),
            }
        )
    report = {
        "schemaVersion": "0.1.0",
        "command": "compare",
        "ok": not diagnostics,
        "summary": {
            "checked": 1 if comparison is not None else 0,
            "failed": len(diagnostics),
        },
        "diagnostics": diagnostics,
    }
    _write_json_atomic(args.diagnostics, report)
    return 0 if report["ok"] else 1


def _tests_milestone_three(args: argparse.Namespace) -> int:
    diagnostics: list[dict[str, str]] = []
    checked = 0
    stage_reports: dict[str, Any] = {}
    try:
        with tempfile.TemporaryDirectory(prefix="raaml-m3-") as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            reconstructed = root / "reconstructed"
            first_result = forward_slice(REPOSITORY_ROOT, first)
            second_result = forward_slice(REPOSITORY_ROOT, second)
            checked += 2
            for filename in ("preservation-manifest.json", "raaml-milestone-3.sysml"):
                if (first / filename).read_bytes() != (second / filename).read_bytes():
                    raise RoundTripError(
                        "FORWARD_NONDETERMINISTIC",
                        f"two forward runs differ for {filename}",
                    )
            v2_report = run_adapter(
                REPOSITORY_ROOT, "v2", first_result["v2"]
            )
            stage_reports["v2"] = stable_adapter_report(v2_report)
            checked += 1
            if not v2_report["ok"]:
                raise RoundTripError("V2_VALIDATION_FAILED", "generated v2 is invalid")
            paths = reverse_slice(
                first_result["manifest"],
                first_result["v2"],
                reconstructed,
            )
            checked += len(paths)
            v1_reports = []
            for path in paths:
                result = run_adapter(
                    REPOSITORY_ROOT,
                    "v1",
                    path,
                    v1_catalog_dir=reconstructed,
                )
                v1_reports.append(stable_adapter_report(result))
                checked += 1
                if not result["ok"]:
                    raise RoundTripError(
                        "V1_VALIDATION_FAILED",
                        f"reconstructed {path.name} is invalid",
                    )
            stage_reports["v1"] = v1_reports
            comparison = compare_reconstructed(
                REPOSITORY_ROOT,
                first_result["manifest"],
                reconstructed,
            )
            stage_reports["comparison"] = comparison["summary"]
            checked += 1
            if not comparison["ok"]:
                raise RoundTripError(
                    "ROUNDTRIP_FACT_DIFFERENCE",
                    f"{comparison['summary']['differences']} fact difference(s)",
                )
            validate_instance_against_schema(
                comparison,
                REPOSITORY_ROOT / "schemas" / "roundtrip-report.schema.json",
            )
            manifest = json.loads(
                first_result["manifest"].read_text(encoding="utf-8")
            )
            manifest["payload"]["canonicalFacts"]["artifacts"][0][
                "declarations"
            ][0]["name"] = "Corrupted"
            corrupt_path = root / "corrupt-manifest.json"
            _write_json_atomic(corrupt_path, manifest)
            try:
                reverse_slice(
                    corrupt_path,
                    first_result["v2"],
                    root / "corrupt-output",
                )
            except RoundTripError as error:
                if error.code != "MANIFEST_DIGEST":
                    raise
            else:
                raise RoundTripError(
                    "CORRUPT_MANIFEST_ACCEPTED",
                    "corrupt manifest was accepted",
                )
            checked += 1
            missing_v2 = root / "missing-target.sysml"
            missing_v2.write_text(
                first_result["v2"].read_text(encoding="utf-8").replace(
                    "        metadata def Situation;\n",
                    "",
                    1,
                ),
                encoding="utf-8",
                newline="\n",
            )
            try:
                reverse_slice(
                    first_result["manifest"],
                    missing_v2,
                    root / "missing-output",
                )
            except RoundTripError as error:
                if error.code not in {"V2_DIGEST", "V2_TARGET_MISSING"}:
                    raise
            else:
                raise RoundTripError(
                    "MISSING_TARGET_ACCEPTED",
                    "manifest with removed targets was accepted",
                )
            checked += 1
            ordered = json.loads(
                first_result["manifest"].read_text(encoding="utf-8")
            )
            core_library = next(
                artifact
                for artifact in ordered["payload"]["canonicalFacts"]["artifacts"]
                if artifact["filename"] == "CoreRAAMLLib.xmi"
            )
            association = next(
                item
                for item in core_library["declarations"]
                if item["kind"] == "Association"
            )
            association["memberEnds"].reverse()
            ordered["payloadSha256"] = hashlib.sha256(
                canonical_json(ordered["payload"])
            ).hexdigest()
            ordered_path = root / "ordered-value.json"
            _write_json_atomic(ordered_path, ordered)
            ordered_output = root / "ordered-output"
            reverse_slice(
                ordered_path,
                first_result["v2"],
                ordered_output,
            )
            ordered_comparison = compare_reconstructed(
                REPOSITORY_ROOT,
                first_result["manifest"],
                ordered_output,
            )
            if ordered_comparison["ok"]:
                raise RoundTripError(
                    "ORDERED_MUTATION_UNDETECTED",
                    "ordered member-end mutation was not detected",
                )
            checked += 1
            published = {
                "schemaVersion": "0.1.0",
                "documentKind": "milestone-3-conformance-report",
                "implementationVersion": __version__,
                "sliceId": "milestone-3-core-general-stpa",
                "ok": True,
                "sourceDigests": {
                    artifact["filename"]: artifact["sha256"]
                    for artifact in first_result["facts"]["artifacts"]
                },
                "lockedInputs": {
                    artifact["id"]: {
                        "collection": artifact["collection"],
                        "filename": artifact["filename"],
                        "sha256": artifact["sha256"],
                    }
                    for artifact in load_lock(
                        REPOSITORY_ROOT / "standards.lock.json"
                    )["artifacts"]
                },
                "tools": {
                    "v2Adapter": stage_reports["v2"].get("adapterVersion"),
                    "v1Adapter": (
                        stage_reports["v1"][0].get("adapterVersion")
                        if stage_reports["v1"]
                        else None
                    ),
                },
                "summary": comparison["summary"],
                "stages": stage_reports,
            }
            _write_json_atomic(args.output, published)
    except (
        AdapterError,
        FactExtractionError,
        RoundTripError,
        SchemaValidationError,
        OSError,
    ) as error:
        diagnostics.append(
            {
                "severity": "error",
                "code": getattr(error, "code", "MILESTONE_THREE_FAILURE"),
                "message": str(error),
            }
        )
    report = {
        "schemaVersion": "0.1.0",
        "command": "tests milestone-3",
        "ok": not diagnostics,
        "summary": {"checked": checked, "failed": len(diagnostics)},
        "diagnostics": diagnostics,
    }
    _write_json_atomic(args.diagnostics, report)
    return 0 if report["ok"] else 1


def _file_digests(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _tests_milestone_four(args: argparse.Namespace) -> int:
    diagnostics: list[dict[str, str]] = []
    checked = 0
    try:
        with tempfile.TemporaryDirectory(prefix="raaml-m4-") as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            first_result = forward_full_corpus(REPOSITORY_ROOT, first)
            second_result = forward_full_corpus(REPOSITORY_ROOT, second)
            checked += 2
            first_digests = _file_digests(first)
            second_digests = _file_digests(second)
            if first_digests != second_digests:
                raise RoundTripError(
                    "FULL_CORPUS_NONDETERMINISTIC",
                    "two full-corpus generations are not byte-identical",
                )
            if len(first_digests) != 18:
                raise RoundTripError(
                    "FULL_CORPUS_OUTPUT_COUNT",
                    f"expected 18 generated files, got {len(first_digests)}",
                )
            manifests = []
            native_target_count = 0
            for manifest_path in first_result["manifests"]:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                validate_instance_against_schema(
                    manifest,
                    REPOSITORY_ROOT
                    / "schemas"
                    / "preservation-manifest.schema.json",
                )
                artifact_facts = manifest["payload"]["canonicalFacts"]
                validate_instance_against_schema(
                    artifact_facts,
                    REPOSITORY_ROOT
                    / "schemas"
                    / "canonical-raaml-facts.schema.json",
                )
                native_target_count += len(manifest["payload"]["nativeTargets"])
                manifests.append(
                    {
                        "artifactId": manifest["payload"]["artifactId"],
                        "sourceFilename": manifest["payload"]["sourceFilename"],
                        "sourceSha256": manifest["payload"]["sourceSha256"],
                        "manifestSha256": hashlib.sha256(
                            manifest_path.read_bytes()
                        ).hexdigest(),
                        "payloadSha256": manifest["payloadSha256"],
                        "nativeTargets": len(
                            manifest["payload"]["nativeTargets"]
                        ),
                    }
                )
                checked += 1
            if len(manifests) != 17:
                raise RoundTripError(
                    "FULL_CORPUS_MANIFEST_COUNT",
                    f"expected 17 manifests, got {len(manifests)}",
                )
            if native_target_count != 343:
                raise RoundTripError(
                    "FULL_CORPUS_NATIVE_TARGET_COUNT",
                    f"expected 343 native targets, got {native_target_count}",
                )
            v2_report = run_adapter(
                REPOSITORY_ROOT,
                "v2",
                first_result["v2"],
            )
            stable_v2_report = stable_adapter_report(v2_report)
            checked += 1
            if not v2_report["ok"]:
                raise RoundTripError(
                    "FULL_CORPUS_V2_INVALID",
                    "generated full-corpus SysML v2 model is invalid",
                )
            if any(v2_report["errorCategories"].values()):
                raise RoundTripError(
                    "FULL_CORPUS_V2_CATEGORY",
                    "a SysML v2 validation category is nonzero",
                )
            structural_errors = validate_native_structure(
                first_result["facts"], v2_report["nativeStructure"]
            )
            if structural_errors:
                raise RoundTripError(
                    "FULL_CORPUS_STRUCTURE", "; ".join(structural_errors[:10])
                )
            v2_text = first_result["v2"].read_text(encoding="utf-8")
            if "private import ScalarValues::*;" not in v2_text:
                raise RoundTripError(
                    "FULL_CORPUS_IMPORT_MISSING",
                    "generated model does not exercise pinned library imports",
                )
            declaration_count = sum(
                len(artifact["declarations"])
                for artifact in first_result["facts"]["artifacts"]
            )
            constraint_count = sum(
                len(declaration["constraints"])
                for artifact in first_result["facts"]["artifacts"]
                for declaration in artifact["declarations"]
            )
            published = {
                "schemaVersion": "0.1.0",
                "documentKind": "milestone-4-build-report",
                "implementationVersion": __version__,
                "scopeId": FULL_CORPUS_ID,
                "ok": True,
                "sourceDigests": {
                    artifact["filename"]: artifact["sha256"]
                    for artifact in first_result["facts"]["artifacts"]
                },
                "generatedOutputs": first_digests,
                "tools": {
                    "mandatoryV2Validator": stable_v2_report.get(
                        "adapterVersion"
                    ),
                    "secondV2Parser": None,
                },
                "interoperability": {
                    "mandatoryValidator": "passed",
                    "secondImplementation": (
                        "not tested with a second implementation"
                    ),
                },
                "summary": {
                    "sourceArtifacts": 17,
                    "generatedFiles": len(first_digests),
                    "preservationManifests": len(manifests),
                    "declarations": declaration_count,
                    "constraintCarriers": constraint_count,
                    "nativeTargets": native_target_count,
                    "v2ValidationErrors": sum(
                        v2_report["errorCategories"].values()
                    ),
                },
                "stages": {
                    "manifests": sorted(
                        manifests,
                        key=lambda item: item["artifactId"],
                    ),
                    "v2": stable_v2_report,
                },
            }
            validate_instance_against_schema(
                published,
                REPOSITORY_ROOT
                / "schemas"
                / "milestone-4-build-report.schema.json",
            )
            _write_json_atomic(args.output, published)
    except (
        AdapterError,
        FactExtractionError,
        RoundTripError,
        SchemaValidationError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        diagnostics.append(
            {
                "severity": "error",
                "code": getattr(error, "code", "MILESTONE_FOUR_FAILURE"),
                "message": str(error),
            }
        )
    report = {
        "schemaVersion": "0.1.0",
        "command": "tests milestone-4",
        "ok": not diagnostics,
        "summary": {"checked": checked, "failed": len(diagnostics)},
        "diagnostics": diagnostics,
    }
    _write_json_atomic(args.diagnostics, report)
    return 0 if report["ok"] else 1


def _adapter_command(args: argparse.Namespace) -> int:
    try:
        report = run_adapter(REPOSITORY_ROOT, args.mode, args.input)
    except AdapterError as error:
        report = {
            "schemaVersion": "0.1.0",
            "command": args.command_name,
            "ok": False,
            "summary": {"checked": 0, "failed": 1},
            "diagnostics": [
                {
                    "severity": "error",
                    "code": "ADAPTER_UNAVAILABLE",
                    "message": str(error),
                }
            ],
        }
    _write_json_atomic(args.diagnostics, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


def _build_adapters(args: argparse.Namespace) -> int:
    try:
        report = build_adapter(REPOSITORY_ROOT)
    except AdapterError as error:
        report = {
            "schemaVersion": "0.1.0",
            "command": "tooling build-adapters",
            "ok": False,
            "summary": {"checked": 0, "failed": 1},
            "diagnostics": [
                {
                    "severity": "error",
                    "code": "ADAPTER_BUILD_FAILED",
                    "message": str(error),
                }
            ],
        }
    _write_json_atomic(args.diagnostics, report)
    return 0 if report["ok"] else 1


def _bootstrap_tooling(args: argparse.Namespace) -> int:
    try:
        report = bootstrap_tooling(REPOSITORY_ROOT)
    except AdapterError as error:
        report = {
            "schemaVersion": "0.1.0",
            "command": "tooling bootstrap",
            "ok": False,
            "summary": {"checked": 0, "failed": 1},
            "diagnostics": [
                {
                    "severity": "error",
                    "code": "TOOLING_BOOTSTRAP_FAILED",
                    "message": str(error),
                }
            ],
        }
    _write_json_atomic(args.diagnostics, report)
    return 0 if report["ok"] else 1


def _schemas_validate(args: argparse.Namespace) -> int:
    report = validate_schemas(REPOSITORY_ROOT)
    _write_json_atomic(args.diagnostics, report)
    if not report["ok"]:
        for diagnostic in report["diagnostics"]:
            print(
                f"{diagnostic['code']}: {diagnostic['message']}",
                file=sys.stderr,
            )
    return 0 if report["ok"] else 1


def _reproduce(args: argparse.Namespace) -> int:
    diagnostics: list[dict[str, str]] = []
    checked = 0
    try:
        report = reproduce_release(
            REPOSITORY_ROOT,
            args.output_dir,
            container_digest=args.container_digest,
            release_tag=args.release_tag,
            require_clean=args.clean,
            supplied_commit=args.git_commit,
            supplied_state=args.source_state,
        )
        checked = report["publishedArtifacts"]
    except (
        AdapterError,
        ConformanceError,
        FactExtractionError,
        LockError,
        ReleaseError,
        RoundTripError,
        SchemaValidationError,
        OSError,
        ValueError,
    ) as error:
        diagnostics.append(
            {
                "severity": "error",
                "code": getattr(error, "code", "REPRODUCE_FAILED"),
                "message": str(error),
            }
        )
    diagnostic_report = {
        "schemaVersion": "0.1.0",
        "command": "reproduce",
        "ok": not diagnostics,
        "summary": {
            "checked": checked,
            "failed": len(diagnostics),
        },
        "diagnostics": diagnostics,
    }
    _write_json_atomic(args.diagnostics, diagnostic_report)
    return 0 if diagnostic_report["ok"] else 1


def _facts_extract(args: argparse.Namespace) -> int:
    diagnostics: list[dict[str, str]] = []
    try:
        raw, canonical = extract_facts(
            REPOSITORY_ROOT,
            lock_path=args.lock,
            source_dir=args.source_dir,
        )
        validate_instance_against_schema(
            raw,
            REPOSITORY_ROOT / "schemas" / "raw-raaml-facts.schema.json",
        )
        validate_instance_against_schema(
            canonical,
            REPOSITORY_ROOT / "schemas" / "canonical-raaml-facts.schema.json",
        )
        if args.check_determinism:
            raw_again, canonical_again = extract_facts(
                REPOSITORY_ROOT,
                lock_path=args.lock,
                source_dir=args.source_dir,
            )
            if serialize_facts(raw) != serialize_facts(raw_again):
                raise FactExtractionError(
                    "FACT_RAW_NONDETERMINISTIC",
                    "two raw extractions are not byte-identical",
                )
            if serialize_facts(canonical) != serialize_facts(canonical_again):
                raise FactExtractionError(
                    "FACT_CANONICAL_NONDETERMINISTIC",
                    "two canonical extractions are not byte-identical",
                )
        _write_json_atomic(args.raw_output, raw)
        _write_json_atomic(args.canonical_output, canonical)
    except FactExtractionError as error:
        diagnostics.append(
            {
                "severity": "error",
                "code": error.code,
                "message": str(error),
            }
        )
    except SchemaValidationError as error:
        diagnostics.append(
            {
                "severity": "error",
                "code": "FACT_SCHEMA_INVALID",
                "message": str(error),
            }
        )
    except OSError as error:
        diagnostics.append(
            {
                "severity": "error",
                "code": "FACT_WRITE_FAILED",
                "message": str(error),
            }
        )

    report = {
        "schemaVersion": "0.1.0",
        "command": "facts extract",
        "ok": not diagnostics,
        "summary": {
            "checked": 17 if not diagnostics else 0,
            "failed": len(diagnostics),
        },
        "diagnostics": diagnostics,
    }
    _write_json_atomic(args.diagnostics, report)
    if diagnostics:
        for diagnostic in diagnostics:
            print(
                f"{diagnostic['code']}: {diagnostic['message']}",
                file=sys.stderr,
            )
        return 1
    print(f"Raw facts: {args.raw_output}")
    print(f"Canonical facts: {args.canonical_output}")
    return 0


def _oracle_audit(args: argparse.Namespace) -> int:
    report = audit_corpus(
        REPOSITORY_ROOT,
        lock_path=args.lock,
        source_dir=args.source_dir,
    )
    _write_json_atomic(args.output, report)
    if report["ok"]:
        print(f"Corpus audit: {args.output}")
        return 0
    for diagnostic in report["diagnostics"]:
        if diagnostic["severity"] == "error":
            print(
                f"{diagnostic['code']}: {diagnostic['message']}",
                file=sys.stderr,
            )
    return 1


def _transformation_audit(args: argparse.Namespace) -> int:
    report = audit_transformation_matrix(
        REPOSITORY_ROOT,
        matrix_path=args.matrix,
        require_resolved=args.require_resolved,
    )
    _write_json_atomic(args.output, report)
    for diagnostic in report["diagnostics"]:
        if diagnostic["severity"] == "error":
            print(
                f"{diagnostic['code']}: {diagnostic['message']}",
                file=sys.stderr,
            )
    if report["ok"]:
        summary = report["summary"]
        print(
            f"Audited {summary['checked']} transformation row(s); "
            f"{summary['open']} open; report: {args.output}"
        )
        return 0
    return 1


def _transformation_surface(args: argparse.Namespace) -> int:
    try:
        report = analyze_corpus_transformation_surface(REPOSITORY_ROOT)
    except (OSError, ValueError) as error:
        print(
            f"TRANSFORMATION_SURFACE_INVALID: {error}",
            file=sys.stderr,
        )
        return 1
    _write_json_atomic(args.output, report)
    print(
        "Inventoried "
        f"{report['rootSysmlApplicationCount']} root-level SysML "
        f"application(s); report: {args.output}"
    )
    return 0


def _transformation_properties(args: argparse.Namespace) -> int:
    try:
        report = analyze_property_transformation_surface(REPOSITORY_ROOT)
    except (OSError, ValueError) as error:
        print(
            f"TRANSFORMATION_PROPERTIES_INVALID: {error}",
            file=sys.stderr,
        )
        return 1
    _write_json_atomic(args.output, report)
    print(
        f"Classified {report['propertyCount']} UML Properties; "
        f"report: {args.output}"
    )
    return 0


def _transformation_constraints(args: argparse.Namespace) -> int:
    try:
        report = analyze_constraint_transformation_surface(REPOSITORY_ROOT)
    except (OSError, ValueError) as error:
        print(
            f"TRANSFORMATION_CONSTRAINTS_INVALID: {error}",
            file=sys.stderr,
        )
        return 1
    _write_json_atomic(args.output, report)
    print(
        f"Classified {report['opaqueExpressionCount']} constraint "
        f"OpaqueExpressions; report: {args.output}"
    )
    return 0


def _validate_ocl_command(args: argparse.Namespace) -> int:
    if args.all:
        if args.input is not None:
            args.parser.error("validate-ocl accepts either INPUT or --all, not both")
        report = validate_ocl_corpus(REPOSITORY_ROOT)
        _write_json_atomic(args.diagnostics, report)
        if not report["ok"]:
            for diagnostic in report["diagnostics"]:
                if diagnostic["severity"] == "error":
                    print(
                        f"{diagnostic['code']}: {diagnostic['message']}",
                        file=sys.stderr,
                    )
            return 1
        print(
            f"Validated {report['summary']['checked']} OCL expression(s); "
            f"diagnostics: {args.diagnostics}"
        )
        return 0
    if args.input is None:
        args.parser.error("validate-ocl requires INPUT or --all")
    args.mode = "ocl"
    args.command_name = "validate-ocl"
    return _adapter_command(args)


def _publication_audit(args: argparse.Namespace) -> int:
    report = audit_repository(REPOSITORY_ROOT)
    _write_json_atomic(args.diagnostics, report)
    summary = report["summary"]
    if report["ok"]:
        print(
            "Publication audit passed: "
            f"{summary['currentTrackedPaths']} current path(s), "
            f"{summary['historicalPaths']} historical path(s); "
            f"diagnostics: {args.diagnostics}"
        )
        return 0
    for diagnostic in report["diagnostics"]:
        print(
            f"{diagnostic['code']}: {diagnostic['message']}",
            file=sys.stderr,
        )
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="raaml")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    sources = commands.add_parser("sources", help="manage pinned standards inputs")
    source_commands = sources.add_subparsers(dest="sources_command", required=True)

    verify = source_commands.add_parser(
        "verify",
        help="verify local source bytes against standards.lock.json",
    )
    verify.add_argument(
        "--lock",
        type=_path,
        default=REPOSITORY_ROOT / "standards.lock.json",
    )
    verify.add_argument(
        "--source-dir",
        type=_path,
        default=REPOSITORY_ROOT / "sources" / "cache",
    )
    verify.add_argument("--collection")
    verify.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "sources-verify.json",
    )
    verify.set_defaults(handler=_sources_verify)

    fetch = source_commands.add_parser(
        "fetch",
        help="explicitly download every locked artifact and verify it",
    )
    fetch.add_argument(
        "--lock",
        type=_path,
        default=REPOSITORY_ROOT / "standards.lock.json",
    )
    fetch.add_argument(
        "--source-dir",
        type=_path,
        default=REPOSITORY_ROOT / "sources" / "cache",
    )
    fetch.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "sources-fetch.json",
    )
    fetch.set_defaults(handler=_sources_fetch)

    schemas = commands.add_parser("schemas", help="validate project schemas")
    schema_commands = schemas.add_subparsers(dest="schemas_command", required=True)
    validate = schema_commands.add_parser(
        "validate",
        help="validate schemas and schema-governed JSON artifacts",
    )
    validate.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "schemas-validate.json",
    )
    validate.set_defaults(handler=_schemas_validate)

    facts = commands.add_parser(
        "facts",
        help="extract and canonicalize the locked RAAML preservation facts",
    )
    fact_commands = facts.add_subparsers(dest="facts_command", required=True)
    extract = fact_commands.add_parser(
        "extract",
        help="extract raw and canonical facts from the locked corpus",
    )
    extract.add_argument(
        "--all",
        action="store_true",
        required=True,
        help="extract all 17 locked RAAML definition artifacts",
    )
    extract.add_argument(
        "--check-determinism",
        action="store_true",
        help="extract twice and require byte-identical raw and canonical output",
    )
    extract.add_argument(
        "--lock",
        type=_path,
        default=REPOSITORY_ROOT / "standards.lock.json",
    )
    extract.add_argument(
        "--source-dir",
        type=_path,
        default=REPOSITORY_ROOT / "sources" / "cache",
    )
    extract.add_argument(
        "--raw-output",
        type=_path,
        default=REPOSITORY_ROOT / "reports" / "facts" / "raw-raaml-facts.json",
    )
    extract.add_argument(
        "--canonical-output",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "facts"
        / "canonical-raaml-facts.json",
    )
    extract.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "facts-extract.json",
    )
    extract.set_defaults(handler=_facts_extract)

    forward = commands.add_parser(
        "forward",
        help="map RAAML facts to SysML v2 plus preservation manifests",
    )
    forward_scope = forward.add_mutually_exclusive_group(required=True)
    forward_scope.add_argument(
        "--milestone-3",
        action="store_true",
        help="generate the frozen Milestone 3 vertical slice",
    )
    forward_scope.add_argument(
        "--milestone-4",
        action="store_true",
        help="generate the complete 17-file Milestone 4 v2 corpus",
    )
    forward.add_argument(
        "--output-dir",
        type=_path,
        default=None,
    )
    forward.add_argument(
        "--diagnostics",
        type=_path,
        default=None,
    )
    forward.set_defaults(handler=_forward_command)

    reverse = commands.add_parser(
        "reverse",
        help="reconstruct v1 XMI from a preservation manifest",
    )
    reverse_input = reverse.add_mutually_exclusive_group(required=True)
    reverse_input.add_argument(
        "--manifest",
        type=_path,
        help="Milestone 3 single preservation manifest",
    )
    reverse_input.add_argument(
        "--manifest-dir",
        type=_path,
        help="directory containing all 17 Milestone 4 preservation manifests",
    )
    reverse.add_argument("--v2", type=_path, required=True)
    reverse.add_argument(
        "--output-dir",
        type=_path,
        default=REPOSITORY_ROOT / "generated" / "milestone-3" / "reconstructed",
    )
    reverse.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "reverse-milestone-3.json",
    )
    reverse.set_defaults(handler=_reverse_command)

    compare = commands.add_parser(
        "compare",
        help="compare source and reconstructed canonical facts",
    )
    compare_scope = compare.add_mutually_exclusive_group(required=True)
    compare_scope.add_argument(
        "--manifest",
        type=_path,
        help="compare the Milestone 3 manifest slice",
    )
    compare_scope.add_argument(
        "--full-corpus",
        action="store_true",
        help="compare all 17 reconstructed artifacts with the locked sources",
    )
    compare.add_argument("--reconstructed-dir", type=_path, required=True)
    compare.add_argument(
        "--output",
        type=_path,
        default=None,
    )
    compare.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "compare-milestone-3.json",
    )
    compare.set_defaults(handler=_compare_command)

    oracle = commands.add_parser(
        "oracle",
        help="audit the corpus independently of production fact extraction",
    )
    oracle_commands = oracle.add_subparsers(
        dest="oracle_command",
        required=True,
    )
    audit = oracle_commands.add_parser(
        "audit",
        help="count and check preservation facts directly from XML events",
    )
    audit.add_argument(
        "--all",
        action="store_true",
        required=True,
        help="audit all 17 locked RAAML definition artifacts",
    )
    audit.add_argument(
        "--lock",
        type=_path,
        default=REPOSITORY_ROOT / "standards.lock.json",
    )
    audit.add_argument(
        "--source-dir",
        type=_path,
        default=REPOSITORY_ROOT / "sources" / "cache",
    )
    audit.add_argument(
        "--output",
        type=_path,
        default=REPOSITORY_ROOT / "reports" / "oracle" / "corpus-audit.json",
    )
    audit.set_defaults(handler=_oracle_audit)

    transformation = commands.add_parser(
        "transformation",
        help="audit the comparison with the official v1-to-v2 transformation",
    )
    transformation_commands = transformation.add_subparsers(
        dest="transformation_command",
        required=True,
    )
    transformation_audit = transformation_commands.add_parser(
        "audit",
        help="validate matrix citations against the pinned transformation model",
    )
    transformation_audit.add_argument(
        "--matrix",
        type=_path,
        default=REPOSITORY_ROOT
        / "analysis"
        / "transformation-matrix-v0.1.json",
    )
    transformation_audit.add_argument(
        "--require-resolved",
        action="store_true",
        help="fail when any matrix row remains classified open",
    )
    transformation_audit.add_argument(
        "--output",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "transformation"
        / "matrix-audit.json",
    )
    transformation_audit.set_defaults(handler=_transformation_audit)
    transformation_surface = transformation_commands.add_parser(
        "surface",
        help="inventory specialized SysML v1 mappings selected by the corpus",
    )
    transformation_surface.add_argument(
        "--output",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "transformation"
        / "corpus-surface.json",
    )
    transformation_surface.set_defaults(handler=_transformation_surface)
    transformation_properties = transformation_commands.add_parser(
        "properties",
        help="classify corpus Properties using the official rule filters",
    )
    transformation_properties.add_argument(
        "--output",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "transformation"
        / "property-surface.json",
    )
    transformation_properties.set_defaults(
        handler=_transformation_properties
    )
    transformation_constraints = transformation_commands.add_parser(
        "constraints",
        help="classify constraint expressions against the official rules",
    )
    transformation_constraints.add_argument(
        "--output",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "transformation"
        / "constraint-surface.json",
    )
    transformation_constraints.set_defaults(
        handler=_transformation_constraints
    )

    publication = commands.add_parser(
        "publication",
        help="audit the conservative public-repository boundary",
    )
    publication_commands = publication.add_subparsers(
        dest="publication_command",
        required=True,
    )
    publication_audit = publication_commands.add_parser(
        "audit",
        help="reject tracked or historical generated and third-party material",
    )
    publication_audit.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "publication-audit.json",
    )
    publication_audit.set_defaults(handler=_publication_audit)

    tests = commands.add_parser("tests", help="run project tests")
    test_commands = tests.add_subparsers(dest="tests_command", required=True)
    unit = test_commands.add_parser("unit", help="run dependency-free unit tests")
    unit.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "tests-unit.json",
    )
    unit.set_defaults(handler=_tests_unit)
    milestone_zero = test_commands.add_parser(
        "milestone-0",
        help="run paired foundation smoke tests through every pinned adapter",
    )
    milestone_zero.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "tests-milestone-0.json",
    )
    milestone_zero.set_defaults(handler=_tests_milestone_zero)
    milestone_one = test_commands.add_parser(
        "milestone-1",
        help="run extraction, oracle, determinism, and corpus OCL gates",
    )
    milestone_one.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "tests-milestone-1.json",
    )
    milestone_one.set_defaults(handler=_tests_milestone_one)
    milestone_three = test_commands.add_parser(
        "milestone-3",
        help="run the complete thin vertical-slice round trip",
    )
    milestone_three.add_argument(
        "--output",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "conformance"
        / "milestone-3.json",
    )
    milestone_three.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "tests-milestone-3.json",
    )
    milestone_three.set_defaults(handler=_tests_milestone_three)
    milestone_four = test_commands.add_parser(
        "milestone-4",
        help="generate and validate the complete 17-file SysML v2 corpus",
    )
    milestone_four.add_argument(
        "--output",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "conformance"
        / "milestone-4.json",
    )
    milestone_four.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "tests-milestone-4.json",
    )
    milestone_four.set_defaults(handler=_tests_milestone_four)
    milestone_five = test_commands.add_parser(
        "milestone-5",
        help="reconstruct and validate all 17 SysML v1 artifacts",
    )
    milestone_five.add_argument(
        "--output",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "conformance"
        / "milestone-5.json",
    )
    milestone_five.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "tests-milestone-5.json",
    )
    milestone_five.set_defaults(handler=_tests_milestone_five)
    milestone_six = test_commands.add_parser(
        "milestone-6",
        help="run full-corpus equality, both validators, and adversarial cases",
    )
    milestone_six.add_argument(
        "--output",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "conformance"
        / "milestone-6.json",
    )
    milestone_six.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "tests-milestone-6.json",
    )
    milestone_six.add_argument(
        "--comparison-output",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "conformance"
        / "milestone-6-comparison.json",
        help=(
            "write source/reconstructed facts, counts, and exact differences"
        ),
    )
    milestone_six.set_defaults(handler=_tests_milestone_six)

    tooling = commands.add_parser("tooling", help="build pinned tool adapters")
    tooling_commands = tooling.add_subparsers(dest="tooling_command", required=True)
    build = tooling_commands.add_parser(
        "build-adapters",
        help="compile the Java adapters against the pinned distribution",
    )
    build.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "tooling-build-adapters.json",
    )
    build.set_defaults(handler=_build_adapters)
    bootstrap = tooling_commands.add_parser(
        "bootstrap",
        help="extract verified local tool archives and build adapters",
    )
    bootstrap.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "tooling-bootstrap.json",
    )
    bootstrap.set_defaults(handler=_bootstrap_tooling)

    adapter_specs = (
        ("validate-v2", "v2"),
        ("validate-v1", "v1"),
    )
    for command_name, mode in adapter_specs:
        command = commands.add_parser(command_name)
        command.add_argument("input", type=_path)
        command.add_argument(
            "--diagnostics",
            type=_path,
            default=REPOSITORY_ROOT
            / "reports"
            / "diagnostics"
            / f"{command_name}.json",
        )
        command.set_defaults(
            handler=_adapter_command,
            mode=mode,
            command_name=command_name,
        )
    validate_ocl = commands.add_parser("validate-ocl")
    validate_ocl.add_argument("input", type=_path, nargs="?")
    validate_ocl.add_argument(
        "--all",
        action="store_true",
        help="parse and resolve every OCL expression in the locked corpus",
    )
    validate_ocl.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "validate-ocl.json",
    )
    validate_ocl.set_defaults(
        handler=_validate_ocl_command,
        parser=validate_ocl,
    )
    reproduce = commands.add_parser(
        "reproduce",
        help="create a deterministic validation or candidate package",
    )
    reproduce.add_argument(
        "--output-dir",
        type=_path,
        default=REPOSITORY_ROOT / "generated" / "release-candidate",
    )
    reproduce.add_argument("--container-digest", required=True)
    reproduce.add_argument(
        "--release-tag",
        required=True,
        help=(
            "candidate tag or explicit development identifier recorded in "
            "the release report"
        ),
    )
    reproduce.add_argument(
        "--clean",
        action="store_true",
        help="fail unless the source tree is clean",
    )
    reproduce.add_argument(
        "--git-commit",
        help="commit identity for a packaged source tree without .git",
    )
    reproduce.add_argument(
        "--source-state",
        choices=("clean", "dirty"),
        help="source state for a packaged source tree without .git",
    )
    reproduce.add_argument(
        "--diagnostics",
        type=_path,
        default=REPOSITORY_ROOT
        / "reports"
        / "diagnostics"
        / "reproduce.json",
    )
    reproduce.set_defaults(handler=_reproduce)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)
