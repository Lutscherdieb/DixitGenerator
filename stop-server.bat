@echo off
rem DixitGenerator -- stop an overview server that has no window to Ctrl+C.
rem
rem You should not normally need this: serve.bat runs in the foreground and
rem Ctrl+C stops it. This exists for a server started detached, with no
rem terminal to interrupt, which otherwise means Task Manager.
rem
rem Called from a Bash-style shell it MUST be invoked as
rem     cmd //c "<absolute path to this file>" 8776
rem The shorter forms fail without failing -- see CLAUDE.md.
rem
rem Usage:  stop-server.bat [port]     (default 8775)
setlocal
set "PORT=%~1"
if "%PORT%"=="" set "PORT=8775"

set "FOUND="
for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /r /c:"LISTENING" ^| findstr /r /c:":%PORT% "') do (
    if not "%%P"=="0" (
        echo Stopping PID %%P -- listening on 127.0.0.1:%PORT%
        taskkill /pid %%P /t /f >nul 2>&1
        set "FOUND=1"
    )
)

if not defined FOUND (
    echo Nothing is listening on port %PORT%.
    exit /b 1
)
echo Done.
