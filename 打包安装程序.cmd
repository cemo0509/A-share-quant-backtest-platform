@echo off
chcp 65001 > nul
echo ================================
echo  打包安装程序（跳过前端打包）
echo ================================
echo.

REM 关闭占用进程
taskkill /f /im "A股量化回测平台.exe" > nul 2>&1
taskkill /f /im electron.exe > nul 2>&1
timeout /t 2 > nul

REM 打包桌面版
cd /d %~dp0electron
call "C:\Program Files\nodejs\npm.cmd" run dist
if errorlevel 1 (
    echo ❌ 打包失败
    pause
    exit /b 1
)

echo.
echo ✅ 打包完成！
echo 安装包在：dist\ 文件夹
echo.
pause
