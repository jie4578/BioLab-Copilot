@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
py -3.11 -m biolab_copilot.ui
if errorlevel 1 (
  echo BioLab Copilot UI 启动失败。请检查 Python 3.11、依赖和终端错误信息。
  exit /b 1
)
endlocal
