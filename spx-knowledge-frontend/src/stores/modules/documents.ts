import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getDocuments } from '@/api/modules/documents'
import type { Document, PaginationResult } from '@/types'

export const useDocumentsStore = defineStore('documents', () => {
  // 状态
  const list = ref<Document[]>([])
  const current = ref<Document | null>(null)
  const loading = ref(false)
  const total = ref(0)

  // Actions
  const fetchList = async (params?: { 
    knowledge_base_id?: number
    page?: number
    size?: number
  }) => {
    loading.value = true
    try {
      const res = await getDocuments(params || {})
      list.value = res.data.items
      total.value = res.data.total
    } catch (error) {
      console.error('获取文档列表失败:', error)
    } finally {
      loading.value = false
    }
  }

  const setCurrent = (doc: Document) => {
    current.value = doc
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

