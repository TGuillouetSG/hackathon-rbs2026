@echo off
setlocal
pushd "%~dp0starter" || exit /b 1

where uv >nul 2>nul
if not errorlevel 1 (
    call uv run flask --app server.app run %*
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m flask --app server.app run %*
) else (
    echo Error: install uv or create the starter virtual environment. 1>&2
    popd
    exit /b 1
)
set "exit_code=%errorlevel%"

popd
exit /b %exit_code%
