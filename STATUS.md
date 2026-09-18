# Project status

- **Current phase:** Phase 2B — Experimental design contract and restricted independent two-group Welch comparison
- **Completed:** Phase 0 baseline commit `5456757`; Phase 1 commit `4bb5e06`; Phase 2A baseline commit `1b5cd90`; read-only CSV and `.xlsx` readers; explicit mappings and structural QC; traceable import artifacts; measurement-row descriptive statistics; explicit two-group design contract; experimental-unit preview; `none` and explicit technical-repeat `mean` policies; plan/design/input/preview hash binding; deterministic SciPy Welch computation; synthetic unit and CLI tests.
- **Current test result:** PASS — 49 pytest tests, `ruff check .`, `mypy src`, and `git diff --check` pass; Phase 0, Phase 1, and Phase 2A regression coverage remains passing.
- **Confirmed decisions:** `generic_grouped` requires `sample_id`, `group`, and `measurement`; Phase 2B additionally requires an explicit `experimental_unit_id` mapping and user design declaration; independence is recorded as user-declared and not software-verified; `independent_biological_n` remains null; `sample_sd` uses `ddof=1`; technical repeats are only averaged under explicit `mean` policy with unique technical IDs; duplicate complete records block Phase 2B inference.
- **Unresolved questions:** Broader inferential methods, ELISA 4PL/5PL selection, detection-range rules, chart/report presentation, AI privacy policy, and institutional retention policy remain out of scope.
- **Next step:** Owner and scientific reviewer acceptance of the uncommitted Phase 2B changes. Do not enter ELISA, charts, AI, UI, or broader inferential work automatically.
- **Last updated:** 2026-09-18 (Asia/Shanghai)
- **Final state:** `READY_FOR_PHASE_2B_REVIEW` (Phase 2B changes remain uncommitted.)
