@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-latest.ps1" %*
exit /b %ERRORLEVEL%
