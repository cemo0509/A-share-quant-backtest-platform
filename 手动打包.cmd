@echo off
chcp 65001 > nul
echo ================================
echo  手动打包脚本
echo ================================
echo.

REM 设置npm镜像
echo [1/6] 设置npm镜像...
call npm config set registry https://registry.npmmirror.com
call npm config set electron_mirror https://cdn.npmmirror.com/binaries/electron/
call npm config set electron_builder_binaries_mirror https://cdn.npmmirror.com/binaries/electron-builder-binaries/
echo ✓ 镜像设置完成
echo.

REM 检查electron是否存在
echo [2/6] 检查electron二进制文件...
if not exist "node_modules\electron\dist\electron.exe" (
    echo ⚠ electron.exe 不存在，尝试重新下载...
    cd node_modules\electron
    call node install.js
    cd ..\..
    
    if not exist "node_modules\electron\dist\electron.exe" (
        echo ✗ electron下载失败！
        echo.
        echo 请手动下载electron：
        echo 1. 访问：https://registry.npmmirror.com/-/binary/electron/33.4.11/electron-v33.4.11-win32-x64.zip
        echo 2. 下载后解压到：node_modules\electron\dist\ 目录
        echo 3. 确保 electron.exe 在 dist 目录中
        echo.
        pause
        exit /b 1
    )
)
echo ✓ electron二进制文件存在
echo.

REM 关闭占用进程
echo [3/6] 关闭占用进程...
taskkill /f /im "A股量化回测平台.exe" > nul 2>&1
taskkill /f /im electron.exe > nul 2>&1
taskkill /f /im node.exe > nul 2>&1
timeout /t 3 > nul
echo ✓ 进程已关闭
echo.

REM 构建前端
echo [4/6] 构建前端...
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
echo [5/6] 复制前端文件...
if not exist "electron\dist" mkdir "electron\dist"
xcopy /y /e frontend\dist\* electron\dist\ > nul
echo ✓ 文件复制完成
echo.

REM 打包
echo [6/6] 打包桌面应用...
call "C:\Program Files\nodejs\npm.cmd" run dist
if errorlevel 1 (
    echo.
    echo ⚠ 完整打包失败，尝试打包为目录模式...
    call "C:\Program Files\nodejs\npm.cmd" run pack
)

echo.
echo ================================
if exist "dist\win-unpacked\A股量化回测平台.exe" (
    echo  ✓ 打包成功！
    echo  可执行文件：dist\win-unpacked\A股量化回测平台.exe
) else (
    echo  ⚠ 打包可能未完成，请检查错误信息
)
echo ================================
echo.
pause
