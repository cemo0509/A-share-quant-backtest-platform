@echo off
chcp 65001 > nul
echo ================================
echo   启动量化回测平台
echo ================================
echo.

if exist "dist\win-unpacked\A股量化回测平台.exe" (
    echo 正在启动程序...
    start "" "dist\win-unpacked\A股量化回测平台.exe"
) else (
    echo ✗ 可执行文件不存在！
    echo 请先运行打包脚本。
    pause
)
