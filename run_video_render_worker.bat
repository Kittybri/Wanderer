@echo off
setlocal
cd /d "%~dp0"
python video_render_worker.py
endlocal
