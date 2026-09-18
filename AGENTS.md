# BioLab Copilot agent and contributor rules

## Project principles

- Keep the system local-first, deterministic, inspectable, and traceable.
- Treat every source file as immutable evidence. Preserve the original bytes and record a SHA-256 hash.
- Profile and flag anomalies; never silently delete, overwrite, impute, or normalize scientific data.
- Generate all scientific numbers with deterministic Python code. Future language models may explain structured results but may not calculate, remove data, or change conclusions.
- Keep scientific computation independent from UI, AI providers, and report rendering.
- Prefer MIT- or Apache-2.0-compatible dependencies and do not copy GPL or AGPL code.
- Keep source code and user documentation in English. Future UI localization may add Chinese support.

## Forbidden behavior

- Do not access files outside the current project directory.
- Do not connect to or copy from Antibody AI Research Assistant.
- Do not use company data, real antibody sequences, personal information, or API keys.
- Do not make network requests in Phase 0.
- Do not add LangChain, a database, Gradio, an LLM SDK, or a formal UI in Phase 0.
- Do not commit or push unless the project owner explicitly authorizes it.
- Do not use an LLM to execute arbitrary statistical code.
- Do not silently modify scientific data or hide warnings.

## Development commands

From the repository root on Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,templates]"
python -m pytest -q
ruff check .
mypy src
```

Phase 0 does not require network access after dependencies are available locally. The XLSX template script is optional and requires the `templates` extra:

```powershell
python scripts\generate_xlsx_templates.py
```

## Testing requirements

- Add or update tests with every contract change.
- Test JSON round trips, JSON Schema presence, invalid fields, and forbidden extra fields.
- Scientific tests must use synthetic fixtures and verify deterministic outputs.
- Run all three quality commands before declaring a phase complete.
- If any test or quality check fails, fix the cause and rerun it. Never delete tests, weaken strictness, or add an unsupported ignore to obtain PASS.

## Phase gates and stop rules

- Work only within the phase explicitly authorized by the project owner.
- At the end of each phase, report scope, tests, warnings, and open decisions, then stop.
- Do not enter the next phase after a failed test or quality check.
- Stop and ask the project owner when a scientific rule or architectural choice would materially change the design.
- Phase 0 ends with contracts, documentation, synthetic examples, and tooling only. It must not implement ingestion, profiling, QC, statistics, fitting, charts, AI, reports, or formal UI.

## Phase 1 implementation boundary

- Phase 1 may implement read-only CSV/XLSX ingestion, explicit mappings, type parsing, structural QC, traceable JSON artifacts, and an offline CLI.
- Phase 1 must not implement statistical tests, CV calculations, outlier detection or deletion, curve fitting, charts, AI/API calls, Word reports, databases, network behavior, or formal UI.
- Keep raw source values and parsed values side by side with source locations. `analysis_ready=false` whenever an error or blocking issue exists.
- Preserve biological, technical, and unknown repeat types. Never infer pairing, independence, sample size, units, or aggregate observations.
