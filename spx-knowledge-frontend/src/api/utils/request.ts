import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAppStore } from '@/stores/modules/app'

const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
  timeout: 30000
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
    } else {
      return res
    }
  },
  (error) => {
    const appStore = useAppStore()
    appStore.setLoading(false)
    
    let message = '请求失败'
    if (error.response) {
      message = error.response.data?.message || error.message
    }
    
    ElMessage.error(message)
    return Promise.reject(error)
  }
)

export default service

