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
                <!-- ✅ 调试信息 -->
                <div style="padding: 10px; background: #f5f5f5; margin-bottom: 10px; font-size: 12px; color: #666;">
                  <div>tableHtml 状态: {{ tableHtml ? `存在 (${tableHtml.length} 字符)` : '空' }}</div>
                  <div>debugTableHtml 状态: {{ debugTableHtml ? `存在 (${debugTableHtml.length} 字符)` : '空' }}</div>
                  <div>tableData 状态: {{ tableData && tableData.length > 0 ? `${tableData.length} 行` : '空' }}</div>
                  <div>isTableChunk: {{ isTableChunk }}</div>
                  <div>currentChunk.chunk_index: {{ currentChunk?.chunk_index }}</div>
                </div>
                
                <!-- ✅ 优先显示 HTML 表格（最准确的原始结构） -->
                <div v-if="debugTableHtml" class="table-html-wrapper">
                  <div class="table-html" v-html="debugTableHtml"></div>
                </div>
                <!-- ✅ 如果没有 HTML，尝试从 cells 生成表格预览 -->
                <div v-else-if="tableData && tableData.length > 0 && !(tableData.length === 1 && tableData[0]?.length <= 1)" class="table-preview-from-cells">
                  <table class="preview-table" border="1" cellpadding="5" cellspacing="0" style="width: 100%; border-collapse: collapse;">
                    <tbody>
                      <tr v-for="(row, rowIdx) in tableData" :key="rowIdx">
                        <td v-for="(cell, cellIdx) in row" :key="cellIdx" style="border: 1px solid #ddd; padding: 8px;">
                          {{ cell }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                  <el-alert
                    type="warning"
                    :closable="false"
                    style="margin-top: 10px;"
                    description="⚠️ 此表格预览由结构化数据生成，原始 HTML 不可用。如果内容不正确，请检查后端表格提取逻辑。"
                  />
                </div>
                <!-- ✅ 如果既没有 HTML 也没有 cells，显示提示 -->
                <el-empty v-else description="无法显示表格预览：缺少表格结构数据（HTML 或 cells）。可能是解析时未正确提取表格结构。" />
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

// ✅ 调试用 computed，确保响应式更新
const debugTableHtml = computed(() => {
  console.log('[响应式调试] tableHtml computed 被调用，当前值:', tableHtml.value ? `${tableHtml.value.substring(0, 50)}...` : '(空)')
  return tableHtml.value
})
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
    
    // ✅ 调试：检查表格块的数据
    const tableChunks = chunks.value.filter((c: any) => c.chunk_type === 'table')
    console.log('[块列表调试] 找到', tableChunks.length, '个表格块')
    tableChunks.forEach((chunk: any, idx: number) => {
      console.log(`[块列表调试] 表格块 #${chunk.chunk_index}:`, {
        id: chunk.id,
        chunk_index: chunk.chunk_index,
        meta: chunk.meta,
        metaType: typeof chunk.meta,
        hasTableData: chunk.meta && (typeof chunk.meta === 'string' ? JSON.parse(chunk.meta || '{}') : chunk.meta)?.table_data
      })
    })
  } catch (error) {
    ElMessage.error('加载块列表失败')
    console.error('[块列表调试] 加载失败:', error)
  }
}

// ✅ 辅助函数：初始化表格数据（从 chunk 数据中提取）
const initializeTableData = (chunk: any) => {
  if (!chunk || chunk.chunk_type !== 'table') {
    tableData.value = []
    tableHtml.value = ''
    return
  }
  
  try {
    // 解析 meta 字段
    const metaRaw = chunk.meta
    console.log('[表格调试] chunk 原始数据:', chunk)
    console.log('[表格调试] metaRaw:', metaRaw, '类型:', typeof metaRaw)
    
    const meta = typeof metaRaw === 'string' ? JSON.parse(metaRaw || '{}') : (metaRaw || {})
    console.log('[表格调试] 解析后的 meta:', meta)
    console.log('[表格调试] meta.table_data:', meta?.table_data)
    
    // ✅ 优先使用 table_data.html（最准确的表格结构）
    const htmlFromMeta = meta?.table_data?.html || ''
    console.log('[表格调试] 从 meta 获取的 html:', htmlFromMeta ? `${htmlFromMeta.substring(0, 100)}...` : '(空)')
    console.log('[表格调试] meta.table_data 完整内容:', JSON.stringify(meta?.table_data, null, 2))
    
    tableHtml.value = htmlFromMeta
    console.log('[表格调试] ✅ tableHtml.value 已设置为:', tableHtml.value ? `${tableHtml.value.substring(0, 100)}...` : '(空)')
    console.log('[表格调试] tableHtml.value 长度:', tableHtml.value ? tableHtml.value.length : 0)
    
    // ✅ 优先使用 table_data.cells（结构化数据，最准确）
    // ⚠️ 重要：只有当 cells 是有效的二维数组（多行多列）时才使用，否则使用 HTML
    const cells = meta?.table_data?.cells
    console.log('[表格调试] cells:', cells, '是否为数组:', Array.isArray(cells))
    
    // ✅ 检查 cells 是否有效（至少2列或2行，或HTML为空时才使用只有1行1列的cells）
    if (Array.isArray(cells) && cells.length > 0) {
      const firstRow = cells[0]
      const isValidCells = Array.isArray(firstRow) && (
        // 有效的表格：至少有2列，或至少有2行
        (firstRow.length >= 2) || 
        (cells.length >= 2) ||
        // 如果HTML为空，即使只有1行1列也使用cells
        !tableHtml.value
      )
      
      if (isValidCells) {
        tableData.value = cells.map((r: any[]) => {
          if (Array.isArray(r)) {
            return r.map(v => String(v ?? ''))
          }
          return [String(r ?? '')]
        })
        console.log('[表格调试] ✅ 成功从 cells 提取表格数据:', tableData.value.length, '行 x', tableData.value[0]?.length || 0, '列')
        // ⚠️ 如果 tableHtml 存在，优先使用 HTML 渲染，但保留 tableData 用于编辑
        if (tableHtml.value) {
          console.log('[表格调试] 同时存在 HTML，将优先渲染 HTML')
        }
        // 不 return，继续处理 HTML（如果有的话）
      } else {
        console.log('[表格调试] ⚠️ cells 结构无效（可能只有1行1列），跳过使用 cells，优先使用 HTML')
      }
    }
    
    // ✅ 如果 tableHtml 存在，优先使用 HTML 渲染
    // 如果 tableData 还没设置或只有1行1列，尝试从 HTML 中提取表格结构
    if (tableHtml.value) {
      // 如果 tableData 为空或无效，从 HTML 提取
      if (!tableData.value || tableData.value.length === 0 || 
          (tableData.value.length === 1 && tableData.value[0]?.length <= 1)) {
        try {
          console.log('[表格调试] 从 HTML 提取表格结构到 tableData...')
          // 创建一个临时 DOM 元素来解析 HTML
          const parser = new DOMParser()
          const doc = parser.parseFromString(tableHtml.value, 'text/html')
          const table = doc.querySelector('table')
          if (table) {
            const rows: string[][] = []
            const trs = table.querySelectorAll('tr')
            trs.forEach(tr => {
              const row: string[] = []
              const cells = tr.querySelectorAll('td, th')
              cells.forEach(cell => {
                row.push(cell.textContent?.trim() || '')
              })
              if (row.length > 0) {
                rows.push(row)
              }
            })
            if (rows.length > 0) {
              tableData.value = rows
              console.log('[表格调试] ✅ 从 HTML 成功提取表格数据:', tableData.value.length, '行 x', tableData.value[0]?.length || 0, '列')
            }
          }
        } catch (e) {
          console.warn('[表格调试] 从 HTML 解析表格失败:', e)
        }
      } else {
        console.log('[表格调试] tableData 已有效，不需要从 HTML 提取')
      }
      // ⚠️ 重要：如果 tableHtml 存在，直接使用它渲染，不再继续执行兜底逻辑
      // 但保留 tableData 用于网格编辑
      return
    }
    
    // ⚠️ 最后兜底：从 content 解析（可能包含 OCR 错误，不推荐）
    const content = chunk.content || ''
    console.log('[表格调试] 兜底逻辑 - content:', content ? `${content.substring(0, 100)}...` : '(空)')
    
    if (content) {
      // 尝试按制表符分隔（这是我们从结构化数据生成的格式）
      if (content.includes('\t')) {
        const lines = content.split('\n').filter(l => l.trim())
        if (lines.length > 0) {
          tableData.value = lines.map(l => l.split('\t').map(c => c.trim()))
          console.log('[表格调试] ✅ 从 content (制表符) 提取表格数据:', tableData.value.length, '行')
          return
        }
      }
      // 尝试按管道符分隔（Markdown 表格格式）
      if (content.includes('|')) {
        const lines = content.split('\n').filter(l => l.trim() && !l.match(/^[\s|:\-]+$/))
        if (lines.length > 0) {
          tableData.value = lines.map(l => {
            const cols = l.split('|').map(c => c.trim()).filter(c => c && !c.match(/^[\-:]+$/))
            return cols.length > 0 ? cols : ['']
          }).filter(row => row.length > 0 && row.some(cell => cell))
          if (tableData.value.length > 0) {
            console.log('[表格调试] ✅ 从 content (管道符) 提取表格数据:', tableData.value.length, '行')
            return
          }
        }
      }
      // 尝试按多个空格分隔（可能是 OCR 文本）
      const lines = content.split('\n').filter(l => l.trim())
      if (lines.length > 0) {
        const parsed = lines.map(l => l.split(/\s{2,}/).filter(c => c.trim()))
        if (parsed.length > 0 && parsed.some(row => row.length > 1)) {
          tableData.value = parsed
          console.log('[表格调试] ✅ 从 content (多空格) 提取表格数据:', tableData.value.length, '行')
          return
        }
      }
      // 如果都不行，至少显示一个单元格，内容是整个 content
      tableData.value = [[content]]
      console.log('[表格调试] ⚠️ 无法解析表格结构，显示为单个单元格')
    } else {
      console.log('[表格调试] ⚠️ content 为空，显示空表格')
      tableData.value = [['']]
    }
  } catch (e) {
    console.error('[表格调试] ❌ 初始化表格数据失败:', e, e.stack)
    const fallbackContent = chunk?.content || ''
    tableData.value = fallbackContent ? [[fallbackContent]] : [['无法加载表格数据']]
  }
  
  console.log('[表格调试] ===== 函数结束时的最终状态 =====')
  console.log('[表格调试] 最终 tableData:', tableData.value, '行数:', tableData.value?.length || 0)
  console.log('[表格调试] 最终 tableHtml:', tableHtml.value ? `${tableHtml.value.substring(0, 100)}...` : '(空)', '长度:', tableHtml.value?.length || 0)
  console.log('[表格调试] tableHtml.value 是否存在:', !!tableHtml.value)
  console.log('[表格调试] =========================================')
}

const onRowClick = async (data: any) => {
  // 同一个列表数据：直接使用左侧已加载的块数据，避免重复请求
  const chunkId = data.id || data.chunk_id
  if (!chunkId) return

  currentChunk.value = { ...data }
  editorContent.value = data.content || ''
  
  // ✅ 初始化表格数据（优先使用 meta.table_data）
  initializeTableData(currentChunk.value)

  // 若内容为空（例如 DB 不存正文），再请求详情补全
  if (!editorContent.value) {
    try {
      const res = await getChunkDetail(props.documentId, chunkId)
      currentChunk.value = res.data
      editorContent.value = res.data?.content || ''
      
      // ✅ 重要：重新初始化表格数据（因为获取了新的数据，可能包含更完整的 meta）
      initializeTableData(currentChunk.value)
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

// ✅ 表格编辑功能：添加行
const addRow = () => {
  if (tableData.value.length === 0) {
    tableData.value = [['']]
  } else {
    const colCount = tableData.value[0]?.length || 1
    tableData.value.push(Array(colCount).fill(''))
  }
}

// ✅ 表格编辑功能：添加列
const addCol = () => {
  if (tableData.value.length === 0) {
    tableData.value = [['']]
  } else {
    tableData.value.forEach(row => {
      row.push('')
    })
  }
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
    }
    
    /* ✅ 表格预览样式 */
    .table-html-wrapper {
      width: 100%;
      overflow-x: auto;
      padding: 10px;
      background: #fff;
      border-radius: 4px;
    }
    
    .table-html {
      width: 100%;
      overflow-x: auto;
      
      :deep(table) {
        width: 100%;
        border-collapse: collapse;
        border: 1px solid #ddd;
        background: white;
        
        th, td {
          border: 1px solid #ddd;
          padding: 8px 12px;
          text-align: left;
          vertical-align: top;
        }
        
        th {
          background-color: #f5f5f5;
          font-weight: 600;
        }
        
        tr:nth-child(even) {
          background-color: #f9f9f9;
        }
        
        tr:hover {
          background-color: #f0f0f0;
        }
      }
      
      :deep(thead) {
        background-color: #f5f5f5;
      }
    }
    
    .table-preview-from-cells {
      width: 100%;
      overflow-x: auto;
      
      .preview-table {
        width: 100%;
        border-collapse: collapse;
        border: 1px solid #ddd;
        background: white;
        
        td {
          border: 1px solid #ddd;
          padding: 8px;
          text-align: left;
          vertical-align: top;
        }
        
        tr:first-child td {
          background-color: #f5f5f5;
          font-weight: 600;
        }
        
        tr:nth-child(even) {
          background-color: #f9f9f9;
        }
      }
    }
  }
  
  .type-pill.text { background: linear-gradient(135deg, rgba(0,140,255,0.6), rgba(0,120,255,0.28)); color: #eaf2ff; box-shadow: 0 0 6px rgba(0,140,255,0.2); }
  .type-pill.table { background: linear-gradient(135deg, rgba(0,210,150,0.6), rgba(0,200,140,0.28)); color: #ecfff7; box-shadow: 0 0 6px rgba(0,210,150,0.2); }

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

