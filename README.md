# Preserving RAAML 1.1 definitions in SysML v2

This repository contains a community proposal and reference implementation
for carrying the 17 normative RAAML 1.1 definition files through SysML v2
without losing a defined set of source facts.

The project is maintained by M45 Engineering as an open community proposal
and reference implementation. It is independent of OMG and is not an OMG
specification, submission, or endorsement.

The project does not define a new version of RAAML or redesign RAAML for
native SysML v2 use. Its narrower purpose is to preserve the normative RAAML
1.1 definitions, and it does not claim support for arbitrary user-authored
RAAML models.

## Development status

The current development generators emit inheritance, properties, specialized
definition kinds, and supported bindings in both Python and TypeScript.
Package-level checks compare the validator's resolved model with source
structure. Unevaluated constraints and unsupported source relationships are
identified explicitly. See [native package mapping v0.2](docs/native-package-mapping-v0.2.md)
for format changes, source exceptions, and remaining validator warnings.

## Signed-candidate result

The signed candidate `v0.9.0-rc.3` completes the full 17-file round trip with:

- zero differences in the defined canonical fact set;
- zero errors from the pinned SysML v1 and SysML v2 validators;
- all 33 source OCL expressions parsed and name-resolved;
- 36 adversarial cases passed;
- 343 source identities bound to generated native v2 targets; and
- a native TypeScript implementation that separately executes the same
  fact extraction, forward mapping, reverse mapping, and canonical equality
  check without calling Python, Java, Docker, or a service at runtime; and
- byte-identical 49-file release directories from a clean Linux host and an
  offline pinned container.

The candidate supports a bounded preservation claim:

```text
canonicalFacts(reverse(forward(x))) == canonicalFacts(x)
```

The TypeScript port is a second language implementation maintained by this
project. It is not a second SysML v2 validator and is not an external
independent reproduction. The candidate also does not establish behavioral
equivalence of OCL, certification suitability, or permission to redistribute
all third-party source material.

After `v0.9.0-rc.2` was signed, the exact generated SysML v2 text was also
opened with Sensmetry Syside Editor 0.10.3. Active validation was confirmed
with a deliberate negative smoke test, and the candidate file produced no
reported problems. This was a manual maintainer-operated check, not part of
an automated conformance gate or an external reproduction. It is supplemental
evidence for the unchanged generated text carried into `rc.3`. See the
[manual Syside record](docs/syside-editor-check-v0.9.0-rc.2.md).

The limited source-grounded material review, historical hosted-output cleanup,
exact-commit validation, source-only archive inspection, and signed-tag
validation are complete. Complete generated corpus outputs will remain local.
See the
[public-release checklist](docs/public-release-checklist.md).

## Start here

| Document | Purpose |
| --- | --- |
| [`docs/native-package-mapping-v0.2.md`](docs/native-package-mapping-v0.2.md) | Current structural mapping, validation scope, and explicit limitations |
| [`docs/generate-sysml-v2-packages.md`](docs/generate-sysml-v2-packages.md) | Generate and open the actual SysML v2 packages locally, including Core, General, and RBD |
| [`GETTING_STARTED.md`](GETTING_STARTED.md) | Exact first-time setup, reproduction, and integration instructions |
| [`docs/python-cli-guide.md`](docs/python-cli-guide.md) | Use the Python reference CLI for extraction, mapping, reconstruction, and equality checking |
| [`typescript/README.md`](typescript/README.md) | Use the preservation mapping directly from TypeScript or a Node.js application |
| [`docs/versioning.md`](docs/versioning.md) | Distinguish candidate tags, contract versions, and implementation versions |
| [`docs/npm-publishing.md`](docs/npm-publishing.md) | Publish the TypeScript package through signed tags and staged npm approval |
| [`docs/executive-summary.md`](docs/executive-summary.md) | Companion blog article and plain-language result |
| [`proposal/community-proposal-v0.1.md`](proposal/community-proposal-v0.1.md) | Draft paper and claim boundary |
| [`proposal/normative-encoding-v0.1.md`](proposal/normative-encoding-v0.1.md) | Detailed preservation and reconstruction rules |
| [`docs/validation-report-v0.9.0-rc.3.md`](docs/validation-report-v0.9.0-rc.3.md) | Signed-candidate validation, reproducibility, and TypeScript evidence |
| [`docs/syside-editor-check-v0.9.0-rc.2.md`](docs/syside-editor-check-v0.9.0-rc.2.md) | Post-tag manual acceptance check with a second SysML v2 implementation |
| [`docs/third-party-rights-audit.md`](docs/third-party-rights-audit.md) | Publication-boundary inventory and publisher decision record |
| [`docs/public-release-checklist.md`](docs/public-release-checklist.md) | Publication-boundary gates and the completed release record |
| [`docs/external-review-guide.md`](docs/external-review-guide.md) | Reviewer questions and remaining publication gates |
| [`docs/fact-contract-v0.1.md`](docs/fact-contract-v0.1.md) | Canonical fact identity and comparison contract |
| [`docs/transformation-analysis-v0.1.md`](docs/transformation-analysis-v0.1.md) | Comparison with the official SysML v1-to-v2 transformation |

Machine-readable transformation analysis is under [`analysis/`](analysis/).
Architecture decisions are under [`adr/`](adr/).

Audit the public-repository boundary from a full Git checkout with:

```text
./raaml publication audit
```

This command checks current and historical Git paths, ignore rules, and known
CI publishing mechanisms. It does not provide legal clearance or inspect
artifacts retained by GitHub outside the Git repository.

## Reproduce the candidate

These are the instructions for the historical signed candidate. Use a clean
checkout of `v0.9.0-rc.3` for its exact results. For the current development
packages and checks, follow [the generation guide](docs/generate-sysml-v2-packages.md)
and [v0.2 mapping notes](docs/native-package-mapping-v0.2.md).

Python 3.14.4 is the tested orchestration runtime. Only `sources fetch` uses
the network.

```text
./raaml sources fetch
./raaml sources verify
./raaml tooling bootstrap
./raaml reproduce --clean \
  --container-digest sha256:<container-image-id> \
  --release-tag v0.9.0-rc.3 \
  --output-dir generated/release-candidate
```

The release command verifies the full forward mapping, reverse mapping,
canonical comparison, validators, adversarial suite, controlled diff, and
STPA walkthrough. It creates `RELEASE.json` and `SHA256SUMS` in the output
directory.

Verify the signed candidate tag with:

```text
git -c gpg.format=ssh \
    -c gpg.ssh.allowedSignersFile=.github/allowed_signers \
    tag -v v0.9.0-rc.3
```

See the [validation report](docs/validation-report-v0.9.0-rc.3.md) for the
exact commit, pre-tag and tag-triggered runs, container image identities,
canonical hashes, archive review, and signature fingerprint.

## Independent clean-room reproduction

A reviewer working from a source-only archive does not have the repository's
Git history or signed tags. For that case, install Docker with
`linux/amd64` support, then run:

```text
./review-reproduce
```

This command builds the digest-pinned validation container, uses that container
to fetch the locked official inputs, and then runs the semantic reproduction
in a second container with networking disabled. It checks the expected
canonical hash, zero fact differences, both validators, and the adversarial
suite. No host Python or Java installation is required.

The command writes only the aggregate reviewer result and diagnostics to the
ignored `review-evidence/` directory. It does not retain the generated SysML
v2 corpus, preservation manifests, reconstructed XMI, or full comparison
record. Reviewers should return `review-result.json` together with their
platform and Docker version.

## Repository boundary

This is a standalone community project. It does not depend on M45 product
code, databases, authentication, or deployment infrastructure. Other tools
may consume versioned releases without becoming part of this repository.

The implementation provides a deterministic command-line tool and a native
TypeScript library. The TypeScript library runs directly in Node.js; it does
not start Python, Java, Docker, or a separate service. Both implementations
operate on the same locked inputs and preservation contract.

Use the [Python CLI guide](docs/python-cli-guide.md) for the complete
repository-local command sequence. Use the
[TypeScript guide](typescript/README.md) to embed the mapping in a Node.js
application.

## Source material

Official OMG specifications, XMI files, icons, and other third-party material
are not licensed by this repository. They are not committed unless a separate
rights review permits redistribution. See
[`THIRD_PARTY_MATERIALS.md`](THIRD_PARTY_MATERIALS.md) and
[`sources/README.md`](sources/README.md).

## Licensing

Original software is licensed under Apache-2.0. Original proposal text,
documentation, and schemas are licensed under CC-BY-4.0. Third-party material
is excluded. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
