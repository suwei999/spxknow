import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// 从环境变量获取后端地址，默认 192.168.131.158:8081
const getBackendTarget = () => {
  const apiBaseUrl = process.env.VITE_API_BASE_URL || 'http://192.168.131.158:8081/api'
  // 移除 /api 后缀，获取基础地址
  return apiBaseUrl.replace('/api', '')
}

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        target: getBackendTarget(),
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
    minify: 'terser',
    chunkSizeWarningLimit: 1000
  }
})

