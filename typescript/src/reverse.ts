import path from "node:path";

import {RaamlPreservationError} from "./errors.js";
import {sha256, stableJson, type JsonObject, type JsonValue} from "./json.js";
import {
  FULL_CORPUS_V2_FILENAME,
  type PreservationManifest,
} from "./forward.js";
import type {CanonicalRaamlFacts, StandardsLock} from "./types.js";
import {
  appendXml,
  serializeXml,
  xmlElement,
  type XmlOutputNode,
} from "./xml-write.js";

const FULL_CORPUS_ID = "milestone-4-full-corpus";
const XMI = "http://www.omg.org/spec/XMI/20131001";
const UML = "http://www.omg.org/spec/UML/20161101";
const MOFEXT = "http://www.omg.org/spec/MOF/20131001";

type RecordValue = Record<string, any>;

export interface ReverseInput {
  readonly lock: StandardsLock;
  readonly sysml: string;
  readonly manifests: ReadonlyMap<string, PreservationManifest>;
}

export interface ReverseResult {
  readonly artifacts: ReadonlyMap<string, Uint8Array>;
  readonly canonical: CanonicalRaamlFacts;
}

export function reverse(input: ReverseInput): ReverseResult {
  const expected = new Map(
    input.lock.artifacts
      .filter((artifact) => artifact.collection === "raaml-1.1-definitions")
      .map((artifact) => [artifact.filename, artifact]),
  );
  if (expected.size !== 17 || input.manifests.size !== expected.size) {
    fail(
      "FULL_CORPUS_MANIFEST_COUNT",
      `expected ${expected.size} manifests, got ${input.manifests.size}`,
    );
  }

  const artifacts: RecordValue[] = [];
  const seen = new Set<string>();
  let sharedMetadata: string | undefined;
  for (
    const [manifestFilename, manifest] of [...input.manifests].sort(
      ([left], [right]) => compare(left, right),
    )
  ) {
    const facts = verifyManifest(manifest);
    const payload = manifest.payload as RecordValue;
    verifyNativeTargets(payload, input.sysml);
    const filename = payload.sourceFilename as string;
    if (seen.has(filename)) {
      fail(
        "FULL_CORPUS_MANIFEST_DUPLICATE",
        `duplicate manifest for ${filename}`,
      );
    }
    seen.add(filename);
    const locked = expected.get(filename);
    if (!locked) {
      fail(
        "FULL_CORPUS_MANIFEST_UNKNOWN",
        `manifest is not for a locked RAAML artifact: ${filename}`,
      );
    }
    if (
      payload.artifactId !== locked.id ||
      payload.sourceSha256 !== locked.sha256
    ) {
      fail(
        "FULL_CORPUS_MANIFEST_LOCK",
        `manifest identity does not match standards.lock.json: ${manifestFilename}`,
      );
    }

    const scoped = structuredClone(facts) as CanonicalRaamlFacts;
    const artifact = scoped.artifacts[0] as RecordValue | undefined;
    if (!artifact || scoped.artifacts.length !== 1) {
      fail(
        "MANIFEST_ARTIFACT_COUNT",
        "full-corpus manifest must contain exactly one source artifact",
      );
    }
    (scoped.artifacts as RecordValue[]).splice(0, 1);
    const metadata = stableJson(scoped);
    if (sharedMetadata === undefined) {
      sharedMetadata = metadata;
    } else if (metadata !== sharedMetadata) {
      fail(
        "FULL_CORPUS_FACTS_INCONSISTENT",
        "manifests disagree on shared canonical-fact metadata",
      );
    }
    artifacts.push(artifact);
  }

  const missing = [...expected.keys()].filter((filename) => !seen.has(filename));
  if (missing.length > 0) {
    fail(
      "FULL_CORPUS_MANIFEST_MISSING",
      `missing manifest(s): ${missing.join(", ")}`,
    );
  }
  artifacts.sort((left, right) => compare(left.artifactId, right.artifactId));
  const canonical: CanonicalRaamlFacts = {
    schemaVersion: "0.2.0",
    documentKind: "canonical-raaml-facts",
    corpus: "raaml-1.1-definitions",
    artifacts,
  };
  const context = new RenderContext(canonical);
  const reconstructed = new Map<string, Uint8Array>();
  for (const artifact of artifacts) {
    reconstructed.set(
      artifact.filename,
      renderV1Artifact(canonical, artifact, context),
    );
  }
  return {artifacts: reconstructed, canonical};
}

function verifyManifest(
  manifest: PreservationManifest,
): CanonicalRaamlFacts {
  if (manifest.schemaVersion !== "0.2.0") {
    fail("MANIFEST_VERSION", "unsupported manifest version");
  }
  if (manifest.documentKind !== "raaml-preservation-manifest") {
    fail("MANIFEST_KIND", "unexpected manifest document kind");
  }
  const payload = manifest.payload as RecordValue;
  if (manifest.payloadSha256 !== sha256(stableJson(payload))) {
    fail("MANIFEST_DIGEST", "manifest payload does not match payloadSha256");
  }
  if (payload.scopeId !== FULL_CORPUS_ID) {
    fail("MANIFEST_SCOPE", "unexpected full-corpus scope");
  }
  if (payload.v2Filename !== FULL_CORPUS_V2_FILENAME) {
    fail("MANIFEST_V2_FILENAME", "unexpected SysML v2 filename");
  }
  const facts = payload.canonicalFacts as CanonicalRaamlFacts | undefined;
  if (!facts || facts.documentKind !== "canonical-raaml-facts") {
    fail("MANIFEST_FACTS", "canonical facts are missing");
  }
  const artifact = facts.artifacts[0] as RecordValue | undefined;
  if (!artifact || facts.artifacts.length !== 1) {
    fail(
      "MANIFEST_ARTIFACT_COUNT",
      "full-corpus manifest must contain exactly one source artifact",
    );
  }
  if (
    payload.artifactId !== artifact.artifactId ||
    payload.sourceFilename !== artifact.filename ||
    payload.sourceSha256 !== artifact.sha256
  ) {
    fail("MANIFEST_ARTIFACT_ID", "manifest artifact identity mismatch");
  }
  return facts;
}

function verifyNativeTargets(payload: RecordValue, sysml: string): void {
  if (sha256(sysml) !== payload.v2Sha256) {
    fail("V2_DIGEST", "SysML v2 model does not match the manifest v2Sha256");
  }
  const targets = payload.nativeTargets as RecordValue[];
  if (!Array.isArray(targets)) {
    fail("MANIFEST_NATIVE_TARGETS", "nativeTargets is missing");
  }
  const missing: string[] = [];
  for (const target of targets) {
    const qualifiedName = target.qualifiedName as string;
    const carrier = target.carrier as string;
    const parts = qualifiedName?.split("::");
    if (!parts || parts.length !== 3 || !carrier) {
      fail(
        "MANIFEST_NATIVE_TARGET",
        `invalid qualified native target: ${qualifiedName}`,
      );
    }
    const [root, packageName, name] = parts as [string, string, string];
    if (!sysml.startsWith(`package ${root} {\n`)) {
      missing.push(qualifiedName);
      continue;
    }
    const marker = `    package ${packageName} {\n`;
    const start = sysml.indexOf(marker);
    if (start < 0) {
      missing.push(qualifiedName);
      continue;
    }
    const bodyStart = start + marker.length;
    const nextPackage = sysml.indexOf("\n    package ", bodyStart);
    const rootEnd = sysml.lastIndexOf("\n}");
    const body = sysml.slice(
      bodyStart,
      nextPackage >= 0 ? nextPackage : rootEnd,
    );
    const declaration = new RegExp(
      `^        (?:abstract )?${escapeRegex(carrier)} ${escapeRegex(name)}(?:\\s|;|\\{)`,
      "gm",
    );
    if ([...body.matchAll(declaration)].length !== 1) {
      missing.push(qualifiedName);
    }
  }
  if (missing.length > 0) {
    fail(
      "V2_TARGET_MISSING",
      `qualified v2 target mismatch: ${missing.slice(0, 3).join(", ")}`,
    );
  }
}

function renderV1Artifact(
  canonical: CanonicalRaamlFacts,
  artifact: RecordValue,
  context: RenderContext,
): Uint8Array {
  const namespaceByUri = namespacePrefixes(canonical);
  const rootAttributes: Record<string, string> = {
    "xmlns:xmi": XMI,
    "xmlns:uml": UML,
    "xmlns:mofext": MOFEXT,
  };
  for (const [uri, prefix] of namespaceByUri) {
    rootAttributes[`xmlns:${prefix}`] = uri;
  }
  const root = xmlElement("xmi:XMI", rootAttributes);
  const packages = [...artifact.packages].sort(
    (left: RecordValue, right: RecordValue) =>
      left.packagePath.length - right.packagePath.length ||
      compare(left.packagePath.join("\0"), right.packagePath.join("\0")),
  );
  const rootPackages = packages.filter(
    (packageRecord: RecordValue) => packageRecord.packagePath.length === 1,
  );
  if (rootPackages.length !== 1) {
    fail(
      "PACKAGE_ROOT",
      `${artifact.filename} must have exactly one root package`,
    );
  }
  const rootPackage = rootPackages[0]!;
  const model = appendXml(
    root,
    rootPackage.kind === "Profile" ? "uml:Profile" : "uml:Package",
    {
      "xmi:type": `uml:${rootPackage.kind}`,
      "xmi:id": context.id(rootPackage.id),
      name: rootPackage.name,
    },
  );
  if (rootPackage.uri.present) {
    model.attributes.set("URI", rootPackage.uri.value ?? "");
  }
  const packageNodes = new Map<string, XmlOutputNode>([
    [packageKey(rootPackage.packagePath), model],
  ]);
  for (const packageRecord of packages as RecordValue[]) {
    let node: XmlOutputNode;
    if (packageRecord === rootPackage) {
      node = model;
    } else {
      const parent = packageNodes.get(
        packageKey(packageRecord.packagePath.slice(0, -1)),
      );
      if (!parent) {
        fail(
          "PACKAGE_PARENT",
          `${artifact.filename} has no parent for ${packageRecord.packagePath.join("::")}`,
        );
      }
      node = appendXml(parent, "packagedElement", {
        "xmi:type": `uml:${packageRecord.kind}`,
        "xmi:id": context.id(packageRecord.id),
        name: packageRecord.name,
      });
      if (packageRecord.uri.present) {
        node.attributes.set("URI", packageRecord.uri.value ?? "");
      }
      packageNodes.set(packageKey(packageRecord.packagePath), node);
    }
    appendComments(
      node,
      packageRecord.comments,
      artifact,
      context,
      packageRecord.id,
    );
  }

  for (const machinery of artifact.machinery as RecordValue[]) {
    const owner = packageNodes.get(packageKey(machinery.ownerPath));
    if (!owner) {
      fail(
        "MACHINERY_OWNER",
        `${artifact.filename} has no package ${machinery.ownerPath.join("::")}`,
      );
    }
    const node = appendXml(owner, machineryTag(machinery.kind), {
      "xmi:type": machineryType(machinery.kind),
      "xmi:id": context.id(machinery.id),
    });
    for (const reference of machinery.targets as RecordValue[]) {
      appendReference(node, reference, artifact, context);
    }
    appendComments(
      node,
      machinery.comments,
      artifact,
      context,
      machinery.id,
    );
  }

  for (const declaration of artifact.declarations as RecordValue[]) {
    const owner = packageNodes.get(
      packageKey(packagePathForCanonicalId(artifact, declaration.id)),
    );
    if (!owner) {
      fail("DECLARATION_OWNER", `missing owner for ${declaration.id}`);
    }
    const node = appendDeclaration(owner, declaration, artifact, context);
    appendComments(
      node,
      declaration.comments,
      artifact,
      context,
      declaration.id,
    );
    for (const extension of declaration.extensions as RecordValue[]) {
      appendExtension(owner, extension, artifact, context);
    }
  }

  root.attributes.set("xmlns:sysml", "http://www.omg.org/spec/SysML/20181001/SysML");
  for (const declaration of artifact.declarations as RecordValue[]) {
    if (declaration.sysmlKind) {
      appendXml(root, `sysml:${declaration.sysmlKind}`, {
        "xmi:id": context.digestId(declaration.id, "sysmlKind"),
        base_Class: context.id(declaration.id),
      });
    }
    for (const connector of declaration.connectors as RecordValue[]) {
      if (connector.isBinding) appendXml(root, "sysml:BindingConnector", {
        "xmi:id": context.digestId(connector.id, "binding"), "base_Connector": context.id(connector.id),
      });
      (connector.ends as RecordValue[]).forEach((end, index) => {
        if (end.propertyPath?.length) appendXml(root, "sysml:NestedConnectorEnd", {
          "xmi:id": context.digestId(connector.id, "nested", String(index + 1)),
          "base_ConnectorEnd": context.ownedId(path.parse(artifact.filename).name, connector.id, "ConnectorEnd", "end", index + 1),
          propertyPath: end.propertyPath.map((ref: RecordValue) => context.referenceValue(ref, artifact)).join(" "),
        });
      });
    }
  }
  for (const namespace of artifact.namespaces as RecordValue[]) {
    appendXml(root, "mofext:Tag", {
      "xmi:type": "mofext:Tag",
      "xmi:id": context.digestId(artifact.artifactId, namespace.prefix),
      name: "org.omg.xmi.nsPrefix",
      value: namespace.prefix,
      element: context.id(rootPackage.id),
    });
  }
  for (const application of artifact.applications as RecordValue[]) {
    const prefix = namespaceByUri.get(application.stereotypeNamespace);
    if (!prefix) {
      fail(
        "APPLICATION_NAMESPACE",
        `no namespace prefix for ${application.stereotypeNamespace}`,
      );
    }
    const attributes: Record<string, string> = {
      "xmi:id": context.id(application.id),
      [application.targetProperty]: context.referenceValue(
        application.target,
        artifact,
      ),
    };
    for (const value of application.values as RecordValue[]) {
      attributes[value.property] = value.values.join(" ");
    }
    appendXml(
      root,
      `${prefix}:${application.stereotypeName}`,
      attributes,
    );
  }
  return serializeXml(root);
}

class RenderContext {
  private readonly ids = new Map<string, string>();
  private readonly artifactForTarget = new Map<string, RecordValue>();
  private readonly sourcesByGeneratedId = new Map<string, string>();

  constructor(canonical: CanonicalRaamlFacts) {
    for (const artifact of canonical.artifacts as RecordValue[]) {
      const key = path.parse(artifact.filename).name;
      for (const packageRecord of artifact.packages as RecordValue[]) {
        this.assign(
          packageRecord.id,
          syntheticId(key, packageRecord.name),
          artifact,
        );
      }
      for (const declaration of artifact.declarations as RecordValue[]) {
        this.assign(
          declaration.id,
          syntheticId(key, declaration.name ?? declaration.id),
          artifact,
        );
        this.indexOwned(artifact, declaration, key);
      }
      for (const machinery of artifact.machinery as RecordValue[]) {
        this.assign(
          machinery.id,
          digestId(key, machinery.id),
          artifact,
        );
      }
      for (const application of artifact.applications as RecordValue[]) {
        this.assign(
          application.id,
          digestId(key, application.id),
          artifact,
        );
      }
    }
  }

  id(canonicalId: string): string {
    const value = this.ids.get(canonicalId);
    if (!value) {
      fail(
        "REFERENCE_TARGET_MISSING",
        `reference target is absent from corpus: ${canonicalId}`,
      );
    }
    return value;
  }

  digestId(...parts: string[]): string {
    const source = parts.join("::");
    return this.claim(source, digestId(...parts));
  }

  ownedId(
    artifact: string,
    owner: string,
    kind: string,
    name: string,
    ordinal: number,
  ): string {
    const source = `${artifact}::${owner}::${kind}::${name}::${ordinal}`;
    return this.claim(
      source,
      syntheticOwnedId(artifact, owner, kind, name, ordinal),
    );
  }

  referenceValue(
    reference: RecordValue,
    currentArtifact: RecordValue,
  ): string {
    const target = reference.target as string;
    if (target.startsWith("external::")) {
      const rest = target.slice("external::".length);
      const separator = rest.indexOf("::");
      if (separator < 0) {
        fail("EXTERNAL_REFERENCE_SHAPE", `invalid external identity: ${target}`);
      }
      const document = rest.slice(0, separator);
      let fragment = rest.slice(separator + 2);
      if (fragment === "Package::UML") {
        fragment = "_0";
      }
      return `${document}#${fragment}`;
    }
    const generated = this.id(target);
    const targetArtifact = this.artifactForTarget.get(target);
    if (!targetArtifact) {
      fail("REFERENCE_TARGET_MISSING", `target has no artifact: ${target}`);
    }
    if (reference.sourceForm === "href") {
      return "https://www.omg.org/spec/RAAML/20240219/" +
        `${targetArtifact.filename}#${generated}`;
    }
    if (targetArtifact.artifactId !== currentArtifact.artifactId) {
      fail(
        "REFERENCE_FORM_CROSS_FILE",
        `non-href cross-file reference: ${target}`,
      );
    }
    return generated;
  }

  private indexOwned(
    artifact: RecordValue,
    declaration: RecordValue,
    key: string,
  ): void {
    for (
      const relation of [
        "properties",
        "ownedEnds",
        "extensions",
        "constraints",
        "connectors",
      ]
    ) {
      (declaration[relation] as RecordValue[]).forEach((item, offset) => {
        this.assign(
          item.id,
          syntheticOwnedId(
            key,
            declaration.id,
            relation,
            item.name ?? item.id,
            offset + 1,
          ),
          artifact,
        );
        if (relation === "extensions") {
          (item.ownedEnds as RecordValue[]).forEach((end, endOffset) => {
            this.assign(
              end.id,
              syntheticOwnedId(
                key,
                item.id,
                "ExtensionEnd",
                end.name ?? end.id,
                endOffset + 1,
              ),
              artifact,
            );
          });
        }
      });
    }
  }

  private assign(
    canonicalId: string,
    generatedId: string,
    artifact: RecordValue,
  ): void {
    this.claim(canonicalId, generatedId);
    this.ids.set(canonicalId, generatedId);
    this.artifactForTarget.set(canonicalId, artifact);
  }

  private claim(source: string, generatedId: string): string {
    const previous = this.sourcesByGeneratedId.get(generatedId);
    if (previous && previous !== source) {
      fail(
        "SYNTHETIC_ID_COLLISION",
        `synthetic ID collision between ${previous} and ${source}`,
      );
    }
    this.sourcesByGeneratedId.set(generatedId, source);
    return generatedId;
  }
}

function appendDeclaration(
  owner: XmlOutputNode,
  declaration: RecordValue,
  artifact: RecordValue,
  context: RenderContext,
): XmlOutputNode {
  const attributes: Record<string, string> = {
    "xmi:type": `uml:${declaration.kind}`,
    "xmi:id": context.id(declaration.id),
  };
  if (declaration.name !== null) {
    attributes.name = declaration.name;
  }
  if (declaration.isAbstract.present) {
    attributes.isAbstract = String(declaration.isAbstract.value);
  }
  const node = appendXml(owner, "packagedElement", attributes);
  for (const reference of declaration.generalizations as RecordValue[]) {
    const relationship = appendXml(node, "generalization", {
      "xmi:type": "uml:Generalization",
      "xmi:id": context.digestId(
        declaration.id,
        "generalization",
        reference.target,
      ),
    });
    appendReference(relationship, reference, artifact, context);
  }
  (declaration.properties as RecordValue[]).forEach((propertyRecord, offset) =>
    appendProperty(
      node,
      "ownedAttribute",
      propertyRecord,
      artifact,
      context,
      offset + 1,
    )
  );
  (declaration.ownedEnds as RecordValue[]).forEach((propertyRecord, offset) =>
    appendProperty(
      node,
      "ownedEnd",
      propertyRecord,
      artifact,
      context,
      offset + 1,
    )
  );
  for (const reference of declaration.memberEnds as RecordValue[]) {
    appendReference(node, reference, artifact, context);
  }
  for (const reference of declaration.navigableOwnedEnds as RecordValue[]) {
    appendReference(node, reference, artifact, context);
  }
  (declaration.literals as RecordValue[]).forEach((literal, offset) => {
    const literalNode = appendXml(node, "ownedLiteral", {
      "xmi:type": "uml:EnumerationLiteral",
      "xmi:id": context.ownedId(
        path.parse(artifact.filename).name,
        declaration.id,
        "EnumerationLiteral",
        literal.name,
        offset + 1,
      ),
      name: literal.name,
    });
    appendComments(
      literalNode,
      literal.comments,
      artifact,
      context,
      `${declaration.id}::${literal.name}`,
    );
  });
  for (const constraint of declaration.constraints as RecordValue[]) {
    const constraintAttributes: Record<string, string> = {
      "xmi:type": "uml:Constraint",
      "xmi:id": context.id(constraint.id),
    };
    if (constraint.name !== null) {
      constraintAttributes.name = constraint.name;
    }
    const constraintNode = appendXml(
      node,
      "ownedRule",
      constraintAttributes,
    );
    for (const reference of constraint.constrainedElements as RecordValue[]) {
      appendReference(constraintNode, reference, artifact, context);
    }
    const specification = appendXml(constraintNode, "specification", {
      "xmi:type": "uml:OpaqueExpression",
      "xmi:id": context.digestId(constraint.id, "specification"),
    });
    for (const body of constraint.bodyLines as string[]) {
      appendXml(specification, "body").text = body;
    }
    for (const language of constraint.languages as string[]) {
      appendXml(specification, "language").text = language;
    }
    appendComments(
      constraintNode,
      constraint.comments,
      artifact,
      context,
      constraint.id,
    );
  }
  for (const connector of declaration.connectors as RecordValue[]) {
    appendConnector(node, connector, artifact, context);
  }
  (declaration.icons as RecordValue[]).forEach((icon, offset) => {
    const iconAttributes: Record<string, string> = {
      "xmi:type": "uml:Image",
      "xmi:id": context.ownedId(
        path.parse(artifact.filename).name,
        declaration.id,
        "Image",
        "icon",
        offset + 1,
      ),
      content: icon.content,
    };
    for (const field of ["format", "location"]) {
      if (icon[field].present) {
        iconAttributes[field] = icon[field].value ?? "";
      }
    }
    appendXml(node, "icon", iconAttributes);
  });
  return node;
}

function appendConnector(
  owner: XmlOutputNode,
  connector: RecordValue,
  artifact: RecordValue,
  context: RenderContext,
): void {
  const attributes: Record<string, string> = {
    "xmi:type": "uml:Connector",
    "xmi:id": context.id(connector.id),
  };
  if (connector.name !== null) {
    attributes.name = connector.name;
  }
  const node = appendXml(owner, "ownedConnector", attributes);
  (connector.ends as RecordValue[]).forEach((end, offset) => {
    const endNode = appendXml(node, "end", {
      "xmi:type": "uml:ConnectorEnd",
      "xmi:id": context.ownedId(
        path.parse(artifact.filename).name,
        connector.id,
        "ConnectorEnd",
        "end",
        offset + 1,
      ),
    });
    appendReference(endNode, end.role, artifact, context);
    if (end.partWithPort !== null) {
      appendReference(endNode, end.partWithPort, artifact, context);
    }
  });
  appendComments(node, connector.comments, artifact, context, connector.id);
}

function appendExtension(
  owner: XmlOutputNode,
  extension: RecordValue,
  artifact: RecordValue,
  context: RenderContext,
): void {
  const node = appendXml(owner, "packagedElement", {
    "xmi:type": "uml:Extension",
    "xmi:id": context.id(extension.id),
  });
  for (const reference of extension.memberEnds as RecordValue[]) {
    appendReference(node, reference, artifact, context);
  }
  for (const reference of extension.navigableOwnedEnds as RecordValue[]) {
    appendReference(node, reference, artifact, context);
  }
  (extension.ownedEnds as RecordValue[]).forEach((end, offset) =>
    appendProperty(
      node,
      "ownedEnd",
      end,
      artifact,
      context,
      offset + 1,
    )
  );
  appendComments(node, extension.comments, artifact, context, extension.id);
}

function appendProperty(
  owner: XmlOutputNode,
  tag: string,
  propertyRecord: RecordValue,
  artifact: RecordValue,
  context: RenderContext,
  ordinal: number,
): void {
  const attributes: Record<string, string> = {
    "xmi:type": `uml:${propertyRecord.kind}`,
    "xmi:id": context.id(propertyRecord.id),
  };
  if (propertyRecord.name !== null) {
    attributes.name = propertyRecord.name;
  }
  if (propertyRecord.aggregation.present) {
    attributes.aggregation = propertyRecord.aggregation.value ?? "";
  }
  for (const field of ["isDerived", "isReadOnly", "isOrdered", "isUnique"]) {
    if (propertyRecord[field].present) {
      attributes[field] = String(propertyRecord[field].value);
    }
  }
  const node = appendXml(owner, tag, attributes);
  if (propertyRecord.type !== null) {
    appendReference(node, propertyRecord.type, artifact, context);
  }
  for (const relation of ["subsettedProperties", "redefinedProperties"]) {
    for (const reference of propertyRecord[relation] as RecordValue[]) {
      appendReference(node, reference, artifact, context);
    }
  }
  for (const role of ["lower", "upper", "default"]) {
    const value = propertyRecord[role] as RecordValue;
    if (value.present) {
      const child = appendXml(node, `${role}Value`, {
        "xmi:type": value.kind,
        "xmi:id": context.digestId(
          propertyRecord.id,
          role,
          String(ordinal),
        ),
      });
      if (value.value !== null) {
        child.attributes.set("value", value.value);
      }
    }
  }
  appendComments(
    node,
    propertyRecord.comments,
    artifact,
    context,
    propertyRecord.id,
  );
}

function appendComments(
  owner: XmlOutputNode,
  comments: RecordValue[],
  artifact: RecordValue,
  context: RenderContext,
  ownerId: string,
): void {
  comments.forEach((comment, offset) => {
    const node = appendXml(owner, "ownedComment", {
      "xmi:type": "uml:Comment",
      "xmi:id": context.digestId(ownerId, "comment", String(offset + 1)),
      body: comment.body,
    });
    for (const reference of comment.annotatedElements as RecordValue[]) {
      appendReference(node, reference, artifact, context);
    }
  });
}

function appendReference(
  owner: XmlOutputNode,
  reference: RecordValue,
  artifact: RecordValue,
  context: RenderContext,
): void {
  const value = context.referenceValue(reference, artifact);
  if (reference.sourceForm === "attribute") {
    owner.attributes.set(reference.role, value);
  } else if (reference.sourceForm === "idref") {
    appendXml(owner, reference.role, {"xmi:idref": value});
  } else {
    appendXml(owner, reference.role, {href: value});
  }
}

function namespacePrefixes(
  canonical: CanonicalRaamlFacts,
): ReadonlyMap<string, string> {
  const byUri = new Map<string, string>();
  const byPrefix = new Map<string, string>();
  for (const artifact of canonical.artifacts as RecordValue[]) {
    for (const namespace of artifact.namespaces as RecordValue[]) {
      const previousUri = byPrefix.get(namespace.prefix);
      const previousPrefix = byUri.get(namespace.uri);
      if (
        (previousUri && previousUri !== namespace.uri) ||
        (previousPrefix && previousPrefix !== namespace.prefix)
      ) {
        fail(
          "APPLICATION_NAMESPACE",
          `conflicting namespace mapping ${namespace.prefix}=${namespace.uri}`,
        );
      }
      byPrefix.set(namespace.prefix, namespace.uri);
      byUri.set(namespace.uri, namespace.prefix);
    }
  }
  return byUri;
}

function packagePathForCanonicalId(
  artifact: RecordValue,
  canonicalId: string,
): string[] {
  const matches = (artifact.packages as RecordValue[])
    .map((packageRecord) => packageRecord.packagePath as string[])
    .filter((packagePath) =>
      canonicalId.startsWith(
        `${artifact.artifactId}::${packagePath.join("::")}::`,
      )
    )
    .sort((left, right) => right.length - left.length);
  const match = matches[0];
  if (!match) {
    fail(
      "DECLARATION_OWNER",
      `${artifact.filename} has no package owner for ${canonicalId}`,
    );
  }
  return match;
}

function syntheticId(artifact: string, name: string): string {
  return `_raaml_${sha256(`${artifact}::${name}`).slice(0, 40)}`;
}

function syntheticOwnedId(
  artifact: string,
  owner: string,
  kind: string,
  name: string,
  ordinal: number,
): string {
  return `_raaml_${
    sha256(`${artifact}::${owner}::${kind}::${name}::${ordinal}`).slice(0, 40)
  }`;
}

function digestId(...parts: string[]): string {
  return `_raaml_${sha256(parts.join("::")).slice(0, 40)}`;
}

function machineryTag(kind: string): string {
  const value = ({
    MetamodelReference: "metamodelReference",
    PackageImport: "packageImport",
    ElementImport: "elementImport",
    ProfileApplication: "profileApplication",
  } as Record<string, string>)[kind];
  if (!value) {
    fail("MACHINERY_KIND", `unsupported machinery kind: ${kind}`);
  }
  return value;
}

function machineryType(kind: string): string {
  const value = ({
    MetamodelReference: "uml:PackageImport",
    PackageImport: "uml:PackageImport",
    ElementImport: "uml:ElementImport",
    ProfileApplication: "uml:ProfileApplication",
  } as Record<string, string>)[kind];
  if (!value) {
    fail("MACHINERY_KIND", `unsupported machinery kind: ${kind}`);
  }
  return value;
}

function packageKey(packagePath: readonly string[]): string {
  return packagePath.join("\0");
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function compare(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function fail(code: string, message: string): never {
  throw new RaamlPreservationError(code, message);
}
