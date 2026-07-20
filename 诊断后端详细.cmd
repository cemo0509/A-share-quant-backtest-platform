@echo off
chcp 65001 > nul
echo ================================
echo   后端启动详细诊断
echo ================================
echo.

echo [1/6] 检查 Python 是否在 PATH 中...
echo.
python --version 2>&1
if %errorlevel% == 0 (
    echo ✓ python 命令可用
) else (
    echo ✗ python 命令不可用
)
echo.
py --version 2>&1
if %errorlevel% == 0 (
    echo ✓ py 命令可用
) else (
    echo ✗ py 命令不可用
)

echo.
echo [2/6] 查找 Python 安装位置...
where python 2>&1
where py 2>&1
echo.

echo [3/6] 检查 8000 端口是否被占用...
netstat -ano | findstr :8000
if %errorlevel% == 0 (
    echo ⚠ 8000 端口已被占用！
) else (
    echo ✓ 8000 端口空闲
)
echo.

echo [4/6] 检查后端目录是否存在...
if exist "%~dp0resources\backend" (
    echo ✓ 找到后端目录: %~dp0resources\backend
    dir "%~dp0resources\backend\*.py" 2>&1 | findstr /C:".py"
) else (
    echo ✗ 后端目录不存在
    echo 期望路径: %~dp0resources\backend
)
echo.

echo [5/6] 尝试手动启动后端（测试）...
if exist "%~dp0resources\backend\main.py" (
    echo 正在尝试启动后端，5秒后自动停止...
    if exist "%~dp0resources\backend\main.py" (
        start /B cmd /c "python ""%~dp0resources\backend\main.py"" > ""%~dp0backend_test.log"" 2>&1"
        timeout /t 5 > nul
        taskkill /f /im python.exe > nul 2>&1
        echo.
        echo --- 后端输出日志 ---
        if exist "%~dp0backend_test.log" (
            type "%~dp0backend_test.log"
        )
    )
) else (
    echo ✗ main.py 不存在，无法测试
)
echo.

echo [6/6] 检查 Python 依赖...
python -c "import flask" 2>&1
if %errorlevel% == 0 (
    echo ✓ flask 已安装
) else (
    echo ✗ flask 未安装（需要运行「安装Python依赖.cmd」）
)
python -c "import backtrader" 2>&1
if %errorlevel% == 0 (
    echo ✓ backtrader 已安装
) else (
    echo ✗ backtrader 未安装（需要运行「安装Python依赖.cmd」）
)
python -c "import pandas" 2>&1
if %errorlevel% == 0 (
    echo ✓ pandas 已安装
) else (
    echo ✗ pandas 未安装（需要运行「安装Python依赖.cmd」）
)
echo.

echo ================================
echo 诊断完成，请将以上输出截图发给开发者
echo ================================
echo.
pause
