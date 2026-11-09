package org.raaml.preservation;

import java.io.IOException;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.eclipse.emf.common.util.Diagnostic;
import org.eclipse.emf.common.util.TreeIterator;
import org.eclipse.emf.common.util.URI;
import org.eclipse.emf.ecore.EClass;
import org.eclipse.emf.ecore.EClassifier;
import org.eclipse.emf.ecore.EAttribute;
import org.eclipse.emf.ecore.EObject;
import org.eclipse.emf.ecore.EPackage;
import org.eclipse.emf.ecore.EReference;
import org.eclipse.emf.ecore.EcoreFactory;
import org.eclipse.emf.ecore.EcorePackage;
import org.eclipse.emf.ecore.resource.Resource;
import org.eclipse.emf.ecore.resource.ResourceSet;
import org.eclipse.emf.ecore.resource.impl.ResourceSetImpl;
import org.eclipse.emf.ecore.util.Diagnostician;
import org.eclipse.emf.ecore.util.EcoreUtil;
import org.eclipse.emf.ecore.xmi.XMLResource;
import org.eclipse.ocl.ParserException;
import org.eclipse.ocl.ecore.OCL;
import org.eclipse.ocl.ecore.OCLExpression;
import org.eclipse.ocl.ecore.OperationCallExp;
import org.eclipse.ocl.ecore.PropertyCallExp;
import org.eclipse.ocl.ecore.TypeExp;
import org.eclipse.ocl.ecore.IteratorExp;
import org.eclipse.uml2.uml.resources.util.UMLResourcesUtil;
import org.eclipse.uml2.uml.internal.resource.XMI2UMLResourceFactoryImpl;
import org.eclipse.xtext.diagnostics.Severity;
import org.eclipse.xtext.validation.Issue;
import org.omg.sysml.interactive.SysMLInteractive;
import org.omg.sysml.interactive.SysMLInteractiveResult;
import org.eclipse.uml2.uml.UMLPackage;
import org.eclipse.uml2.uml.Profile;

/**
 * Narrow, machine-readable adapters over the pinned upstream Java distribution.
 */
public final class ToolAdapter {
    private static final String ADAPTER_VERSION = "0.1.0";
    private static final Pattern UNTYPED_HREF = Pattern.compile(
        "<([A-Za-z_][A-Za-z0-9_.:-]*)(\\s+)"
            + "((?:(?!xmi:type=)[^>])*?\\bhref=\"([^\"]+)\"[^>]*)>"
    );
    private static final List<String> V1_OVERLAY_ORDER = List.of(
        "CoreRAAML.xmi",
        "CoreRAAMLLib.xmi",
        "GeneralRAAML.xmi",
        "GeneralRAAMLLib.xmi",
        "FMEA.xmi",
        "FTA.xmi",
        "GSN.xmi",
        "ISO26262.xmi",
        "RBD.xmi",
        "GeneralRAAMLSecurity.xmi",
        "STPA.xmi",
        "FMEALib.xmi",
        "FTALib.xmi",
        "ISO26262Lib.xmi",
        "RBDLib.xmi",
        "GeneralRAAMLSecurityLib.xmi",
        "STPALib.xmi"
    );

    private ToolAdapter() {
    }

    public static void main(String[] args) {
        Map<String, Object> report;
        int exitCode;
        try {
            if (args.length < 1) {
                throw new IllegalArgumentException(
                    "expected adapter mode: v2, v1, v1-corpus, ocl, or ocl-corpus"
                );
            }
            report = switch (args[0]) {
                case "v2" -> validateV2(args);
                case "v1" -> validateV1(args);
                case "v1-corpus" -> validateV1Corpus(args);
                case "ocl" -> parseOcl(args);
                case "ocl-corpus" -> parseOclCorpus(args);
                default -> throw new IllegalArgumentException("unknown adapter mode: " + args[0]);
            };
            exitCode = Boolean.TRUE.equals(report.get("ok")) ? 0 : 1;
        } catch (Exception error) {
            report = baseReport(args.length == 0 ? "unknown" : args[0]);
            report.put("ok", false);
            report.put("diagnostics", List.of(diagnostic(
                "error",
                "ADAPTER_FAILURE",
                error.getClass().getSimpleName() + ": " + safeMessage(error)
            )));
            finalizeReport(report);
            exitCode = 2;
        }
        System.out.println(toJson(report));
        System.exit(exitCode);
    }

    private static Map<String, Object> validateV2(String[] args) throws IOException {
        if (args.length != 3) {
            throw new IllegalArgumentException("usage: v2 MODEL_FILE LIBRARY_DIRECTORY");
        }
        Path model = existingRegularFile(args[1]);
        Path library = existingDirectory(args[2]);
        String input = Files.readString(model, StandardCharsets.UTF_8);

        SysMLInteractive validator = SysMLInteractive.createInstance();
        validator.loadLibrary(library.toAbsolutePath().toString());
        SysMLInteractiveResult result = validator.process(input, false);

        List<Map<String, Object>> diagnostics = new ArrayList<>();
        Map<String, Integer> categories = new LinkedHashMap<>();
        categories.put("lexicalSyntax", 0);
        categories.put("importLibrary", 0);
        categories.put("nameResolutionLinking", 0);
        categories.put("typeMultiplicity", 0);
        categories.put("modelValidation", 0);

        if (result.getException() != null) {
            diagnostics.add(diagnostic(
                "error",
                "V2_ADAPTER_EXCEPTION",
                result.getException().getClass().getSimpleName() + ": "
                    + safeMessage(result.getException())
            ));
            categories.compute("modelValidation", (key, count) -> count + 1);
        }

        for (Issue issue : result.getIssues()) {
            String category = classifyV2Issue(issue);
            if (issue.getSeverity() == Severity.ERROR) {
                categories.compute(category, (key, count) -> count + 1);
            }
            Map<String, Object> item = diagnostic(
                issue.getSeverity().name().toLowerCase(Locale.ROOT),
                issue.getCode() == null ? "V2_VALIDATION" : issue.getCode(),
                issue.getMessage()
            );
            item.put("category", category);
            if (issue.getLineNumber() != null) {
                item.put("line", issue.getLineNumber());
            }
            if (issue.getColumn() != null) {
                item.put("column", issue.getColumn());
            }
            diagnostics.add(item);
        }

        boolean ok = categories.values().stream().mapToInt(Integer::intValue).sum() == 0;
        Map<String, Object> report = baseReport("v2");
        report.put("ok", ok);
        report.put("input", model.getFileName().toString());
        report.put("errorCategories", categories);
        report.put("diagnostics", diagnostics);
        report.put("nativeStructure", nativeStructure(result));
        finalizeReport(report);
        return report;
    }

    private static Map<String, Object> nativeStructure(SysMLInteractiveResult result) {
        Map<String, Object> elements = new java.util.TreeMap<>();
        if (result.getRootElement() == null) {
            return elements;
        }
        TreeIterator<EObject> iterator = result.getRootElement().eAllContents();
        while (iterator.hasNext()) {
            EObject object = iterator.next();
            if (!(object instanceof org.omg.sysml.lang.sysml.Type type)) {
                continue;
            }
            String name = unescapedQualifiedName(type);
            if (type.getDeclaredName() == null || name == null
                    || !name.startsWith("RaamlFullCorpus::")) {
                continue;
            }
            Map<String, Object> description = new LinkedHashMap<>();
            description.put("kind", type.eClass().getName());
            description.put("abstract", type.isAbstract());
            description.put("annotations", new ArrayList<String>());
            description.put("supertypes", type.getOwnedSpecialization().stream()
                .filter(relation -> relation.getGeneral() != null)
                .map(relation -> unescapedQualifiedName(relation.getGeneral()))
                .filter(java.util.Objects::nonNull).sorted().toList());
            if (type instanceof org.omg.sysml.lang.sysml.Feature feature) {
                description.put("types", feature.getType().stream()
                    .map(ToolAdapter::unescapedQualifiedName)
                    .filter(java.util.Objects::nonNull).sorted().toList());
                description.put("ordered", feature.isOrdered());
                description.put("unique", feature.isUnique());
                description.put("derived", feature.isDerived());
                for (org.omg.sysml.lang.sysml.Relationship relation : feature.getOwnedRelationship()) {
                    if (relation instanceof org.omg.sysml.lang.sysml.FeatureValue value && value.isDefault()) {
                        description.put("default", boundValue(value.getValue()));
                    }
                }
                if (feature.getMultiplicity() instanceof org.omg.sysml.lang.sysml.MultiplicityRange range) {
                    description.put("lower", boundValue(range.getBound().size() == 1 ? range.getUpperBound() : range.getLowerBound()));
                    description.put("upper", boundValue(range.getUpperBound()));
                }
            }
            elements.put(name, description);
        }
        iterator = result.getRootElement().eAllContents();
        while (iterator.hasNext()) {
            EObject object = iterator.next();
            if (object instanceof org.omg.sysml.lang.sysml.MetadataFeature metadata
                    && metadata.getMetaclass() != null) {
                for (org.omg.sysml.lang.sysml.Element target : metadata.getAnnotatedElement()) {
                    Object entry = elements.get(unescapedQualifiedName(target));
                    if (entry instanceof Map<?, ?> record
                            && record.get("annotations") instanceof List<?> list) {
                        @SuppressWarnings("unchecked")
                        List<String> annotations = (List<String>) list;
                        annotations.add(unescapedQualifiedName(metadata.getMetaclass()));
                        annotations.sort(String::compareTo);
                    }
                }
            }
        }
        return elements;
    }

    private static String unescapedQualifiedName(org.omg.sysml.lang.sysml.Element element) {
        List<String> names = new ArrayList<>();
        for (org.omg.sysml.lang.sysml.Element cursor = element; cursor != null; cursor = cursor.getOwner()) {
            if (cursor.getDeclaredName() != null) {
                names.add(0, cursor.getDeclaredName());
            }
        }
        return String.join("::", names);
    }

    private static String boundValue(org.omg.sysml.lang.sysml.Expression expression) {
        if (expression instanceof org.omg.sysml.lang.sysml.LiteralInteger integer) {
            return Integer.toString(integer.getValue());
        }
        if (expression instanceof org.omg.sysml.lang.sysml.LiteralInfinity) {
            return "*";
        }
        return null;
    }

    private static String classifyV2Issue(Issue issue) {
        if (issue.isSyntaxError()) {
            return "lexicalSyntax";
        }
        String text = ((issue.getCode() == null ? "" : issue.getCode()) + " "
            + (issue.getMessage() == null ? "" : issue.getMessage())).toLowerCase(Locale.ROOT);
        if (containsAny(text, "import", "library", "package not found")) {
            return "importLibrary";
        }
        if (containsAny(text, "resolve", "reference", "linking", "not visible", "not found")) {
            return "nameResolutionLinking";
        }
        if (containsAny(text, "type", "multiplicity", "conform", "cardinality")) {
            return "typeMultiplicity";
        }
        return "modelValidation";
    }

    private static Map<String, Object> validateV1(String[] args) throws IOException {
        if (args.length != 3 && args.length != 4) {
            throw new IllegalArgumentException(
                "usage: v1 MODEL_FILE CATALOG_DIRECTORY [OVERLAY_DIRECTORY]"
            );
        }
        Path model = existingRegularFile(args[1]);
        Path catalog = existingDirectory(args[2]);
        Path overlay = args.length == 4 ? existingDirectory(args[3]) : null;

        ResourceSet resourceSet = initializeV1ResourceSet(catalog, overlay);
        if (!model.getFileName().toString().equals("CoreRAAML.xmi")) {
            registerProfile(
                resourceSet,
                (overlay == null ? catalog : overlay).resolve("CoreRAAML.xmi")
            );
        }

        Resource resource = loadNormalized(
            resourceSet,
            URI.createFileURI(model.toAbsolutePath().toString()),
            model
        );
        EcoreUtil.resolveAll(resourceSet);
        return validateV1Resource(resourceSet, resource, model.getFileName().toString());
    }

    private static ResourceSet initializeV1ResourceSet(Path catalog, Path overlay)
        throws IOException {
        ResourceSet resourceSet = UMLResourcesUtil.init(new ResourceSetImpl());
        resourceSet.getPackageRegistry().put(
            "http://www.omg.org/spec/UML/20131001",
            UMLPackage.eINSTANCE
        );
        String umlBase = "http://www.omg.org/spec/UML/20131001/";
        preload(resourceSet, umlBase + "PrimitiveTypes.xmi", catalog.resolve("PrimitiveTypes.xmi"));
        preload(resourceSet, umlBase + "UML.xmi", catalog.resolve("UML.xmi"));
        requireFragment(resourceSet, umlBase + "UML.xmi", "Parameter");
        preload(resourceSet, umlBase + "StandardProfile.xmi", catalog.resolve("StandardProfile.xmi"));
        String localSysml = catalog.resolve("SysML.xmi").toUri().toString();
        preload(resourceSet, localSysml, catalog.resolve("SysML.xmi"));
        alias(
            resourceSet,
            "https://www.omg.org/spec/SysML/20181001/SysML.xmi",
            localSysml
        );
        alias(
            resourceSet,
            "http://www.omg.org/spec/SysML/20181001/SysML.xmi",
            localSysml
        );
        String qudv =
            "https://www.omg.org/spec/SysML/20181001/QUDV.xmi";
        preload(resourceSet, qudv, catalog.resolve("QUDV.xmi"));
        alias(
            resourceSet,
            "http://www.omg.org/spec/SysML/20181001/QUDV.xmi",
            qudv
        );
        String iso80000 =
            "https://www.omg.org/spec/SysML/20181001/ISO80000.xmi";
        preload(resourceSet, iso80000, catalog.resolve("ISO80000.xmi"));
        requireFragment(
            resourceSet,
            localSysml,
            "SysML.DirectedRelationshipPropertyPath"
        );
        alias(resourceSet, "https://www.omg.org/spec/UML/20161101/UML.xmi", umlBase + "UML.xmi");
        alias(resourceSet, "http://www.omg.org/spec/UML/20161101/UML.xmi", umlBase + "UML.xmi");
        alias(
            resourceSet,
            "https://www.omg.org/spec/UML/20161101/PrimitiveTypes.xmi",
            umlBase + "PrimitiveTypes.xmi"
        );
        alias(
            resourceSet,
            "http://www.omg.org/spec/UML/20161101/PrimitiveTypes.xmi",
            umlBase + "PrimitiveTypes.xmi"
        );
        alias(
            resourceSet,
            "https://www.omg.org/spec/UML/20161101/StandardProfile.xmi",
            umlBase + "StandardProfile.xmi"
        );
        alias(
            resourceSet,
            "http://www.omg.org/spec/UML/20161101/StandardProfile.xmi",
            umlBase + "StandardProfile.xmi"
        );
        alias(
            resourceSet,
            "http://www.omg.org/spec/SysML/20181001/ISO80000.xmi",
            iso80000
        );

        try (var files = Files.list(catalog)) {
            files.filter(path -> path.getFileName().toString().endsWith(".xmi"))
                .forEach(path -> alias(
                    resourceSet,
                    "https://www.omg.org/spec/RAAML/20240219/" + path.getFileName(),
                    URI.createFileURI(path.toAbsolutePath().toString()).toString()
                ));
        }
        if (overlay != null) {
            try (var files = Files.list(overlay)) {
                for (Path path : files
                    .filter(item -> item.getFileName().toString().endsWith(".xmi"))
                    .sorted(
                        Comparator
                            .comparingInt(
                                (Path item) -> overlayRank(
                                    item.getFileName().toString()
                                )
                            )
                            .thenComparing(
                                item -> item.getFileName().toString()
                            )
                    )
                    .toList()) {
                    String filename = path.getFileName().toString();
                    String remote =
                        "https://www.omg.org/spec/RAAML/20240219/" + filename;
                    String generated = "generated:/" + filename;
                    alias(resourceSet, remote, generated);
                    alias(
                        resourceSet,
                        "http://www.omg.org/spec/RAAML/20240219/" + filename,
                        generated
                    );
                    preload(
                        resourceSet,
                        generated,
                        path
                    );
                }
            }
        }
        return resourceSet;
    }

    private static Map<String, Object> validateV1Resource(
        ResourceSet resourceSet,
        Resource resource,
        String input
    ) {
        List<Map<String, Object>> diagnostics = new ArrayList<>();
        for (Resource loaded : resourceSet.getResources()) {
            addResourceDiagnostics(loaded, diagnostics);
        }
        TreeIterator<EObject> contents = resource.getAllContents();
        while (contents.hasNext()) {
            EObject object = contents.next();
            if (object.eIsProxy()) {
                diagnostics.add(diagnostic(
                    "error",
                    "V1_UNRESOLVED_PROXY",
                    EcoreUtil.getURI(object).toString()
                ));
            }
        }
        for (EObject root : resource.getContents()) {
            collectDiagnostic(Diagnostician.INSTANCE.validate(root), diagnostics);
        }

        boolean ok = diagnostics.stream()
            .noneMatch(item -> "error".equals(item.get("severity")));
        Map<String, Object> report = baseReport("v1");
        report.put("ok", ok);
        report.put("input", input);
        report.put("loadedResources", resourceSet.getResources().size());
        report.put("diagnostics", diagnostics);
        finalizeReport(report);
        return report;
    }

    private static Map<String, Object> validateV1Corpus(String[] args) throws IOException {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                "usage: v1-corpus MODEL_DIRECTORY CATALOG_DIRECTORY"
            );
        }
        Path models = existingDirectory(args[1]);
        Path catalog = existingDirectory(args[2]);
        List<Path> modelPaths;
        try (var files = Files.list(models)) {
            modelPaths = files
                .filter(path -> path.getFileName().toString().endsWith(".xmi"))
                .sorted(
                    Comparator
                        .comparingInt(
                            (Path item) -> overlayRank(
                                item.getFileName().toString()
                            )
                        )
                        .thenComparing(item -> item.getFileName().toString())
                )
                .toList();
        }
        if (modelPaths.size() != V1_OVERLAY_ORDER.size()) {
            throw new IllegalArgumentException(
                "expected " + V1_OVERLAY_ORDER.size()
                    + " corpus XMI files, got " + modelPaths.size()
            );
        }
        List<String> filenames = modelPaths.stream()
            .map(path -> path.getFileName().toString())
            .toList();
        if (!new LinkedHashSet<>(filenames).equals(
            new LinkedHashSet<>(V1_OVERLAY_ORDER)
        )) {
            throw new IllegalArgumentException(
                "corpus filenames do not match the required RAAML overlay"
            );
        }

        ResourceSet resourceSet = initializeV1ResourceSet(catalog, models);
        registerProfile(resourceSet, models.resolve("CoreRAAML.xmi"));
        EcoreUtil.resolveAll(resourceSet);

        List<Map<String, Object>> results = new ArrayList<>();
        for (Path path : modelPaths) {
            String filename = path.getFileName().toString();
            Resource resource = resourceSet.getResource(
                URI.createURI("generated:/" + filename),
                false
            );
            if (resource == null) {
                throw new IllegalArgumentException(
                    "preloaded corpus resource is missing: " + filename
                );
            }
            results.add(validateV1Resource(resourceSet, resource, filename));
        }

        long failures = results.stream()
            .filter(result -> !Boolean.TRUE.equals(result.get("ok")))
            .count();
        Map<String, Object> report = baseReport("v1-corpus");
        report.put("ok", failures == 0);
        report.put("results", results);
        report.put("diagnostics", List.of());
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("checked", results.size());
        summary.put("failed", failures);
        report.put("summary", summary);
        return report;
    }

    private static int overlayRank(String filename) {
        int index = V1_OVERLAY_ORDER.indexOf(filename);
        return index < 0 ? V1_OVERLAY_ORDER.size() : index;
    }

    private static void registerProfile(ResourceSet resourceSet, Path profilePath) {
        Resource resource = loadNormalized(
            resourceSet,
            URI.createFileURI(profilePath.toAbsolutePath().toString()),
            profilePath
        );
        Profile profile = null;
        for (EObject root : resource.getContents()) {
            if (root instanceof Profile candidate) {
                profile = candidate;
                break;
            }
        }
        if (profile == null) {
            throw new IllegalArgumentException("profile artifact has no UML Profile root: " + profilePath);
        }
        EPackage definition = profile.define();
        if (definition == null || definition.getNsURI() == null) {
            throw new IllegalArgumentException("profile could not be defined: " + profilePath);
        }
        resourceSet.getPackageRegistry().put(definition.getNsURI(), definition);
    }

    private static void addResourceDiagnostics(
        Resource resource,
        List<Map<String, Object>> diagnostics
    ) {
        for (Resource.Diagnostic error : resource.getErrors()) {
            Map<String, Object> item = diagnostic("error", "V1_RESOURCE_ERROR", error.getMessage());
            item.put("line", error.getLine());
            item.put("column", error.getColumn());
            diagnostics.add(item);
        }
        for (Resource.Diagnostic warning : resource.getWarnings()) {
            Map<String, Object> item = diagnostic("warning", "V1_RESOURCE_WARNING", warning.getMessage());
            item.put("line", warning.getLine());
            item.put("column", warning.getColumn());
            diagnostics.add(item);
        }
    }

    private static void collectDiagnostic(
        Diagnostic source,
        List<Map<String, Object>> diagnostics
    ) {
        if (source.getSeverity() >= Diagnostic.WARNING) {
            String severity = source.getSeverity() >= Diagnostic.ERROR ? "error" : "warning";
            diagnostics.add(diagnostic(severity, "V1_MODEL_DIAGNOSTIC", source.getMessage()));
        }
        for (Diagnostic child : source.getChildren()) {
            collectDiagnostic(child, diagnostics);
        }
    }

    private static Map<String, Object> parseOcl(String[] args) throws IOException {
        if (args.length != 2) {
            throw new IllegalArgumentException("usage: ocl EXPRESSION_FILE");
        }
        Path expressionFile = existingRegularFile(args[1]);
        String text = Files.readString(expressionFile, StandardCharsets.UTF_8);

        EcoreFactory factory = EcoreFactory.eINSTANCE;
        EPackage scope = factory.createEPackage();
        scope.setName("raamlSmoke");
        scope.setNsPrefix("raamlSmoke");
        scope.setNsURI("urn:raaml:smoke");
        EClass situation = factory.createEClass();
        situation.setName("Situation");
        scope.getEClassifiers().add(situation);
        EReference from = factory.createEReference();
        from.setName("from");
        from.setEType(situation);
        from.setUpperBound(-1);
        situation.getEStructuralFeatures().add(from);

        List<Map<String, Object>> diagnostics = new ArrayList<>();
        Set<String> names = new LinkedHashSet<>();
        OCL ocl = OCL.newInstance();
        try {
            OCL.Helper helper = ocl.createOCLHelper();
            helper.setContext(situation);
            OCLExpression expression = helper.createQuery(text);
            names.add(situation.getName());
            collectOclName(expression, names);
            TreeIterator<EObject> nodes = expression.eAllContents();
            while (nodes.hasNext()) {
                collectOclName(nodes.next(), names);
            }
        } catch (ParserException error) {
            diagnostics.add(diagnostic("error", "OCL_PARSE_ERROR", safeMessage(error)));
        } finally {
            ocl.dispose();
        }

        List<String> referencedNames = new ArrayList<>(names);
        referencedNames.sort(Comparator.naturalOrder());
        Map<String, Object> report = baseReport("ocl");
        report.put("ok", diagnostics.isEmpty());
        report.put("input", expressionFile.getFileName().toString());
        report.put("referencedNames", referencedNames);
        report.put("diagnostics", diagnostics);
        finalizeReport(report);
        return report;
    }

    private static Map<String, Object> parseOclCorpus(String[] args) throws IOException {
        if (args.length != 2) {
            throw new IllegalArgumentException("usage: ocl-corpus CATALOG_FILE");
        }
        Path catalogFile = existingRegularFile(args[1]);
        Set<String> typeNames = new LinkedHashSet<>();
        Set<String> propertyNames = new LinkedHashSet<>();
        List<String[]> constraints = new ArrayList<>();
        Base64.Decoder decoder = Base64.getDecoder();
        for (String line : Files.readAllLines(catalogFile, StandardCharsets.UTF_8)) {
            if (line.isEmpty()) {
                continue;
            }
            String[] fields = line.split("\\t", -1);
            switch (fields[0]) {
                case "TYPE" -> {
                    requireFieldCount(fields, 2, "TYPE");
                    typeNames.add(decodeField(decoder, fields[1]));
                }
                case "PROPERTY" -> {
                    requireFieldCount(fields, 2, "PROPERTY");
                    propertyNames.add(decodeField(decoder, fields[1]));
                }
                case "CONSTRAINT" -> {
                    requireFieldCount(fields, 4, "CONSTRAINT");
                    constraints.add(new String[] {
                        decodeField(decoder, fields[1]),
                        decodeField(decoder, fields[2]),
                        decodeField(decoder, fields[3])
                    });
                }
                default -> throw new IllegalArgumentException(
                    "unknown OCL catalog record: " + fields[0]
                );
            }
        }
        if (constraints.isEmpty()) {
            throw new IllegalArgumentException("OCL catalog has no constraints");
        }

        EcoreFactory factory = EcoreFactory.eINSTANCE;
        EPackage scope = factory.createEPackage();
        scope.setName("raamlCorpus");
        scope.setNsPrefix("raamlCorpus");
        scope.setNsURI("urn:raaml:corpus");
        EClass any = factory.createEClass();
        any.setName("RaamlAny");
        scope.getEClassifiers().add(any);
        for (String propertyName : propertyNames) {
            if ("name".equals(propertyName)) {
                EAttribute attribute = factory.createEAttribute();
                attribute.setName(propertyName);
                attribute.setEType(EcorePackage.Literals.ESTRING);
                attribute.setUpperBound(-1);
                any.getEStructuralFeatures().add(attribute);
            } else {
                EReference reference = factory.createEReference();
                reference.setName(propertyName);
                reference.setEType(any);
                reference.setUpperBound(-1);
                any.getEStructuralFeatures().add(reference);
            }
        }
        Map<String, EClass> classes = new LinkedHashMap<>();
        for (String typeName : typeNames) {
            EClass classifier = factory.createEClass();
            classifier.setName(typeName);
            classifier.getESuperTypes().add(any);
            scope.getEClassifiers().add(classifier);
            classes.put(typeName, classifier);
        }

        List<Map<String, Object>> diagnostics = new ArrayList<>();
        List<Map<String, Object>> results = new ArrayList<>();
        OCL ocl = OCL.newInstance();
        try {
            for (String[] constraint : constraints) {
                String key = constraint[0];
                String owner = constraint[1];
                String text = constraint[2];
                Map<String, Object> result = new LinkedHashMap<>();
                result.put("key", key);
                result.put("owner", owner);
                List<Map<String, Object>> itemDiagnostics = new ArrayList<>();
                Set<String> referencedTypes = new LinkedHashSet<>();
                Set<String> referencedProperties = new LinkedHashSet<>();
                Set<String> referencedOperations = new LinkedHashSet<>();
                Set<String> referencedIterators = new LinkedHashSet<>();
                EClass context = classes.get(owner);
                if (context == null) {
                    itemDiagnostics.add(diagnostic(
                        "error",
                        "OCL_CONTEXT_UNRESOLVED",
                        "context type is not in the catalog: " + owner
                    ));
                } else {
                    try {
                        OCL.Helper helper = ocl.createOCLHelper();
                        helper.setContext(context);
                        OCLExpression expression = helper.createQuery(text);
                        collectOclReferences(
                            expression,
                            referencedTypes,
                            referencedProperties,
                            referencedOperations,
                            referencedIterators
                        );
                        TreeIterator<EObject> nodes = expression.eAllContents();
                        while (nodes.hasNext()) {
                            collectOclReferences(
                                nodes.next(),
                                referencedTypes,
                                referencedProperties,
                                referencedOperations,
                                referencedIterators
                            );
                        }
                    } catch (ParserException error) {
                        itemDiagnostics.add(diagnostic(
                            "error",
                            "OCL_PARSE_ERROR",
                            safeMessage(error)
                        ));
                    }
                }
                sortInto(result, "referencedTypes", referencedTypes);
                sortInto(result, "referencedProperties", referencedProperties);
                sortInto(result, "referencedOperations", referencedOperations);
                sortInto(result, "referencedIterators", referencedIterators);
                result.put("diagnostics", itemDiagnostics);
                result.put("ok", itemDiagnostics.isEmpty());
                results.add(result);
                for (Map<String, Object> item : itemDiagnostics) {
                    Map<String, Object> aggregate = new LinkedHashMap<>(item);
                    aggregate.put(
                        "message",
                        key + ": " + String.valueOf(item.get("message"))
                    );
                    diagnostics.add(aggregate);
                }
            }
        } finally {
            ocl.dispose();
        }

        Map<String, Object> report = baseReport("ocl-corpus");
        report.put("ok", diagnostics.isEmpty());
        report.put("input", catalogFile.getFileName().toString());
        report.put("results", results);
        report.put("diagnostics", diagnostics);
        finalizeReport(report);
        @SuppressWarnings("unchecked")
        Map<String, Object> summary = (Map<String, Object>) report.get("summary");
        summary.put("checked", results.size());
        return report;
    }

    private static void requireFieldCount(
        String[] fields,
        int expected,
        String record
    ) {
        if (fields.length != expected) {
            throw new IllegalArgumentException(
                record + " record has " + fields.length
                    + " fields; expected " + expected
            );
        }
    }

    private static String decodeField(Base64.Decoder decoder, String value) {
        return new String(decoder.decode(value), StandardCharsets.UTF_8);
    }

    private static void sortInto(
        Map<String, Object> target,
        String field,
        Set<String> values
    ) {
        List<String> sorted = new ArrayList<>(values);
        sorted.sort(Comparator.naturalOrder());
        target.put(field, sorted);
    }

    private static void collectOclReferences(
        EObject node,
        Set<String> types,
        Set<String> properties,
        Set<String> operations,
        Set<String> iterators
    ) {
        if (node instanceof TypeExp typeExpression) {
            EClassifier type = typeExpression.getReferredType();
            if (type != null && type.getName() != null) {
                types.add(type.getName());
            }
        } else if (node instanceof PropertyCallExp propertyExpression) {
            if (propertyExpression.getReferredProperty() != null) {
                properties.add(propertyExpression.getReferredProperty().getName());
            }
        } else if (node instanceof OperationCallExp operationExpression) {
            if (operationExpression.getReferredOperation() != null) {
                operations.add(operationExpression.getReferredOperation().getName());
            }
        } else if (node instanceof IteratorExp iteratorExpression) {
            if (iteratorExpression.getName() != null) {
                iterators.add(iteratorExpression.getName());
            }
        }
    }

    private static void collectOclName(EObject node, Set<String> names) {
        if (node instanceof TypeExp typeExpression) {
            EClassifier type = typeExpression.getReferredType();
            if (type != null && type.getName() != null) {
                names.add(type.getName());
            }
        } else if (node instanceof PropertyCallExp propertyExpression) {
            if (propertyExpression.getReferredProperty() != null) {
                names.add(propertyExpression.getReferredProperty().getName());
            }
        } else if (node instanceof OperationCallExp operationExpression) {
            if (operationExpression.getReferredOperation() != null) {
                names.add(operationExpression.getReferredOperation().getName());
            }
        } else if (node instanceof IteratorExp iteratorExpression) {
            if (iteratorExpression.getName() != null) {
                names.add(iteratorExpression.getName());
            }
        }
    }

    private static void preload(ResourceSet resourceSet, String remote, Path local) {
        if (!Files.isRegularFile(local)) {
            throw new IllegalArgumentException("catalog artifact is missing: " + local);
        }
        try {
            loadNormalized(resourceSet, URI.createURI(remote), local);
        } catch (RuntimeException error) {
            throw new IllegalArgumentException("cannot preload catalog artifact: " + local, error);
        }
    }

    private static Resource loadNormalized(
        ResourceSet resourceSet,
        URI resourceUri,
        Path local
    ) {
        try {
            byte[] original = Files.readAllBytes(local);
            String text = new String(original, StandardCharsets.UTF_8)
                .replace(
                    "http://www.omg.org/spec/UML/20161101",
                    "http://www.omg.org/spec/UML/20131001"
                )
                .replace(
                    "https://www.omg.org/spec/UML/20161101",
                    "http://www.omg.org/spec/UML/20131001"
                );
            for (Map.Entry<URI, URI> mapping
                : resourceSet.getURIConverter().getURIMap().entrySet()) {
                text = text.replace(mapping.getKey().toString(), mapping.getValue().toString());
            }
            text = addConcreteProxyTypes(resourceSet, text);
            Resource resource = new XMI2UMLResourceFactoryImpl().createResource(resourceUri);
            resourceSet.getResources().add(resource);
            resource.load(
                new ByteArrayInputStream(text.getBytes(StandardCharsets.UTF_8)),
                Map.of(
                    XMLResource.OPTION_DEFER_IDREF_RESOLUTION,
                    Boolean.TRUE,
                    XMLResource.OPTION_DEFER_ATTACHMENT,
                    Boolean.TRUE
                )
            );
            return resource;
        } catch (IOException error) {
            throw new IllegalArgumentException("cannot load normalized XMI: " + local, error);
        }
    }

    private static String addConcreteProxyTypes(ResourceSet resourceSet, String text) {
        Matcher matcher = UNTYPED_HREF.matcher(text);
        StringBuffer result = new StringBuffer();
        while (matcher.find()) {
            EObject target;
            try {
                target = resourceSet.getEObject(URI.createURI(matcher.group(4)), true);
            } catch (RuntimeException error) {
                target = null;
            }
            if (target instanceof org.eclipse.uml2.uml.Element) {
                String replacement = "<" + matcher.group(1) + matcher.group(2)
                    + "xmi:type=\"uml:" + target.eClass().getName() + "\" "
                    + matcher.group(3) + ">";
                matcher.appendReplacement(result, Matcher.quoteReplacement(replacement));
            } else {
                matcher.appendReplacement(result, Matcher.quoteReplacement(matcher.group()));
            }
        }
        matcher.appendTail(result);
        return result.toString();
    }

    private static void alias(ResourceSet resourceSet, String remote, String target) {
        resourceSet.getURIConverter().getURIMap().put(
            URI.createURI(remote),
            URI.createURI(target)
        );
    }

    private static void requireFragment(
        ResourceSet resourceSet,
        String resourceUri,
        String fragment
    ) {
        Resource resource = resourceSet.getResource(URI.createURI(resourceUri), false);
        EObject object = resource == null ? null : resource.getEObject(fragment);
        if (object == null) {
            throw new IllegalArgumentException(
                "catalog fragment is unavailable: " + resourceUri + "#" + fragment
            );
        }
        if (!(object instanceof org.eclipse.uml2.uml.Type)) {
            throw new IllegalArgumentException(
                "catalog fragment has wrong runtime type: " + object.getClass().getName()
            );
        }
    }

    private static Path existingRegularFile(String value) {
        Path path = Path.of(value);
        if (!Files.isRegularFile(path) || Files.isSymbolicLink(path)) {
            throw new IllegalArgumentException("not a regular non-symlink file: " + value);
        }
        return path;
    }

    private static Path existingDirectory(String value) {
        Path path = Path.of(value);
        if (!Files.isDirectory(path) || Files.isSymbolicLink(path)) {
            throw new IllegalArgumentException("not a non-symlink directory: " + value);
        }
        return path;
    }

    private static boolean containsAny(String text, String... candidates) {
        for (String candidate : candidates) {
            if (text.contains(candidate)) {
                return true;
            }
        }
        return false;
    }

    private static Map<String, Object> baseReport(String adapter) {
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("schemaVersion", "0.1.0");
        report.put("adapter", adapter);
        report.put("adapterVersion", ADAPTER_VERSION);
        report.put("command", "validate-" + adapter);
        return report;
    }

    @SuppressWarnings("unchecked")
    private static void finalizeReport(Map<String, Object> report) {
        List<Map<String, Object>> diagnostics =
            (List<Map<String, Object>>) report.getOrDefault("diagnostics", List.of());
        long failures = diagnostics.stream()
            .filter(item -> "error".equals(item.get("severity")))
            .count();
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("checked", 1);
        summary.put("failed", failures);
        report.put("summary", summary);
    }

    private static Map<String, Object> diagnostic(
        String severity,
        String code,
        String message
    ) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("severity", severity);
        value.put("code", code);
        value.put("message", message == null ? "" : message);
        return value;
    }

    private static String safeMessage(Throwable error) {
        String message = error.getMessage() == null ? "(no message)" : error.getMessage();
        if (error.getCause() != null && error.getCause() != error) {
            return message + "; caused by " + error.getCause().getClass().getSimpleName()
                + ": " + safeMessage(error.getCause());
        }
        return message;
    }

    private static String toJson(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof String string) {
            return "\"" + jsonEscape(string) + "\"";
        }
        if (value instanceof Boolean || value instanceof Number) {
            return value.toString();
        }
        if (value instanceof Map<?, ?> map) {
            StringBuilder result = new StringBuilder("{");
            boolean first = true;
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!first) {
                    result.append(",");
                }
                first = false;
                result.append(toJson(entry.getKey().toString()));
                result.append(":");
                result.append(toJson(entry.getValue()));
            }
            return result.append("}").toString();
        }
        if (value instanceof Iterable<?> iterable) {
            StringBuilder result = new StringBuilder("[");
            boolean first = true;
            for (Object item : iterable) {
                if (!first) {
                    result.append(",");
                }
                first = false;
                result.append(toJson(item));
            }
            return result.append("]").toString();
        }
        throw new IllegalArgumentException("cannot serialize " + value.getClass().getName());
    }

    private static String jsonEscape(String value) {
        StringBuilder result = new StringBuilder();
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            switch (character) {
                case '"' -> result.append("\\\"");
                case '\\' -> result.append("\\\\");
                case '\b' -> result.append("\\b");
                case '\f' -> result.append("\\f");
                case '\n' -> result.append("\\n");
                case '\r' -> result.append("\\r");
                case '\t' -> result.append("\\t");
                default -> {
                    if (character < 0x20) {
                        result.append(String.format("\\u%04x", (int) character));
                    } else {
                        result.append(character);
                    }
                }
            }
        }
        return result.toString();
    }
}
