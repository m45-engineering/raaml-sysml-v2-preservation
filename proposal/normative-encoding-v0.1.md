# RAAML 1.1 on SysML v2: a preservation encoding for the normative definitions

**Status:** Draft Community Proposal v0.1
**Author:** Florian Wolf
**Intended license:** Creative Commons Attribution 4.0 International (CC BY 4.0), subject to a separate review of incorporated or redistributed third-party artifacts
**Standing:** Independent community proposal; not an OMG specification, submission, or endorsement

This document describes the v0.1 preservation proposal and signed-candidate
evidence. The current development implementation's expanded native structure,
schema v0.2 additions, and explicit limitations are documented in
[native package mapping v0.2](../docs/native-package-mapping-v0.2.md).

## Introduction

RAAML—the OMG Risk Analysis and Assessment Modeling Language—gives safety and reliability concepts a precise form that software can inspect. A hazard, unsafe control action, fault-tree gate, or assurance claim is not merely text on a diagram. It has a type, properties, and defined links to other parts of the system model. RAAML covers methods including STPA, FTA, FMEA, RBD, GSN, ISO 26262 analysis, and security analysis.

RAAML 1.1, published by the OMG in December 2025, was built for SysML v1.6. It uses UML 2.5.1 profiles: a profile adds specialized meanings, called stereotypes, to existing kinds of UML element such as Class, Property, and Signal.

SysML v2 is built differently. KerML supplies its basic modeling concepts, and metadata definitions provide its extension mechanism. A SysML v2 tool therefore cannot simply load a SysML v1 profile, and a v1 stereotype cannot simply be copied into a v2 model. A translation must decide what each definition becomes. That decision can lose information.

This translation is needed because SysML v1 and v2 will coexist while new programs and tools begin using v2. Remaining on v1 may be correct for an existing program. But if a system architecture moves to v2 while its RAAML analysis remains in a separate v1 environment, the links among system elements, hazards, failure modes, controls, claims, and evidence become harder to maintain. A common preservation rule is safer than asking each organization or tool vendor to invent a different translation.

SysML v2 also defines a standard textual notation. SysML v1 XMI is technically text, but it is commonly verbose, tool-dependent, and poorly suited to reviewing engineering changes. A stable textual model makes focused diffs, automated checks, and Git-based version history more practical. Git history is tamper-evident rather than tamper-proof; safety or certification use also needs signed baselines, access controls, protected history, independent retention, and approval records.

This document proposes a translation for the 17 official RAAML 1.1 definition files published by the OMG: nine profiles and eight libraries. In standards language, these files are *normative*: they are part of the material that defines RAAML 1.1, not merely examples.

The document lists the facts that must survive a trip from v1 to v2 and back. They include stereotype definitions, the kinds of UML elements they extend, inheritance, properties, OCL constraints, icons, library classes, associations, Ports, connectors, enumerations, imports, and the stereotype applications already contained in the official library files.

The proposal does **not** cover RAAML models created by users. Version 0.1
defines a narrower test: read the listed facts from each official v1 file,
translate the file to v2, rebuild v1 XMI, and confirm that the same facts are
still present. At signed candidate tag `v0.9.0-rc.3`, the Python reference
implementation and native TypeScript implementation passed that test for all
17 official files with zero
differences in the defined fact set. Spacing, XML element order, and
tool-generated XMI IDs are not part of the test.

This is an **independent community proposal** for technical review. It does not define a new version of RAAML and should not decide questions that belong to future OMG work. Its purpose is narrower: keep the existing RAAML 1.1 definitions usable while v1 and v2 tools coexist.

## Executive summary

**Problem.** RAAML 1.1 defines its safety and reliability concepts as SysML v1/UML profiles. SysML v2 uses a different foundation and cannot load those profiles directly.

**Approach.** Rather than redesign RAAML, the proposal gives each official v1 definition a useful v2 form and keeps a record of the source details needed to rebuild it. A stereotype becomes a v2 `metadata def`. A plain library Class becomes an `occurrence def`; official specialized rules apply when Block or ConstraintBlock is present. The record keeps the original UML bases, inheritance, properties, extension-end names, icons, and OCL references. The original OCL text is stored rather than declared equivalent to a v2 constraint without proof.

**Key decisions.**

- Use a familiar v2 form only when doing so does not erase a listed v1 fact. Section 11 shows shortcuts that are forbidden.
- When several v2 forms seem possible, use one fixed selection rule and record every source fact needed for reversal.
- Generate repeatable XMI IDs with a specified SHA-256 rule. Repeatable IDs do not make the whole XML file byte-for-byte identical.
- Require an implementation to show that every listed fact survives all 17 official files. The signed candidate has passed this test; Section “Implementation evidence” states the limits of that result.

**Readership map.**

- *What gets preserved* — Section 1.
- *Encoding pattern for a single stereotype* — Section 2 through Section 4.
- *Mapping table for a specific RAAML profile (CoreRAAML, STPA, FTA, FMEA, RBD, GSN, ISO26262, security)* — Section 9.
- *Implementing the reverse mapper* — Section 10.
- *Designing test coverage* — Section 10.7 (fact-diff conformance).
- *Why the encoding takes the shape it does* — Section 11 (what preservation forbids).

## Implementation evidence

The implementations at signed candidate tag `v0.9.0-rc.3` report:

- 17 source artifacts and 17 preservation manifests;
- 343 generated native v2 targets;
- zero SysML v2 validation errors with the pinned validator;
- 17 reconstructed v1 artifacts and zero v1 validation errors;
- zero differences in the complete canonical fact comparison;
- 33 OCL expressions parsed and name-resolved;
- 36 passing adversarial cases in the reference conformance suite;
- a passing native TypeScript canonical equality gate; and
- byte-identical 49-file release directories from a clean Linux host and an
  offline pinned container.

The complete evidence identity and verification command are in
[`docs/validation-report-v0.9.0-rc.3.md`](../docs/validation-report-v0.9.0-rc.3.md).

This evidence supports only the preservation contract defined here. It does
not cover arbitrary user-authored RAAML models, prove equivalent OCL
evaluation, prove cross-tool semantic equivalence, or constitute independent
external reproduction. After the candidate was signed, a manual
maintainer-operated check found no problems when Sensmetry Syside Editor
0.10.3 validated the exact generated SysML v2 text. The encoding remains a
community proposal, not an OMG standard.

## Reference inputs

The proposal is written against the following 17 official RAAML 1.1 XMI files published by the OMG. The files are not redistributed by this repository while their redistribution rights remain under review:

- `CoreRAAML.xmi`, `CoreRAAMLLib.xmi`
- `GeneralRAAML.xmi`, `GeneralRAAMLLib.xmi`
- `STPA.xmi`, `STPALib.xmi`
- `FTA.xmi`, `FTALib.xmi`, `FMEA.xmi`, `FMEALib.xmi`, `RBD.xmi`, `RBDLib.xmi`
- `GSN.xmi`, `ISO26262.xmi`, `ISO26262Lib.xmi`, `GeneralRAAMLSecurity.xmi`, `GeneralRAAMLSecurityLib.xmi`

These comprise **nine profile files and eight library files**. The proposal text can be openly licensed without automatically granting permission to redistribute the OMG files themselves. That question needs a separate rights review.

## 1. Scope of the preservation contract

The test compares model facts, not XML text. A *fact* is one entry in the list below. Two files pass when extraction produces the same standard fact list from both. The required v0.1 test is:

```
facts(reverse(forward(officialFile))) == facts(officialFile)
```

This test applies only to the 17 official definition files. A future version may add a separate test for models created by users.

The preserved fact set:

1. Profile-level declarations: profile name, profile URI, profile-owned comments and their annotated elements, and each `uml:Stereotype` — its name, `isAbstract` flag, profile membership, and `ownedComment` bodies.
2. Each stereotype's `base_*` properties — the full set of base UML metaclasses it extends.
3. Each stereotype's `uml:Extension` `ownedEnd` name (e.g. `extension_ControlAction`).
4. Each stereotype's `uml:Generalization` edges, including both the intra-profile idref form (`general="..."`) and the cross-profile href form (`<general href="...xmi#..."/>`).
5. Each stereotype's owned properties that are **not** `base_*`: their name, type (primitive, Enumeration, UML/SysML metaclass reference, library-class reference, or another stereotype), multiplicity, default value, `isDerived` flag, `subsettedProperty` and `redefinedProperty` links.
6. Each stereotype's `icon` content (SVG payload, hex-encoded) when present.
7. Each stereotype's OCL constraints: the constraint name, the OCL text verbatim, and the `constrainedElement` reference (context).
8. Library `uml:Class` declarations: name, `isAbstract`, package membership, generalizations (intra-library idref and cross-library href), all owned properties with the metadata of item 5 (including `uml:Port`-typed properties discriminated by `propertyKind`, preserving the 65 Ports in `RBDLib` (45), `FTALib` (16), and `FMEALib` (4)), and all `<ownedConnector>` elements with their `ConnectorEnd` shape (94 connectors: `RBDLib` 69, `FTALib` 21, `FMEALib` 4). Ports carry the same field set as Properties plus the Port discriminator; Connectors are preserved via `Raaml_ConnectorDef` on the enclosing library class (Section 6).
9. Library `uml:Enumeration` declarations: name, ordered `ownedLiteral` list.
10. `uml:AssociationClass` declarations: name, package membership, `isAbstract`, ordered `memberEnd` references, separately owned end declarations, `navigableOwnedEnd` references, generalizations, owned properties, and comments.
11. Plain `uml:Association` declarations in library packages: name, generalizations, ordered `memberEnd` references, separately owned end declarations, `navigableOwnedEnd` references, and per-owned-end name / type / aggregation / explicitly present multiplicity literals / `redefinedProperty` / comments. The library XMIs contain 40 such associations: 1 in `CoreRAAMLLib`, 7 in `GeneralRAAMLLib`, 7 in `STPALib`, 4 in `FTALib`, 7 in `FMEALib`, 2 in `RBDLib`, 12 in `ISO26262Lib`, and 0 in `GeneralRAAMLSecurityLib`. Member ends may be owned by the association or by a classifier; ownership is not normalized away.
12. Profile and package machinery present in the normative artifacts: `metamodelReference`, `ProfileApplication`, `PackageImport`, `ElementImport`, namespace-prefix values, imported targets, and relevant owned comments.
13. Stereotype applications contained in the normative library artifacts: the stereotype identity, target element, and values for every non-`base_*` stereotype property. For example, `STPALib.xmi:289-305` applies `STPA::UndesiredControlAction` to library classes. Arbitrary applications in user-authored system models are outside v0.1 scope.

The following file-format details are explicitly **outside** the list: original XMI IDs, ordering of elements within a package, whitespace, comments on the XMI root, and the choice between the compact and expanded XML forms for stereotype applications. The reverse mapper writes the compact form used by these source files.

The draft calls this a *fact-preserving round trip*. It does not yet use the stronger word *bijection*. That would require a clearly defined set of allowed v2 inputs and a tested reverse property for that set. Version 0.1 also does not claim that a native v2 constraint means the same thing as the source OCL; it preserves the OCL text and the elements to which it is bound.

## 2. Core pattern: a v2 definition plus a source record

Each RAAML 1.1 stereotype becomes a v2 `metadata def`. Section 3 explains how the mapper chooses the kind of v2 element that the metadata can annotate. Facts about one definition are stored with that definition. Facts about the whole source file are stored once in a required **preservation manifest** beside the v2 model.

The manifest records which source file this is, whether it is a profile or library, its package or profile name, its URI, comments, imports, profile applications, namespace values, and the OCL records described in Section 5. Version 0.1 uses JSON. Choosing one form keeps the pass-or-fail test simple.

Each import record distinguishes an ordinary `PackageImport` from a
`MetamodelReference`. Both reuse the official `NamespaceImport` target for the
underlying PackageImport. The explicit discriminator is mandatory because the
official transformation has no MetamodelReference-specific rule. Profile
applications are also retained in the manifest because the official
transformation does not map them.

The SysML v2 fragments below are **illustrative pseudocode** that defines the
intended information shape. They are not accepted concrete syntax unless a
block is explicitly labeled as validated syntax. The reference
implementation's generated `.sysml` files are the parser-tested concrete
encoding. At the signed candidate tag, every generated official
definition was written in the repository's accepted v2 syntax and passed the
pinned validator. After `v0.9.0-rc.2` was signed, the exact full-corpus text
also produced no reported problems in a manual Sensmetry Syside Editor 0.10.3 check. That observation is
not part of the immutable `rc.2` candidate or an automated conformance gate.

The base payload, applied to every generated `Raaml_*` metadata def:

```
metadata def Raaml_BaseAnnotation {
    attribute v1Profile: String[0..1];                            // e.g. "STPA"; mandatory on stereotype metadata,
                                                                  // absent on library-only markers
    attribute v1StereotypeName: String[0..1];                     // e.g. "ControlAction"; mandatory on stereotype metadata,
                                                                  // absent on library-only markers
    attribute v1Bases: Raaml_BaseRef[0..*];                       // full base_* set
    attribute v1IsAbstract: Boolean = false;
    attribute v1ExtensionEndNames: Raaml_ExtensionEndName[0..*];  // per base_*
    attribute v1Generalizations: Raaml_ElementRef[0..*];          // stereotype-to-stereotype
    attribute v1OwnedProperties: Raaml_PropertyDef[0..*];         // non-base_* owned
    attribute v1PropertyValues: Raaml_PropertyValue[0..*];        // per stereotype application
    attribute v1OwnedComments: String[0..*];
    attribute v1Icons: Raaml_Icon[0..*];
    attribute v1OCLConstraints: Raaml_OCLConstraintRef[0..*];
    attribute v1AnnotatedMetaclass: String[0..1];                 // disambiguates v2-kind reverse (Section 3.3);
                                                                  // normative only where an in-library
                                                                  // stereotype application requires it
}

datatype Raaml_BaseRef {
    attribute metaclass: String;              // e.g. "Signal", "Element", "Abstraction"
    attribute baseAttributeName: String;      // canonical form "base_<metaclass>";
                                              //   both fields must be consistent:
                                              //   metaclass == substring after "base_"
    attribute multiplicityLower: String = "1";
    attribute multiplicityUpper: String = "1";
    attribute typeHref: String[0..1];         // verbatim <type href="..."/> URI;
                                              //   e.g. "http://www.omg.org/spec/UML/20161101/UML.xmi#Class"
                                              //   or "http://www.omg.org/spec/UML/20131001/UML.xmi#Class"
                                              //   for LossScenario — preserves source URI variants
}

datatype Raaml_ExtensionEndName {
    attribute forBase: String;                // e.g. "Class"
    attribute extensionEndName: String;       // e.g. "extension_ControlAction"
}

datatype Raaml_ElementRef {
    attribute kind: String;                   // "stereotype" | "libraryClass" | "umlMetaclass"
                                              //   | "sysmlMetaclass" | "enumeration"
                                              //   | "libraryAssociation" | "associationClass"
                                              //   | "property" | "port" | "connector"
                                              //   | "associationEnd" | "enumerationLiteral"
                                              //   | "profile" | "package"
    attribute profileOrLibrary: String[0..1]; // e.g. "CoreRAAML", "STPALib", "SysML"
    attribute name: String;                   // resolvable within profileOrLibrary
    attribute href: String[0..1];             // for cross-artifact edges
    attribute ownerName: String[0..1];        // when kind is "property" or "enumerationLiteral"
}

datatype Raaml_PropertyDef {
    attribute name: String;                   // not starting with "base_"
    attribute typeRef: Raaml_ElementRef;
    attribute multiplicity: String;           // e.g. "1", "0..1", "0..*"
    attribute defaultValue: String[0..1];     // serialized form
    attribute defaultValueKind: String[0..1]; // "LiteralString" | "LiteralInteger" | "LiteralBoolean"
                                              //   | "LiteralUnlimitedNatural" | "LiteralReal"
                                              //   | "LiteralNull" | "InstanceValue"
                                              //   | "OpaqueExpression" — discriminator for defaultValue
    attribute isDerived: Boolean = false;
    attribute aggregation: String = "none";   // "none" | "shared" | "composite"
    attribute propertyKind: String = "Property"; // "Property" | "Port" — discriminates
                                                 //   <ownedAttribute xmi:type="uml:Property">
                                                 //   from <ownedAttribute xmi:type="uml:Port">
    attribute subsettedProperty: Raaml_ElementRef[0..*];
    attribute redefinedProperty: Raaml_ElementRef[0..*];
    attribute ownedComments: String[0..*];
}

datatype Raaml_ConnectorDef {
    attribute visibility: String = "public";  // "public" | "private" | "protected"
    attribute ends: Raaml_ConnectorEnd[2..*]; // always 2 in the current RAAML corpus,
                                              //   but UML 2.5.1 permits more
    attribute ownedComments: String[0..*];
}

datatype Raaml_ConnectorEnd {
    attribute roleRef: Raaml_ElementRef;             // points to a Port or Property
    attribute partWithPortRef: Raaml_ElementRef[0..1]; // points to the owning part usage,
                                                       //   empty when the end is a direct role
}

datatype Raaml_PropertyValue {
    attribute propertyName: String;
    attribute valueKind: String;              // "string" | "enumLiteral" | "elementRef"
    attribute stringValue: String[0..1];
    attribute enumerationRef: Raaml_ElementRef[0..1];
    attribute enumerationLiteralName: String[0..1];
    attribute elementRef: Raaml_ElementRef[0..1];
}

datatype Raaml_Icon {
    attribute mimeType: String;               // e.g. "image/svg+xml" (informational)
    attribute format: String[0..1];           // verbatim uml:Image@format attribute
                                              //   (e.g. "SVG" in FTA.xmi;
                                              //   "custom_created.mdico" in GSN.xmi)
    attribute location: String[0..1];         // verbatim uml:Image@location attribute
                                              //   (filesystem path or URL, may be empty)
    attribute encoding: String;               // "hex"
    attribute content: String;                // hex-encoded byte stream, preserved verbatim
}

datatype Raaml_OCLConstraintRef {
    attribute constraintKey: String;          // owner-qualified key into the constraint store (Section 5)
}
```

Every RAAML 1.1 `uml:Stereotype` maps to a SysML v2
`MetadataDefinition`, following official rule
`StereotypeMetadataDefinition_Mapping`. The stereotype's `base_*` Properties
do not select a different definition kind. They state which UML metaclasses
the metadata may annotate and remain explicit preservation facts.

The following table is total over the base metaclasses used in the RAAML 1.1
XMIs:

| RAAML 1.1 `base_*` | Normative v2 carrier | Preservation consequence |
| --- | --- | --- |
| `Class`, `Property`, `Signal`, `DataType`, `State` | `MetadataDefinition` | Retain the exact base metaclass, Property multiplicity, Extension, and ExtensionEnd. |
| `Dependency`, `Abstraction`, `Association` | `MetadataDefinition` | Retain the exact relationship metaclass; nearby v2 relationship concepts do not replace the RAAML stereotype. |
| `Comment`, `Package`, `Classifier`, `Element` | `MetadataDefinition` | Retain the exact general or concrete annotation domain for reversal. |

`SysML::Block` is a SysML v1 stereotype, not a basic kind of UML element. It therefore never appears as `base_SysML::Block`. Definitions such as `CoreRAAML::Situation`, `STPA::ControlStructure`, and `ISO26262::DependabilityRequirement` extend UML `Class` and separately inherit from the SysML `Block` stereotype. The mapper preserves both facts without changing the RAAML stereotype's `MetadataDefinition` carrier.

## 3. Stereotype definitions and applications

### 3.1 One carrier for every stereotype definition

Every source `uml:Stereotype` has one normative v2 carrier:
`MetadataDefinition`. There is no base-metaclass precedence list. A stereotype
that extends `Signal`, `Class`, and `DataType` remains one
`MetadataDefinition` with three preserved source bases.

The forward mapper may derive domain-oriented views for navigation, but those
views are non-normative and cannot be used to infer the v1 bases during
reversal.

### 3.2 Reverse rule

`v1Bases` stores only the `base_*` properties declared on that stereotype. It does not copy inherited bases. For example, the concrete FTA gates inherit `base_Class` and `base_Property` from `FTA::Gate`, and the concrete FTA events inherit them from `FTA::Event`. Their own `v1Bases` lists are empty. During reversal, the mapper follows `v1Generalizations` to recover the complete inherited set.

For each entry in `v1Bases` (locally owned):

1. Emit a `uml:Property` `ownedAttribute` named `base_<Metaclass>` on the regenerated `uml:Stereotype`.
2. Emit a corresponding `uml:Extension` packagedElement and `uml:ExtensionEnd` with `name` taken from `v1ExtensionEndNames` (defaulting to `extension_<StereotypeName>`).
3. Emit multiplicity from `Raaml_BaseRef.multiplicityLower`/`multiplicityUpper` (default `[1]` when unspecified).

FTA `Event` and `Gate` allow each base with multiplicity `[0..1]`, so the record keeps those bounds. The reverse mapper must not generate new `base_*` properties on subtypes that only inherit them. Doing so would add facts that were not in the source. The inheritance link is enough to carry the inherited property and its multiplicity.

### 3.3 The `Element` case

`base_Element`, used by `IDCarrier`, `Undeveloped`, `Item`, and `ASILAssignment`, means “this stereotype may annotate any UML element.” SysML v2 has no single more-specific form that captures that statement. The mapper therefore handles the definition and an application separately:

- **Definition:** `Raaml_<Name>` may annotate a general element; `v1Bases` records `Element`.
- **Application:** if an in-scope source application targets a Class, Property, Package, Comment, or another UML kind, `v1AnnotatedMetaclass` records that original kind.
- **Reverse:** the recorded kind tells the mapper which `base_*` value to write. Without it, the mapper would know only that the original target was some UML element.

`v1AnnotatedMetaclass` is mandatory on every instance-level application. The
official occurrence helpers do not map an application instance, connect it to
the applied element, or preserve its tagged values. The reverse mapper must
therefore use the explicit application record rather than infer the source
metaclass from a v2 element kind.

### 3.4 Stereotype generalizations

Generalizations to `SysML::Block`, `CoreRAAML::Situation`,
`SysML::AbstractRequirement`, and other RAAML or SysML v1 stereotypes remain
ordered source references in `v1Generalizations`. They do not change the
normative `MetadataDefinition` carrier.

For example, `ISO26262::DependabilityRequirement` retains both of its source
generalizations, and `CoreRAAML::Situation` retains its generalization to
SysML v1 `Block`. Reversal rebuilds those recorded edges directly. A
domain-oriented tool may interpret them to derive PartDefinition or
OccurrenceDefinition views, but those views are outside the version 0.1
preservation encoding.

### 3.5 Application records

For each of the 108 in-scope RAAML stereotype applications, the manifest
records:

- the qualified RAAML stereotype identity;
- the resolved target element identity;
- the target's original UML metaclass;
- every non-`base_*` tagged value, including primitive kind, enumeration
  literal identity, order, and resolved element references where applicable.

The official `StereotypeOccurenceUsage_Mapping` takes a `Stereotype`
definition as its source. It does not take an application instance, connect a
usage to the applied element, or transfer tagged values. The helper operations
for discovering applied stereotypes and tag values are implementation
specific. A mapper may emit a `MetadataUsage` as a supplemental navigable
view, but reversal always uses the application record.

## 4. Properties and Property-based stereotypes

`Controller`, `Sensor`, `Actuator`, and `ControlledProcess` extend UML
`Property` and `Class`. `BasicEvent` also extends both, while FTA `TransferIn`
extends `Property` without extending `Class`.

These are facts about each stereotype definition, so all of those stereotypes
remain `MetadataDefinition`s. The mapper does not create a companion Class or
choose a usage kind from an extension Property's aggregation.

Actual UML Properties in the library files follow the official Property
rules. Across the 267 source Properties, the relevant selectors are ownership,
association role, owning ConstraintBlock, source type, and whether the type
has SysML v1 `Block` applied. Composite aggregation alone does not select
`PartUsage`; the corpus contains no Property that satisfies the official
PartProperty filter.

The complete mutually exclusive Property table is frozen in
`analysis/property-transformation-surface-v0.1.json`. The preservation record
still retains source ownership, type reference, aggregation, multiplicity,
subset/redefinition references, and the `Property` versus `Port` distinction.

## 5. OCL constraint store

The JSON manifest keeps the original OCL and JavaScript constraints in a
**constraint store**. Version 0.1 also emits the official
`ConstraintDefinition`, `AssertConstraintUsage`, and `CalculationUsage` view
when its required fields exist. The stored source expression remains the
source used for reconstruction and behavioral claims.

The corpus contains 60 constraint OpaqueExpressions. Fifty-nine have exactly
one language and one body: 33 OCL2.0 and 26 JavaScript. FMEALib
`RPNCalculation` has one body, `RPN=SEV*DET*OCC`, but no language. The official
`OpaqueExpressionSpecification_Mapping` evaluates `language.get(0)`, which is
invalid for that source. Version 0.1 does not invent a language; it preserves
the expression and emits an explicit diagnostic instead of a
TextualRepresentation for that body.

Constraint store schema (one entry per v1 `uml:Constraint`):

```
{
  "storeId": "FTA.constraints",
  "constraints": [
    {
      "constraintKey": "FTA::stereotype::Tree::TreeIsFTATree::1",
      "owner": {
        "kind": "stereotype",
        "profileOrLibrary": "FTA",
        "name": "Tree"
      },
      "name": "TreeIsFTATree",                      // constraint name from v1
      "oclText": "self.base_Class.closure(...)",    // illustrative; exact source text at runtime
      "constrainedElements": [                      // item 7 of Section 1
        { "kind": "stereotype",
          "profileOrLibrary": "FTA",
          "name": "Tree" }
      ],
      "ownedComments": ["..."],
      "specification": {
        "language": "OCL",
        "bodyLines": ["..."]                        // preserved multi-line layout
      }
    }
  ]
}
```

Each `Raaml_*` metadata def's `v1OCLConstraints` attribute references store entries by `constraintKey`. The key is:

```
<artifact>::<ownerKind>::<ownerQualifiedName>::<constraintName>::<oneBasedOrdinal>
```

The final number distinguishes repeated constraints with the same owner and name; counting begins at one in source order. The owner must be part of the key because `CoreRAAML.xmi` contains two constraints named `ClientIsSituation`: one belongs to `Violates`, the other to `RelevantTo`.

**Names inside OCL must still resolve.** The source constraints refer to RAAML declarations by name in several forms:

- Library-class names: FTA and RBD expressions traverse `base_Class`
  generalizations and test for the class name `FTATree`.
- Profile stereotype names: GSN expressions invoke `allInstances()` on
  `GSNArgumentNode`, `Strategy`, `Goal`, `Undeveloped`,
  `ContextualInformation`, and `GSNNode` (GSN.xmi:109-166).
- Library association / enumeration names when navigated by name.

The mapper therefore keeps the names of referenced classes, stereotypes, associations, and enumerations unchanged. Renaming one without rewriting and rechecking its OCL would leave the constraint pointing at the wrong thing or at nothing.

Each stored constraint also lists the RAAML names found in its text. The test can then fail immediately if a name no longer resolves after reconstruction:

```
"referencedNames": [
  { "kind": "stereotype", "profileOrLibrary": "GSN", "name": "GSNArgumentNode" },
  { "kind": "libraryClass", "profileOrLibrary": "FTALib", "name": "FTATree" }
]
```

**Generation.** A real OCL 2.4 parser must produce `referencedNames`. It reads the expression as OCL syntax, finds names used as variables or types, and resolves each name using the imports visible to the owning profile. If more than one declaration could match, it records every candidate and reports the ambiguity. The reference implementation parsed and resolved all 33 OCL expressions in the official corpus at the signed candidate tag.

A text search is not enough. OCL contains nested navigation, `closure(...)`, `.allInstances()`, and conditional expressions. A search can mistake a keyword for a name or miss a name because it appears inside a larger expression.

**Role.** `referencedNames` is used at two points:

- **Forward-mapping emission**: populated once per constraint when the constraint store is generated.
- **Round-trip conformance (Section 10.7)**: the fact-diff checks that every name in `referencedNames` resolves to a declaration in the reverse-mapped model. A mismatch fails conformance even when `oclText` is byte-identical, because it means the OCL is now dangling.

`referencedNames` is only a reference check. Passing it proves that the named declarations still exist; it does not prove that the constraint evaluates successfully. The model structure may have changed in another way. Behavioral evaluation is outside the version 0.1 conformance claim.

**Optional additional validation.** An implementation may rebuild the UML view and evaluate the original OCL there. Any such result must name the OCL engine and version and must be reported separately from fact preservation. Version 0.1 does not require evaluation on either v1 or v2 and does not claim equivalent behavior across OCL engines.

## 6. Library elements

Each plain UML Class in an official library becomes a v2
`OccurrenceDefinition`, following `Class_Mapping`, and is marked with
`Raaml_LibraryClass`. The corpus contains 100 such Classes. Seven other
Classes have SysML v1 `Block` applied and become `PartDefinition`s; 36 have
`ConstraintBlock` applied and become `ConstraintDefinition`s. The
preservation marker records the original UML Class and applied stereotype
facts in every case. AssociationClasses, ordinary Associations, and
Enumerations use the separate rules below.

Each generated `def` carries a `Raaml_LibraryClass` annotation that extends `Raaml_BaseAnnotation`:

```
metadata def Raaml_LibraryClass :> Raaml_BaseAnnotation {
    attribute v1Library: String;              // e.g. "STPALib"
    attribute v1ClassName: String;
    attribute v1OwnedConnectors: Raaml_ConnectorDef[0..*];  // Section 2; for library classes
                                                            //   that own <ownedConnector>s
                                                            //   (RBDLib, FTALib, FMEALib)
    // v1IsAbstract, v1OwnedProperties, v1OwnedComments inherited from base.
    // Ports in v1OwnedProperties use propertyKind = "Port".
}
```

A UML library Class that inherits from another Class becomes a v2 definition that specializes its parent. The source may point to a parent in the same file with an ID or to a parent in another file with a URL plus fragment. `v1Generalizations` records which form was used so the reverse mapper can write it again.

A UML Enumeration becomes a v2 `enum def`. Literal order is preserved because changing the sequence would change the listed source fact. Four of the five Enumerations also have SysML v1 `ValueType` applied. For those four, version 0.1 deliberately chooses the EnumerationDefinition rule over the overlapping AttributeDefinition rule and preserves the ValueType application. This keeps all 15 affected literals native and reversible.

**AssociationClasses.** A UML AssociationClass is both a relationship and a Class: the relationship itself may have properties and inheritance. `RiskRealization` (`STPALib.xmi:197`) is the only one in the eight official library files. Its main v2 form is a `connection def`, and the following marker keeps the facts needed to rebuild the Class side as well:

```
metadata def Raaml_AssociationClass :> Raaml_BaseAnnotation {
    attribute v1Library: String;
    attribute v1ClassName: String;
    attribute v1MemberEndRefs: Raaml_ElementRef[2..*];
    attribute v1OwnedEnds: Raaml_AssocEnd[0..*];
    attribute v1NavigableOwnedEndRefs: Raaml_ElementRef[0..*];
    attribute v1Generalizations: Raaml_ElementRef[0..*];  // overrides base (both edges)
}

datatype Raaml_AssocEnd {
    attribute name: String[0..1];             // e.g. "harmPotential", "harm"; absent on some unnamed ends
    attribute typeRef: Raaml_ElementRef;
    attribute aggregation: String;            // "none" | "shared" | "composite"
    attribute multiplicityLower: String[0..1]; // absent when the source omits an explicit lowerValue
    attribute multiplicityLowerKind: String[0..1];
    attribute multiplicityUpper: String[0..1]; // absent when the source omits an explicit upperValue
    attribute multiplicityUpperKind: String[0..1];
    attribute redefinedProperty: Raaml_ElementRef[0..*];
    attribute ownedComments: String[0..*];
}
```

The source contains 40 ordinary associations. Together they list 80 ordered member-end references, but only 40 ends are owned by the associations themselves; other member ends are Properties owned by Classes. Only 12 owned ends explicitly write a lower bound, and only 10 explicitly write an upper bound. The record must therefore distinguish “not written” from “written with the default value.”

`RiskRealization` inherits from both `GeneralRAAMLLib::AbstractRisk`, a Class, and `CoreRAAMLLib::Causality`, an Association. It owns the ends `harmPotential` and `harm`; each end redefines two earlier properties. The record keeps the different kinds of parent rather than flattening both to an untyped link.

If an AssociationClass has attributes of its own, `v1OwnedProperties` stores them just as it does for a Class. `RiskRealization` has no such attributes, but the schema must still allow them.

Without the `Raaml_AssociationClass` marker, the reverse mapper could not know whether a v2 connection came from a UML Association or a UML AssociationClass. The marker is therefore required.

**Ordinary library associations.** Seven of the eight libraries contain ordinary UML Associations, 40 in total. Their ends have types; some inherit from other associations; some ends redefine earlier properties. Unlike an AssociationClass, an ordinary Association cannot itself carry Class features. Each becomes a v2 `connection def` with this marker:

```
metadata def Raaml_LibraryAssociation :> Raaml_BaseAnnotation {
    attribute v1Library: String;
    attribute v1AssociationName: String;
    attribute v1MemberEndRefs: Raaml_ElementRef[2..*];
    attribute v1OwnedEnds: Raaml_AssocEnd[0..*];
    attribute v1NavigableOwnedEndRefs: Raaml_ElementRef[0..*];
    attribute v1Generalizations: Raaml_ElementRef[0..*];
    // v1OwnedComments inherited from base
}
```

The marker tells the reverse mapper to write a UML Association, not an AssociationClass. It writes `ownedEnd` only for ends that the source Association actually owned. A member end owned by a Class remains a Property on that Class. The ordered `memberEnd` and `navigableOwnedEnd` references are then written exactly as recorded.

Worked example — `STPALib::ProcessModelFlawFactor` (`STPALib.xmi:228-256`): one generalization to `CoreRAAMLLib::Causality`, two association-owned ends each with one `redefinedProperty` href, and explicit lower and upper multiplicity literals. `STPALib` contains seven plain associations in total, but their ownership and multiplicity shapes must be extracted individually rather than inferred from this example. `ISO26262Lib` contains 12 plain associations, including multi-ended and multiply generalized cases. All use the same separation of ordered member-end references from owned-end declarations.

## 7. Stereotype inheritance

Every profile contains stereotype inheritance. A source file points to a parent in the same profile with an ID and to a parent in another profile with a URL plus fragment. The record keeps both the parent and the form of the source reference.

**Encoding.** Each `Raaml_*` metadata definition specializes its parent metadata definitions in v2. `v1Generalizations` also records every source inheritance link so it can be rebuilt:

- `kind = "stereotype"` for cross-profile and intra-profile edges to other stereotypes.
- `profileOrLibrary` and `name` for name resolution.
- `href` populated iff the original XMI used the href form; otherwise empty and reverse emits the idref form.

If a stereotype has several parents, `v1Generalizations` contains one entry for each. This covers examples such as `DependabilityRequirement` and `ElementGroupBasedItem`.

**A child may declare a base again or only inherit it.** `UnsafeControlAction` declares its own `base_Class`; the concrete FTA gate and event subtypes declare no bases and inherit them from their parents. `v1Bases` records only what the child itself declares. Section 3.2 explains why the reverse mapper must not add inherited bases as new declarations.

## 8. `DirectedRelationshipPropertyPath` and relationship stereotypes

`ControllingMeasure`, `Violates`, `RelevantTo`, `Detection`, `Prevention`, `Recommendation`, and `Mitigation` extend UML `Dependency`. `RelevantTo` and `ControllingMeasure` also inherit four ordered path properties from the SysML v1 `DirectedRelationshipPropertyPath` stereotype.

**Encoding.** Each becomes a `metadata def`, extending
`Raaml_BaseAnnotation`, with `Dependency` retained in `v1Bases`. When
inheriting from `DirectedRelationshipPropertyPath`, the stereotype carries:

```
metadata def Raaml_PathRelationship :> Raaml_BaseAnnotation {
    attribute v1IsPropertyPath: Boolean = true;
    attribute v1SourceContext: Raaml_ElementRef[0..1];
    attribute v1TargetContext: Raaml_ElementRef[0..1];
    attribute v1SourcePropertyPath: Raaml_ElementRef[0..*];  // ordered
    attribute v1TargetPropertyPath: Raaml_ElementRef[0..*];  // ordered
}
```

All four paths are kept. If an in-scope stereotype application supplies values for them, `v1PropertyValues` records those values under the original property names.

SysML v2 has relationships such as `Satisfy`, `Allocation`, and `DeriveReqt` whose meanings may look close to some RAAML relationships. They are not substituted. `Detection`, `Prevention`, `Mitigation`, and the other RAAML relationships must keep their own names and identities so the reverse mapper knows which stereotype to rebuild.

**ISO26262 `Abstraction`-based stereotypes.** `IndependenceRequirement`, `ASILDecompose`, `UserInfoRequirement`, and `RecoveryRequirement` extend `Abstraction` (a UML `Dependency` subtype). Each remains a `MetadataDefinition` with `Abstraction` in `v1Bases`. `IndependenceRequirement` and `ASILDecompose` inherit from `SysML::DeriveReqt`; `UserInfoRequirement` and `RecoveryRequirement` inherit from `SysML::Satisfy`. These inheritance edges are recorded in `v1Generalizations` with `kind = "sysmlMetaclass"`.

**`Verified` and `Confirmed` are *not* `Abstraction`-based.** Both own `base_Class` only and have no `<generalization>` edges (ISO26262.xmi:285-298, :299-312). They carry a `result: String` property each.

## 9. Concept-by-concept table

Covers every stereotype declared across the nine profile XMIs. The "Base"
column lists all `base_*` metaclasses. The domain-view column is informative:
it records a possible derived interpretation from the earlier draft. It is
not part of the version 0.1 encoding, is not emitted by the reference mapper,
and is never used for reversal. The normative carrier for every stereotype
listed below is `MetadataDefinition`.

### 9.1 CoreRAAML

| Element | Bases | Informative domain view | Notes |
| --- | --- | --- | --- |
| `ControllingMeasure` (CoreRAAML.xmi:14, abstract, `:> DirectedRelationshipPropertyPath`) | `Dependency` | `Dependency` | Section 8; `affects: uml:Property[0..*]` in `v1OwnedProperties` |
| `Violates` (CoreRAAML.xmi:41) | `Dependency` | `Dependency` | |
| `RelevantTo` (CoreRAAML.xmi:73, `:> DirectedRelationshipPropertyPath`) | `Dependency` | `Dependency` | Section 8 |
| `Situation` (CoreRAAML.xmi:100) | `Class` | `Definition` → `OccurrenceDefinition` (Section 3.4 hard-coded anchor) | `base_Class` + generalization to `SysML::Block`. Every downstream stereotype that generalizes `Situation` inherits the `OccurrenceDefinition` elevation transitively |
| `IDCarrier` (CoreRAAML.xmi:120) | `Element` | (any) + `v1AnnotatedMetaclass` | `Id: String` in `v1OwnedProperties` |

### 9.2 GeneralRAAML

| Element | Bases | Informative domain view | Notes |
| --- | --- | --- | --- |
| `FailureMode` (GeneralRAAML.xmi:18) | `Class` | `Definition` → `OccurrenceDefinition` (Section 3.4) | Generalization → `CoreRAAML::Situation` |
| `Error` (GeneralRAAML.xmi:46) | `Class` | `Definition` → `OccurrenceDefinition` (Section 3.4) | Generalization → `CoreRAAML::Situation` |
| `Fault` (GeneralRAAML.xmi:73) | `Class` | `Definition` → `OccurrenceDefinition` (Section 3.4) | Generalization → `CoreRAAML::Situation` |
| `FailureState` (GeneralRAAML.xmi:65) | `State` | `StateDefinition` | |
| `Hazard` (GeneralRAAML.xmi:188, `:> Situation`) | `Class` | `Definition` → `OccurrenceDefinition` (Section 3.4) | Generalization → `CoreRAAML::Situation` |
| `PresentIn` (GeneralRAAML.xmi:207, `:> RelevantTo`) | `Dependency` | `Dependency` | Generalization → `CoreRAAML::RelevantTo` |
| `Detection` (GeneralRAAML.xmi:93) | `Dependency` | `Dependency` | Section 8 |
| `Recommendation` (GeneralRAAML.xmi:112) | `Dependency` | `Dependency` | Section 8 |
| `Prevention` (GeneralRAAML.xmi:131) | `Dependency` | `Dependency` | Section 8 |
| `Mitigation` (GeneralRAAML.xmi:150) | `Dependency` | `Dependency` | Section 8 |
| `Undeveloped` (GeneralRAAML.xmi:169) | `Element` | (any) + `v1AnnotatedMetaclass` | |
| `Item` (GeneralRAAML.xmi:226, abstract) | `Element` | (any) + `v1AnnotatedMetaclass` | `member`, `boundaryMember` derived properties with `subsettedProperty` edges |
| `SingleElementItem` (GeneralRAAML.xmi:259, `:> Item`) | `Element` | (any) | `member` redefines `Item::member` |
| `ElementGroupBasedItem` (GeneralRAAML.xmi:283, `:> Item`, `:> SysML::ElementGroup`) | `Comment` | v2 `Comment` | Multi-inheritance; `member` redefines `Item::member` and `SysML::ElementGroup::member` |

### 9.3 STPA

Verified by `grep 'uml:Stereotype.*name='` against `STPA.xmi`. `OperationalSituation` and `MalfunctioningBehavior` are ISO26262 stereotypes (see Section 9.8), not STPA — any prior revision that listed them here was incorrect.

| Element | Bases | Informative domain view | Notes |
| --- | --- | --- | --- |
| `ControlAction` (STPA.xmi:15, decl + 3 Extensions at 29-52) | `Signal`, `Class`, `DataType` | `ItemDefinition` | Triple base preserved in `v1Bases`; emitted as three separate `uml:Extension` elements on reverse |
| `Feedback` (STPA.xmi:53, decl + 3 Extensions) | `Signal`, `Class`, `DataType` | `ItemDefinition` | Same shape as `ControlAction` |
| `UndesiredControlAction` (STPA.xmi:91) | `Class` | `Definition` → `OccurrenceDefinition` (Section 3.4) | Generalizes `CoreRAAML::Situation` (cross-profile href) |
| `LossScenario` (STPA.xmi:110) | `Class` | `Definition` → `OccurrenceDefinition` (Section 3.4) | Generalizes `CoreRAAML::Situation`; **`base_Class` type href uses `20131001` UML URI** (other stereotypes use `20161101`) — preserved via `Raaml_BaseRef.typeHref` |
| `ControlledProcess` (STPA.xmi:129) | `Property`, `Class` | `PartUsage` + companion | Section 4 |
| `Actuator` (STPA.xmi:140) | `Property`, `Class` | `PartUsage` + companion | Section 4 |
| `Sensor` (STPA.xmi:151) | `Property`, `Class` | `PartUsage` + companion | Section 4 |
| `Controller` (STPA.xmi:162) | `Property`, `Class` | `PartUsage` + companion | Section 4 |
| `ControlStructure` (STPA.xmi:173) | `Class` | `Definition` → `PartDefinition` (Section 3.4) | `base_Class` + generalization to `SysML::Block` (cross-metamodel href); not a direct `base_SysML::Block` |
| `UnsafeControlAction` (STPA.xmi:256) | `Class` | `Definition` → `OccurrenceDefinition` (Section 3.4) | Generalization → `UndesiredControlAction` (intra-profile idref) |

### 9.4 FTA

Verified stereotype list: 19 stereotypes. The **only** stereotypes with locally-owned `base_*` attributes are `Tree`, `Gate`, `Event`, `TransferIn`, `TransferOut`. Every event subtype (DormantEvent, BasicEvent, ConditionalEvent, ZeroEvent, HouseEvent, IntermediateEvent, TopEvent) inherits its bases from `Event` via `uml:Generalization`. Every gate subtype (AND, OR, SEQ, XOR, INHIBIT, MAJORITY_VOTE, NOT) inherits its bases from `Gate`. Per Section 3.2, `v1Bases` is empty on each inheriting subtype; the effective set is reconstructed from the generalization chain.

| Element | Owned bases (`v1Bases`) | Inherits bases from | Informative domain view | Notes |
| --- | --- | --- | --- | --- |
| `Tree` (FTA.xmi:19) | `Class` | — | `Definition` → `OccurrenceDefinition` (Section 3.4) | OCL `TreeIsFTATree`; generalization → `CoreRAAML::Situation` |
| `Gate` (FTA.xmi:46, abstract) | `Class` (FTA.xmi:50, multiplicity `[0..1]`), `Property` (FTA.xmi:54, multiplicity `[0..1]`) | — | `PartUsage` + companion (Section 4) | |
| `Event` (FTA.xmi:75, abstract) | `Class` (FTA.xmi:80, multiplicity `[0..1]`), `Property` (FTA.xmi:84, multiplicity `[0..1]`) | — | `PartUsage` + companion | Carries icon |
| `DormantEvent` (FTA.xmi:105) | (empty) | `Event` | `PartUsage` + companion | icon |
| `BasicEvent` (FTA.xmi:125) | (empty) | `Event` | `PartUsage` + companion | icon |
| `ConditionalEvent` (FTA.xmi:155) | (empty) | `Event` | `PartUsage` + companion | icon |
| `ZeroEvent` (FTA.xmi:175) | (empty) | `Event` | `PartUsage` + companion | icon |
| `HouseEvent` (FTA.xmi:195) | (empty) | `Event` | `PartUsage` + companion | OCL `HouseEventIsHouseEvent`; icon |
| `AND` (FTA.xmi:215) | (empty) | `Gate` | `PartUsage` + companion | OCL `ANDIsAND`; icon |
| `OR` (FTA.xmi:235) | (empty) | `Gate` | `PartUsage` + companion | OCL; icon |
| `SEQ` (FTA.xmi:255) | (empty) | `Gate` | `PartUsage` + companion | OCL; icon |
| `XOR` (FTA.xmi:275) | (empty) | `Gate` | `PartUsage` + companion | OCL; icon |
| `INHIBIT` (FTA.xmi:295) | (empty) | `Gate` | `PartUsage` + companion | OCL; icon |
| `MAJORITY_VOTE` (FTA.xmi:315) | (empty) | `Gate` | `PartUsage` + companion | OCL; icon |
| `NOT` (FTA.xmi:335) | (empty) | `Gate` | `PartUsage` + companion | OCL; icon |
| `IntermediateEvent` (FTA.xmi:355) | (empty) | `Event` | `PartUsage` + companion | |
| `TopEvent` (FTA.xmi:374) | (empty) | `Event` | `PartUsage` + companion | |
| `TransferIn` (FTA.xmi:393) | `Property` (FTA.xmi:405) | — | `PartUsage` | OCL `TypeIsTransferOut`; icon |
| `TransferOut` (FTA.xmi:418) | `Class` (FTA.xmi:423) | — (generalizes `Tree`) | `Definition` → `OccurrenceDefinition` (Section 3.4) | icon |

All FTA event / gate icons are preserved in `v1Icons` as hex-encoded SVG with `format="SVG"` and original `location` attribute.

### 9.5 FMEA

`FMEA.xmi` declares exactly one stereotype.

| Element | Bases | Informative domain view | Notes |
| --- | --- | --- | --- |
| `FMEAItem` (FMEA.xmi:23) | `Class` | `Definition` → `PartDefinition` (Section 3.4) | Generalization → `SysML::Block` (FMEA.xmi:35-37, cross-metamodel href); OCL `FMEAItemIsAbstractFMEAItem` binds library class `AbstractFMEAItem` by name |

### 9.6 RBD

Only `ReliabilitySituation` and `Restorable` locally own their `base_Class`;
the other six stereotypes inherit via generalization, so their local
`v1Bases` lists are empty. `ReliabilitySituation` generalizes
`CoreRAAML::Situation`; its descendants retain that chain. `Restorable` has no
generalization edge. All eight stereotype declarations remain
`MetadataDefinition`s; the occurrence-oriented entries below are informative
domain views only.

| Element | Owned bases (`v1Bases`) | Inherits bases from | Informative domain view | Notes |
| --- | --- | --- | --- | --- |
| `ReliabilitySituation` (RBD.xmi:15, abstract) | `Class` (RBD.xmi:22) | — | `Definition` → `OccurrenceDefinition` (Section 3.4) | Generalization → `CoreRAAML::Situation` (RBD.xmi:19-21) |
| `Restorable` (RBD.xmi:34) | `Class` (RBD.xmi:45) | — | `Definition` (no elevation — no generalization edge) | OCL binds library class `Restorable` by name |
| `ComponentReliability` (RBD.xmi:57) | (empty) | `ReliabilitySituation` (RBD.xmi:68) | `Definition` → `OccurrenceDefinition` | OCL binds `ComponentReliabilitySituation` by name |
| `SystemReliability` (RBD.xmi:70, abstract) | (empty) | `ReliabilitySituation` (RBD.xmi:74) | `Definition` → `OccurrenceDefinition` | |
| `InSeries` (RBD.xmi:76) | (empty) | `SystemReliability` (RBD.xmi:87) | `Definition` → `OccurrenceDefinition` | OCL binds `InSeries` by name |
| `InParallel` (RBD.xmi:89) | (empty) | `SystemReliability` (RBD.xmi:100) | `Definition` → `OccurrenceDefinition` | OCL binds `InParallel` by name |
| `HomogeneousKofN` (RBD.xmi:102) | (empty) | `SystemReliability` (RBD.xmi:113) | `Definition` → `OccurrenceDefinition` | OCL binds `HomogeneousKofN` by name |
| `HeterogeneousKofN` (RBD.xmi:115) | (empty) | `SystemReliability` (RBD.xmi:126) | `Definition` → `OccurrenceDefinition` | OCL binds `HeterogeneousKofN` by name |

### 9.7 GSN

The three abstract parent stereotypes (`GSNNode`, `GSNArgumentNode`, `ContextualInformation`) extend `Element`, not `Class` (GSN.xmi:184,201,233). The concrete subtypes extend `Class`. This matters because `Element`-based annotations require `v1AnnotatedMetaclass` on every instance application per Section 3.3.

| Element | Bases | Informative domain view | Notes |
| --- | --- | --- | --- |
| `GSNNode` (GSN.xmi:175, abstract) | `Element` | (any) + `v1AnnotatedMetaclass` | |
| `GSNArgumentNode` (GSN.xmi:196, abstract, `:> GSNNode`) | `Element` | (any) + `v1AnnotatedMetaclass` | |
| `ContextualInformation` (GSN.xmi:229, abstract, `:> GSNNode`) | `Element` | (any) + `v1AnnotatedMetaclass` | |
| `Goal` (GSN.xmi:18, `:> GSNArgumentNode`) | `Class` | `Definition` | icon |
| `Strategy` (GSN.xmi:28, `:> GSNArgumentNode`) | `Class` | `Definition` | icon |
| `Solution` (GSN.xmi:38, `:> GSNNode`) | `Class` | `Definition` | icon |
| `Justification` (GSN.xmi:48, `:> ContextualInformation`) | `Class` | `Definition` | icon |
| `Assumption` (GSN.xmi:58, `:> ContextualInformation`) | `Class` | `Definition` | icon |
| `Context` (GSN.xmi:68, `:> ContextualInformation`) | `Class` | `Definition` | icon |
| `SupportedBy` (GSN.xmi:102) | `Dependency` | `Dependency` | OCL binds `GSNArgumentNode`, `Strategy`, `Goal` by name via `.allInstances()` |
| `InContextOf` (GSN.xmi:148) | `Dependency` | `Dependency` | OCL binds `GSNArgumentNode`, `ContextualInformation`, `GSNNode` by name |
| `Undeveloped`-combination annotation | per GSN profile | | Preserved in `v1OwnedComments` on the profile package (normative notation guidance in GSN.xmi:9) |

### 9.8 ISO26262

| Element | Bases | Informative domain view | Notes |
| --- | --- | --- | --- |
| `OperationalSituation` (ISO26262.xmi:15) | `Class` | `Definition` → `OccurrenceDefinition` (Section 3.4) | Generalization → `CoreRAAML::Situation` (ISO26262.xmi:19-21) |
| `MalfunctioningBehavior` (ISO26262.xmi:34) | `Class` | `Definition` → `OccurrenceDefinition` (Section 3.4) | Generalization → `GeneralRAAML::FailureMode` (ISO26262.xmi:38-40); transitive via `FailureMode → Situation` |
| `IndependenceRequirement` (ISO26262.xmi:54, `:> SysML::DeriveReqt`) | `Abstraction` | `Dependency` | Section 8 |
| `ASILDecompose` (ISO26262.xmi:73, `:> SysML::DeriveReqt`) | `Abstraction` | `Dependency` | Section 8; generalization at ISO26262.xmi:77-79 |
| `SafeState` (ISO26262.xmi:92, base decl at :96) | `Dependency` | `Dependency` | Verified `base_Dependency`, not `base_Class` |
| `UserInfoRequirement` (ISO26262.xmi:108) | `Abstraction` | `Dependency` | Generalizes `SysML::Satisfy` |
| `RecoveryRequirement` (ISO26262.xmi:119) | `Abstraction` | `Dependency` | Generalizes `SysML::Satisfy` |
| `OperatingMode` (ISO26262.xmi:130, base decl at :134) | `Dependency` | `Dependency` | Verified `base_Dependency`, not `base_Class` |
| `FunctionalSafetyRequirement` (ISO26262.xmi:162) | `Class` | `Definition` | Generalization → `AbstractRequirement` |
| `SoftwareSafetyRequirement` (ISO26262.xmi:182) | `Class` | `Definition` | |
| `HardwareSafetyRequirement` (ISO26262.xmi:202) | `Class` | `Definition` | |
| `TechnicalSafetyRequirement` (ISO26262.xmi:222) | `Class` | `Definition` | |
| `SafetyGoal` (ISO26262.xmi:242) | `Class` | `Definition` | |
| `DependabilityRequirement` (ISO26262.xmi:262, abstract, multi-inheritance) | `Class` | `Definition` → `PartDefinition` (Section 3.4) | Generalizations → `SysML::AbstractRequirement` (no elevation) AND `SysML::Block` (ISO26262.xmi:269-271 — elevation wins by Section 3.4 rule 2). **ExtensionEnd name drift**: the ExtensionEnd is named `extension_SafetyRequirement` at ISO26262.xmi:280 (not `extension_DependabilityRequirement`) — an authoring inconsistency in the RAAML 1.1 source. `v1ExtensionEndNames` preserves the name verbatim |
| `Verified` (ISO26262.xmi:285) | `Class` | `Definition` | No generalization; carries `result: String`. Not `:> SysML::Satisfy` despite semantic adjacency |
| `Confirmed` (ISO26262.xmi:299) | `Class` | `Definition` | No generalization; carries `result: String` |
| `HazardAndRiskAssessment` (ISO26262.xmi:329) | `Package` | `Package` | |
| `LessonLearned` (ISO26262.xmi:345) | `Comment` | v2 `Comment` | |
| `ASILAssignment` (ISO26262.xmi:361) | `Element` | (any) + `v1AnnotatedMetaclass` | `ASIL: ASIL[1]` (`isDerived=true`), `ASILOverride: ASIL[0..1]`; enumeration `ASIL` in `ISO26262` with 20 literals |
| `ASILOverrideRationale` (ISO26262.xmi:388) | `Comment` | v2 `Comment` | |

### 9.9 GeneralRAAMLSecurity

| Element | Bases | Informative domain view | Notes |
| --- | --- | --- | --- |
| `Threat` (GeneralRAAMLSecurity.xmi:15, base decl at :22, `:> Situation`) | `Class` | `Definition` → `OccurrenceDefinition` (Section 3.4) | Generalization → `CoreRAAML::Situation` (GeneralRAAMLSecurity.xmi:19-21) |
| `Impacts` (GeneralRAAMLSecurity.xmi:34, `:> RelevantTo`) | `Dependency` | `Dependency` | Section 8 |
| `Asset` (GeneralRAAMLSecurity.xmi:66) | `Class` | `Definition` | No generalization; `base_Class` at :70 |
| `Valuates` (GeneralRAAMLSecurity.xmi:74, `:> DirectedRelationshipPropertyPath`) | `Dependency` | `Dependency` | Section 8 |
| `SecurityActor` (GeneralRAAMLSecurity.xmi:101) | `Classifier` | `Definition` + `v1AnnotatedMetaclass = "Classifier"` | |
| `PresentedBy` (GeneralRAAMLSecurity.xmi:117, `:> RelevantTo`) | `Dependency` | `Dependency` | |

### 9.10 Libraries

| Library | Notable elements | v2 form |
| --- | --- | --- |
| `CoreRAAMLLib` | `AnySituation`, `Causality` | `OccurrenceDefinition` + `Raaml_LibraryAssociation` for the association |
| `GeneralRAAMLLib` | `FailureMode`, `Hazard`, `HarmPotential`, `Loss`; named associations including `ErrorPropagation`, `Activation`, `ErrorRealization` | Official Class specialization + `Raaml_LibraryAssociation` for associations |
| `STPALib` | `ProcessModelFlaw`, `UndesiredControlAction`, `LossScenario`, `Loss`, `RiskRealization` (AssociationClass) | Official Class specialization + `Raaml_AssociationClass` for `RiskRealization` |
| `FTALib` | gate/event classes, `FTATree`, `HouseEventProbability` enumeration | Official Class specialization + `enum def` |
| `FMEALib`, `RBDLib`, `ISO26262Lib` (`Exposure`, `Severity`, `Controllability` enums), `GeneralRAAMLSecurityLib` | per library | Official Class specialization + `enum def` for the enumerations |

## 10. How to rebuild the v1 files

Input consists of the v2 model and the JSON manifests produced from the 17 official RAAML files. Every generated definition carries a marker that says whether it came from a stereotype, library Class, AssociationClass, or ordinary Association.

### 10.1 Profile structure reconstruction

1. Load the manifest for each source file and collect the RAAML annotations from the v2 model.
2. Rebuild each UML Profile from the recorded name, URI, comments, annotated elements, imports, and namespace values.
3. Rebuild every import target from the manifest. An implementation may check these targets against a known RAAML 1.1 table, but it must not use that table instead of the stored facts. Otherwise a changed input could be silently replaced by an expected value.

### 10.2 Stereotype declarations

For each distinct non-empty `(v1Profile, v1StereotypeName)` pair appearing on stereotype metadata in `M`:

1. Require each stereotype name to be unique within its profile. The same name may appear in two different profiles because the profile name distinguishes them.
2. Emit a `uml:Stereotype` with that name, `isAbstract = v1IsAbstract`, and owned comments from `v1OwnedComments`. The profile URI belongs to the enclosing `uml:Profile` and is emitted from the preservation manifest.
3. For each `Raaml_BaseRef` in `v1Bases`, emit a `uml:Property` `ownedAttribute` named `baseAttributeName` (or `base_<metaclass>`), a `uml:Extension`, and a `uml:ExtensionEnd` with `name` taken from `v1ExtensionEndNames` (or the default).
4. For each `Raaml_PropertyDef` in `v1OwnedProperties`, emit a `uml:Property` with name, type (resolved via Section 10.5), multiplicity, default, `isDerived`, `subsettedProperty`, `redefinedProperty`.
5. For each `Raaml_ElementRef` in `v1Generalizations`, emit a `uml:Generalization`: `<general href="..."/>` when `href` is populated; `general="..."` (intra-profile idref) when `profileOrLibrary == v1Profile` and `href` is empty; for intra-profile idrefs, the target ID is synthesized deterministically by the algorithm specified in Section 10.5.1 so it is stable across round-trips and identical across independent reverse-mapper implementations.
6. For each `Raaml_Icon`, emit `<icon xmi:type="uml:Image" content="..."/>` with the hex-encoded payload.
7. For each `v1OCLConstraints` reference, resolve to the constraint store and emit `<ownedRule xmi:type="uml:Constraint">` with the text, `constrainedElement` idref/href resolved via the context reference.

### 10.3 Library declarations

For each `Raaml_LibraryClass`-annotated v2 `def`:

1. Emit a `uml:Class` in the `v1Library` package with `name = v1ClassName`, `isAbstract = v1IsAbstract`, owned comments.
2. Emit generalizations from `v1Generalizations` (same intra/cross rule as Section 10.2.5).
3. Emit owned properties from `v1OwnedProperties`. For each `Raaml_PropertyDef`, emit an `<ownedAttribute>` with `xmi:type="uml:Property"` when `propertyKind = "Property"` or `xmi:type="uml:Port"` when `propertyKind = "Port"`. Preserve: `name`, type (resolved via Section 10.5), `multiplicity` (as `<lowerValue>` + `<upperValue>` literals), `defaultValue` (wrapped in the `defaultValueKind` literal form), `isDerived`, `aggregation`, `subsettedProperty` refs, `redefinedProperty` refs, and owned comments. This is the same field set as Section 10.2.4 plus the Port/Property discriminator.
4. Emit owned connectors from `v1OwnedConnectors`. For each `Raaml_ConnectorDef`, emit an `<ownedConnector xmi:type="uml:Connector">` with the recorded `visibility` and, for each `Raaml_ConnectorEnd` in `ends`, an `<end xmi:type="uml:ConnectorEnd">` child whose `role` idref is resolved via `roleRef` and whose optional `partWithPort` idref is resolved via `partWithPortRef`. IDs for owned properties, Ports, connectors, and connector ends use `syntheticOwnedId` from Section 10.5.1.

For each `Raaml_AssociationClass`-annotated `connection def`:

1. Emit a `uml:AssociationClass` with `v1ClassName`, `isAbstract`, package membership, owned comments, and generalizations from `v1Generalizations`.
2. Emit each association-owned `uml:Property` from `v1OwnedEnds`, including only the multiplicity literal elements that were explicitly present and using their recorded literal kinds.
3. Emit the ordered `memberEnd` idrefs from `v1MemberEndRefs` and `navigableOwnedEnd` idrefs from `v1NavigableOwnedEndRefs`. A member end owned by a classifier references the property already emitted on that classifier.
4. Emit any inherited class-side features from `v1OwnedProperties` as `ownedAttribute`s on the AssociationClass.

For each `Raaml_LibraryAssociation`-annotated `connection def`:

1. Emit a `uml:Association` (not `AssociationClass`) with `v1AssociationName`, `isAbstract = v1IsAbstract`, generalizations from `v1Generalizations`.
2. Emit `ownedEnd` children from `v1OwnedEnds`, preserving type, aggregation, redefinitions, comments, and the presence, value, and literal kind of lower and upper multiplicities.
3. Emit the ordered `memberEnd` idrefs from `v1MemberEndRefs` and `navigableOwnedEnd` idrefs from `v1NavigableOwnedEndRefs`.

**Put library applications back in the library file.** If a v2 definition represents a library Class and also carries a RAAML stereotype application, rebuild both in the library XMI named by `v1Library`. The application points to the newly generated ID of that Class.

### 10.4 Applications in user models (outside version 0.1)

Version 0.1 handles only the stereotype applications already present in the official library files. A future version may cover applications in user models, including repeated applications, unnamed targets, structured values, and models edited after conversion. Until that work is specified and tested, it is outside the claim.

### 10.5 Rebuilding references

For every stored `Raaml_ElementRef`:

- If `href` is populated, emit the href directly.
- Else if `profileOrLibrary` identifies the referring artifact, resolve the declaration or owned element by `(kind, ownerName, name)` and emit its `syntheticId` or `syntheticOwnedId` from Section 10.5.1.
- Else if `profileOrLibrary` names a different RAAML profile or library, synthesize the href using `syntheticId(profileOrLibrary, name)` for a top-level declaration or `syntheticOwnedId(...)` when `ownerName` is present. The preservation manifest records the artifact URI prefix rather than requiring the resolver to guess it from a filename.
- `kind == "sysmlMetaclass"` resolves to the SysML 1.6 XMI URI: `http://www.omg.org/spec/SysML/20181001/SysML.xmi#SysML.<name>`.
- `kind == "umlMetaclass"` resolves to the UML 2.5.1 XMI URI: `http://www.omg.org/spec/UML/20161101/UML.xmi#<name>`.

**Keep URI differences that occur in the source.** `LossScenario::base_Class` points to the 2013 UML Class URI, while the other stereotypes use the 2016 URI. `typeHref` stores the URI exactly as read so reversal does not silently “correct” it. If a source declaration omits the URI, the mapper uses the 2016 URI as its stated default.

### 10.5.1 Synthetic ID algorithm

The original XMI IDs were assigned by a modeling tool and are not preserved. The reverse mapper creates repeatable replacements. The same input text must always produce the same ID:

```
syntheticId(profileOrLibrary, name) =
    "_raaml_" ||
    lowercaseHex( firstBytes(20, SHA-256( UTF-8(profileOrLibrary || "::" || name) )) )
```

An owned element also includes its owner in the input because two Classes can both own a Property with the same name:

```
syntheticOwnedId(artifact, ownerQualifiedName, elementKind, localName, ordinal) =
    "_raaml_" ||
    lowercaseHex( firstBytes(20, SHA-256( UTF-8(
        artifact || "::" || ownerQualifiedName || "::" ||
        elementKind || "::" || localName || "::" || decimal(ordinal)
    ) )) )
```

`elementKind` states what is being identified. `ordinal` begins at one and distinguishes siblings that have the same kind and name. Every input must come from the stored model facts; the mapper must not depend on where an unrelated XML node happened to appear.

- Hash: SHA-256 (FIPS 180-4).
- Input: UTF-8 bytes of `profileOrLibrary`, then `::`, then `name`. Do not trim or change case. Names containing `::` are not allowed because that text separates the fields.
- Output slice: the first 20 bytes of the digest, rendered as 40 lowercase hexadecimal characters.
- Prefix: the literal ASCII string `_raaml_`.
- Total length: 47 characters. Example: `syntheticId("STPA", "Controller")` is `_raaml_91a0d44384d4417f8bb0389b94d928b88f545a34`.

**If two inputs produce the same ID, stop.** The hash is truncated to 160 bits, which gives roughly 80 bits of general collision resistance. A collision is extremely unlikely for this corpus, but the mapper must fail rather than invent an unrecorded tie-breaker. The test report must include a collision check across all 17 files.

The new ID is not meant to match the original MagicDraw ID. Tools loading the rebuilt file will see `_raaml_...` IDs. That is acceptable because original IDs are outside the fact list.

### 10.5.2 IDs for applications in the official libraries

A stereotype application in an official library points to the generated ID of its target Class. Its own ID is computed from the profile, stereotype, and target ID. Repeated applications and targets in user models remain outside version 0.1.

### 10.6 Supporting elements must also be present

Some UML elements are needed only because they own, type, or link one of the listed RAAML facts. The mapper must still carry them. The test fails if an owner, type, parent, connector end, association end, import, constrained element, or application target cannot be found. Unrelated elements added later by a user are outside version 0.1.

### 10.7 The complete pass-or-fail comparison

For each official file, the test extracts the standard fact list, converts the file to v2 plus its manifest, rebuilds v1 XMI, extracts the list again, and compares the two. The comparison must cover every category from Section 1:

- **Profile/package:** artifact identity and kind, profile or package name, URI, owned comments plus annotated targets, metamodel references, package imports, element imports, profile applications, namespace prefixes, and resolved import targets.
- **Stereotype:** name, owning profile, `isAbstract`, locally owned `base_*` entries including multiplicity and source type URI, extension-end names, generalizations, owned properties, owned comments, icons, and owner-qualified OCL constraints.
- **Property/Port:** name, discriminator, owner, type reference, aggregation, multiplicity, default value plus literal kind, `isDerived`, subsetted and redefined properties, and comments.
- **Library class:** name, package membership, `isAbstract`, generalizations, properties and Ports, comments, and owned connectors.
- **Connector:** owner, visibility, ordered ends, role references, optional `partWithPort` references, and comments.
- **Enumeration:** name, package membership, and ordered literal-name sequence.
- **AssociationClass:** name, package membership, `isAbstract`, generalizations, owned properties and comments, ordered member-end references, separately owned-end declarations, navigable-owned-end references, and each owned end's name, type, aggregation, explicit multiplicity literals, redefinitions, and comments.
- **Plain association:** name, package membership, `isAbstract`, generalizations, comments, ordered member-end references, separately owned-end declarations, navigable-owned-end references, and the same complete owned-end tuple.
- **Normative library stereotype application:** stereotype identity, resolved target identity, and property values with primitive kind, enumeration-literal identity, ordering where applicable, and resolved element references.
- **OCL constraint:** owner-qualified `constraintKey`, original name, verbatim body and language representation, resolved constrained elements, comments, and the resolvability of extracted RAAML names.

Unordered UML values are compared as sets after their references have been resolved. Ordered values—such as enumeration literals, connector ends, association member ends, and preserved OCL body lines—are compared as sequences. The implementation must publish before-and-after counts for every category and fail on every listed fact that is missing, added, unresolved, or changed.

The test does not compare raw XML bytes. It ignores the file-format differences that Section 1 explicitly excludes.

## 11. What preservation forbids

The following shortcuts may look cleaner in v2, but each would erase or add a listed source fact:

- **Picking one base for `ControlAction` / `Feedback`.** The `Signal`/`Class`/`DataType` triple extension is preserved in full in `v1Bases`; the common `MetadataDefinition` carrier does not reduce it.
- **Collapsing `Detection` / `Prevention` / `ControllingMeasure` / `Impacts` / `Valuates` into v2 `Satisfy`, `Allocation`, or `DeriveReqt`.** Each RAAML stereotype keeps its own `metadata def`; v2's own relationship kinds are used only as inheritance targets recorded in `v1Generalizations`.
- **Replacing `RiskRealization`'s AssociationClass form with a plain `connection def`.** The `Raaml_AssociationClass` marker is mandatory.
- **Translating a source expression to native `constraint def` as the sole form.** The constraint store is authoritative. Native constraint views are also emitted where possible, but they do not replace the source.
- **Flattening `DirectedRelationshipPropertyPath` to a single path.** All four paths (`sourceContext`, `targetContext`, `sourcePropertyPath`, `targetPropertyPath`) are preserved.
- **Dropping SVG icons.** `v1Icons` is mandatory when the v1 declaration has an `<icon>`.
- **Dropping `ExtensionEnd.name` values.** `v1ExtensionEndNames` preserves each.
- **Dropping stereotype `isAbstract`.** Preserved in `v1IsAbstract`.
- **Inferring `base_Element` targets from context alone.** `v1AnnotatedMetaclass` is mandatory whenever `v1Bases` contains `Element` on an instance-level application.
- **Translating enumeration-typed stereotype properties to strings.** `Raaml_PropertyValue.enumerationRef` + `enumerationLiteralName` preserves the literal identity; the reverse resolves to the matching `uml:EnumerationLiteral` idref.
- **Dropping plain `uml:Association` elements in libraries.** `Raaml_LibraryAssociation` is mandatory for every library `uml:Association`; reverse without the marker produces a `uml:Association` with no RAAML lineage, losing the fact-set entry.
- **Eliding `v1AnnotatedMetaclass` from an application.** The explicit target metaclass is mandatory because the official occurrence helpers do not fully map application instances.
- **Using a non-specified hash or alternative synthesis for intra-profile idrefs.** Section 10.5.1 locks the algorithm; any other hash breaks cross-implementation consistency.
- **Dropping the `format` attribute on `uml:Image`.** `Raaml_Icon.format` is preserved verbatim.
- **Renaming library classes, profile stereotypes, or library enumerations without rewriting OCL text.** Section 5 commits to stability; a rename is a breaking change to every constraint that mentions the renamed entity.
- **Regenerating `base_*` on stereotype subtypes that inherit.** Section 3.2 says `v1Bases` carries locally-owned bases only; reverse must not synthesize inherited base_* attributes.
- **Dropping `base_*` multiplicity.** `Raaml_BaseRef.multiplicityLower`/`multiplicityUpper` are preserved; FTA `Event` carries `[0..1]` on both `base_Class` and `base_Property` (FTA.xmi:82, 86).
- **Dropping association-end multiplicity.** `Raaml_AssocEnd.multiplicityLower`/`multiplicityUpper` are preserved.
- **Dropping `uml:Image@location`.** Preserved in `Raaml_Icon.location`.
- **Normalizing `20131001` UML URIs to `20161101`.** `Raaml_BaseRef.typeHref` preserves the source per entry; reverse emits what was read.
- **Treating `SysML::Block` as a UML metaclass.** It is a SysML 1.6 stereotype; stereotypes "extending SysML::Block" actually own `base_Class` + a generalization (Section 3.4).
- **Changing a stereotype carrier because it generalizes `Situation` or `SysML::Block`.** Those edges are preserved generalizations; the stereotype remains a `MetadataDefinition`.
- **Emitting a companion `uml:Class` for a Property-based stereotype.** A source extension Property describes the stereotype's annotation domain; it is not an application instance or a request to invent another Class.
- **Claiming `Verified`/`Confirmed` are `Abstraction`-based or `:> SysML::Satisfy`.** Neither is true; both own `base_Class` with no generalization (Section 8, Section 9.8).
- **Degrading `uml:Port` to `uml:Property` on reverse.** `Raaml_PropertyDef.propertyKind` discriminates; emitting `xmi:type="uml:Property"` for a Port loses the port semantics that RBDLib's parametric-distribution blocks rely on.
- **Dropping `<ownedConnector>` elements.** Library classes that own connectors (94 across RBDLib, FTALib, and FMEALib) preserve them via `Raaml_LibraryClass.v1OwnedConnectors`; the reverse emits `<ownedConnector xmi:type="uml:Connector">` with ends.
- **Changing `Restorable` because its name matches a library Class.** The stereotype and library Class are distinct source declarations with distinct official carriers. The OCL name reference is a separate concern.

## 12. Non-goals

- Not an OMG specification and not a proposal for a new version of RAAML. It is an independent community proposal intended to inform discussion.
- Not a redesign of RAAML for natural, native use in v2. When a cleaner v2 form would lose a listed v1 fact, version 0.1 keeps the fact.
- Not support for arbitrary user-created RAAML or pure-v2 models. Version 0.1 covers only the 17 official definition files.
- Not a promise tied to one v2 tool. The generated text must name the parsers used for testing.
- Not a replacement for OCL. The original constraint text, ownership, bindings, and resolvable RAAML names are preserved. Behavioral evaluation is outside the version 0.1 conformance claim and may be reported separately as additional evidence.
