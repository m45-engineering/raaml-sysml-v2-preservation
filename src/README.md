# Implementation

The implementation exposes a standalone file- and command-line interface and
does not depend on M45 product code or infrastructure.

`facts.py` extracts source facts, including the SysML applications needed to
select native definitions and reconstruct nested connector paths.
`v2.py` renders the full native structure and checks the validator's resolved
model against source obligations. `roundtrip.py` handles manifests,
deterministic v1 reconstruction, comparison, and the legacy milestone-3 view.
See [the development mapping notes](../docs/native-package-mapping-v0.2.md)
for the distinction between structural mapping and executable constraints.
