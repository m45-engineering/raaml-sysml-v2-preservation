# Generate the RAAML packages for SysML v2

Follow these steps to generate the SysML v2 definitions for **Core, General,
and RBD** on your own computer.

The result is one file, `raaml-full-corpus.sysml`, containing all 17 translated
RAAML packages. You can open it in a text editor or a SysML v2 modeling tool.
The packages are named sections inside that file, not separate downloads.

The current development output includes native structure but does not execute
the preserved source constraint expressions. Five source relationships are
explicitly marked `UNMAPPED`; see [the mapping notes](native-package-mapping-v0.2.md)
for those exceptions and remaining validator warnings.

**The generated file is not included in this repository.** These instructions
create it locally from the official RAAML inputs. Generated outputs remain
outside Git under the project's [publication policy](../THIRD_PARTY_MATERIALS.md).

## 1. Install Git and Python

You need:

- [Git](https://git-scm.com/downloads);
- [Python 3.14.4](https://www.python.org/downloads/release/python-3144/), the
  version used by this project; and
- an internet connection for downloading the repository and source inputs.

Open a terminal. On Windows, use PowerShell. On macOS or Linux, use Terminal.
Run:

```text
git --version
python3 --version
```

The first command should print a Git version; the second should print
`Python 3.14.4`.

**On Windows:** use `py -3.14` instead of `python3` in every command below,
including the version check. For example, run `py -3.14 --version`.

You do not need Java, Docker, or any additional Python packages for generation.

## 2. Download this repository

Run these commands one at a time:

```text
git clone https://github.com/florian-zeev/raaml-sysml-v2-preservation.git
cd raaml-sysml-v2-preservation
python3 raaml --version
```

The last command should print the implementation version. Keep this terminal
open and run all remaining commands from this directory.

If you already have a checkout, use that directory instead of cloning again.

## 3. Download and check the official inputs

Run:

```text
python3 raaml sources fetch
```

Wait until it finishes. The first download is about 624 MB: the current command
downloads the full locked input set, including specifications and validator
archives. The generation step does not run those validators. Later runs reuse
verified files already present in `sources/cache/`.

A successful download prints a line beginning with `Fetched`.

Next, run:

```text
python3 raaml sources verify --collection raaml-1.1-definitions
```

A successful check prints a line beginning with:

```text
Verified 17 source artifact(s)
```

This checks that the downloaded RAAML files match the versions and hashes in
[`standards.lock.json`](../standards.lock.json). If either command reports an
error, stop and see the troubleshooting section below.

## 4. Generate the SysML v2 packages

Copy this entire command as one line:

```text
python3 raaml forward --milestone-4 --output-dir generated/packages --diagnostics generated/packages-diagnostics.json
```

`--milestone-4` selects the complete 17-file RAAML definition corpus, including
Core, General, and RBD. The command reads the official inputs, extracts their
model definitions, and writes the SysML v2 representation.

The command can finish without printing anything. Open
`generated/packages-diagnostics.json` in a text editor and check that it
contains `"ok": true` and `"failed": 0`.
The diagnostics also list warnings for preserved, unimplemented source
expressions and the five source relationships not emitted natively.

## 5. Open your generated file

In your file manager, open the repository folder, then `generated`, then
`packages`. Open this file:

```text
generated/packages/raaml-full-corpus.sysml
```

**This is the actual generated SysML v2 model.** It now exists on your computer;
it is not a file downloaded from GitHub. Its package structure includes:

```text
RaamlFullCorpus
├── CoreRAAML
├── CoreRAAMLLib
├── GeneralRAAML
├── GeneralRAAMLLib
├── RBD
├── RBDLib
└── other RAAML packages
```

Use your editor's Find command to locate `package CoreRAAML {`,
`package GeneralRAAML {`, or `package RBDLib {`. RBD definitions include
`InSeries`, `InParallel`, and `ComponentReliabilitySituation`.

For modeling-tool inspection, open the generated `packages` folder in your
SysML v2 editor, then open `raaml-full-corpus.sysml`. Keep the complete file
together: packages refer to shared definitions and other packages. The
project records a [previous check with Syside Editor](syside-editor-check-v0.9.0-rc.2.md).

The adjacent `manifests` folder contains 17 JSON files used to preserve source
information and reconstruct the original models. Open the `.sysml` file to
inspect the SysML v2 packages; keep the manifests if you want to run the
[reverse mapping](python-cli-guide.md#4-reconstruct-the-sysml-v1-definitions).

## If something goes wrong

- **Git or Python is not found:** finish installing it, close and reopen your
  terminal, and repeat the version checks in step 1.
- **Python cannot open `raaml`:** you are in the wrong directory. Change into
  the downloaded `raaml-sysml-v2-preservation` folder and retry.
- **A download fails:** check your internet connection and rerun
  `python3 raaml sources fetch`. Verified downloads are reused. If it still
  fails, retain the terminal error and `reports/diagnostics/sources-fetch.json`.
- **Verification or generation fails:** retain the terminal error,
  `reports/diagnostics/sources-verify.json`, and
  `generated/packages-diagnostics.json`, whichever exist. Do not change the
  expected hashes to make a check pass.

## What this output establishes

These steps generate a preservation-oriented SysML v2 representation of the
official RAAML 1.1 definitions. They do not run the SysML validators or the full
round-trip conformance checks, and they do not establish that the original OCL
constraints execute natively in SysML v2. See the
[Python CLI guide](python-cli-guide.md) for reconstruction and comparison, or
[Getting started](../GETTING_STARTED.md) for the full validation workflow.
