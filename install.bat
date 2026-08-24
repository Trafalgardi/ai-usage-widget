@echo off
chcp 65001 >nul
echo Installing pinned AI CLI Control Center dependencies...
py -3.12 -m pip install -r requirements-build.txt
echo.
echo Done. Run start_widget.vbs or: py -3.12 widget_v2.py
pause
