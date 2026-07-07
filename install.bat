@echo off
chcp 65001 >nul
echo Установка зависимостей виджета...
python -m pip install --upgrade pywebview pystray Pillow
echo.
echo Готово! Запускай start_widget.vbs или: python widget.py
pause
