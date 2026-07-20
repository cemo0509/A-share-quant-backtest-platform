"""临时测试脚本：模拟打包环境启动后端"""
import sys, os

# 将 backend 目录加入 path
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

import uvicorn
uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
