# Architecture

## Layered architecture

```text
Future UI / CLI
        |
Application orchestration and batch boundaries
        |
Assay plugins -> deterministic statistics -> visualization -> reporting
        |
Ingestion -> profiling/QC -> confirmed analysis plan
        |
Contracts and audit primitives
        |
Local filesystem and user-controlled configuration
```

Phase 1 implements the contracts, read-only ingestion, and structural profiling/QC boundaries.
Phase 2A implements a deterministic `generic_grouped` descriptive-statistics boundary at
`measurement_rows` level. Phase 2B adds only a separate explicit-design boundary for one
two-group `generic_grouped` Welch comparison at `experimental_units` level. Phase 3A adds a
separate standard-only ELISA 4PL boundary at `standard_curve_levels`; Phase 3B adds only the
research-only per-measurement inverse boundary. Visualization, reporting, AI, batch orchestration,
and UI remain out of scope.

## Module responsibilities

- `contracts`: versioned Pydantic models, enums, serialization, and JSON Schema. No I/O or scientific calculations.
- `ingestion`: read-only Phase 1 CSV/XLSX intake, source preservation, encoding/format errors, sheet selection, resource limits, and hashes.
- `profiling`: Phase 1 structural shape/type/missingness profiling, explicit mapping validation, and reviewable alerts. It does not calculate CVs or statistics.
- `assays`: future plugin definitions and assay-specific validation/planning rules.
- `statistics`: Phase 2A row-level plan binding/descriptive calculations, Phase 2B explicit-design experimental-unit preview/Welch calculation, Phase 3A standard-only 4PL preview/fitting, and Phase 3B research-only per-measurement inverse estimation. It does not infer biological sample size, verify independence, select models automatically, claim validated quantification, or depend on UI/AI.
- `visualization`: future rendering from structured results; it must not recompute scientific values.
- `reporting`: future JSON/XLSX/DOCX rendering from manifest and derived artifacts.
- `audit`: future run-manifest persistence and provenance checks.
- `ai`: future optional adapter that receives structured results and returns labeled narrative only.
- `batch`: future orchestration for multiple independent runs with isolated manifests.
- `ui`: future presentation layer; it must not own scientific rules.

## Data flow

Source bytes -> immutable `InputFile` identity -> `DatasetProfile` and `ValidationIssue` list ->
Phase 1 `ImportResult` -> unconfirmed `AnalysisPlan` -> explicit design/unit or standard preview
-> plan-hash and warning confirmation -> Phase 2A row-level, Phase 2B unit-level, or Phase 3A
standard-level structured result -> Phase 3B research-only measurement-row inverse (when
explicitly confirmed) -> future `ChartArtifact` / `ReportArtifact` -> `RunManifest`.

The original file is never replaced by a derived table. Any future derived representation must carry its source hash and transformation metadata. Warnings and unresolved issues travel with the run.

## Dependency direction

Dependencies point inward toward contracts. Ingestion, profiling, assays, statistics, visualization, reporting, AI, batch, and UI may depend on contracts, but contracts must not depend on any of them. Phase 2A, 2B, 3A, and 3B statistics consume the read-only Phase 1 import contract and ingestion hash helper; SciPy is isolated at the Welch and 4PL calculation boundaries. Phase 3B consumes a validated Phase 3A artifact and never refits the curve. These modules must not depend on UI, AI, database, or network code. AI may depend on a read-only result DTO and an explicit provider adapter, never on a data-frame execution environment. Reporting may consume artifacts but must not calculate statistics.

## Future plugin interface

The intended plugin boundary is a small, typed interface with methods conceptually equivalent to:

- identify whether a confirmed `ExperimentSpec` applies;
- validate/profile assay-specific fields and emit `ValidationIssue` values;
- propose an `AnalysisPlan` without executing it;
- execute only a confirmed plan and return `AnalysisResult`;
- describe supported outputs and assumptions.

The interface will be designed and tested in the phase that introduces assays. Plugins must declare a stable name, contract version, supported input schema, assumptions, and deterministic implementation version. Phase 0 does not add an executable plugin registry.

## Optional Antibody AI integration boundary

Any future integration is optional and isolated behind an adapter in `ai` or an external integration package. It may map user-approved identifiers such as `antibody_id`, `sequence_id`, `mutation_id`, `experiment_id`, or `sample_id` into context, subject to explicit consent and redaction. It must not require the external project, copy its code, receive raw files by default, calculate statistics, delete data, or modify conclusions. The core system must remain fully functional when the adapter is absent.
