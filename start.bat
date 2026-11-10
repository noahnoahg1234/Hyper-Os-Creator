@echo off
REM Start Hyper OS Creator and open it in your browser.
cd /d "%~dp0"
python -m hyperos serve %*
if errorlevel 1 pause
