@echo off
chcp 65001 > nul
echo ================================
echo  Closing all occupying processes
echo ================================
echo.

echo [1/5] Closing A股量化回测平台.exe...
taskkill /f /im "A股量化回测平台.exe" > nul 2>&1
if %errorlevel% equ 0 (
    echo        ✓ Closed successfully
) else (
    echo        - Process not found (skip)
)

echo [2/5] Closing electron.exe...
taskkill /f /im electron.exe > nul 2>&1
if %errorlevel% equ 0 (
    echo        ✓ Closed successfully
) else (
    echo        - Process not found (skip)
)

echo [3/5] Closing node.exe...
taskkill /f /im node.exe > nul 2>&1
if %errorlevel% equ 0 (
    echo        ✓ Closed successfully
) else (
    echo        - Process not found (skip)
)

echo [4/5] Closing npm processes...
taskkill /f /im npm.cmd > nul 2>&1
taskkill /f /im npx.cmd > nul 2>&1
echo        ✓ Done

echo [4.5/5] Closing processes holding backend port 8000 (兜底清理残留后端)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %%a > nul 2>&1
echo        ✓ Done

echo [5/5] Waiting for processes to fully close...
timeout /t 3 > nul
echo        ✓ Done

echo.
echo ================================
echo  All occupying processes closed!
echo  You can now run: 打包桌面版.cmd
echo ================================
echo.

pause
