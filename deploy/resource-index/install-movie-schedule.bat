@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-movie-schedule.ps1" %*
exit /b %ERRORLEVEL%
