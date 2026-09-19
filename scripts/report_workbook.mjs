import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [dataPath, outputPath, chartDir, qaDir] = process.argv.slice(2);
if (!dataPath || !outputPath || !chartDir) {
  throw new Error("Usage: report_workbook.mjs report_data.json report.xlsx charts [qa_dir]");
}

const data = JSON.parse(await fs.readFile(dataPath, "utf8"));
const workbook = Workbook.create();
const NAVY = "#1F4E78";
const LIGHT_BLUE = "#D9E2F3";
const LIGHT_GRAY = "#F2F2F2";
const BORDER = "#D9D9D9";
const FONT = "Arial";

const labels = {
  analysis_level: "Analysis level",
  source_filename: "Source filename",
  source_sha256: "Source SHA-256",
  input_artifact_sha256: "Input artifact SHA-256",
  upstream_run_id: "Upstream run ID",
  upstream_manifest_sha256: "Upstream manifest SHA-256",
  independent_biological_n: "Independent biological n",
  n_measurements: "Measurement rows",
  n_experimental_units: "Experimental units",
  sample_sd: "Sample SD",
  sample_sd_reason: "Sample SD reason",
  status: "Status",
  reason: "Reason",
};
const label = (key) => labels[key] ?? String(key).replaceAll("_", " ");
const safe = (value) => {
  if (value === null || value === undefined) return null;
  if (typeof value === "string" && /^[=+\-@]/.test(value)) return `'${value}`;
  return value;
};
const matrix = (headers, rows) => [headers, ...rows.map((row) => row.map(safe))];

function colName(index) {
  let value = index + 1;
  let name = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    value = Math.floor((value - 1) / 26);
  }
  return name;
}

function writeMatrix(sheet, startRow, startCol, values) {
  const range = sheet.getRangeByIndexes(startRow, startCol, values.length, values[0].length);
  range.values = values;
  range.format.font = { name: FONT, size: 10, color: "#000000" };
  range.format.verticalAlignment = "center";
  return range;
}

function styleHeader(sheet, rowIndex, columnCount) {
  const range = sheet.getRangeByIndexes(rowIndex, 0, 1, columnCount);
  range.format = {
    fill: NAVY,
    font: { name: FONT, size: 10, bold: true, color: "#FFFFFF" },
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: BORDER },
  };
}

function styleBody(sheet, startRow, rowCount, columnCount) {
  if (rowCount <= 0) return;
  const range = sheet.getRangeByIndexes(startRow, 0, rowCount, columnCount);
  range.format = {
    font: { name: FONT, size: 10, color: "#000000" },
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: BORDER },
  };
  for (let row = 0; row < rowCount; row += 1) {
    if (row % 2 === 1) {
      sheet.getRangeByIndexes(startRow + row, 0, 1, columnCount).format.fill = LIGHT_GRAY;
    }
  }
}

function setWidths(sheet, widths) {
  widths.forEach((width, index) => {
    sheet.getRangeByIndexes(0, index, 200, 1).format.columnWidth = width;
  });
}

function addDataTable(sheet, name, startRow, headers, rows, widths = []) {
  const values = matrix(headers, rows);
  writeMatrix(sheet, startRow, 0, values);
  styleHeader(sheet, startRow, headers.length);
  styleBody(sheet, startRow + 1, rows.length, headers.length);
  if (rows.length > 0) {
    sheet.tables.add(`A${startRow + 1}:${colName(headers.length - 1)}${startRow + rows.length + 1}`, true, name);
  }
  if (widths.length > 0) setWidths(sheet, widths);
  sheet.freezePanes.freezeRows(startRow + 1);
}

function addTitle(sheet, title, subtitle) {
  sheet.showGridLines = false;
  sheet.getRange("A1").values = [[safe(title)]];
  sheet.getRange("A1").format = { font: { name: FONT, size: 15, bold: true, color: "#000000" } };
  sheet.getRange("A2").values = [[safe(subtitle)]];
  sheet.getRange("A2").format = { font: { name: FONT, size: 10, italic: true, color: "#595959" } };
}

function addImageIfPresent(sheet, relative) {
  const fullPath = path.join(chartDir, path.basename(relative));
  // Chart files are stored below charts/, so path.basename is sufficient here.
  return fs.readFile(fullPath).then((bytes) => {
    const dataUrl = `data:image/png;base64,${Buffer.from(bytes).toString("base64")}`;
    sheet.images.add({
      dataUrl,
      anchor: { from: { row: 3, col: 4 }, extent: { widthPx: 600, heightPx: 330 } },
    });
  }).catch(() => undefined);
}

function addSummary(sheet) {
  addTitle(sheet, data.title, `${data.report_type} | ${data.report_id}`);
  const source = data.source;
  addDataTable(
    sheet,
    "SummarySource",
    3,
    ["Field", "Value"],
    [
      ["Report type", data.report_type],
      ["Scope", data.scope],
      ["Source filename", source.source_filename],
      ["Source SHA-256", source.source_sha256],
      ["Upstream run ID", source.upstream_run_id],
      ["Independent biological n", data.results.independent_biological_n ?? null],
    ],
    [28, 86],
  );
  const chart = data.charts?.[0];
  if (chart) addImageIfPresent(sheet, chart);
}

function addProvenance() {
  const sheet = workbook.worksheets.add("Provenance");
  addTitle(sheet, "Provenance", "Logical names and hashes only; no absolute paths.");
  const rows = Object.entries(data.source).map(([key, value]) => [label(key), value]);
  addDataTable(sheet, "ProvenanceTable", 3, ["Field", "Value"], rows, [34, 100]);
  return sheet;
}

function addIssues() {
  const sheet = workbook.worksheets.add("Issues");
  addTitle(sheet, "Issues", "Warnings and limitations retained from upstream artifacts.");
  const issues = data.qc.issues ?? [];
  const rows = issues.length
    ? issues.map((item) => [item.code, item.severity, item.message, item.location, item.suggested_action])
    : [["", "", "No warnings or issues were recorded.", "", ""]];
  addDataTable(sheet, "IssuesTable", 3, ["Code", "Severity", "Message", "Location", "Recommended action"], rows, [28, 14, 62, 40, 55]);
  return sheet;
}

function addMethods() {
  const sheet = workbook.worksheets.add("Methods");
  addTitle(sheet, "Methods", "Confirmed upstream method declarations.");
  const rows = Object.entries(data.methods).map(([key, value]) => [label(key), value]);
  addDataTable(sheet, "MethodsTable", 3, ["Method field", "Value"], rows, [40, 100]);
  return sheet;
}

function addGenericSheets() {
  const group = workbook.worksheets.add("Group Statistics");
  addTitle(group, "Group Statistics", "Measurement rows; independent biological n is not calculated.");
  addDataTable(
    group,
    "GroupStatisticsTable",
    3,
    ["Group", "Measurement rows", "Mean", "Median", "Minimum", "Maximum", "Sample SD"],
    data.results.group_statistics.map((item) => [item.group, item.n_measurements, item.mean, item.median, item.min, item.max, item.sample_sd]),
    [24, 18, 16, 16, 16, 16, 16],
  );
  const measurements = workbook.worksheets.add("Measurements");
  addTitle(measurements, "Measurements", "All parsed measurement rows used by the upstream descriptive result.");
  addDataTable(
    measurements,
    "MeasurementsTable",
    3,
    ["Record number", "Sample identifier", "Group", "Measurement", "Repeat type", "Source location"],
    data.results.measurements.map((item) => [item.record_number, item.sample_id, item.group, item.measurement, item.replicate_type, item.source_location]),
    [16, 22, 18, 16, 18, 60],
  );
}

function addWelchSheets() {
  const group = workbook.worksheets.add("Group Statistics");
  addTitle(group, "Group Statistics", "Experimental-unit level summaries used by Welch's method.");
  addDataTable(
    group,
    "WelchGroupStatisticsTable",
    3,
    ["Group", "Measurement rows", "Experimental units", "Mean", "Sample SD"],
    data.results.group_statistics.map((item) => [item.group, item.n_measurements, item.n_experimental_units, item.mean, item.sample_sd]),
    [24, 18, 20, 18, 18],
  );
  const units = workbook.worksheets.add("Experimental Units");
  addTitle(units, "Experimental Units", "Only unit-level values are used for the inferential comparison.");
  addDataTable(
    units,
    "ExperimentalUnitsTable",
    3,
    ["Experimental unit", "Group", "Unit value", "Measurement rows", "Technical repeat count", "Source records"],
    data.results.experimental_units.map((item) => [item.experimental_unit_id, item.group, item.aggregated_value, item.n_measurements, item.technical_repeat_count, JSON.stringify(item.source_record_numbers)]),
    [24, 18, 18, 18, 22, 28],
  );
  const comparison = workbook.worksheets.add("Comparison");
  addTitle(comparison, "Comparison", "One confirmed two-sided Welch comparison.");
  addDataTable(comparison, "ComparisonTable", 3, ["Field", "Value"], Object.entries(data.results.comparison).map(([key, value]) => [label(key), value]), [42, 30]);
  const source = workbook.worksheets.add("Technical Source Records");
  addTitle(source, "Technical Source Records", "Source rows retained separately from experimental-unit results.");
  addDataTable(
    source,
    "TechnicalSourceTable",
    3,
    ["Record number", "Experimental unit", "Group", "Measurement", "Technical repeat", "Source location"],
    data.results.technical_source_records.map((item) => [item.record_number, item.experimental_unit_id, item.group, item.measurement, item.technical_repeat_id, item.source_location]),
    [16, 24, 18, 16, 20, 60],
  );
}

function addElisaSheets() {
  const params = workbook.worksheets.add("Curve Parameters");
  addTitle(params, "Curve Parameters", "Standard-only 4PL parameters and diagnostics.");
  addDataTable(params, "CurveParametersTable", 3, ["Parameter", "Value"], Object.entries(data.results.curve_parameters).map(([key, value]) => [label(key), value]), [42, 36]);
  addDataTable(params, "CurveDiagnosticsTable", 13, ["Diagnostic", "Value"], Object.entries(data.results.diagnostics).map(([key, value]) => [label(key), value]), [42, 60]);
  const levels = workbook.worksheets.add("Standard Levels");
  addTitle(levels, "Standard Levels", "Concentration levels used by the upstream fit.");
  addDataTable(levels, "StandardLevelsTable", 3, ["Concentration", "Measurements", "Response mean", "Response SD", "Source records"], data.results.fit_levels.map((item) => [item.concentration, item.n_measurements, item.response_mean, item.response_sd, JSON.stringify(item.source_record_numbers)]), [18, 18, 20, 18, 30]);
  const raw = workbook.worksheets.add("Raw Standards");
  addTitle(raw, "Raw Standards", "Original standard records retained with inclusion decisions.");
  addDataTable(raw, "RawStandardsTable", 3, ["Record number", "Sample identifier", "Sample type", "Raw concentration", "Parsed concentration", "Raw response", "Parsed response", "Included", "Reason"], data.results.raw_standard_records.map((item) => [item.record_number, item.sample_id, item.sample_type, item.raw_concentration, item.parsed_concentration, item.raw_response, item.parsed_response, item.included, item.exclusion_reason]), [16, 22, 18, 20, 20, 20, 20, 14, 45]);
  const residuals = workbook.worksheets.add("Residuals");
  addTitle(residuals, "Residuals", "Observed, predicted, and residual values from the selected fit levels.");
  addDataTable(residuals, "ResidualsTable", 3, ["Concentration", "Observed response", "Predicted response", "Residual", "Source records"], data.results.residuals.map((item) => [item.concentration, item.observed, item.predicted, item.residual, JSON.stringify(item.source_record_numbers)]), [20, 22, 22, 18, 30]);
  const samples = workbook.worksheets.add("Sample Estimates");
  addTitle(samples, "Sample Estimates", "Research-only per-measurement estimates; blank cells mean no estimate was calculated.");
  const inverse = data.results.inverse;
  const sampleRows = inverse ? inverse.records.map((item) => [item.measurement_id, item.sample_id, item.response, item.dilution_factor, item.concentration_in_assayed_sample, item.concentration_in_original_sample, item.status, item.reason]) : [];
  addDataTable(samples, "SampleEstimatesTable", 3, ["Measurement ID", "Sample identifier", "Response", "Dilution factor", "Assayed concentration", "Original concentration", "Status", "Reason"], sampleRows, [22, 22, 18, 18, 24, 24, 34, 60]);
  const statuses = workbook.worksheets.add("Sample Status Summary");
  addTitle(statuses, "Sample Status Summary", "Counts of per-measurement research-only statuses.");
  if (inverse) {
    const order = ["estimated_within_standard_span", "below_standard_span", "above_standard_span", "outside_model_domain", "near_asymptote_unstable", "numerical_failure"];
    addDataTable(statuses, "SampleStatusTable", 3, ["Status", "Measurement rows"], order.map((status) => [status, inverse.records.filter((item) => item.status === status).length]), [42, 22]);
  } else {
    addDataTable(statuses, "SampleStatusTable", 3, ["Status", "Measurement rows"], [["No inverse package supplied", null]], [42, 22]);
  }
}

addSummary(workbook.worksheets.add("Report Summary"));
addProvenance();
addIssues();
addMethods();
if (data.report_type === "generic_grouped") addGenericSheets();
if (data.report_type === "welch_two_group") addWelchSheets();
if (data.report_type === "elisa_4pl") addElisaSheets();

workbook.recalculate();
if (qaDir) {
  await fs.mkdir(qaDir, { recursive: true });
  for (const sheet of workbook.worksheets.items) {
    const preview = await workbook.render({ sheetName: sheet.name, autoCrop: "all", scale: 1, format: "png" });
    const safeName = sheet.name.replaceAll(/[^A-Za-z0-9_-]/g, "_");
    await fs.writeFile(path.join(qaDir, `${safeName}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
}
const output = await SpreadsheetFile.exportXlsx(workbook);
await fs.mkdir(path.dirname(outputPath), { recursive: true });
await output.save(outputPath);
