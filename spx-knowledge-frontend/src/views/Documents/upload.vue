<template>
  <div class="upload-page">
    <el-card>
      <template #header>
        <span>文档上传</span>
      </template>

      <el-form :model="form" label-width="120px">
        <el-form-item label="选择知识库" :required="true">
          <el-select 
            v-model="form.knowledge_base_id" 
            placeholder="请先选择知识库"
            style="width: 300px"
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

        <!-- 智能标签推荐 -->
        <el-form-item label="标签">
          <TagSelector
            v-model="form.tags"
            :recommended-tags="recommendedTags"
            :max-tags="10"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="handleSubmit" :loading="uploading">
            上传
          </el-button>
          <el-button @click="$router.back()">取消</el-button>
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
  .file-info {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
}
</style>

