import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getKnowledgeBases } from '@/api/modules/knowledge-bases'
import type { KnowledgeBase, PaginationResult } from '@/types'

export const useKnowledgeBasesStore = defineStore('knowledgeBases', () => {
  // 状态
  const list = ref<KnowledgeBase[]>([])
  const current = ref<KnowledgeBase | null>(null)
  const loading = ref(false)
  const total = ref(0)

  // Actions
  const fetchList = async (params?: { category_id?: number; status?: string; page?: number; size?: number }) => {
    loading.value = true
    try {
      const res = await getKnowledgeBases(params || {})
      list.value = res.data.items
      total.value = res.data.total
    } catch (error) {
      console.error('获取知识库列表失败:', error)
    } finally {
      loading.value = false
    }
  }

  const setCurrent = (kb: KnowledgeBase) => {
    current.value = kb
  }

  const clear = () => {
    list.value = []
    current.value = null
    total.value = 0
  }

  return {
    list,
    current,
    loading,
    total,
    fetchList,
    setCurrent,
    clear
  }
})

