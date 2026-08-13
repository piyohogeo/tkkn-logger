@echo off
setlocal
cd /d "%~dp0.."

echo Tokkun '99 missing digit collection
echo No input is sent by this tool.
echo.
echo Missing digit templates: 3, 6, 7
echo During the next 90 seconds, please play 3 or more short runs.
echo Show each RESULT for about one second before advancing to MESSAGE.
echo After starting, switch focus back to the game within 3 seconds.
echo.

".venv\Scripts\python.exe" "scripts\collect_samples.py" --duration 90 --fps 15 --start-delay 3
set "COLLECT_EXIT=%ERRORLEVEL%"

echo.
if "%COLLECT_EXIT%"=="0" (
  echo Glyph sample collection completed successfully.
) else (
  echo Collection was incomplete. Partial data was kept safely.
)
pause
exit /b %COLLECT_EXIT%
