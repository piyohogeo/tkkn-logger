@echo off
setlocal
cd /d "%~dp0.."

echo Tokkun '99 integrated logger smoke test
echo This tool observes and records only. It never sends game input.
echo.
echo During the next 120 seconds, play at least one complete run:
echo   TITLE -^> PLAYING -^> RESULT -^> MESSAGE -^> TITLE
echo Keep each RESULT and MESSAGE visible for about one second.
echo Switch focus back to the game after starting.
echo.

".venv\Scripts\python.exe" "scripts\run_live_logger.py" --duration 120 --fps 30 --mode collect_all
set "LOGGER_EXIT=%ERRORLEVEL%"

echo.
if "%LOGGER_EXIT%"=="0" (
  echo Integrated smoke test completed.
) else (
  echo Integrated smoke test reported an error. Any partial video was retained.
)
pause
exit /b %LOGGER_EXIT%
