@echo off
setlocal
cd /d "%~dp0.."

echo Tokkun '99 automatic logger - experimental Windows Graphics Capture
echo Observation only. No game input is ever sent.
echo Recording remains 30 FPS. Use run_logger.cmd for the established MSS backend.
echo Press Ctrl+C to stop safely.
echo.

".venv\Scripts\python.exe" "scripts\run_live_logger.py" --duration 0 --fps 30 --mode records_only --capture-backend wgc
set "LOGGER_EXIT=%ERRORLEVEL%"

echo.
if "%LOGGER_EXIT%"=="0" (
  echo WGC logger stopped safely.
) else (
  echo WGC logger reported an error. Any active video was retained in quarantine.
)
pause
exit /b %LOGGER_EXIT%
