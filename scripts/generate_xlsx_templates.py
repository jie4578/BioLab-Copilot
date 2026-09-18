"""Generate synthetic XLSX templates for Phase 0.

This script only writes a new workbook with headers, instructions, and safe synthetic
placeholder rows. It does not read input files or perform analysis.
"""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

GENERIC_HEADERS = ["sample_id", "group", "measurement", "replicate"]
ELISA_HEADERS = [
    "sample_id",
    "sample_type",
    "group",
    "standard_concentration",
    "measurement",
    "replicate",
    "unit",
]


def _add_sheet(workbook: Workbook, title: str, headers: list[str], row: list[str]) -> None:
    sheet = workbook.create_sheet(title)
    sheet.append(headers)
    sheet.append(row)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions


def build_workbook() -> Workbook:
    """Return a workbook containing only synthetic template content."""

    workbook = Workbook()
    instructions = workbook.active
    instructions.title = "README"
    instructions.append(["BioLab Copilot Phase 0 templates"])
    instructions.append(["Synthetic headers and placeholder rows only; no analysis is performed."])
    instructions.append(["Keep blanks as blanks and preserve suspected outliers for future QC."])
    instructions["A1"].font = Font(bold=True)
    _add_sheet(
        workbook,
        "generic_grouped",
        GENERIC_HEADERS,
        ["SYN-TEMPLATE-01", "control", "1.00", "1"],
    )
    _add_sheet(
        workbook,
        "elisa_standard_curve",
        ELISA_HEADERS,
        ["STD-TEMPLATE-01", "standard", "", "0.10", "0.08", "1", "ng/mL"],
    )
    return workbook


def main() -> None:
    output = Path(__file__).resolve().parents[1] / "templates" / "biolab_copilot_templates.xlsx"
    output.parent.mkdir(parents=True, exist_ok=True)
    build_workbook().save(output)
    print(f"Wrote synthetic template: {output}")


if __name__ == "__main__":
    main()

