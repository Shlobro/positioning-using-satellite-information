@echo off
python "%~dp0localization_gui.py" %*
if errorlevel 1 (
    echo.
    echo ERROR: Make sure dependencies are installed:
    echo   pip install PyQt6 pyqtgraph numpy Pillow
    echo Optional for RoMa scenarios: pip install romatch torch
    pause
)
