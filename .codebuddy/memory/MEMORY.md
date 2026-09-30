# 项目长期记忆（A股量化回测平台）

## 运行环境（极易踩坑，必读）

### 后端：必须用 python-embed 的解释器
- **唯一可用解释器**：`python-embed\python.exe`（Python 3.11.9）——装有全部依赖
  （aiohttp 3.14.1 / pandas 3.0.3 / fastapi / uvicorn）。
- **⚠️ 嵌入式 Python 的 `sys.path` 不含当前目录，也不读 `PYTHONPATH`**（2026-09-30 实测）：
  所以 `cd backend` 后 `python-embed\python.exe xxx.py` 会报
  `ModuleNotFoundError: No module named 'core'`；`python -m xxx` 同样失败。
  临时脚本必须在开头写
  `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))`。
  （`pytest` 不受影响——它会自己把 rootdir 加进搜索路径，所以以前跑测试没暴露这个问题。）
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
- **2026-09-14 推送仍 403 的真正根因（已查证，非 URL 问题）**：
  远端返回 `Permission to cemo0509/... denied to cemo0509` —— GCM 已成功以
  `cemo0509` 登录，但该账号**对本仓库没有写权限**。本机 `git config user`
  是 `QuantDev/quantdev@example.com`（仅 commit 署名，与 GitHub 登录无关）。
  修复：在 Windows 凭据管理器删除 `git:https://github.com`（User: cemo0509）
  那条，再用**对该仓库有写权限的账号**重新登录即可。
  若重登仍 403，说明仓库真正 owner 是另一个账号，需换那个账号登录。
- **严格按需求边界，不顺手修范围外的模块**（2026-09-30 用户明确选择）：
  发现边界外缺陷时**先报告、由用户决定是否修**，不要自行顺手改。
  例：回测页 `Backtest.tsx` 只渲染 InputNumber，对 bool/select/list 参数渲染错位，
  用户选择"留到下次"，本次改造不得顺带修改。

## 策略编辑器改造（2026-09-30 评审，用户暂缓开工）
- 需求稿：桌面 `需求说明_策略编辑器改造与自定义策略页_2026-09-30.md`（用户与 WorkBuddy 对齐稿）。
- 目标形态：页面 A（`/strategy`）改为**纯参数调节**，右侧只显示所选策略自己的 params（**15 个策略全量适配**）；
  页面 B 新建「自定义策略」页承可视化编辑器；新增「另存为新策略」（参数固化成新记录，**不覆盖**原预置策略）。
- 已核实的后端基础（可直接用，无需新建参数接口）：
  - `backend/core/strategies/registry.py`：15 个策略 params 字段齐全（name/label/default/min/max/type/options/step）。
    三种特殊类型：`grid_trading.center_type`(select)、`adaptive.position_scale`(bool)、`factor_score.factor_weights`(list)。
  - `GET /api/strategy/list` 已返回全部策略 params；`GET /api/strategy/{key}` 已存在。
  - 回测 `engine.run_backtest(strategy_key, params)` 走 `get_strategy()` 取类 + 注入参数（按策略类声明过滤）
    → **「预置 key + 参数字典」式策略在回测侧可行**，只需扩展 `get_strategy` 支持变体。
  - `POST /api/strategy/custom/save` 只存 Python 源码（`strategies/custom/*.py`），**不适用**参数化保存。
- 方案要点（已与用户对齐）：
  - Q1 参数面板：用 `/api/strategy/list` 的 params（不用逐请求 `/{key}`，切换零延迟、天然同步）；
    抽公共组件按 type 渲染（int/float→InputNumber、bool→Switch、select→Select、list→4 个数字框）。
  - Q2 页面 B：新建 `CustomStrategy.tsx` 页面壳，**整体复用 `VisualEditor` 组件**（自带保存/生成代码/回测闭环）。
  - Q3 存储：新增参数化变体 `variants/<key>.json`（key/name/base_key/params）+ 扩展 `get_strategy`
    + `list_strategies` 合并 + 新接口 `POST /api/strategy/variant/save`。
- **已于 2026-09-30 实施完成并推送（commit `ddf93ee`）**：① 代码模式（Monaco）按决策直接移除；
  ② 严格按边界，回测页 `Backtest.tsx` 未动；③ 已验证：15 个策略参数与需求附件逐条一致，
  类型全覆盖（int 42 / float 24 / select 2 / bool 1 / list 1）；
  变体回测确认固化参数生效（另存 5/10 → 8 笔交易，默认 5/20 → 3 笔，结果不同）。
- ⚠️ 遗留待确认：移除代码编辑后，已保存的 Python 自定义策略（`strategies/custom/*.py`）**没有编辑入口**
  （回测页仍可选到），是否需要保留删除/管理入口。

## UI 升级状态（重要：它从未进入 git）
- 2026-07-20 的 UI 升级改了 **15 个前端文件**（`App.tsx` / `index.css` / 各页面 / `stores/index.ts`），
  但**只存在于快照目录** `version_snapshots\v1.1.4_UI_upgraded_20260720`，**从未 commit**。
  对照快照：`v1.1.4_pre_UI_upgrade_20260720`（升级前）。
- 2026-09-30 哈希核验当前工作区：pre 版 5 个、**UI 升级版 0 个**，其余 10 个是后来
  9/2 整改（S-03/S-04/F-02…）与 9/14 新功能改过的 → **当前代码不含 UI 升级**。
- 推论：以 GitHub 最新代码打包 = **不含 UI 升级**（但含因子选股器 + 同花顺式 FactorEditor）。
  若哪天要把 UI 升级找回来，源头只有那个快照目录（且需与后续改动合并）。
- 含 UI 升级的旧构建产物已备份：`version_snapshots\dist_backup_with_UI_upgrade_20260914`（507 文件）。

## 打包速查（electron-builder）
- 版本号在**项目根** `package.json` 的 `version`（electron-builder 读它产出文件名）。
  electron 配置在根目录 `electron-builder.yml`（注意：electron 目录下**没有** package.json）。
- 完整流程：`npm run build`（frontend）→ 覆盖 `electron\dist` → `npm run dist`（根）。
  `npm run dist` = electron-builder，需 NSIS：`$env:PATH += ';C:\Program Files (x86)\NSIS\Bin'`。
- 2026-09-30 用此流程产出 v1.1.5（189.4 MB，耗时很短）。

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

## 核验 GitHub 代码时必须绕开 CDN 缓存（重要，会制造"改动没生效"的假象）
- 通过 `raw.githubusercontent.com` 核验**刚推送**的代码时，会命中 CDN 旧副本
  （raw 响应带约 5 分钟 max-age），看起来像"改动根本没提交"。
- 所有 raw URL **一律带 cache-buster**，例如：
  `.../stores/index.ts?cb=20260902175600`
- **⚠️ 本仓库是私有仓库：raw.githubusercontent.com 未授权时返回 404 页面（不是文件内容）**。
  2026-09-30 用它核验 UI 升级状态时，5 个文件哈希全部被判为"与快照都不同"，
  是彻底的假象。**核验远端代码只能用 git 对象**（`git fetch` 后比对
  `origin/main` 与本地 HEAD / blob），不要依赖 raw 下载内容。
- 这是 WorkBuddy 在 2026-09-02 复核时差点误判的根因——它第一次拉到旧代码，
  险些判定"一条都没改"，加 cache-buster 重拉才拿到真实版本。
- 同理，任何"推送后立刻核验"的场景都要留意这个时间窗。
