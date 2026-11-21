@echo off
cd /d "%~dp0"
start "" pyw -3.14 "%~dp0mew_autopilot.py"
timeout /t 1 /nobreak >nul
start "" pyw -3.14 "%~dp0ingame_button.py"
start "" "C:\Users\cenao\Downloads\Mewtator 1 0.6.0 2026-09-09T16-58Z 4laXlBFga\Mewtator\Mewtator.exe"