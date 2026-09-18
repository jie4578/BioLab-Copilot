# BioLab Copilot

BioLab Copilot is a local-first foundation for traceable biological experiment data analysis. The planned workflow is: import data, profile and quality-control it, confirm an analysis plan, run deterministic statistics, create charts, optionally obtain constrained AI-assisted interpretation, and export Word/Excel/JSON artifacts.

## Phase 1 status

Phase 0 is committed as the local baseline. Phase 1 adds read-only CSV/XLSX ingestion, explicit mappings, type parsing, structural QC, traceable JSON outputs, and an offline CLI. It intentionally contains no statistical test, CV calculation, outlier detection, curve fitting, AI integration, report renderer, database, network function, or formal UI.

## Windows quick start

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,templates]"
python -m pytest -q
ruff check .
mypy src
```

## Phase 1 CLI

Run from the project root. The package can be used directly from the source tree with `PYTHONPATH=src` or after editable installation.

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m biolab_copilot.cli list-sheets templates\biolab_copilot_templates.xlsx
python -m biolab_copilot.cli suggest-mapping examples\generic_grouped_normal.csv --experiment-type generic_grouped
python -m biolab_copilot.cli import examples\generic_grouped_normal.csv `
  --experiment-type generic_grouped `
  --mapping '{"sample_id":"sample_id","group":"group","measurement":"measurement","replicate":"replicate_id"}' `
  --output-dir outputs\phase1
```

The mapping direction is `source_column -> canonical_field`. Each run creates a new directory with `dataset_profile.json`, `validation_issues.json`, `imported_data.json`, and `run_manifest.json`. Exit code `0` means no error/blocking QC issue; `2` means an input or QC error/blocking issue; `3` means an unexpected CLI failure. Warnings are retained and do not delete records.

See [PLAN.md](PLAN.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md) for the controlled roadmap. This project is not production-ready and has not completed scientific validation.
