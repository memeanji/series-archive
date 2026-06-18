@echo off
REM Series Archive 매일 자동 수집 (Windows 작업 스케줄러가 매일 05:00 호출)
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
REM S4U(로그인 없이 실행) 환경에서 한글 경로 cd 실패 방지 — 절대경로로 직접 호출
set "ROOT=C:\Users\894플러스\ad-reference-collector"
set "PY=C:\Users\894플러스\AppData\Local\Programs\Python\Python314\python.exe"
cd /d "%ROOT%"
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
REM 요일별 분할 수집(오늘 요일 그룹만) — 약 12~15개 브랜드 안정적 갱신
"%PY%" "%ROOT%\jobs\daily_group_update.py" >> "%ROOT%\logs\daily_update.log" 2>&1
