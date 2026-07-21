@echo off
REM Series Archive 보관정책 정리 (주 1회, 일요일 02:00). 40일+ 미수집 광고 + 썸네일 삭제 + VACUUM + demo.db + push.
REM %USERPROFILE% + 절대 python 경로 → S4U(무로그인) 세션에서 비ASCII 경로 문제 회피.
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "ROOT=%USERPROFILE%\ad-reference-collector"
set "PY=%USERPROFILE%\AppData\Local\Programs\Python\Python314\python.exe"
cd /d "%ROOT%"
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
echo [%date% %time%] start retention ROOT=%ROOT% >> "%ROOT%\logs\daily_run_trace.log"
"%PY%" "%ROOT%\jobs\retention_cleanup.py" --apply --days 40 --push >> "%ROOT%\logs\retention.log" 2>&1
echo [%date% %time%] end retention rc=%errorlevel% >> "%ROOT%\logs\daily_run_trace.log"
