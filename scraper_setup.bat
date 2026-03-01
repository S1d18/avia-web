@echo off
chcp 65001 >nul
echo ===================================
echo   Avia Scraper - First Time Setup
echo ===================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Install Python 3.11+ from python.org
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo [1/4] Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo [ERROR] Failed to create venv
    pause
    exit /b 1
)

echo [2/4] Installing dependencies...
venv\Scripts\pip.exe install -r requirements.txt playwright playwright-stealth >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to install packages
    pause
    exit /b 1
)

echo [3/4] Installing Chromium browser for Playwright...
venv\Scripts\python.exe -m playwright install chromium >nul 2>&1

echo [4/4] Checking .env config...
if not exist .env (
    echo [WARNING] No .env file found!
    echo Create .env with these lines:
    echo   SCRAPE_API_KEY=your_api_key_here
    echo   SCRAPE_PROXIES=,http://user:pass@host:port,http://user:pass@host2:port2
    echo.
) else (
    echo .env found - OK
)

echo.
echo ===================================
echo   Setup complete!
echo   Run scraper_run.bat to start
echo ===================================
pause
