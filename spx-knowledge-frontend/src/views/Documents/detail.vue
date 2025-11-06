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
          <template v-if="previewUrl">
            <!-- PDF 直接内嵌展示 -->
            <iframe
              v-if="isPdf"
              class="preview-frame"
              :src="previewUrl"
              frameborder="0"
              referrerpolicy="no-referrer"
            />
            <!-- Office 文档通过 Office Web Viewer 内嵌展示（使用 MinIO 签名 URL） -->
            <iframe
              v-else-if="isOffice"
              class="preview-frame"
              :src="officeViewerUrl"
              frameborder="0"
              referrerpolicy="no-referrer"
            />
            <!-- 图片原样展示 -->
            <img v-else-if="isImage" class="image-inline" :src="previewUrl" />
            <!-- 其他类型：提供打开原文件按钮 -->
            <div v-else class="preview-download">
              <el-alert type="info" :closable="false" show-icon title="该文件类型暂不支持内嵌预览，已提供原文件直链。" />
              <el-button type="primary" :href="previewUrl" target="_blank">打开原文件</el-button>
            </div>
          </template>
          <div class="content-preview" v-else v-html="contentPreview"></div>
        </el-tab-pane>

        <el-tab-pane label="分块列表" name="chunks">
          <el-table :data="chunks" v-loading="chunksLoading" class="chunk-table">
            <el-table-column prop="chunk_index" label="序号" width="80" />
            <el-table-column prop="chunk_type" label="类型" width="120" />
            <el-table-column prop="char_count" label="字符数" width="120" />
            <el-table-column label="操作" width="140">
              <template #default="{ row }">
                <el-tag size="small" type="info" @click="showChunk(row)" style="cursor:pointer">查看内容</el-tag>
              </template>
            </el-table-column>
          </el-table>

          <el-dialog v-model="chunkDialogVisible" title="分块内容" width="60%">
            <pre class="chunk-content">{{ currentChunkContent }}</pre>
          </el-dialog>
        </el-tab-pane>

        <el-tab-pane label="版本历史" name="versions">
          <template v-if="versionsCount > 0">
            <el-timeline>
              <el-timeline-item
                v-for="version in versions"
                :key="version.id"
                :timestamp="formatDateTime(version.created_at)"
              >
                <div :class="['version-line', getVersionType(version)]">
                  <el-tag class="ver-tag" size="large">{{ version.version_number }}</el-tag>
                  <span class="version-desc" :title="version.description || '—'">{{ version.description || '—' }}</span>
                </div>
              </el-timeline-item>
            </el-timeline>
          </template>
          <el-empty v-else description="暂无版本（0）" />
        </el-tab-pane>

        <el-tab-pane label="图片列表" name="images">
          <div class="image-gallery">
            <div
              v-for="image in images"
              :key="image.id"
              class="image-item"
              @click="viewImage(image)"
            >
              <img :src="image.url || image.image_path" :alt="image.description" />
              <div class="image-info">{{ image.description }}</div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import {
  getDocumentDetail,
  deleteDocument,
  reprocessDocument,
  getDocumentChunks,
  getDocumentImages,
  getDocumentVersions,
  getDocumentPreview,
  getChunkContentFromOS
} from '@/api/modules/documents'
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
const previewUrl = ref('')
const previewType = ref('')
const isPdf = computed(() => /pdf/i.test(previewType.value) || /\.pdf(\?|$)/i.test(previewUrl.value))
const isImage = computed(() => /^(image\/)\w+/i.test(previewType.value) || /\.(png|jpg|jpeg|gif|webp|bmp)(\?|$)/i.test(previewUrl.value))
const isOffice = computed(() => {
  // 支持常见 Office 类型：doc/docx/xls/xlsx/ppt/pptx
  if (/msword|officedocument|vnd\.ms-|vnd\.openxmlformats/i.test(previewType.value)) return true
  return /\.(doc|docx|xls|xlsx|ppt|pptx)(\?|$)/i.test(previewUrl.value)
})
const officeViewerUrl = computed(() => `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(previewUrl.value)}`)

const chunkDialogVisible = ref(false)
const currentChunkContent = ref('')
const versionsCount = computed(() => versions.value?.length || 0)
const showChunk = async (row: any) => {
  try {
    const resp = await getChunkContentFromOS(documentId, row.id)
    const data = (resp as any)?.data
    currentChunkContent.value = data?.content || ''
  } catch (e) {
    currentChunkContent.value = ''
  } finally {
    chunkDialogVisible.value = true
  }
}

const loadDetail = async () => {
  loading.value = true
  try {
    const res = await getDocumentDetail(documentId)
    document.value = res.data
    await Promise.all([loadChunks(), loadImages(), buildPreview(), loadVersions(), loadPreviewUrl()])
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
    // 简单加载前 200 条分块用于列表与预览构建
    const resp = await getDocumentChunks(documentId, { page: 1, size: 200 })
    const data = (resp as any)?.data
    // 后端分页统一 { list, total } 或直接数组，做兼容
    chunks.value = Array.isArray(data) ? data : (data?.list ?? [])
  } catch (error) {
    ElMessage.error('加载分块失败')
  } finally {
    chunksLoading.value = false
  }
}

const buildPreview = async () => {
  try {
    // 若 chunks 已加载，直接构建；否则先拉取少量块
    if (chunks.value.length === 0) {
      const resp = await getDocumentChunks(documentId, { page: 1, size: 50, include_content: true } as any)
      const data = (resp as any)?.data
      const list = Array.isArray(data) ? data : (data?.list ?? [])
      contentPreview.value = list.map((c: any) => c.content).filter(Boolean).join('\n\n')
    } else {
      contentPreview.value = chunks.value.map((c: any) => c.content).filter(Boolean).slice(0, 50).join('\n\n')
    }
  } catch (e) {
    contentPreview.value = ''
  }
}

const loadImages = async () => {
  try {
    const resp = await getDocumentImages(documentId)
    const data = (resp as any)?.data
    images.value = Array.isArray(data) ? data : (data?.list ?? [])
  } catch (error) {
    // 图片为空不报错
    images.value = []
  }
}

const loadVersions = async () => {
  try {
    const resp = await getDocumentVersions(documentId, { page: 1, size: 50 })
    const data = (resp as any)?.data
    versions.value = Array.isArray(data) ? data : (data?.list ?? [])
  } catch (error) {
    versions.value = []
  }
}

const loadPreviewUrl = async () => {
  try {
    const resp = await getDocumentPreview(documentId)
    const data = (resp as any)?.data
    previewUrl.value = data?.preview_url || ''
    previewType.value = data?.content_type || ''
  } catch (e) {
    previewUrl.value = ''
    previewType.value = ''
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

// 版本类型：用于颜色标注
const getVersionType = (v: any): string => {
  const desc = String(v?.description || '')
  if (/回退|恢复|revert/i.test(desc)) return 'revert'
  if (/编辑|修改|变更|edit|update/i.test(desc)) return 'edit'
  return 'init'
}

onMounted(() => {
  loadDetail()
})
</script>

<style lang="scss" scoped>
.document-detail-page {
  /* 提升标签页可读性 */
  :deep(.el-tabs__item) {
    color: rgba(255, 255, 255, 0.75);
    font-weight: 500;
  }
  :deep(.el-tabs__item.is-active) {
    color: #ffffff;
  }
  :deep(.el-tabs__item:hover) {
    color: #ffffff;
  }
  :deep(.el-tabs__active-bar) {
    background-color: #409eff; /* 高亮下划线颜色 */
  }

  .content-preview {
    padding: 20px;
    background: #f9f9f9;
    border-radius: 4px;
    min-height: 300px;
  }

  /* 版本历史时间轴可读性增强 */
  :deep(.el-timeline-item__timestamp) {
    color: #cbd5e1;
    font-size: 13px;
  }
  .version-line {
    display: flex;
    align-items: center;
    gap: 14px;
    .version-desc {
      color: #e2e8f0;
      font-size: 16px;
      font-weight: 500;
      letter-spacing: .2px;
    }
    :deep(.ver-tag) {
      font-size: 14px;
      padding: 6px 12px;
    }
  }

  /* ===== 科技感增强样式（时间轴） ===== */
  :deep(.el-timeline) {
    padding-left: 8px;
  }
  /* 竖线：渐变+微弱发光 */
  :deep(.el-timeline-item__tail) {
    border-left: none !important;
    width: 3px;
    background: linear-gradient(180deg, rgba(64,158,255,0.85), rgba(56,189,248,0.65));
    box-shadow: 0 0 8px rgba(64,158,255,0.45);
  }
  /* 节点：霓虹点 */
  :deep(.el-timeline-item__node) {
    background: radial-gradient(circle at 30% 30%, #4a90e2, #2563eb);
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.2), 0 0 12px rgba(56,189,248,0.5);
    border: none;
  }
  /* 版本号标签：渐变胶囊 + 轻微发光 */
  .version-line :deep(.ver-tag) {
    background: linear-gradient(135deg, #3b82f6, #06b6d4) !important;
    color: #eaf6ff !important;
    border: none !important;
    box-shadow: 0 2px 10px rgba(59,130,246,0.35) !important;
    border-radius: 999px !important;
  }
  /* 颜色区分：回退=红橙、编辑=蓝青、初始=紫蓝 */
  .version-line.revert :deep(.ver-tag) {
    background: linear-gradient(135deg, #ef4444, #f59e0b) !important;
    box-shadow: 0 2px 10px rgba(239,68,68,0.35) !important;
  }
  .version-line.edit :deep(.ver-tag) {
    background: linear-gradient(135deg, #3b82f6, #06b6d4) !important;
  }
  .version-line.init :deep(.ver-tag) {
    background: linear-gradient(135deg, #8b5cf6, #3b82f6) !important;
  }
  /* 文本悬浮高亮 */
  .version-line {
    transition: transform .15s ease, filter .15s ease;
  }
  .version-line:hover {
    transform: translateX(2px);
    filter: brightness(1.05);
  }

  .preview-frame {
    width: 100%;
    height: 72vh;
    background: #fff;
  }

  .image-inline {
    max-width: 100%;
    height: auto;
    background: #fff;
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

  /* 降低表格 hover 亮度，适配深色背景 */
  :deep(.chunk-table .el-table__row:hover>td) {
    background-color: rgba(255, 255, 255, 0.06) !important;
  }

  .chunk-content {
    white-space: pre-wrap;
    line-height: 1.6;
    max-height: 70vh;
    overflow: auto;
    background: #111;
    color: #ddd;
    padding: 12px;
    border-radius: 4px;
  }
}
</style>

