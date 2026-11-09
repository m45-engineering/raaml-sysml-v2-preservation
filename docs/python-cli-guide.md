# Python CLI guide

The Python implementation is the reference command-line implementation of the
RAAML 1.1 preservation mapping. It can extract the defined source facts, map
the complete 17-file definition corpus to SysML v2, reconstruct SysML v1 XMI,
and compare the reconstructed facts with the source facts.

The supported Python interface is the repository-local `./raaml` command. The
modules under `src/raaml_preservation/` are implementation details, not a
stable importable library API. Use the native TypeScript library when an
application needs to embed the mapping directly.

## Scope

The CLI operates on the 17 normative RAAML 1.1 profile and library definition
files recorded in `standards.lock.json`. It does not claim to transform an
arbitrary user-authored RAAML model.

The commands below generate complete-corpus outputs locally. Those outputs may
contain facts derived from official third-party material. They are ignored by
Git and must not be committed or attached to a public issue or release. See
[`THIRD_PARTY_MATERIALS.md`](../THIRD_PARTY_MATERIALS.md).

## Requirements

The current development mapping uses fact and manifest schema version `0.2.0`.
See [native package mapping v0.2](native-package-mapping-v0.2.md) for structural
coverage, explicit source exceptions, and validation commands.

- Git
- Python 3.14.4, as recorded in [`.python-version`](../.python-version)
- an internet connection for `sources fetch`

The forward, reverse, and comparison commands use the Python standard library
and do not require package installation. Java and Docker are not required for
the mapping workflow below. They are used by the separate validator and full
reproduction workflows.

Check the runtime and CLI:

```text
python3 --version
./raaml --version
./raaml --help
```

Run all commands from the repository root.

## 1. Obtain and verify the locked inputs

```text
./raaml sources fetch
./raaml sources verify --collection raaml-1.1-definitions
```

`sources fetch` is the only command in this workflow that uses the network. It
downloads each input from the URL recorded in `standards.lock.json` and rejects
any file whose byte size or SHA-256 differs from the lock.

The inputs are stored under the ignored `sources/cache/` directory. The
repository does not redistribute them.

## 2. Extract the source facts

```text
./raaml facts extract \
  --all \
  --check-determinism \
  --raw-output generated/python-guide/raw-raaml-facts.json \
  --canonical-output generated/python-guide/canonical-raaml-facts.json \
  --diagnostics generated/python-guide/facts-diagnostics.json
```

This writes:

- the source-shaped raw fact document;
- the normalized canonical fact document used for equality; and
- a machine-readable diagnostic report.

`--check-determinism` performs the extraction twice and requires byte-identical
raw and canonical output.

## 3. Map the corpus to SysML v2

```text
./raaml forward \
  --milestone-4 \
  --output-dir generated/python-guide/forward \
  --diagnostics generated/python-guide/forward-diagnostics.json
```

The result is:

```text
generated/python-guide/forward/
├── raaml-full-corpus.sysml
└── manifests/
    ├── CoreRAAML.preservation.json
    ├── ...
    └── STPALib.preservation.json
```

The SysML v2 file is the native structural view. The 17 preservation manifests
carry the source facts, source identity, native-target bindings, and integrity
digests needed for deterministic reconstruction.

## 4. Reconstruct the SysML v1 definitions

```text
./raaml reverse \
  --manifest-dir generated/python-guide/forward/manifests \
  --v2 generated/python-guide/forward/raaml-full-corpus.sysml \
  --output-dir generated/python-guide/reconstructed \
  --diagnostics generated/python-guide/reverse-diagnostics.json
```

The command verifies the manifest payload digests and their binding to the
SysML v2 file before writing 17 reconstructed XMI files. It fails rather than
silently continuing when an input is missing, changed, duplicated, or outside
the locked corpus.

## 5. Compare source and reconstructed facts

```text
./raaml compare \
  --full-corpus \
  --reconstructed-dir generated/python-guide/reconstructed \
  --output generated/python-guide/comparison.json \
  --diagnostics generated/python-guide/compare-diagnostics.json
```

Inspect the result without installing another tool:

```text
python3 -c 'import json; p=json.load(open("generated/python-guide/comparison.json")); print(json.dumps({"ok": p["ok"], "summary": p["summary"]}, indent=2))'
```

A successful comparison contains:

```json
{
  "ok": true,
  "summary": {
    "artifacts": 17,
    "differences": 0,
    "reconstructedFactsSha256": "638ef422aee4a528d5de2a5bca8c7203a0b10ca5e6dfd552c45e76c8f76a7cbc",
    "sourceFactsSha256": "638ef422aee4a528d5de2a5bca8c7203a0b10ca5e6dfd552c45e76c8f76a7cbc"
  }
}
```

This is the implemented preservation test:

```text
canonicalFacts(reverse(forward(x))) == canonicalFacts(x)
```

It is fact equality under the documented contract, not byte-for-byte XMI
equality.

## Diagnostics and failures

Every pipeline command above accepts an explicit diagnostics path and returns
a nonzero process status on failure. A diagnostic document contains an `ok`
field and entries with a machine-readable `code` and human-readable `message`.

For automation:

1. require process status zero;
2. require the command diagnostic report to contain `"ok": true`;
3. for comparison, also require `comparison.json` to contain `"ok": true` and
   `summary.differences` to equal zero; and
4. retain only evidence permitted by the publication boundary.

Use `./raaml COMMAND --help` to inspect every option. For example:

```text
./raaml forward --help
./raaml reverse --help
./raaml compare --help
```

## Validation and scientific reproduction

The pipeline above demonstrates the mapping and canonical equality check. It
does not invoke the pinned SysML v1 and SysML v2 validators.

For the complete evidence workflow—including both validators, adversarial
cases, host/container comparison, and offline reproduction—follow
[`GETTING_STARTED.md`](../GETTING_STARTED.md) and run `./review-reproduce`.
