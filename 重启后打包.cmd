@echo off
chcp 65001 > nul
echo ================================
echo   重启后打包脚本
echo ================================
echo.

REM 等待系统稳定
timeout /t 5 > nul

REM 关闭可能占用文件的进程
echo [1/5] 关闭占用进程...
taskkill /f /im "A股量化回测平台.exe" > nul 2>&1
taskkill /f /im electron.exe > nul 2>&1
taskkill /f /im node.exe > nul 2>&1
taskkill /f /im npm.exe > nul 2>&1
timeout /t 3 > nul
echo ✓ 进程已关闭
echo.

REM 删除旧的打包目录
echo [2/5] 删除旧的打包目录...
if exist "dist" (
    rmdir /s /q "dist"
    echo        ✓ 删除成功
) else (
    echo        - 目录不存在（跳过）
)
echo.

REM 重新构建前端（确保最新）
echo [3/5] 构建前端...
cd frontend
call "C:\Program Files\nodejs\npm.cmd" run build
if errorlevel 1 (
    echo ✗ 前端构建失败！
    pause
    exit /b 1
)
cd ..
echo ✓ 前端构建完成
echo.

REM 复制前端到electron目录
echo [4/5] 复制前端文件...
if not exist "electron\dist" mkdir "electron\dist"
xcopy /y /e frontend\dist\* electron\dist\ > nul
echo ✓ 文件复制完成
echo.

REM 打包（目录模式 + 安装程序模式）
echo [5/5] 打包桌面应用...
cd ..
call "C:\Program Files\nodejs\npm.cmd" run dist
if errorlevel 1 (
    echo.
    echo ⚠ 完整打包失败，尝试只打包目录模式...
    call "C:\Program Files\nodejs\npm.cmd" run pack
)

echo.
echo ================================
if exist "dist\win-unpacked\A股量化回测平台.exe" (
    echo  ✓ 打包成功！
    echo.
    echo  可执行文件：
    echo  - 目录模式：dist\win-unpacked\A股量化回测平台.exe
    if exist "dist\*.exe" (
        echo  - 安装程序：dist\*.exe
    )
    echo.
    echo  现在可以运行程序测试了！
) else (
    echo  ✗ 打包失败，请检查错误信息
)
echo ================================
echo.
pause
