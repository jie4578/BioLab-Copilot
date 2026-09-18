# Project status

- **Current phase:** Phase 3A — ELISA standard-only 4PL fitting and diagnostics
- **Completed:** Phase 0 baseline `5456757`; Phase 1 `4bb5e06`; Phase 2A `1b5cd90`; Phase 2B baseline `fe549c9`; read-only CSV/XLSX import; structural QC; confirmed generic grouped descriptions; explicit experimental-unit Welch analysis; explicit ELISA 4PL design, standard preview, deterministic multi-start fitting, diagnostics, and offline CLI.
- **Current test result:** PASS — 62 pytest tests, `ruff check .`, and `mypy src` pass after the Phase 3A implementation. `git diff --check` is run as the final gate.
- **Confirmed decisions:** Phase 3A accepts only `elisa_standard_curve`; the user explicitly declares one curve context, units, direction, and replicate policy. Only standard rows enter the fit. Sample, blank, and control rows are preserved and excluded. The 4PL uses stable log/`expit` evaluation, float64 SciPy least-squares, deterministic bounded multi-starts, raw-response unweighted linear loss, and no model/direction fallback. Six positive concentration levels are an engineering precondition, not scientific validation.
- **4PL status semantics:** A computed numerical candidate is not a validated assay curve. Every successful result contains `curve_validated=false` and `quantification_enabled=false`; no unknown-sample concentration is produced.
- **Unresolved questions:** Unknown-sample back-calculation, 5PL selection, blank/normalization rules, detection/quantification range validation, chart/report presentation, AI privacy policy, and institutional retention remain out of scope.
- **Next step:** Owner and scientific reviewer acceptance of the uncommitted Phase 3A changes. Do not enter unknown-sample fitting, 5PL, charts, reports, AI, or UI automatically.
- **Last updated:** 2026-09-18 (Asia/Shanghai)
- **Final state:** `READY_FOR_PHASE_3A_REVIEW` (Phase 3A changes remain uncommitted.)
