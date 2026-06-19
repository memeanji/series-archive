@echo off
REM Series Archive daily collect (Task Scheduler 05:00). Use %USERPROFILE% to avoid
REM non-ASCII path bytes being misread by cmd under S4U(no-login) session.
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "ROOT=%USERPROFILE%\ad-reference-collector"
set "PY=%USERPROFILE%\AppData\Local\Programs\Python\Python314\python.exe"
cd /d "%ROOT%"
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
echo [%date% %time%] start ROOT=%ROOT% >> "%ROOT%\logs\daily_run_trace.log"
"%PY%" "%ROOT%\jobs\daily_group_update.py" >> "%ROOT%\logs\daily_update.log" 2>&1
echo [%date% %time%] end rc=%errorlevel% >> "%ROOT%\logs\daily_run_trace.log"
