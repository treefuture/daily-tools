@echo off
chcp 65001 >nul
title 窗口识别自动化工具
cd /d "%~dp0"
echo 启动窗口识别自动化工具...
python window_automation_gui.py
if %errorlevel% neq 0 (
    echo.
    echo 启动失败，请确认已安装依赖: pip install -r requirements.txt
    pause
)
