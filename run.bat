@echo off
chcp 65001 >nul
title SKHY ADR Premium Dashboard
cd /d "%~dp0"

echo ========================================================
echo   SKHY(ADR) Premium Trend Dashboard - Runner
echo ========================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to PATH.
    pause
    exit /b 1
)

echo [INFO] Starting SKHY(ADR) Premium Dashboard...
echo.
streamlit run app.py

pause
