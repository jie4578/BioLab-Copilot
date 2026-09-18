# Project status

- **Current phase:** Phase 1 — Read-only CSV/XLSX ingestion and structural QC
- **Completed:** Phase 0 baseline commit `5456757`; read-only CSV and `.xlsx` readers; explicit experiment selection and column mapping; numeric/text parsing; structural QC; traceable import result; offline CLI; synthetic boundary tests; input-format and decision documentation.
- **Current test result:** PASS — 22 pytest tests, `ruff check .`, `mypy src`, and `git diff --check` all pass. Manual CLI acceptance is recorded in the final handoff.
- **Confirmed decisions:** `generic_grouped` requires `sample_id`, `group`, `measurement`; `elisa_standard_curve` requires `sample_id`, `sample_type`, `measurement`, with conditional standard concentration; repeat type is biological/technical/unknown and never inferred; source bytes and hashes are preserved; Phase 2 statistics are not implemented.
- **Unresolved questions:** Statistical tests, CV thresholds, ELISA 4PL/5PL selection, detection-range rules, and institutional privacy/retention policy remain Phase 2+ decisions.
- **Next step:** Owner acceptance of the uncommitted Phase 1 changes. Do not enter Phase 2 automatically.
- **Last updated:** 2026-09-18 (Asia/Shanghai)
- **Final state:** `READY_FOR_PHASE_2_GENERIC_STATS` (Phase 1 changes remain uncommitted; Phase 2 has not started.)
