# Project status

- **Current phase:** Phase 2A — Generic grouped descriptive statistics and explicit analysis-plan confirmation
- **Completed:** Phase 0 baseline commit `5456757`; Phase 1 commit `4bb5e06`; read-only CSV and `.xlsx` readers; explicit experiment selection and column mapping; numeric/text parsing; structural QC; traceable import result; offline CLI; explicit Phase 2A plan binding and hash confirmation; deterministic measurement-row descriptive statistics; synthetic boundary tests; input-format, statistics, and decision documentation.
- **Current test result:** PASS — 37 pytest tests, `ruff check .`, `mypy src`, and `git diff --check` pass after the latest run. Phase 1 regression coverage remains passing.
- **Confirmed decisions:** `generic_grouped` requires `sample_id`, `group`, `measurement`; `elisa_standard_curve` requires `sample_id`, `sample_type`, `measurement`, with conditional standard concentration; repeat type is biological/technical/unknown and never inferred; source bytes and hashes are preserved; Phase 2A is `measurement_rows` only; `sample_sd` uses `ddof=1`; `independent_biological_n` remains null; duplicate and warning records are retained and require explicit confirmation when listed by the plan.
- **Unresolved questions:** Phase 2B inferential design, CV thresholds, ELISA 4PL/5PL selection, detection-range rules, and institutional privacy/retention policy remain unimplemented and require later review.
- **Next step:** Owner acceptance of the uncommitted Phase 2A changes. Do not enter Phase 2B automatically.
- **Last updated:** 2026-09-18 (Asia/Shanghai)
- **Final state:** `READY_FOR_PHASE_2B_INFERENTIAL_DESIGN` (Phase 2A changes remain uncommitted; Phase 2B has not started.)
