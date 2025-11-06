import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAppStore } from '@/stores/modules/app'

const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
  timeout: 120000 // 2 分钟，避免 rerank 等长耗时请求超时
})

// 请求拦截器
service.interceptors.request.use(
  (config) => {
    const appStore = useAppStore()
    
    // 添加loading
    appStore.setLoading(true)
    
    // 添加token（如果有）
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    
    // 如果是 FormData，让浏览器自动设置 Content-Type（包括 boundary）
    // 不要手动设置，否则会丢失 boundary 信息
    if (config.data instanceof FormData) {
      delete config.headers['Content-Type']
    }
    
    return config
  },
  (error) => {
    appStore.setLoading(false)
    return Promise.reject(error)
  }
)

// 响应拦截器
service.interceptors.response.use(
  (response) => {
    const appStore = useAppStore()
    appStore.setLoading(false)
    
    const res = response.data
    
    // 检查响应格式：如果有 code 字段，需要验证
    if (res && typeof res === 'object' && 'code' in res) {
      if (res.code !== 200 && res.code !== 0) {
        ElMessage.error(res.message || 'Error')
        
        // 401: 未登录
        if (res.code === 401) {
          ElMessageBox.confirm('登录状态已过期，请重新登录', '提示', {
            confirmButtonText: '重新登录',
            cancelButtonText: '取消',
            type: 'warning'
          }).then(() => {
            // 重新登录逻辑
          })
        }
        
        return Promise.reject(new Error(res.message || 'Error'))
      }
    }
    // 如果没有 code 字段，直接返回响应（兼容直接返回数据的格式）
    return res
  },
  (error) => {
    const appStore = useAppStore()
    appStore.setLoading(false)
    
    let message = '请求失败'
    if (error.response) {
      // FastAPI HTTPException 返回格式: {detail: "..."}
      const detail = error.response.data?.detail
      if (detail) {
        message = typeof detail === 'string' ? detail : JSON.stringify(detail)
      } else {
        message = error.response.data?.message || error.message
      }
      // 只在非 404 错误时显示错误消息（404 可能是正常的业务逻辑）
      if (error.response.status !== 404) {
        ElMessage.error(message)
      }
    } else {
      ElMessage.error(message)
    }
    
    return Promise.reject(error)
  }
)

export default service

