const { contextBridge, ipcRenderer } = require('electron')

// 通过 preload 暴露安全的 API 给渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform,
  versions: {
    node: process.versions.node,
    chrome: process.versions.chrome,
    electron: process.versions.electron,
  },
  // 后端状态
  getBackendUrl: () => `http://127.0.0.1:${process.env.BACKEND_PORT || 8000}`,
})
