@echo off
python "%~dp0map_calibrator.py" %*
if errorlevel 1 (
    echo.
    echo ERROR: Make sure Pillow is installed: pip install Pillow
    pause
)
