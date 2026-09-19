# Phase 4A Reporting Definitions

## Scope

Phase 4A is a deterministic presentation boundary. It converts completed structured artifacts
into reviewable PNG, JSON, DOCX, and XLSX files. It does not recalculate a statistic, refit an
ELISA curve, change an analysis plan, or modify any source or upstream run artifact.

The report commands accept only project-local run directories with a completed or explicitly
partial upstream manifest, matching schema version, confirmed plan, valid artifact hashes, and
the expected assay and analysis level:

- `render-generic-report`: Phase 2A `generic_grouped`, `measurement_rows`.
- `render-welch-report`: Phase 2B `generic_grouped`, `experimental_units`, `welch_t`, two-sided.
- `render-elisa-report`: Phase 3A `elisa_standard_curve`, `standard_curve_levels`, with an
  optional separately validated Phase 3B research-only inverse run.

The report output directory must not already exist. This prevents a new report from silently
overwriting an older report package.

## Chart definitions

Charts use a fixed Matplotlib Agg backend, fixed figure size/DPI, fixed palette, and explicit
axis labels. They consume values already present in the structured result:

- Generic grouped: every measurement row plus group mean and sample SD. The footnote states that
  measurement-row counts are not independent biological sample counts.
- Welch: experimental-unit values plus group mean and sample SD. Technical repeats are not
  redrawn as inferentially independent points.
- ELISA: raw standard records, fitted 4PL curve, concentration-level fit points, residuals, and
  optional research-only sample status counts. The curve plot uses a logarithmic positive-
  concentration axis; zero concentration remains in tables and is not placed on that axis.

The ELISA chart displays the existing Phase 3A fit and does not call an optimizer. The optional
sample status chart summarizes existing Phase 3B statuses and does not create concentration
values.

## JSON report data

`report_data.json` is the canonical presentation input. It contains report type and version,
human-readable scope, structured methods, upstream warnings, result values, chart paths, source
hash descriptors, and limitations. Numeric values are serialized with strict JSON settings;
`NaN` and `Infinity` are rejected. Missing scientific values remain JSON `null` and are shown as
“Not calculated” in Word tables.

The report manifest records source manifest hashes, source artifact hashes by role, software
versions, configuration, output-relative paths, output hashes, warnings, and report creation
time. It intentionally does not include its own hash, avoiding a self-reference cycle. Source
absolute paths are never copied into the report package.

## Word report

The DOCX template has fixed styles and sections: Purpose and Scope, Data and Analysis Sources,
QC and Warning Summary, Confirmed Methods, Results, Charts, Limitations and Prohibited
Interpretations, and Traceability. Tables use explicit headers and visible borders. Core metadata
uses the project name and fixed content timestamps; no external relationships or linked files are
created. The report is reopened with `python-docx` during acceptance checks.

## Excel report

The XLSX template is authored directly with the declared `openpyxl` Python dependency and
contains values only. It has no formulas, macros, external links, or hidden calculation
dependency. Every report has
Summary, Provenance, Issues, and Methods sheets. Additional sheets are selected by report type:

- Generic: Group Statistics and Measurements.
- Welch: Group Statistics, Experimental Units, Comparison, and Technical Source Records.
- ELISA: Curve Parameters, Standard Levels, Raw Standards, Residuals, Sample Estimates, and
  Sample Status Summary.

Sheets use fixed names, readable widths, frozen headers, and tables. No workbook recalculation is
needed because the report contains already-computed values and no formulas. The saved workbook is
reopened with `openpyxl` and inspected for formulas, macros, and external links.

## Failure and interpretation rules

An upstream hash mismatch, changed plan, unconfirmed plan, unsupported schema, wrong assay/level,
invalid validation semantics, or unsafe output path blocks rendering. The CLI returns a nonzero
diagnostic status and must not publish a `COMPLETED` report manifest. A report being rendered
successfully means only that the structured artifacts passed presentation-boundary validation.
It does not establish experimental-unit independence, statistical adequacy, assay validation,
accuracy, precision, matrix compatibility, or a validated quantification range.

Phase 4A does not create PDFs, AI interpretation, UI state, databases, network requests, or new
scientific calculations.
