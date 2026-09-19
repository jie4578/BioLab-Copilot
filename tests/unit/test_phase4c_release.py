"""Release-hardening checks that do not require a Windows process or network."""

from __future__ import annotations

import tomllib
from pathlib import Path

from biolab_copilot import __version__

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_release_version_has_one_packaging_source() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    assert __version__ == "0.1.0"
    assert project["requires-python"] == ">=3.11,<3.14"
    assert project["dynamic"] == ["version"]
    assert pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"] == (
        "biolab_copilot.__version__"
    )


def test_windows_scripts_are_project_relative_and_use_local_venv() -> None:
    setup = (PROJECT_ROOT / "setup_windows.bat").read_text(encoding="utf-8")
    start = (PROJECT_ROOT / "start_local.bat").read_text(encoding="utf-8")
    assert "%~dp0" in setup
    assert "%~dp0" in start
    assert ".venv\\Scripts\\python.exe" in setup
    assert ".venv\\Scripts\\python.exe" in start
    assert "3.13" in setup
    assert "3.12" in setup
    assert "3.11" in setup
    assert "BIOLAB_PROJECT_ROOT" in start
    assert "C:\\Users\\Administrator" not in setup + start


def test_report_runtime_uses_declared_python_dependencies() -> None:
    renderer = (PROJECT_ROOT / "src/biolab_copilot/reporting/renderer.py").read_text(
        encoding="utf-8"
    )
    assert "BIOLAB_REPORT_NODE" not in renderer
    assert "BIOLAB_REPORT_PYTHON" not in renderer
    assert "subprocess" not in renderer
    assert "write_xlsx" in renderer
    assert "write_docx" in renderer
    assert "Path.home()" in renderer
