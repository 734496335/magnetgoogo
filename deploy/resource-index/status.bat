@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0status.ps1" %*
exit /b %ERRORLEVEL%
