@echo off
chcp 65001 > nul
echo ================================
echo   检查 Python 安装状态
echo ================================
echo.

:: 检查 py 命令
echo [1/3] 检查 Python Launcher (py)...
py --version > nul 2>&1
if %errorlevel% == 0 (
    echo ✓ Python Launcher 已安装
    py --version
    goto :check_version
) else (
    echo ✗ Python Launcher 未安装
)

:: 检查 python 命令
echo.
echo [2/3] 检查 Python (python)...
python --version > nul 2>&1
if %errorlevel% == 0 (
    echo ✓ Python 已安装
    python --version
    goto :check_version
) else (
    echo ✗ Python 未安装
)

:: 都没找到
echo.
echo ================================
echo ❌ 未检测到 Python 安装
echo ================================
echo.
echo 本软件需要 Python 3.8 或更高版本。
echo.
echo 请按以下步骤安装 Python：
echo.
echo 1. 下载 Python 安装包（推荐 Python 3.11）：
echo    国内镜像：https://mirrors.tuna.tsinghua.edu.cn/python/
echo    官网：https://www.python.org/downloads/
echo.
echo 2. 运行安装包，务必勾选：
echo    ☑ Add Python to PATH
echo    （添加到环境变量，非常重要！）
echo.
echo 3. 点击 "Install Now" 完成安装
echo.
echo 4. 安装完成后，重新运行本脚本验证
echo.
pause
goto :end

:check_version
echo.
echo [3/3] 检查 Python 版本...
python --version 2> nul | findstr /R "3\.[89]\..* 3\.1[0-9]\..*" > nul
if %errorlevel% == 0 (
    echo ✓ Python 版本符合要求（3.8+）
) else (
    py --version 2> nul | findstr /R "3\.[89]\..* 3\.1[0-9]\..*" > nul
    if !errorlevel! == 0 (
        echo ✓ Python 版本符合要求（3.8+）
    ) else (
        echo ⚠ Python 版本可能过低，推荐安装 Python 3.11
    )
)

echo.
echo ================================
echo ✅ Python 已正确安装
echo ================================
echo.
echo 现在可以运行「安装Python依赖.cmd」安装后端依赖，
echo 然后运行「启动程序.cmd」启动软件。
echo.
pause

:end
