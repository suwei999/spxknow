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

      <div class="search-bar">
        <el-input
          v-model="searchText"
          placeholder="搜索图片..."
          clearable
          @keyup.enter="handleSearch"
        >
          <template #append>
            <el-button @click="handleSearch">搜索</el-button>
          </template>
        </el-input>
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
              <div class="image-title">{{ image.description || '图片' }}</div>
              <div class="image-meta">
                <el-tag size="small">{{ image.image_type }}</el-tag>
                <span>{{ formatFileSize(image.file_size || 0) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        @current-change="loadData"
        class="pagination"
      />
    </el-card>

    <el-dialog v-model="imageDialogVisible" title="图片详情" width="800px">
      <div v-if="selectedImage" class="image-detail">
        <img :src="selectedImage.image_path" class="detail-image" />
        <div class="detail-info">
          <p><strong>描述:</strong> {{ selectedImage.description }}</p>
          <p><strong>类型:</strong> {{ selectedImage.image_type }}</p>
          <p><strong>来源文档:</strong> {{ selectedImage.document_id }}</p>
          <p v-if="selectedImage.ocr_text"><strong>OCR文字:</strong> {{ selectedImage.ocr_text }}</p>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getDocumentImages } from '@/api/modules/documents'
import { formatFileSize } from '@/utils/format'

const loading = ref(false)
const images = ref<any[]>([])
const searchText = ref('')
const viewType = ref<'list' | 'grid'>('grid')
const page = ref(1)
const size = ref(24)
const total = ref(0)
const imageDialogVisible = ref(false)
const selectedImage = ref<any>(null)

const loadData = async () => {
  loading.value = true
  try {
    // TODO: 实现图片列表加载
    // const res = await getImages({ page: page.value, size: size.value, search: searchText.value })
    // images.value = res.data.items
    // total.value = res.data.total
  } catch (error) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  page.value = 1
  loadData()
}

const handleImageClick = (image: any) => {
  selectedImage.value = image
  imageDialogVisible.value = true
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

  .search-bar {
    margin-bottom: 20px;
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
        }
      }
    }
  }

  .pagination {
    margin-top: 20px;
    text-align: right;
  }

  .image-detail {
    .detail-image {
      width: 100%;
      max-height: 400px;
      object-fit: contain;
    }

    .detail-info {
      margin-top: 20px;

      p {
        margin-bottom: 10px;
      }
    }
  }
}
</style>

