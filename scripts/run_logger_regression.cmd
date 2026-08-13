@echo off
setlocal
cd /d "%~dp0.."

echo Tokkun '99 automatic logger - regression frame experiment
echo Observation only. No game input is ever sent.
echo Distinct RESULT frames are saved as lossless PNGs, up to 300 per run.
echo Press Ctrl+C to stop safely.
echo.

".venv\Scripts\python.exe" "scripts\run_live_logger.py" --duration 0 --fps 30 --mode records_only --log-result-frames
set "LOGGER_EXIT=%ERRORLEVEL%"

echo.
if "%LOGGER_EXIT%"=="0" (
  echo Logger stopped safely.
) else (
  echo Logger reported an error. Any active video and regression frames were retained.
)
pause
exit /b %LOGGER_EXIT%
