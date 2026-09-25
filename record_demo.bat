@echo off
setlocal
pushd "%~dp0starter" || exit /b 1

if not defined UV_CACHE_DIR set "UV_CACHE_DIR=%CD%\.uv-cache"
if not defined DEMO_URL set "DEMO_URL=http://127.0.0.1:5000"
if not defined DEMO_BROWSER_CHANNEL (
    if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "DEMO_BROWSER_CHANNEL=msedge"
    if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "DEMO_BROWSER_CHANNEL=msedge"
)

where uv >nul 2>nul
if errorlevel 1 (
    echo Error: uv is required. Install uv and retry. 1>&2
    goto :failed
)

echo Checking Playwright browser files with uv...
uv run playwright install chromium
if errorlevel 1 goto :failed

powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri $env:DEMO_URL -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -ne 200) { exit 1 } } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 goto :server_ready

echo Starting the Flask app with uv...
for /f %%P in ('powershell -NoProfile -Command "$p = Start-Process -FilePath 'uv' -ArgumentList @('run','flask','--app','server.app','run','--no-reload') -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -PassThru; $p.Id"') do set "SERVER_PID=%%P"
if not defined SERVER_PID (
    echo Error: uv could not start the Flask app. 1>&2
    goto :failed
)

for /l %%I in (1,1,120) do (
    powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri $env:DEMO_URL -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -ne 200) { exit 1 } } catch { exit 1 }" >nul 2>nul
    if not errorlevel 1 goto :server_ready
    timeout /t 1 /nobreak >nul
)
echo Error: the Flask app did not become ready at %DEMO_URL%. 1>&2
goto :failed

:server_ready
echo Recording the client 001 and 003 demo...
uv run python record_demo.py
if errorlevel 1 goto :failed

echo.
if not defined DEMO_OUTPUT_DIR echo Video saved to: %CD%\output\demo\rdv-demo-001-003.webm
set "EXIT_CODE=0"
goto :done

:failed
set "EXIT_CODE=1"

:done
if defined SERVER_PID taskkill /PID %SERVER_PID% /T /F >nul 2>nul
popd
if not defined DEMO_NO_PAUSE pause
exit /b %EXIT_CODE%
