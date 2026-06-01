@echo off
chcp 65001 >nul
title 图片压缩工具 - Image Compressor

echo ============================================
echo   图片压缩工具 - Image Compressor
echo ============================================
echo.

:: 检查 Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.x
    pause
    exit /b 1
)

:: 检查 Pillow
python -c "from PIL import Image" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [安装] 正在安装 Pillow 库...
    pip install Pillow
)

:: 如果有拖放参数
if "%~1"=="" (
    echo [使用说明]
    echo   将图片或文件夹拖放到此批处理文件上即可压缩
    echo.
    echo   或者直接运行: %~nx0 ^<图片或目录路径^>
    echo.
    pause
    exit /b
)

:: 获取脚本所在目录
set SCRIPT_DIR=%~dp0

:: 构建输出目录名（基于当前时间）
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DATETIME=%%I
set OUTPUT_DIR=compressed_%DATETIME:~0,8%_%DATETIME:~8,6%

:: 执行压缩
echo [处理中] 正在压缩图片...
python "%SCRIPT_DIR%image_compressor.py" %* -o "%OUTPUT_DIR%" -r -w 2

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [完成] 压缩完成！输出目录: %OUTPUT_DIR%
    echo.
    explorer "%OUTPUT_DIR%"
) else (
    echo.
    echo [错误] 压缩过程中出现错误
)

echo.
pause
