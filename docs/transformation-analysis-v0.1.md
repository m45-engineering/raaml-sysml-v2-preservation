# RAAML preservation transformation analysis v0.1

**Status:** Implemented and validated for signed candidate `v0.9.0-rc.3`

This historical analysis records mapping decisions and the candidate's bounded
preservation evidence. It is not proof that every listed native relationship
was emitted by that candidate. The development correction and package-level
checks are described in [native package mapping v0.2](native-package-mapping-v0.2.md).

**Date started:** 2026-07-28

## Purpose

This analysis compares the RAAML preservation proposal with the official SysML
v1-to-v2 transformation before mapper code is written. The comparison has two
separate questions:

1. What v2 element does the official transformation create?
2. What additional source facts must this project retain to reconstruct the
   official RAAML 1.1 files exactly within the v0.1 preservation contract?

The preservation layer should supplement the official transformation where
the official target does not retain enough information for reversal. It should
deviate only when the official target cannot serve the proposal's stated
purpose, and every deviation must have a written reason and test obligation.

## Normative inputs

| Input | OMG identity | Locked SHA-256 |
| --- | --- | --- |
| SysML v1 to SysML v2 Transformation, SysML 2.0 Part 2 | `formal/26-03-03` | `64366027dfef1ab630f741884695a68471939fcf68c3c7d874790d2c86ea518c` |
| Machine-readable transformation model | `ptc/25-04-10` | `093359439fb62cb3a9b1e89fd850ac4ac0b4bbe135b4b54f7861492722cc8459` |

The files are acquired and verified through `standards.lock.json`. They are
not committed or redistributed by this project.

## Corpus surface that requires a decision

The frozen canonical baseline contains:

| Source construct | Count |
| --- | ---: |
| Profiles | 9 |
| Nested packages | 15 |
| Stereotypes | 94 |
| Library classes | 143 |
| Enumerations / literals | 5 / 35 |
| Associations / AssociationClasses | 40 / 1 |
| Properties / Ports | 267 / 65 |
| Connectors | 94 |
| Constraints | 60 |
| Generalizations | 219 |
| Extensions / ExtensionEnds | 84 / 84 |
| Comments / images | 431 / 22 |
| Metamodel references / package imports / profile applications | 9 / 9 / 8 |
| Normative RAAML stereotype applications | 108 |

The source also contains 263 root-level SysML v1 stereotype applications.
The fact contract intentionally excluded them from the RAAML application comparison,
but they select specialized official transformation rules and therefore belong
in this analysis:

| SysML v1 application | Count | Applied to |
| --- | ---: | --- |
| BindingConnector | 90 | Connector |
| Block | 8 | 7 Classes and 1 AssociationClass |
| ConstraintBlock | 36 | Class |
| NestedConnectorEnd | 125 | ConnectorEnd |
| ValueType | 4 | Enumeration |

The deterministic inventory is
`analysis/corpus-transformation-surface-v0.1.json`. This combined list is the
minimum transformation surface. A mapping decision that is not exercised by
one of these categories is outside the v0.1 corpus claim.

## Classification meanings

- **Reuse:** Apply the official rule without changing its semantic target.
- **Specialize:** Apply a more specific official rule because the source meets
  its filter, such as a SysML v1 Block rather than a plain UML Class.
- **Supplement:** Apply the official rule and retain additional source facts
  in the preservation representation.
- **Deviate:** Deliberately choose a different v2 target or behavior.
- **Open:** The evidence is not yet sufficient to classify the row.

## Resolved rule matrix

The machine-rule identifiers below are XMI IDs in the pinned
`SysMLv1Tov2.xmi`.

| RAAML source construct | Official transformation | Clause / machine rule | Initial classification | Preservation consequence |
| --- | --- | --- | --- | --- |
| UML Profile | Package | 7.7.9.3.21; `Mappings-UML4SysML-Packages-Profile_Mapping` | Supplement | Reuse the Package target; retain profile identity, URI, comments, and namespace-prefix facts needed for reversal. |
| UML Package | Package, including URI metadata when present | 7.7.9.3.11; `Mappings-UML4SysML-Packages-Package_Mapping` | Supplement | Reuse package nesting and URI mapping; retain source presence and artifact identity. |
| UML PackageImport | NamespaceImport | 7.7.9.3.12; `Mappings-UML4SysML-Packages-PackageImport_Mapping` | Supplement | Reuse the import; retain the exact source reference form and target identity. |
| UML MetamodelReference | Underlying PackageImport behavior | 7.7.9.3.12 plus the source stereotype | Supplement | Reuse NamespaceImport and retain an explicit MetamodelReference discriminator because no official MetamodelReference-specific rule exists. |
| UML ProfileApplication | Not mapped | 7.7.9.1-7.7.9.2, Tables 12-13 | Supplement | Preserve each profile application and target in the manifest so it can be reconstructed. |
| UML Stereotype | MetadataDefinition | 7.7.9.3.24; `Mappings-UML4SysML-Packages-StereotypeMetadataDefinition_Mapping` | Supplement | The MetadataDefinition is the normative v2 carrier. Retain source bases, extension details, generalizations, properties, icons, constraints, and comments for reversal. |
| UML Extension / ExtensionEnd | Handled in the Stereotype mapping context | 7.7.9.1-7.7.9.2, Tables 12-13; stereotype occurrence rules 7.7.9.3.26-34 | Supplement | Reuse the official annotation-target machinery; retain exact base-property ownership, multiplicity, ExtensionEnd name, and href spelling. |
| UML Generalization | Subclassification | 7.7.4.2.12; `Mappings-UML4SysML-Classification-Generalization_Mapping` | Supplement | Reuse Subclassification; retain local-versus-external reference form and exact target identity. |
| Plain UML Class in a RAAML library | OccurrenceDefinition | 7.7.12.2.10; `Mappings-UML4SysML-StructuredClassifiers-Class_Mapping` | Supplement | Reuse OccurrenceDefinition for the 100 plain Classes and retain exact source Class facts. Seven other Classes select Block_Mapping and 36 select ConstraintBlock_Mapping. |
| SysML v1 Block on a UML Class | PartDefinition | 7.8.4.3.3; `Mappings-SysMLv1-Blocks-Block_Mapping` | Supplement | Seven FTA library Classes select the Block rule. Preserve the applied Block for reversal; do not infer it only from a RAAML stereotype's inheritance graph. |
| SysML v1 ConstraintBlock on a UML Class | ConstraintDefinition | 7.8.5.2.1; `Mappings-SysMLv1-ConstraintBlocks-ConstraintBlock_Mapping` | Supplement | All 36 ConstraintBlocks need the native target plus source Class, application, parameter, and constraint facts. |
| SysML v1 Block on a UML AssociationClass | ConnectionDefinition | 7.8.4.3.1; `Mappings-SysMLv1-Blocks-AssociationBlock_Mapping` | Supplement | STPA `RiskRealization` selects AssociationBlock_Mapping, not Block_Mapping. Preserve both the AssociationClass kind and Block application. |
| UML Enumeration | EnumerationDefinition | 7.7.10.2.11; `Mappings-UML4SysML-SimpleClassifiers-Enumeration_Mapping` | Supplement | Reuse the definition; retain literal order and exact source ownership. |
| UML EnumerationLiteral | EnumerationUsage | 7.7.10.2.12; `Mappings-UML4SysML-SimpleClassifiers-EnumerationLiteral_Mapping` | Supplement | Reuse the usage and preserve ordered membership. |
| UML Enumeration with SysML v1 ValueType | Overlapping AttributeDefinition and EnumerationDefinition rules | 7.7.10.2.11-13 and 7.8.4.3.15 | Deviate | The official model does not state precedence for this overlap. Use EnumerationDefinition to retain native enumeration structure and preserve the ValueType application for reversal. |
| UML AssociationClass | ConnectionDefinition | 7.7.12.2.1; `Mappings-UML4SysML-StructuredClassifiers-AssociationClass_Mapping` | Supplement | Reuse the connection target; retain the Class facet, parent kinds, owned-end facts, and an explicit AssociationClass discriminator. |
| UML Association | ConnectionDefinition | 7.7.12.2.2 and 7.7.12.2.20; `AssociationCommon_Mapping`, `ConnectorType_Mapping` | Supplement | Reuse the connection target; retain association ownership, ordered member ends, navigability, multiplicity presence, and an Association discriminator. |
| UML Property | Metadata/extension handling, AttributeUsage, OccurrenceUsage, Feature, or dual classifier/association views depending on the official filters | 7.7.4.2.35-38; 7.7.9.3.24-34; 7.7.10.2.1-5; 7.7.12.2.23-35; 7.8.5.2.2 | Supplement | The complete 267-Property decision table is reproduced in `analysis/property-transformation-surface-v0.1.json`. Preserve source ownership and exact Property facts around each native target. |
| UML Port | PortUsage | 7.7.12.2.36-37; `Port_Mapping`, `PortUntyped_Mapping` | Supplement | All 51 typed and 14 untyped corpus Ports have an official target. Retain original type reference, multiplicity presence, and Port-versus-Property identity. |
| UML Connector | ConnectionUsage | 7.7.12.2.14; `Mappings-UML4SysML-StructuredClassifiers-Connector_Mapping` | Supplement | Reuse ConnectionUsage; retain ordered ends, role, `partWithPort`, visibility, and source ownership. |
| UML ConnectorEnd | Feature-based connector-end mappings | 7.7.12.2.15-19 | Supplement | Reuse the official end representation; preserve the exact ordered source-end records for reversal. |
| SysML v1 BindingConnector | BindingConnectorAsUsage | 7.8.4.3.2; `Mappings-SysMLv1-Blocks-BindingConnector_Mapping` | Supplement | Ninety of 94 Connectors select this specialized rule. Preserve the application so four ordinary Connectors remain distinguishable. |
| SysML v1 NestedConnectorEnd with propertyPath | Feature with ordered FeatureChaining | 7.7.12.2.18 and 7.8.4.2; `ConnectorEndToSubsettedFeature_Mapping` | Supplement | The standard creates no separate stereotype target, but 125 ConnectorEnds use its ordered property path to select the feature-chain rule. |
| UML Comment | Comment plus Annotation | 7.7.6.2.2-4; `Comment_Mapping`, `CommentAnnotation_Mapping`, `CommentOwnership_Mapping` | Supplement | Reuse Comment/Annotation; retain exact body, owner, and all annotated-element references. |
| UML Constraint | ConstraintDefinition plus AssertConstraintUsage | 7.7.6.2.5-8; `Constraint_Mapping`, `ConstraintUsage_Mapping` | Supplement | Generate the official structural view and keep the original constraint record authoritative for reversal and behavioral claims. |
| UML OpaqueExpression with one language and body | CalculationUsage and TextualRepresentation | 7.7.14.3.18 and 7.7.14.3.31; `OpaqueExpression_Mapping`, `OpaqueExpressionSpecification_Mapping` | Supplement | All 59 labeled expressions fit the official get(0) rules; retain exact source arrays as well. |
| UML OpaqueExpression with a body but no language | CalculationUsage; TextualRepresentation language is invalid | 7.7.14.3.18 and 7.7.14.3.31 | Deviate | Do not invent a language for FMEALib `RPNCalculation`; preserve the body and report that a faithful native textual representation was not emitted. |
| UML Image | Not mapped; mapping not specified | 7.7.9.1-7.7.9.2, Tables 12-13 | Supplement | Store format, location, encoding, and content in the preservation representation. Do not invent a normative native-v2 icon mapping. |
| RAAML stereotype application in a library | No complete official application-instance mapping | 7.2.2 Helper `getAppliedStereotypes`; stereotype occurrence rules 7.7.9.3.26-34 | Supplement | Preserve all 108 application targets and tagged values. The occurrence rules take a Stereotype definition as input and do not map an application instance, target binding, or tagged values. |
| Namespace prefix / MagicDraw `mofext:Tag` | No direct rule identified | No machine rule identified | Supplement | Preserve as artifact metadata; do not present it as native SysML v2 semantics. |
| Exact URL spelling, XMI ownership, explicit-default presence, icon bytes, and source IDs | Not preservation goals of the general semantic transformation | Cross-cutting | Supplement | Keep only the facts included by the v0.1 preservation contract. Original MagicDraw XMI IDs remain excluded. |

## First material findings

### 1. Plain library Classes map to OccurrenceDefinition

The official `Class_Mapping` target is `OccurrenceDefinition`. The current
proposal says a UML library Class becomes a generic `Definition` or textual
`def`, but it does not identify a concrete generic SysML v2 textual production
that has been validated by the pinned parser.

The resolved rule reuses `OccurrenceDefinition` for the 100 plain UML
Classes. Seven Classes with Block applied become PartDefinitions, and 36 with
ConstraintBlock applied become ConstraintDefinitions. Source Class identity,
properties, inheritance, connectors, and applications remain preservation
facts.

### 2. A RAAML stereotype is first a MetadataDefinition

The official transformation does not choose `PartDefinition`,
`OccurrenceDefinition`, or `ItemDefinition` as the primary replacement for a
UML Stereotype. It maps the Stereotype to a `MetadataDefinition` and handles
its extensions in that context.

The proposal's base-metaclass precedence table may still be useful for
constraining what the metadata may annotate or for generating optional
domain-oriented views. It should not replace the official stereotype mapping
without an explicit deviation.

### 3. The preservation manifest remains necessary

The official transformation explicitly leaves Images and ProfileApplications
unmapped. It also does not aim to retain every XMI-level distinction needed for
the proposed reverse reconstruction, such as exact href spelling, explicit
default presence, ExtensionEnd names, or association-end ownership.

The manifest is therefore not a competing transformation. It is the
supplement that makes the narrower round-trip preservation claim testable.

### 4. OCL should have two clearly separated roles

The official transformation maps a UML Constraint and its OpaqueExpression to
native v2 constraint/calculation elements. The proposal currently retains OCL
in a sidecar and treats a native v2 constraint as optional.

The forward mapper emits the official native structural view while also
retaining the exact source constraint. Emitting both follows the official
transformation without claiming that the native constraint behaves
identically to the original OCL or JavaScript.

The source has 60 constraint OpaqueExpressions, not 59. Fifty-nine have
exactly one language and one body: 33 OCL2.0 and 26 JavaScript. The remaining
FMEALib expression has a body but no language. The official textual
representation rule calls `language.get(0)`, so v0.1 preserves that expression
without guessing a language and reports the missing native view.

### 5. Specialized SysML applications are part of the mapping surface

The first matrix used only the canonical RAAML application count
and incorrectly reported zero actual Block applications. The source corpus
does contain transformation-relevant SysML applications. In particular,
`RiskRealization` is an AssociationClass with Block applied, and four
ValueTypes are also UML Enumerations.

The analysis now inventories all 263 root-level SysML applications directly
from the pinned source XMI. This does not change the fact-contract definition
of a RAAML application fact; it prevents the transformation analysis from
applying a generic rule
where an official specialized rule has been selected.

### 6. Property aggregation does not choose the v2 kind

The official filters classify all 267 UML Properties without using
aggregation as the primary kind selector:

| Mutually exclusive category | Count | Official result |
| --- | ---: | --- |
| Stereotype `base_*` Property | 84 | Handled with metadata/extension semantics |
| Association-owned end | 42 | Feature |
| Classifier-owned, non-owned Association end | 41 | OccurrenceUsage plus association-end Feature |
| ConstraintBlock parameter | 17 | AttributeUsage |
| DataType-typed Property | 45 | AttributeUsage |
| Class/Interface-typed Property | 27 | OccurrenceUsage |
| Untyped Property | 11 | Feature |
| Property typed by an applied Block | 0 | PartUsage |

This corrects the proposal's shorter aggregation-based table. In particular,
`composite` does not by itself mean `PartUsage`: none of the in-scope
Properties meets the official PartProperty filter. A source type must actually
have SysML v1 Block applied.

The 41 non-owned Association ends also expose a subtle dual role. The original
Property remains owned by its classifier and is mapped as a typed
OccurrenceUsage, while the Association receives a separate end Feature.
Reversal must not collapse those two views into an Association-owned Property.

## Reproduction commands

After acquiring the locked inputs:

```text
./raaml sources verify
./raaml transformation surface
./raaml transformation properties
./raaml transformation constraints
./raaml transformation audit --require-resolved
pdftotext -layout \
  sources/cache/SysML-2.0-Transformation.pdf \
  tmp/pdfs/SysML-2.0-Transformation.txt
```

Relevant machine rules can be located by XMI ID in
`sources/cache/SysMLv1Tov2.xmi`. The transformation audit automates that check and
fails if a cited rule is absent from the pinned model.

## Resolution status

The matrix contains no `Open` rows. The decisions are incorporated into the
community proposal and normative encoding, the selected textual forms pass
the pinned SysML v2 implementation, and the version 0.1 mapping tables are
frozen. See
[`validation-report-v0.9.0-rc.3.md`](validation-report-v0.9.0-rc.3.md) for
the clean Linux and offline-container evidence.
