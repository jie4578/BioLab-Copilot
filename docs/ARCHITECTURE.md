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

Phase 0 implements only the contracts layer and placeholders. The diagram is a target boundary, not implemented behavior.

## Module responsibilities

- `contracts`: versioned Pydantic models, enums, serialization, and JSON Schema. No I/O or scientific calculations.
- `ingestion`: future read-only CSV/XLSX intake, source preservation, encoding/format errors, and hashes.
- `profiling`: future descriptive shape/type/missingness profiling and alerts.
- `assays`: future plugin definitions and assay-specific validation/planning rules.
- `statistics`: future deterministic calculations only; numeric outputs must be structured and testable.
- `visualization`: future rendering from structured results; it must not recompute scientific values.
- `reporting`: future JSON/XLSX/DOCX rendering from manifest and derived artifacts.
- `audit`: future run-manifest persistence and provenance checks.
- `ai`: future optional adapter that receives structured results and returns labeled narrative only.
- `batch`: future orchestration for multiple independent runs with isolated manifests.
- `ui`: future presentation layer; it must not own scientific rules.

## Data flow

Source bytes -> immutable `InputFile` identity -> `DatasetProfile` and `ValidationIssue` list -> confirmed `AnalysisPlan` -> `AnalysisResult` -> `ChartArtifact` / `ReportArtifact` -> `RunManifest`.

The original file is never replaced by a derived table. Any future derived representation must carry its source hash and transformation metadata. Warnings and unresolved issues travel with the run.

## Dependency direction

Dependencies point inward toward contracts. Ingestion, profiling, assays, statistics, visualization, reporting, AI, batch, and UI may depend on contracts, but contracts must not depend on any of them. Statistics must not depend on UI or AI. AI may depend on a read-only result DTO and an explicit provider adapter, never on a data frame execution environment. Reporting may consume artifacts but must not calculate statistics.

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

