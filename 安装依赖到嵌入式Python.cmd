@echo off
chcp 65001 > nul
echo ================================
echo   安装依赖到嵌入式 Python
echo ================================
echo.

if not exist "%~dp0python-embed\python.exe" (
    echo ✗ 未找到嵌入式 Python
    echo 请先运行「下载嵌入式Python.cmd」
    pause
    exit /b 1
)

echo [1/3] 配置嵌入式 Python（启用 site-packages）...
:: 嵌入式 Python 默认禁用 pip，需要修改 ._pth 文件
for %%f in (%~dp0python-embed\python*._pth) do (
    echo 处理文件: %%f
    powershell -Command "(Get-Content '%%f') -replace '^#import site', 'import site' | Set-Content '%%f'"
)
echo ✓ 已启用 site-packages
echo.

echo [2/3] 下载并安装 pip...
cd /d "%~dp0python-embed"
"%~dp0python-embed\python.exe" -c "import urllib.request; urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', 'get-pip.py')"
"%~dp0python-embed\python.exe" get-pip.py --no-warn-script-location
del get-pip.py
cd /d "%~dp0"
echo ✓ pip 安装完成
echo.

echo [3/3] 安装后端依赖（基于 requirements.txt）...
"%~dp0python-embed\python.exe" -m pip install fastapi "uvicorn[standard]" pydantic backtrader akshare pandas numpy pyarrow flask flask-cors tushare --no-warn-script-location
echo.

echo ================================
echo ✅ 依赖安装完成
echo ================================
echo.
echo 现在可以运行「打包桌面版.cmd」重新打包
echo 打包后用户无需安装 Python 即可使用
echo.
pause
