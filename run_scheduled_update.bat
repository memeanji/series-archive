@echo off
cd /d C:\Users\894플러스\ad-reference-collector
python jobs\scheduled_update.py >> _scheduled.log 2>&1
