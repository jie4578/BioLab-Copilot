"""Exit successfully when the interpreter is within the supported Python range."""

from __future__ import annotations

import sys

SUPPORTED = {(3, 11), (3, 12), (3, 13)}


def main() -> int:
    version = sys.version_info[:2]
    if version in SUPPORTED:
        print(f"Supported Python {version[0]}.{version[1]}")
        return 0
    print("BioLab Copilot requires Python 3.11, 3.12, or 3.13.")
    print(f"Detected Python {version[0]}.{version[1]}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
