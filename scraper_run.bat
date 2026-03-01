@echo off
chcp 65001 >nul
title Avia Scraper - Flight Price Tracker
echo ===================================
echo   Avia Scraper - Starting...
echo ===================================
echo.
echo   Interval: 30 min
echo   Days: 30 (both directions)
echo   Press Ctrl+C to stop
echo.
echo ===================================

cd /d "%~dp0"
venv\Scripts\python.exe scrape_and_send.py --days 30 --loop --interval 30

pause
