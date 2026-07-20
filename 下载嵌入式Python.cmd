@echo off
chcp 65001 > nul
echo ================================
echo   下载 Python 嵌入式版本
echo ================================
echo.

set PYTHON_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip
set OUTPUT=%~dp0python-embed.zip

echo 正在下载 Python 3.11.9 嵌入式版本...
echo 下载地址: %PYTHON_URL%
echo.

:: 使用 curl 下载（Windows 10+ 内置）
curl -L -o "%OUTPUT%" "%PYTHON_URL%"

if exist "%OUTPUT%" (
    echo.
    echo ✓ 下载完成: %OUTPUT%
    echo.
    echo 正在解压到 python-embed 目录...
    if not exist "%~dp0python-embed" mkdir "%~dp0python-embed"
    powershell -Command "Expand-Archive -Path '%OUTPUT%' -DestinationPath '%~dp0python-embed' -Force"
    echo ✓ 解压完成
    echo.
    echo 下一步：运行「安装依赖到嵌入式Python.cmd」
    del "%OUTPUT%"
) else (
    echo ✗ 下载失败，请手动下载：
    echo %PYTHON_URL%
    echo 并解压到 python-embed 目录
)

echo.
pause
