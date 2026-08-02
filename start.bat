@echo off
cd /d "%~dp0"
title Community Discord Bot
echo Starting Discord Bot...
echo.
"C:\Users\jasmi\AppData\Local\Programs\Python\Python312\python.exe" -u main.py
echo.
echo Bot stopped. Press any key to exit.
pause >nul
