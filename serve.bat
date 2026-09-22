@echo off
rem DixitGenerator -- start the local overview in THIS terminal window.
rem
rem Home: the VS Code terminal panel, via Terminal > Run Task > "Overview: serve"
rem (the default build task, so Ctrl+Shift+B runs it too). It stays in the
rem foreground, so Ctrl+C stops it. Ctrl+C then asks "Terminate batch job
rem (Y/N)?" -- Python already had the signal by then, so the server is down
rem either way; Y just closes the script.
rem
rem 8775 is the author's port. A throwaway server for testing belongs on 8776,
rem and is stopped in the same turn it was started -- see CLAUDE.md.
rem
rem Usage:  serve.bat [port]     (default 8775)
setlocal
cd /d "%~dp0"

set "PORT=%~1"
if "%PORT%"=="" set "PORT=8775"

rem Prefer a project venv over whatever `python` happens to be on PATH, so the
rem task cannot start against an interpreter that has no dixitgen installed.
set "PY=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"

"%PY%" -c "import dixitgen" 2>nul
if errorlevel 1 (
    echo.
    echo   dixitgen is not importable by "%PY%".
    echo   Run:  "%PY%" -m pip install -e .
    echo.
    exit /b 1
)

title DixitGenerator overview :%PORT%
echo Overview: http://127.0.0.1:%PORT%/web/index.html
echo Stop it:  Ctrl+C in this terminal  (or stop-server.bat %PORT%)
echo.
"%PY%" -m dixitgen.cli serve --port %PORT%
