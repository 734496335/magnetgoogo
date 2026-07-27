@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish-media-r2-staging.ps1" %*
exit /b %ERRORLEVEL%
