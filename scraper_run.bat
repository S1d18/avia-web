@echo off
chcp 65001 >nul
title Avia Scraper - Flight Price Tracker
echo ===================================
echo   Avia Scraper - Starting...
echo ===================================
echo.
echo   Day loop: 30 days every 30 min
echo   Night run: 90 days once at 00:00
echo   Press Ctrl+C to stop
echo.
echo ===================================

cd /d "%~dp0"
venv\Scripts\python.exe scrape_and_send.py --days 30 --loop --interval 30 --night-days 90 --night-hour 0

pause
