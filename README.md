# A股量化回测平台

![版本](https://img.shields.io/badge/版本-v1.1.4-green)
![状态](https://img.shields.io/badge/状态-持续迭代-blue)
![许可证](https://img.shields.io/badge/许可证-MIT-orange)

面向 A 股市场的桌面端量化回测与策略开发平台。

## 🎉 v1.1.4 版本已发布！

当前桌面版具备完整的量化回测、可视化策略编辑、智能推荐、选股池、实时监控等功能。
安装包内置嵌入式 Python，用户无需额外安装 Python 环境。

### v1.1.4 更新内容
- **主题三态切换（明 / 暗 / 跟随系统）**：顶部由单一开关升级为「浅色 / 深色 / 跟随系统」三选项分段控件；选「跟随系统」时界面与全部图表实时跟随操作系统的明暗设置自动切换。

## 🎉 v1.1.3 版本已发布！

当前桌面版具备完整的量化回测、可视化策略编辑、智能推荐、选股池、实时监控等功能。
安装包内置嵌入式 Python，用户无需额外安装 Python 环境。

### v1.1.3 更新内容
- **路由跳转提速**：菜单空闲时预加载所有页面 chunk，点击跳转几乎无白屏；点击菜单前同步触发预加载。
- **前端构建分包优化**：将 `echarts` / `antd` / `lightweight-charts` / `monaco`+`reactflow` / 基础 vendor 拆分为独立长缓存 chunk，减少重复传输、提升二次加载速度。
- **细节修复**：图表组件卸载后 `ResizeObserver` 空引用崩溃（KLineChart / EquityCurve），策略比较「查看详情」弹窗资金曲线时间排序防御。

## 技术栈

- **回测引擎**：Backtrader
- **数据源**：AKShare（A股全量免费数据）
- **后端**：FastAPI (Python)
- **前端**：React + TypeScript + Ant Design (Vite)
- **图表**：Lightweight-Charts + ECharts
- **策略编辑器**：Monaco Editor + React Flow
- **桌面框架**：Electron

## 目录结构

```
量化软件开发/
├── electron/      # Electron 主进程
├── frontend/      # React 前端
├── backend/       # FastAPI 后端
└── docs/          # 文档
```

## 快速开始

### 后端

```bash
cd backend
pip install -r requirements.txt
python main.py          # 启动 FastAPI，默认 http://127.0.0.1:8000
```

### 前端

```bash
cd frontend
npm install
npm run dev             # 启动 Vite，默认 http://localhost:5173
```

### 桌面端（Electron）

```bash
npm install
npm run electron:dev
```

## 📦 v1.1.2 核心功能

### ✅ 已完成功能

- **策略管理** - 内置 14 个经典策略（双均线/MACD/RSI/KDJ/布林带/海龟/动量/网格/均值回归/自适应等）+ 自定义策略编辑器（Monaco Editor）
- **可视化策略编辑器** - React Flow 拖拽式条件编辑 + 智能推荐模式（4 个预设：MACD金叉/RSI超卖/KDJ金叉/均线多头）+ 两段式指标库
- **回测系统** - Backtrader 引擎，支持参数配置、资金曲线、交易明细、指标分析
- **参数优化** - 多进程参数网格搜索，按夏普比率排序
- **选股池** - 交互式条件选股（东财+同花顺融合）+ CCI+MACD 双因子选股
- **实时监控** - 盘中实时选股池，可组合因子定时扫描
- **个股详情** - K线/分时图 + 8 大技术指标叠加（MACD/KDJ/RSI/BOLL/WR/OBV/BIAS/CCI）
- **数据管理** - AKShare 数据源 + Parquet 本地缓存 + 实时行情
- **模拟交易** - 模拟账户、订单管理、持仓管理、交易记录
- **桌面应用** - Electron 封装 + NSIS 安装包 + 嵌入式 Python，用户无需安装 Python

### 📖 详细文档

- **三方协作同步** - 查看 `任务同步总览_三方协作.md`
- **WorkBuddy 参考** - 查看 `WorkBuddy同步说明.md`
- **功能清单** - 查看 `功能清单_当前已实现_v1.1.2.md`
- **代码审查报告** - 查看 `智能推荐模式代码审查报告_2026-07-11.md`

## 快速开始

### 环境要求

- **Node.js** (v16.0.0+) - [下载地址](https://nodejs.org/)
- **Python** (v3.8.0+) - [下载地址](https://www.python.org/)

### 方式一：从源代码运行

#### 1. 安装依赖

**前端依赖：**
```bash
cd frontend
npm install
cd ..
```

**后端依赖：**
```bash
cd backend
pip install -r requirements.txt
cd ..
```

#### 2. 启动应用

**Windows用户：**
```bash
# 双击运行启动脚本
start.bat
```

**Linux/macOS用户：**
```bash
bash start.sh
```

**或手动启动：**
```bash
# 终端1：启动后端
cd backend
python main.py

# 终端2：启动前端
cd frontend
npm run dev

# 终端3：启动Electron
npm run electron:dev
```

### 方式二：打包成桌面应用

```bash
# 1. 构建前端
npm run build:frontend

# 2. 打包Electron应用
npm run electron:build

# 3. 安装程序将位于 dist/ 目录
# Windows: A股量化回测平台-1.0.0-x64.exe
```

## 项目结构

```
量化软件开发/
├── backend/              # 后端服务（FastAPI + Backtrader）
│   ├── api/            # API路由
│   ├── core/           # 核心功能模块
│   └── main.py         # 后端入口
├── frontend/           # 前端应用（React + TypeScript）
│   ├── src/           # 源代码
│   └── dist/          # 构建输出
├── electron/           # Electron主进程
├── build/              # 打包资源
├── dist/               # 打包输出
├── electron-builder.yml # Electron打包配置
├── package.json        # 项目配置（版本v1.0.0）
├── start.bat          # Windows启动脚本
├── start.sh           # Linux/macOS启动脚本
├── README.md          # 本文件
├── README_V1.0.md     # v1.0版本详细说明
├── PACKAGING_GUIDE.md # 打包指南
├── VERSION_1.0_SUMMARY.md # 版本总结
└── DEPLOYMENT.md      # 部署文档
```

## 开发路线

### ✅ v1.0.0 (2026-07-02) - 已完成
1. **阶段一**：Backtrader 跑通最小回测闭环 ✅
2. **阶段二**：搭建前后端分离框架 ✅
3. **阶段三**：完善可视化策略编辑、步进推演、Electron 打包 ✅

### ✅ v1.1.x (2026-07) - 已完成
- 14 个预置策略（含自适应/因子评分/智能退出等） ✅
- 可视化策略编辑器 + 智能推荐模式 ✅
- 选股池 + 实时监控引擎 ✅
- 个股详情页 + 8 大技术指标 ✅
- 嵌入式 Python 打包 ✅

### 🔮 未来计划 (v1.2.0+)
- [ ] 双均线/布林带两列比较可视化支持
- [ ] 自动更新机制（electron-updater）
- [ ] 回测结果 PDF 报告导出
- [ ] 策略回测基准对比（Buy & Hold）
- [ ] 实盘交易接口对接

## 技术栈

- **回测引擎**：Backtrader
- **数据源**：AKShare（A股全量免费数据）
- **后端**：FastAPI (Python)
- **前端**：React + TypeScript + Ant Design (Vite)
- **图表**：ECharts
- **策略编辑器**：Monaco Editor
- **桌面框架**：Electron
- **打包工具**：electron-builder

## 常见问题

### Q: npm或python命令不可用？
**A**: 需要先安装Node.js和Python，并添加到系统PATH环境变量中。

### Q: 后端启动失败？
**A**: 检查端口8000是否被占用，或查看错误日志。

### Q: 前端构建失败？
**A**: 确保已进入frontend目录并执行`npm install`安装依赖。

### Q: Electron打包失败？
**A**: 确保已经执行`npm run build:frontend`构建前端，并检查所有依赖是否安装。

## 贡献与支持

欢迎提交Issue和Pull Request！

## 许可证

MIT License

---

## 📞 联系方式

如有问题或建议，请通过以下方式联系：
- 提交Issue
- 发送邮件

**⚠️ 免责声明**：本平台仅供学习和研究使用，不构成任何投资建议。使用本平台进行实盘交易的风险由用户自行承担。

**🎉 感谢使用A股量化回测平台 v1.1.2！**
