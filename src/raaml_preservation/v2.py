"""Native structural rendering of the bounded RAAML definition corpus."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def identifier(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]", "_", value)
    return f"_{value}" if not value or value[0].isdigit() else value


def validate_native_structure(
    facts: dict[str, Any], structure: dict[str, Any]
) -> list[str]:
    """Compare source obligations with the validator's resolved model."""
    model = NativeModel(facts)
    problems = []
    kinds = {
        "metadata def": "MetadataDefinition",
        "occurrence def": "OccurrenceDefinition",
        "part def": "PartDefinition",
        "attribute def": "AttributeDefinition",
        "constraint def": "ConstraintDefinition",
        "connection def": "ConnectionDefinition",
        "enum def": "EnumerationDefinition",
    }
    for key, declaration in model.declarations.items():
        path = "RaamlFullCorpus::" + model.names[key]
        actual = structure.get(path)
        if actual is None:
            problems.append(f"Missing definition: {path}")
            continue
        expected_abstract = (
            declaration["kind"] == "Enumeration" or declaration["isAbstract"]["value"]
        )
        if (
            actual["kind"] != kinds[model.kinds[key]]
            or actual["abstract"] != expected_abstract
        ):
            problems.append(f"Definition kind or abstractness differs: {path}")
        for ref in declaration["generalizations"]:
            if ref["target"] in model.names:
                expected = "RaamlFullCorpus::" + model.names[ref["target"]]
                if expected not in actual["supertypes"]:
                    problems.append(f"Missing generalization: {path} -> {expected}")
        for annotation in model.annotations.get(key, []):
            if (
                annotation not in model.abstract_stereotypes
                and "RaamlFullCorpus::" + annotation not in actual["annotations"]
            ):
                problems.append(f"Missing metadata annotation: {path} -> {annotation}")
        for prop in declaration["properties"]:
            if prop["isBase"]:
                continue
            name = path + "::" + (prop["name"] or identifier(prop["id"]))
            feature = structure.get(name)
            if feature is None:
                problems.append(f"Missing property: {name}")
                continue
            if model.kinds[key] != "connection def":
                expected_lower = (
                    model.literal(prop["lower"]) if prop["lower"]["present"] else "1"
                )
                expected_upper = (
                    model.literal(prop["upper"]) if prop["upper"]["present"] else "1"
                )
                if (feature.get("lower"), feature.get("upper")) != (
                    expected_lower,
                    expected_upper,
                ):
                    problems.append(f"Property multiplicity differs: {name}")
                if (feature["ordered"], feature["unique"]) != (
                    prop["isOrdered"]["value"],
                    prop["isUnique"]["value"],
                ):
                    problems.append(f"Property ordering or uniqueness differs: {name}")
                if feature["derived"] != prop["isDerived"]["value"]:
                    problems.append(f"Property derived status differs: {name}")
                if prop["default"]["present"] and feature.get(
                    "default"
                ) != model.literal(prop["default"]):
                    problems.append(f"Property default differs: {name}")
                for ref in prop["subsettedProperties"] + prop["redefinedProperties"]:
                    inherited = model.properties.get(ref["target"])
                    if inherited and not inherited["isBase"]:
                        expected = (
                            "RaamlFullCorpus::"
                            + model.names[model.owners[ref["target"]]]
                            + "::"
                            + (inherited["name"] or identifier(ref["target"]))
                        )
                        if expected not in feature["supertypes"]:
                            problems.append(
                                f"Missing property refinement: {name} -> {expected}"
                            )
            target = model.prop_type(prop)
            if target in model.names or (target and model.scalar(target)):
                expected_type = model.type_name(target)
                if target in model.names:
                    expected_type = "RaamlFullCorpus::" + expected_type
                if expected_type not in feature["types"]:
                    problems.append(f"Property type differs: {name}")
    return problems


class NativeModel:
    def __init__(self, facts: dict[str, Any]):
        if facts.get("schemaVersion") != "0.2.0":
            raise ValueError(
                "Native generation requires fact schema 0.2.0; re-extract the source files"
            )
        self.facts = facts
        self.declarations = {}
        self.properties = {}
        self.names = {}
        self.owners = {}
        for artifact in facts["artifacts"]:
            package = identifier(Path(artifact["filename"]).stem)
            for declaration in artifact["declarations"]:
                key = declaration["id"]
                self.declarations[key] = declaration
                self.names[key] = f"{package}::{identifier(declaration['name'] or key)}"
                for prop in declaration["properties"] + declaration["ownedEnds"]:
                    self.properties[prop["id"]] = prop
                    self.owners[prop["id"]] = key
        self.kinds = {key: self.kind(key) for key in self.declarations}
        self.abstract_stereotypes = {
            self.names[key]
            for key, declaration in self.declarations.items()
            if declaration["kind"] == "Stereotype"
            and declaration["isAbstract"]["value"]
        }
        stereotype_names = {}
        for artifact in facts["artifacts"]:
            for package in artifact["packages"]:
                if package["uri"]["value"]:
                    for declaration in artifact["declarations"]:
                        if declaration["kind"] == "Stereotype":
                            stereotype_names[
                                (package["uri"]["value"], declaration["name"])
                            ] = self.names[declaration["id"]]
        self.annotations: dict[str, list[str]] = {}
        for artifact in facts["artifacts"]:
            for app in artifact["applications"]:
                name = stereotype_names.get(
                    (app["stereotypeNamespace"], app["stereotypeName"])
                )
                if name is not None:
                    self.annotations.setdefault(app["target"]["target"], []).append(
                        name
                    )

    def kind(self, key: str) -> str:
        declaration = self.declarations[key]
        if declaration["kind"] == "Stereotype":
            return "metadata def"
        if declaration["kind"] == "Enumeration":
            return "enum def"
        if declaration.get("sysmlKind") == "ConstraintBlock":
            return "constraint def"
        if declaration["kind"] in {"Association", "AssociationClass"}:
            return "connection def"
        if declaration.get("sysmlKind") == "Block":
            return "part def"
        if any(self.scalar(ref["target"]) for ref in declaration["generalizations"]):
            return "attribute def"
        return "occurrence def"

    @staticmethod
    def scalar(target: str) -> str | None:
        if not target.startswith("external::"):
            return None
        if target.endswith("::ISO-80000_dataType.time"):
            return "ISQBase::DurationValue"
        name = target.rsplit("::", 1)[-1].removeprefix("SysML_dataType.")
        if name in {"Real", "Integer", "String", "Boolean", "UnlimitedNatural"}:
            return f"ScalarValues::{name}"
        return None

    def type_name(self, target: str) -> str:
        if target in self.names:
            return self.names[target]
        scalar = self.scalar(target)
        if scalar:
            return scalar
        metaclass = target.rsplit("::", 1)[-1]
        if metaclass == "Property":
            return "KerML::Feature"
        if metaclass == "Element":
            return "KerML::Element"
        raise ValueError(f"No native type mapping for {target}")

    def prop_name(self, key: str) -> str:
        name = self.properties[key]["name"] or identifier(key)
        return "'" + name.replace("\\", "\\\\").replace("'", "\\'") + "'"

    def prop_reference(self, key: str) -> str:
        return self.names[self.owners[key]] + "::" + self.prop_name(key)

    def prop_type(self, prop: dict[str, Any]) -> str | None:
        if prop["type"]:
            return prop["type"]["target"]
        for reference in prop["redefinedProperties"] + prop["subsettedProperties"]:
            if reference["target"] in self.properties:
                return self.prop_type(self.properties[reference["target"]])
        return None

    @staticmethod
    def literal(record: dict[str, Any], default: str = "0") -> str:
        value = record["value"]
        if record["kind"] == "uml:LiteralString":
            import json

            return json.dumps(value or "", ensure_ascii=False)
        if record["kind"] == "uml:LiteralBoolean":
            return value or "false"
        return value if value is not None else default

    def multiplicity(self, prop: dict[str, Any]) -> str:
        lower = self.literal(prop["lower"]) if prop["lower"]["present"] else "1"
        upper = self.literal(prop["upper"]) if prop["upper"]["present"] else "1"
        return f"[{lower}]" if lower == upper else f"[{lower}..{upper}]"

    def property_line(
        self, prop: dict[str, Any], owner: dict[str, Any], *, end: bool = False
    ) -> str:
        target = self.prop_type(prop)
        target_kind = self.kinds.get(target)
        scalar = target is not None and self.scalar(target) is not None
        if end:
            prefix = "end "
        elif target_kind == "constraint def":
            prefix = "constraint "
        elif target_kind == "metadata def" or (
            target and target.startswith("external::") and not scalar
        ):
            prefix = "ref "
        elif (
            scalar
            or target_kind in {"attribute def", "enum def"}
            or owner.get("sysmlKind") == "ConstraintBlock"
        ):
            prefix = "attribute "
        elif target is None:
            prefix = "ref "
        elif target_kind == "part def":
            prefix = "part "
        else:
            prefix = "occurrence "
        if (
            not end
            and prop["aggregation"]["value"] != "composite"
            and prefix in {"part ", "occurrence "}
        ):
            prefix = "ref " + prefix
        if not end and prop["isDerived"]["value"]:
            prefix = "derived " + prefix
        line = prefix + self.prop_name(prop["id"])
        if target:
            line += " : " + self.type_name(target)
        line += "[1]" if end else self.multiplicity(prop)
        if prop["isOrdered"]["value"]:
            line += " ordered"
        if not prop["isUnique"]["value"]:
            line += " nonunique"
        for relation, keyword in (
            ("subsettedProperties", "subsets"),
            ("redefinedProperties", "redefines"),
        ):
            references = (
                []
                if end
                else [
                    ref
                    for ref in prop[relation]
                    if ref["target"] in self.properties
                    and not self.properties[ref["target"]]["isBase"]
                ]
            )
            if references:
                line += (
                    " "
                    + keyword
                    + " "
                    + ", ".join(
                        self.prop_reference(ref["target"]) for ref in references
                    )
                )
        if prop["default"]["present"]:
            line += " default := " + self.literal(prop["default"])
        return line + ";"

    def endpoint(self, end: dict[str, Any]) -> str:
        path = [ref["target"] for ref in end.get("propertyPath", [])]
        if not path and end["partWithPort"]:
            path = [end["partWithPort"]["target"]]
        path.append(end["role"]["target"])
        return ".".join(self.prop_name(key) for key in path)

    def is_subtype(self, key: str, parent: str) -> bool:
        if key == parent:
            return True
        return any(
            ref["target"] in self.declarations
            and self.is_subtype(ref["target"], parent)
            for ref in self.declarations[key]["generalizations"]
        )

    def local_connector(self, owner: str, connector: dict[str, Any]) -> bool:
        for end in connector["ends"]:
            path = end.get("propertyPath", [])
            first = (
                path[0]["target"]
                if path
                else (
                    end["partWithPort"]["target"]
                    if end["partWithPort"]
                    else end["role"]["target"]
                )
            )
            if not self.is_subtype(owner, self.owners[first]):
                return False
        return True

    @staticmethod
    def documentation(comments: list[dict[str, Any]], indent: str) -> list[str]:
        return [
            indent + "doc /* " + comment["body"].replace("*/", "* /") + " */"
            for comment in comments
        ]

    def targets(self) -> list[dict[str, str]]:
        result = []
        for key, declaration in self.declarations.items():
            name = identifier(declaration["name"] or key)
            carrier = self.kinds[key]
            result.append(
                {
                    "canonicalId": key,
                    "carrier": carrier,
                    "declaration": f"{carrier} {name} {{",
                    "qualifiedName": "RaamlFullCorpus::" + self.names[key],
                }
            )
            for constraint in declaration["constraints"]:
                cname = identifier(f"{name}_{constraint['name'] or 'Constraint'}")
                result.append(
                    {
                        "canonicalId": constraint["id"],
                        "carrier": "constraint def",
                        "declaration": f"constraint def {cname} {{",
                        "qualifiedName": "RaamlFullCorpus::"
                        + self.names[key].rsplit("::", 1)[0]
                        + "::"
                        + cname,
                    }
                )
        return sorted(result, key=lambda item: item["canonicalId"])

    def notes(self) -> list[dict[str, str]]:
        notes = []
        for key, declaration in self.declarations.items():
            for constraint in declaration["constraints"]:
                notes.append(
                    {
                        "severity": "warning",
                        "code": "SOURCE_EXPRESSION_UNIMPLEMENTED",
                        "sourceId": constraint["id"],
                        "message": "Source expression is preserved as documentation and in the manifest; it is not executable SysML.",
                    }
                )
            for connector in declaration["connectors"]:
                if not self.local_connector(key, connector):
                    notes.append(
                        {
                            "severity": "warning",
                            "code": "SOURCE_CONNECTOR_CONTEXT",
                            "sourceId": connector["id"],
                            "message": "Source connector path is outside its owning type; retained in manifest without an invalid native binding.",
                        }
                    )
            for annotation in self.annotations.get(key, []):
                if annotation in self.abstract_stereotypes:
                    notes.append(
                        {
                            "severity": "warning",
                            "code": "SOURCE_ABSTRACT_ANNOTATION",
                            "sourceId": key,
                            "message": "Source applies an abstract stereotype; retained in manifest without instantiating abstract metadata.",
                        }
                    )
        return notes

    def render(self) -> str:
        lines = [
            "package RaamlFullCorpus {",
            "    private import ScalarValues::*;",
            "    metadata def Raaml_BaseAnnotation;",
            "    // Structural mapping only. Source constraint expressions below are not executable.",
        ]
        for artifact in self.facts["artifacts"]:
            lines.append(
                f"    package {identifier(Path(artifact['filename']).stem)} {{"
            )
            for declaration in artifact["declarations"]:
                key = declaration["id"]
                kind = self.kinds[key]
                name = identifier(declaration["name"] or key)
                abstract = "abstract " if declaration["isAbstract"]["value"] else ""
                annotations = self.annotations.get(key, [])
                if annotations and abstract:
                    lines.append("        abstract")
                    abstract = ""
                for annotation in annotations:
                    if annotation in self.abstract_stereotypes:
                        lines.append(
                            "        // UNMAPPED source annotation: abstract stereotype "
                            + annotation
                            + "; retained in manifest."
                        )
                    else:
                        lines.append("        #RaamlFullCorpus::" + annotation)
                bases = []
                for ref in declaration["generalizations"]:
                    target = ref["target"]
                    if target in self.names or self.scalar(target):
                        bases.append(self.type_name(target))
                if kind == "metadata def" and not bases:
                    bases.append("RaamlFullCorpus::Raaml_BaseAnnotation")
                heading = f"        {abstract}{kind} {name}"
                if bases:
                    heading += " :> " + ", ".join(bases)
                lines.append(heading + " {")
                lines.extend(
                    self.documentation(declaration["comments"], "            ")
                )
                external_bases = [
                    ref["target"]
                    for ref in declaration["generalizations"]
                    if ref["target"].startswith("external::")
                    and not self.scalar(ref["target"])
                ]
                for target in external_bases:
                    lines.append(
                        "            // V1 metaclass inheritance retained in manifest: "
                        + target
                    )
                if kind == "enum def":
                    lines.extend(
                        f"            {identifier(item['name'])};"
                        for item in declaration["literals"]
                    )
                else:
                    ends = {ref["target"] for ref in declaration["memberEnds"]}
                    props = declaration["properties"] + declaration["ownedEnds"]
                    for prop in props:
                        if prop["isBase"]:
                            continue
                        lines.extend(
                            self.documentation(prop["comments"], "            ")
                        )
                        if prop["kind"] == "Port":
                            lines.append(
                                "            // V1 ConstraintBlock port mapped to a value parameter."
                            )
                        if prop["isReadOnly"]["value"]:
                            lines.append(
                                "            // V1 read-only modifier retained in manifest."
                            )
                        lines.append(
                            "            "
                            + self.property_line(
                                prop,
                                declaration,
                                end=kind == "connection def" and prop["id"] in ends,
                            )
                        )
                    if kind == "connection def":
                        owned_ids = {prop["id"] for prop in props}
                        for ref in declaration["memberEnds"]:
                            if ref["target"] not in owned_ids:
                                prop = self.properties[ref["target"]]
                                lines.append(
                                    "            "
                                    + self.property_line(prop, declaration, end=True)
                                )
                    for connector in declaration["connectors"]:
                        if not self.local_connector(key, connector):
                            lines.append(
                                "            // UNMAPPED source connector: endpoint path is outside the owning type; retained in manifest."
                            )
                            continue
                        if len(connector["ends"]) != 2:
                            raise ValueError(
                                f"Only binary connectors are supported: {connector['id']}"
                            )
                        left, right = [self.endpoint(end) for end in connector["ends"]]
                        if connector.get("isBinding"):
                            lines.append(f"            bind {left} = {right};")
                        else:
                            lines.append(f"            connect {left} to {right};")
                lines.append("        }")
                for constraint in declaration["constraints"]:
                    cname = identifier(f"{name}_{constraint['name'] or 'Constraint'}")
                    lines.append(f"        constraint def {cname} {{")
                    text = (
                        "UNIMPLEMENTED source expression ("
                        + ", ".join(constraint["languages"] or ["unspecified language"])
                        + "). Preserved for review; not evaluated.\n"
                        + "\n".join(constraint["bodyLines"])
                    )
                    lines.extend(self.documentation([{"body": text}], "            "))
                    lines.append("        }")
            lines.append("    }")
        lines.append("}")
        return "\n".join(lines) + "\n"
