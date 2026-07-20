@echo off
echo === 测试嵌入式 Python 后端启动 ===

echo [1] 启动后端...
start "" "%~dp0python-embed\python.exe" "%~dp0test_backend.py"

echo [2] 等待后端就绪...
set COUNT=0
:loop
timeout /t 1 /nobreak > nul
set /a COUNT+=1
curl -s http://127.0.0.1:8000/api/health > nul 2>&1 && goto :ok
if %COUNT% LSS 15 goto :loop

echo [FAIL] 后端启动超时!
type "%~dp0backend_test.log" 2>nul
goto :cleanup

:ok
echo [OK] 后端启动成功！
curl -s http://127.0.0.1:8000/api/health

:cleanup
echo [3] 关闭后端...
taskkill /f /im python.exe > nul 2>&1
echo 测试完成
pause
