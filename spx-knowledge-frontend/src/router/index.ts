import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

// 路由配置
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Layout',
    component: () => import('@/components/layout/AppLayout.vue'),
    redirect: '/home',
    children: [
      {
        path: 'home',
        name: 'Home',
        component: () => import('@/views/Home.vue'),
        meta: {
          title: '首页',
          keepAlive: true
        }
      },
      {
        path: 'knowledge-bases',
        name: 'KnowledgeBases',
        component: () => import('@/views/KnowledgeBases/index.vue'),
        meta: {
          title: '知识库管理',
          keepAlive: true
        }
      },
      {
        path: 'knowledge-bases/create',
        name: 'KnowledgeBaseCreate',
        component: () => import('@/views/KnowledgeBases/create.vue'),
        meta: {
          title: '创建知识库',
          keepAlive: false
        }
      },
      {
        path: 'knowledge-bases/:id',
        name: 'KnowledgeBaseDetail',
        component: () => import('@/views/KnowledgeBases/detail.vue'),
        meta: {
          title: '知识库详情',
          keepAlive: false
        }
      },
      {
        path: 'knowledge-bases/:id/edit',
        name: 'KnowledgeBaseEdit',
        component: () => import('@/views/KnowledgeBases/edit.vue'),
        meta: {
          title: '编辑知识库',
          keepAlive: false
        }
      },
      {
        path: 'documents/:id',
        name: 'DocumentDetail',
        component: () => import('@/views/Documents/detail.vue'),
        meta: {
          title: '文档详情',
          keepAlive: false
        }
      },
      {
        path: 'documents/:id/edit',
        name: 'DocumentEdit',
        component: () => import('@/views/Documents/edit.vue'),
        meta: {
          title: '编辑文档',
          keepAlive: false
        }
      },
      {
        path: 'documents/:id/versions',
        name: 'DocumentVersions',
        component: () => import('@/views/Documents/versions.vue'),
        meta: {
          title: '文档版本',
          keepAlive: false
        }
      },
      {
        path: 'search/results',
        name: 'SearchResults',
        component: () => import('@/views/Search/results.vue'),
        meta: {
          title: '搜索结果',
          keepAlive: false
        }
      },
      {
        path: 'qa/chat',
        name: 'QAChat',
        component: () => import('@/views/QA/chat.vue'),
        meta: {
          title: '智能问答',
          keepAlive: false
        }
      },
      {
        path: 'qa/history',
        name: 'QAHistory',
        component: () => import('@/views/QA/history.vue'),
        meta: {
          title: '问答历史',
          keepAlive: true
        }
      },
      {
        path: 'images/search',
        name: 'ImageSearch',
        component: () => import('@/views/Images/search.vue'),
        meta: {
          title: '图片搜索',
          keepAlive: false
        }
      },
      {
        path: 'images/:id',
        name: 'ImageViewer',
        component: () => import('@/views/Images/viewer.vue'),
        meta: {
          title: '图片详情',
          keepAlive: false
        }
      },
      {
        path: 'documents/upload',
        name: 'DocumentUpload',
        component: () => import('@/views/Documents/upload.vue'),
        meta: {
          title: '文档上传',
          keepAlive: false
        }
      },
      {
        path: 'documents',
        name: 'Documents',
        component: () => import('@/views/Documents/index.vue'),
        meta: {
          title: '文档管理',
          keepAlive: true
        }
      },
      {
        path: 'search',
        name: 'Search',
        component: () => import('@/views/Search/index.vue'),
        meta: {
          title: '搜索',
          keepAlive: false
        }
      },
      {
        path: 'qa',
        name: 'QA',
        component: () => import('@/views/QA/index.vue'),
        meta: {
          title: '智能问答',
          keepAlive: true
        }
      },
      {
        path: 'images',
        name: 'Images',
        component: () => import('@/views/Images/index.vue'),
        meta: {
          title: '图片管理',
          keepAlive: true
        }
      },
      {
        path: 'observability',
        name: 'Observability',
        component: () => import('@/views/Observability/index.vue'),
        meta: {
          title: '运维诊断',
          keepAlive: false
        }
      }
    ]
  },
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import('@/views/Error/403.vue')
  },
  {
    path: '/500',
    name: 'ServerError',
    component: () => import('@/views/Error/500.vue')
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/Error/404.vue')
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

// 路由守卫
import { useAppStore } from '@/stores/modules/app'

router.beforeEach((to, from, next) => {
  const appStore = useAppStore()
  
  // 设置标题
  if (to.meta?.title) {
    document.title = `${to.meta.title} - ${appStore.appTitle}`
  }
  
  next()
})

export default router

