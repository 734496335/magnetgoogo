@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-movies-safe.ps1" %*
exit /b %ERRORLEVEL%
