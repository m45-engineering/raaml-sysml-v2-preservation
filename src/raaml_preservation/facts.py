from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

from .secure_xml import UnsafeXmlError, preflight_xml
from .sources import load_lock, verify_sources


SCHEMA_VERSION = "0.2.0"
CORPUS = "raaml-1.1-definitions"
XMI_NAMESPACE = "http://www.omg.org/spec/XMI/20131001"
XMI_ID = f"{{{XMI_NAMESPACE}}}id"
XMI_IDREF = f"{{{XMI_NAMESPACE}}}idref"
XMI_TYPE = f"{{{XMI_NAMESPACE}}}type"
RAAML_NAMESPACE_PREFIX = "https://www.omg.org/spec/RAAML/"
IDENTITY_SEPARATOR = "::"
MAGICDRAW_ID = re.compile(r"^_[A-Za-z0-9_]+$")

DECLARATION_TYPES = {
    "uml:Stereotype": "Stereotype",
    "uml:Class": "Class",
    "uml:Enumeration": "Enumeration",
    "uml:Association": "Association",
    "uml:AssociationClass": "AssociationClass",
}
PROPERTY_TYPES = {
    "uml:Property": "Property",
    "uml:Port": "Port",
    "uml:ExtensionEnd": "ExtensionEnd",
}
MACHINERY_TAGS = {
    "metamodelReference": "MetamodelReference",
    "packageImport": "PackageImport",
    "elementImport": "ElementImport",
    "profileApplication": "ProfileApplication",
}


class FactExtractionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def extract_facts(
    repository_root: Path,
    *,
    lock_path: Path | None = None,
    source_dir: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    lock_path = lock_path or repository_root / "standards.lock.json"
    source_dir = source_dir or repository_root / "sources" / "cache"
    lock = load_lock(lock_path)
    verification = verify_sources(
        lock_path=lock_path,
        source_dir=source_dir,
        collection=CORPUS,
    )
    if not verification["ok"]:
        first = verification["diagnostics"][0]
        raise FactExtractionError(first["code"], first["message"])

    allowed = _allowed_remote_documents(lock)
    artifacts = [
        artifact
        for artifact in lock["artifacts"]
        if artifact["collection"] == CORPUS
    ]
    if len(artifacts) != 17:
        raise FactExtractionError(
            "FACT_CORPUS_SIZE",
            f"expected 17 locked RAAML definitions, got {len(artifacts)}",
        )

    raw_artifacts = []
    for artifact in artifacts:
        path = source_dir / artifact["filename"]
        try:
            preflight_xml(path, allowed_remote_documents=allowed)
        except UnsafeXmlError as error:
            raise FactExtractionError(error.code, str(error)) from error
        raw_artifacts.append(_extract_artifact(path, artifact))

    raw = {
        "schemaVersion": SCHEMA_VERSION,
        "documentKind": "raw-raaml-facts",
        "corpus": CORPUS,
        "artifacts": raw_artifacts,
    }
    external_index = _external_identity_aliases()
    canonical = canonicalize_facts(raw, external_index=external_index)
    return raw, canonical


def extract_artifact_set(
    repository_root: Path,
    artifacts: list[dict[str, str]],
    source_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract a declared artifact set without replacing its source provenance.

    This is used for reconstructed outputs. Each descriptor supplies the
    original artifact identity and digest, while ``source_dir`` supplies the
    XMI bytes being checked.
    """
    lock = load_lock(repository_root / "standards.lock.json")
    allowed = _allowed_remote_documents(lock)
    raw_artifacts = []
    for artifact in artifacts:
        path = source_dir / artifact["filename"]
        try:
            preflight_xml(path, allowed_remote_documents=allowed)
        except UnsafeXmlError as error:
            raise FactExtractionError(error.code, str(error)) from error
        raw_artifacts.append(_extract_artifact(path, artifact))
    raw = {
        "schemaVersion": SCHEMA_VERSION,
        "documentKind": "raw-raaml-facts",
        "corpus": CORPUS,
        "artifacts": raw_artifacts,
    }
    return raw, canonicalize_facts(raw)


def canonicalize_facts(
    raw: dict[str, Any],
    *,
    external_index: dict[str, str] | None = None,
) -> dict[str, Any]:
    if raw.get("documentKind") != "raw-raaml-facts":
        raise FactExtractionError("FACT_DOCUMENT_KIND", "expected raw-raaml-facts")

    canonical = copy.deepcopy(raw)
    external_index = external_index or _external_identity_aliases()
    canonical["documentKind"] = "canonical-raaml-facts"
    source_index: dict[tuple[str, str], str] = {}
    filename_to_artifact = {
        artifact["filename"]: artifact for artifact in canonical["artifacts"]
    }

    for artifact in canonical["artifacts"]:
        artifact_id = artifact["artifactId"]
        for package in artifact["packages"]:
            package_id = _named_id(
                artifact_id,
                package["packagePath"][:-1],
                package["kind"],
                package["name"],
            )
            source_index[(artifact["filename"], package["sourceHandle"])] = package_id
            package["id"] = package_id
            del package["sourceHandle"]

        for declaration in artifact["declarations"]:
            name = declaration["name"]
            if name is not None:
                declaration_id = _named_id(
                    artifact_id,
                    declaration["packagePath"],
                    declaration["kind"],
                    name,
                )
                source_index[
                    (artifact["filename"], declaration["sourceHandle"])
                ] = declaration_id
                declaration["id"] = declaration_id

    _index_named_declaration_properties(canonical, source_index)
    _assign_anonymous_declaration_ids(canonical, source_index)
    _assign_owned_ids(canonical, source_index)

    for artifact in canonical["artifacts"]:
        filename = artifact["filename"]
        for declaration in artifact["declarations"]:
            _canonicalize_declaration(
                declaration,
                filename,
                filename_to_artifact,
                source_index,
                external_index,
            )
        for package in artifact["packages"]:
            package["comments"] = _canonicalize_comments(
                package["comments"],
                filename,
                filename_to_artifact,
                source_index,
                external_index,
            )
        machinery_ids: set[str] = set()
        for machinery in artifact["machinery"]:
            del machinery["sourceHandle"]
            machinery["targets"] = [
                _canonical_reference(
                    item,
                    filename,
                    filename_to_artifact,
                    source_index,
                    external_index,
                )
                for item in machinery["targets"]
            ]
            machinery["comments"] = _canonicalize_comments(
                machinery["comments"],
                filename,
                filename_to_artifact,
                source_index,
                external_index,
            )
            digest = hashlib.sha256(
                _canonical_json(
                    {
                        "kind": machinery["kind"],
                        "ownerPath": machinery["ownerPath"],
                        "targets": machinery["targets"],
                        "comments": machinery["comments"],
                    }
                ).encode("utf-8")
            ).hexdigest()[:24]
            machinery["id"] = (
                f"{artifact['artifactId']}::machinery::"
                f"{machinery['kind']}::{digest}"
            )
            if machinery["id"] in machinery_ids:
                raise FactExtractionError(
                    "FACT_MACHINERY_AMBIGUOUS",
                    f"machinery identity is ambiguous: {machinery['id']}",
                )
            machinery_ids.add(machinery["id"])
        _canonicalize_applications(
            artifact,
            filename_to_artifact,
            source_index,
            external_index,
        )

        artifact["namespaces"] = sorted(
            artifact["namespaces"], key=_canonical_json
        )
        artifact["packages"] = sorted(artifact["packages"], key=lambda item: item["id"])
        artifact["declarations"] = sorted(
            artifact["declarations"], key=lambda item: item["id"]
        )
        artifact["machinery"] = sorted(
            artifact["machinery"], key=lambda item: item["id"]
        )
        artifact["applications"] = sorted(
            artifact["applications"], key=lambda item: item["id"]
        )

    canonical["artifacts"] = sorted(
        canonical["artifacts"], key=lambda item: item["artifactId"]
    )
    _reject_source_ids(canonical)
    return canonical


def serialize_facts(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def count_facts(canonical: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {
        "profiles": 0,
        "packages": 0,
        "stereotypes": 0,
        "classes": 0,
        "enumerations": 0,
        "enumerationLiterals": 0,
        "associations": 0,
        "associationClasses": 0,
        "properties": 0,
        "ports": 0,
        "connectors": 0,
        "constraints": 0,
        "extensions": 0,
        "extensionEnds": 0,
        "comments": 0,
        "images": 0,
        "raamlApplications": 0,
    }
    declaration_categories = {
        "Stereotype": "stereotypes",
        "Class": "classes",
        "Enumeration": "enumerations",
        "Association": "associations",
        "AssociationClass": "associationClasses",
    }
    property_categories = {
        "Property": "properties",
        "Port": "ports",
        "ExtensionEnd": "extensionEnds",
    }

    def count_property(property_record: dict[str, Any]) -> None:
        counts[property_categories[property_record["kind"]]] += 1

    def count_comments(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "comments":
                    counts["comments"] += len(child)
                count_comments(child)
        elif isinstance(value, list):
            for child in value:
                count_comments(child)

    for artifact in canonical["artifacts"]:
        counts["raamlApplications"] += len(artifact["applications"])
        for package in artifact["packages"]:
            counts["profiles" if package["kind"] == "Profile" else "packages"] += 1
        for declaration in artifact["declarations"]:
            counts[declaration_categories[declaration["kind"]]] += 1
            counts["enumerationLiterals"] += len(declaration["literals"])
            counts["connectors"] += len(declaration["connectors"])
            counts["constraints"] += len(declaration["constraints"])
            counts["extensions"] += len(declaration["extensions"])
            counts["images"] += len(declaration["icons"])
            for property_record in declaration["properties"]:
                count_property(property_record)
            for property_record in declaration["ownedEnds"]:
                count_property(property_record)
            for extension in declaration["extensions"]:
                for property_record in extension["ownedEnds"]:
                    count_property(property_record)
    count_comments(canonical)
    return counts


def _allowed_remote_documents(lock: dict[str, Any]) -> frozenset[str]:
    authoritative = {
        artifact["authoritativeUrl"] for artifact in lock["artifacts"]
    }
    historical = {
        url.replace("https://www.omg.org/", "http://www.omg.org/", 1)
        for url in authoritative
        if url.startswith("https://www.omg.org/")
    }
    return frozenset(authoritative | historical)


def _external_identity_aliases() -> dict[str, str]:
    canonical_document = "https://www.omg.org/spec/UML/20161101/UML.xmi"
    target = f"external::{canonical_document}::Package::UML"
    return {
        f"{canonical_document}#_0": target,
        f"{canonical_document.replace('https://', 'http://', 1)}#_0": target,
    }


def _extract_artifact(path: Path, artifact: dict[str, Any]) -> dict[str, Any]:
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError) as error:
        raise FactExtractionError("FACT_XML_PARSE", f"{path.name}: {error}") from error
    root = tree.getroot()
    children = list(root)
    if not children:
        raise FactExtractionError("FACT_ROOT_EMPTY", f"{path.name}: empty XMI root")
    model = children[0]
    parent = {child: owner for owner in root.iter() for child in owner}
    sysml_applications = {}
    for application in children[1:]:
        if not _namespace(application.tag).startswith("http://www.omg.org/spec/SysML/"):
            continue
        for key, value in application.attrib.items():
            if key.startswith("base_"):
                sysml_applications.setdefault(value, {})[
                    _local_name(application.tag)
                ] = application
    package_paths = _package_paths(model)
    packages = [
        _extract_package(element, package_paths[element])
        for element in model.iter()
        if _is_package(element)
    ]
    declarations = [
        _extract_declaration(
            element, package_paths[_owning_package(element, parent)], sysml_applications
        )
        for element in model.iter()
        if element.get(XMI_TYPE) in DECLARATION_TYPES
    ]
    declaration_by_handle = {
        declaration["sourceHandle"]: declaration for declaration in declarations
    }

    for element in model.iter():
        if element.get(XMI_TYPE) != "uml:Extension":
            continue
        extension = _extract_extension(element)
        owned_ends = extension["ownedEnds"]
        if len(owned_ends) != 1 or owned_ends[0]["type"] is None:
            raise FactExtractionError(
                "FACT_EXTENSION_SHAPE",
                f"{path.name}: Extension must have one typed owned end",
            )
        target_value = owned_ends[0]["type"]["sourceValue"]
        target = declaration_by_handle.get(target_value)
        if target is None or target["kind"] != "Stereotype":
            raise FactExtractionError(
                "FACT_EXTENSION_TARGET",
                f"{path.name}: Extension target is not a local Stereotype",
            )
        target["extensions"].append(extension)

    machinery = []
    for element in model.iter():
        local = _local_name(element.tag)
        if local not in MACHINERY_TAGS:
            continue
        owner = _owning_package(element, parent)
        machinery.append(
            _extract_machinery(
                element,
                MACHINERY_TAGS[local],
                package_paths[owner],
            )
        )

    profile_uri = model.get("URI")
    namespaces = []
    for element in children[1:]:
        if (
            _local_name(element.tag) == "Tag"
            and element.get("name") == "org.omg.xmi.nsPrefix"
            and element.get("value")
            and profile_uri
        ):
            namespaces.append({"prefix": element.get("value"), "uri": profile_uri})

    applications = []
    for element in children[1:]:
        namespace = _namespace(element.tag)
        if namespace.startswith(RAAML_NAMESPACE_PREFIX):
            applications.append(_extract_application(element, namespace))

    return {
        "artifactId": artifact["id"],
        "filename": artifact["filename"],
        "sha256": artifact["sha256"],
        "namespaces": namespaces,
        "packages": packages,
        "declarations": declarations,
        "machinery": machinery,
        "applications": applications,
    }


def _extract_package(element: ET.Element, path: list[str]) -> dict[str, Any]:
    name = _required_name(element, "package")
    kind = "Profile" if element.get(XMI_TYPE) == "uml:Profile" else "Package"
    return {
        "sourceHandle": _source_handle(element),
        "kind": kind,
        "packagePath": path,
        "name": name,
        "uri": _presence_string(element, "URI"),
        "comments": _extract_comments(element),
    }


def _extract_declaration(
    element: ET.Element,
    package_path: list[str],
    sysml_applications: dict[str, dict[str, ET.Element]],
) -> dict[str, Any]:
    kind = DECLARATION_TYPES[element.get(XMI_TYPE)]
    properties = [
        _extract_property(child)
        for child in element
        if _local_name(child.tag) == "ownedAttribute"
    ]
    owned_ends = [
        _extract_property(child)
        for child in element
        if _local_name(child.tag) == "ownedEnd"
    ]
    return {
        "sourceHandle": _source_handle(element),
        "kind": kind,
        "sysmlKind": next(
            (
                name
                for name in ("ConstraintBlock", "Block")
                if name in sysml_applications.get(_source_handle(element), {})
            ),
            None,
        ),
        "packagePath": package_path,
        "name": element.get("name"),
        "isAbstract": _presence_boolean(element, "isAbstract", False),
        "comments": _extract_comments(element),
        "generalizations": _extract_generalizations(element),
        "properties": properties,
        "extensions": [],
        "icons": _extract_icons(element),
        "constraints": _extract_constraints(element),
        "literals": _extract_literals(element),
        "connectors": _extract_connectors(element, sysml_applications),
        "memberEnds": _references(element, "memberEnd"),
        "ownedEnds": owned_ends,
        "navigableOwnedEnds": _references(element, "navigableOwnedEnd"),
    }


def _extract_property(element: ET.Element) -> dict[str, Any]:
    property_kind = PROPERTY_TYPES.get(element.get(XMI_TYPE))
    if property_kind is None:
        raise FactExtractionError(
            "FACT_PROPERTY_KIND",
            f"unsupported property type {element.get(XMI_TYPE)!r}",
        )
    name = element.get("name")
    return {
        "sourceHandle": _source_handle(element),
        "kind": property_kind,
        "name": name,
        "isBase": bool(name and name.startswith("base_")),
        "type": _single_reference(element, "type"),
        "aggregation": _presence_string(element, "aggregation"),
        "lower": _extract_value_literal(element, "lowerValue"),
        "upper": _extract_value_literal(element, "upperValue"),
        "default": _extract_value_literal(element, "defaultValue"),
        "isDerived": _presence_boolean(element, "isDerived", False),
        "isReadOnly": _presence_boolean(element, "isReadOnly", False),
        "isOrdered": _presence_boolean(element, "isOrdered", False),
        "isUnique": _presence_boolean(element, "isUnique", True),
        "subsettedProperties": _references(element, "subsettedProperty"),
        "redefinedProperties": _references(element, "redefinedProperty"),
        "comments": _extract_comments(element),
    }


def _extract_extension(element: ET.Element) -> dict[str, Any]:
    return {
        "sourceHandle": _source_handle(element),
        "memberEnds": _references(element, "memberEnd"),
        "navigableOwnedEnds": _references(element, "navigableOwnedEnd"),
        "ownedEnds": [
            _extract_property(child)
            for child in element
            if _local_name(child.tag) == "ownedEnd"
            and child.get(XMI_TYPE) == "uml:ExtensionEnd"
        ],
        "comments": _extract_comments(element),
    }


def _extract_comments(element: ET.Element) -> list[dict[str, Any]]:
    comments = []
    for child in element:
        if _local_name(child.tag) != "ownedComment":
            continue
        body = child.get("body")
        if body is None:
            bodies = [
                grandchild.text or ""
                for grandchild in child
                if _local_name(grandchild.tag) == "body"
            ]
            body = "\n".join(bodies)
        comments.append(
            {
                "body": body,
                "annotatedElements": _references(child, "annotatedElement"),
            }
        )
    return comments


def _extract_icons(element: ET.Element) -> list[dict[str, Any]]:
    icons = []
    for child in element:
        if _local_name(child.tag) != "icon" or child.get(XMI_TYPE) != "uml:Image":
            continue
        icons.append(
            {
                "format": _presence_string(child, "format"),
                "content": child.get("content", ""),
                "location": _presence_string(child, "location"),
            }
        )
    return icons


def _extract_constraints(element: ET.Element) -> list[dict[str, Any]]:
    constraints = []
    for child in element:
        if _local_name(child.tag) != "ownedRule":
            continue
        specification = next(
            (
                item
                for item in child
                if _local_name(item.tag) == "specification"
            ),
            None,
        )
        languages: list[str] = []
        body_lines: list[str] = []
        if specification is not None:
            languages = [
                item.text or ""
                for item in specification
                if _local_name(item.tag) == "language"
            ]
            body_lines = [
                item.text or ""
                for item in specification
                if _local_name(item.tag) == "body"
            ]
        constraints.append(
            {
                "sourceHandle": _source_handle(child),
                "name": child.get("name"),
                "constrainedElements": _references(child, "constrainedElement"),
                "languages": languages,
                "bodyLines": body_lines,
                "comments": _extract_comments(child),
            }
        )
    return constraints


def _extract_literals(element: ET.Element) -> list[dict[str, Any]]:
    literals = []
    for child in element:
        if _local_name(child.tag) == "ownedLiteral":
            literals.append(
                {
                    "name": _required_name(child, "EnumerationLiteral"),
                    "comments": _extract_comments(child),
                }
            )
    return literals


def _extract_connectors(
    element: ET.Element, sysml_applications: dict[str, dict[str, ET.Element]]
) -> list[dict[str, Any]]:
    connectors = []
    for child in element:
        if (
            _local_name(child.tag) != "ownedConnector"
            or child.get(XMI_TYPE) != "uml:Connector"
        ):
            continue
        ends = []
        for end in child:
            if _local_name(end.tag) != "end":
                continue
            role = _single_reference(end, "role")
            if role is None:
                raise FactExtractionError(
                    "FACT_CONNECTOR_ROLE",
                    "ConnectorEnd has no role",
                )
            nested = sysml_applications.get(_source_handle(end), {}).get(
                "NestedConnectorEnd"
            )
            property_path = (
                nested.get("propertyPath", "").split() if nested is not None else []
            )
            ends.append(
                {
                    "role": role,
                    "partWithPort": _single_reference(end, "partWithPort"),
                    "propertyPath": [
                        {
                            "role": "propertyPath",
                            "form": "attribute",
                            "sourceValue": value,
                        }
                        for value in property_path
                    ],
                }
            )
        connectors.append(
            {
                "sourceHandle": _source_handle(child),
                "name": child.get("name"),
                "isBinding": "BindingConnector"
                in sysml_applications.get(_source_handle(child), {}),
                "ends": ends,
                "comments": _extract_comments(child),
            }
        )
    return connectors


def _extract_generalizations(element: ET.Element) -> list[dict[str, str]]:
    references = []
    for child in element:
        if _local_name(child.tag) != "generalization":
            continue
        reference = _single_reference(child, "general")
        if reference is None:
            raise FactExtractionError(
                "FACT_GENERALIZATION_TARGET",
                "Generalization has no general target",
            )
        references.append(reference)
    return references


def _extract_machinery(
    element: ET.Element,
    kind: str,
    owner_path: list[str],
) -> dict[str, Any]:
    target_roles = {
        "MetamodelReference": ("importedPackage",),
        "PackageImport": ("importedPackage",),
        "ElementImport": ("importedElement",),
        "ProfileApplication": ("appliedProfile",),
    }[kind]
    targets = [
        reference
        for role in target_roles
        for reference in _references(element, role)
    ]
    return {
        "sourceHandle": _source_handle(element),
        "kind": kind,
        "ownerPath": owner_path,
        "targets": targets,
        "comments": _extract_comments(element),
    }


def _extract_application(
    element: ET.Element,
    namespace: str,
) -> dict[str, Any]:
    attributes = {
        _local_name(key): value
        for key, value in element.attrib.items()
        if key not in {XMI_ID, XMI_TYPE}
    }
    targets = [
        (name, value)
        for name, value in attributes.items()
        if name.startswith("base_")
    ]
    if len(targets) != 1:
        raise FactExtractionError(
            "FACT_APPLICATION_TARGET",
            f"{_local_name(element.tag)} must have exactly one base_* target",
        )
    target_property, target_value = targets[0]
    values = [
        {"property": name, "values": value.split()}
        for name, value in sorted(attributes.items())
        if not name.startswith("base_")
    ]
    return {
        "sourceHandle": _source_handle(element),
        "stereotypeNamespace": namespace,
        "stereotypeName": _local_name(element.tag),
        "targetProperty": target_property,
        "target": {
            "role": target_property,
            "form": "attribute",
            "sourceValue": target_value,
        },
        "values": values,
    }


def _extract_value_literal(element: ET.Element, role: str) -> dict[str, Any]:
    child = next(
        (item for item in element if _local_name(item.tag) == role),
        None,
    )
    if child is None:
        return {"present": False, "kind": None, "value": None}
    return {
        "present": True,
        "kind": child.get(XMI_TYPE),
        "value": child.get("value"),
    }


def _references(element: ET.Element, role: str) -> list[dict[str, str]]:
    result = []
    attribute = element.get(role)
    if attribute is not None:
        for value in attribute.split():
            result.append(
                {"role": role, "form": "attribute", "sourceValue": value}
            )
    for child in element:
        if _local_name(child.tag) != role:
            continue
        if child.get(XMI_IDREF):
            result.append(
                {
                    "role": role,
                    "form": "idref",
                    "sourceValue": child.get(XMI_IDREF),
                }
            )
        elif child.get("href"):
            result.append(
                {
                    "role": role,
                    "form": "href",
                    "sourceValue": child.get("href"),
                }
            )
        else:
            raise FactExtractionError(
                "FACT_REFERENCE_SHAPE",
                f"{role} has neither xmi:idref nor href",
            )
    return result


def _single_reference(
    element: ET.Element,
    role: str,
) -> dict[str, str] | None:
    references = _references(element, role)
    if not references:
        return None
    if len(references) != 1:
        raise FactExtractionError(
            "FACT_REFERENCE_CARDINALITY",
            f"{role} expected at most one target, got {len(references)}",
        )
    return references[0]


def _package_paths(model: ET.Element) -> dict[ET.Element, list[str]]:
    result: dict[ET.Element, list[str]] = {}

    def visit(element: ET.Element, path: list[str]) -> None:
        if _is_package(element):
            path = [*path, _required_name(element, "package")]
            result[element] = path
        for child in element:
            visit(child, path)

    visit(model, [])
    return result


def _owning_package(
    element: ET.Element,
    parent: dict[ET.Element, ET.Element],
) -> ET.Element:
    current = element
    while current in parent:
        current = parent[current]
        if _is_package(current):
            return current
    if _is_package(element):
        return element
    raise FactExtractionError("FACT_PACKAGE_OWNER", "element has no owning package")


def _is_package(element: ET.Element) -> bool:
    return element.get(XMI_TYPE) in {"uml:Profile", "uml:Package"}


def _presence_boolean(
    element: ET.Element,
    name: str,
    default: bool,
) -> dict[str, Any]:
    value = element.get(name)
    if value is None:
        return {"present": False, "value": default}
    if value not in {"true", "false"}:
        raise FactExtractionError(
            "FACT_BOOLEAN",
            f"{name} must be 'true' or 'false', got {value!r}",
        )
    return {"present": True, "value": value == "true"}


def _presence_string(element: ET.Element, name: str) -> dict[str, Any]:
    if name not in element.attrib:
        return {"present": False, "value": None}
    return {"present": True, "value": element.get(name)}


def _source_handle(element: ET.Element) -> str:
    value = element.get(XMI_ID)
    if not value:
        raise FactExtractionError(
            "FACT_SOURCE_HANDLE",
            f"{_local_name(element.tag)} has no xmi:id",
        )
    return value


def _required_name(element: ET.Element, kind: str) -> str:
    name = element.get("name")
    if not name:
        raise FactExtractionError("FACT_NAME", f"{kind} has no name")
    _check_name(name)
    return name


def _check_name(name: str) -> None:
    if IDENTITY_SEPARATOR in name:
        raise FactExtractionError(
            "FACT_NAME_SEPARATOR",
            f"name contains reserved separator {IDENTITY_SEPARATOR!r}: {name!r}",
        )


def _named_id(
    artifact_id: str,
    package_path: Iterable[str],
    kind: str,
    name: str,
) -> str:
    _check_name(name)
    segments = [artifact_id, *package_path, kind, name]
    return IDENTITY_SEPARATOR.join(segments)


def _assign_anonymous_declaration_ids(
    canonical: dict[str, Any],
    source_index: dict[tuple[str, str], str],
) -> None:
    for artifact in canonical["artifacts"]:
        for declaration in artifact["declarations"]:
            if declaration["name"] is not None:
                continue
            signature = {
                key: value
                for key, value in declaration.items()
                if key != "sourceHandle"
            }
            signature = _scrub_source_handles(
                signature,
                filename=artifact["filename"],
                source_index=source_index,
            )
            digest = hashlib.sha256(_canonical_json(signature).encode("utf-8")).hexdigest()
            declaration_id = IDENTITY_SEPARATOR.join(
                [
                    artifact["artifactId"],
                    *declaration["packagePath"],
                    declaration["kind"],
                    f"anonymous-{digest[:24]}",
                ]
            )
            key = (artifact["filename"], declaration["sourceHandle"])
            if declaration_id in source_index.values():
                raise FactExtractionError(
                    "FACT_ANONYMOUS_AMBIGUOUS",
                    f"anonymous declaration identity is ambiguous: {declaration_id}",
                )
            source_index[key] = declaration_id
            declaration["id"] = declaration_id


def _index_named_declaration_properties(
    canonical: dict[str, Any],
    source_index: dict[tuple[str, str], str],
) -> None:
    for artifact in canonical["artifacts"]:
        filename = artifact["filename"]
        for declaration in artifact["declarations"]:
            owner_id = declaration.get("id")
            if owner_id is None:
                continue
            for relation in ("properties", "ownedEnds"):
                _assign_property_ids(
                    declaration[relation],
                    owner_id,
                    relation,
                    filename,
                    source_index,
                )


def _assign_owned_ids(
    canonical: dict[str, Any],
    source_index: dict[tuple[str, str], str],
) -> None:
    for artifact in canonical["artifacts"]:
        filename = artifact["filename"]
        for declaration in artifact["declarations"]:
            owner_id = declaration["id"]
            for relation in ("properties", "ownedEnds"):
                if any("id" not in item for item in declaration[relation]):
                    _assign_property_ids(
                        declaration[relation],
                        owner_id,
                        relation,
                        filename,
                        source_index,
                    )
            for extension in declaration["extensions"]:
                digest = hashlib.sha256(
                    _canonical_json(
                        _scrub_source_handles(
                            {
                                key: value
                                for key, value in extension.items()
                                if key != "sourceHandle"
                            },
                            filename=filename,
                            source_index=source_index,
                        )
                    ).encode("utf-8")
                ).hexdigest()[:24]
                extension_id = f"{owner_id}::extension::{digest}"
                if extension_id in source_index.values():
                    raise FactExtractionError(
                        "FACT_EXTENSION_AMBIGUOUS",
                        f"Extension identity is ambiguous: {extension_id}",
                    )
                source_index[(filename, extension["sourceHandle"])] = extension_id
                extension["id"] = extension_id
                _assign_property_ids(
                    extension["ownedEnds"],
                    extension_id,
                    "ownedEnds",
                    filename,
                    source_index,
                )
            constraint_occurrences: dict[tuple[str, str], int] = {}
            for constraint in declaration["constraints"]:
                body_digest = hashlib.sha256(
                    _canonical_json(
                        {
                            "name": constraint["name"],
                            "bodyLines": constraint["bodyLines"],
                            "languages": constraint["languages"],
                        }
                    ).encode("utf-8")
                ).hexdigest()[:24]
                label = constraint["name"] or "anonymous"
                occurrence_key = (label, body_digest)
                occurrence = constraint_occurrences.get(occurrence_key, 0) + 1
                constraint_occurrences[occurrence_key] = occurrence
                constraint_id = (
                    f"{owner_id}::constraint::{label}::"
                    f"{body_digest}::{occurrence}"
                )
                source_index[(filename, constraint["sourceHandle"])] = constraint_id
                constraint["id"] = constraint_id
            for connector in declaration["connectors"]:
                digest = hashlib.sha256(
                    _canonical_json(
                        _scrub_source_handles(
                            connector["ends"],
                            filename=filename,
                            source_index=source_index,
                        )
                    ).encode("utf-8")
                ).hexdigest()[:24]
                connector_id = f"{owner_id}::connector::{digest}"
                if connector_id in source_index.values():
                    raise FactExtractionError(
                        "FACT_CONNECTOR_AMBIGUOUS",
                        f"Connector identity is ambiguous: {connector_id}",
                    )
                source_index[(filename, connector["sourceHandle"])] = connector_id
                connector["id"] = connector_id


def _assign_property_ids(
    properties: list[dict[str, Any]],
    owner_id: str,
    relation: str,
    filename: str,
    source_index: dict[tuple[str, str], str],
) -> None:
    seen: set[str] = set()
    for index, property_record in enumerate(properties, start=1):
        name = property_record["name"]
        if name is not None:
            _check_name(name)
            property_id = f"{owner_id}::{property_record['kind']}::{name}"
        elif relation == "ownedEnds":
            property_id = f"{owner_id}::ownedEnd::{index}"
        else:
            digest = hashlib.sha256(
                _canonical_json(
                    _scrub_source_handles(
                        {
                            key: value
                            for key, value in property_record.items()
                            if key != "sourceHandle"
                        }
                    )
                ).encode("utf-8")
            ).hexdigest()[:24]
            property_id = (
                f"{owner_id}::{property_record['kind']}::anonymous-{digest}"
            )
        if property_id in seen:
            raise FactExtractionError(
                "FACT_OWNED_ID_COLLISION",
                f"owned identity collision: {property_id}",
            )
        seen.add(property_id)
        source_index[(filename, property_record["sourceHandle"])] = property_id
        property_record["id"] = property_id


def _canonicalize_declaration(
    declaration: dict[str, Any],
    filename: str,
    filename_to_artifact: dict[str, dict[str, Any]],
    source_index: dict[tuple[str, str], str],
    external_index: dict[str, str],
) -> None:
    del declaration["sourceHandle"]
    declaration["comments"] = _canonicalize_comments(
        declaration["comments"],
        filename,
        filename_to_artifact,
        source_index,
        external_index,
    )
    declaration["generalizations"] = _sorted_references(
        declaration["generalizations"],
        filename,
        filename_to_artifact,
        source_index,
        external_index,
    )
    declaration["properties"] = _canonicalize_properties(
        declaration["properties"],
        filename,
        filename_to_artifact,
        source_index,
        external_index,
        ordered=False,
    )
    for extension in declaration["extensions"]:
        del extension["sourceHandle"]
        extension["memberEnds"] = [
            _canonical_reference(
                item,
                filename,
                filename_to_artifact,
                source_index,
                external_index,
            )
            for item in extension["memberEnds"]
        ]
        extension["navigableOwnedEnds"] = [
            _canonical_reference(
                item,
                filename,
                filename_to_artifact,
                source_index,
                external_index,
            )
            for item in extension["navigableOwnedEnds"]
        ]
        extension["ownedEnds"] = _canonicalize_properties(
            extension["ownedEnds"],
            filename,
            filename_to_artifact,
            source_index,
            external_index,
            ordered=True,
        )
        extension["comments"] = _canonicalize_comments(
            extension["comments"],
            filename,
            filename_to_artifact,
            source_index,
            external_index,
        )
    declaration["extensions"] = sorted(
        declaration["extensions"], key=lambda item: item["id"]
    )
    for constraint in declaration["constraints"]:
        del constraint["sourceHandle"]
        constraint["constrainedElements"] = [
            _canonical_reference(
                item,
                filename,
                filename_to_artifact,
                source_index,
                external_index,
            )
            for item in constraint["constrainedElements"]
        ]
        constraint["comments"] = _canonicalize_comments(
            constraint["comments"],
            filename,
            filename_to_artifact,
            source_index,
            external_index,
        )
    declaration["constraints"] = sorted(
        declaration["constraints"], key=lambda item: item["id"]
    )
    declaration["connectors"] = _canonicalize_connectors(
        declaration["connectors"],
        filename,
        filename_to_artifact,
        source_index,
        external_index,
    )
    declaration["memberEnds"] = [
        _canonical_reference(
            item,
            filename,
            filename_to_artifact,
            source_index,
            external_index,
        )
        for item in declaration["memberEnds"]
    ]
    declaration["ownedEnds"] = _canonicalize_properties(
        declaration["ownedEnds"],
        filename,
        filename_to_artifact,
        source_index,
        external_index,
        ordered=True,
    )
    declaration["navigableOwnedEnds"] = [
        _canonical_reference(
            item,
            filename,
            filename_to_artifact,
            source_index,
            external_index,
        )
        for item in declaration["navigableOwnedEnds"]
    ]
    declaration["icons"] = sorted(declaration["icons"], key=_canonical_json)


def _canonicalize_properties(
    properties: list[dict[str, Any]],
    filename: str,
    filename_to_artifact: dict[str, dict[str, Any]],
    source_index: dict[tuple[str, str], str],
    external_index: dict[str, str],
    *,
    ordered: bool,
) -> list[dict[str, Any]]:
    for property_record in properties:
        del property_record["sourceHandle"]
        if property_record["type"] is not None:
            property_record["type"] = _canonical_reference(
                property_record["type"],
                filename,
                filename_to_artifact,
                source_index,
                external_index,
            )
        property_record["subsettedProperties"] = _sorted_references(
            property_record["subsettedProperties"],
            filename,
            filename_to_artifact,
            source_index,
            external_index,
        )
        property_record["redefinedProperties"] = _sorted_references(
            property_record["redefinedProperties"],
            filename,
            filename_to_artifact,
            source_index,
            external_index,
        )
        property_record["comments"] = _canonicalize_comments(
            property_record["comments"],
            filename,
            filename_to_artifact,
            source_index,
            external_index,
        )
    if ordered:
        return properties
    return sorted(properties, key=lambda item: item["id"])


def _canonicalize_connectors(
    connectors: list[dict[str, Any]],
    filename: str,
    filename_to_artifact: dict[str, dict[str, Any]],
    source_index: dict[tuple[str, str], str],
    external_index: dict[str, str],
) -> list[dict[str, Any]]:
    for connector in connectors:
        del connector["sourceHandle"]
        for end in connector["ends"]:
            end["propertyPath"] = [
                _canonical_reference(
                    reference,
                    filename,
                    filename_to_artifact,
                    source_index,
                    external_index,
                )
                for reference in end["propertyPath"]
            ]
            end["role"] = _canonical_reference(
                end["role"],
                filename,
                filename_to_artifact,
                source_index,
                external_index,
            )
            if end["partWithPort"] is not None:
                end["partWithPort"] = _canonical_reference(
                    end["partWithPort"],
                    filename,
                    filename_to_artifact,
                    source_index,
                    external_index,
                )
        connector["comments"] = _canonicalize_comments(
            connector["comments"],
            filename,
            filename_to_artifact,
            source_index,
            external_index,
        )
    return sorted(connectors, key=lambda item: item["id"])


def _canonicalize_comments(
    comments: list[dict[str, Any]],
    filename: str,
    filename_to_artifact: dict[str, dict[str, Any]],
    source_index: dict[tuple[str, str], str],
    external_index: dict[str, str],
) -> list[dict[str, Any]]:
    for comment in comments:
        comment["annotatedElements"] = _sorted_references(
            comment["annotatedElements"],
            filename,
            filename_to_artifact,
            source_index,
            external_index,
        )
    return sorted(comments, key=_canonical_json)


def _canonicalize_applications(
    artifact: dict[str, Any],
    filename_to_artifact: dict[str, dict[str, Any]],
    source_index: dict[tuple[str, str], str],
    external_index: dict[str, str],
) -> None:
    filename = artifact["filename"]
    seen: dict[str, int] = {}
    for application in artifact["applications"]:
        target = _canonical_reference(
            application["target"],
            filename,
            filename_to_artifact,
            source_index,
            external_index,
        )
        base = IDENTITY_SEPARATOR.join(
            [
                application["stereotypeNamespace"],
                application["stereotypeName"],
                target["target"],
            ]
        )
        seen[base] = seen.get(base, 0) + 1
        application["id"] = f"{base}::application::{seen[base]}"
        application["target"] = target
        del application["sourceHandle"]


def _sorted_references(
    references: list[dict[str, str]],
    filename: str,
    filename_to_artifact: dict[str, dict[str, Any]],
    source_index: dict[tuple[str, str], str],
    external_index: dict[str, str],
) -> list[dict[str, str]]:
    result = [
        _canonical_reference(
            item,
            filename,
            filename_to_artifact,
            source_index,
            external_index,
        )
        for item in references
    ]
    return sorted(result, key=_canonical_json)


def _canonical_reference(
    reference: dict[str, str],
    filename: str,
    filename_to_artifact: dict[str, dict[str, Any]],
    source_index: dict[tuple[str, str], str],
    external_index: dict[str, str],
) -> dict[str, str]:
    value = reference["sourceValue"]
    if reference["form"] == "href":
        document, separator, fragment = value.partition("#")
        if not separator or not fragment:
            raise FactExtractionError(
                "FACT_HREF_FRAGMENT",
                f"href has no fragment: {value}",
            )
        target_filename = Path(urlsplit(document).path).name
        if target_filename in filename_to_artifact:
            key = (target_filename, fragment)
            if key not in source_index:
                raise FactExtractionError(
                    "FACT_REFERENCE_UNRESOLVED",
                    f"cannot resolve RAAML href target {value}",
                )
            target = source_index[key]
        else:
            target = external_index.get(value)
            if target is None:
                https_value = value.replace(
                    "http://www.omg.org/",
                    "https://www.omg.org/",
                    1,
                )
                target = external_index.get(https_value)
            if target is None and MAGICDRAW_ID.fullmatch(fragment):
                raise FactExtractionError(
                    "FACT_EXTERNAL_ID_UNRESOLVED",
                    f"external href fragment has no stable name: {value}",
                )
            if target is None:
                target = f"external::{document}::{fragment}"
    else:
        key = (filename, value)
        if key not in source_index:
            raise FactExtractionError(
                "FACT_REFERENCE_UNRESOLVED",
                f"cannot resolve local target {filename}#{value}",
            )
        target = source_index[key]
    return {
        "role": reference["role"],
        "sourceForm": reference["form"],
        "target": target,
    }


def _reject_source_ids(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"sourceHandle", "sourceValue"}:
                raise FactExtractionError(
                    "FACT_SOURCE_ID_LEAK",
                    f"canonical facts contain {key} at {path}",
                )
            _reject_source_ids(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_source_ids(child, f"{path}[{index}]")


def _scrub_source_handles(
    value: Any,
    *,
    filename: str | None = None,
    source_index: dict[tuple[str, str], str] | None = None,
) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            if key == "sourceHandle":
                continue
            if key == "sourceValue":
                target = None
                if filename is not None and source_index is not None:
                    target = source_index.get((filename, str(child)))
                if target is None and isinstance(child, str) and "#" in child:
                    document, _, fragment = child.partition("#")
                    if fragment and not MAGICDRAW_ID.fullmatch(fragment):
                        target = f"external::{document}::{fragment}"
                result[key] = target or "<unresolved-reference>"
            else:
                result[key] = _scrub_source_handles(
                    child,
                    filename=filename,
                    source_index=source_index,
                )
        return result
    if isinstance(value, list):
        return [
            _scrub_source_handles(
                item,
                filename=filename,
                source_index=source_index,
            )
            for item in value
        ]
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _namespace(tag: str) -> str:
    if not tag.startswith("{"):
        return ""
    return tag[1:].split("}", 1)[0]
