import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    port: 5173,
  },
  build: {
    // 提升警告阈值，避免正常拆分下的噪声
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        // 将体积大且稳定的第三方库拆分为独立 vendor chunk，利用浏览器长缓存
        manualChunks: {
          echarts: ['echarts'],
          antd: ['antd', '@ant-design/icons'],
          charts: ['lightweight-charts'],
          editor: ['@monaco-editor/react', 'reactflow'],
          vendor: ['react', 'react-dom', 'react-router-dom', 'axios', 'dayjs', 'zustand'],
        },
      },
    },
  },
})
