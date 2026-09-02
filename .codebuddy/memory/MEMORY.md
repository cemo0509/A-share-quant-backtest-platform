# 项目长期记忆（A股量化回测平台）

## 运行环境（极易踩坑，必读）

### 后端：必须用 python-embed 的解释器
- **唯一可用解释器**：`python-embed\python.exe`（Python 3.11.9）——装有全部依赖
  （aiohttp 3.14.1 / pandas 3.0.3 / fastapi / uvicorn）。
- 系统里**另外两个 Python 都缺依赖，启动必崩**：
  - `py` → Python 3.14.6（`AppData\Local\Python\pythoncore-3.14-64`）：`ModuleNotFoundError: No module named 'aiohttp'`
  - uv 的 `Astral\CPython3.12.14`（`AppData\Roaming\uv\python\...`）：同样缺 aiohttp
  - 注意：`python` 命令本身**不存在**（只有 Microsoft Store 别名）。
- 启动方式：工作目录 = `backend`，执行 `python-embed\python.exe main.py`
  → uvicorn 监听 `127.0.0.1:8000`（main.py 的 `__main__` 硬编码 port=8000）。
- 健康检查：`GET http://127.0.0.1:8000/api/health` → `{"status":"ok"}`

### 前端：vite 只监听 IPv6 回环
- 启动：工作目录 = `frontend`，执行 `node node_modules/vite/bin/vite.js`（等价 `npm run dev`）→ 端口 5173。
- **只监听 `::1`（IPv6）**：必须访问 `http://localhost:5173`；
  用 `127.0.0.1:5173` 探测会得到「down」的**假象**（实际服务正常）。
- 前端 axios baseURL 默认 `http://127.0.0.1:8000/api`（后端是 IPv4，可正常连通）。
- CORS：backend 用 `allow_origin_regex` 已放行 `localhost|127.0.0.1` 的 5173/5174/4173，前后端联调无跨域问题。

## 中文路径坑（重要）
项目根含中文：`C:\Users\22864\CodeBuddy\量化软件开发`
- PowerShell 脚本里**不能出现中文字面路径**：脚本编码会破坏中文，报
  `DirectoryNotFoundException`（历史坑：`cd <中文>; npx` 失败）。
- 正确做法：shell 默认已在项目根，用
  `$root = (Get-Location).Path` + `Join-Path $root 'backend'` 构造路径。
- `Start-Process -RedirectStandardError/-RedirectStandardOutput` 的相对路径是相对
  **调用者 cwd**，**不是** `-WorkingDirectory`（排查时日志会落在项目根，不在目标目录）。

## 路由速查
`/backtest` 回测 · `/optimize` 参数优化 · `/compare` 策略比较 ·
`/results` 回测结果 · `/history` 回测历史 · `/stock/:symbol` 个股 ·
`/stock-scan` 选股 · `/realtime-pool` 实时池 · `/strategy` 策略编辑器

## 启动速查（可直接复用）
```powershell
$root = (Get-Location).Path
$py = Join-Path $root 'python-embed\python.exe'
Start-Process -FilePath $py -ArgumentList 'main.py' `
  -WorkingDirectory (Join-Path $root 'backend') -WindowStyle Hidden
Start-Process -FilePath 'node' -ArgumentList 'node_modules/vite/bin/vite.js' `
  -WorkingDirectory (Join-Path $root 'frontend') -WindowStyle Hidden
# 验证：http://localhost:5173 与 http://127.0.0.1:8000/api/health
```
注意：排查用的 `*.log` 会被运行中的进程占用而无法删除，停服后再清理。

## 协作约定
- Web 开发策略：写完代码只保证**编译通过 + 冒烟 + 必要正确性检查**，
  **不做额外视觉校验**；观感/布局类由用户在浏览器确认。
- Git：remote 用干净 URL（`https://github.com/cemo0509/A-share-quant-backtest-platform.git`），
  认证交给 GCM，**禁止**把 token 内联进 remote URL。

## Dev 模式后端稳定性（坑过）
- `python-embed\python.exe main.py` 起的 uvicorn（reload=True）在 dev 模式下
  **子进程会无声退出**，导致 8000 突然 down；前端因 `getStrategies` 失败，
  `setStrategies([])` 让 Select **下拉框打开但没东西可选**——表现为"没法选"。
- 诊断（任意一条 down 都可定位）：
  ```powershell
  Get-Process python       # 空 = 后端进程已死
  Get-NetTCPConnection -State Listen -LocalPort 8000   # 空 = 没监听
  ```
- 恢复：用「启动速查」那段 Start-Process 再起一次即可（无需清理，下次同样会死）。
  若怀疑代码 bug，看根目录 `backend-err3.log`（上次启动的 stderr）。
