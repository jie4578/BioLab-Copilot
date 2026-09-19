@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%" || goto :error

set "PYTHON_LAUNCHER="
where py >nul 2>nul
if not errorlevel 1 (
  for %%V in (3.13 3.12 3.11) do (
    py -%%V scripts\check_python_compat.py >nul 2>nul
    if not errorlevel 1 if not defined PYTHON_LAUNCHER set "PYTHON_LAUNCHER=py -%%V"
  )
)

if not defined PYTHON_LAUNCHER (
  where python >nul 2>nul
  if not errorlevel 1 (
    python scripts\check_python_compat.py >nul 2>nul
    if not errorlevel 1 set "PYTHON_LAUNCHER=python"
  )
)

if not defined PYTHON_LAUNCHER (
  echo 安装失败：未找到兼容的 Python。支持范围为 Python 3.11、3.12 或 3.13。
  echo 当前已验证版本为 Python 3.13；本机其他版本仍需单独验证。
  echo 项目不会修改系统 Python、PATH 或注册表。
  goto :error
)

echo 使用解释器：!PYTHON_LAUNCHER!
if not exist ".venv\Scripts\python.exe" (
  echo 正在创建项目本地虚拟环境：%PROJECT_DIR%.venv
  call !PYTHON_LAUNCHER! -m venv ".venv"
  if errorlevel 1 goto :error
)

echo 正在安装项目及声明的开发、UI 和模板依赖。不会安装模型或创建 Provider。
".venv\Scripts\python.exe" -m pip install -e ".[dev,ui,templates]"
if errorlevel 1 goto :error

echo 安装完成。日常启动请运行 start_local.bat。
endlocal
exit /b 0

:error
echo BioLab Copilot 安装未完成。请保留此窗口中的错误信息并检查 Python、pip 和依赖来源。
pause
endlocal
exit /b 1
