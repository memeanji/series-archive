@echo off
REM Series Archive 구글 요일별 그룹 수집 (Task Scheduler 20:00, 퇴근 후). 근무시간(09~19시) 회피.
REM %USERPROFILE% + 절대 python 경로 → S4U(무로그인) 세션에서 비ASCII 경로 문제 회피.
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "ROOT=%USERPROFILE%\ad-reference-collector"
set "PY=%USERPROFILE%\AppData\Local\Programs\Python\Python314\python.exe"
cd /d "%ROOT%"
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
echo [%date% %time%] start google_group ROOT=%ROOT% >> "%ROOT%\logs\daily_run_trace.log"
"%PY%" "%ROOT%\jobs\google_group_update.py" >> "%ROOT%\logs\google_update.log" 2>&1
echo [%date% %time%] end google_group rc=%errorlevel% >> "%ROOT%\logs\daily_run_trace.log"
