@echo off
rem V2M one-click launcher (production): serve the built SPA from the backend and
rem open it in the default browser. Close this window to stop the server.
setlocal
cd /d "%~dp0server"

if not exist ".venv-ml\Scripts\python.exe" (
  echo [V2M] server\.venv-ml not found. Create the Python 3.12 venv first ^(see README^).
  pause
  exit /b 1
)

rem Build the frontend once if it hasn't been built yet (backend serves web\dist at /).
if not exist "..\web\dist\index.html" (
  echo [V2M] Building web frontend ^(first run^)...
  pushd ..\web
  call npm run build
  popd
  if not exist "..\web\dist\index.html" (
    echo [V2M] Build failed - web\dist not produced. Check Node/npm install.
    pause
    exit /b 1
  )
)

rem Open the browser a few seconds after the server starts (URL assumes default V2M_PORT=8000).
start "V2M-open" /min cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000"

echo [V2M] Starting server at http://127.0.0.1:8000  (close this window to stop)
".venv-ml\Scripts\python.exe" run.py

endlocal
