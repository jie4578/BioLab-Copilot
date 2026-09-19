# Windows installation and startup

BioLab Copilot is a local pilot for Windows 11. It does not modify system Python, `PATH`, the
registry, or security settings, and it does not require administrator privileges.

## Prerequisites

- Windows 11 or a compatible Windows environment.
- Python 3.11, 3.12, or 3.13. The project metadata allows `>=3.11,<3.14`.
- Python 3.13 is the current verified Windows runtime. Python 3.11 and 3.12 are not yet verified
  on the current host and must not be described as locally validated.
- A local package source or internet connection during one-time dependency installation. The
  application itself does not make runtime network requests.

## One-time installation

From File Explorer, double-click `setup_windows.bat`, or run it from PowerShell in any directory:

```powershell
C:\path\to\BioLab-Copilot\setup_windows.bat
```

The script resolves its own directory, prefers Python 3.13, then checks Python 3.12 and 3.11,
creates `.venv` below the project, and installs the declared development, UI, and template extras
into that environment. It fails visibly if no interpreter in the supported range or dependency
source is available. It never installs models or creates a provider.

Equivalent manual commands are:

```powershell
cd C:\path\to\BioLab-Copilot
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,ui,templates]"
```

## Daily startup

Double-click `start_local.bat`, or run:

```powershell
cd C:\path\to\BioLab-Copilot
.\.venv\Scripts\python.exe -m biolab_copilot.ui
```

The server must display only:

```text
http://127.0.0.1:7860
```

It uses `share=False` and disables Gradio analytics. Stop it with `Ctrl+C` in the terminal.

When invoking an installed wheel from outside the project directory, set the project boundary
explicitly before using paths or starting the UI:

```powershell
$env:BIOLAB_PROJECT_ROOT = (Resolve-Path C:\path\to\BioLab-Copilot).Path
```

The provided `start_local.bat` sets this variable automatically.

## Troubleshooting

- **Python not found:** install a supported Python 3.11-3.13 interpreter. The setup script checks
  the `py` launcher first and then a `python` command.
- **`.venv` not found:** run `setup_windows.bat` first.
- **Port 7860 is busy:** stop the existing local pilot or choose a reviewed local configuration;
  do not expose the service publicly.
- **Gradio missing:** reinstall with `.[ui]` inside `.venv`.
- **Report rendering unavailable:** confirm that the project dependencies installed successfully.
  DOCX uses `python-docx`, XLSX uses `openpyxl`, and PNG uses the declared matplotlib stack.
  The application does not require Node, npm, Codex runtime modules, or artifact-tool, and it
  does not silently download a missing report tool.

## Offline operation

After the declared dependencies are installed, imports, QC, deterministic analysis, charting, and
report rendering run locally. Installation may need network access unless dependencies are already
cached; this is not a claim of completely offline installation. No API key, LLM, provider,
database, telemetry, or cloud endpoint is required at runtime.
