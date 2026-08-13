@echo off
setlocal
cd /d "%~dp0.."

echo Tokkun '99 state sample collection
echo No input is sent by this tool.
echo.
echo During the next 60 seconds, please show this sequence by normal play:
echo   TITLE -^> PLAYING -^> RESULT -^> MESSAGE -^> TITLE
echo Intentionally ending the run early is fine.
echo After starting, switch focus back to the game within 3 seconds.
echo.

".venv\Scripts\python.exe" "scripts\collect_samples.py" --duration 60 --fps 15 --start-delay 3
set "COLLECT_EXIT=%ERRORLEVEL%"

echo.
if "%COLLECT_EXIT%"=="0" (
  echo Sample collection completed successfully.
) else (
  echo Sample collection was incomplete. The partial data was kept safely.
)
pause
exit /b %COLLECT_EXIT%
