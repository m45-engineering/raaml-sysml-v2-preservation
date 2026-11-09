# Native package mapping: development version 0.2

This describes the current development generators. It does not change the
historical results for signed candidate `v0.9.0-rc.3`, and is not a new signed
release or a claim of complete RAAML behavioral equivalence.

## What changed

Both Python and TypeScript now generate native structure instead of only
named declaration shells:

- RAAML stereotype inheritance becomes metadata-definition inheritance.
- Internal library inheritance and abstractness are emitted.
- Actual source Block and ConstraintBlock applications select part and
  constraint definitions. Names are not used to guess these classifications.
- Properties retain their names, types, multiplicities, ordering, uniqueness,
  defaults, internal subsetting/redefinition, and derived status.
- The 65 source ports belong to ConstraintBlocks. They become value parameters,
  not newly invented SysML v2 port interfaces.
- Nested connector paths and BindingConnector applications are read from the
  source. Accessible bindings are emitted in their owning definitions.
- Concrete RAAML stereotype applications become metadata annotations.
- Source comments and unevaluated constraint expressions appear in the text.

The model remains one `raaml-full-corpus.sysml` file containing 17 packages.
Generated files and manifests remain local and ignored by Git.

## Preservation format

Raw facts, canonical facts, and preservation manifests now use schema version
`0.2.0`. The source contract adds:

- `sysmlKind` on declarations: `Block`, `ConstraintBlock`, or `null`;
- `isBinding` on connectors; and
- ordered `propertyPath` references on connector ends.

The reverse mappers reconstruct these source applications too. Existing fact
categories remain preserved. The additional facts change canonical hashes and
can change identifiers derived from anonymous source structures. Version 0.1
manifests are not accepted as version 0.2 manifests; regenerate them from the
locked sources. The standards lock and release-report formats retain their
own version numbers.

## Explicit limits and source exceptions

**None of the 60 source constraint expressions is claimed to execute in SysML
v2.** Their declarations contain `UNIMPLEMENTED` documentation with the source
language and expression. Exact records remain in manifests. No assertion is
added that would falsely imply those expressions are enforced.

Four source connectors in `FTALib` refer through `FTATree.topEvent` while owned
by `HouseEvent`, `IntermediateEvent`, `TopEvent`, or `ZeroEvent`. Those owners
do not inherit the referenced feature. Both generators identify the inaccessible
path, emit an `UNMAPPED` comment, and retain the connector in the manifest.
They do not invent a different owner or relationship.

The source applies the abstract `DependabilityRequirement` stereotype to
`ISO26262SafetyRequirementTemplate`. SysML v2 rejects an instance of abstract
metadata. This application is explicitly marked `UNMAPPED` and preserved in
the manifest; the stereotype remains abstract.

Further structural translation boundaries:

- SysML v1/UML metaclass inheritance and `base_*` properties are source-profile
  machinery, not direct SysML v2 type relationships. They remain in manifests;
  source metaclass parents are identified in generated comments.
- A v2 connection end identifies one participant. Connection ends use `[1]`;
  v1 association multiplicities and end refinements remain in manifests.
  Classifier-owned relationship properties retain their source multiplicities
  and internal refinements in the native model.
- External v1 property refinements and the v1 read-only flag remain in
  manifests. They are not presented as enforced v2 constraints.
- SysML v2 enumeration definitions are abstract by language semantics; their
  literals are the concrete values. Source enumeration abstractness remains
  in the manifest rather than overriding this language rule.

## Package-level validation

The Java adapter returns a `nativeStructure` map from the pinned validator's
resolved model. The full-corpus build gate compares it with source obligations
for definition kinds, abstractness, internal inheritance, property presence,
types, multiplicities, ordering, uniqueness, defaults, derived status,
internal property refinements, and concrete metadata annotations. It fails on a missing
relationship even if the remaining text parses successfully.

The tests modify a copy of the generated packages to remove one inheritance
relationship. That text still validates, but the structural comparison detects
the missing relationship. This is a package regression test, not an example
application model.

The validator currently reports zero errors and 15 warnings. The warnings
concern source multiplicity refinements, dimensioned time values bound to
scalar parameters, and duplicate names inherited from multiple parents. They
remain visible; the project does not suppress them or claim warning-free output.

Use the [generation guide](generate-sysml-v2-packages.md) to produce the file.
On a platform supported by the pinned tooling, validate it with:

```text
python3 raaml tooling bootstrap
python3 raaml validate-v2 generated/packages/raaml-full-corpus.sysml --diagnostics generated/packages-validation.json
python3 raaml tests milestone-4
```

The final command checks both validator acceptance and source-to-native
structure. Standalone `validate-v2` checks language acceptance only. Neither
command evaluates the preserved source expressions.

## Development validation record

Local validation on November 9, 2026 used Python 3.14.4 and the pinned SysML
validator. Python and TypeScript produced byte-identical SysML text and
canonical facts. Reconstruction preserved all 17 source artifacts with zero
canonical differences, zero v1/v2 validator errors, and 36 passing adversarial
cases. This is local development evidence, not a signed release.

| Artifact | SHA-256 |
| --- | --- |
| Canonical facts v0.2 | `638ef422aee4a528d5de2a5bca8c7203a0b10ca5e6dfd552c45e76c8f76a7cbc` |
| Generated SysML v2 | `b02964848e164f9a728ca8d0341cd945c987b2749a71efd47b7d705c2b0b7b48` |

The Python unit tests and TypeScript tests check the new mapping and reversal.
The milestone-4 build additionally checks the resolved native structure.
Detailed generated evidence is local under `generated/` and is not committed.
