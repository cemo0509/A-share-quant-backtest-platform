@echo off
chcp 65001 > nul
echo ================================
echo  启动量化回测平台（测试版）
echo ================================
echo.

REM 启动后端
echo [1/2] 启动后端...
start "后端" cmd /k "cd /d %~dp0backend && py -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"

REM 等待后端启动
timeout /t 3 > nul

REM 启动前端
echo [2/2] 启动前端...
start "前端" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ✅ 启动完成！
echo 后端: http://localhost:8000
echo 前端: http://localhost:5173
echo.
pause
