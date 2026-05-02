@echo off
chcp 65001 >nul
echo ========================================
echo     Запуск Telegram Бота Скорой Помощи
echo ========================================
echo.

cd /d C:\Users\ZoziDo\ambulance_bot

echo Активирую виртуальное окружение...
call venv\Scripts\activate.bat

echo Запускаю бота...
python main.py

echo.
echo Бот остановлен. Нажмите любую клавишу для выхода...
pause >nul