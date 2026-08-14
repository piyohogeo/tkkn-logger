@echo off
setlocal
cd /d "%~dp0.."

echo Tokkun '99 MSS vs WGC 30 FPS A/B benchmark
echo This tool captures only and never sends game input.
echo Keep the game visible and on the static TITLE screen for about 75 seconds.
echo Close Task Manager or other animated windows if possible to reduce DWM noise.
echo.
pause

".venv\Scripts\python.exe" "scripts\benchmark_capture.py" --fps 30 --duration 10 --cooldown 2
set "BENCHMARK_EXIT=%ERRORLEVEL%"

echo.
if "%BENCHMARK_EXIT%"=="0" (
  echo Capture A/B benchmark completed successfully.
) else (
  echo Capture A/B benchmark did not complete.
)
pause
exit /b %BENCHMARK_EXIT%
