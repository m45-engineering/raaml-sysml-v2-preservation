import path from "node:path";

import {RaamlPreservationError} from "./errors.js";
import {asciiCanonicalJson, sha256, type JsonValue} from "./json.js";
import type {CanonicalRaamlFacts, RawRaamlFacts} from "./types.js";

const IDENTITY_SEPARATOR = "::";
const MAGICDRAW_ID = /^_[A-Za-z0-9_]+$/;

type RecordValue = Record<string, any>;
type SourceIndex = Map<string, string>;

export function canonicalizeFacts(rawInput: RawRaamlFacts): CanonicalRaamlFacts {
  if (rawInput.documentKind !== "raw-raaml-facts") {
    fail("FACT_DOCUMENT_KIND", "expected raw-raaml-facts");
  }
  const canonical = structuredClone(rawInput) as unknown as RecordValue;
  canonical.documentKind = "canonical-raaml-facts";
  const sourceIndex: SourceIndex = new Map();
  const filenameToArtifact = new Map<string, RecordValue>(
    canonical.artifacts.map((artifact: RecordValue) => [
      artifact.filename as string,
      artifact,
    ]),
  );

  for (const artifact of canonical.artifacts as RecordValue[]) {
    for (const packageRecord of artifact.packages as RecordValue[]) {
      const packageId = namedId(
        artifact.artifactId,
        packageRecord.packagePath.slice(0, -1),
        packageRecord.kind,
        packageRecord.name,
      );
      sourceIndex.set(
        sourceKey(artifact.filename, packageRecord.sourceHandle),
        packageId,
      );
      packageRecord.id = packageId;
      delete packageRecord.sourceHandle;
    }
    for (const declaration of artifact.declarations as RecordValue[]) {
      if (declaration.name !== null) {
        const declarationId = namedId(
          artifact.artifactId,
          declaration.packagePath,
          declaration.kind,
          declaration.name,
        );
        sourceIndex.set(
          sourceKey(artifact.filename, declaration.sourceHandle),
          declarationId,
        );
        declaration.id = declarationId;
      }
    }
  }

  indexNamedDeclarationProperties(canonical, sourceIndex);
  assignAnonymousDeclarationIds(canonical, sourceIndex);
  assignOwnedIds(canonical, sourceIndex);

  const externalIndex = externalIdentityAliases();
  for (const artifact of canonical.artifacts as RecordValue[]) {
    const filename = artifact.filename as string;
    for (const declaration of artifact.declarations as RecordValue[]) {
      canonicalizeDeclaration(
        declaration,
        filename,
        filenameToArtifact,
        sourceIndex,
        externalIndex,
      );
    }
    for (const packageRecord of artifact.packages as RecordValue[]) {
      packageRecord.comments = canonicalizeComments(
        packageRecord.comments,
        filename,
        filenameToArtifact,
        sourceIndex,
        externalIndex,
      );
    }
    const machineryIds = new Set<string>();
    for (const machinery of artifact.machinery as RecordValue[]) {
      delete machinery.sourceHandle;
      machinery.targets = (machinery.targets as RecordValue[]).map((item) =>
        canonicalReference(
          item,
          filename,
          filenameToArtifact,
          sourceIndex,
          externalIndex,
        )
      );
      machinery.comments = canonicalizeComments(
        machinery.comments,
        filename,
        filenameToArtifact,
        sourceIndex,
        externalIndex,
      );
      const digest = sha256(asciiCanonicalJson({
        kind: machinery.kind,
        ownerPath: machinery.ownerPath,
        targets: machinery.targets,
        comments: machinery.comments,
      } as JsonValue)).slice(0, 24);
      machinery.id =
        `${artifact.artifactId}::machinery::${machinery.kind}::${digest}`;
      if (machineryIds.has(machinery.id)) {
        fail(
          "FACT_MACHINERY_AMBIGUOUS",
          `machinery identity is ambiguous: ${machinery.id}`,
        );
      }
      machineryIds.add(machinery.id);
    }
    canonicalizeApplications(
      artifact,
      filenameToArtifact,
      sourceIndex,
      externalIndex,
    );

    artifact.namespaces.sort(compareJson);
    artifact.packages.sort(compareById);
    artifact.declarations.sort(compareById);
    artifact.machinery.sort(compareById);
    artifact.applications.sort(compareById);
  }
  canonical.artifacts.sort(compareByArtifactId);
  rejectSourceIds(canonical);
  return canonical as CanonicalRaamlFacts;
}

function indexNamedDeclarationProperties(
  canonical: RecordValue,
  sourceIndex: SourceIndex,
): void {
  for (const artifact of canonical.artifacts as RecordValue[]) {
    for (const declaration of artifact.declarations as RecordValue[]) {
      if (!declaration.id) {
        continue;
      }
      for (const relation of ["properties", "ownedEnds"]) {
        assignPropertyIds(
          declaration[relation],
          declaration.id,
          relation,
          artifact.filename,
          sourceIndex,
        );
      }
    }
  }
}

function assignAnonymousDeclarationIds(
  canonical: RecordValue,
  sourceIndex: SourceIndex,
): void {
  for (const artifact of canonical.artifacts as RecordValue[]) {
    for (const declaration of artifact.declarations as RecordValue[]) {
      if (declaration.name !== null) {
        continue;
      }
      const signature = scrubSourceHandles(
        without(declaration, "sourceHandle"),
        artifact.filename,
        sourceIndex,
      );
      const digest = sha256(asciiCanonicalJson(signature as JsonValue));
      const declarationId = [
        artifact.artifactId,
        ...declaration.packagePath,
        declaration.kind,
        `anonymous-${digest.slice(0, 24)}`,
      ].join(IDENTITY_SEPARATOR);
      if ([...sourceIndex.values()].includes(declarationId)) {
        fail(
          "FACT_ANONYMOUS_AMBIGUOUS",
          `anonymous declaration identity is ambiguous: ${declarationId}`,
        );
      }
      sourceIndex.set(
        sourceKey(artifact.filename, declaration.sourceHandle),
        declarationId,
      );
      declaration.id = declarationId;
    }
  }
}

function assignOwnedIds(
  canonical: RecordValue,
  sourceIndex: SourceIndex,
): void {
  for (const artifact of canonical.artifacts as RecordValue[]) {
    const filename = artifact.filename as string;
    for (const declaration of artifact.declarations as RecordValue[]) {
      const ownerId = declaration.id as string;
      for (const relation of ["properties", "ownedEnds"]) {
        if ((declaration[relation] as RecordValue[]).some((item) => !item.id)) {
          assignPropertyIds(
            declaration[relation],
            ownerId,
            relation,
            filename,
            sourceIndex,
          );
        }
      }
      for (const extension of declaration.extensions as RecordValue[]) {
        const signature = scrubSourceHandles(
          without(extension, "sourceHandle"),
          filename,
          sourceIndex,
        );
        const digest = sha256(asciiCanonicalJson(signature as JsonValue)).slice(0, 24);
        const extensionId = `${ownerId}::extension::${digest}`;
        if ([...sourceIndex.values()].includes(extensionId)) {
          fail(
            "FACT_EXTENSION_AMBIGUOUS",
            `Extension identity is ambiguous: ${extensionId}`,
          );
        }
        sourceIndex.set(
          sourceKey(filename, extension.sourceHandle),
          extensionId,
        );
        extension.id = extensionId;
        assignPropertyIds(
          extension.ownedEnds,
          extensionId,
          "ownedEnds",
          filename,
          sourceIndex,
        );
      }
      const constraintOccurrences = new Map<string, number>();
      for (const constraint of declaration.constraints as RecordValue[]) {
        const bodyDigest = sha256(asciiCanonicalJson({
          name: constraint.name,
          bodyLines: constraint.bodyLines,
          languages: constraint.languages,
        } as JsonValue)).slice(0, 24);
        const label = constraint.name ?? "anonymous";
        const occurrenceKey = `${label}\0${bodyDigest}`;
        const occurrence = (constraintOccurrences.get(occurrenceKey) ?? 0) + 1;
        constraintOccurrences.set(occurrenceKey, occurrence);
        const constraintId =
          `${ownerId}::constraint::${label}::${bodyDigest}::${occurrence}`;
        sourceIndex.set(
          sourceKey(filename, constraint.sourceHandle),
          constraintId,
        );
        constraint.id = constraintId;
      }
      for (const connector of declaration.connectors as RecordValue[]) {
        const digest = sha256(asciiCanonicalJson(
          scrubSourceHandles(
            connector.ends,
            filename,
            sourceIndex,
          ) as JsonValue,
        )).slice(0, 24);
        const connectorId = `${ownerId}::connector::${digest}`;
        if ([...sourceIndex.values()].includes(connectorId)) {
          fail(
            "FACT_CONNECTOR_AMBIGUOUS",
            `Connector identity is ambiguous: ${connectorId}`,
          );
        }
        sourceIndex.set(
          sourceKey(filename, connector.sourceHandle),
          connectorId,
        );
        connector.id = connectorId;
      }
    }
  }
}

function assignPropertyIds(
  properties: RecordValue[],
  ownerId: string,
  relation: string,
  filename: string,
  sourceIndex: SourceIndex,
): void {
  const seen = new Set<string>();
  properties.forEach((propertyRecord, offset) => {
    let propertyId: string;
    if (propertyRecord.name !== null) {
      checkName(propertyRecord.name);
      propertyId = `${ownerId}::${propertyRecord.kind}::${propertyRecord.name}`;
    } else if (relation === "ownedEnds") {
      propertyId = `${ownerId}::ownedEnd::${offset + 1}`;
    } else {
      const signature = scrubSourceHandles(
        without(propertyRecord, "sourceHandle"),
      );
      const digest = sha256(asciiCanonicalJson(signature as JsonValue)).slice(0, 24);
      propertyId = `${ownerId}::${propertyRecord.kind}::anonymous-${digest}`;
    }
    if (seen.has(propertyId)) {
      fail("FACT_OWNED_ID_COLLISION", `owned identity collision: ${propertyId}`);
    }
    seen.add(propertyId);
    sourceIndex.set(
      sourceKey(filename, propertyRecord.sourceHandle),
      propertyId,
    );
    propertyRecord.id = propertyId;
  });
}

function canonicalizeDeclaration(
  declaration: RecordValue,
  filename: string,
  filenameToArtifact: ReadonlyMap<string, RecordValue>,
  sourceIndex: SourceIndex,
  externalIndex: ReadonlyMap<string, string>,
): void {
  delete declaration.sourceHandle;
  declaration.comments = canonicalizeComments(
    declaration.comments,
    filename,
    filenameToArtifact,
    sourceIndex,
    externalIndex,
  );
  declaration.generalizations = sortedReferences(
    declaration.generalizations,
    filename,
    filenameToArtifact,
    sourceIndex,
    externalIndex,
  );
  declaration.properties = canonicalizeProperties(
    declaration.properties,
    filename,
    filenameToArtifact,
    sourceIndex,
    externalIndex,
    false,
  );
  for (const extension of declaration.extensions as RecordValue[]) {
    delete extension.sourceHandle;
    extension.memberEnds = canonicalReferences(
      extension.memberEnds,
      filename,
      filenameToArtifact,
      sourceIndex,
      externalIndex,
    );
    extension.navigableOwnedEnds = canonicalReferences(
      extension.navigableOwnedEnds,
      filename,
      filenameToArtifact,
      sourceIndex,
      externalIndex,
    );
    extension.ownedEnds = canonicalizeProperties(
      extension.ownedEnds,
      filename,
      filenameToArtifact,
      sourceIndex,
      externalIndex,
      true,
    );
    extension.comments = canonicalizeComments(
      extension.comments,
      filename,
      filenameToArtifact,
      sourceIndex,
      externalIndex,
    );
  }
  declaration.extensions.sort(compareById);
  for (const constraint of declaration.constraints as RecordValue[]) {
    delete constraint.sourceHandle;
    constraint.constrainedElements = canonicalReferences(
      constraint.constrainedElements,
      filename,
      filenameToArtifact,
      sourceIndex,
      externalIndex,
    );
    constraint.comments = canonicalizeComments(
      constraint.comments,
      filename,
      filenameToArtifact,
      sourceIndex,
      externalIndex,
    );
  }
  declaration.constraints.sort(compareById);
  declaration.connectors = canonicalizeConnectors(
    declaration.connectors,
    filename,
    filenameToArtifact,
    sourceIndex,
    externalIndex,
  );
  declaration.memberEnds = canonicalReferences(
    declaration.memberEnds,
    filename,
    filenameToArtifact,
    sourceIndex,
    externalIndex,
  );
  declaration.ownedEnds = canonicalizeProperties(
    declaration.ownedEnds,
    filename,
    filenameToArtifact,
    sourceIndex,
    externalIndex,
    true,
  );
  declaration.navigableOwnedEnds = canonicalReferences(
    declaration.navigableOwnedEnds,
    filename,
    filenameToArtifact,
    sourceIndex,
    externalIndex,
  );
  declaration.icons.sort(compareJson);
}

function canonicalizeProperties(
  properties: RecordValue[],
  filename: string,
  filenameToArtifact: ReadonlyMap<string, RecordValue>,
  sourceIndex: SourceIndex,
  externalIndex: ReadonlyMap<string, string>,
  ordered: boolean,
): RecordValue[] {
  for (const propertyRecord of properties) {
    delete propertyRecord.sourceHandle;
    if (propertyRecord.type !== null) {
      propertyRecord.type = canonicalReference(
        propertyRecord.type,
        filename,
        filenameToArtifact,
        sourceIndex,
        externalIndex,
      );
    }
    propertyRecord.subsettedProperties = sortedReferences(
      propertyRecord.subsettedProperties,
      filename,
      filenameToArtifact,
      sourceIndex,
      externalIndex,
    );
    propertyRecord.redefinedProperties = sortedReferences(
      propertyRecord.redefinedProperties,
      filename,
      filenameToArtifact,
      sourceIndex,
      externalIndex,
    );
    propertyRecord.comments = canonicalizeComments(
      propertyRecord.comments,
      filename,
      filenameToArtifact,
      sourceIndex,
      externalIndex,
    );
  }
  return ordered ? properties : properties.sort(compareById);
}

function canonicalizeConnectors(
  connectors: RecordValue[],
  filename: string,
  filenameToArtifact: ReadonlyMap<string, RecordValue>,
  sourceIndex: SourceIndex,
  externalIndex: ReadonlyMap<string, string>,
): RecordValue[] {
  for (const connector of connectors) {
    delete connector.sourceHandle;
    for (const end of connector.ends as RecordValue[]) {
      end.propertyPath = end.propertyPath.map((reference: RecordValue) => canonicalReference(reference, filename, filenameToArtifact, sourceIndex, externalIndex));
      end.role = canonicalReference(
        end.role,
        filename,
        filenameToArtifact,
        sourceIndex,
        externalIndex,
      );
      if (end.partWithPort !== null) {
        end.partWithPort = canonicalReference(
          end.partWithPort,
          filename,
          filenameToArtifact,
          sourceIndex,
          externalIndex,
        );
      }
    }
    connector.comments = canonicalizeComments(
      connector.comments,
      filename,
      filenameToArtifact,
      sourceIndex,
      externalIndex,
    );
  }
  return connectors.sort(compareById);
}

function canonicalizeComments(
  comments: RecordValue[],
  filename: string,
  filenameToArtifact: ReadonlyMap<string, RecordValue>,
  sourceIndex: SourceIndex,
  externalIndex: ReadonlyMap<string, string>,
): RecordValue[] {
  for (const comment of comments) {
    comment.annotatedElements = sortedReferences(
      comment.annotatedElements,
      filename,
      filenameToArtifact,
      sourceIndex,
      externalIndex,
    );
  }
  return comments.sort(compareJson);
}

function canonicalizeApplications(
  artifact: RecordValue,
  filenameToArtifact: ReadonlyMap<string, RecordValue>,
  sourceIndex: SourceIndex,
  externalIndex: ReadonlyMap<string, string>,
): void {
  const seen = new Map<string, number>();
  for (const application of artifact.applications as RecordValue[]) {
    const target = canonicalReference(
      application.target,
      artifact.filename,
      filenameToArtifact,
      sourceIndex,
      externalIndex,
    );
    const base = [
      application.stereotypeNamespace,
      application.stereotypeName,
      target.target,
    ].join(IDENTITY_SEPARATOR);
    const occurrence = (seen.get(base) ?? 0) + 1;
    seen.set(base, occurrence);
    application.id = `${base}::application::${occurrence}`;
    application.target = target;
    delete application.sourceHandle;
  }
}

function sortedReferences(
  references: RecordValue[],
  filename: string,
  filenameToArtifact: ReadonlyMap<string, RecordValue>,
  sourceIndex: SourceIndex,
  externalIndex: ReadonlyMap<string, string>,
): RecordValue[] {
  return canonicalReferences(
    references,
    filename,
    filenameToArtifact,
    sourceIndex,
    externalIndex,
  ).sort(compareJson);
}

function canonicalReferences(
  references: RecordValue[],
  filename: string,
  filenameToArtifact: ReadonlyMap<string, RecordValue>,
  sourceIndex: SourceIndex,
  externalIndex: ReadonlyMap<string, string>,
): RecordValue[] {
  return references.map((reference) =>
    canonicalReference(
      reference,
      filename,
      filenameToArtifact,
      sourceIndex,
      externalIndex,
    )
  );
}

function canonicalReference(
  reference: RecordValue,
  filename: string,
  filenameToArtifact: ReadonlyMap<string, RecordValue>,
  sourceIndex: SourceIndex,
  externalIndex: ReadonlyMap<string, string>,
): RecordValue {
  const value = reference.sourceValue as string;
  let target: string | undefined;
  if (reference.form === "href") {
    const separator = value.indexOf("#");
    if (separator < 0 || separator === value.length - 1) {
      fail("FACT_HREF_FRAGMENT", `href has no fragment: ${value}`);
    }
    const document = value.slice(0, separator);
    const fragment = value.slice(separator + 1);
    const targetFilename = path.posix.basename(
      document.includes("://") ? new URL(document).pathname : document,
    );
    if (filenameToArtifact.has(targetFilename)) {
      target = sourceIndex.get(sourceKey(targetFilename, fragment));
      if (!target) {
        fail(
          "FACT_REFERENCE_UNRESOLVED",
          `cannot resolve RAAML href target ${value}`,
        );
      }
    } else {
      target = externalIndex.get(value) ??
        externalIndex.get(
          value.replace("http://www.omg.org/", "https://www.omg.org/"),
        );
      if (!target && MAGICDRAW_ID.test(fragment)) {
        fail(
          "FACT_EXTERNAL_ID_UNRESOLVED",
          `external href fragment has no stable name: ${value}`,
        );
      }
      target ??= `external::${document}::${fragment}`;
    }
  } else {
    target = sourceIndex.get(sourceKey(filename, value));
    if (!target) {
      fail(
        "FACT_REFERENCE_UNRESOLVED",
        `cannot resolve local target ${filename}#${value}`,
      );
    }
  }
  return {
    role: reference.role,
    sourceForm: reference.form,
    target,
  };
}

function scrubSourceHandles(
  value: any,
  filename?: string,
  sourceIndex?: SourceIndex,
): any {
  if (Array.isArray(value)) {
    return value.map((item) => scrubSourceHandles(item, filename, sourceIndex));
  }
  if (value !== null && typeof value === "object") {
    const result: RecordValue = {};
    for (const [key, child] of Object.entries(value)) {
      if (key === "sourceHandle") {
        continue;
      }
      if (key === "sourceValue") {
        let target = filename && sourceIndex
          ? sourceIndex.get(sourceKey(filename, String(child)))
          : undefined;
        if (!target && typeof child === "string" && child.includes("#")) {
          const separator = child.indexOf("#");
          const document = child.slice(0, separator);
          const fragment = child.slice(separator + 1);
          if (fragment && !MAGICDRAW_ID.test(fragment)) {
            target = `external::${document}::${fragment}`;
          }
        }
        result[key] = target ?? "<unresolved-reference>";
      } else {
        result[key] = scrubSourceHandles(child, filename, sourceIndex);
      }
    }
    return result;
  }
  return value;
}

function rejectSourceIds(value: any, currentPath = "$"): void {
  if (Array.isArray(value)) {
    value.forEach((child, index) =>
      rejectSourceIds(child, `${currentPath}[${index}]`)
    );
    return;
  }
  if (value !== null && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      if (key === "sourceHandle" || key === "sourceValue") {
        fail(
          "FACT_SOURCE_ID_LEAK",
          `canonical facts contain ${key} at ${currentPath}`,
        );
      }
      rejectSourceIds(child, `${currentPath}.${key}`);
    }
  }
}

function externalIdentityAliases(): ReadonlyMap<string, string> {
  const document = "https://www.omg.org/spec/UML/20161101/UML.xmi";
  const target = `external::${document}::Package::UML`;
  return new Map([
    [`${document}#_0`, target],
    [`${document.replace("https://", "http://")}#_0`, target],
  ]);
}

function namedId(
  artifactId: string,
  packagePath: string[],
  kind: string,
  name: string,
): string {
  checkName(name);
  return [artifactId, ...packagePath, kind, name].join(IDENTITY_SEPARATOR);
}

function checkName(name: string): void {
  if (name.includes(IDENTITY_SEPARATOR)) {
    fail(
      "FACT_NAME_SEPARATOR",
      `name contains reserved separator '${IDENTITY_SEPARATOR}': ${name}`,
    );
  }
}

function without(value: RecordValue, key: string): RecordValue {
  return Object.fromEntries(
    Object.entries(value).filter(([candidate]) => candidate !== key),
  );
}

function sourceKey(filename: string, sourceHandle: string): string {
  return `${filename}\0${sourceHandle}`;
}

function compareById(left: RecordValue, right: RecordValue): number {
  return compare(left.id, right.id);
}

function compareByArtifactId(left: RecordValue, right: RecordValue): number {
  return compare(left.artifactId, right.artifactId);
}

function compareJson(left: any, right: any): number {
  return compare(
    asciiCanonicalJson(left as JsonValue),
    asciiCanonicalJson(right as JsonValue),
  );
}

function compare(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function fail(code: string, message: string): never {
  throw new RaamlPreservationError(code, message);
}
