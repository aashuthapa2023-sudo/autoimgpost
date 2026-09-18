@echo off
title Auto-Post Pipeline - Running Every Hour
echo ===================================================
echo   Auto-Post Pipeline Hourly Scheduler
echo   Press Ctrl+C to stop
echo ===================================================
echo.

:loop
echo [%date% %time%] Running pipeline for all channels...
python main.py run
echo.
echo [%date% %time%] Next run in 60 minutes. Waiting...
timeout /t 3600 /nobreak
echo.
goto loop
