<template>
  <div class="images-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>图片管理</span>
          <el-radio-group v-model="viewType" size="small">
            <el-radio-button label="list">列表</el-radio-button>
            <el-radio-button label="grid">网格</el-radio-button>
          </el-radio-group>
        </div>
      </template>

      <!-- 筛选栏 -->
      <div class="filter-bar">
        <el-form :inline="true" :model="filterForm">
          <el-form-item label="来源文档">
            <el-input
              v-model.number="filterForm.document_id"
              placeholder="请输入文档ID"
              clearable
              style="width: 200px"
              @clear="handleFilter"
            >
              <template #append>
                <el-button type="primary" @click="handleFilter">筛选</el-button>
              </template>
            </el-input>
          </el-form-item>
          <el-form-item>
            <el-button class="reset-btn" @click="handleReset">重置</el-button>
          </el-form-item>
        </el-form>
      </div>

      <div v-loading="loading" class="images-container" :class="{ 'grid-view': viewType === 'grid' }">
        <el-empty v-if="images.length === 0" description="暂无图片" />

        <div v-else class="image-list">
          <div
            v-for="image in images"
            :key="image.id"
            class="image-item"
            @click="handleImageClick(image)"
          >
            <img :src="image.image_path" :alt="image.description" />
            <div class="image-info">
              <div class="image-title">{{ image.description || `图片 #${image.id}` }}</div>
              <div class="image-meta">
                <div class="meta-left">
                  <el-tag v-if="image.image_type" size="small" type="info">{{ image.image_type }}</el-tag>
                  <el-tag v-if="image.document_id" size="small" type="warning">文档{{ image.document_id }}</el-tag>
                </div>
                <div class="meta-right">
                  <span>{{ formatFileSize(image.file_size || 0) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        :page-sizes="[12, 24, 48, 96]"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="loadData"
        @size-change="loadData"
        class="pagination"
      />
    </el-card>

    <el-dialog v-model="imageDialogVisible" title="图片详情" width="900px">
      <div v-if="selectedImage" class="image-detail">
        <div class="detail-info">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="图片ID">{{ selectedImage.id }}</el-descriptions-item>
            <el-descriptions-item label="来源文档ID">{{ selectedImage.document_id || '-' }}</el-descriptions-item>
            <el-descriptions-item label="图片类型">{{ selectedImage.image_type || '-' }}</el-descriptions-item>
            <el-descriptions-item label="文件大小">{{ formatFileSize(selectedImage.file_size || 0) }}</el-descriptions-item>
            <el-descriptions-item label="图片尺寸" v-if="selectedImage.width && selectedImage.height">
              {{ selectedImage.width }} × {{ selectedImage.height }} 像素
            </el-descriptions-item>
            <el-descriptions-item label="向量模型">{{ selectedImage.vector_model || '-' }}</el-descriptions-item>
            <el-descriptions-item label="向量维度">{{ selectedImage.vector_dim || '-' }}</el-descriptions-item>
            <el-descriptions-item label="处理状态">{{ selectedImage.status || '-' }}</el-descriptions-item>
            <el-descriptions-item label="创建时间" v-if="selectedImage.created_at">
              {{ new Date(selectedImage.created_at).toLocaleString() }}
            </el-descriptions-item>
          </el-descriptions>
          
          <el-divider />
          
          <div v-if="selectedImage.description" class="info-section">
            <h4>描述</h4>
            <p>{{ selectedImage.description }}</p>
          </div>
          
          <div v-if="selectedImage.ocr_text" class="info-section">
            <h4>OCR识别文字</h4>
            <p class="ocr-text">{{ selectedImage.ocr_text }}</p>
          </div>
          
          <div v-if="selectedImage.meta" class="info-section">
            <h4>元数据</h4>
            <pre class="meta-data">{{ typeof selectedImage.meta === 'string' ? selectedImage.meta : JSON.stringify(selectedImage.meta, null, 2) }}</pre>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElDescriptions, ElDescriptionsItem, ElDivider } from 'element-plus'
import { getImageList, getImageDetail } from '@/api/modules/images'
import { formatFileSize } from '@/utils/format'

const loading = ref(false)
const images = ref<any[]>([])
const viewType = ref<'list' | 'grid'>('grid')
const page = ref(1)
const size = ref(24)
const total = ref(0)
const imageDialogVisible = ref(false)
const selectedImage = ref<any>(null)

const filterForm = ref({
  document_id: undefined as number | undefined
})

const loadData = async () => {
  loading.value = true
  try {
    // 计算 skip（后端使用 skip/limit）
    const skip = (page.value - 1) * size.value
    
    const params: any = {
      skip,
      limit: size.value
    }
    
    // 如果有文档ID筛选，添加到参数
    if (filterForm.value.document_id) {
      params.document_id = filterForm.value.document_id
    }
    
    const res = await getImageList(params)
    
    // 处理返回数据
    const data = res?.data || res
    if (Array.isArray(data)) {
      images.value = data
      // 如果后端返回总数，使用总数；否则使用当前数组长度
      total.value = (res as any)?.total || data.length
    } else {
      images.value = data?.items || data?.list || []
      total.value = data?.total || images.value.length
    }
  } catch (error: any) {
    console.error('加载图片列表失败:', error)
    ElMessage.error(error?.response?.data?.detail || error?.message || '加载图片列表失败')
    images.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

const handleFilter = () => {
  page.value = 1
  loadData()
}

const handleReset = () => {
  filterForm.value.document_id = undefined
  page.value = 1
  loadData()
}

const handleImageClick = async (image: any) => {
  try {
    // 加载完整图片详情
    const detailRes = await getImageDetail(image.id)
    const detail = detailRes?.data || detailRes || image
    // 确保 image_path 可直接访问（后端应已处理，这里再次兜底）
    if (detail && typeof detail.image_path === 'string' && !/^https?:\/\//.test(detail.image_path)) {
      const enc = encodeURIComponent(detail.image_path)
      detail.image_path = `/api/images/file?object=${enc}`
    }
    selectedImage.value = detail
    imageDialogVisible.value = true
  } catch (error: any) {
    console.error('加载图片详情失败:', error)
    // 如果加载详情失败，使用列表中的基本信息
    selectedImage.value = image
    imageDialogVisible.value = true
  }
}

onMounted(() => {
  loadData()
})
</script>

<style lang="scss" scoped>
.images-page {
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .filter-bar {
    margin-bottom: 20px;
    padding: 16px;
    background: #f5f7fa;
    border-radius: 4px;
    :deep(.el-input-group__append) .el-button {
      font-weight: 600;
    }
    .reset-btn {
      background: #ffffff;
      border-color: #cbd5e1;
      color: #1f2937;
      font-weight: 600;
    }
  }

  .images-container {
    min-height: 400px;

    &.grid-view {
      .image-list {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
        gap: 16px;
      }
    }

    .image-item {
      border: 1px solid #e5e5e5;
      border-radius: 4px;
      overflow: hidden;
      cursor: pointer;
      transition: box-shadow 0.3s;

      &:hover {
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
      }

      img {
        width: 100%;
        height: 200px;
        object-fit: cover;
      }

      .image-info {
        padding: 12px;
        
        .image-title {
          font-weight: 500;
          margin-bottom: 8px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .image-meta {
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 12px;
          color: #999;
          gap: 8px;

          .meta-left {
            display: flex;
            gap: 4px;
            flex-wrap: wrap;
          }

          .meta-right {
            flex-shrink: 0;
          }
        }
      }
    }
  }

  .pagination {
    margin-top: 20px;
    text-align: right;
  }

    .image-detail {
    .detail-info {
      .info-section {
        margin-top: 16px;

        h4 {
          margin-bottom: 8px;
          color: #303133;
          font-size: 14px;
          font-weight: 600;
        }

        p {
          margin: 0;
          color: #606266;
          line-height: 1.6;
        }

        .ocr-text {
          background: #f5f7fa;
          padding: 12px;
          border-radius: 4px;
          white-space: pre-wrap;
          word-break: break-word;
        }

        .meta-data {
          background: #f5f7fa;
          padding: 12px;
          border-radius: 4px;
          overflow-x: auto;
          font-size: 12px;
          line-height: 1.5;
          max-height: 300px;
          overflow-y: auto;
        }
      }
    }
  }
}
</style>

