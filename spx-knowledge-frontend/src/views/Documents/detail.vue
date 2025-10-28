<template>
  <div class="document-detail-page" v-loading="loading">
    <el-card v-if="document">
      <template #header>
        <div class="card-header">
          <span>文档详情</span>
          <div>
            <el-button @click="handleEdit">编辑</el-button>
            <el-button type="danger" @click="handleDelete">删除</el-button>
          </div>
        </div>
      </template>

      <el-descriptions :column="2" border>
        <el-descriptions-item label="标题">{{ document.title }}</el-descriptions-item>
        <el-descriptions-item label="文件名">{{ document.file_name }}</el-descriptions-item>
        <el-descriptions-item label="类型">{{ document.file_type }}</el-descriptions-item>
        <el-descriptions-item label="大小">{{ formatFileSize(document.file_size) }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusType(document.status)">
            {{ getStatusText(document.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatDateTime(document.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ formatDateTime(document.updated_at) }}</el-descriptions-item>
      </el-descriptions>

      <el-divider>文档内容</el-divider>

      <el-tabs v-model="activeTab">
        <el-tab-pane label="内容预览" name="preview">
          <div class="content-preview" v-html="contentPreview"></div>
        </el-tab-pane>

        <el-tab-pane label="分块列表" name="chunks">
          <el-table :data="chunks" v-loading="chunksLoading">
            <el-table-column prop="chunk_index" label="序号" width="80" />
            <el-table-column prop="content" label="内容" show-overflow-tooltip />
            <el-table-column prop="chunk_type" label="类型" width="120" />
            <el-table-column prop="char_count" label="字符数" width="100" />
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="版本历史" name="versions">
          <el-timeline>
            <el-timeline-item
              v-for="version in versions"
              :key="version.id"
              :timestamp="formatDateTime(version.created_at)"
            >
              <el-tag>{{ version.version_number }}</el-tag>
              <p>{{ version.description }}</p>
            </el-timeline-item>
          </el-timeline>
        </el-tab-pane>

        <el-tab-pane label="图片列表" name="images">
          <div class="image-gallery">
            <div
              v-for="image in images"
              :key="image.id"
              class="image-item"
              @click="viewImage(image)"
            >
              <img :src="image.image_path" :alt="image.description" />
              <div class="image-info">{{ image.description }}</div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import { getDocumentDetail, deleteDocument, reprocessDocument } from '@/api/modules/documents'
import { formatFileSize, formatDateTime } from '@/utils/format'
import type { Document } from '@/types'

const route = useRoute()
const router = useRouter()
const documentId = Number(route.params.id)

const document = ref<Document | null>(null)
const loading = ref(false)
const chunks = ref<any[]>([])
const chunksLoading = ref(false)
const versions = ref<any[]>([])
const images = ref<any[]>([])
const activeTab = ref('preview')
const contentPreview = ref('')

const loadDetail = async () => {
  loading.value = true
  try {
    const res = await getDocumentDetail(documentId)
    document.value = res.data
    await loadChunks()
  } catch (error) {
    ElMessage.error('加载详情失败')
    router.back()
  } finally {
    loading.value = false
  }
}

const loadChunks = async () => {
  chunksLoading.value = true
  try {
    // TODO: 加载分块数据
    chunks.value = []
  } catch (error) {
    ElMessage.error('加载分块失败')
  } finally {
    chunksLoading.value = false
  }
}

const handleEdit = () => {
  router.push(`/documents/${documentId}/edit`)
}

const handleDelete = async () => {
  try {
    await ElMessageBox.confirm('确定要删除该文档吗？', '提示')
    await deleteDocument(documentId)
    ElMessage.success('删除成功')
    router.push('/documents')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const viewImage = (image: any) => {
  // TODO: 查看图片
}

const getStatusType = (status: string) => {
  const map: Record<string, string> = {
    'completed': 'success',
    'processing': 'warning',
    'failed': 'danger'
  }
  return map[status] || 'info'
}

const getStatusText = (status: string) => {
  const map: Record<string, string> = {
    'completed': '已完成',
    'processing': '处理中',
    'failed': '失败'
  }
  return map[status] || status
}

onMounted(() => {
  loadDetail()
})
</script>

<style lang="scss" scoped>
.document-detail-page {
  .content-preview {
    padding: 20px;
    background: #f9f9f9;
    border-radius: 4px;
    min-height: 300px;
  }

  .image-gallery {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 16px;

    .image-item {
      border: 1px solid #e5e5e5;
      border-radius: 4px;
      overflow: hidden;
      cursor: pointer;

      img {
        width: 100%;
        height: 150px;
        object-fit: cover;
      }

      .image-info {
        padding: 8px;
        font-size: 12px;
        color: #666;
      }
    }
  }
}
</style>

