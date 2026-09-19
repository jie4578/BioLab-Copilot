# Contributing

Contributions are welcome when they preserve the project's local-first, deterministic, and
traceable scope. Source code and user documentation are written in English; future UI
localization must not change scientific semantics.

## Development setup

Use a supported Python interpreter in the `>=3.11,<3.14` range. The current host has verified
Python 3.13.9; Python 3.11 and 3.12 are CI-planned validation targets until their jobs run.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,ui,templates]"
```

The first dependency installation may require network access or a pre-populated package cache.
After dependencies are available, application execution and scientific analysis are local-only.

## Required checks

Before submitting a change, run:

```powershell
python -m pytest -q
ruff check .
mypy src
git diff --check
```

Scientific changes require synthetic fixtures, independent expected-value assertions, provenance
checks, strict JSON checks, and documentation of assumptions and limitations. Do not weaken tests,
silence warnings, or add an unsupported ignore to obtain a passing result.

## Data and security rules

Never add real experiment data, patient information, antibody sequences, API keys, tokens,
personal information, generated outputs, virtual environments, or local absolute paths. Do not
read or copy from other projects. Preserve raw input bytes and hashes; do not silently delete,
impute, normalize, or overwrite scientific data.

The current release does not accept new AI, database, cloud, telemetry, provider, or network
runtime behavior. Future AI work must remain an optional explanation layer over structured
deterministic results and must not calculate or alter conclusions.

## Pull requests

Describe the phase and scope, affected contracts, tests run, synthetic fixtures used, known
limitations, and any change to security or provenance behavior. Keep commits focused and do not
include generated reports or temporary acceptance directories.
