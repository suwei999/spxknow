<template>
  <div class="documents-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>文档管理</span>
          <el-button type="primary" @click="handleUpload">上传文档</el-button>
        </div>
      </template>

      <el-table :data="documents" v-loading="loading">
        <el-table-column prop="title" label="标题" />
        <el-table-column prop="file_name" label="文件名" />
        <el-table-column prop="file_type" label="类型" />
        <el-table-column prop="file_size" label="大小">
          <template #default="{ row }">
            {{ formatFileSize(row.file_size) }}
          </template>
        </el-table-column>
        <el-table-column prop="knowledge_base_name" label="所属知识库" />
        <el-table-column prop="status" label="状态" width="150">
          <template #default="{ row }">
            <div class="status-cell">
              <el-tag :type="getStatusType(row.status)">
                {{ getStatusText(row.status) }}
              </el-tag>
              <!-- 处理进度显示 -->
              <el-progress 
                v-if="row.status === 'processing' || row.status === 'parsing' || row.status === 'vectorizing'"
                :percentage="row.progress || 0"
                :status="row.progress === 100 ? 'success' : undefined"
                :stroke-width="4"
                style="margin-top: 5px"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="handleDetail(row)">详情</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        @current-change="loadData"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import { getDocuments, deleteDocument } from '@/api/modules/documents'
import { formatFileSize } from '@/utils/format'
import { WebSocketClient } from '@/utils/websocketClient'
import type { Document } from '@/types'

const router = useRouter()

const documents = ref<Document[]>([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)

const loadData = async () => {
  loading.value = true
  try {
    const res = await getDocuments({ page: page.value, size: size.value })
    const data = res?.data ?? {}
    documents.value = data.list ?? data.items ?? []
    total.value = data.total ?? 0
  } catch (error) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

const handleUpload = () => {
  router.push('/documents/upload')
}

const handleDetail = (row: Document) => {
  router.push(`/documents/${row.id}`)
}

const handleDelete = async (row: Document) => {
  try {
    await ElMessageBox.confirm('确定要删除该文档吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    await deleteDocument(row.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const getStatusType = (status: string) => {
  const map: Record<string, string> = {
    'completed': 'success',
    'processing': 'warning',
    'failed': 'danger',
    'pending': 'info'
  }
  return map[status] || 'info'
}

const getStatusText = (status: string) => {
  const map: Record<string, string> = {
    'completed': '已完成',
    'processing': '处理中',
    'failed': '失败',
    'pending': '待处理'
  }
  return map[status] || status
}

const wsClient = ref<WebSocketClient | null>(null)

// 初始化WebSocket监听
const initWebSocket = () => {
  const wsUrl = 'ws://localhost:8000/ws/documents/status'
  wsClient.value = new WebSocketClient(wsUrl)
  
  // 订阅文档状态更新
  wsClient.value.subscribe('status_update', (data: any) => {
    const document = documents.value.find(d => d.id === data.document_id)
    if (document) {
      document.status = data.status
      document.progress = data.progress
    }
  })
  
  // 连接回调
  wsClient.value.onConnect(() => {
    console.log('文档状态WebSocket已连接')
  })
  
  wsClient.value.connect()
}

onMounted(() => {
  loadData()
  initWebSocket()
})

onUnmounted(() => {
  if (wsClient.value) {
    wsClient.value.disconnect()
  }
})
</script>

<style lang="scss" scoped>
.documents-page {
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .status-cell {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  /* 降低表格 hover 亮度，提升可读性 */
  :deep(.el-table) {
    --el-table-row-hover-bg-color: rgba(180, 180, 180, 0.16);
  }
}
</style>

