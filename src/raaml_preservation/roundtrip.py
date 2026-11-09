from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable
import xml.etree.ElementTree as ET

from .facts import (
    count_facts,
    extract_artifact_set,
    extract_facts,
    serialize_facts,
)
from .sources import load_lock
from .v2 import NativeModel


SCHEMA_VERSION = "0.1.0"
MANIFEST_SCHEMA_VERSION = "0.2.0"
SLICE_ID = "milestone-3-core-general-stpa"
FULL_CORPUS_ID = "milestone-4-full-corpus"
FULL_CORPUS_V2_FILENAME = "raaml-full-corpus.sysml"
FULL_ARTIFACTS = {
    "CoreRAAML.xmi",
    "CoreRAAMLLib.xmi",
    "GeneralRAAML.xmi",
    "GeneralRAAMLLib.xmi",
}
STPA_PROFILE_NAMES = {"ControlStructure", "Controller", "ControlAction"}
STPA_LIBRARY_NAMES = {"Loss"}
XMI = "http://www.omg.org/spec/XMI/20131001"
UML = "http://www.omg.org/spec/UML/20161101"
MOFEXT = "http://www.omg.org/spec/MOF/20131001"
XMI_ID = f"{{{XMI}}}id"
XMI_TYPE = f"{{{XMI}}}type"
XMI_IDREF = f"{{{XMI}}}idref"
SAFE_NAME = re.compile(r"[^A-Za-z0-9_]")
HashProvider = Callable[[bytes], str]

ET.register_namespace("xmi", XMI)
ET.register_namespace("uml", UML)
ET.register_namespace("mofext", MOFEXT)


class RoundTripError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def select_milestone_three_slice(canonical: dict[str, Any]) -> dict[str, Any]:
    selected = copy.deepcopy(canonical)
    selected["artifacts"] = []
    for artifact in canonical["artifacts"]:
        filename = artifact["filename"]
        if filename in FULL_ARTIFACTS:
            selected["artifacts"].append(copy.deepcopy(artifact))
            continue
        if filename == "STPA.xmi":
            item = copy.deepcopy(artifact)
            item["declarations"] = [
                declaration
                for declaration in item["declarations"]
                if declaration["name"] in STPA_PROFILE_NAMES
            ]
            selected["artifacts"].append(item)
            continue
        if filename == "STPALib.xmi":
            item = copy.deepcopy(artifact)
            item["declarations"] = [
                declaration
                for declaration in item["declarations"]
                if declaration["name"] in STPA_LIBRARY_NAMES
            ]
            kept_ids = {item["declarations"][0]["id"]}
            item["applications"] = [
                application
                for application in item["applications"]
                if application["target"]["target"] in kept_ids
            ]
            selected["artifacts"].append(item)
    selected["artifacts"].sort(key=lambda item: item["artifactId"])
    _require_slice_coverage(selected)
    _require_reference_closure(selected)
    return selected


def create_manifest(canonical_slice: dict[str, Any]) -> dict[str, Any]:
    v2_bytes = render_v2(canonical_slice).encode("utf-8")
    payload = {
        "sliceId": SLICE_ID,
        "v2Sha256": hashlib.sha256(v2_bytes).hexdigest(),
        "nativeTargets": _native_targets(canonical_slice),
        "canonicalFacts": canonical_slice,
    }
    return {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "documentKind": "raaml-preservation-manifest",
        "payloadSha256": hashlib.sha256(canonical_json(payload)).hexdigest(),
        "payload": payload,
    }


def create_full_corpus_manifest(
    canonical: dict[str, Any],
    artifact: dict[str, Any],
    v2_bytes: bytes,
) -> dict[str, Any]:
    artifact_facts = copy.deepcopy(canonical)
    artifact_facts["artifacts"] = [copy.deepcopy(artifact)]
    payload = {
        "scopeId": FULL_CORPUS_ID,
        "artifactId": artifact["artifactId"],
        "sourceFilename": artifact["filename"],
        "sourceSha256": artifact["sha256"],
        "v2Filename": FULL_CORPUS_V2_FILENAME,
        "v2Sha256": hashlib.sha256(v2_bytes).hexdigest(),
        "nativeTargets": _native_targets(
            artifact_facts,
            root_package="RaamlFullCorpus",
        ),
        "canonicalFacts": artifact_facts,
    }
    return {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "documentKind": "raaml-preservation-manifest",
        "payloadSha256": hashlib.sha256(canonical_json(payload)).hexdigest(),
        "payload": payload,
    }


def verify_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schemaVersion") != MANIFEST_SCHEMA_VERSION:
        raise RoundTripError("MANIFEST_VERSION", "unsupported manifest version")
    if manifest.get("documentKind") != "raaml-preservation-manifest":
        raise RoundTripError("MANIFEST_KIND", "unexpected manifest document kind")
    payload = manifest.get("payload")
    if not isinstance(payload, dict):
        raise RoundTripError("MANIFEST_PAYLOAD", "manifest payload is missing")
    expected = hashlib.sha256(canonical_json(payload)).hexdigest()
    if manifest.get("payloadSha256") != expected:
        raise RoundTripError(
            "MANIFEST_DIGEST",
            "manifest payload does not match payloadSha256",
        )
    if payload.get("sliceId") != SLICE_ID:
        raise RoundTripError("MANIFEST_SLICE", "unexpected slice identity")
    facts = payload.get("canonicalFacts")
    if not isinstance(facts, dict):
        raise RoundTripError("MANIFEST_FACTS", "canonical facts are missing")
    _require_slice_coverage(facts)
    _require_reference_closure(facts)
    return facts


def verify_full_corpus_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schemaVersion") != MANIFEST_SCHEMA_VERSION:
        raise RoundTripError("MANIFEST_VERSION", "unsupported manifest version")
    if manifest.get("documentKind") != "raaml-preservation-manifest":
        raise RoundTripError("MANIFEST_KIND", "unexpected manifest document kind")
    payload = manifest.get("payload")
    if not isinstance(payload, dict):
        raise RoundTripError("MANIFEST_PAYLOAD", "manifest payload is missing")
    expected = hashlib.sha256(canonical_json(payload)).hexdigest()
    if manifest.get("payloadSha256") != expected:
        raise RoundTripError(
            "MANIFEST_DIGEST",
            "manifest payload does not match payloadSha256",
        )
    if payload.get("scopeId") != FULL_CORPUS_ID:
        raise RoundTripError("MANIFEST_SCOPE", "unexpected full-corpus scope")
    if payload.get("v2Filename") != FULL_CORPUS_V2_FILENAME:
        raise RoundTripError("MANIFEST_V2_FILENAME", "unexpected SysML v2 filename")
    facts = payload.get("canonicalFacts")
    if not isinstance(facts, dict):
        raise RoundTripError("MANIFEST_FACTS", "canonical facts are missing")
    artifacts = facts.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1:
        raise RoundTripError(
            "MANIFEST_ARTIFACT_COUNT",
            "full-corpus manifest must contain exactly one source artifact",
        )
    artifact = artifacts[0]
    if payload.get("artifactId") != artifact.get("artifactId"):
        raise RoundTripError("MANIFEST_ARTIFACT_ID", "artifact identity mismatch")
    if payload.get("sourceFilename") != artifact.get("filename"):
        raise RoundTripError("MANIFEST_SOURCE_FILENAME", "source filename mismatch")
    if payload.get("sourceSha256") != artifact.get("sha256"):
        raise RoundTripError("MANIFEST_SOURCE_DIGEST", "source digest mismatch")
    return facts


def verify_native_targets(manifest: dict[str, Any], v2_path: Path) -> None:
    verify_manifest(manifest)
    _verify_native_targets_payload(manifest["payload"], v2_path)


def _verify_native_targets_payload(
    payload: dict[str, Any],
    v2_path: Path,
) -> None:
    try:
        v2_bytes = v2_path.read_bytes()
        text = v2_bytes.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise RoundTripError("V2_READ", str(error)) from error
    if hashlib.sha256(v2_bytes).hexdigest() != payload.get("v2Sha256"):
        raise RoundTripError(
            "V2_DIGEST",
            "SysML v2 model does not match the manifest v2Sha256",
        )
    targets = payload.get("nativeTargets")
    if not isinstance(targets, list):
        raise RoundTripError("MANIFEST_NATIVE_TARGETS", "nativeTargets is missing")
    if targets and all("qualifiedName" in target for target in targets):
        _verify_qualified_native_targets(targets, text)
        return
    expected_counts: dict[str, int] = {}
    for target in targets:
        line = target.get("declaration")
        if not isinstance(line, str) or not line:
            raise RoundTripError(
                "MANIFEST_NATIVE_TARGET",
                "native target declaration is invalid",
            )
        expected_counts[line] = expected_counts.get(line, 0) + 1
    actual_lines = [line.strip() for line in text.splitlines()]
    missing = [
        line
        for line, count in expected_counts.items()
        if actual_lines.count(line) != count
    ]
    if missing:
        raise RoundTripError(
            "V2_TARGET_MISSING",
            f"native v2 target count mismatch: {missing[:3]}",
        )


def _verify_qualified_native_targets(
    targets: list[dict[str, Any]],
    text: str,
) -> None:
    missing = []
    for target in targets:
        qualified_name = target.get("qualifiedName")
        carrier = target.get("carrier")
        if not isinstance(qualified_name, str) or not isinstance(carrier, str):
            raise RoundTripError(
                "MANIFEST_NATIVE_TARGET",
                "qualified native target is invalid",
            )
        parts = qualified_name.split("::")
        if len(parts) != 3:
            raise RoundTripError(
                "MANIFEST_NATIVE_TARGET",
                f"invalid qualified native target: {qualified_name}",
            )
        root, package, name = parts
        if not text.startswith(f"package {root} {{\n"):
            missing.append(qualified_name)
            continue
        marker = f"    package {package} {{\n"
        start = text.find(marker)
        if start < 0:
            missing.append(qualified_name)
            continue
        body_start = start + len(marker)
        next_package = text.find("\n    package ", body_start)
        root_end = text.rfind("\n}")
        body_end = next_package if next_package >= 0 else root_end
        declaration = re.compile(
            rf"^        (?:abstract )?{re.escape(carrier)} {re.escape(name)}(?:\s|;|\{{)",
            re.MULTILINE,
        )
        if len(declaration.findall(text[body_start:body_end])) != 1:
            missing.append(qualified_name)
    if missing:
        raise RoundTripError(
            "V2_TARGET_MISSING",
            f"qualified v2 target mismatch: {missing[:3]}",
        )


def forward_slice(repository_root: Path, output_dir: Path) -> dict[str, Any]:
    _, canonical = extract_facts(repository_root)
    canonical_slice = select_milestone_three_slice(canonical)
    manifest = create_manifest(canonical_slice)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "preservation-manifest.json"
    v2_path = output_dir / "raaml-milestone-3.sysml"
    manifest_path.write_bytes(
        json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    v2_path.write_text(render_v2(canonical_slice), encoding="utf-8", newline="\n")
    return {
        "manifest": manifest_path,
        "v2": v2_path,
        "facts": canonical_slice,
    }


def forward_full_corpus(repository_root: Path, output_dir: Path) -> dict[str, Any]:
    _, canonical = extract_facts(repository_root)
    _require_full_corpus_coverage(canonical)
    _require_reference_closure(canonical)
    v2_text = render_full_corpus_v2(canonical)
    v2_bytes = v2_text.encode("utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    v2_path = output_dir / FULL_CORPUS_V2_FILENAME
    v2_path.write_bytes(v2_bytes)
    manifest_dir = output_dir / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_paths = []
    for artifact in canonical["artifacts"]:
        manifest = create_full_corpus_manifest(canonical, artifact, v2_bytes)
        manifest_path = (
            manifest_dir
            / f"{Path(artifact['filename']).stem}.preservation.json"
        )
        manifest_path.write_bytes(
            json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        )
        manifest_paths.append(manifest_path)
    return {
        "manifests": manifest_paths,
        "v2": v2_path,
        "facts": canonical,
    }


def reverse_slice(
    manifest_path: Path,
    v2_path: Path,
    output_dir: Path,
) -> list[Path]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RoundTripError("MANIFEST_READ", str(error)) from error
    facts = verify_manifest(manifest)
    verify_native_targets(manifest, v2_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for artifact in facts["artifacts"]:
        path = output_dir / artifact["filename"]
        path.write_bytes(render_v1_artifact(facts, artifact))
        paths.append(path)
    return paths


def reverse_full_corpus(
    manifest_dir: Path,
    v2_path: Path,
    output_dir: Path,
    *,
    hash_provider: HashProvider | None = None,
) -> list[Path]:
    if manifest_dir.is_symlink() or not manifest_dir.is_dir():
        raise RoundTripError(
            "MANIFEST_DIRECTORY",
            "manifest directory does not exist or is not a directory",
        )
    manifest_paths = sorted(manifest_dir.glob("*.preservation.json"))
    if any(path.is_symlink() or not path.is_file() for path in manifest_paths):
        raise RoundTripError(
            "MANIFEST_FILE_UNSAFE",
            "manifest inputs must be regular files, not symbolic links",
        )

    locked = load_lock(Path(__file__).resolve().parents[2] / "standards.lock.json")
    expected = {
        artifact["filename"]: artifact
        for artifact in locked["artifacts"]
        if artifact["collection"] == "raaml-1.1-definitions"
    }
    if len(manifest_paths) != len(expected):
        raise RoundTripError(
            "FULL_CORPUS_MANIFEST_COUNT",
            f"expected {len(expected)} manifests, got {len(manifest_paths)}",
        )

    combined: dict[str, Any] | None = None
    shared_facts: bytes | None = None
    seen: set[str] = set()
    v2_digest: str | None = None
    for manifest_path in manifest_paths:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RoundTripError("MANIFEST_READ", str(error)) from error
        facts = verify_full_corpus_manifest(manifest)
        payload = manifest["payload"]
        filename = payload["sourceFilename"]
        if filename in seen:
            raise RoundTripError(
                "FULL_CORPUS_MANIFEST_DUPLICATE",
                f"duplicate manifest for {filename}",
            )
        seen.add(filename)
        locked_artifact = expected.get(filename)
        if locked_artifact is None:
            raise RoundTripError(
                "FULL_CORPUS_MANIFEST_UNKNOWN",
                f"manifest is not for a locked RAAML artifact: {filename}",
            )
        if (
            payload["artifactId"] != locked_artifact["id"]
            or payload["sourceSha256"] != locked_artifact["sha256"]
        ):
            raise RoundTripError(
                "FULL_CORPUS_MANIFEST_LOCK",
                f"manifest identity does not match standards.lock.json: {filename}",
            )
        current_v2_digest = payload.get("v2Sha256")
        if v2_digest is None:
            v2_digest = current_v2_digest
        elif current_v2_digest != v2_digest:
            raise RoundTripError(
                "FULL_CORPUS_V2_INCONSISTENT",
                "manifests do not identify the same SysML v2 model",
            )
        _verify_native_targets_payload(payload, v2_path)

        common = copy.deepcopy(facts)
        artifact = common["artifacts"].pop()
        serialized_common = canonical_json(common)
        if shared_facts is None:
            shared_facts = serialized_common
            combined = common
            combined["artifacts"] = []
        elif serialized_common != shared_facts:
            raise RoundTripError(
                "FULL_CORPUS_FACTS_INCONSISTENT",
                "manifests disagree on shared canonical-fact metadata",
            )
        assert combined is not None
        combined["artifacts"].append(artifact)

    missing = sorted(set(expected) - seen)
    if missing:
        raise RoundTripError(
            "FULL_CORPUS_MANIFEST_MISSING",
            f"missing manifest(s): {missing}",
        )
    assert combined is not None
    combined["artifacts"].sort(key=lambda item: item["artifactId"])
    _require_full_corpus_coverage(combined)
    _require_reference_closure(combined)

    rendered = [
        (
            artifact["filename"],
            render_v1_artifact(
                combined,
                artifact,
                hash_provider=hash_provider,
            ),
        )
        for artifact in combined["artifacts"]
    ]
    if output_dir.is_symlink():
        raise RoundTripError(
            "OUTPUT_DIRECTORY_UNSAFE",
            "output directory must not be a symbolic link",
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for filename, payload in rendered:
        path = output_dir / filename
        path.write_bytes(payload)
        paths.append(path)
    return paths


def compare_reconstructed(
    repository_root: Path,
    manifest_path: Path,
    reconstructed_dir: Path,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = verify_manifest(manifest)
    descriptors = [
        {
            "id": artifact["artifactId"],
            "filename": artifact["filename"],
            "sha256": artifact["sha256"],
        }
        for artifact in expected["artifacts"]
    ]
    _, actual = extract_artifact_set(repository_root, descriptors, reconstructed_dir)
    differences = _differences(expected, actual)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "documentKind": "raaml-roundtrip-report",
        "sliceId": SLICE_ID,
        "ok": not differences,
        "summary": {
            "artifacts": len(expected["artifacts"]),
            "sourceFactsSha256": hashlib.sha256(serialize_facts(expected)).hexdigest(),
            "reconstructedFactsSha256": hashlib.sha256(
                serialize_facts(actual)
            ).hexdigest(),
            "differences": len(differences),
        },
        "differences": differences,
        "sourceFacts": expected,
        "reconstructedFacts": actual,
    }


def compare_full_corpus(
    repository_root: Path,
    reconstructed_dir: Path,
) -> dict[str, Any]:
    _, expected = extract_facts(repository_root)
    descriptors = [
        {
            "id": artifact["artifactId"],
            "filename": artifact["filename"],
            "sha256": artifact["sha256"],
        }
        for artifact in expected["artifacts"]
    ]
    _, actual = extract_artifact_set(
        repository_root,
        descriptors,
        reconstructed_dir,
    )
    differences = _differences(expected, actual)
    expected_by_id = {
        artifact["artifactId"]: artifact
        for artifact in expected["artifacts"]
    }
    actual_by_id = {
        artifact["artifactId"]: artifact
        for artifact in actual["artifacts"]
    }
    per_artifact = []
    for artifact_id in sorted(set(expected_by_id) | set(actual_by_id)):
        source = expected_by_id.get(artifact_id)
        reconstructed = actual_by_id.get(artifact_id)
        artifact_differences = _differences(source, reconstructed)
        artifact = source or reconstructed
        assert artifact is not None
        per_artifact.append(
            {
                "artifactId": artifact_id,
                "filename": artifact["filename"],
                "sourceCounts": (
                    _single_artifact_counts(expected, source)
                    if source is not None
                    else {}
                ),
                "reconstructedCounts": (
                    _single_artifact_counts(actual, reconstructed)
                    if reconstructed is not None
                    else {}
                ),
                "differences": len(artifact_differences),
            }
        )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "documentKind": "raaml-full-corpus-comparison-report",
        "corpusId": expected["corpus"],
        "ok": not differences,
        "summary": {
            "artifacts": len(expected["artifacts"]),
            "sourceFactsSha256": hashlib.sha256(
                serialize_facts(expected)
            ).hexdigest(),
            "reconstructedFactsSha256": hashlib.sha256(
                serialize_facts(actual)
            ).hexdigest(),
            "differences": len(differences),
        },
        "sourceCounts": count_facts(expected),
        "reconstructedCounts": count_facts(actual),
        "perArtifact": per_artifact,
        "differences": differences,
        "sourceFacts": expected,
        "reconstructedFacts": actual,
    }


def _single_artifact_counts(
    corpus: dict[str, Any],
    artifact: dict[str, Any],
) -> dict[str, int]:
    scoped = {
        "schemaVersion": corpus["schemaVersion"],
        "documentKind": corpus["documentKind"],
        "corpus": corpus["corpus"],
        "artifacts": [artifact],
    }
    return count_facts(scoped)


def render_v2(facts: dict[str, Any]) -> str:
    return _render_v2_model(
        facts,
        root_package="RaamlMilestone3",
        include_preservation_metadata=False,
        include_scalar_import=False,
    )


def render_full_corpus_v2(facts: dict[str, Any]) -> str:
    try:
        return NativeModel(facts).render()
    except ValueError as error:
        raise RoundTripError("NATIVE_MAPPING", str(error)) from error


def _render_v2_model(
    facts: dict[str, Any],
    *,
    root_package: str,
    include_preservation_metadata: bool,
    include_scalar_import: bool,
) -> str:
    lines = [
        f"package {root_package} {{",
    ]
    if include_scalar_import:
        lines.append("    private import ScalarValues::*;")
    lines.append("    private occurrence def PreservedAssociationEnd;")
    if include_preservation_metadata:
        lines.extend(
            [
                "    metadata def Raaml_BaseAnnotation;",
                (
                    "    metadata def Raaml_LibraryClass "
                    ":> Raaml_BaseAnnotation;"
                ),
                (
                    "    metadata def Raaml_AssociationClass "
                    ":> Raaml_BaseAnnotation;"
                ),
                (
                    "    metadata def Raaml_LibraryAssociation "
                    ":> Raaml_BaseAnnotation;"
                ),
            ]
        )
    for artifact in facts["artifacts"]:
        package_name = _identifier(Path(artifact["filename"]).stem)
        lines.append(f"    package {package_name} {{")
        for declaration in artifact["declarations"]:
            name = _identifier(declaration["name"] or declaration["id"])
            kind = declaration["kind"]
            if kind == "Stereotype":
                specialization = (
                    " :> RaamlFullCorpus::Raaml_BaseAnnotation"
                    if include_preservation_metadata
                    else ""
                )
                lines.append(f"        metadata def {name}{specialization};")
            elif kind == "Class":
                if include_preservation_metadata:
                    lines.append(
                        "        #RaamlFullCorpus::Raaml_LibraryClass"
                    )
                lines.append(f"        occurrence def {name};")
            elif kind in {"Association", "AssociationClass"}:
                if include_preservation_metadata:
                    marker = (
                        "Raaml_AssociationClass"
                        if kind == "AssociationClass"
                        else "Raaml_LibraryAssociation"
                    )
                    lines.append(f"        #RaamlFullCorpus::{marker}")
                lines.append(f"        connection def {name} {{")
                for end_name, end_type in _association_ends(
                    facts, artifact, declaration
                ):
                    lines.append(f"            end {end_name} : {end_type};")
                lines.append("        }")
            elif kind == "Enumeration":
                lines.append(f"        enum def {name} {{")
                for literal in declaration["literals"]:
                    lines.append(f"            {_identifier(literal['name'])};")
                lines.append("        }")
            for constraint in declaration["constraints"]:
                constraint_name = _identifier(
                    f"{name}_{constraint['name'] or 'Constraint'}"
                )
                lines.append(f"        constraint def {constraint_name};")
        lines.append("    }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _native_targets(
    facts: dict[str, Any],
    *,
    root_package: str | None = None,
) -> list[dict[str, str]]:
    if root_package == "RaamlFullCorpus":
        return NativeModel(facts).targets()
    targets = []
    for artifact in facts["artifacts"]:
        package_name = _identifier(Path(artifact["filename"]).stem)
        for declaration in artifact["declarations"]:
            name = _identifier(declaration["name"] or declaration["id"])
            carrier = {
                "Stereotype": "metadata def",
                "Class": "occurrence def",
                "Association": "connection def",
                "AssociationClass": "connection def",
                "Enumeration": "enum def",
            }[declaration["kind"]]
            terminator = " {" if carrier in {"connection def", "enum def"} else ";"
            target = {
                "canonicalId": declaration["id"],
                "carrier": carrier,
                "declaration": f"{carrier} {name}{terminator}",
            }
            if root_package is not None:
                target["qualifiedName"] = (
                    f"{root_package}::{package_name}::{name}"
                )
            targets.append(target)
            for constraint in declaration["constraints"]:
                constraint_name = _identifier(
                    f"{name}_{constraint['name'] or 'Constraint'}"
                )
                target = {
                    "canonicalId": constraint["id"],
                    "carrier": "constraint def",
                    "declaration": f"constraint def {constraint_name};",
                }
                if root_package is not None:
                    target["qualifiedName"] = (
                        f"{root_package}::{package_name}::{constraint_name}"
                    )
                targets.append(target)
    return sorted(targets, key=lambda item: item["canonicalId"])


def _association_ends(
    facts: dict[str, Any],
    current_artifact: dict[str, Any],
    declaration: dict[str, Any],
) -> list[tuple[str, str]]:
    properties: dict[str, dict[str, Any]] = {}
    declarations: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for artifact in facts["artifacts"]:
        for candidate in artifact["declarations"]:
            declarations[candidate["id"]] = (artifact, candidate)
            for prop in candidate["properties"] + candidate["ownedEnds"]:
                properties[prop["id"]] = prop
    result = []
    used_names: set[str] = set()
    for ordinal, reference in enumerate(declaration["memberEnds"], start=1):
        prop = properties.get(reference["target"])
        if prop is None or prop["type"] is None:
            end_name = f"end{ordinal}"
            end_type = "PreservedAssociationEnd"
        else:
            end_name = _identifier(f"end_{prop['name'] or ordinal}")
            target = declarations.get(prop["type"]["target"])
            if target is None:
                end_type = "PreservedAssociationEnd"
            else:
                target_artifact, target_declaration = target
                target_name = _identifier(
                    target_declaration["name"] or target_declaration["id"]
                )
                if target_artifact["artifactId"] == current_artifact["artifactId"]:
                    end_type = target_name
                else:
                    end_type = (
                        f"{_identifier(Path(target_artifact['filename']).stem)}"
                        f"::{target_name}"
                    )
        if end_name in used_names:
            end_name = f"{end_name}{ordinal}"
        used_names.add(end_name)
        result.append((end_name, end_type))
    while len(result) < 2:
        ordinal = len(result) + 1
        result.append((f"end{ordinal}", "PreservedAssociationEnd"))
    return result


def render_v1_artifact(
    facts: dict[str, Any],
    artifact: dict[str, Any],
    *,
    hash_provider: HashProvider | None = None,
) -> bytes:
    context = _RenderContext(facts, hash_provider=hash_provider)
    for namespace in facts["artifacts"]:
        for item in namespace["namespaces"]:
            ET.register_namespace(item["prefix"], item["uri"])
    root = ET.Element(f"{{{XMI}}}XMI")
    packages = sorted(
        artifact["packages"],
        key=lambda item: (len(item["packagePath"]), item["packagePath"]),
    )
    root_packages = [
        package for package in packages if len(package["packagePath"]) == 1
    ]
    if len(root_packages) != 1:
        raise RoundTripError(
            "PACKAGE_ROOT",
            f"{artifact['filename']} must have exactly one root package",
        )
    root_package = root_packages[0]
    model_tag = (
        f"{{{UML}}}"
        f"{'Profile' if root_package['kind'] == 'Profile' else 'Package'}"
    )
    model = ET.SubElement(
        root,
        model_tag,
        {
            XMI_TYPE: f"uml:{root_package['kind']}",
            XMI_ID: context.ids[root_package["id"]],
            "name": root_package["name"],
        },
    )
    if root_package["uri"]["present"]:
        model.set("URI", root_package["uri"]["value"] or "")
    package_nodes = {tuple(root_package["packagePath"]): model}
    for package in packages:
        path = tuple(package["packagePath"])
        if package is root_package:
            node = model
        else:
            parent = package_nodes.get(path[:-1])
            if parent is None:
                raise RoundTripError(
                    "PACKAGE_PARENT",
                    f"{artifact['filename']} has no parent for {path}",
                )
            node = ET.SubElement(
                parent,
                "packagedElement",
                {
                    XMI_TYPE: f"uml:{package['kind']}",
                    XMI_ID: context.ids[package["id"]],
                    "name": package["name"],
                },
            )
            if package["uri"]["present"]:
                node.set("URI", package["uri"]["value"] or "")
            package_nodes[path] = node
        _append_comments(
            node,
            package["comments"],
            artifact,
            context,
            package["id"],
        )
    for machinery in artifact["machinery"]:
        owner = package_nodes.get(tuple(machinery["ownerPath"]))
        if owner is None:
            raise RoundTripError(
                "MACHINERY_OWNER",
                f"{artifact['filename']} has no package {machinery['ownerPath']}",
            )
        node = ET.SubElement(
            owner,
            _machinery_tag(machinery["kind"]),
            {
                XMI_TYPE: _machinery_type(machinery["kind"]),
                XMI_ID: context.ids[machinery["id"]],
            },
        )
        for reference in machinery["targets"]:
            _append_reference(node, reference, artifact, context)
        _append_comments(node, machinery["comments"], artifact, context, machinery["id"])
    for declaration in artifact["declarations"]:
        owner_path = _package_path_for_canonical_id(artifact, declaration["id"])
        owner = package_nodes[owner_path]
        node = _append_declaration(owner, declaration, artifact, context)
        _append_comments(
            node, declaration["comments"], artifact, context, declaration["id"]
        )
        for extension in declaration["extensions"]:
            _append_extension(owner, extension, artifact, context)
    sysml_namespace = "http://www.omg.org/spec/SysML/20181001/SysML"
    for declaration in artifact["declarations"]:
        if declaration.get("sysmlKind"):
            ET.SubElement(
                root,
                f"{{{sysml_namespace}}}{declaration['sysmlKind']}",
                {
                    XMI_ID: context.digest_id(declaration["id"], "sysmlKind"),
                    "base_Class": context.ids[declaration["id"]],
                },
            )
        for connector in declaration["connectors"]:
            if connector.get("isBinding"):
                ET.SubElement(
                    root,
                    f"{{{sysml_namespace}}}BindingConnector",
                    {
                        XMI_ID: context.digest_id(connector["id"], "binding"),
                        "base_Connector": context.ids[connector["id"]],
                    },
                )
            for ordinal, end in enumerate(connector["ends"], start=1):
                if end.get("propertyPath"):
                    ET.SubElement(
                        root,
                        f"{{{sysml_namespace}}}NestedConnectorEnd",
                        {
                            XMI_ID: context.digest_id(
                                connector["id"], "nested", str(ordinal)
                            ),
                            "base_ConnectorEnd": context.owned_id(
                                Path(artifact["filename"]).stem,
                                connector["id"],
                                "ConnectorEnd",
                                "end",
                                ordinal,
                            ),
                            "propertyPath": " ".join(
                                context.reference_value(ref, artifact)
                                for ref in end["propertyPath"]
                            ),
                        },
                    )
    for namespace in artifact["namespaces"]:
        ET.SubElement(
            root,
            f"{{{MOFEXT}}}Tag",
            {
                XMI_TYPE: "mofext:Tag",
                XMI_ID: context.digest_id(
                    artifact["artifactId"],
                    namespace["prefix"],
                ),
                "name": "org.omg.xmi.nsPrefix",
                "value": namespace["prefix"],
                "element": context.ids[root_package["id"]],
            },
        )
    for application in artifact["applications"]:
        attrs = {
            XMI_ID: context.ids[application["id"]],
            application["targetProperty"]: context.reference_value(
                application["target"], artifact
            ),
        }
        for value in application["values"]:
            attrs[value["property"]] = " ".join(value["values"])
        ET.SubElement(
            root,
            f"{{{application['stereotypeNamespace']}}}{application['stereotypeName']}",
            attrs,
        )
    ET.indent(root, space="  ")
    return ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
        short_empty_elements=True,
    ) + b"\n"


def _package_path_for_canonical_id(
    artifact: dict[str, Any],
    canonical_id: str,
) -> tuple[str, ...]:
    matches = []
    for package in artifact["packages"]:
        path = tuple(package["packagePath"])
        prefix = f"{artifact['artifactId']}::{'::'.join(path)}::"
        if canonical_id.startswith(prefix):
            matches.append(path)
    if not matches:
        raise RoundTripError(
            "DECLARATION_OWNER",
            f"{artifact['filename']} has no package owner for {canonical_id}",
        )
    return max(matches, key=len)


class _RenderContext:
    def __init__(
        self,
        facts: dict[str, Any],
        *,
        hash_provider: HashProvider | None = None,
    ):
        self.facts = facts
        self.hash_provider = hash_provider or _sha256_hex
        self.artifact_by_id = {
            artifact["artifactId"]: artifact for artifact in facts["artifacts"]
        }
        self.artifact_for_target: dict[str, dict[str, Any]] = {}
        self.ids: dict[str, str] = {}
        self.sources_by_generated_id: dict[str, str] = {}
        for artifact in facts["artifacts"]:
            key = Path(artifact["filename"]).stem
            for package in artifact["packages"]:
                self._assign(
                    package["id"],
                    synthetic_id(
                        key,
                        package["name"],
                        hash_provider=self.hash_provider,
                    ),
                )
                self.artifact_for_target[package["id"]] = artifact
            for declaration in artifact["declarations"]:
                name = declaration["name"] or declaration["id"]
                self._assign(
                    declaration["id"],
                    synthetic_id(
                        key,
                        name,
                        hash_provider=self.hash_provider,
                    ),
                )
                self.artifact_for_target[declaration["id"]] = artifact
                self._index_owned(artifact, declaration, key)
            for machinery in artifact["machinery"]:
                self._assign(
                    machinery["id"],
                    _digest_id(
                        key,
                        machinery["id"],
                        hash_provider=self.hash_provider,
                    ),
                )
                self.artifact_for_target[machinery["id"]] = artifact
            for application in artifact["applications"]:
                self._assign(
                    application["id"],
                    _digest_id(
                        key,
                        application["id"],
                        hash_provider=self.hash_provider,
                    ),
                )
                self.artifact_for_target[application["id"]] = artifact

    def _assign(self, canonical_id: str, generated_id: str) -> None:
        self._claim(canonical_id, generated_id)
        self.ids[canonical_id] = generated_id

    def _claim(self, source: str, generated_id: str) -> str:
        previous = self.sources_by_generated_id.get(generated_id)
        if previous is not None and previous != source:
            raise RoundTripError(
                "SYNTHETIC_ID_COLLISION",
                f"synthetic ID collision between {previous} and {source}",
            )
        self.sources_by_generated_id[generated_id] = source
        return generated_id

    def digest_id(self, *parts: str) -> str:
        source = "::".join(parts)
        return self._claim(
            source,
            _digest_id(*parts, hash_provider=self.hash_provider),
        )

    def owned_id(
        self,
        artifact: str,
        owner: str,
        kind: str,
        name: str,
        ordinal: int,
    ) -> str:
        source = f"{artifact}::{owner}::{kind}::{name}::{ordinal}"
        return self._claim(
            source,
            synthetic_owned_id(
                artifact,
                owner,
                kind,
                name,
                ordinal,
                hash_provider=self.hash_provider,
            ),
        )

    def _index_owned(
        self,
        artifact: dict[str, Any],
        declaration: dict[str, Any],
        key: str,
    ) -> None:
        for relation in ("properties", "ownedEnds", "extensions", "constraints", "connectors"):
            for ordinal, item in enumerate(declaration[relation], start=1):
                local = item.get("name") or item["id"]
                self._assign(
                    item["id"],
                    synthetic_owned_id(
                        key,
                        declaration["id"],
                        relation,
                        local,
                        ordinal,
                        hash_provider=self.hash_provider,
                    ),
                )
                self.artifact_for_target[item["id"]] = artifact
                if relation == "extensions":
                    for end_ordinal, end in enumerate(item["ownedEnds"], start=1):
                        self._assign(
                            end["id"],
                            synthetic_owned_id(
                                key,
                                item["id"],
                                "ExtensionEnd",
                                end.get("name") or end["id"],
                                end_ordinal,
                                hash_provider=self.hash_provider,
                            ),
                        )
                        self.artifact_for_target[end["id"]] = artifact

    def reference_value(
        self,
        reference: dict[str, str],
        current_artifact: dict[str, Any],
    ) -> str:
        target = reference["target"]
        if target.startswith("external::"):
            _, rest = target.split("external::", 1)
            document, separator, fragment = rest.partition("::")
            if not separator:
                raise RoundTripError(
                    "EXTERNAL_REFERENCE_SHAPE",
                    f"invalid external identity: {target}",
                )
            if fragment == "Package::UML":
                fragment = "_0"
            return f"{document}#{fragment}"
        if target not in self.ids:
            raise RoundTripError(
                "REFERENCE_TARGET_MISSING",
                f"reference target is absent from slice: {target}",
            )
        target_artifact = self.artifact_for_target[target]
        if reference["sourceForm"] == "href":
            return (
                "https://www.omg.org/spec/RAAML/20240219/"
                f"{target_artifact['filename']}#{self.ids[target]}"
            )
        if target_artifact["artifactId"] != current_artifact["artifactId"]:
            raise RoundTripError(
                "REFERENCE_FORM_CROSS_FILE",
                f"non-href cross-file reference: {target}",
            )
        return self.ids[target]


def _append_declaration(
    model: ET.Element,
    declaration: dict[str, Any],
    artifact: dict[str, Any],
    context: _RenderContext,
) -> ET.Element:
    attrs = {
        XMI_TYPE: f"uml:{declaration['kind']}",
        XMI_ID: context.ids[declaration["id"]],
    }
    if declaration["name"] is not None:
        attrs["name"] = declaration["name"]
    if declaration["isAbstract"]["present"]:
        attrs["isAbstract"] = str(declaration["isAbstract"]["value"]).lower()
    node = ET.SubElement(model, "packagedElement", attrs)
    for reference in declaration["generalizations"]:
        relationship = ET.SubElement(
            node,
            "generalization",
            {
                XMI_TYPE: "uml:Generalization",
                XMI_ID: context.digest_id(
                    declaration["id"],
                    "generalization",
                    reference["target"],
                ),
            },
        )
        _append_reference(relationship, reference, artifact, context)
    for ordinal, prop in enumerate(declaration["properties"], start=1):
        _append_property(node, "ownedAttribute", prop, artifact, context, ordinal)
    for ordinal, owned_end in enumerate(declaration["ownedEnds"], start=1):
        _append_property(node, "ownedEnd", owned_end, artifact, context, ordinal)
    for reference in declaration["memberEnds"]:
        _append_reference(node, reference, artifact, context)
    for reference in declaration["navigableOwnedEnds"]:
        _append_reference(node, reference, artifact, context)
    for literal_ordinal, literal in enumerate(declaration["literals"], start=1):
        literal_node = ET.SubElement(
            node,
            "ownedLiteral",
            {
                XMI_TYPE: "uml:EnumerationLiteral",
                XMI_ID: context.owned_id(
                    Path(artifact["filename"]).stem,
                    declaration["id"],
                    "EnumerationLiteral",
                    literal["name"],
                    literal_ordinal,
                ),
                "name": literal["name"],
            },
        )
        _append_comments(
            literal_node,
            literal["comments"],
            artifact,
            context,
            f"{declaration['id']}::{literal['name']}",
        )
    for constraint in declaration["constraints"]:
        constraint_node = ET.SubElement(
            node,
            "ownedRule",
            {
                XMI_TYPE: "uml:Constraint",
                XMI_ID: context.ids[constraint["id"]],
            },
        )
        if constraint["name"] is not None:
            constraint_node.set("name", constraint["name"])
        for reference in constraint["constrainedElements"]:
            _append_reference(constraint_node, reference, artifact, context)
        specification = ET.SubElement(
            constraint_node,
            "specification",
            {
                XMI_TYPE: "uml:OpaqueExpression",
                XMI_ID: context.digest_id(
                    constraint["id"],
                    "specification",
                ),
            },
        )
        for body in constraint["bodyLines"]:
            ET.SubElement(specification, "body").text = body
        for language in constraint["languages"]:
            ET.SubElement(specification, "language").text = language
        _append_comments(
            constraint_node,
            constraint["comments"],
            artifact,
            context,
            constraint["id"],
        )
    for connector in declaration["connectors"]:
        _append_connector(node, connector, artifact, context)
    for icon_ordinal, icon in enumerate(declaration["icons"], start=1):
        icon_node = ET.SubElement(
            node,
            "icon",
            {
                XMI_TYPE: "uml:Image",
                XMI_ID: context.owned_id(
                    Path(artifact["filename"]).stem,
                    declaration["id"],
                    "Image",
                    "icon",
                    icon_ordinal,
                ),
                "content": icon["content"],
            },
        )
        for field in ("format", "location"):
            if icon[field]["present"]:
                icon_node.set(field, icon[field]["value"] or "")
    return node


def _append_connector(
    owner: ET.Element,
    connector: dict[str, Any],
    artifact: dict[str, Any],
    context: _RenderContext,
) -> None:
    attrs = {
        XMI_TYPE: "uml:Connector",
        XMI_ID: context.ids[connector["id"]],
    }
    if connector["name"] is not None:
        attrs["name"] = connector["name"]
    node = ET.SubElement(owner, "ownedConnector", attrs)
    for ordinal, end in enumerate(connector["ends"], start=1):
        end_node = ET.SubElement(
            node,
            "end",
            {
                XMI_TYPE: "uml:ConnectorEnd",
                XMI_ID: context.owned_id(
                    Path(artifact["filename"]).stem,
                    connector["id"],
                    "ConnectorEnd",
                    "end",
                    ordinal,
                ),
            },
        )
        _append_reference(end_node, end["role"], artifact, context)
        if end["partWithPort"] is not None:
            _append_reference(
                end_node,
                end["partWithPort"],
                artifact,
                context,
            )
    _append_comments(
        node,
        connector["comments"],
        artifact,
        context,
        connector["id"],
    )


def _append_extension(
    model: ET.Element,
    extension: dict[str, Any],
    artifact: dict[str, Any],
    context: _RenderContext,
) -> None:
    node = ET.SubElement(
        model,
        "packagedElement",
        {
            XMI_TYPE: "uml:Extension",
            XMI_ID: context.ids[extension["id"]],
        },
    )
    for reference in extension["memberEnds"]:
        _append_reference(node, reference, artifact, context)
    for reference in extension["navigableOwnedEnds"]:
        _append_reference(node, reference, artifact, context)
    for ordinal, end in enumerate(extension["ownedEnds"], start=1):
        _append_property(node, "ownedEnd", end, artifact, context, ordinal)
    _append_comments(node, extension["comments"], artifact, context, extension["id"])


def _append_property(
    owner: ET.Element,
    tag: str,
    prop: dict[str, Any],
    artifact: dict[str, Any],
    context: _RenderContext,
    ordinal: int,
) -> None:
    attrs = {
        XMI_TYPE: f"uml:{prop['kind']}",
        XMI_ID: context.ids[prop["id"]],
    }
    if prop["name"] is not None:
        attrs["name"] = prop["name"]
    for field in ("aggregation",):
        if prop[field]["present"]:
            attrs[field] = prop[field]["value"] or ""
    for field in ("isDerived", "isReadOnly", "isOrdered", "isUnique"):
        if prop[field]["present"]:
            attrs[field] = str(prop[field]["value"]).lower()
    node = ET.SubElement(owner, tag, attrs)
    if prop["type"] is not None:
        _append_reference(node, prop["type"], artifact, context)
    for relation in ("subsettedProperties", "redefinedProperties"):
        for reference in prop[relation]:
            _append_reference(node, reference, artifact, context)
    for role in ("lower", "upper", "default"):
        value = prop[role]
        if value["present"]:
            child = ET.SubElement(
                node,
                f"{role}Value",
                {
                    XMI_TYPE: value["kind"],
                    XMI_ID: context.digest_id(
                        prop["id"],
                        role,
                        str(ordinal),
                    ),
                },
            )
            if value["value"] is not None:
                child.set("value", value["value"])
    _append_comments(node, prop["comments"], artifact, context, prop["id"])


def _append_comments(
    owner: ET.Element,
    comments: list[dict[str, Any]],
    artifact: dict[str, Any],
    context: _RenderContext,
    owner_id: str,
) -> None:
    for ordinal, comment in enumerate(comments, start=1):
        node = ET.SubElement(
            owner,
            "ownedComment",
            {
                XMI_TYPE: "uml:Comment",
                XMI_ID: context.digest_id(
                    owner_id,
                    "comment",
                    str(ordinal),
                ),
                "body": comment["body"],
            },
        )
        for reference in comment["annotatedElements"]:
            _append_reference(node, reference, artifact, context)


def _append_reference(
    owner: ET.Element,
    reference: dict[str, str],
    artifact: dict[str, Any],
    context: _RenderContext,
) -> None:
    value = context.reference_value(reference, artifact)
    role = reference["role"]
    if reference["sourceForm"] == "attribute":
        owner.set(role, value)
    elif reference["sourceForm"] == "idref":
        ET.SubElement(owner, role, {XMI_IDREF: value})
    else:
        ET.SubElement(owner, role, {"href": value})


def _require_slice_coverage(facts: dict[str, Any]) -> None:
    filenames = {artifact["filename"] for artifact in facts.get("artifacts", [])}
    required = FULL_ARTIFACTS | {"STPA.xmi", "STPALib.xmi"}
    if filenames != required:
        raise RoundTripError(
            "SLICE_ARTIFACTS",
            f"expected {sorted(required)}, got {sorted(filenames)}",
        )
    declarations = {
        declaration["name"]
        for artifact in facts["artifacts"]
        for declaration in artifact["declarations"]
    }
    required_names = {
        "Situation",
        "ControlStructure",
        "Controller",
        "ControlAction",
        "Undeveloped",
        "Loss",
    }
    missing = required_names - declarations
    if missing:
        raise RoundTripError("SLICE_DECLARATIONS", f"missing {sorted(missing)}")
    undeveloped = next(
        declaration
        for artifact in facts["artifacts"]
        for declaration in artifact["declarations"]
        if declaration["name"] == "Undeveloped"
    )
    if not undeveloped["icons"] or undeveloped["properties"][0]["name"] != "base_Element":
        raise RoundTripError(
            "SLICE_UNDEVELOPED",
            "Undeveloped must retain base_Element and its icon",
        )
    if not any(
        declaration["constraints"]
        for artifact in facts["artifacts"]
        for declaration in artifact["declarations"]
    ):
        raise RoundTripError("SLICE_OCL", "slice has no constraint")
    if not any(
        application["stereotypeName"] == "Situation"
        for artifact in facts["artifacts"]
        for application in artifact["applications"]
    ):
        raise RoundTripError("SLICE_APPLICATION", "slice has no Situation application")


def _require_full_corpus_coverage(facts: dict[str, Any]) -> None:
    locked = load_lock(
        Path(__file__).resolve().parents[2] / "standards.lock.json"
    )
    expected = {
        artifact["filename"]
        for artifact in locked["artifacts"]
        if artifact["collection"] == "raaml-1.1-definitions"
    }
    actual = {
        artifact["filename"]
        for artifact in facts.get("artifacts", [])
    }
    if len(expected) != 17 or actual != expected:
        raise RoundTripError(
            "FULL_CORPUS_ARTIFACTS",
            f"expected {sorted(expected)}, got {sorted(actual)}",
        )
    declaration_count = sum(
        len(artifact["declarations"]) for artifact in facts["artifacts"]
    )
    if declaration_count != 283:
        raise RoundTripError(
            "FULL_CORPUS_DECLARATIONS",
            f"expected 283 declarations, got {declaration_count}",
        )


def _require_reference_closure(facts: dict[str, Any]) -> None:
    known = set()
    references = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            identifier = value.get("id")
            if isinstance(identifier, str):
                known.add(identifier)
            if {"role", "sourceForm", "target"} <= set(value):
                references.append(value["target"])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(facts)
    missing = sorted(
        target
        for target in references
        if not target.startswith("external::") and target not in known
    )
    if missing:
        raise RoundTripError(
            "REFERENCE_TARGET_MISSING",
            f"slice has {len(missing)} unresolved target(s): {missing[:3]}",
        )


def _differences(expected: Any, actual: Any, path: str = "$") -> list[dict[str, Any]]:
    if type(expected) is not type(actual):
        return [{"path": path, "expected": expected, "actual": actual}]
    if isinstance(expected, dict):
        differences = []
        for key in sorted(set(expected) | set(actual)):
            if key not in expected or key not in actual:
                differences.append(
                    {
                        "path": f"{path}.{key}",
                        "expected": expected.get(key),
                        "actual": actual.get(key),
                    }
                )
            else:
                differences.extend(
                    _differences(expected[key], actual[key], f"{path}.{key}")
                )
        return differences
    if isinstance(expected, list):
        differences = []
        if len(expected) != len(actual):
            differences.append(
                {
                    "path": f"{path}.length",
                    "expected": len(expected),
                    "actual": len(actual),
                }
            )
        for index, (left, right) in enumerate(zip(expected, actual)):
            differences.extend(_differences(left, right, f"{path}[{index}]"))
        return differences
    return [] if expected == actual else [
        {"path": path, "expected": expected, "actual": actual}
    ]


def _sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def synthetic_id(
    artifact: str,
    name: str,
    *,
    hash_provider: HashProvider | None = None,
) -> str:
    provider = hash_provider or _sha256_hex
    return "_raaml_" + provider(
        f"{artifact}::{name}".encode("utf-8")
    )[:40]


def synthetic_owned_id(
    artifact: str,
    owner: str,
    kind: str,
    name: str,
    ordinal: int,
    *,
    hash_provider: HashProvider | None = None,
) -> str:
    value = f"{artifact}::{owner}::{kind}::{name}::{ordinal}"
    provider = hash_provider or _sha256_hex
    return "_raaml_" + provider(value.encode("utf-8"))[:40]


def _digest_id(
    *parts: str,
    hash_provider: HashProvider | None = None,
) -> str:
    provider = hash_provider or _sha256_hex
    return "_raaml_" + provider("::".join(parts).encode("utf-8"))[:40]


def _identifier(value: str) -> str:
    result = SAFE_NAME.sub("_", value)
    if not result or result[0].isdigit():
        result = f"_{result}"
    return result


def _machinery_tag(kind: str) -> str:
    return {
        "MetamodelReference": "metamodelReference",
        "PackageImport": "packageImport",
        "ElementImport": "elementImport",
        "ProfileApplication": "profileApplication",
    }[kind]


def _machinery_type(kind: str) -> str:
    return {
        "MetamodelReference": "uml:PackageImport",
        "PackageImport": "uml:PackageImport",
        "ElementImport": "uml:ElementImport",
        "ProfileApplication": "uml:ProfileApplication",
    }[kind]
