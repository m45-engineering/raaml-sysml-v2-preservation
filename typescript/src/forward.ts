import path from "node:path";
import {NativeModel} from "./native-model.js";

import {RaamlPreservationError} from "./errors.js";
import {sha256, stableJson, type JsonObject, type JsonValue} from "./json.js";
import type {CanonicalRaamlFacts} from "./types.js";

const FULL_CORPUS_ID = "milestone-4-full-corpus";
export const FULL_CORPUS_V2_FILENAME = "raaml-full-corpus.sysml";

type RecordValue = Record<string, any>;

export interface PreservationManifest extends JsonObject {
  readonly schemaVersion: "0.2.0";
  readonly documentKind: "raaml-preservation-manifest";
  readonly payloadSha256: string;
  readonly payload: JsonObject;
}

export interface ForwardResult {
  readonly sysml: string;
  readonly manifests: ReadonlyMap<string, PreservationManifest>;
  readonly canonical: CanonicalRaamlFacts;
  readonly mappingNotes: readonly JsonObject[];
}

export function forward(canonical: CanonicalRaamlFacts): ForwardResult {
  requireFullCorpusCoverage(canonical);
  requireReferenceClosure(canonical);
  const sysml = renderFullCorpusSysml(canonical);
  const sysmlBytes = new TextEncoder().encode(sysml);
  const manifests = new Map<string, PreservationManifest>();
  for (const artifact of canonical.artifacts as RecordValue[]) {
    const filename =
      `${path.parse(artifact.filename as string).name}.preservation.json`;
    manifests.set(
      filename,
      createManifest(canonical, artifact, sysmlBytes),
    );
  }
  return {sysml, manifests, canonical, mappingNotes: new NativeModel(canonical).notes()};
}

export function renderFullCorpusSysml(
  canonical: CanonicalRaamlFacts,
): string {
  return new NativeModel(canonical).render();
}

function createManifest(
  canonical: CanonicalRaamlFacts,
  artifact: RecordValue,
  sysmlBytes: Uint8Array,
): PreservationManifest {
  const artifactFacts = structuredClone(canonical) as CanonicalRaamlFacts;
  (artifactFacts.artifacts as RecordValue[]).splice(
    0,
    artifactFacts.artifacts.length,
    structuredClone(artifact),
  );
  const payload: JsonObject = {
    scopeId: FULL_CORPUS_ID,
    artifactId: artifact.artifactId,
    sourceFilename: artifact.filename,
    sourceSha256: artifact.sha256,
    v2Filename: FULL_CORPUS_V2_FILENAME,
    v2Sha256: sha256(sysmlBytes),
    nativeTargets: nativeTargets(artifactFacts),
    canonicalFacts: artifactFacts,
  };
  return {
    schemaVersion: "0.2.0",
    documentKind: "raaml-preservation-manifest",
    payloadSha256: sha256(stableJson(payload)),
    payload,
  };
}

function nativeTargets(canonical: CanonicalRaamlFacts): JsonObject[] {
  return new NativeModel(canonical).targets();
}

function requireFullCorpusCoverage(canonical: CanonicalRaamlFacts): void {
  if (canonical.artifacts.length !== 17) {
    fail(
      "FULL_CORPUS_ARTIFACTS",
      `expected 17 artifacts, got ${canonical.artifacts.length}`,
    );
  }
  const declarationCount = canonical.artifacts.reduce(
    (total, artifact) =>
      total + ((artifact as RecordValue).declarations as unknown[]).length,
    0,
  );
  if (declarationCount !== 283) {
    fail(
      "FULL_CORPUS_DECLARATIONS",
      `expected 283 declarations, got ${declarationCount}`,
    );
  }
}

function requireReferenceClosure(value: JsonValue): void {
  const known = new Set<string>();
  const references: string[] = [];
  const visit = (child: JsonValue): void => {
    if (Array.isArray(child)) {
      child.forEach(visit);
    } else if (child !== null && typeof child === "object") {
      const identifierValue = child.id;
      if (typeof identifierValue === "string") {
        known.add(identifierValue);
      }
      if (
        typeof child.role === "string" &&
        typeof child.sourceForm === "string" &&
        typeof child.target === "string"
      ) {
        references.push(child.target);
      }
      Object.values(child).forEach(visit);
    }
  };
  visit(value);
  const missing = references.filter(
    (target) => !target.startsWith("external::") && !known.has(target),
  );
  if (missing.length > 0) {
    fail(
      "REFERENCE_TARGET_MISSING",
      `corpus has ${missing.length} unresolved target(s): ${missing.slice(0, 3).join(", ")}`,
    );
  }
}

function fail(code: string, message: string): never {
  throw new RaamlPreservationError(code, message);
}
