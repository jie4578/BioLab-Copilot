# Local pilot acceptance record

## Release identity

- Package version: `0.1.0`
- Version source: `src/biolab_copilot/__init__.py`, exposed to packaging through
  `tool.setuptools.dynamic`; UI and report manifests import the same value.
- Scope: local synthetic-data pilot only.

## Accepted workflows

The following workflows were exercised through the local Gradio UI with synthetic data:

- Generic grouped measurement-row descriptive statistics.
- Explicit two-group Welch analysis at experimental-unit level.
- Standard-only ELISA 4PL fitting with explicit direction.
- Research-only per-measurement ELISA 4PL inverse estimation with explicit dilution handling.

The browser acceptance also covered below/above positive-standard-span statuses, domain failures,
unconfirmed plans, stale confirmations, blocking QC, traversal rejection, session-relative
downloads, and report generation.

## Safety acceptance

- Server binding: `127.0.0.1:7860` only.
- Gradio public sharing: disabled.
- Analytics: disabled.
- Runtime AI, LLM SDK, provider, database, telemetry, and network features: absent.
- Source bytes and upstream artifacts: hash-bound and not overwritten by the UI.
- Downloads: limited to the current session directory.
- ELISA inverse: permanently labeled research-only; no validated quantification claim.
- Synthetic fixtures only; no company data, patient data, antibody sequence data, personal data,
  or secrets.

## Quality evidence

The Phase 4B acceptance run passed 79 tests. The current Phase 4C.1 source checks passed 82 tests,
`ruff check .`, `mypy src`, and `git diff --check`. A successful
local pilot review does not establish clinical validation, assay validation, or production
readiness.

## Known environment limits

- The supported range is Python 3.11 through 3.13. Python 3.13 is the current verified Windows
  runtime; Python 3.11 and 3.12 are not yet verified on the current host.
- Installation may need network access unless dependencies are cached. Runtime report generation
  uses declared `openpyxl`, `python-docx`, and matplotlib dependencies and does not require Node,
  npm, Codex runtime modules, or artifact-tool.
- The pilot has no authentication, multi-user retention, institutional access control, or remote
  deployment support.
