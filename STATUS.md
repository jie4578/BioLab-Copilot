# Project status

- **Current phase:** Phase 4C — Local Pilot Release Hardening (uncommitted)
- **Phase 4B baseline:** `a9273a431488e1776eec00cb73653854ab0c9adf`
- **Completed:** Phase 0 `5456757`; Phase 1 `4bb5e06`; Phase 2A `1b5cd90`; Phase 2B `fe549c9`; Phase 3A `9280e0a`; Phase 3B `99a42974384258337b795435d605232a576f175e`; Phase 4A `8f232b340e354ff211cbfc7f953aaedf0c3aa280`; Phase 4B local UI and real-browser acceptance.
- **Current release version:** `0.1.0`, sourced from `src/biolab_copilot/__init__.py`; setuptools, UI, and report manifests use that value.
- **Current test result:** PASS — 82 tests passed; `ruff check .`, `mypy src`, and `git diff --check` passed.
- **Phase 4C.1 work:** Report rendering now uses Python-only `openpyxl` and `python-docx`; the installer selects Python 3.11-3.13 with a preference for the verified 3.13 runtime, and installed wheels resolve the project root explicitly.
- **Confirmed safety:** UI remains local-only at `127.0.0.1:7860`, uses `share=False`, disables analytics, and does not add AI, LLM, provider, database, telemetry, cloud, or runtime network behavior.
- **Current runtime evidence:** Python 3.13 is verified on this host; Python 3.11 and 3.12 remain unverified. Installation may require network access unless dependencies are cached; runtime analysis and reporting are offline.
- **Report dependency boundary:** Report generation must use declared Python dependencies only and must not require Node, npm, artifact-tool, Codex runtime modules, or subprocesses.
- **Preserved item:** `tests/phase2a-boundaries-lliqpk1e/` is pre-existing and remains untouched and uncommitted.
- **Next step:** Review the Python 3.13 wheel-isolation report and UI acceptance evidence; keep Phase 4C/4C.1 changes uncommitted.
- **Last updated:** 2026-09-19 (Asia/Shanghai)
- **Final state:** Phase 4C release review in progress; Phase 4C changes remain uncommitted and unstaged.
