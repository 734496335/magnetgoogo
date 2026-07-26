@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-media-release.ps1" %*
exit /b %ERRORLEVEL%
