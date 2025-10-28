import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

// 样式
import '@/styles/index.scss'

// 应用实例
const app = createApp(App)

// Element Plus图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// Pinia
const pinia = createPinia()
app.use(pinia)

// 路由
app.use(router)

// Element Plus
app.use(ElementPlus, {
  locale: zhCn,
})

// 挂载应用
app.mount('#app')

