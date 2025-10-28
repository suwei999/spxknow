<template>
  <div class="knowledge-base-detail-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>知识库详情</span>
          <div>
            <el-button @click="handleEdit">编辑</el-button>
            <el-button type="danger" @click="handleDelete">删除</el-button>
          </div>
        </div>
      </template>

      <div v-if="detail" class="detail-content">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="名称">{{ detail.name }}</el-descriptions-item>
          <el-descriptions-item label="分类">{{ detail.category_name }}</el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">{{ detail.description }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="detail.status === 'active' ? 'success' : 'info'">
              {{ detail.status }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(detail.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ formatDateTime(detail.updated_at) }}</el-descriptions-item>
        </el-descriptions>

        <el-divider>文档列表</el-divider>

        <el-table :data="documents" v-loading="documentsLoading">
          <el-table-column prop="title" label="标题" />
          <el-table-column prop="file_name" label="文件名" />
          <el-table-column prop="file_type" label="类型" />
          <el-table-column prop="status" label="状态">
            <template #default="{ row }">
              <el-tag :type="getStatusType(row.status)">{{ getStatusText(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作">
            <template #default="{ row }">
              <el-button size="small" @click="viewDocument(row)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          v-model:current-page="docPage"
          v-model:page-size="docSize"
          :total="docTotal"
          @current-change="loadDocuments"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import { getKnowledgeBaseDetail, deleteKnowledgeBase } from '@/api/modules/knowledge-bases'
import { getDocuments } from '@/api/modules/documents'
import { formatDateTime } from '@/utils/format'
import type { KnowledgeBase, Document } from '@/types'

const route = useRoute()
const router = useRouter()
const knowledgeBaseId = Number(route.params.id)

const detail = ref<KnowledgeBase | null>(null)
const documents = ref<Document[]>([])
const documentsLoading = ref(false)
const docPage = ref(1)
const docSize = ref(20)
const docTotal = ref(0)

const loadDetail = async () => {
  try {
    const res = await getKnowledgeBaseDetail(knowledgeBaseId)
    detail.value = res.data
  } catch (error) {
    ElMessage.error('加载详情失败')
    router.back()
  }
}

const loadDocuments = async () => {
  documentsLoading.value = true
  try {
    const res = await getDocuments({
      knowledge_base_id: knowledgeBaseId,
      page: docPage.value,
      size: docSize.value
    })
    documents.value = res.data.items
    docTotal.value = res.data.total
  } catch (error) {
    ElMessage.error('加载文档列表失败')
  } finally {
    documentsLoading.value = false
  }
}

const handleEdit = () => {
  router.push(`/knowledge-bases/${knowledgeBaseId}/edit`)
}

const handleDelete = async () => {
  try {
    await ElMessageBox.confirm('确定要删除该知识库吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    await deleteKnowledgeBase(knowledgeBaseId)
    ElMessage.success('删除成功')
    router.push('/knowledge-bases')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const viewDocument = (doc: Document) => {
  router.push(`/documents/${doc.id}`)
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

onMounted(() => {
  loadDetail()
  loadDocuments()
})
</script>

<style lang="scss" scoped>
.knowledge-base-detail-page {
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .detail-content {
    .el-descriptions {
      margin-bottom: 20px;
    }
  }
}
</style>

