@echo off
REM Series Archive 매일 자동 수집 (Windows 작업 스케줄러가 매일 05:00 호출)
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "C:\Users\894플러스\ad-reference-collector"
set "PY=C:\Users\894플러스\AppData\Local\Programs\Python\Python314\python.exe"
if not exist logs mkdir logs
"%PY%" jobs\scheduled_update.py >> "logs\daily_update.log" 2>&1
