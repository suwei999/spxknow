<template>
  <div class="chunk-editor">
    <!-- 左侧：块列表 -->
    <div class="chunk-list">
      <el-card class="chunk-list-card">
        <template #header>
          <div class="list-header">
            <span>文档块列表</span>
            <el-input
              v-model="searchKeyword"
              placeholder="搜索块..."
              clearable
              size="small"
              style="width: 150px"
            />
          </div>
        </template>
        
        <el-scrollbar height="calc(100vh - 200px)">
          <el-tree
            :data="chunksTree"
            :props="{ children: 'children', label: 'chunk_index' }"
            @node-click="handleChunkSelect"
            :highlight-current="true"
          >
            <template #default="{ node, data }">
              <div class="chunk-item">
                <div class="chunk-info">
                  <span class="chunk-index">{{ data.chunk_index }}</span>
                  <span class="chunk-preview">{{ data.content_preview || '无内容' }}</span>
                </div>
                <el-tag :type="getTypeColor(data.chunk_type)" size="small">
                  {{ data.chunk_type }}
                </el-tag>
              </div>
            </template>
          </el-tree>
        </el-scrollbar>
      </el-card>
    </div>

    <!-- 中间：编辑器 -->
    <div class="editor-main">
      <el-card v-if="currentChunk">
        <template #header>
          <div class="editor-header">
            <span>编辑块 #{{ currentChunk.chunk_index }}</span>
            <div>
              <el-button size="small" @click="handleCancel">取消</el-button>
              <el-button type="primary" size="small" @click="handleSave" :loading="saving">
                保存修改
              </el-button>
            </div>
          </div>
        </template>

        <div class="editor-content">
          <!-- 富文本编辑器 -->
          <QuillEditor
            ref="editorRef"
            v-model:content="editorContent"
            content-type="html"
            theme="snow"
            :options="editorOptions"
            @ready="onEditorReady"
            class="editor"
          />
        </div>

        <!-- 元数据信息 -->
        <el-divider>块元数据</el-divider>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="块ID">{{ currentChunk.chunk_id }}</el-descriptions-item>
          <el-descriptions-item label="块类型">{{ currentChunk.chunk_type }}</el-descriptions-item>
          <el-descriptions-item label="字符数">{{ currentChunk.char_count }}</el-descriptions-item>
          <el-descriptions-item label="版本号">{{ currentChunk.version || 1 }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(currentChunk.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="修改时间">{{ formatDateTime(currentChunk.last_modified_at) }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-empty v-else description="请从左侧选择块进行编辑" />
    </div>

    <!-- 右侧：版本历史 -->
    <div class="version-history">
      <el-card v-if="currentChunk">
        <template #header>
          <span>版本历史</span>
        </template>

        <el-scrollbar height="calc(100vh - 200px)">
          <el-timeline>
            <el-timeline-item
              v-for="version in chunkVersions"
              :key="version.id"
              :timestamp="formatDateTime(version.created_at)"
              :icon="version.version === currentChunk.version ? 'CaretRight' : ''"
            >
              <el-card>
                <div class="version-header">
                  <el-tag size="small">v{{ version.version }}</el-tag>
                  <span class="version-comment">{{ version.version_comment || '无说明' }}</span>
                </div>
                <div class="version-actions">
                  <el-button size="small" @click="handleCompareVersion(version)">对比</el-button>
                  <el-button size="small" type="primary" @click="handleRestoreVersion(version)">
                    恢复
                  </el-button>
                </div>
              </el-card>
            </el-timeline-item>
          </el-timeline>
        </el-scrollbar>
      </el-card>

      <el-empty v-else description="选择块查看版本历史" />
    </div>
  </div>

  <!-- 版本对比对话框 -->
  <el-dialog v-model="compareDialogVisible" title="版本对比" width="90%">
    <div class="compare-content">
      <div class="compare-left">
        <h4>版本 {{ compareVersions.new?.version }}</h4>
        <pre>{{ compareVersions.new?.content || '无内容' }}</pre>
      </div>
      <div class="compare-right">
        <h4>版本 {{ compareVersions.old?.version }}</h4>
        <pre>{{ compareVersions.old?.content || '无内容' }}</pre>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CaretRight } from '@element-plus/icons-vue'
import {
  getDocumentChunks,
  getChunkDetail,
  updateChunk,
  getChunkVersions,
  restoreChunkVersion,
  revertToPreviousVersion
} from '@/api/modules/documents'
import { formatDateTime } from '@/utils/format'
import { QuillEditor } from '@vueup/vue-quill'
import '@vueup/vue-quill/dist/vue-quill.snow.css'

const props = defineProps<{
  documentId: number
}>()

const emit = defineEmits(['close'])

const chunks = ref<any[]>([])
const currentChunk = ref<any>(null)
const chunkVersions = ref<any[]>([])
const searchKeyword = ref('')
const saving = ref(false)
const compareDialogVisible = ref(false)
const compareVersions = ref<any>({})
const editorRef = ref<any>()
const editorContent = ref('')

const editorOptions = {
  modules: {
    toolbar: [
      [{ 'header': [1, 2, 3, false] }],
      ['bold', 'italic', 'underline', 'strike'],
      [{ 'list': 'ordered'}, { 'list': 'bullet' }],
      [{ 'color': [] }, { 'background': [] }],
      ['link'],
      ['code-block']
    ]
  }
}

const chunksTree = computed(() => {
  return chunks.value.map(chunk => ({
    ...chunk,
    chunk_index: `块 #${chunk.chunk_index}`
  }))
})

const loadChunks = async () => {
  try {
    const res = await getDocumentChunks(props.documentId)
    chunks.value = res.data.chunks || []
  } catch (error) {
    ElMessage.error('加载块列表失败')
  }
}

const handleChunkSelect = async (data: any) => {
  if (!data.chunk_id) return
  
  try {
    const res = await getChunkDetail(props.documentId, data.chunk_id)
    currentChunk.value = res.data
    
    // 设置编辑器内容
    editorContent.value = res.data.content
    
    // 加载版本历史
    await loadChunkVersions(data.chunk_id)
  } catch (error) {
    ElMessage.error('加载块内容失败')
  }
}

const onEditorReady = () => {
  // 编辑器准备就绪
}

const loadChunkVersions = async (chunkId: number) => {
  try {
    const res = await getChunkVersions(props.documentId, chunkId)
    chunkVersions.value = res.data.versions || []
  } catch (error) {
    console.error('加载版本历史失败:', error)
  }
}

const handleSave = async () => {
  if (!currentChunk.value) return
  
  try {
    await ElMessageBox.confirm(
      '修改后将重新向量化整个文档。确定要保存吗？',
      '确认修改',
      { type: 'warning' }
    )
    
    saving.value = true
    const content = editorContent.value
    
    await updateChunk(props.documentId, currentChunk.value.chunk_id, {
      content,
      version_comment: '块级修改'
    })
    
    ElMessage.success('保存成功，正在重新向量化...')
    await loadChunks()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('保存失败')
    }
  } finally {
    saving.value = false
  }
}

const handleCancel = () => {
  emit('close')
}

const handleCompareVersion = async (version: any) => {
  try {
    const res = await restoreChunkVersion(props.documentId, currentChunk.value.chunk_id, version.version)
    compareVersions.value = {
      new: currentChunk.value,
      old: res.data
    }
    compareDialogVisible.value = true
  } catch (error) {
    ElMessage.error('加载版本对比失败')
  }
}

const handleRestoreVersion = async (version: any) => {
  try {
    await ElMessageBox.confirm('确定要恢复到此版本吗？', '确认回退', { type: 'warning' })
    
    await revertToPreviousVersion(props.documentId, currentChunk.value.chunk_id)
    ElMessage.success('恢复成功')
    
    // 重新加载当前块
    await handleChunkSelect(currentChunk.value)
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('恢复失败')
    }
  }
}

const getTypeColor = (type: string) => {
  const map: Record<string, string> = {
    text: '',
    heading: 'success',
    code: 'warning',
    table: 'info'
  }
  return map[type] || ''
}

onMounted(() => {
  loadChunks()
})
</script>

<style lang="scss" scoped>
.chunk-editor {
  display: grid;
  grid-template-columns: 300px 1fr 300px;
  gap: 20px;
  height: 100vh;

  .chunk-list {
    .chunk-list-card {
      .list-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
    }

    .chunk-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px;
      
      .chunk-info {
        flex: 1;
        display: flex;
        flex-direction: column;
        
        .chunk-index {
          font-weight: 500;
          margin-bottom: 4px;
        }
        
        .chunk-preview {
          font-size: 12px;
          color: #666;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
      }
    }
  }

  .editor-main {
    .editor-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .editor-content {
      .editor {
        min-height: 400px;
        
        :deep(.ql-container) {
          min-height: 400px;
        }
      }
    }
  }

  .version-history {
    .version-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;
      
      .version-comment {
        flex: 1;
        font-size: 12px;
        color: #666;
      }
    }
    
    .version-actions {
      display: flex;
      gap: 8px;
      margin-top: 8px;
    }
  }

  .compare-content {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    max-height: 600px;
    overflow-y: auto;

    .compare-left,
    .compare-right {
      h4 {
        margin-bottom: 10px;
      }

      pre {
        padding: 10px;
        background: #f5f5f5;
        border-radius: 4px;
        white-space: pre-wrap;
        word-break: break-all;
      }
    }
  }
}
</style>

