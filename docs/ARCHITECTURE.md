# Architecture

## Runtime layers

```text
Local Gradio UI / offline CLI
             |
Workflow orchestration and explicit plan confirmation
             |
Read-only ingestion -> structural QC -> versioned contracts
             |
Deterministic statistics and ELISA 4PL workflows
             |
PNG visualization and DOCX / XLSX / JSON reporting
             |
Local run directories, manifests, and SHA-256 provenance
```

The UI is a presentation layer over existing Python services. It does not call the CLI through
subprocesses or reproduce scientific formulas. Both entry points operate on local files and
preserve the source file bytes as evidence.

## Module responsibilities

- `contracts`: Pydantic models, enums, JSON serialization, and schema versions. It contains no
  scientific calculations.
- `ingestion`: read-only CSV/XLSX import, explicit column mappings, source values, source
  locations, file hashes, and bounded format handling.
- `profiling`: structural dataset profiles and reviewable QC issues. It does not silently clean,
  remove, impute, or normalize data.
- `assays`: assay-specific schema and mapping guidance; workflow selection remains explicit.
- `statistics`: confirmed grouped descriptions, declared experimental-unit Welch analysis,
  standard-only 4PL fitting, and per-measurement research-only ELISA inverse estimation.
- `visualization`: deterministic PNGs from completed structured results; it does not recompute
  statistics.
- `reporting`: validates upstream artifacts and renders DOCX/XLSX/JSON plus charts. It does not
  recalculate results or modify plans and input files.
- `audit`: manifest and provenance contracts used by each run.
- `batch`: reserved for future isolated multi-run orchestration; it is not a user-facing batch
  analysis workflow in the current pilot.
- `ai`: reserved for future optional work; no LLM or provider integration is currently included.
- `ui`: local Gradio interface, per-session artifact isolation, explicit user controls, and
  session-contained downloads.

## Current scientific boundaries

- `generic_grouped` descriptions summarize measurement rows and do not establish biological
  independence.
- Welch analysis accepts exactly two explicitly named groups and an explicit experimental-unit
  declaration. Independence is user-declared and is not verified by software.
- ELISA 4PL fitting uses a user-declared direction and standard rows only. A numerical fit does
  not validate a curve or assay.
- ELISA inverse estimation is per measurement, research-only, and limited to the positive observed
  standard concentration span. Out-of-span measurements remain unestimated.
- Technical repeats, unknown repeats, sample identity, and dilution settings are never inferred or
  silently aggregated.

## Data flow

```text
CSV/XLSX source bytes
  -> immutable input identity and SHA-256
  -> DatasetProfile + ValidationIssue records
  -> Phase 1 ImportResult
  -> explicit, unconfirmed AnalysisPlan
  -> preview and plan/warning review
  -> explicit SHA-256 confirmation
  -> deterministic structured result
  -> charts and report artifacts
  -> RunManifest with output hashes and status
```

An error or blocking QC issue prevents execution. Warnings and their source references remain
attached to the run. For the Gradio pilot, session data stays below
`outputs/ui-sessions/<session-id>/`; UI paths exposed to users are session-relative.

## Dependency direction

Dependencies point inward toward contracts. Ingestion, profiling, assays, statistics,
visualization, reporting, audit, batch, and UI may depend on contracts. Contracts do not depend on
these modules. Statistics may use declared numerical libraries inside calculation boundaries;
the UI and report renderer do not own or change the scientific formulas. No runtime provider,
database, telemetry, cloud, or network service is present.

## Future plugin boundary

If additional assay support is approved, an assay plugin should declare a stable identifier,
contract version, supported input schema, assumptions, and deterministic implementation version.
It may validate assay-specific fields, propose an unconfirmed plan, and execute only a confirmed
plan. This is a design boundary, not a claim that a general plugin registry exists today.

## Future AI boundary

No AI/LLM integration exists in the current release. Any future optional explanation adapter
would receive approved structured results only, produce clearly labeled narrative, and remain
unable to calculate statistics, remove data, or change conclusions. Core import, QC, analysis,
and reporting must remain usable without it.
