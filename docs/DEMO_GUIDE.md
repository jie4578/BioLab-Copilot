# Synthetic local pilot demo guide

This guide uses only synthetic files committed under `examples/`. It is not a research result and
must not be presented as one. Start the UI with `start_local.bat`, then open
`http://127.0.0.1:7860`.

The current verified Windows runtime is Python 3.13. The project metadata allows Python 3.11-3.13,
but Python 3.11 and 3.12 are not yet verified on the current host. First-time dependency
installation may require network access unless packages are cached. Runtime analysis and report
generation are local and use declared Python dependencies (`openpyxl`, `python-docx`, and
matplotlib); no Node, artifact-tool, AI, or cloud service is required.

## Common interaction pattern

1. Open **导入与结构 QC**.
2. Select the experiment type explicitly.
3. Select the CSV file and paste the exact source-to-canonical mapping.
4. Run import/QC and review the DatasetProfile and every issue.
5. Open **计划、确认与执行**, select the workflow, and generate the unconfirmed plan.
6. Review the plan, preview, warning codes, and displayed SHA-256. Confirm only the listed
   warnings that have been reviewed, check the explicit confirmation box, then confirm the plan.
7. Execute and verify the result status before opening **报告与下载**.
8. Generate a report and download only the displayed session-relative path.

The UI must never infer assay type, mapping, experimental units, independence, dilution, or
replicate semantics.

## 1. Generic grouped descriptive statistics

- File: `examples/generic_grouped_normal.csv`
- Experiment type: `Generic grouped`
- Mapping:

```json
{"sample_id":"sample_id","group":"group","measurement":"measurement","replicate":"replicate_id"}
```

- Workflow: `Generic grouped 描述统计`
- Design JSON: not used by this workflow.
- Expected QC: ready, with an explicit unknown-repeat warning.
- Expected result: `control` has two measurement rows with mean `1.0`; `treatment` has two rows
  with mean approximately `1.445`. `independent_biological_n` remains `null`.
- Report type: `Generic grouped`.

## 2. Welch two-group analysis

- File: `examples/phase4a_welch.csv`
- Experiment type: `Generic grouped`
- Mapping: paste the contents of `examples/phase4a_welch_mapping.json`.
- Workflow: `Welch 两组分析`
- Design JSON: paste the contents of `examples/phase2b_design.json`.
- Expected result: groups A and B have values `[1,2,3]` and `[4,5,6]`; mean difference is `-3`,
  t is approximately `-3.6742`, df is `4`, p is approximately `0.02131`, and the 95% CI is
  approximately `[-5.267, -0.733]`.
- Report type: `Welch two-group`.

## 3. ELISA standard-only 4PL

- File: `examples/phase3a_increasing.csv`.
- Experiment type: `ELISA standard curve`.
- Mapping: paste the contents of `examples/phase3a_mapping.json`.
- Workflow: `ELISA 4PL 标准曲线拟合`.
- Design JSON: paste the contents of `examples/phase3a_design_increasing.json`.
- Expected result: increasing curve with parameters close to L=`0.1`, U=`2.1`, C=`10`, B=`1`.
  The result must display `curve_validated=false` and
  `quantification_enabled=false`. Sample rows are retained but not fitted.
- Report type: `ELISA 4PL`.

## 4. ELISA research-only inverse

- File: `examples/phase3a_increasing.csv`.
- Experiment type: `ELISA standard curve`.
- Mapping: paste the contents of `examples/phase3a_mapping.json`.
- First run the 4PL workflow above and keep its run ID.
- Workflow: `ELISA research-only 浓度反算`.
- Design JSON: paste the contents of `examples/phase3b_inverse_design.json` and set the
  current 4PL run ID explicitly in the dedicated field.
- Expected result: `intended_use=research_only`,
  `research_only_acknowledged=true`,
  `validated_quantification_enabled=false`, and a per-measurement estimate for the synthetic
  sample. No CV, SD, repeat aggregation, extrapolation, or validated quantification statement is
  produced.
- Report type: `ELISA 4PL`; provide the inverse run ID as the optional inverse source.

## Negative-path demo

Use `examples/generic_grouped_missing.csv` or `examples/columns_messy.csv` with an intentionally
incomplete mapping. QC must show an error or blocking issue, and the execute button must not
produce a successful analysis. A changed input or plan invalidates the previous confirmation.
