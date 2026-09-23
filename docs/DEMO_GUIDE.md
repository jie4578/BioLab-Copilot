# Synthetic local pilot demo

This 3–5 minute walkthrough uses only fabricated inputs under `examples/`. It is a software
demonstration, not experimental evidence. Start the application with `start_local.bat` and open
`http://127.0.0.1:7860`.

## Before the demo

- Install once with `setup_windows.bat`; launch with `start_local.bat`.
- Keep each workflow's experiment type, source-to-canonical mapping, design declaration, QC
  issues, and plan SHA-256 visible for review.
- Confirm only warnings that have been read and understood. A generated plan is not confirmed.
- Use only the committed synthetic files below. Expected values are illustrative fixture checks,
  not biological findings.

## 3–5 minute walkthrough

### 1. Home and scope

Show the version, local address, four workflow names, and research-use notice on the Home tab.
Explain that the UI calls deterministic Python workflows and does not send data to a cloud
service or AI provider.

### 2. Generic grouped descriptive statistics

- File: `examples/generic_grouped_normal.csv`
- Experiment type: `generic_grouped`
- Mapping JSON:
  `{"sample_id":"sample_id","group":"group","measurement":"measurement","replicate":"replicate_id"}`
- Workflow: **Generic grouped 描述统计**; no separate design JSON is required.
- Review the original and parsed values, source locations, DatasetProfile, and any unknown-repeat
  warning. Generate the plan, review its SHA-256, confirm the displayed plan explicitly, and run.
- Expected: `control` has two measurement rows with mean `1.0`; `treatment` has two rows with
  mean approximately `1.445`. `independent_biological_n` remains null.
- Generate a Generic grouped report and show its session-relative download items.

### 3. Declared experimental-unit Welch analysis

- File: `examples/phase4a_welch.csv`
- Experiment type: `generic_grouped`
- Paste the mapping from `examples/phase4a_welch_mapping.json`.
- Workflow: **Welch 两组分析**; paste the explicit design from
  `examples/phase2b_design.json`.
- Review the experimental-unit preview, group names, assumptions, warning confirmations, and
  plan SHA-256 before confirming and executing.
- Expected synthetic groups: A=`[1,2,3]`, B=`[4,5,6]`; mean difference `-3`, t approximately
  `-3.6742`, df `4`, two-sided p approximately `0.02131`, and 95% CI approximately
  `[-5.267,-0.733]`. The software records independence as user-declared, not verified.
- Generate a Welch report.

### 4. ELISA standard-only 4PL

- File: `examples/phase3a_increasing.csv`
- Experiment type: `elisa_standard_curve`
- Paste the mapping from `examples/phase3a_mapping.json`.
- Workflow: **ELISA 4PL 标准曲线拟合**; paste
  `examples/phase3a_design_increasing.json`.
- Review the standard inclusion preview and confirm the plan SHA-256. Generate and execute the
  fit, then render the ELISA report.
- Expected: an increasing 4PL curve with parameters near L=`0.1`, U=`2.1`, C=`10`, B=`1`;
  the result must retain `curve_validated=false` and `quantification_enabled=false`. Sample rows
  remain visible but are excluded from standard fitting.

### 5. ELISA research-only inverse boundary

- File: `examples/phase3b_inverse_boundary.csv`
- Experiment type: `elisa_standard_curve`
- Use the mapping from `examples/phase3a_mapping.json` and increasing curve design from
  `examples/phase3a_design_increasing.json`.
- First fit the standards in this file. In the **ELISA research-only 浓度反算** workflow, select
  the resulting curve run ID, paste `examples/phase3b_inverse_design.json`, and explicitly
  acknowledge research-only use and the configured dilution factor (`1` means explicitly
  undiluted in this synthetic example).
- Generate and review the inverse plan, confirm its SHA-256, then execute.
- Expected statuses: `SYN-IN-SPAN` is within the standard span; `SYN-BELOW-SPAN` and
  `SYN-ABOVE-SPAN` have null concentration fields with below/above-span statuses. No extrapolated
  concentration is produced. The result remains `intended_use=research_only` and
  `validated_quantification_enabled=false`.
- Generate the ELISA report with the inverse run ID as its optional source.

### 6. Close with provenance

Point out the source SHA-256, plan confirmation, run status, warnings, software version, and
artifact hashes in the generated files. Explain that installation may need network access when
dependencies are not cached; analysis and reporting run locally after installation.

## 60-second project introduction

> BioLab Copilot is a local-first, research-use workbench for laboratory CSV and Excel data. It
> makes the analysis path reviewable: users map columns explicitly, inspect structural QC, review
> and confirm a hash-bound plan, then run deterministic Python analysis and create traceable
> reports. The current pilot supports grouped descriptions, a declared two-group Welch test,
> standard-only ELISA 4PL fitting, and research-only inverse estimates inside the observed
> standard span. It preserves raw input identity, records warnings and hashes, and does not use
> an LLM to calculate results. It is an early research-use tool, not validated bioanalysis or
> clinical software.

## Screenshot capture notes

Use the task list in [docs/images/README.md](images/README.md). The current UI presents analysis
results and report downloads on separate tabs; the 4PL chart is a generated PNG report artifact
and is not rendered inline by the UI. Do not combine views or fabricate a chart screenshot to
make them appear on one page.
