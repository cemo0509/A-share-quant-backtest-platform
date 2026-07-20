@echo off
chcp 65001 > nul
echo ================================
echo   量化回测平台 - 后端诊断工具
echo ================================
echo.

REM 检查Python
echo [1/6] 检查Python...
python --version 2>&1
if errorlevel 1 (
    echo ✗ Python未安装！
    goto end
)
echo.

REM 检查依赖
echo [2/6] 检查Python依赖...
python -c "import flask; print('✓ Flask')" 2>&1
python -c "import backtrader; print('✓ Backtrader')" 2>&1
python -c "import pandas; print('✓ Pandas')" 2>&1
python -c "import tushare; print('✓ Tushare')" 2>&1
echo.

REM 检查端口占用
echo [3/6] 检查端口5000...
netstat -ano | findstr :5000
if errorlevel 1 (
    echo - 端口5000未被占用
) else (
    echo ⚠ 端口5000已被占用！
)
echo.

REM 检查后端文件
echo [4/6] 检查后端文件...
if exist "dist\win-unpacked\resources\backend\main.py" (
    echo ✓ 后端文件存在（绿色版）
) else (
    echo - 绿色版后端文件不存在，检查安装版...
)

REM 查找安装目录
set INSTALL_DIR=%LOCALAPPDATA%\Programs\A股量化回测平台
if exist "%INSTALL_DIR%\resources\backend\main.py" (
    echo ✓ 后端文件存在（安装版）：%INSTALL_DIR%
) else (
    echo ✗ 后端文件不存在！
)
echo.

REM 尝试手动启动后端
echo [5/6] 尝试手动启动后端...
if exist "%INSTALL_DIR%\resources\backend\main.py" (
    echo 正在启动后端...
    start "后端服务" cmd /k "cd /d "%INSTALL_DIR%\resources\backend" && python main.py"
    timeout /t 5 > nul
    echo ✓ 后端已启动，请检查程序是否变为在线状态
) else (
    echo ✗ 无法找到后端文件，无法启动
)
echo.

REM 测试连接
echo [6/6] 测试后端连接...
curl -s http://localhost:5000/api/health 2>&1 || echo ✗ 无法连接到后端
echo.

echo ================================
echo 诊断完成！
echo ================================
echo.
pause

:end
