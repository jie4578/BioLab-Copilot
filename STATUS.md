# Project status

- **Current phase:** Phase 3B — research-only unknown-sample 4PL inverse and dilution correction
- **Completed:** Phase 0 baseline `5456757`; Phase 1 `4bb5e06`; Phase 2A `1b5cd90`; Phase 2B baseline `fe549c9`; Phase 3A baseline `9280e0a`; read-only CSV/XLSX import; structural QC; confirmed generic grouped descriptions; explicit experimental-unit Welch analysis; standard-only ELISA 4PL design, fit, and diagnostics; research-only per-measurement inverse contracts and offline CLI.
- **Current test result:** PASS — 71 pytest tests, `ruff check .`, `mypy src`, and `git diff --check` pass. Tests cover independent increasing/decreasing rational values, protected domain and span handling, explicit dilution, row preservation, stale confirmation, and import-to-fit-to-inverse CLI flows.
- **Confirmed decisions:** Phase 3B accepts only unchanged, converged Phase 3A 4PL artifacts without severe numerical diagnostics. It processes only `sample` rows independently, requires explicit research-use/context/dilution declarations, refuses extrapolation, and preserves `curve_validated=false` and `validated_quantification_enabled=false`.
- **Research-only status semantics:** A numerical inverse estimate does not validate an assay, its accuracy, precision, matrix compatibility, experimental design, or quantification range. Unknown repeat rows are not aggregated and no biological sample count is inferred.
- **Unresolved questions:** 5PL selection, blank/normalization rules, LOD/LLOQ/ULOQ, validated range, chart/report presentation, AI privacy policy, and institutional retention remain out of scope.
- **Next step:** Owner and scientific reviewer acceptance of the uncommitted Phase 3B changes. Do not enter charts, reports, AI, UI, or validation claims automatically.
- **Last updated:** 2026-09-18 (Asia/Shanghai)
- **Final state:** `READY_FOR_PHASE_3B_REVIEW` only after all final checks pass; Phase 3B changes remain uncommitted.
