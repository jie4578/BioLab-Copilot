"""Check built distribution archives for generated, private, or local-only content."""

from __future__ import annotations

import argparse
import re
import tarfile
import zipfile
from pathlib import Path

FORBIDDEN_MARKERS = (
    "/outputs/",
    "/dist/",
    "/build/",
    "/.venv",
    "/.env",
    "phase2a-boundaries-lliqpk1e",
    "__pycache__/",
)
ABSOLUTE_PATH_PATTERN = re.compile(r"(?i)([a-z]:[\\/]|/users/|/home/)")


def _normalise(name: str) -> str:
    return "/" + name.replace("\\", "/").lstrip("/")


def _invalid_name(name: str) -> str | None:
    normalised = _normalise(name)
    if any(marker in normalised for marker in FORBIDDEN_MARKERS):
        return "generated or temporary path"
    if ABSOLUTE_PATH_PATTERN.search(name):
        return "absolute local path"
    if name.endswith(".env") or name.endswith(".pem") or name.endswith(".key"):
        return "private configuration or key file"
    return None


def _check_archive(path: Path) -> int:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, mode="r:gz") as archive:
            names = archive.getnames()
    else:
        raise ValueError(f"Unsupported distribution archive: {path.name}")

    for name in names:
        reason = _invalid_name(name)
        if reason is not None:
            raise ValueError(f"{path.name}: {reason}: {name}")
    print(f"OK {path.name}: {len(names)} members checked")
    return len(names)


def _expand_archives(paths: list[Path]) -> list[Path]:
    archives: list[Path] = []
    for path in paths:
        if path.is_dir():
            directory_archives = sorted(
                (
                    candidate
                    for candidate in path.iterdir()
                    if candidate.is_file()
                    and (
                        candidate.suffix == ".whl"
                        or candidate.name.endswith(".tar.gz")
                    )
                ),
                key=lambda candidate: candidate.name,
            )
            if not directory_archives:
                raise ValueError(f"No distribution archives found in: {path}")
            archives.extend(directory_archives)
        else:
            archives.append(path)
    return archives


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args()
    for archive in _expand_archives(args.archives):
        _check_archive(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
