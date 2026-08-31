@echo off
chcp 65001 > nul
REM 添加 NSIS 到 PATH（生成 .exe 安装包必需）
set "PATH=%PATH%;C:\Program Files (x86)\NSIS\Bin"
echo ================================
echo  Packaging Quant Backtest Platform (Desktop v1.1.2)
echo ================================
echo.

REM Close occupying processes
echo [0/4] Closing occupying processes...
taskkill /f /im "A股量化回测平台.exe" > nul 2>&1
taskkill /f /im electron.exe > nul 2>&1
taskkill /f /im node.exe > nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %%a > nul 2>&1
timeout /t 3 > nul
echo [0/4] Done.

REM Remove old unpacked directory
echo [1/4] Removing old unpacked directory...
if exist "dist_build\win-unpacked" (
    rmdir /s /q "dist_build\win-unpacked"
    echo        ✓ Removed successfully
) else (
    echo        - Directory not found (skip)
)

REM Build frontend
echo [2/4] Building frontend...
cd /d %~dp0frontend
call "C:\Program Files\nodejs\npm.cmd" run build
if errorlevel 1 (
    echo [ERROR] Frontend build failed!
    pause
    exit /b 1
)

echo [3/4] Copying frontend to electron...
if not exist "..\electron\dist" mkdir "..\electron\dist"
xcopy /y /e dist\* ..\electron\dist\
if errorlevel 1 (
    echo [ERROR] Copy failed!
    pause
    exit /b 1
)

echo [4/4] Packaging desktop application...
cd /d %~dp0
call "C:\Program Files\nodejs\npm.cmd" run dist
if errorlevel 1 (
    echo [ERROR] Desktop packaging failed!
    pause
    exit /b 1
)

echo.
echo ================================
echo  Packaging completed successfully!
echo  Installer location: dist_build\ folder
echo ================================
echo.
REM pause removed: automated CI / CodeBuddy task panel should exit cleanly
exit /b 0
