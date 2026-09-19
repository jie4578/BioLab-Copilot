"""Project-local path resolution for source and installed-wheel execution."""

from __future__ import annotations

import os
from pathlib import Path


def project_root(explicit: Path | None = None) -> Path:
    """Resolve the project root without relying on a source checkout layout.

    A wheel cannot infer its host project's root from ``__file__``. The startup
    script sets ``BIOLAB_PROJECT_ROOT``; command-line users can set the same
    project-owned variable, or run from a directory containing ``pyproject.toml``.
    """

    configured = explicit or (
        Path(value) if (value := os.environ.get("BIOLAB_PROJECT_ROOT")) else None
    )
    if configured is not None:
        root = configured.expanduser().resolve()
        if not (root / "pyproject.toml").is_file():
            raise ValueError("BIOLAB_PROJECT_ROOT must point to a project with pyproject.toml.")
        return root

    source_candidate = Path(__file__).resolve().parents[2]
    if (source_candidate / "pyproject.toml").is_file():
        return source_candidate

    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file() and (
            (candidate / "src" / "biolab_copilot").is_dir()
            or (candidate / "outputs").is_dir()
        ):
            return candidate
    raise ValueError(
        "Project root could not be resolved. Run from the project directory or set "
        "BIOLAB_PROJECT_ROOT."
    )
