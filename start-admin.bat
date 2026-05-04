@echo off
chcp 65001 >nul
title MagGoogo Admin Dashboard

echo.
echo   ==========================================
echo     MagGoogo 运营后台  (本地)
echo   ==========================================
echo.

:: 检查 Node.js
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo   [错误] 未找到 Node.js，请先安装: https://nodejs.org
    pause
    exit /b 1
)

:: 检查依赖
if not exist "%~dp0admin-server\node_modules" (
    echo   [首次运行] 安装依赖...
    cd /d "%~dp0admin-server"
    npm install
    echo.
)

:: 启动服务
echo   启动中...
cd /d "%~dp0admin-server"
start "" "http://localhost:3800"
node server.js
