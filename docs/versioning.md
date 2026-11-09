# Versioning

This repository uses several version numbers for different things. They must
not be treated as interchangeable.

## Candidate tags

Tags such as `v0.9.0-rc.3` identify an immutable, signed source state and its
validation evidence. The tag is the version to cite when reproducing or
reviewing a published candidate.

The current signed candidate is `v0.9.0-rc.3`. It is a release candidate for
this community proposal and reference implementation. It is not a version of
RAAML and does not mean “RAAML 0.9” or “RAAML 2.0.”

## Proposal and contract versions

The written proposal and machine-readable contracts are independently
versioned. The signed candidate uses proposal/fact contract `0.1` and schema
version `0.1.0`. Current development raw facts, canonical facts, and manifests
use `0.2.0`; their additions are documented in
[native package mapping v0.2](native-package-mapping-v0.2.md). Other report and
lock schemas retain their existing version numbers.

A schema version describes the shape and meaning of a JSON document. It does
not identify a Git commit or validation run.

## Implementation versions

The development Python CLI reports `0.2.0.dev0` and the development TypeScript
package reports `0.2.0-dev.0`. These are unreleased implementation versions,
not versions of RAAML or a new signed preservation-evidence state.

The Python implementation is not published as a PyPI package. The previous
TypeScript release candidate `0.1.0-rc.3` is published under the `next` tag in the
`@m45-engineering` organization scope. Cite both the package version and the
corresponding signed Git candidate when referring to a tested implementation.

TypeScript package releases use their own signed tags. Package `0.1.0-rc.3`
maps to `typescript-v0.1.0-rc.3`. See the
[npm publishing procedure](npm-publishing.md).

## Future changes

- A documentation-only change on `main` does not alter an existing signed
  candidate.
- A change to facts, identity, schemas, mapping, reconstruction, validation,
  or the stated preservation claim requires a new candidate and new evidence.
- Existing signed tags are never moved or replaced.
- If Python or TypeScript packages are published later, their package versions
  will be mapped explicitly to the candidate tags and contract versions they
  implement.
