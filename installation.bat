@echo off
title Yuanx - Install Dependencies

echo ========================================
echo Yuanx - Installing Dependencies
echo ========================================
echo.

echo Upgrading pip...
python -m pip install --upgrade pip

echo.
echo Installing Python dependencies...
python -m pip install -U discord.py pillow psutil pyautogui playwright pynput opencv-python numpy sounddevice scipy pycaw comtypes

echo.
echo ========================================
echo Installing Playwright Chromium...
echo ========================================

python -m playwright install chromium

echo.
echo ========================================
echo Installation completed.
echo ========================================
echo.

pause