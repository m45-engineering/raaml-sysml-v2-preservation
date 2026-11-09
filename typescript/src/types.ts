import type {JsonObject} from "./json.js";

export interface LockedArtifact extends JsonObject {
  readonly id: string;
  readonly collection: string;
  readonly authoritativeUrl: string;
  readonly filename: string;
  readonly byteSize: number;
  readonly sha256: string;
}

export interface StandardsLock extends JsonObject {
  readonly schemaVersion: "0.1.0";
  readonly artifacts: LockedArtifact[];
}

export interface RawRaamlFacts extends JsonObject {
  readonly schemaVersion: "0.2.0";
  readonly documentKind: "raw-raaml-facts";
  readonly corpus: "raaml-1.1-definitions";
  readonly artifacts: JsonObject[];
}

export interface CanonicalRaamlFacts extends JsonObject {
  readonly schemaVersion: "0.2.0";
  readonly documentKind: "canonical-raaml-facts";
  readonly corpus: "raaml-1.1-definitions";
  readonly artifacts: JsonObject[];
}

export interface ExtractFactsInput {
  readonly lock: StandardsLock;
  readonly sources: ReadonlyMap<string, Uint8Array>;
}

export interface ExtractFactsResult {
  readonly raw: RawRaamlFacts;
  readonly canonical: CanonicalRaamlFacts;
}
