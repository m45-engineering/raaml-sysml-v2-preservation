import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import {
  RaamlPreservationError,
  asciiPrettyJson,
  extractFacts,
  extractReconstructedFacts,
  forward,
  reverse,
  sha256,
  type PreservationManifest,
  type StandardsLock,
} from "./index.js";

const REPOSITORY_ROOT = path.resolve(import.meta.dirname, "../..");
const EXPECTED_CANONICAL_SHA256 =
  "638ef422aee4a528d5de2a5bca8c7203a0b10ca5e6dfd552c45e76c8f76a7cbc";
const EXPECTED_SYSML_SHA256 =
  "b02964848e164f9a728ca8d0341cd945c987b2749a71efd47b7d705c2b0b7b48";

const lock = JSON.parse(
  fs.readFileSync(path.join(REPOSITORY_ROOT, "standards.lock.json"), "utf8"),
) as StandardsLock;
const lockedArtifacts = lock.artifacts.filter(
  (artifact) => artifact.collection === "raaml-1.1-definitions",
);
const sourcesAvailable = lockedArtifacts.every((artifact) =>
  fs.existsSync(
    path.join(REPOSITORY_ROOT, "sources", "cache", artifact.filename),
  )
);

test(
  "TypeScript reproduces the complete canonical round trip",
  {skip: sourcesAvailable ? false : "locked RAAML corpus is not in the local cache"},
  () => {
    const sources = new Map(
      lockedArtifacts.map((artifact) => [
        artifact.filename,
        fs.readFileSync(
          path.join(REPOSITORY_ROOT, "sources", "cache", artifact.filename),
        ),
      ]),
    );
    const source = extractFacts({lock, sources}).canonical;
    assert.equal(
      sha256(asciiPrettyJson(source)),
      EXPECTED_CANONICAL_SHA256,
    );

    const mapped = forward(source);
    assert.equal(sha256(mapped.sysml), EXPECTED_SYSML_SHA256);
    assert.equal(mapped.manifests.size, 17);
    assert.equal(source.schemaVersion, "0.2.0");
    assert.match(mapped.sysml, /occurrence def InSeries :> RBDLib::SystemReliabilitySituation \{/);
    assert.match(mapped.sysml, /constraint def InSeriesCalculation \{/);
    assert.match(mapped.sysml, /constraint 'rc' : RBDLib::InSeriesCalculation\[1\];/);
    assert.match(mapped.sysml, /attribute 'input' : ScalarValues::Real\[0\.\.\*\];/);
    assert.match(mapped.sysml, /metadata def InSeries :> RBD::SystemReliability \{/);
    assert.match(mapped.sysml, /bind 'rc'\.'input' = 'rb'\.'reliability';/);
    assert.equal(mapped.mappingNotes.filter((note) => note.code === "SOURCE_CONNECTOR_CONTEXT").length, 4);
    assert.equal(mapped.mappingNotes.filter((note) => note.code === "SOURCE_ABSTRACT_ANNOTATION").length, 1);
    assert.equal(mapped.mappingNotes.filter((note) => note.code === "SOURCE_EXPRESSION_UNIMPLEMENTED").length, 60);

    const reconstructed = reverse({
      lock,
      sysml: mapped.sysml,
      manifests: mapped.manifests,
    });
    assert.equal(reconstructed.artifacts.size, 17);
    const actual = extractReconstructedFacts({
      lock,
      sources: reconstructed.artifacts,
    }).canonical;
    assert.equal(asciiPrettyJson(actual), asciiPrettyJson(source));
  },
);

test(
  "TypeScript rejects a changed preservation payload",
  {skip: sourcesAvailable ? false : "locked RAAML corpus is not in the local cache"},
  () => {
    const sources = new Map(
      lockedArtifacts.map((artifact) => [
        artifact.filename,
        fs.readFileSync(
          path.join(REPOSITORY_ROOT, "sources", "cache", artifact.filename),
        ),
      ]),
    );
    const mapped = forward(extractFacts({lock, sources}).canonical);
    const manifests = new Map(mapped.manifests);
    const [name, original] = manifests.entries().next().value as [
      string,
      PreservationManifest,
    ];
    const changed = structuredClone(original);
    (changed.payload as Record<string, unknown>).sourceFilename = "changed.xmi";
    manifests.set(name, changed);

    assert.throws(
      () => reverse({lock, sysml: mapped.sysml, manifests}),
      (error) =>
        error instanceof RaamlPreservationError &&
        error.code === "MANIFEST_DIGEST",
    );
  },
);
