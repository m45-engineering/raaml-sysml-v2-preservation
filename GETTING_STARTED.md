# Getting started

This repository contains:

- a proposal for preserving the 17 normative RAAML 1.1 definition files in
  SysML v2;
- a Python reference implementation of the forward and reverse mappings;
- a native TypeScript implementation for use in Node.js applications; and
- a reproducible test that checks whether the defined RAAML facts survive the
  complete round trip.

**Looking for the actual SysML v2 packages?** Follow
[Generate the RAAML packages for SysML v2](docs/generate-sysml-v2-packages.md).
That guide creates a local `.sysml` file containing Core, General, RBD, and
the other translated packages. The generated file is not included in Git.

You do not need Python or Java on your computer to run the test. The
recommended path uses Docker and runs the required tools inside a container.

## Run the complete reproduction

The steps below start with a computer that does not yet have this repository.

### 1. Install Git

Check whether Git is already installed:

```text
git --version
```

If that prints a version number, continue to step 2.

If the command is not found, install Git:

- macOS: install [Git for macOS](https://git-scm.com/download/mac);
- Windows: install [Git for Windows](https://git-scm.com/download/win);
- Linux: follow the [Git installation instructions](https://git-scm.com/download/linux)
  for your distribution.

On Windows, complete the remaining steps in Git Bash or Windows Subsystem for
Linux.

### 2. Install and start Docker

Install Docker:

- macOS or Windows: install
  [Docker Desktop](https://docs.docker.com/desktop/);
- Linux: install
  [Docker Engine](https://docs.docker.com/engine/install/).

Start Docker. Then open a terminal and run:

```text
docker version
```

The output must contain both a `Client` section and a `Server` section. If the
server section is missing, Docker is installed but its service is not running.

### 3. Download this repository

In the terminal, run:

```text
git clone https://github.com/florian-zeev/raaml-sysml-v2-preservation.git
cd raaml-sysml-v2-preservation
```

The repository is public and does not require GitHub authentication to clone.
A reviewer who receives a source-only archive should instead follow
[Run from a source-only archive](#run-from-a-source-only-archive).

### 4. Check that you are in the correct directory

Run:

```text
ls review-reproduce standards.lock.json
```

Both names must be printed. If either is missing, return to step 3 and change
into the repository directory.

### 5. Allow the reproduction script to run

On macOS, Linux, Git Bash, or Windows Subsystem for Linux, run:

```text
chmod +x review-reproduce
```

This changes only the local permission on the script.

### 6. Run the reproduction

Make sure the computer has an internet connection and at least 4 GB of free
disk space. Then run:

```text
./review-reproduce
```

The first run downloads about 624 MB of locked source and validation inputs.
It can take more than ten minutes, depending on the computer and connection.

The script performs these actions:

1. builds the pinned `linux/amd64` validation container;
2. downloads each locked input from its recorded source;
3. checks the exact size and SHA-256 of every input;
4. disables networking for the semantic reproduction;
5. extracts the defined facts from all 17 RAAML source files;
6. maps those facts to SysML v2 and preservation manifests;
7. reconstructs the SysML v1 artifacts;
8. validates the generated SysML v2 and reconstructed SysML v1;
9. compares every canonical source and reconstructed fact; and
10. runs the adversarial conformance cases.

### 7. Check the result

A successful run ends with:

```text
Independent reproduction passed.
Canonical SHA-256: 638ef422aee4a528d5de2a5bca8c7203a0b10ca5e6dfd552c45e76c8f76a7cbc
Reviewer result: review-evidence/review-result.json
Diagnostics: review-evidence/review-diagnostics.json
```

Open `review-evidence/review-result.json`. A passing result reports:

- `"ok": true`;
- 17 source artifacts and 17 reconstructed artifacts;
- canonical SHA-256
  `638ef422aee4a528d5de2a5bca8c7203a0b10ca5e6dfd552c45e76c8f76a7cbc`;
- zero canonical fact differences;
- zero SysML v1 validation errors;
- zero SysML v2 validation errors; and
- zero failed adversarial cases.

The reproduction does not retain or publish the third-party source corpus,
generated SysML v2 corpus, or reconstructed XMI. It retains only the aggregate
result and diagnostics in `review-evidence/`.

If the command fails, do not edit the generated evidence. Record:

- the complete terminal output;
- `review-evidence/review-diagnostics.json`, if it exists;
- the output of `docker version`; and
- the step at which the failure occurred.

## Use the TypeScript library

The complete Docker reproduction above is for reviewing the scientific
evidence. An application that uses the TypeScript library does not need
Docker, Python, or Java. See [`typescript/README.md`](typescript/README.md) for
the exact installation, build, test, and API steps.

## Use the Python command-line implementation

The Python reference implementation is a repository-local CLI rather than a
published Python package. It can run the complete extraction, forward mapping,
reverse reconstruction, and canonical comparison without Docker or Java.

Follow [`docs/python-cli-guide.md`](docs/python-cli-guide.md) for the exact
commands, output layout, diagnostics, and success criteria.

## Run from a source-only archive

If someone gives you a `.tar.gz` review package, they should also give you its
SHA-256 through a separate channel.

On macOS:

```text
shasum -a 256 PACKAGE.tar.gz
```

On Linux or Windows Subsystem for Linux:

```text
sha256sum PACKAGE.tar.gz
```

Replace `PACKAGE.tar.gz` with the actual filename. Compare the printed hash
with the hash supplied by the sender. Stop if they differ.

Extract and enter the package:

```text
tar -xzf PACKAGE.tar.gz
cd raaml-sysml-v2-preservation
```

Then continue with step 4 above.

## Read the proposal without running anything

No software setup is required to review the written proposal. Read:

1. [`docs/executive-summary.md`](docs/executive-summary.md) for the companion
   blog article, motivation, and result;
2. [`proposal/community-proposal-v0.1.md`](proposal/community-proposal-v0.1.md)
   for the proposal and its claim boundary;
3. [`proposal/normative-encoding-v0.1.md`](proposal/normative-encoding-v0.1.md)
   for the detailed mapping and reconstruction rules; and
4. [`docs/validation-report-v0.9.0-rc.3.md`](docs/validation-report-v0.9.0-rc.3.md)
   for the evidence and limitations.

See [`docs/versioning.md`](docs/versioning.md) to distinguish the signed
candidate tag from proposal, schema, Python, and TypeScript versions.

This is an independent community draft. It is not an OMG specification or an
OMG-endorsed proposal.

## Use the work from TypeScript or another language

The interchange contract is not tied to Python:

- the machine-readable contracts in [`schemas/`](schemas/) use JSON Schema
  draft 2020-12;
- preservation manifests and reports are JSON;
- the proposed native representation is SysML v2 text; and
- the mapping, identity, reconstruction, and conformance rules are documented
  in [`proposal/normative-encoding-v0.1.md`](proposal/normative-encoding-v0.1.md)
  and [`docs/fact-contract-v0.1.md`](docs/fact-contract-v0.1.md).

The complete implementation is more than a schema. It must also:

- parse and resolve the SysML v1 XMI/XML inputs securely;
- construct canonical identities and resolve references;
- perform the forward and reverse transformations;
- generate stable replacement XMI identifiers;
- preserve and verify manifest integrity;
- extract and resolve OCL names; and
- invoke the pinned SysML v1 and SysML v2 validators.

Python is the language of the reference command-line implementation. It is
not a requirement of the proposal.

The repository also contains a native TypeScript implementation under
[`typescript/`](typescript/). It performs fact extraction, canonicalization,
forward mapping, reverse reconstruction, and the equality check directly in
Node.js. It does not call the Python implementation at runtime. See
[`typescript/README.md`](typescript/README.md) for exact build and integration
steps.

The Python and TypeScript implementations are maintained by the same project.
Their agreement is useful cross-language evidence, but it is not an external
independent reproduction. An implementation in another language can use the
schemas and normative rules as its contract and must pass the same
conformance requirements. Validating JSON against the schemas alone is not
equivalent to performing the transformation.

## What a passing reproduction does not prove

It does not establish:

- support for arbitrary user-authored RAAML models;
- semantic equivalence of the OCL constraints;
- interoperability with a second SysML v2 implementation;
- suitability for certification use; or
- OMG endorsement.
