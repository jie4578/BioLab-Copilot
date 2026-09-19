# Changelog

All notable changes are recorded here. This project follows a small, local pilot release
sequence; entries do not imply clinical validation or production readiness.

## [0.1.0] - 2026-09-19

### Added

- Local-first Gradio pilot UI for explicit import, structural QC, confirmed analysis plans,
  deterministic results, and report downloads.
- Generic grouped descriptive statistics, two-group Welch analysis, standard-only ELISA 4PL
  diagnostics, and research-only per-measurement ELISA inverse estimation through the UI.
- Windows setup and startup scripts, synthetic demo guidance, installation guidance, and pilot
  acceptance documentation.
- Portable Python-only Word/Excel report rendering with direct `python-docx` and `openpyxl`
  dependencies; no runtime Node, npm, artifact-tool, Codex runtime, or subprocess dependency.
- Python support metadata now allows 3.11-3.13; Python 3.13 is the current verified Windows
  runtime and Python 3.11/3.12 remain unverified on this host.

### Safety and scope

- No AI, LLM, database, cloud service, telemetry, or runtime network feature was added.
- ELISA inverse estimates remain research-only; no validated quantification claim is made.
- This release is for local pilot evaluation and is not production-ready or clinically validated.
