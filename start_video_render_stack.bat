@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=python"
set "CF_EXE=%USERPROFILE%\Downloads\cloudflared.exe"

if not exist "%CF_EXE%" (
  echo cloudflared.exe was not found at "%CF_EXE%".
  echo Download it first or update CF_EXE in this script.
  pause
  exit /b 1
)

start "Video Render Worker" powershell -NoExit -Command "cd /d '%~dp0'; & '%PYTHON_EXE%' 'video_render_worker.py'"
timeout /t 3 >nul
start "Video Render Tunnel" powershell -NoExit -Command "cd /d '%~dp0'; & '%CF_EXE%' tunnel --url http://127.0.0.1:8765 --no-autoupdate --logfile '%~dp0cloudflared.log'"

echo Started the video render worker and tunnel in separate windows.
echo When the tunnel window shows a trycloudflare.com URL, use that as VIDEO_RENDER_BASE_URL.
endlocal
