@echo off
REM Windows batch helper to call PowerShell build script
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
pause