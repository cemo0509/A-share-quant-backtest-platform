const { app, BrowserWindow, Menu } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const http = require('http')

let mainWindow = null
let backendProcess = null
let backendRetried = false
let backendRestarting = false
const BACKEND_PORT = 8000
const APP_NAME = 'A股量化回测平台'
const APP_VERSION = '1.1.4'

// ==================== 后端管理 ====================

/** 查找可用的 Python 解释器 */
function findPython() {
  // 优先使用打包在内置的嵌入式 Python
  if (app.isPackaged) {
    const resourcesPath = process.resourcesPath || path.join(process.execPath, '..', '..', 'resources')
    // 嵌入式 Python 路径
    const embedPython = path.join(resourcesPath, 'python', 'python.exe')
    if (require('fs').existsSync(embedPython)) {
      console.log(`[electron] 使用内置 Python: ${embedPython}`)
      return embedPython
    }
  }
  
  // 开发环境或内置 Python 不存在时，查找系统 Python
  const candidates = [
    process.env.PYTHON_PATH,
    'py',           // Windows Python Launcher（优先）
    'python',
    'python3',
    'C:\\Windows\\py.exe',
  ]
  
  // 测试每个候选，返回第一个能用的
  for (const candidate of candidates) {
    if (!candidate) continue
    try {
      const { execSync } = require('child_process')
      execSync(`${candidate} --version`, { stdio: 'ignore' })
      console.log(`[electron] 找到 Python: ${candidate}`)
      return candidate
    } catch (e) {
      // 继续尝试下一个
    }
  }
  
  return null  // 没找到返回 null
}

/** 显示 Python 未安装提示 */
function showPythonMissingDialog() {
  const { dialog, shell } = require('electron')
  const choice = dialog.showMessageBoxSync(mainWindow || BrowserWindow.getFocusedWindow(), {
    type: 'warning',
    title: '需要安装 Python',
    message: '未检测到 Python 安装',
    detail: '本软件需要 Python 3.8 或更高版本才能运行后端服务。\n\n请按以下步骤操作：\n1. 下载并安装 Python（安装时务必勾选 "Add Python to PATH"）\n2. 安装完成后重新启动本软件\n\n推荐下载：Python 3.11（国内镜像，速度更快）',
    buttons: ['打开国内镜像下载', '打开 Python 官网', '退出'],
    defaultId: 0,
    cancelId: 2,
  })
  
  if (choice === 0) {
    // 清华镜像站 - Python 3.11 最新版
    shell.openExternal('https://mirrors.tuna.tsinghua.edu.cn/python/')
  } else if (choice === 1) {
    shell.openExternal('https://www.python.org/downloads/')
  }
  
  app.quit()
}

/** 清理占用指定端口的进程 + 杀掉所有残留 Python 进程（Windows） */
function killPortProcess(port) {
  if (process.platform !== 'win32') return
  const { execSync } = require('child_process')
  
  // 1. 杀掉所有 python / pythonw 进程（彻底清理上一个实例的残留）
  try {
    console.log('[electron] 清理所有残留 Python 进程...')
    execSync('taskkill /F /IM python.exe 2>nul & taskkill /F /IM pythonw.exe 2>nul', { timeout: 5000 })
  } catch (e) {
    // 没有进程在运行时会报错，忽略
  }
  
  // 2. 精确清理占用目标端口的进程
  try {
    const output = execSync(`netstat -ano | findstr :${port}`, { encoding: 'utf8', timeout: 3000 })
    const lines = output.trim().split('\n')
    const pids = new Set()
    for (const line of lines) {
      const regex = new RegExp(`:${port}\\s+.*LISTENING\\s+(\\d+)`)
      const match = line.match(regex)
      if (match) pids.add(match[1])
    }
    for (const pid of pids) {
      console.log(`[electron] 端口 ${port} 被 PID ${pid} 占用，正在清理...`)
      execSync(`taskkill /F /PID ${pid}`, { timeout: 3000 })
      console.log(`[electron] PID ${pid} 已终止`)
    }
  } catch (e) {
    console.log(`[electron] 端口 ${port} 清理结果: ${e.message}`)
  }
  
  // 3. 等待 TIME_WAIT 释放（默认 120s，等待 5s 足够大多数情况）
  console.log('[electron] 等待端口 TIME_WAIT 释放 (5s)...')
  try {
    execSync('timeout /t 5 /nobreak >nul', { timeout: 8000 })
  } catch (e) {
    // timeout 可能被中断，忽略
  }
  console.log('[electron] 端口清理完成')
}

/** 启动后端服务 */
function startBackend() {
  const pythonPath = findPython()
  
  // 检查 Python 是否可用
  if (!pythonPath) {
    console.error('[electron] 未找到 Python，无法启动后端')
    // 延迟显示对话框，确保窗口已创建
    setTimeout(() => showPythonMissingDialog(), 1000)
    return
  }

  // 启动前清理可能残留的端口占用
  killPortProcess(BACKEND_PORT)
  
  // 开发环境: <project>/backend
  // 打包环境: <appRoot>/resources/backend
  let backendDir
  if (app.isPackaged) {
    // 打包后: process.resourcesPath 就是 <appRoot>/resources
    const resourcesPath = process.resourcesPath || path.join(process.execPath, '..', '..', 'resources')
    backendDir = path.join(resourcesPath, 'backend')
  } else {
    // 开发环境
    backendDir = path.join(__dirname, '..', '..', 'backend')
  }
  
  console.log(`[electron] 后端目录: ${backendDir}`)
  console.log(`[electron] 后端目录是否存在: ${require('fs').existsSync(backendDir)}`)

  // 检查后端目录是否存在
  if (!require('fs').existsSync(backendDir)) {
    console.error(`[electron] 后端目录不存在: ${backendDir}`)
    setTimeout(() => {
      const { dialog } = require('electron')
      dialog.showMessageBoxSync(mainWindow || BrowserWindow.getFocusedWindow(), {
        type: 'error',
        title: '后端文件缺失',
        message: '后端文件不完整',
        detail: `找不到后端目录：\n${backendDir}\n\n请重新安装本软件。`,
        buttons: ['确定'],
      })
    }, 1000)
    return
  }

  console.log(`[electron] 启动后端: ${pythonPath} main.py (cwd: ${backendDir})`)

  // 构建环境变量：确保嵌入式 Python 目录在 PATH 中
  const env = { ...process.env }
  if (app.isPackaged) {
    const pythonDir = path.dirname(pythonPath)
    env.PATH = `${pythonDir};${env.PATH || ''}`
    console.log(`[electron] 已添加 Python 到 PATH: ${pythonDir}`)
  }

  backendProcess = spawn(pythonPath, ['-u', 'main.py'], {
    cwd: backendDir,
    shell: true,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: env,
  })

  backendProcess.stdout.on('data', (data) => {
    const text = data.toString().trim()
    if (text) console.log(`[backend] ${text}`)
  })

  backendProcess.stderr.on('data', (data) => {
    const text = data.toString().trim()
    if (text) console.error(`[backend:err] ${text}`)
  })

  backendProcess.on('error', (err) => {
    console.error(`[electron] 后端启动失败:`, err.message)
    backendProcess = null
    // 如果后端启动失败且是第一次，尝试重试
    if (!backendRetried) {
      backendRetried = true
      console.log('[electron] 后端启动失败，3秒后重试...')
      setTimeout(() => {
        killPortProcess(BACKEND_PORT)
        setTimeout(() => startBackend(), 500)
      }, 3000)
    }
  })

  backendProcess.on('close', (code) => {
    console.log(`[electron] 后端退出 (code=${code})`)
    backendProcess = null
    // 异常退出时自动重启一次
    if (code !== 0 && !backendRestarting) {
      backendRestarting = true
      console.log(`[electron] 后端异常退出，3秒后重启...`)
      setTimeout(() => {
        backendRestarting = false
        killPortProcess(BACKEND_PORT)
        setTimeout(() => startBackend(), 500)
      }, 3000)
    }
  })
}

/** 轮询后端健康检查，就绪后加载前端 */
function waitForBackend(retries = 30, interval = 1000) {
  return new Promise((resolve, reject) => {
    let attempts = 0

    const check = () => {
      attempts++
      const req = http.get(`http://127.0.0.1:${BACKEND_PORT}/api/health`, (res) => {
        if (res.statusCode === 200) {
          console.log(`[electron] 后端就绪 (${attempts} 次尝试)`)
          res.resume()
          resolve()
        } else {
          res.resume()
          retry()
        }
      })

      req.on('error', () => retry())
      req.setTimeout(2000, () => {
        req.destroy()
        retry()
      })
    }

    const retry = () => {
      if (attempts >= retries) {
        reject(new Error(`后端启动超时（已尝试 ${retries} 次）`))
        return
      }
      setTimeout(check, interval)
    }

    check()
  })
}

/** 停止后端（Windows 上需杀死整个进程树 + 所有 Python） */
function stopBackend() {
  if (process.platform === 'win32') {
    // 彻底清理：先杀进程树，再杀所有残留 Python
    if (backendProcess) {
      console.log('[electron] 正在停止后端进程树...')
      try {
        require('child_process').execSync(`taskkill /PID ${backendProcess.pid} /F /T 2>nul`, { timeout: 5000 })
      } catch (e) { /* ignore */ }
      backendProcess = null
    }
    // 确保所有 Python 进程都被杀掉
    try {
      require('child_process').execSync('taskkill /F /IM python.exe 2>nul & taskkill /F /IM pythonw.exe 2>nul', { timeout: 5000 })
    } catch (e) { /* ignore - 没有进程时命令返回非零 */ }
    console.log('[electron] 后端已完全停止')
  } else {
    if (backendProcess) {
      backendProcess.kill('SIGTERM')
      backendProcess = null
    }
  }
}

// ==================== 窗口管理 ====================

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    title: APP_NAME,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, 'preload.js'),
    },
  })

  const isDev = !app.isPackaged

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
    mainWindow.webContents.openDevTools()
  } else {
    // 打包环境：尝试多个可能的前端文件路径
    const possiblePaths = [
      // electron-builder 配置：files 包含 frontend/dist/**
      // 实际位置：resources/app.asar/frontend/dist/index.html
      path.join(process.resourcesPath, 'app.asar', 'frontend', 'dist', 'index.html'),
      // 解压后：resources/frontend/dist/index.html
      path.join(process.resourcesPath, 'frontend', 'dist', 'index.html'),
      // 另一种可能：resources/app/frontend/dist/index.html
      path.join(process.resourcesPath, 'app', 'frontend', 'dist', 'index.html'),
      // 开发环境打包：__dirname/../frontend/dist/index.html
      path.join(__dirname, '..', 'frontend', 'dist', 'index.html'),
      // win-unpacked 环境
      path.join(__dirname, '..', '..', 'frontend', 'dist', 'index.html'),
    ]

    let frontEndPath = null
    for (const p of possiblePaths) {
      console.log(`[electron] 检查前端路径: ${p}`)
      if (require('fs').existsSync(p)) {
        frontEndPath = p
        console.log(`[electron] 找到前端文件: ${p}`)
        break
      }
    }

    if (frontEndPath) {
      console.log(`[electron] 加载前端: ${frontEndPath}`)
      mainWindow.loadFile(frontEndPath)
    } else {
      console.error(`[electron] 找不到前端文件，已尝试：`, possiblePaths)
      // 显示详细错误页面
      const errorHtml = `
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"><title>加载错误</title></head>
        <body style="font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#f0f2f5">
          <div style="text-align:center;padding:40px;background:white;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.1)">
            <h2 style="color:#ff4d4f;margin-bottom:20px">加载错误</h2>
            <p style="color:#666;margin-bottom:10px">找不到前端文件</p>
            <p style="color:#999;font-size:12px">请检查打包配置或联系开发者</p>
            <hr style="margin:20px 0;border:none;border-top:1px solid #eee">
            <p style="color:#999;font-size:11px">已尝试的路径：</p>
            <ul style="text-align:left;color:#999;font-size:11px;max-height:200px;overflow-y:auto">
              ${possiblePaths.map(p => `<li>${p}</li>`).join('')}
            </ul>
          </div>
        </body>
        </html>
      `
      mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(errorHtml)}`)
    }
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  // 设置应用菜单
  const menuTemplate = [
    {
      label: '文件',
      submenu: [
        { role: 'quit', label: '退出' },
      ],
    },
    {
      label: '视图',
      submenu: [
        { role: 'reload', label: '刷新' },
        { role: 'toggleDevTools', label: '开发者工具' },
        { type: 'separator' },
        { role: 'zoomIn', label: '放大' },
        { role: 'zoomOut', label: '缩小' },
        { role: 'resetZoom', label: '重置缩放' },
      ],
    },
    {
      label: '帮助',
      submenu: [
        {
          label: '关于',
          click: () => {
            const { dialog } = require('electron')
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: '关于',
              message: `${APP_NAME} v${APP_VERSION}`,
              detail: '基于 Backtrader + FastAPI + React + Electron\n面向 A 股市场的桌面端量化回测与策略开发平台',
            })
          },
        },
      ],
    },
  ]
  Menu.setApplicationMenu(Menu.buildFromTemplate(menuTemplate))
}

// ==================== 应用生命周期 ====================

app.whenReady().then(async () => {
  console.log('[electron] 应用启动，正在启动后端...')
  startBackend()

  // 等待后端启动就绪后再创建窗口，避免用户在后端就绪前操作触发
  // ERR_CONNECTION_REFUSED / 500（启动窗口期竞态）。超时也降级创建窗口，
  // 交给前端 axios 重试机制兜底。
  waitForBackend().then(() => {
    console.log('[electron] 后端启动成功')
    createWindow()
  }).catch((err) => {
    console.error('[electron] 后端启动失败，降级直接加载前端：', err.message)
    createWindow()
  })

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  stopBackend()
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  stopBackend()
})
