@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "ARG_PAGES_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%ARG_PAGES_PY%" set "ARG_PAGES_PY="
if defined ARG_PAGES_PY (
  "%ARG_PAGES_PY%" "%~dp0scripts\update_catalog.py" --repo "%~dp0." %*
) else (
  py -3 "%~dp0scripts\update_catalog.py" --repo "%~dp0." %*
)
set "ARG_PAGES_EXIT=%ERRORLEVEL%"
echo.
if not "%ARG_PAGES_EXIT%"=="0" echo Update failed. The previous catalog is preserved when possible. See the error above.
if /i not "%ARG_PAGES_NO_PAUSE%"=="1" pause
exit /b %ARG_PAGES_EXIT%
