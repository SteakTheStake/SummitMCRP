@echo off
setlocal

cd /d "%~dp0"

echo Starting Repeat CTM Tile Generator...
echo.

python -m pip show pillow >nul 2>&1
if errorlevel 1 (
    echo Installing Pillow...
    python -m pip install pillow
)

python -m pip show tkinterdnd2 >nul 2>&1
if errorlevel 1 (
    echo Installing tkinterdnd2...
    python -m pip install tkinterdnd2
)

echo.
python repeat_ctm_gui.py

echo.
echo Tool closed.
pause