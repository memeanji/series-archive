@echo off
REM Series Archive FULL crawl (meta+google all brands) + demo.db push.
REM Use %USERPROFILE% + absolute python so it works under S4U (no-login) session,
REM and PYTHONUTF8=1 so git/subprocess output decodes as UTF-8 (not cp949).
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "ROOT=%USERPROFILE%\ad-reference-collector"
set "PY=%USERPROFILE%\AppData\Local\Programs\Python\Python314\python.exe"
cd /d "%ROOT%"
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
echo [%date% %time%] start scheduled_update ROOT=%ROOT% >> "%ROOT%\logs\daily_run_trace.log"
"%PY%" "%ROOT%\jobs\scheduled_update.py" >> "%ROOT%\_scheduled.log" 2>&1
echo [%date% %time%] end scheduled_update rc=%errorlevel% >> "%ROOT%\logs\daily_run_trace.log"
