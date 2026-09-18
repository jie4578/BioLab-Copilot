# Windows 11 development notes

Use Python 3.11 explicitly so the environment matches `pyproject.toml`:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,templates]"
```

If PowerShell blocks activation, run the commands from an activated developer shell or use the interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe src
```

All paths in the project should use `pathlib.Path`; input filenames must be treated as data, not shell commands. Keep files UTF-8 and avoid committing `.venv`, generated artifacts, user data, or secrets.

