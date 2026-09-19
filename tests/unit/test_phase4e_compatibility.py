"""Regression checks for the public CI Python-version compatibility boundary."""

import runpy
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_numpy_bound_preserves_python_311_mypy_compatibility_boundary() -> None:
    """Keep the dependency bound explicit instead of relying on resolver luck."""
    pyproject = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    project = pyproject["project"]
    assert project["requires-python"] == ">=3.11,<3.14"
    assert "numpy>=2.0,<2.5" in project["dependencies"]
    assert pyproject["tool"]["mypy"]["python_version"] == "3.11"


def test_release_checker_accepts_a_distribution_directory() -> None:
    """The documented dist-directory check should expand archives deterministically."""
    checker = runpy.run_path(str(PROJECT_ROOT / "scripts/check_release_artifacts.py"))

    class FakePath:
        def __init__(
            self,
            name: str,
            *,
            directory: bool = False,
            children: tuple[object, ...] = (),
        ) -> None:
            self.name = name
            self._directory = directory
            self._children = children

        @property
        def suffix(self) -> str:
            return ".whl" if self.name.endswith(".whl") else ".txt"

        def is_dir(self) -> bool:
            return self._directory

        def is_file(self) -> bool:
            return not self._directory

        def iterdir(self) -> tuple[object, ...]:
            return self._children

    directory = FakePath(
        "dist",
        directory=True,
        children=(
            FakePath("b.whl"),
            FakePath("ignored.txt"),
            FakePath("a.tar.gz"),
        ),
    )

    archives = checker["_expand_archives"]([directory])

    assert [archive.name for archive in archives] == ["a.tar.gz", "b.whl"]
