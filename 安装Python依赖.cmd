@echo off
chcp 65001 > nul
echo ================================
echo   安装量化回测平台Python依赖
echo ================================
echo.

REM 检查Python是否安装
python --version > nul 2>&1
if errorlevel 1 (
    echo ✗ Python未安装或不在PATH中！
    echo.
    echo 请先安装Python：
    echo 1. 访问 https://www.python.org/downloads/
    echo 2. 下载并安装Python 3.8+
    echo 3. 安装时务必勾选 "Add Python to PATH"
    echo 4. 安装完成后重启电脑
    echo.
    pause
    exit /b 1
)

echo ✓ Python已安装
echo.

REM 升级pip
echo [1/6] 升级pip...
python -m pip install --upgrade pip
echo.

REM 安装依赖
echo [2/6] 安装 Flask (后端框架)...
pip install flask flask-cors
echo.

echo [3/6] 安装 backtrader (回测框架)...
pip install backtrader
echo.

echo [4/6] 安装 pandas (数据处理)...
pip install pandas
echo.

echo [5/6] 安装 numpy (数值计算)...
pip install numpy
echo.

echo [6/6] 安装 tushare (数据接口)...
pip install tushare
echo.

REM 验证安装
echo ================================
echo 验证安装...
echo ================================
python -c "import flask; print('✓ Flask')" 2>&1
python -c "import backtrader; print('✓ Backtrader')" 2>&1
python -c "import pandas; print('✓ Pandas')" 2>&1
python -c "import numpy; print('✓ Numpy')" 2>&1
python -c "import tushare; print('✓ Tushare')" 2>&1
echo.

echo ================================
echo ✓ Python依赖安装完成！
echo ================================
echo.
echo 现在可以启动量化回测平台了。
echo.
pause
