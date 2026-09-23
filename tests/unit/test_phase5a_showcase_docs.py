"""Small integrity checks for the public showcase documentation and synthetic fixture."""

from __future__ import annotations

import csv
import re
import struct
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_showcase_markdown_links_resolve_inside_the_repository() -> None:
    markdown_files = (
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "docs/DEMO_GUIDE.md",
    )
    for markdown_file in markdown_files:
        content = markdown_file.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", content):
            if target.startswith(("https://", "http://", "#")):
                continue
            relative_target = target.split("#", maxsplit=1)[0]
            assert (markdown_file.parent / relative_target).resolve().is_relative_to(
                PROJECT_ROOT.resolve()
            )
            assert (markdown_file.parent / relative_target).is_file(), (
                f"Broken link in {markdown_file.relative_to(PROJECT_ROOT)}: {target}"
            )


def test_inverse_boundary_showcase_fixture_is_synthetic_and_complete() -> None:
    fixture = PROJECT_ROOT / "examples/phase3b_inverse_boundary.csv"
    with fixture.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))

    assert len(rows) == 12
    assert all(row["sample_id"].startswith("SYN-") for row in rows)
    sample_ids = {row["sample_id"] for row in rows if row["sample_type"] == "sample"}
    assert sample_ids == {"SYN-IN-SPAN", "SYN-BELOW-SPAN", "SYN-ABOVE-SPAN"}
    assert all(
        row["standard_concentration"] == ""
        for row in rows
        if row["sample_type"] == "sample"
    )


def test_screenshot_checklist_names_the_public_capture_set() -> None:
    checklist = (PROJECT_ROOT / "docs/images/README.md").read_text(encoding="utf-8")
    expected_names = (
        "ui-overview.png",
        "generic-result.png",
        "welch-result.png",
        "elisa-4pl-result.png",
        "elisa-4pl-report.png",
        "elisa-inverse-boundary.png",
        "report-downloads.png",
    )
    assert all(name in checklist for name in expected_names)


def test_public_screenshots_are_real_png_assets_with_readable_dimensions() -> None:
    image_dir = PROJECT_ROOT / "docs/images"
    expected_names = (
        "ui-overview.png",
        "generic-result.png",
        "welch-result.png",
        "elisa-4pl-result.png",
        "elisa-4pl-report.png",
        "elisa-inverse-boundary.png",
        "report-downloads.png",
    )
    for name in expected_names:
        payload = (image_dir / name).read_bytes()
        assert payload.startswith(b"\x89PNG\r\n\x1a\n"), name
        width, height = struct.unpack(">II", payload[16:24])
        assert width >= 1200, name
        assert height >= 720, name
