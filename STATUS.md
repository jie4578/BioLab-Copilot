# Project status

- **Current phase:** Phase 5A — Public Showcase; implementation complete and awaiting review.
- **Baseline:** `main` and `origin/main` were both `28c054396983f1b74d46fed63b7dd318b0d985c7` at phase start. This work is on `docs/public-showcase`.
- **Release:** `v0.1.0` is the current release. The package version comes from `src/biolab_copilot/__init__.py`.
- **Implemented workflows:** Generic grouped measurement-row descriptions; explicit two-group experimental-unit Welch analysis; standard-only ELISA 4PL fitting; per-measurement research-only ELISA inverse estimates.
- **Scientific boundary:** No Phase 5A statistical implementation changes are permitted. ELISA inverse output remains research-only, does not extrapolate, and does not enable validated quantification.
- **Runtime:** The UI is local-only at `127.0.0.1:7860`; Python 3.13.9 is verified on this host. The CI configuration targets Python 3.11, 3.12, and 3.13; consult GitHub Actions for current job results.
- **Dependency compatibility:** Phase 4E.1 bounds NumPy to `>=2.0,<2.5` while preserving `requires-python >=3.11,<3.14` and mypy's Python 3.11 target.
- **Phase 5A checks:** 88 pytest tests passed; `ruff check .`, `mypy src`, and `git diff --check` passed after the documentation, synthetic fixture, and genuine screenshot updates.
- **Synthetic inverse fixture:** `examples/phase3b_inverse_boundary.csv` is fabricated from the documented increasing 4PL form. It includes one within-span, one below-span, and one above-span response.
- **Browser asset status:** Playwright drove installed Microsoft Edge against the real local Gradio UI. Generic grouped, Welch, ELISA 4PL, and ELISA inverse workflows completed with explicit mapping, plan generation, SHA-256 confirmation, execution, report generation, and download-scope validation where applicable.
- **Screenshot status:** Seven privacy-reviewed PNGs are present in `docs/images/`. The home image hides the ephemeral session ID; result and report images contain no user name, local absolute path, credential, or real experiment data.
- **Synthetic acceptance evidence:** Generic means were 1.0 and 1.445; Welch produced mean difference -3, t -3.6742346141747673, df 4, p 0.021311641128756727, and CI [-5.266957935527524, -0.7330420644724769]; 4PL recovered L/U/C/B approximately 0.1/2.1/10/1 with validation flags false; inverse retained one within-span estimate and two out-of-span null results.
- **Preserved item:** `tests/phase2a-boundaries-lliqpk1e/` remains the pre-existing untracked directory and has not been changed, staged, or committed.
- **Git restrictions:** Phase 5A changes remain unstaged and uncommitted on `docs/public-showcase`; no push, tag, or Release is part of this phase.
- **Last updated:** 2026-09-23 (Asia/Shanghai)
- **Final state:** `READY_FOR_PHASE_5A_REVIEW` after final quality checks.
