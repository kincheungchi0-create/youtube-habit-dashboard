@echo off
cd /d %~dp0
chcp 65001 > nul
echo Starting YouTube Habit Tracker Daemon...
echo Log output will also be saved to daemon.log
python daemon.py
pause
