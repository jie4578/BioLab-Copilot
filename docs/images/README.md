# Public UI screenshots and recapture checklist

This folder contains genuine captures made from the running local BioLab Copilot UI. They were
captured on 2026-09-23 with Playwright driving the installed Microsoft Edge browser against
`http://127.0.0.1:7860`. The automation selected files directly on the browser file input and then
used the visible UI controls for mapping, QC, plan generation, SHA-256 confirmation, execution,
report generation, and download validation.

No interface content was drawn, synthesized, composited, or retouched. Only the fabricated inputs
listed below were used. Browser chrome was excluded, the ephemeral session identifier was hidden
for the home capture, and every image was reviewed for local paths, user names, secrets, and
non-synthetic data.

## Capture setup

1. Install the declared project dependencies if needed, then start with `start_local.bat`.
2. Open `http://127.0.0.1:7860` in a browser at 100% zoom with a viewport near 1280×720 or
   1440×900.
3. Capture only the browser content area. Do not include the desktop, terminal, browser tabs,
   bookmarks, account/avatar, operating-system file paths, or real user data.
4. Inspect the image at readable size. Remove the capture if any local path, user name, personal
   information, credential, or non-synthetic value appears.

## Required captures

| File | UI state and synthetic input | What must be visible |
| --- | --- | --- |
| `ui-overview.png` | Home tab; no file upload needed | Product name, four workflows, local-only status, and research-use statement. Crop out the ephemeral session identifier. |
| `generic-result.png` | Generic grouped workflow with `examples/generic_grouped_normal.csv` | QC/profile summary and descriptive results; keep all values visibly synthetic. |
| `welch-result.png` | Welch workflow with `examples/phase4a_welch.csv` | Groups A/B, mean difference, t, df, p value, and 95% CI; show the user-declared independence caveat if it fits. |
| `elisa-4pl-result.png` | 4PL workflow with `examples/phase3a_increasing.csv` | Fitted parameters and `curve_validated=false` / `quantification_enabled=false`. |
| `elisa-4pl-report.png` | ELISA report tab after fitting and research-only inverse execution | Session-relative DOCX/XLSX/JSON/manifest paths and the real curve, residual, and sample-status PNG artifact names. |
| `elisa-inverse-boundary.png` | Inverse workflow with `examples/phase3b_inverse_boundary.csv` | One within-span estimate plus below/above-span rows with null concentration values and `intended_use=research_only`. |
| `report-downloads.png` | Report tab after generating a report in the current session | Meaningful report filenames and session-relative download paths only. |

The UI shows analysis results and report downloads on separate tabs. It does not embed the 4PL
chart in the analysis-result view; `elisa-4pl-report.png` therefore shows the genuine report
download area and the generated chart filenames rather than compositing charts into the result
screen.

## Workflow details for capture

### Generic grouped

- Select `generic_grouped` and `examples/generic_grouped_normal.csv`.
- Map `sample_id -> sample_id`, `group -> group`, `measurement -> measurement`, and
  `replicate -> replicate_id`.
- Import, review the profile and unknown-repeat warning, generate the Generic grouped plan,
  review and confirm its displayed SHA-256, execute, then capture the results tab.
- Expected: control mean `1.0` (`n_measurements=2`); treatment mean approximately `1.445`
  (`n_measurements=2`); `independent_biological_n=null`.
- Generate a Generic grouped report and capture `report-downloads.png` on the report tab.

### Welch

- Select `generic_grouped`, upload `examples/phase4a_welch.csv`, and paste
  `examples/phase4a_welch_mapping.json` as the mapping.
- Paste `examples/phase2b_design.json` into the design field. The file explicitly declares the
  two groups, `experimental_unit_id`, repeat policy, and assumptions.
- Review the experimental-unit preview, plan and warning list; confirm the exact displayed plan
  hash and execute.
- Expected: mean difference `-3`, t approximately `-3.6742`, df `4`, p approximately `0.02131`,
  and 95% CI approximately `[-5.267,-0.733]`.

### ELISA 4PL

- Select `elisa_standard_curve`, upload `examples/phase3a_increasing.csv`, and paste
  `examples/phase3a_mapping.json` as the mapping.
- Paste `examples/phase3a_design_increasing.json` as the design. Review that the direction is
  explicitly increasing and the standard replicate policy is `none`.
- Confirm the displayed plan hash and execute. Capture the fitted parameters and the explicit
  non-validation labels. The generated curve PNG may be reviewed separately as a report artifact;
  it is not an embedded UI panel.

### ELISA research-only inverse boundary

- Select `elisa_standard_curve`, upload `examples/phase3b_inverse_boundary.csv`, and use the same
  mapping and increasing 4PL design listed above.
- Fit the standards first and keep the curve run ID. For inverse estimation, select the inverse
  workflow, enter that run ID, and paste `examples/phase3b_inverse_design.json`.
- The synthetic design explicitly acknowledges `research_only` and uses a uniform dilution
  factor of `1`; this means explicitly undiluted for the fixture, not a software default.
- Generate the inverse plan, review warnings and SHA-256, confirm, execute, and capture the
  per-record statuses. Confirm both out-of-span concentration fields are JSON `null`.

## Final review

- Open every PNG after capture and check legibility and privacy.
- Confirm the 4PL and inverse images preserve `curve_validated=false`,
  `validated_quantification_enabled=false`, and `intended_use=research_only` where applicable.
- Confirm there are no outputs from `outputs/`, downloaded reports, or user-uploaded files in the
  Git change list. Only the reviewed PNG files belong in this directory.

## Captured asset review

- `ui-overview.png`: 1440×900; session identifier hidden; local-only and research-use statements
  visible.
- `generic-result.png`: 1440×1080; both fabricated groups, measurement counts, means, medians,
  ranges, and sample SD values visible.
- `welch-result.png`: 1440×900; groups, method, mean difference, confidence interval, t, df, p,
  and the user-declared independence warning visible.
- `elisa-4pl-result.png`: 1440×1080; four fitted parameters, diagnostics, and both non-validation
  flags visible.
- `elisa-inverse-boundary.png`: 1440×2600; research-only flags plus all three fabricated sample
  rows, including null concentrations for below/above-span results, visible.
- `elisa-4pl-report.png` and `report-downloads.png`: 1440×900; only session-relative report paths
  and meaningful artifact names visible.
