@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: .venv was not found.
  echo Run the approved environment setup first.
  pause
  exit /b 1
)

echo Tokkun '99 capture probe
echo This tool captures the game client only. It does not send any input.
echo Keep the game visible and on the TITLE screen for about 5 seconds.
echo.

".venv\Scripts\python.exe" "scripts\probe_capture.py" --backend auto --duration 3 --fps 30
set "PROBE_EXIT=%ERRORLEVEL%"

echo.
if "%PROBE_EXIT%"=="0" (
  echo Probe completed successfully.
) else (
  echo Probe did not complete. Keep the game visible and try again.
)
echo Report: artifacts\calibration\capture_probe\report.json
pause
exit /b %PROBE_EXIT%
