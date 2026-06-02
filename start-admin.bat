@echo off
chcp 65001 >nul
title MagGoogo Admin Dashboard

echo.
echo   ==========================================
echo     MagGoogo Admin Dashboard (Local)
echo   ==========================================
echo.

where node >nul 2>nul
if %errorlevel% neq 0 (
    echo   [Error] Node.js not found. Please install it first: https://nodejs.org
    pause
    exit /b 1
)

if not exist "%~dp0admin-server\node_modules" (
    echo   [First Run] Installing dependencies...
    cd /d "%~dp0admin-server"
    npm install
    echo.
)

echo   Starting...
cd /d "%~dp0admin-server"
start "" "http://localhost:3800"
node server.js
