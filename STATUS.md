# Project status

- **Current phase:** Phase 4D — GitHub Public Release Preparation (uncommitted)
- **Phase 4B baseline:** `a9273a431488e1776eec00cb73653854ab0c9adf`
- **Phase 4C baseline:** `6c6a1f8f9d82d73bf9dd86ee7fd5d0bf74c8b8d0`
- **Completed:** Phase 0 `5456757`; Phase 1 `4bb5e06`; Phase 2A `1b5cd90`; Phase 2B `fe549c9`; Phase 3A `9280e0a`; Phase 3B `99a42974384258337b795435d605232a576f175e`; Phase 4A `8f232b340e354ff211cbfc7f953aaedf0c3aa280`; Phase 4B local UI and real-browser acceptance.
- **Current release version:** `0.1.0`, sourced from `src/biolab_copilot/__init__.py`; setuptools, UI, and report manifests use that value.
- **Current test result:** PASS — 82 tests passed; `ruff check .`, `mypy src`, and `git diff --check` pass after the current Phase 4D edits.
- **Phase 4C.1 work:** Report rendering now uses Python-only `openpyxl` and `python-docx`; the installer selects Python 3.11-3.13 with a preference for the verified 3.13 runtime, and installed wheels resolve the project root explicitly.
- **Confirmed safety:** UI remains local-only at `127.0.0.1:7860`, uses `share=False`, disables analytics, and does not add AI, LLM, provider, database, telemetry, cloud, or runtime network behavior.
- **Current runtime evidence:** Python 3.13 is verified on this host; Python 3.11 and 3.12 remain unverified. Installation may require network access unless dependencies are cached; runtime analysis and reporting are offline.
- **Report dependency boundary:** Report generation must use declared Python dependencies only and must not require Node, npm, artifact-tool, Codex runtime modules, or subprocesses.
- **Preserved item:** `tests/phase2a-boundaries-lliqpk1e/` is pre-existing and remains untouched and uncommitted.
- **Phase 4D scope:** Public README/release documentation, security/contribution guidance, GitHub Actions CI, and wheel/sdist content inspection only. No remote, push, tag, or scientific feature is authorized.
- **CI status:** Matrix configuration is planned for Python 3.11, 3.12, and 3.13. Only Python 3.13.9 has been verified on the current host.
- **Security review:** No credentials, private keys, email addresses, phone numbers, or credential assignments were found in the current public candidate or nine-commit history. The protected untracked boundary directory contains a pre-existing diagnostic JSON with a local path and remains untouched; an older Phase 4B renderer commit contains non-sensitive local-user redaction literals that are not rewritten.
- **Next step:** Run Phase 4D local quality, YAML, build, package-content, and security/history checks; keep all Phase 4D changes uncommitted.
- **Last updated:** 2026-09-19 (Asia/Shanghai)
- **Final state:** Phase 4D public release review in progress; Phase 4D changes remain uncommitted and unstaged.
