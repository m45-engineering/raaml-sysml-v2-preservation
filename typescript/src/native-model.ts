import path from "node:path";
import type {CanonicalRaamlFacts} from "./types.js";
import {RaamlPreservationError} from "./errors.js";

type RecordValue = Record<string, any>;
const identifier = (value: string): string => {
  const result = value.replace(/[^A-Za-z0-9_]/g, "_");
  return !result || /^\d/.test(result) ? `_${result}` : result;
};

export class NativeModel {
  private declarations = new Map<string, RecordValue>();
  private properties = new Map<string, RecordValue>();
  private names = new Map<string, string>();
  private owners = new Map<string, string>();
  private kinds = new Map<string, string>();
  private annotations = new Map<string, string[]>();

  constructor(private facts: CanonicalRaamlFacts) {
    if (facts.schemaVersion !== "0.2.0") throw new RaamlPreservationError("NATIVE_MAPPING", "Native generation requires fact schema 0.2.0; re-extract the source files");
    for (const artifact of facts.artifacts as RecordValue[]) {
      const packageName = identifier(path.parse(artifact.filename).name);
      for (const declaration of artifact.declarations as RecordValue[]) {
        const key = declaration.id;
        this.declarations.set(key, declaration);
        this.names.set(key, `${packageName}::${identifier(declaration.name ?? key)}`);
        for (const prop of [...declaration.properties, ...declaration.ownedEnds]) {
          this.properties.set(prop.id, prop);
          this.owners.set(prop.id, key);
        }
      }
    }
    for (const key of this.declarations.keys()) this.kinds.set(key, this.kind(key));
    const stereotypeNames = new Map<string, string>();
    for (const artifact of facts.artifacts as RecordValue[]) for (const pkg of artifact.packages) {
      if (pkg.uri.value) for (const declaration of artifact.declarations) {
        if (declaration.kind === "Stereotype") stereotypeNames.set(`${pkg.uri.value}\n${declaration.name}`, this.names.get(declaration.id)!);
      }
    }
    for (const artifact of facts.artifacts as RecordValue[]) for (const app of artifact.applications) {
      const name = stereotypeNames.get(`${app.stereotypeNamespace}\n${app.stereotypeName}`);
      if (!name) continue; // Per-source manifests do not contain the other profiles.
      const annotations = this.annotations.get(app.target.target) ?? [];
      annotations.push(name);
      this.annotations.set(app.target.target, annotations);
    }
  }

  private kind(key: string): string {
    const declaration = this.declarations.get(key)!;
    if (declaration.kind === "Stereotype") return "metadata def";
    if (declaration.kind === "Enumeration") return "enum def";
    if (declaration.sysmlKind === "ConstraintBlock") return "constraint def";
    if (["Association", "AssociationClass"].includes(declaration.kind)) return "connection def";
    if (declaration.sysmlKind === "Block") return "part def";
    if (declaration.generalizations.some((ref: RecordValue) => this.scalar(ref.target))) return "attribute def";
    return "occurrence def";
  }

  private scalar(target: string): string | undefined {
    if (!target.startsWith("external::")) return undefined;
    if (target.endsWith("::ISO-80000_dataType.time")) return "ISQBase::DurationValue";
    const name = target.split("::").at(-1)!.replace(/^SysML_dataType\./, "");
    return ["Real", "Integer", "String", "Boolean", "UnlimitedNatural"].includes(name) ? `ScalarValues::${name}` : undefined;
  }

  private typeName(target: string): string {
    const name = this.names.get(target) ?? this.scalar(target);
    if (name) return name;
    const metaclass = target.split("::").at(-1);
    if (metaclass === "Property") return "KerML::Feature";
    if (metaclass === "Element") return "KerML::Element";
    throw new RaamlPreservationError("NATIVE_MAPPING", `No native type mapping for ${target}`);
  }

  private propName(key: string): string {
    const name: string = this.properties.get(key)!.name ?? identifier(key);
    return `'${name.replaceAll("\\", "\\\\").replaceAll("'", "\\'")}'`;
  }

  private propReference(key: string): string {
    return `${this.names.get(this.owners.get(key)!)}::${this.propName(key)}`;
  }

  private propType(prop: RecordValue): string | undefined {
    if (prop.type) return prop.type.target;
    for (const ref of [...prop.redefinedProperties, ...prop.subsettedProperties]) {
      const original = this.properties.get(ref.target);
      if (original) return this.propType(original);
    }
    return undefined;
  }

  private literal(record: RecordValue, fallback = "0"): string {
    if (record.kind === "uml:LiteralString") return JSON.stringify(record.value ?? "");
    if (record.kind === "uml:LiteralBoolean") return record.value ?? "false";
    return record.value ?? fallback;
  }

  private multiplicity(prop: RecordValue): string {
    const lower = prop.lower.present ? this.literal(prop.lower) : "1";
    const upper = prop.upper.present ? this.literal(prop.upper) : "1";
    return lower === upper ? `[${lower}]` : `[${lower}..${upper}]`;
  }

  private propertyLine(prop: RecordValue, owner: RecordValue, end = false): string {
    const target = this.propType(prop);
    const targetKind = target ? this.kinds.get(target) : undefined;
    const scalar = target && this.scalar(target);
    let prefix: string;
    if (end) prefix = "end ";
    else if (targetKind === "constraint def") prefix = "constraint ";
    else if (targetKind === "metadata def" || (target?.startsWith("external::") && !scalar)) prefix = "ref ";
    else if (scalar || ["attribute def", "enum def"].includes(targetKind ?? "") || owner.sysmlKind === "ConstraintBlock") prefix = "attribute ";
    else if (!target) prefix = "ref ";
    else if (targetKind === "part def") prefix = "part ";
    else prefix = "occurrence ";
    if (!end && prop.aggregation.value !== "composite" && ["part ", "occurrence "].includes(prefix)) prefix = `ref ${prefix}`;
    if (!end && prop.isDerived.value) prefix = `derived ${prefix}`;
    let line = prefix + this.propName(prop.id);
    if (target) line += ` : ${this.typeName(target)}`;
    line += end ? "[1]" : this.multiplicity(prop);
    if (prop.isOrdered.value) line += " ordered";
    if (!prop.isUnique.value) line += " nonunique";
    for (const [relation, keyword] of [["subsettedProperties", "subsets"], ["redefinedProperties", "redefines"]]) {
      const refs = end ? [] : prop[relation!].filter((ref: RecordValue) => this.properties.has(ref.target) && !this.properties.get(ref.target)!.isBase);
      if (refs.length) line += ` ${keyword} ${refs.map((ref: RecordValue) => this.propReference(ref.target)).join(", ")}`;
    }
    if (prop.default.present) line += ` default := ${this.literal(prop.default)}`;
    return `${line};`;
  }

  private endpoint(end: RecordValue): string {
    let keys = (end.propertyPath ?? []).map((ref: RecordValue) => ref.target);
    if (!keys.length && end.partWithPort) keys = [end.partWithPort.target];
    keys.push(end.role.target);
    return keys.map((key: string) => this.propName(key)).join(".");
  }

  private isSubtype(key: string, parent: string): boolean {
    return key === parent || this.declarations.get(key)!.generalizations.some((ref: RecordValue) => this.declarations.has(ref.target) && this.isSubtype(ref.target, parent));
  }

  private localConnector(owner: string, connector: RecordValue): boolean {
    return connector.ends.every((end: RecordValue) => {
      const first = end.propertyPath?.[0]?.target ?? end.partWithPort?.target ?? end.role.target;
      return this.isSubtype(owner, this.owners.get(first)!);
    });
  }

  private documentation(comments: RecordValue[], indent: string): string[] {
    return comments.map((comment) => `${indent}doc /* ${comment.body.replaceAll("*/", "* /")} */`);
  }

  targets(): RecordValue[] {
    const result: RecordValue[] = [];
    for (const [key, declaration] of this.declarations) {
      const name = identifier(declaration.name ?? key);
      const carrier = this.kinds.get(key)!;
      result.push({canonicalId: key, carrier, declaration: `${carrier} ${name} {`, qualifiedName: `RaamlFullCorpus::${this.names.get(key)}`});
      for (const constraint of declaration.constraints) {
        const cname = identifier(`${name}_${constraint.name ?? "Constraint"}`);
        result.push({canonicalId: constraint.id, carrier: "constraint def", declaration: `constraint def ${cname} {`, qualifiedName: `RaamlFullCorpus::${this.names.get(key)!.split("::")[0]}::${cname}`});
      }
    }
    return result.sort((a, b) => a.canonicalId < b.canonicalId ? -1 : a.canonicalId > b.canonicalId ? 1 : 0);
  }

  notes(): RecordValue[] {
    const notes: RecordValue[] = [];
    for (const [key, declaration] of this.declarations) {
      for (const constraint of declaration.constraints) notes.push({severity: "warning", code: "SOURCE_EXPRESSION_UNIMPLEMENTED", sourceId: constraint.id, message: "Source expression is preserved as documentation and in the manifest; it is not executable SysML."});
      for (const connector of declaration.connectors) if (!this.localConnector(key, connector)) notes.push({severity: "warning", code: "SOURCE_CONNECTOR_CONTEXT", sourceId: connector.id, message: "Source connector path is outside its owning type; retained in manifest without an invalid native binding."});
      for (const annotation of this.annotations.get(key) ?? []) {
        if ([...this.declarations].some(([id, d]) => this.names.get(id) === annotation && d.kind === "Stereotype" && d.isAbstract.value)) notes.push({severity: "warning", code: "SOURCE_ABSTRACT_ANNOTATION", sourceId: key, message: "Source applies an abstract stereotype; retained in manifest without instantiating abstract metadata."});
      }
    }
    return notes;
  }

  render(): string {
    const lines = ["package RaamlFullCorpus {", "    private import ScalarValues::*;", "    metadata def Raaml_BaseAnnotation;", "    // Structural mapping only. Source constraint expressions below are not executable."];
    for (const artifact of this.facts.artifacts as RecordValue[]) {
      lines.push(`    package ${identifier(path.parse(artifact.filename).name)} {`);
      for (const declaration of artifact.declarations as RecordValue[]) {
        const key = declaration.id;
        const kind = this.kinds.get(key)!;
        const name = identifier(declaration.name ?? key);
        let abstract = declaration.isAbstract.value ? "abstract " : "";
        const annotations = this.annotations.get(key) ?? [];
        if (annotations.length && abstract) {
          lines.push("        abstract");
          abstract = "";
        }
        for (const annotation of annotations) {
          const abstract = [...this.declarations].some(([id, declaration]) => this.names.get(id) === annotation && declaration.kind === "Stereotype" && declaration.isAbstract.value);
          lines.push(abstract ? `        // UNMAPPED source annotation: abstract stereotype ${annotation}; retained in manifest.` : `        #RaamlFullCorpus::${annotation}`);
        }
        const bases = declaration.generalizations.filter((ref: RecordValue) => this.names.has(ref.target) || this.scalar(ref.target)).map((ref: RecordValue) => this.typeName(ref.target));
        if (kind === "metadata def" && !bases.length) bases.push("RaamlFullCorpus::Raaml_BaseAnnotation");
        lines.push(`        ${abstract}${kind} ${name}${bases.length ? ` :> ${bases.join(", ")}` : ""} {`);
        lines.push(...this.documentation(declaration.comments, "            "));
        for (const ref of declaration.generalizations as RecordValue[]) {
          if (ref.target.startsWith("external::") && !this.scalar(ref.target)) lines.push(`            // V1 metaclass inheritance retained in manifest: ${ref.target}`);
        }
        if (kind === "enum def") {
          lines.push(...declaration.literals.map((item: RecordValue) => `            ${identifier(item.name)};`));
        } else {
          const ends = new Set(declaration.memberEnds.map((ref: RecordValue) => ref.target));
          const props = [...declaration.properties, ...declaration.ownedEnds];
          for (const prop of props) {
            if (prop.isBase) continue;
            lines.push(...this.documentation(prop.comments, "            "));
            if (prop.kind === "Port") lines.push("            // V1 ConstraintBlock port mapped to a value parameter.");
            if (prop.isReadOnly.value) lines.push("            // V1 read-only modifier retained in manifest.");
            lines.push(`            ${this.propertyLine(prop, declaration, kind === "connection def" && ends.has(prop.id))}`);
          }
          if (kind === "connection def") {
            const owned = new Set(props.map((prop) => prop.id));
            for (const ref of declaration.memberEnds) if (!owned.has(ref.target)) lines.push(`            ${this.propertyLine(this.properties.get(ref.target)!, declaration, true)}`);
          }
          for (const connector of declaration.connectors) {
            if (!this.localConnector(key, connector)) {
              lines.push("            // UNMAPPED source connector: endpoint path is outside the owning type; retained in manifest.");
              continue;
            }
            if (connector.ends.length !== 2) throw new RaamlPreservationError("NATIVE_MAPPING", `Only binary connectors are supported: ${connector.id}`);
            const [left, right] = connector.ends.map((end: RecordValue) => this.endpoint(end));
            lines.push(connector.isBinding ? `            bind ${left} = ${right};` : `            connect ${left} to ${right};`);
          }
        }
        lines.push("        }");
        for (const constraint of declaration.constraints) {
          const cname = identifier(`${name}_${constraint.name ?? "Constraint"}`);
          lines.push(`        constraint def ${cname} {`);
          const text = `UNIMPLEMENTED source expression (${constraint.languages.length ? constraint.languages.join(", ") : "unspecified language"}). Preserved for review; not evaluated.\n${constraint.bodyLines.join("\n")}`;
          lines.push(...this.documentation([{body: text}], "            "));
          lines.push("        }");
        }
      }
      lines.push("    }");
    }
    lines.push("}");
    return `${lines.join("\n")}\n`;
  }
}
