# Native TypeScript implementation

This directory contains the native TypeScript implementation of the RAAML 1.1
preservation mapping. It is intended for Node.js applications, including
TypeScript applications such as M45.

M45 Engineering maintains this package as part of an open community proposal
and reference implementation. It is independent of OMG and is not an OMG
specification, submission, or endorsement.

It performs the mapping in process. It does not call Python, Java, Docker, or a
network service at runtime.

## Scope

This checkout contains unreleased development version `0.2.0-dev.0`, with
fact and manifest schema version `0.2.0`. The npm `next` release described
below is the older signed candidate. Build this checkout to use the corrected
native structure. See [the mapping notes](../docs/native-package-mapping-v0.2.md)
for unsupported expressions, source exceptions, and validator warnings.

The library:

1. reads caller-supplied bytes for the 17 locked normative RAAML 1.1
   definition files;
2. extracts and canonicalizes the facts covered by the preservation contract;
3. creates the SysML v2 representation and one preservation manifest per
   source artifact;
4. reconstructs the SysML v1 XMI artifacts from those outputs; and
5. lets the caller extract and compare the reconstructed canonical facts.

It does not define a new version of RAAML and does not claim to transform
arbitrary user-authored RAAML models. `forward` requires complete coverage of
the locked 17-file corpus and fails when references are unresolved.

## Runtime requirements

- Node.js 24 or newer
- ESM (`import`), not CommonJS `require`
- the `saxes` 6.0.0 runtime dependency
- the locked source bytes and `standards.lock.json`, supplied by the caller

The current implementation uses Node.js APIs such as `node:crypto` and
`node:path`. It is not a browser package.

The API is synchronous and keeps the corpus, canonical facts, SysML v2 text,
manifests, and reconstructed bytes in memory. Applications should run it in a
worker or background job if blocking the main Node.js event loop is
unacceptable.

The npm package has its own semantic version. That implementation version is
not a RAAML version or the signed preservation-candidate identity. See the
[versioning documentation](https://github.com/florian-zeev/raaml-sysml-v2-preservation/blob/main/docs/versioning.md).

## Install from npm

Release candidates are published under the `next` tag:

```text
npm install @m45-engineering/raaml-sysml-v2-preservation@next
```

With pnpm:

```text
pnpm add @m45-engineering/raaml-sysml-v2-preservation@next
```

The installed package contains the native TypeScript library and its runtime
dependency. It does not include the official RAAML source files. Callers must
supply the authorized, locked source bytes and `standards.lock.json`.

## Build and test

From the repository root:

```text
./raaml sources fetch
npm ci --prefix typescript
npm test --prefix typescript
```

`sources fetch` requires the repository's Python CLI and network access once.
The application using the compiled TypeScript library does not require Python
or network access. An integrator may obtain the locked source bytes by another
authorized process and supply them directly.

The test processes all 17 source artifacts and requires:

- the TypeScript canonical facts to have the reference SHA-256;
- the generated SysML v2 text to have the reference SHA-256;
- all 17 artifacts to be reconstructed; and
- facts extracted from the reconstructed XMI to equal the source facts.

`forward` also returns `mappingNotes`, identifying preserved expressions and
source relationships that are not emitted as executable/native relationships.
These warnings do not mean that a formula has been implemented.

Compile without running the tests:

```text
npm ci --prefix typescript
npm run build --prefix typescript
```

The compiled JavaScript and declarations are written to `typescript/dist/`.

## Install from a checkout

To test an unpublished checkout, build it and install it from its local
directory. Replace the paths below with real absolute paths:

```text
cd /path/to/raaml-sysml-v2-preservation
npm ci --prefix typescript
npm run build --prefix typescript

cd /path/to/your-application
npm install /path/to/raaml-sysml-v2-preservation/typescript
```

For a pnpm application, use this final command instead:

```text
pnpm add /path/to/raaml-sysml-v2-preservation/typescript
```

This installs the compiled TypeScript library and `saxes`. It does not install
the Python implementation, Java validators, Docker, the official RAAML source
files, or `standards.lock.json`.

## Complete round-trip example

The API accepts bytes supplied by the caller. It does not assume a directory
layout or read files by itself. This example reads a repository checkout,
writes the local outputs, and verifies facts extracted from the reconstructed
XMI.

```ts
import fs from "node:fs";
import path from "node:path";

import {
  RaamlPreservationError,
  asciiPrettyJson,
  extractFacts,
  extractReconstructedFacts,
  forward,
  reverse,
  type StandardsLock,
} from "@m45-engineering/raaml-sysml-v2-preservation";

const repository = process.env.RAAML_REPOSITORY;
if (!repository) {
  throw new Error("Set RAAML_REPOSITORY to the preservation repository path");
}

const lock = JSON.parse(
  fs.readFileSync(path.join(repository, "standards.lock.json"), "utf8"),
) as StandardsLock;
const definitions = lock.artifacts.filter(
  (artifact) => artifact.collection === "raaml-1.1-definitions",
);
const sources = new Map(
  definitions.map((artifact) => [
    artifact.filename,
    fs.readFileSync(
      path.join(repository, "sources", "cache", artifact.filename),
    ),
  ]),
);

try {
  const source = extractFacts({lock, sources});
  const mapped = forward(source.canonical);
  const reconstructed = reverse({
    lock,
    sysml: mapped.sysml,
    manifests: mapped.manifests,
  });

  // Equality must be checked from the reconstructed XMI bytes, not merely
  // from the canonical facts embedded in the manifests.
  const reconstructedFacts = extractReconstructedFacts({
    lock,
    sources: reconstructed.artifacts,
  });
  if (
    asciiPrettyJson(reconstructedFacts.canonical) !==
      asciiPrettyJson(source.canonical)
  ) {
    throw new Error("canonical RAAML facts differ after the round trip");
  }

  const output = path.resolve("generated", "typescript-example");
  fs.mkdirSync(path.join(output, "manifests"), {recursive: true});
  fs.mkdirSync(path.join(output, "reconstructed"), {recursive: true});
  fs.writeFileSync(path.join(output, "raaml-full-corpus.sysml"), mapped.sysml);
  for (const [filename, manifest] of mapped.manifests) {
    fs.writeFileSync(
      path.join(output, "manifests", filename),
      asciiPrettyJson(manifest),
    );
  }
  for (const [filename, bytes] of reconstructed.artifacts) {
    fs.writeFileSync(path.join(output, "reconstructed", filename), bytes);
  }

  console.log("RAAML canonical round trip passed");
} catch (error) {
  if (error instanceof RaamlPreservationError) {
    console.error(`${error.code}: ${error.message}`);
    process.exitCode = 1;
  } else {
    throw error;
  }
}
```

Set the repository path and run the example with the TypeScript execution tool
used by the consuming application. For example, after saving it as
`roundtrip.ts` in an application that uses `tsx`:

```text
RAAML_REPOSITORY=/path/to/raaml-sysml-v2-preservation npx tsx roundtrip.ts
```

`tsx` is only an example application development tool; it is not a dependency
of this library.

The caller may instead read source bytes from object storage, a database, or
an authorized upload. The library deliberately leaves input acquisition and
output persistence to the application.

## Error handling

Expected validation failures throw `RaamlPreservationError`. Its `code` is
machine-readable and its `message` explains the specific input failure.
Examples include:

- `XML_DTD_FORBIDDEN` for an XML document containing a DTD;
- `FULL_CORPUS_MANIFEST_COUNT` for a missing or extra manifest;
- `MANIFEST_DIGEST` for a changed manifest payload; and
- `V2_DIGEST` when the SysML v2 text no longer matches its manifest.

Do not continue a transformation after one of these errors. Log the code,
associate the failure with the relevant artifact or operation, and require a
human or upstream process to resolve the input.

The XML parser rejects DTDs, XInclude, unauthorized remote references, path
traversal, malformed UTF-8/XML, and configured resource-limit violations. The
default limits are exported as `DEFAULT_XML_LIMITS`.

| Default XML limit | Value |
| --- | ---: |
| Input bytes per document | 10 MiB |
| Element nesting depth | 256 |
| Attributes per element | 256 |
| Attribute bytes per element | 1 MiB |
| Text bytes per document | 32 MiB |

Call `parseXml` directly with `ParseXmlOptions.limits` only when a lower-level
consumer needs different limits. Raising a limit increases resource-exhaustion
risk and does not expand the supported RAAML corpus.

## Public API

The package root exports the following symbols.

| Area | Exports | Purpose |
| --- | --- | --- |
| High-level extraction | `extractFacts`, `extractReconstructedFacts` | Extract raw and canonical facts from official or reconstructed XMI bytes. |
| Mapping | `forward`, `reverse`, `renderFullCorpusSysml`, `FULL_CORPUS_V2_FILENAME` | Create or verify the SysML v2 view and preservation manifests, then reconstruct XMI. |
| Mapping types | `ForwardResult`, `PreservationManifest`, `ReverseInput`, `ReverseResult` | Type the forward and reverse operations. |
| Fact types | `CanonicalRaamlFacts`, `RawRaamlFacts`, `ExtractFactsInput`, `ExtractFactsResult`, `LockedArtifact`, `StandardsLock` | Type the locked inputs and extracted documents. |
| Low-level fact functions | `extractRawFacts`, `extractReconstructedRawFacts`, `canonicalizeFacts` | Build or canonicalize facts when the high-level helpers are not sufficient. |
| Errors | `RaamlPreservationError` | Report a failed invariant with a machine-readable `code`. |
| Deterministic JSON and digests | `stableJson`, `canonicalJson`, `asciiCanonicalJson`, `prettyJson`, `asciiPrettyJson`, `sha256` | Serialize evidence deterministically and compute SHA-256. |
| JSON types | `JsonObject`, `JsonPrimitive`, `JsonValue` | Type JSON-compatible contract values. |
| Secure XML | `parseXml`, `DEFAULT_XML_LIMITS`, `attribute`, `children`, `descendants` | Parse and inspect namespace-aware XML under explicit security limits. |
| XML types | `ParseXmlOptions`, `XmlAttribute`, `XmlElement`, `XmlLimits`, `XmlName` | Type parser inputs, limits, and parsed nodes. |

For the normal application workflow, prefer `extractFacts`, `forward`,
`reverse`, `extractReconstructedFacts`, `asciiPrettyJson`, and
`RaamlPreservationError`. The lower-level exports exist for alternative
implementations and tests; they do not expand the project's preservation
claim.

## Input ownership and publication boundary

The official OMG files are not licensed or distributed by this package. The
application is responsible for obtaining authorized source bytes and verifying
them against `standards.lock.json` before use.

Generated canonical facts, full-corpus SysML v2, manifests, and reconstructed
XMI can reproduce source-grounded material. Do not commit, publish, or attach
them unless the applicable rights and project policy permit it. See
[`../THIRD_PARTY_MATERIALS.md`](../THIRD_PARTY_MATERIALS.md).

## Validation boundary

The native library enforces source locks, parsing restrictions, reference
closure, manifest integrity, native-target bindings, deterministic
reconstruction, and canonical fact equality when the caller performs the
complete example above.

It does not invoke the pinned SysML v1 or SysML v2 validators. Those validators
are part of the repository's scientific evidence workflow, not an application
runtime dependency. Run `./review-reproduce` from the repository root when a
complete reproduction of the published evidence is required.

## Relationship to Python and Java

Python remains the reference command-line implementation and is used to check
that TypeScript produces the same canonical and mapped outputs. Java is used
only by the repository's pinned SysML v1 validation evidence. Neither is
required by an application calling the TypeScript library.

Both implementations are maintained by this project. Agreement between them
is cross-language evidence, not an external independent reproduction.
