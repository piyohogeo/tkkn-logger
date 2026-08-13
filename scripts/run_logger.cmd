@echo off
setlocal
cd /d "%~dp0.."

echo Tokkun '99 automatic logger
echo Observation only. No game input is ever sent.
echo Non-record videos are discarded after their RESULT image and DB row are saved.
echo Press Ctrl+C to stop safely.
echo.

".venv\Scripts\python.exe" "scripts\run_live_logger.py" --duration 0 --fps 30 --mode records_only
set "LOGGER_EXIT=%ERRORLEVEL%"

echo.
if "%LOGGER_EXIT%"=="0" (
  echo Logger stopped safely.
) else (
  echo Logger reported an error. Any active video was retained in quarantine.
)
pause
exit /b %LOGGER_EXIT%
