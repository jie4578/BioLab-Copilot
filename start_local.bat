@echo off
setlocal EnableExtensions
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%" || goto :error
if not exist ".venv\Scripts\python.exe" (
  echo BioLab Copilot 启动失败：未找到项目 .venv。
  echo 请先运行 setup_windows.bat。
  goto :error
)
".venv\Scripts\python.exe" scripts\check_python_compat.py >nul 2>nul
if errorlevel 1 (
  echo BioLab Copilot 启动失败：.venv 中的 Python 版本不在支持范围 3.11-3.13。
  goto :error
)
set "PYTHONPATH=%PROJECT_DIR%src"
set "BIOLAB_PROJECT_ROOT=%PROJECT_DIR%"
".venv\Scripts\python.exe" -m biolab_copilot.ui
if errorlevel 1 goto :error
endlocal
exit /b 0

:error
echo BioLab Copilot UI 启动失败。请检查 Python 版本、项目依赖、端口 7860 和上面的错误信息。
pause
endlocal
exit /b 1
