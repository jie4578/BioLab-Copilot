"""Start the local-only BioLab Copilot pilot UI."""

from __future__ import annotations

import inspect
import os
import sys

from .app import build_app


def main() -> int:
    try:
        os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
        app = build_app()
        kwargs: dict[str, object] = {
            "server_name": "127.0.0.1",
            "server_port": 7860,
            "share": False,
            "show_error": True,
            "inbrowser": False,
        }
        if "analytics_enabled" in inspect.signature(app.launch).parameters:
            kwargs["analytics_enabled"] = False
        app.launch(**kwargs)
        return 0
    except Exception as exc:  # pragma: no cover - process boundary
        print(f"BioLab Copilot UI 启动失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
