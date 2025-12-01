<template>
  <div class="documents-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>文档管理</span>
          <el-button type="primary" @click="handleUpload">上传文档</el-button>
        </div>
      </template>

      <el-table 
        ref="tableRef"
        :data="documents" 
        v-loading="loading"
        @selection-change="handleSelectionChange"
      >
        <!-- 添加选择列 -->
        <el-table-column type="selection" width="55" />
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
        <el-table-column prop="security_scan_status" label="安全扫描" width="120">
          <template #default="{ row }">
            <el-tag :type="getSecurityScanStatusType(row.security_scan_status || 'pending')" size="small">
              {{ getSecurityScanStatusText(row.security_scan_status || 'pending') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="AI标签" width="200">
          <template #default="{ row }">
            <div v-if="row.metadata?.auto_keywords && row.metadata.auto_keywords.length > 0">
              <el-tag
                v-for="(keyword, index) in row.metadata.auto_keywords.slice(0, 3)"
                :key="index"
                size="small"
                style="margin-right: 4px; margin-bottom: 4px;"
              >
                {{ keyword }}
              </el-tag>
              <el-tag v-if="row.metadata.auto_keywords.length > 3" size="small" type="info">
                +{{ row.metadata.auto_keywords.length - 3 }}
              </el-tag>
            </div>
            <span v-else style="color: #909399; font-size: 12px;">暂无标签</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="handleDetail(row)">详情</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 批量操作工具栏 -->
      <div v-if="selectedDocuments.length > 0" class="batch-toolbar">
        <span>已选择 {{ selectedDocuments.length }} 项</span>
        <el-button @click="showMoveDialog = true">批量移动</el-button>
        <el-button @click="showTagsDialog = true">批量标签</el-button>
        <el-button type="danger" @click="handleBatchDelete">批量删除</el-button>
        <el-button @click="clearSelection">取消选择</el-button>
      </div>

      <el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        @current-change="loadData"
      />
    </el-card>

    <!-- 批量移动对话框 -->
    <el-dialog v-model="showMoveDialog" title="批量移动文档" width="500px">
      <el-form :model="moveForm" label-width="100px">
        <el-form-item label="目标知识库" required>
          <el-select v-model="moveForm.target_knowledge_base_id" placeholder="请选择知识库" style="width: 100%">
            <el-option
              v-for="kb in knowledgeBases"
              :key="kb.id"
              :label="kb.name"
              :value="kb.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="目标分类（可选）">
          <el-input v-model="moveForm.target_category_id" placeholder="分类ID（可选）" type="number" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button class="dialog-cancel-btn" @click="showMoveDialog = false">取消</el-button>
        <el-button type="primary" @click="handleBatchMove">确定</el-button>
      </template>
    </el-dialog>

    <!-- 批量标签对话框 -->
    <el-dialog v-model="showTagsDialog" title="批量标签管理" width="500px">
      <el-form :model="tagsForm" label-width="100px">
        <el-form-item label="操作类型">
          <el-radio-group v-model="tagsForm.operation">
            <el-radio label="add">添加标签</el-radio>
            <el-radio label="remove">删除标签</el-radio>
            <el-radio label="replace">替换标签</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="标签">
          <el-input
            v-model="tagsForm.tags"
            type="textarea"
            :rows="3"
            placeholder="请输入标签，多个标签用逗号分隔"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button class="dialog-cancel-btn" @click="showTagsDialog = false">取消</el-button>
        <el-button type="primary" @click="handleBatchTags">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import { getDocuments, deleteDocument, batchDeleteDocuments, batchMoveDocuments, batchAddTags, batchRemoveTags, batchReplaceTags } from '@/api/modules/documents'
import { getKnowledgeBases } from '@/api/modules/knowledge-bases'
import type { KnowledgeBase } from '@/types'
import { formatFileSize } from '@/utils/format'
import { WebSocketClient } from '@/utils/websocketClient'
import type { Document } from '@/types'

const router = useRouter()

const documents = ref<Document[]>([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)
const selectedDocuments = ref<Document[]>([])
const showMoveDialog = ref(false)
const showTagsDialog = ref(false)
const knowledgeBases = ref<KnowledgeBase[]>([])

// 批量操作表单
const moveForm = ref({
  target_knowledge_base_id: null as number | null,
  target_category_id: null as number | null
})

const tagsForm = ref({
  operation: 'add' as 'add' | 'remove' | 'replace',
  tags: '' as string | string[]  // 支持字符串（逗号分隔）或数组
})

const loadData = async () => {
  loading.value = true
  try {
      const res = await getDocuments({ page: page.value, size: size.value })
      // 后端返回格式: { code: 0, message: "ok", data: { list: [], total: 0 } }
      // 响应拦截器已经返回了 response.data，所以 res 就是响应数据本身
      if (res && typeof res === 'object') {
      if (res.code === 0 && res.data) {
        documents.value = res.data.list ?? res.data.items ?? []
        total.value = res.data.total ?? 0
      } else if (res.data) {
        // 兼容没有 code 字段的格式
        documents.value = res.data.list ?? res.data.items ?? []
        total.value = res.data.total ?? 0
      } else {
        documents.value = []
        total.value = 0
      }
    } else {
      documents.value = []
      total.value = 0
    }
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || error.message || '加载失败')
    documents.value = []
    total.value = 0
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

// 表格选择变化
const handleSelectionChange = (selection: Document[]) => {
  selectedDocuments.value = selection
}

// 清空选择
const tableRef = ref()
const clearSelection = () => {
  tableRef.value?.clearSelection()
  selectedDocuments.value = []
}

// 批量删除
const handleBatchDelete = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedDocuments.value.length} 个文档吗？`,
      '批量删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const documentIds = selectedDocuments.value.map(d => d.id)
    const res = await batchDeleteDocuments(documentIds)
    
    if (res.code === 0) {
      ElMessage.success(`成功删除 ${res.data.deleted_count} 个文档`)
      if (res.data.failed_count > 0) {
        ElMessage.warning(`${res.data.failed_count} 个文档删除失败`)
      }
      clearSelection()
      loadData()
    } else {
      ElMessage.error(res.message || '批量删除失败')
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || error.message || '批量删除失败')
    }
  }
}

// 批量移动
const handleBatchMove = async () => {
  if (!moveForm.value.target_knowledge_base_id) {
    ElMessage.warning('请选择目标知识库')
    return
  }
  
  try {
    const documentIds = selectedDocuments.value.map(d => d.id)
    const res = await batchMoveDocuments({
      document_ids: documentIds,
      target_knowledge_base_id: moveForm.value.target_knowledge_base_id,
      target_category_id: moveForm.value.target_category_id || undefined
    })
    
    if (res.code === 0) {
      ElMessage.success(`成功移动 ${res.data.moved_count} 个文档`)
      if (res.data.failed_count > 0) {
        ElMessage.warning(`${res.data.failed_count} 个文档移动失败`)
      }
      showMoveDialog.value = false
      clearSelection()
      loadData()
    } else {
      ElMessage.error(res.message || '批量移动失败')
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || error.message || '批量移动失败')
  }
}

// 批量标签管理
const handleBatchTags = async () => {
  // 确保 tags 是数组格式
  let tagsArray: string[] = []
  if (Array.isArray(tagsForm.value.tags)) {
    tagsArray = tagsForm.value.tags
  } else if (typeof tagsForm.value.tags === 'string') {
    tagsArray = tagsForm.value.tags.split(',').map(t => t.trim()).filter(Boolean)
  }
  
  if (tagsArray.length === 0) {
    ElMessage.warning('请输入标签')
    return
  }
  
  try {
    const documentIds = selectedDocuments.value.map(d => d.id)
    let res: any
    
    if (tagsForm.value.operation === 'add') {
      res = await batchAddTags({
        document_ids: documentIds,
        tags: tagsArray
      })
    } else if (tagsForm.value.operation === 'remove') {
      res = await batchRemoveTags({
        document_ids: documentIds,
        tags: tagsArray
      })
    } else {
      res = await batchReplaceTags({
        document_ids: documentIds,
        tags: tagsArray
      })
    }
    
    if (res.code === 0) {
      const actionText = tagsForm.value.operation === 'add' ? '添加' : tagsForm.value.operation === 'remove' ? '删除' : '替换'
      ElMessage.success(`成功${actionText}标签`)
      showTagsDialog.value = false
      resetTagsForm()
      clearSelection()
      loadData()
    } else {
      ElMessage.error(res.message || '批量标签操作失败')
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || error.message || '批量标签操作失败')
  }
}

// 加载知识库列表
const loadKnowledgeBases = async () => {
  try {
    const res = await getKnowledgeBases({ page: 1, size: 1000 })
    const data = res?.data || res
    knowledgeBases.value = data?.list || data?.items || []
  } catch (error) {
    // 忽略错误
  }
}

// 重置标签表单
const resetTagsForm = () => {
  tagsForm.value = {
    operation: 'add',
    tags: ''
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

// 安全扫描状态类型
const getSecurityScanStatusType = (status: string) => {
  const map: Record<string, string> = {
    'safe': 'success',
    'infected': 'danger',
    'error': 'warning',
    'skipped': 'info',
    'scanning': 'warning',
    'pending': ''
  }
  return map[status] || 'info'
}

// 安全扫描状态文本
const getSecurityScanStatusText = (status: string) => {
  const map: Record<string, string> = {
    'safe': '安全',
    'infected': '感染',
    'error': '错误',
    'skipped': '跳过',
    'scanning': '扫描中',
    'pending': '待扫描'
  }
  return map[status] || status || '未知'
}

const wsClient = ref<WebSocketClient | null>(null)

// 初始化WebSocket监听
const initWebSocket = () => {
  // 使用环境变量或默认值构建WebSocket URL
  const wsBaseURL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000'
  const wsUrl = `${wsBaseURL}/ws/documents/status`
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
    // WebSocket 连接成功
  })
  
  wsClient.value.connect()
}

onMounted(() => {
  loadData()
  loadKnowledgeBases()
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

  .batch-toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px;
    margin-top: 16px;
    background-color: rgba(60, 130, 246, 0.1);
    border-radius: 4px;
    border: 1px solid rgba(60, 130, 246, 0.2);
  }

  :deep(.dialog-cancel-btn) {
    color: #cbd5f5;
    border-color: #475569;
    background-color: rgba(71, 85, 105, 0.2);
    transition: all 0.2s ease;
  }

  :deep(.dialog-cancel-btn:hover) {
    color: #ffffff;
    border-color: #60a5fa;
    background-color: rgba(96, 165, 250, 0.2);
  }
}
</style>

