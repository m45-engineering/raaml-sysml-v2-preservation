import {sha256} from "./json.js";
import {RaamlPreservationError} from "./errors.js";
import type {
  ExtractFactsInput,
  LockedArtifact,
  RawRaamlFacts,
} from "./types.js";
import {
  attribute,
  children,
  descendants,
  parseXml,
  type XmlElement,
} from "./xml.js";

const CORPUS = "raaml-1.1-definitions";
const XMI_NAMESPACE = "http://www.omg.org/spec/XMI/20131001";
const RAAML_NAMESPACE_PREFIX = "https://www.omg.org/spec/RAAML/";

const DECLARATION_TYPES: Readonly<Record<string, string>> = Object.freeze({
  "uml:Stereotype": "Stereotype",
  "uml:Class": "Class",
  "uml:Enumeration": "Enumeration",
  "uml:Association": "Association",
  "uml:AssociationClass": "AssociationClass",
});
const PROPERTY_TYPES: Readonly<Record<string, string>> = Object.freeze({
  "uml:Property": "Property",
  "uml:Port": "Port",
  "uml:ExtensionEnd": "ExtensionEnd",
});
const MACHINERY_TAGS: Readonly<Record<string, string>> = Object.freeze({
  metamodelReference: "MetamodelReference",
  packageImport: "PackageImport",
  elementImport: "ElementImport",
  profileApplication: "ProfileApplication",
});

type RecordValue = Record<string, any>;

export function extractRawFacts(input: ExtractFactsInput): RawRaamlFacts {
  return extractRawFactsInternal(input, true);
}

export function extractReconstructedRawFacts(
  input: ExtractFactsInput,
): RawRaamlFacts {
  return extractRawFactsInternal(input, false);
}

function extractRawFactsInternal(
  input: ExtractFactsInput,
  verifyLockedBytes: boolean,
): RawRaamlFacts {
  if (input.lock.schemaVersion !== "0.1.0") {
    fail("LOCK_VERSION", "standards lock must use schemaVersion 0.1.0");
  }
  const artifacts = input.lock.artifacts.filter(
    (artifact) => artifact.collection === CORPUS,
  );
  if (artifacts.length !== 17) {
    fail(
      "FACT_CORPUS_SIZE",
      `expected 17 locked RAAML definitions, got ${artifacts.length}`,
    );
  }

  const allowedRemoteDocuments = allowedRemoteDocumentsFor(input.lock.artifacts);
  const rawArtifacts = artifacts.map((artifact) => {
    const bytes = input.sources.get(artifact.filename);
    if (!bytes) {
      fail("SOURCE_MISSING", `source artifact is missing: ${artifact.filename}`);
    }
    if (verifyLockedBytes && bytes.byteLength !== artifact.byteSize) {
      fail(
        "SOURCE_SIZE_MISMATCH",
        `${artifact.filename}: expected ${artifact.byteSize} bytes, got ${bytes.byteLength}`,
      );
    }
    if (verifyLockedBytes && sha256(bytes) !== artifact.sha256) {
      fail("SOURCE_HASH_MISMATCH", `${artifact.filename}: SHA-256 mismatch`);
    }
    return extractArtifact(bytes, artifact, allowedRemoteDocuments);
  });

  return {
    schemaVersion: "0.2.0",
    documentKind: "raw-raaml-facts",
    corpus: CORPUS,
    artifacts: rawArtifacts,
  };
}

function extractArtifact(
  bytes: Uint8Array,
  artifact: LockedArtifact,
  allowedRemoteDocuments: ReadonlySet<string>,
): RecordValue {
  let root: XmlElement;
  try {
    root = parseXml(bytes, {allowedRemoteDocuments});
  } catch (error) {
    if (error instanceof RaamlPreservationError) {
      throw error;
    }
    fail(
      "FACT_XML_PARSE",
      `${artifact.filename}: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
  const rootChildren = root.children;
  const sysmlApplications = new Map<string, Map<string, XmlElement>>();
  for (const application of rootChildren) {
    if (!application.namespace.startsWith("http://www.omg.org/spec/SysML/")) continue;
    for (const attr of application.attributes.values()) {
      if (!attr.local.startsWith("base_")) continue;
      const entries = sysmlApplications.get(attr.value) ?? new Map<string, XmlElement>();
      entries.set(application.local, application);
      sysmlApplications.set(attr.value, entries);
    }
  }
  const model = rootChildren[0];
  if (!model) {
    fail("FACT_ROOT_EMPTY", `${artifact.filename}: empty XMI root`);
  }

  const allElements = [model, ...descendants(model, () => true)];
  const parent = new Map<XmlElement, XmlElement>();
  for (const owner of [root, ...descendants(root, () => true)]) {
    for (const child of owner.children) {
      parent.set(child, owner);
    }
  }
  const paths = packagePaths(model);
  const packages = allElements
    .filter(isPackage)
    .map((element) => extractPackage(element, requiredPath(paths, element)));
  const declarations = allElements
    .filter((element) => declarationKind(element) !== undefined)
    .map((element) =>
      extractDeclaration(
        element,
        requiredPath(paths, owningPackage(element, parent)),
        sysmlApplications,
      ),
    );
  const declarationByHandle = new Map(
    declarations.map((declaration) => [
      declaration.sourceHandle as string,
      declaration,
    ]),
  );

  for (const element of allElements) {
    if (xmiType(element) !== "uml:Extension") {
      continue;
    }
    const extension = extractExtension(element);
    const ownedEnds = extension.ownedEnds as RecordValue[];
    const targetReference = ownedEnds[0]?.type as RecordValue | null | undefined;
    if (ownedEnds.length !== 1 || !targetReference) {
      fail(
        "FACT_EXTENSION_SHAPE",
        `${artifact.filename}: Extension must have one typed owned end`,
      );
    }
    const target = declarationByHandle.get(targetReference.sourceValue as string);
    if (!target || target.kind !== "Stereotype") {
      fail(
        "FACT_EXTENSION_TARGET",
        `${artifact.filename}: Extension target is not a local Stereotype`,
      );
    }
    (target.extensions as RecordValue[]).push(extension);
  }

  const machinery: RecordValue[] = [];
  for (const element of allElements) {
    const kind = MACHINERY_TAGS[element.local];
    if (!kind) {
      continue;
    }
    machinery.push(
      extractMachinery(
        element,
        kind,
        requiredPath(paths, owningPackage(element, parent)),
      ),
    );
  }

  const profileUri = attribute(model, "URI");
  const namespaces: RecordValue[] = [];
  for (const element of rootChildren.slice(1)) {
    const prefix = attribute(element, "value");
    if (
      element.local === "Tag" &&
      attribute(element, "name") === "org.omg.xmi.nsPrefix" &&
      prefix &&
      profileUri
    ) {
      namespaces.push({prefix, uri: profileUri});
    }
  }

  const applications = rootChildren
    .slice(1)
    .filter((element) => element.namespace.startsWith(RAAML_NAMESPACE_PREFIX))
    .map((element) => extractApplication(element));

  return {
    artifactId: artifact.id,
    filename: artifact.filename,
    sha256: artifact.sha256,
    namespaces,
    packages,
    declarations,
    machinery,
    applications,
  };
}

function extractPackage(element: XmlElement, path: string[]): RecordValue {
  return {
    sourceHandle: sourceHandle(element),
    kind: xmiType(element) === "uml:Profile" ? "Profile" : "Package",
    packagePath: path,
    name: requiredName(element, "package"),
    uri: presenceString(element, "URI"),
    comments: extractComments(element),
  };
}

function extractDeclaration(
  element: XmlElement,
  packagePath: string[],
  sysmlApplications: Map<string, Map<string, XmlElement>>,
): RecordValue {
  const kind = declarationKind(element);
  if (!kind) {
    fail("FACT_DECLARATION_KIND", "unsupported declaration kind");
  }
  return {
    sourceHandle: sourceHandle(element),
    kind,
    sysmlKind: ["ConstraintBlock", "Block"].find((name) => sysmlApplications.get(sourceHandle(element))?.has(name)) ?? null,
    packagePath,
    name: attribute(element, "name") ?? null,
    isAbstract: presenceBoolean(element, "isAbstract", false),
    comments: extractComments(element),
    generalizations: extractGeneralizations(element),
    properties: children(element, "ownedAttribute").map(extractProperty),
    extensions: [],
    icons: extractIcons(element),
    constraints: extractConstraints(element),
    literals: extractLiterals(element),
    connectors: extractConnectors(element, sysmlApplications),
    memberEnds: references(element, "memberEnd"),
    ownedEnds: children(element, "ownedEnd").map(extractProperty),
    navigableOwnedEnds: references(element, "navigableOwnedEnd"),
  };
}

function extractProperty(element: XmlElement): RecordValue {
  const type = xmiType(element);
  const kind = type ? PROPERTY_TYPES[type] : undefined;
  if (!kind) {
    fail("FACT_PROPERTY_KIND", `unsupported property type ${String(type)}`);
  }
  const name = attribute(element, "name") ?? null;
  return {
    sourceHandle: sourceHandle(element),
    kind,
    name,
    isBase: name?.startsWith("base_") ?? false,
    type: singleReference(element, "type"),
    aggregation: presenceString(element, "aggregation"),
    lower: extractValueLiteral(element, "lowerValue"),
    upper: extractValueLiteral(element, "upperValue"),
    default: extractValueLiteral(element, "defaultValue"),
    isDerived: presenceBoolean(element, "isDerived", false),
    isReadOnly: presenceBoolean(element, "isReadOnly", false),
    isOrdered: presenceBoolean(element, "isOrdered", false),
    isUnique: presenceBoolean(element, "isUnique", true),
    subsettedProperties: references(element, "subsettedProperty"),
    redefinedProperties: references(element, "redefinedProperty"),
    comments: extractComments(element),
  };
}

function extractExtension(element: XmlElement): RecordValue {
  return {
    sourceHandle: sourceHandle(element),
    memberEnds: references(element, "memberEnd"),
    navigableOwnedEnds: references(element, "navigableOwnedEnd"),
    ownedEnds: children(element, "ownedEnd")
      .filter((child) => xmiType(child) === "uml:ExtensionEnd")
      .map(extractProperty),
    comments: extractComments(element),
  };
}

function extractComments(element: XmlElement): RecordValue[] {
  return children(element, "ownedComment").map((comment) => {
    const bodyAttribute = attribute(comment, "body");
    const body = bodyAttribute ?? children(comment, "body")
      .map((bodyElement) => bodyElement.text)
      .join("\n");
    return {
      body,
      annotatedElements: references(comment, "annotatedElement"),
    };
  });
}

function extractIcons(element: XmlElement): RecordValue[] {
  return children(element, "icon")
    .filter((icon) => xmiType(icon) === "uml:Image")
    .map((icon) => ({
      format: presenceString(icon, "format"),
      content: attribute(icon, "content") ?? "",
      location: presenceString(icon, "location"),
    }));
}

function extractConstraints(element: XmlElement): RecordValue[] {
  return children(element, "ownedRule").map((constraint) => {
    const specification = children(constraint, "specification")[0];
    return {
      sourceHandle: sourceHandle(constraint),
      name: attribute(constraint, "name") ?? null,
      constrainedElements: references(constraint, "constrainedElement"),
      languages: specification
        ? children(specification, "language").map((item) => item.text)
        : [],
      bodyLines: specification
        ? children(specification, "body").map((item) => item.text)
        : [],
      comments: extractComments(constraint),
    };
  });
}

function extractLiterals(element: XmlElement): RecordValue[] {
  return children(element, "ownedLiteral").map((literal) => ({
    name: requiredName(literal, "EnumerationLiteral"),
    comments: extractComments(literal),
  }));
}

function extractConnectors(element: XmlElement, sysmlApplications: Map<string, Map<string, XmlElement>>): RecordValue[] {
  return children(element, "ownedConnector")
    .filter((connector) => xmiType(connector) === "uml:Connector")
    .map((connector) => ({
      sourceHandle: sourceHandle(connector),
      name: attribute(connector, "name") ?? null,
      isBinding: sysmlApplications.get(sourceHandle(connector))?.has("BindingConnector") ?? false,
      ends: children(connector, "end").map((end) => {
        const role = singleReference(end, "role");
        if (!role) {
          fail("FACT_CONNECTOR_ROLE", "ConnectorEnd has no role");
        }
        return {
          role,
          partWithPort: singleReference(end, "partWithPort"),
          propertyPath: (attribute(sysmlApplications.get(sourceHandle(end))?.get("NestedConnectorEnd") ?? end, "propertyPath") ?? "").split(/\s+/).filter(Boolean).map((value) => ({role: "propertyPath", form: "attribute", sourceValue: value})),
        };
      }),
      comments: extractComments(connector),
    }));
}

function extractGeneralizations(element: XmlElement): RecordValue[] {
  return children(element, "generalization").map((generalization) => {
    const reference = singleReference(generalization, "general");
    if (!reference) {
      fail("FACT_GENERALIZATION_TARGET", "Generalization has no general target");
    }
    return reference;
  });
}

function extractMachinery(
  element: XmlElement,
  kind: string,
  ownerPath: string[],
): RecordValue {
  const roles: Readonly<Record<string, readonly string[]>> = {
    MetamodelReference: ["importedPackage"],
    PackageImport: ["importedPackage"],
    ElementImport: ["importedElement"],
    ProfileApplication: ["appliedProfile"],
  };
  return {
    sourceHandle: sourceHandle(element),
    kind,
    ownerPath,
    targets: (roles[kind] ?? []).flatMap((role) => references(element, role)),
    comments: extractComments(element),
  };
}

function extractApplication(element: XmlElement): RecordValue {
  const applicationAttributes = [...element.attributes.values()]
    .filter(
      (item) =>
        !(item.namespace === XMI_NAMESPACE &&
          (item.local === "id" || item.local === "type")),
    );
  const targets = applicationAttributes.filter((item) =>
    item.local.startsWith("base_")
  );
  if (targets.length !== 1) {
    fail(
      "FACT_APPLICATION_TARGET",
      `${element.local} must have exactly one base_* target`,
    );
  }
  const target = targets[0]!;
  const values = applicationAttributes
    .filter((item) => !item.local.startsWith("base_"))
    .sort((left, right) => compare(left.local, right.local))
    .map((item) => ({
      property: item.local,
      values: item.value.split(/\s+/).filter(Boolean),
    }));
  return {
    sourceHandle: sourceHandle(element),
    stereotypeNamespace: element.namespace,
    stereotypeName: element.local,
    targetProperty: target.local,
    target: {
      role: target.local,
      form: "attribute",
      sourceValue: target.value,
    },
    values,
  };
}

function extractValueLiteral(
  element: XmlElement,
  role: string,
): RecordValue {
  const literal = children(element, role)[0];
  if (!literal) {
    return {present: false, kind: null, value: null};
  }
  return {
    present: true,
    kind: xmiType(literal) ?? null,
    value: attribute(literal, "value") ?? null,
  };
}

function references(element: XmlElement, role: string): RecordValue[] {
  const result: RecordValue[] = [];
  const direct = attribute(element, role);
  if (direct !== undefined) {
    for (const value of direct.split(/\s+/).filter(Boolean)) {
      result.push({role, form: "attribute", sourceValue: value});
    }
  }
  for (const child of children(element, role)) {
    const idref = attribute(child, "idref", XMI_NAMESPACE);
    const href = attribute(child, "href");
    if (idref) {
      result.push({role, form: "idref", sourceValue: idref});
    } else if (href) {
      result.push({role, form: "href", sourceValue: href});
    } else {
      fail(
        "FACT_REFERENCE_SHAPE",
        `${role} has neither xmi:idref nor href`,
      );
    }
  }
  return result;
}

function singleReference(
  element: XmlElement,
  role: string,
): RecordValue | null {
  const found = references(element, role);
  if (found.length === 0) {
    return null;
  }
  if (found.length !== 1) {
    fail(
      "FACT_REFERENCE_CARDINALITY",
      `${role} expected at most one target, got ${found.length}`,
    );
  }
  return found[0]!;
}

function packagePaths(model: XmlElement): Map<XmlElement, string[]> {
  const result = new Map<XmlElement, string[]>();
  const visit = (element: XmlElement, parentPath: string[]): void => {
    let path = parentPath;
    if (isPackage(element)) {
      path = [...parentPath, requiredName(element, "package")];
      result.set(element, path);
    }
    for (const child of element.children) {
      visit(child, path);
    }
  };
  visit(model, []);
  return result;
}

function owningPackage(
  element: XmlElement,
  parents: ReadonlyMap<XmlElement, XmlElement>,
): XmlElement {
  let current: XmlElement | undefined = element;
  while (current) {
    if (isPackage(current)) {
      return current;
    }
    current = parents.get(current);
  }
  fail("FACT_PACKAGE_OWNER", "element has no owning package");
}

function requiredPath(
  paths: ReadonlyMap<XmlElement, string[]>,
  element: XmlElement,
): string[] {
  const path = paths.get(element);
  if (!path) {
    fail("FACT_PACKAGE_OWNER", "element has no package path");
  }
  return path;
}

function isPackage(element: XmlElement): boolean {
  return ["uml:Profile", "uml:Package"].includes(xmiType(element) ?? "");
}

function declarationKind(element: XmlElement): string | undefined {
  const type = xmiType(element);
  return type ? DECLARATION_TYPES[type] : undefined;
}

function presenceBoolean(
  element: XmlElement,
  name: string,
  defaultValue: boolean,
): RecordValue {
  const value = attribute(element, name);
  if (value === undefined) {
    return {present: false, value: defaultValue};
  }
  if (value !== "true" && value !== "false") {
    fail("FACT_BOOLEAN", `${name} must be 'true' or 'false', got ${value}`);
  }
  return {present: true, value: value === "true"};
}

function presenceString(element: XmlElement, name: string): RecordValue {
  const value = attribute(element, name);
  return value === undefined
    ? {present: false, value: null}
    : {present: true, value};
}

function sourceHandle(element: XmlElement): string {
  const value = attribute(element, "id", XMI_NAMESPACE);
  if (!value) {
    fail("FACT_SOURCE_HANDLE", `${element.local} has no xmi:id`);
  }
  return value;
}

function requiredName(element: XmlElement, kind: string): string {
  const name = attribute(element, "name");
  if (!name) {
    fail("FACT_NAME", `${kind} has no name`);
  }
  if (name.includes("::")) {
    fail("FACT_NAME_SEPARATOR", `name contains reserved separator '::': ${name}`);
  }
  return name;
}

function xmiType(element: XmlElement): string | undefined {
  return attribute(element, "type", XMI_NAMESPACE);
}

function allowedRemoteDocumentsFor(
  artifacts: readonly LockedArtifact[],
): ReadonlySet<string> {
  const allowed = new Set(artifacts.map((artifact) => artifact.authoritativeUrl));
  for (const url of [...allowed]) {
    if (url.startsWith("https://www.omg.org/")) {
      allowed.add(url.replace("https://www.omg.org/", "http://www.omg.org/"));
    }
  }
  return allowed;
}

function compare(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function fail(code: string, message: string): never {
  throw new RaamlPreservationError(code, message);
}
