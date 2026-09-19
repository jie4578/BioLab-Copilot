# Windows 11 development notes

Use a supported Python 3.11-3.13 interpreter. Python 3.13 is the current verified Windows runtime;
Python 3.11 and 3.12 are not yet verified on the current host:

```powershell
py -3.13 -m venv .venv
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
