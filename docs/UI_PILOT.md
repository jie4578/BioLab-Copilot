# Local UI pilot

Phase 4B exposes the existing deterministic workflows through a small Gradio surface. It is a
local presentation boundary, not a new scientific engine.

## Workflow states

The interface separates these states:

1. **Import completed** — the source was copied into the session and its bytes were read without
   mutation.
2. **QC reviewed** — `DatasetProfile` and every `ValidationIssue` are visible. Any error or
   blocking issue prevents analysis execution.
3. **Plan generated** — the plan and any unit/standard/sample preview are unconfirmed.
4. **Plan confirmed** — the user explicitly confirms the displayed plan SHA-256 and each listed
   warning. Confirmation is re-hashed after the confirmation fields are persisted.
5. **Analysis executed** — the existing backend revalidates input, plan, design, and preview
   bindings before calculating.
6. **Report generated** — the existing Phase 4A renderer creates a new report package from the
   completed run without recalculating it.

## Session and download boundary

Each process-created session uses `outputs/ui-sessions/<session-id>/`. Source copies, import
artifacts, plans, analysis runs, and reports remain below that directory. Displayed paths are
session-relative; absolute machine paths are not shown to the user. Downloads reject absolute
paths, `..` traversal, symlink escapes, missing files, and files outside the active session.

## Explicitness and safety

The UI does not infer assay type, worksheet, mapping, experimental units, independence, pairing,
dilution, or replicate type. It calls the existing Python functions directly and never invokes
the CLI through a subprocess. ELISA inverse estimates retain `research_only` semantics. The
server is bound to `127.0.0.1`, with `share=False` and analytics disabled; no provider, API,
database, telemetry, or external network service is created.

The pilot does not provide authentication, multi-user retention, institutional access control,
or a claim of production readiness. Browser automation is an optional environment-level smoke
check; service-layer tests remain the authoritative offline safety tests.
