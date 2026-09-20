@echo off
cd /d "%~dp0"

:run
python ctm_stitch.py export

echo.
choice /C RQ /N /M "Press R to run again or Q to quit: "
if errorlevel 2 exit /b
goto run
