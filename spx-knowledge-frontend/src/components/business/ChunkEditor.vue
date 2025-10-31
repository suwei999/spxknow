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
        
        <el-table
          :data="chunksTable"
          height="calc(100vh - 220px)"
          @row-click="onRowClick"
          highlight-current-row
          class="chunk-table"
        >
          <el-table-column prop="index" label="序号" width="70" align="center" />
          <el-table-column prop="chunk_type" label="类型" width="100" align="center">
            <template #default="scope">
              <span :class="['type-pill', scope.row.chunk_type]">{{ scope.row.chunk_type }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="char_count" label="字符数" width="90" align="center" />
        </el-table>
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
          <!-- 表格块：以表格方式编辑 -->
          <template v-if="isTableChunk">
            <el-tabs v-model="tableTab" type="border-card">
              <el-tab-pane label="原始预览" name="preview">
                <div class="table-html" v-if="tableHtml" v-html="tableHtml"></div>
                <el-empty v-else description="无原始预览，已使用网格编辑" />
              </el-tab-pane>
              <el-tab-pane label="网格编辑" name="grid">
                <div class="table-editor-tools">
                  <el-button size="small" @click="addRow">加一行</el-button>
                  <el-button size="small" @click="addCol">加一列</el-button>
                </div>
                <el-table :data="tableObjects" border class="table-editor">
                  <el-table-column v-for="(col, cIdx) in tableColumns" :key="cIdx" :label="col" :prop="col" align="center">
                    <template #default="scope">
                      <el-input v-model="tableData[scope.$index][cIdx]" size="small" />
                    </template>
                  </el-table-column>
                </el-table>
              </el-tab-pane>
            </el-tabs>
          </template>
          <!-- 文本块：富文本编辑器 -->
          <template v-else>
            <QuillEditor
              ref="editorRef"
              v-model:content="editorContent"
              content-type="html"
              theme="snow"
              :options="editorOptions"
              @ready="onEditorReady"
              class="editor"
            />
          </template>
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
const isTableChunk = computed(() => (currentChunk.value?.chunk_type === 'table'))
const tableData = ref<string[][]>([])
const tableHtml = ref<string>('')
const tableTab = ref<'preview' | 'grid'>('preview')
const tableColumns = computed(() => {
  const cols = tableData.value[0]?.length || 0
  return Array.from({ length: cols }, (_, i) => `C${i + 1}`)
})
const tableObjects = computed(() => {
  // 将二维数组转换为 element-plus table 需要的对象数组
  return tableData.value.map(row => {
    const obj: Record<string, string> = {}
    row.forEach((val, idx) => { obj[`C${idx + 1}`] = val })
    return obj
  })
})

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

const chunksTable = computed(() => {
  return (chunks.value || []).map((chunk: any) => ({
    ...chunk,
    index: chunk.chunk_index,
  }))
})

const loadChunks = async () => {
  try {
    const res = await getDocumentChunks(props.documentId, { page: 1, size: 1000, include_content: true } as any)
    const data = (res as any)?.data
    chunks.value = Array.isArray(data) ? data : (data?.list || data?.chunks || [])
  } catch (error) {
    ElMessage.error('加载块列表失败')
  }
}

const onRowClick = async (data: any) => {
  // 同一个列表数据：直接使用左侧已加载的块数据，避免重复请求
  const chunkId = data.id || data.chunk_id
  if (!chunkId) return

  currentChunk.value = { ...data }
  editorContent.value = data.content || ''
  // 初始化表格数据
  if (currentChunk.value.chunk_type === 'table') {
    try {
      const metaRaw = (currentChunk.value as any).meta
      const meta = typeof metaRaw === 'string' ? JSON.parse(metaRaw) : (metaRaw || {})
      const cells = meta?.table_data?.cells
      tableHtml.value = meta?.table_data?.html || ''
      if (Array.isArray(cells) && Array.isArray(cells[0])) {
        tableData.value = cells.map((r: any[]) => r.map(v => String(v ?? '')))
      } else {
        // 简单按换行和空格切分
        const lines = (currentChunk.value.content || '').split('\n')
        tableData.value = lines.map(l => l.split(/\s+/))
      }
    } catch (e) {
      tableData.value = [[currentChunk.value.content || '']]
    }
  } else {
    tableData.value = []
    tableHtml.value = ''
  }

  // 若内容为空（例如 DB 不存正文），再请求详情补全
  if (!editorContent.value) {
    try {
      const res = await getChunkDetail(props.documentId, chunkId)
      currentChunk.value = res.data
      editorContent.value = res.data?.content || ''
    } catch (error) {
      // 保持已有数据
    }
  }

  try {
    await loadChunkVersions(chunkId)
  } catch (e) {}
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
    let content = editorContent.value
    let metadata: any = undefined
    if (isTableChunk.value) {
      // 将表格合并为文本（用于搜索），同时把结构写回 metadata
      content = tableData.value.map(r => r.join('\t')).join('\n')
      const metaRaw = (currentChunk.value as any).meta
      const metaObj = typeof metaRaw === 'string' ? (JSON.parse(metaRaw || '{}') || {}) : (metaRaw || {})
      metaObj.table_data = { cells: tableData.value, html: tableHtml.value }
      metadata = metaObj
    }
    await updateChunk(props.documentId, currentChunk.value.chunk_id, {
      content,
      metadata,
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
      padding: 6px 12px;
      height: 46px;
      margin: 16px 0; /* 明显缝隙 */
      box-sizing: border-box;
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.06); /* 淡底色，便于区分 */
      border: 1px solid rgba(255, 255, 255, 0.10);
      box-shadow: 0 2px 8px rgba(0,0,0,0.18);
      transition: background 0.15s ease;
      
      &:hover { background: rgba(255, 255, 255, 0.10); }

      .chunk-info {
        display: flex;
        align-items: center;
        gap: 22px; /* 数字与类型之间距离更大 */
        
        .chunk-index {
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
          font-size: 16px;
          font-weight: 700;
          letter-spacing: 0.2px;
          width: 28px; height: 28px;
          display: inline-flex;
          align-items: center; justify-content: center;
          border-radius: 50%;
          color: #fff;
          background: radial-gradient( circle at 30% 30%, rgba(74, 144, 255, 0.85), rgba(74,144,255,0.45) );
          box-shadow: 0 0 8px rgba(74,144,255,0.35), inset 0 0 0 1px rgba(255,255,255,0.25);
        }
      }

      :deep(.type-tag) {
        border-radius: 8px;
        height: 26px;
        line-height: 24px;
        padding: 0 12px;
        font-size: 14px;
        margin-left: 10px;
        box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.15);
        border: none;
      }

      /* 科技感色系 */
      :deep(.type-tag.text) {
        color: #e9f3ff;
        background: linear-gradient(135deg, rgba(0, 140, 255, 0.75), rgba(0, 120, 255, 0.35));
        box-shadow: 0 0 12px rgba(0,140,255,0.35);
      }
      :deep(.type-tag.table) {
        color: #ecfff7;
        background: linear-gradient(135deg, rgba(0, 220, 155, 0.75), rgba(0, 205, 145, 0.35));
        box-shadow: 0 0 12px rgba(0,220,155,0.35);
      }
    }

    /* 表格风格（根据你的截图弱化 hover 高亮、收窄行距） */
    :deep(.chunk-table) {
      background: transparent;
      .el-table__header th { background: rgba(255,255,255,0.06); color: #dfe7f3; padding: 8px 0; }
      .el-table__row { height: 36px; }
      .el-table__row:hover > td { background: rgba(255,255,255,0.045) !important; color: #e6ecf5; }
      .el-table__row.current-row > td { background: rgba(64,158,255,0.10) !important; color: #eaf2ff; }
      .type-pill { display: inline-block; min-width: 48px; padding: 2px 10px; border-radius: 999px; font-size: 13px; }
      .type-pill.text { background: linear-gradient(135deg, rgba(0,140,255,0.6), rgba(0,120,255,0.28)); color: #eaf2ff; box-shadow: 0 0 6px rgba(0,140,255,0.2); }
      .type-pill.table { background: linear-gradient(135deg, rgba(0,210,150,0.6), rgba(0,200,140,0.28)); color: #ecfff7; box-shadow: 0 0 6px rgba(0,210,150,0.2); }
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
      .table-editor { margin-top: 6px; }
      .table-editor-tools { display: flex; gap: 8px; }
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

