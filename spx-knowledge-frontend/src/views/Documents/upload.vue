<template>
  <div class="upload-page">
    <el-card class="upload-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">文档上传</span>
          <span class="card-subtitle">选择知识库、上传文件并添加标签</span>
        </div>
      </template>

      <el-form :model="form" label-width="120px">
        <el-form-item label="选择知识库" :required="true">
          <el-select 
            v-model="form.knowledge_base_id" 
            placeholder="请先选择知识库"
            class="kb-select"
            :disabled="uploading"
          >
            <el-option
              v-for="kb in knowledgeBases"
              :key="kb.id"
              :label="kb.name"
              :value="kb.id"
            />
          </el-select>
          <el-alert 
            v-if="!form.knowledge_base_id" 
            title="请先选择知识库后再上传文件" 
            type="warning" 
            :closable="false"
            style="margin-top: 10px"
          />
        </el-form-item>

        <el-form-item label="选择文件">
            <el-upload
              ref="uploadRef"
              :auto-upload="false"
              :on-change="handleFileChange"
              :on-remove="handleFileRemove"
              :limit="1"
              drag
            >
            <template #default>
              <el-icon class="el-icon--upload"><Upload /></el-icon>
              <div class="el-upload__text">
                将文件拖到此处，或<em>点击上传</em>
              </div>
            </template>
          </el-upload>
        </el-form-item>

        <el-form-item v-if="file">
          <div class="file-info">
            <span>文件名: {{ file.name }}</span>
            <span>大小: {{ formatFileSize(file.size) }}</span>
            <el-button size="small" type="primary" @click="handlePreviewFile" style="margin-left: 10px">
              预览
            </el-button>
          </div>
        </el-form-item>

        <!-- 标签选择 -->
        <el-form-item label="标签">
          <TagSelector
            v-model="form.tags"
            :recommended-tags="recommendedTags"
            :max-tags="10"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" size="large" @click="handleSubmit" :loading="uploading">
            上传
          </el-button>
          <el-button size="large" @click="$router.back()">取消</el-button>
        </el-form-item>

        <el-form-item v-if="uploadResult">
          <el-result icon="success" title="上传成功" sub-title="文档已添加到知识库">
            <template #extra>
              <el-button type="primary" @click="$router.push(`/documents/${uploadResult.document_id}`)">
                查看文档
              </el-button>
            </template>
          </el-result>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 文件预览 -->
    <FilePreview
      v-model="showPreview"
      :file="previewFile"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import { getKnowledgeBases } from '@/api/modules/knowledge-bases'
import { uploadDocument } from '@/api/modules/documents'
import { formatFileSize } from '@/utils/format'
import TagSelector from '@/components/business/TagSelector.vue'
import FilePreview from '@/components/business/FilePreview.vue'
import type { KnowledgeBase } from '@/types'

const knowledgeBases = ref<KnowledgeBase[]>([])
const loading = ref(false)
const uploading = ref(false)
const file = ref<File | null>(null)
const uploadResult = ref<any>(null)

const form = ref({
  knowledge_base_id: undefined as number | undefined,
  tags: [] as string[]
})

const uploadRef = ref()
const showPreview = ref(false)
const previewFile = ref<any>(null)
const recommendedTags = ref<string[]>(['技术文档', '用户手册', 'API文档', '产品介绍'])

const loadKnowledgeBases = async () => {
  loading.value = true
  try {
    const res = await getKnowledgeBases({ page: 1, size: 100 })
    const data = res?.data ?? {}
    knowledgeBases.value = data.list ?? data.items ?? []
  } catch (error) {
    ElMessage.error('加载知识库列表失败')
  } finally {
    loading.value = false
  }
}

const handleFileChange = (uploadFile: any) => {
  if (uploadFile.raw) {
    file.value = uploadFile.raw
  }
}

const handleFileRemove = () => {
  file.value = null
}

const handleSubmit = async () => {
  if (!form.value.knowledge_base_id) {
    ElMessage.warning('请选择知识库')
    return
  }

  if (!file.value) {
    ElMessage.warning('请选择文件')
    return
  }

  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', file.value)
    formData.append('knowledge_base_id', String(form.value.knowledge_base_id))
    if (form.value.tags && form.value.tags.length > 0) {
      formData.append('tags', JSON.stringify(form.value.tags))
    }

    uploadResult.value = await uploadDocument(formData)
    ElMessage.success('上传成功')
  } catch (error) {
    ElMessage.error('上传失败')
  } finally {
    uploading.value = false
  }
}

const handlePreviewFile = () => {
  if (file.value) {
    previewFile.value = {
      name: file.value.name,
      size: file.value.size,
      url: URL.createObjectURL(file.value)
    }
    showPreview.value = true
  }
}

loadKnowledgeBases()
</script>

<style lang="scss" scoped>
.upload-page {
  display: flex;
  justify-content: center;
  padding: 24px;
  position: relative;
}

/* 科技感动态网格背景 */
.upload-page::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(1200px 600px at 80% -20%, rgba(99,102,241,0.18), transparent 60%),
    radial-gradient(800px 400px at 10% 110%, rgba(59,130,246,0.15), transparent 55%),
    repeating-linear-gradient(
      90deg,
      rgba(255,255,255,0.06) 0,
      rgba(255,255,255,0.06) 1px,
      transparent 1px,
      transparent 28px
    ),
    repeating-linear-gradient(
      0deg,
      rgba(255,255,255,0.05) 0,
      rgba(255,255,255,0.05) 1px,
      transparent 1px,
      transparent 28px
    );
  mask-image: radial-gradient(closest-side, rgba(0,0,0,0.9), rgba(0,0,0,0.4));
}

.upload-card {
  width: 100%;
  max-width: 920px;
  background: linear-gradient(180deg, rgba(17,24,39,0.65), rgba(17,24,39,0.35));
  border: 1px solid rgba(99, 102, 241, 0.35);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35), inset 0 0 60px rgba(99,102,241,0.08);
  backdrop-filter: blur(6px);
  border-radius: 12px;
}

.card-header {
  display: flex;
  flex-direction: column;
}

.card-title {
  font-size: 18px;
  font-weight: 600;
  color: #e9eef5;
  text-shadow: 0 0 12px rgba(99,102,241,0.55);
}

.card-subtitle {
  margin-top: 4px;
  font-size: 13px;
  color: #c8d3e6;
  opacity: 0.95;
}

.kb-select {
  width: 360px;
}

.file-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: var(--el-text-color-primary);
}

/* 强化左侧表单标签与辅助文字的可读性（深色背景下） */
:deep(.el-form-item__label) {
  color: #e9eef5 !important;
  opacity: 1 !important;
  font-weight: 600;
  font-size: 14px;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
}

/* 拖拽上传提示文字 */
:deep(.el-upload__text) {
  color: #eef4ff !important;
  font-weight: 600;
  text-shadow: 0 1px 2px rgba(0,0,0,0.35);
}
:deep(.el-upload-dragger) {
  background: rgba(30,41,59,0.5);
  border: 1px dashed rgba(99,102,241,0.6);
  box-shadow: inset 0 0 30px rgba(99,102,241,0.08);
}
:deep(.el-upload-dragger .el-icon--upload) {
  color: #93c5fd;
}
:deep(.el-upload-dragger em) {
  color: #93c5fd !important;
}

/* 输入框占位符与文本颜色 */
:deep(.el-input__inner) {
  color: var(--el-text-color-primary);
}
:deep(.el-input__inner::placeholder) {
  color: #cbd5e1;
  opacity: 1;
}

/* 警告条文字颜色 */
:deep(.el-alert__title) {
  color: #1f2937;
}

/* 主操作按钮视觉增强 */
:deep(.el-button.el-button--primary) {
  box-shadow: 0 4px 16px rgba(59,130,246,0.35);
}

/* 上传成功提示的可读性增强 */
:deep(.el-result__title) {
  color: #e6f0ff !important;
  text-shadow: 0 1px 2px rgba(0,0,0,0.35);
  font-weight: 700;
}
:deep(.el-result__subtitle) {
  color: #cbd5e1 !important;
  opacity: 1;
}
:deep(.el-result .icon-success) {
  filter: drop-shadow(0 0 10px rgba(16,185,129,0.35));
}
</style>

