@echo off
REM Series Archive view snapshots. Use %USERPROFILE% + absolute python so it works
REM under S4U (no-login) session; PYTHONUTF8=1 so subprocess/git output is UTF-8.
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "ROOT=%USERPROFILE%\ad-reference-collector"
set "PY=%USERPROFILE%\AppData\Local\Programs\Python\Python314\python.exe"
cd /d "%ROOT%"
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
echo [%date% %time%] start snapshot ROOT=%ROOT% >> "%ROOT%\logs\daily_run_trace.log"
"%PY%" "%ROOT%\jobs\snapshot_views.py" >> "%ROOT%\_snapshot.log" 2>&1
echo [%date% %time%] end snapshot rc=%errorlevel% >> "%ROOT%\logs\daily_run_trace.log"
