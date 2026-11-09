# Canonical RAAML fact contract v0.1

**Status:** Implemented and validated for signed candidate `v0.9.0-rc.3`

This is the historical v0.1 contract. Current development adds the v0.2 source
selectors and connector paths documented in
[native package mapping v0.2](native-package-mapping-v0.2.md), while retaining
the facts listed here.

**Corpus:** the 17 artifacts in the `raaml-1.1-definitions` collection of
`standards.lock.json`

## Purpose

This document turns the preservation list in the proposal into a testable data
contract. It does not itself map RAAML to SysML v2. It defines what a mapper
must preserve and gives independent implementations a common comparison
surface.

The production extractor emits two documents:

1. a raw fact document that retains source reference forms and explicit
   presence information; and
2. a canonical fact document whose identities, resolved references, ordering,
   and JSON serialization are deterministic.

The independent corpus audit does not import the production extractor or its
canonicalization helpers. It reports category counts and selected relationships
directly from XML events.

## Corpus observations that constrain the design

The locked corpus contains:

| Fact | Count | Unnamed |
|---|---:|---:|
| Profiles | 9 | 0 |
| Packages, including nested packages | 15 | 0 |
| Stereotypes | 94 | 0 |
| Library Classes | 143 | 0 |
| Enumerations | 5 | 0 |
| Enumeration literals | 35 | 0 |
| Ordinary Associations | 40 | 30 |
| AssociationClasses | 1 | 0 |
| Properties, excluding Ports and ExtensionEnds | 267 | 37 |
| Ports | 65 | 0 |
| Connectors | 94 | 94 |
| Constraints | 60 | 27 |
| Extensions and ExtensionEnds | 84 each | 0 ExtensionEnds |
| Comments | 431 | not applicable |
| Images | 22 | not applicable |
| RAAML stereotype applications in libraries | 108 | not applicable |

There are also 263 root-level SysML stereotype applications. They are needed
while resolving targets and interpreting the source libraries, but they are
not RAAML application facts in the v0.1 preservation comparison.

The corpus has nested packages, including the `RequirementManagement` package
inside the ISO 26262 profile and nested library packages. Package membership
therefore means the complete qualified package path, not only the file's root
profile or package.

The corpus uses both attribute and child-element forms for references. It also
uses both local `xmi:idref` references and external `href` references. Raw facts
must retain the form that was present; canonical facts must resolve both forms
to the same kind of target identity while retaining the original reference
form as a preserved value where the proposal requires it.

## Common rules

### Identity

Identity follows [ADR 0002](../adr/0002-canonical-fact-identity.md).

- Named declarations use artifact, qualified package path, kind, and name.
- Owned facts additionally use their owner's identity.
- Anonymous declarations use a digest of their complete canonical structure,
  never an XMI ID or package sibling position.
- Missing names remain missing.
- A collision or an identity ambiguity is an error.

Original XMI IDs may appear in raw references solely as source-resolution
handles. They must not appear in canonical identities or canonical comparison
facts.

### Presence

Absent and explicitly present values are different facts whenever the proposal
requires source reconstruction. Raw records therefore use either a reference
object with a `form` field or a value object with an explicit `present` field.
Canonical records do not fill an absent optional source value with a UML
default.

This rule is especially important for Association owned-end lower and upper
multiplicity: an omitted literal is not equal to an explicitly written literal
whose value happens to be the UML default.

### Ordering

These arrays preserve source-defined order:

- Enumeration literals;
- Association and AssociationClass member ends;
- Connector ends;
- Opaque-expression language entries and body lines;
- repeated values whose UML relationship is ordered.

All other collections are serialized in canonical identity order and compared
as multisets. XML sibling order is not otherwise a fact.

### References

Every reference record has:

- `role`: the UML relationship being represented;
- `form`: `idref`, `href`, or `attribute`;
- `sourceValue`: the exact source reference value in raw facts;
- `target`: the resolved canonical identity in canonical facts.

An unresolved in-scope reference is an error. A reference to a locked support
artifact may resolve to a stable external qualified name rather than become an
extracted RAAML declaration.

## Fact-category matrix

| Category | Required values | Owner / identity | Order |
|---|---|---|---|
| Artifact root | locked artifact ID, filename, SHA-256, root kind | locked artifact | artifact order from the lock |
| Profile or root package | kind, name, URI when present, qualified path | artifact + kind + name | unordered |
| Nested package | name, qualified path, comments | owning package | unordered |
| Stereotype | name, explicit `isAbstract`, package membership, comments | package path + kind + name | unordered |
| Base property | name, UML metaclass type, explicit multiplicity, property flags | stereotype | unordered |
| Extension | associated base property and ExtensionEnd | package + structural identity | unordered |
| ExtensionEnd | name, type, aggregation, explicit multiplicity | Extension | ordered by the Extension relationship |
| Generalization | owner, source form, resolved target | generalizing declaration | unordered multiset |
| Property / Port | kind, optional name, type, aggregation, explicit multiplicity and default, `isDerived`, `isReadOnly`, `isOrdered`, `isUnique`, subset/redefine links, comments | owning classifier | unordered unless used by an ordered relationship |
| Icon | format, content, and presence of location; XMI ID excluded | owning stereotype | unordered multiset |
| Constraint | optional name, constrained elements, specification languages and bodies, comments | owning declaration | repeated same-name constraints use contract ordinal |
| Library Class | name, `isAbstract`, package path, generalizations, properties, connectors, comments | package path + kind + name | unordered |
| Connector | optional name, kind, ends, comments | owning Class | connector collection unordered; ends ordered |
| ConnectorEnd | role and optional `partWithPort`, each resolved | owning Connector | ordered |
| Enumeration | name, package path, comments, literals | package path + kind + name | literals ordered |
| AssociationClass | name, package path, `isAbstract`, generalizations, ordered member ends, separately owned ends, navigable ends, properties, comments | package path + kind + name | member and navigable ends ordered |
| Ordinary Association | optional name, package path, generalizations, ordered member ends, separately owned ends, navigable ends, comments | named or anonymous package-member rule | member and navigable ends ordered |
| Association owned end | optional name, type, aggregation, explicit lower/upper kind and value, redefine links, comments | owning Association | source owned-end relationship order |
| Import / application machinery | metamodel references, package imports, element imports, profile applications, imported/applied targets, comments | owning package | unordered multiset |
| Namespace prefix | prefix value and applicable namespace/artifact | artifact | unordered multiset |
| RAAML stereotype application | stereotype namespace and name, resolved target, every non-`base_*` value | stereotype + target + occurrence | unordered multiset |

## Raw document requirements

The raw schema must:

- require exactly one record per locked RAAML artifact;
- retain source reference forms and values;
- retain explicit-versus-absent state;
- distinguish `Property`, `Port`, `ExtensionEnd`, `Association`, and
  `AssociationClass`;
- allow anonymous declarations without inventing names;
- retain package paths;
- prohibit undeclared fields.

Raw facts may contain source XMI IDs only in a dedicated `sourceHandle` or
`sourceValue` field. A test scans every other field and fails if an XMI ID
leaks into the comparison surface.

## Canonical document requirements

The canonical schema must:

- contain no source XMI IDs;
- use owner-qualified synthetic identities;
- contain only resolved in-scope references;
- use explicit null or absence consistently as defined by the schema;
- serialize with UTF-8, LF line endings, sorted object keys, and a final
  newline;
- sort every unordered collection by its complete canonical identity;
- retain the ordered arrays named above.

Two extractions from the same verified corpus must be byte-identical.

## Fail-closed behavior

Extraction fails with a stable diagnostic code when:

- a source file does not match its lock entry;
- XML preflight rejects the input;
- an in-scope element or value shape is unsupported;
- a required target cannot be resolved;
- a name contains the reserved `::` identity separator;
- an anonymous structural identity is ambiguous;
- a synthetic identity collides;
- a required top-level fact category is absent from the output schema or
  coverage matrix.

No warning may silently drop an in-scope fact.

## Coverage obligations

Every matrix row requires:

- at least one golden corpus fact;
- at least one negative or mutation test;
- a production-extractor count;
- an independently computed audit count;
- an explicit schema path.

The coverage gate fails if a category is removed from the schema, extractor,
audit, golden set, or mutation suite.

## Claim boundary

This contract does not establish that:

- a SysML v2 encoding parses;
- RAAML facts can be mapped forward;
- a v1 artifact can be reconstructed;
- OCL constraints have equivalent behavior in another language or engine.

Those claims are separate from this contract. The complete
forward-and-reverse validation result is recorded in
[`validation-report-v0.9.0-rc.3.md`](validation-report-v0.9.0-rc.3.md).
