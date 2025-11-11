<template>
  <div class="qa-page">
    <el-row :gutter="20">
      <el-col :span="6">
        <el-card class="session-list">
          <template #header>
            <div class="card-header">
              <span>会话列表</span>
              <el-button size="small" @click="handleCreateSession">新建会话</el-button>
            </div>
          </template>

          <div class="session-item" 
               v-for="session in sessions" 
               :key="session.session_id || session.id"
               :class="{ active: (currentSession?.session_id || currentSession?.id) === (session.session_id || session.id) }"
               @click="selectSession(session)">
            <div class="session-title">{{ session.session_name || session.title || `会话 ${session.session_id || session.id}` }}</div>
            <div class="session-time">{{ formatDateTime(session.created_at || session.last_activity) }}</div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="18">
        <el-card class="chat-area">
          <template #header>
            <div class="chat-header">
              <span>智能问答</span>
              <div class="header-actions" v-if="currentSession">
                <el-tag size="small" effect="plain" type="info">检索: {{ displaySearchType }}</el-tag>
                <el-tag size="small" effect="plain" type="info">阈值: {{ sessionConfig.similarity_threshold.toFixed(2) }}</el-tag>
                <el-tag size="small" effect="plain" type="info">来源: {{ sessionConfig.max_sources }}</el-tag>
                <el-button size="small" type="primary" plain @click="configDialogVisible = true">
                  配置
                </el-button>
              </div>
            </div>
          </template>

          <div class="chat-messages" ref="messagesRef">
            <div 
              v-for="message in messages" 
              :key="message.id"
              class="message"
              :class="{ 'user-message': message.type === 'user', 'assistant-message': message.type === 'assistant' }">
              <div class="message-content" v-html="renderMessageContent(message)"></div>
              <div
                v-if="message.type === 'assistant' && message.source_info && message.source_info.length"
                class="message-sources">
                <div class="source-title">参考来源</div>
                <ul class="source-list">
                  <li
                    v-for="(source, idx) in message.source_info"
                    :key="`${source.document_id || idx}`"
                    class="source-item">
                    <el-tag size="small" type="info">来源{{ idx + 1 }}</el-tag>
                    <span class="source-doc">
                      <a
                        v-if="source.document_id"
                        :href="getDocumentLink(source.document_id)"
                        target="_blank"
                        rel="noopener"
                      >
                        {{ source.document_title || `文档 ${source.document_id}` }}
                      </a>
                      <span v-else>{{ source.document_title || `文档${idx + 1}` }}</span>
                      <span v-if="source.document_id" class="source-doc-id">（ID: {{ source.document_id }}）</span>
                    </span>
                    <div v-if="source.content_snippet" class="source-snippet">{{ source.content_snippet }}</div>
                  </li>
                </ul>
              </div>
              <div class="message-time">{{ formatDateTime(message.created_at) }}</div>
            </div>
          </div>

          <div class="chat-input">
            <el-input
              v-model="inputText"
              type="textarea"
              :rows="3"
              placeholder="请输入问题..."
              @keydown.enter.exact.prevent="handleSendQuestion"
            />
            <div class="input-actions">
              <el-button type="primary" @click="handleSendQuestion" :loading="answering">
                发送
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog
      v-model="configDialogVisible"
      title="问答配置"
      width="460px"
      destroy-on-close
    >
      <el-form label-width="120px" :model="sessionConfig" class="config-form">
        <el-form-item label="检索方式">
          <el-select v-model="sessionConfig.search_type" placeholder="选择检索方式">
            <el-option
              v-for="opt in searchTypeOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="相似度阈值">
          <div class="threshold-control">
            <el-slider
              v-model="sessionConfig.similarity_threshold"
              :min="0"
              :max="1"
              :step="0.01"
              :format-tooltip="(val: number) => val.toFixed(2)"
            />
            <el-input-number
              v-model="sessionConfig.similarity_threshold"
              :min="0"
              :max="1"
              :step="0.01"
              :precision="2"
            />
          </div>
        </el-form-item>
        <el-form-item label="返回来源数">
          <el-input-number
            v-model="sessionConfig.max_sources"
            :min="1"
            :max="50"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingConfig" @click="handleSaveConfig">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, nextTick, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { createQASession, getQASessions, getQASessionDetail, askQuestion, updateSessionConfig } from '@/api/modules/qa'
import { formatDateTime } from '@/utils/format'

const messages = ref<any[]>([])
const sessions = ref<any[]>([])
const currentSession = ref<any>(null)
const inputText = ref('')
const answering = ref(false)
const messagesRef = ref<HTMLElement>()
const configDialogVisible = ref(false)
const savingConfig = ref(false)

const DEFAULT_THRESHOLD = 0.66
const DEFAULT_MAX_SOURCES = 10

const searchTypeOptions = [
  { label: '混合检索', value: 'hybrid' },
  { label: '向量检索', value: 'vector' },
  { label: '关键词检索', value: 'keyword' },
  { label: '精确匹配', value: 'exact' }
]

const sessionConfig = reactive({
  search_type: 'hybrid',
  similarity_threshold: DEFAULT_THRESHOLD,
  max_sources: DEFAULT_MAX_SOURCES
})

const searchTypeLabels: Record<string, string> = {
  hybrid: '混合检索',
  vector: '向量检索',
  keyword: '关键词检索',
  exact: '精确匹配'
}

const displaySearchType = computed(() => searchTypeLabels[sessionConfig.search_type] || sessionConfig.search_type || '混合检索')

const clampThreshold = (value: any) => {
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return DEFAULT_THRESHOLD
  return Math.min(1, Math.max(0, Number(numeric.toFixed(2))))
}

const clampMaxSources = (value: any) => {
  const numeric = Number(value)
  if (Number.isNaN(numeric) || numeric <= 0) return DEFAULT_MAX_SOURCES
  return Math.min(50, Math.max(1, Math.round(numeric)))
}

const applySessionConfig = (session: any) => {
  if (!session) return
  const searchConfig = session.search_config || {}
  sessionConfig.search_type = session.search_type || searchConfig.search_type || 'hybrid'
  sessionConfig.similarity_threshold = clampThreshold(searchConfig.similarity_threshold ?? DEFAULT_THRESHOLD)
  sessionConfig.max_sources = clampMaxSources(searchConfig.max_sources ?? DEFAULT_MAX_SOURCES)
}

const loadSessions = async () => {
  try {
    const res = await getQASessions()
    const payload: any = res?.data ?? res ?? []
    const list: any[] = Array.isArray(payload) ? payload : (payload?.sessions || payload?.list || [])
    sessions.value = Array.isArray(list) ? list : []
    if (sessions.value.length > 0 && !currentSession.value) {
      selectSession(sessions.value[0])
    }
  } catch (error: any) {
    // 无会话时返回404/空也不应弹错
    console.warn('加载会话列表失败或为空:', error?.response?.status)
    sessions.value = []
  }
}

const selectSession = (session: any) => {
  currentSession.value = session
  loadMessages(session.session_id || session.id)
}

const loadMessages = async (sessionId: string) => {
  try {
    if (!sessionId) return
    
    const res = await getQASessionDetail(sessionId)
    const session = res?.data ?? res
    
    if (!session) {
      console.warn('会话详情为空')
      return
    }
    
    currentSession.value = { ...(currentSession.value || {}), ...session }
    applySessionConfig(session)
    
    // 清空当前消息
    messages.value = []
    
    // 从会话详情中提取历史问答对（添加数据验证）
    if (session.questions && Array.isArray(session.questions) && session.questions.length > 0) {
      const sortedQuestions = [...session.questions].sort((a: any, b: any) => {
        const timeA = new Date(a.created_at || '').getTime()
        const timeB = new Date(b.created_at || '').getTime()
        return timeA - timeB
      })

      sortedQuestions.forEach((qa: any, index: number) => {
        // 验证问答数据完整性
        if (!qa || typeof qa !== 'object') {
          console.warn(`跳过无效的问答数据，索引: ${index}`)
          return
        }
        
        // 添加用户问题
        if (qa.question_content) {
          messages.value.push({
            id: `q_${qa.question_id || `temp_${index}`}`,
            type: 'user',
            content: qa.question_content,
            created_at: qa.created_at || new Date().toISOString()
          })
        }
        
        // 添加助手回答
        if (qa.answer_content) {
          const sources = normalizeSources(qa.source_info)
          const processing = normalizeProcessingInfo(qa.processing_info)

          messages.value.push({
            id: `a_${qa.question_id || `temp_${index}`}`,
            type: 'assistant',
            content: qa.answer_content,
            created_at: qa.created_at || new Date().toISOString(),
            source_info: sources,
            processing_info: processing
          })
        }
      })
    } else {
      // 如果没有历史消息，显示提示
      console.log('该会话暂无历史消息')
    }
    
    await nextTick()
    scrollToBottom()
  } catch (error: any) {
    console.warn('加载会话消息失败或为空:', error?.response?.status)
    // 清空消息列表即可，不弹错
    messages.value = []
  }
}

const handleCreateSession = async () => {
  try {
    const { ElMessageBox } = await import('element-plus')
    const { value } = await ElMessageBox.prompt('请输入会话名称（全局唯一）', '新建会话', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '会话名称不能为空',
      inputPlaceholder: '例如：技术讨论-2025-11-06'
    })
    const name = (value || '').trim()
    if (!name) return

    const res: any = await createQASession({ knowledge_base_id: 1, session_name: name })
    // 兼容后端自定义异常返回 {code:400,message}
    if (res && (res.code === 400 || res.data?.code === 400)) {
      const msg = res.message || res.data?.message || '创建会话失败'
      ElMessage.error(msg)
      return
    }
    const newSession = res?.data ?? res
    sessions.value.unshift(newSession)
    selectSession(newSession)
    ElMessage.success('会话创建成功')
  } catch (error: any) {
    if (error?.action === 'cancel') return
    console.error('创建会话失败:', error)
    ElMessage.error(error?.response?.data?.detail || error?.message || '创建会话失败')
  }
}

const handleSendQuestion = async () => {
  if (!inputText.value.trim()) {
    ElMessage.warning('请输入问题')
    return
  }

  if (!currentSession.value) {
    await handleCreateSession()
    if (!currentSession.value) return
  }

  const question = inputText.value.trim()
  const questionId = Date.now()
  
  // 添加用户问题到消息列表
  messages.value.push({
    id: `q_${questionId}`,
    type: 'user',
    content: question,
    created_at: new Date().toISOString()
  })

  inputText.value = ''
  answering.value = true

  await nextTick()
  scrollToBottom()

  const payload = {
    text_content: question,
    input_type: 'text',
    search_type: sessionConfig.search_type,
    similarity_threshold: clampThreshold(sessionConfig.similarity_threshold),
    max_sources: clampMaxSources(sessionConfig.max_sources)
  }

  try {
    const res = await askQuestion(currentSession.value.session_id || currentSession.value.id, payload)
    const answer = res?.data ?? res
    const sources = normalizeSources(answer.source_info)
    const processing = normalizeProcessingInfo(answer.processing_info)

    messages.value.push({
      id: `a_${questionId}`,
      type: 'assistant',
      content: answer.answer_content || answer.answer || '暂无回答',
      created_at: new Date().toISOString(),
      source_info: sources,
      processing_info: processing
    })

    await nextTick()
    scrollToBottom()
    
    // 重新加载会话消息以同步历史记录（延迟一下，确保后端保存完成）
    setTimeout(async () => {
      await loadMessages(currentSession.value.session_id || currentSession.value.id)
    }, 500)
  } catch (error: any) {
    console.error('问答失败:', error)
    const detail = error?.response?.data?.detail
    if (detail) {
      ElMessage.error(detail)
    } else {
      ElMessage.error('回答失败')
    }
    // 移除用户问题（因为失败）
    messages.value.pop()
  } finally {
    answering.value = false
  }
}


const scrollToBottom = () => {
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

const handleSaveConfig = async () => {
  if (!currentSession.value) return
  const sessionId = currentSession.value.session_id || currentSession.value.id
  if (!sessionId) return

  const payload = {
    search_type: sessionConfig.search_type,
    similarity_threshold: clampThreshold(sessionConfig.similarity_threshold),
    max_sources: clampMaxSources(sessionConfig.max_sources)
  }

  savingConfig.value = true
  try {
    await updateSessionConfig(sessionId, payload)
    currentSession.value = {
      ...(currentSession.value || {}),
      search_type: payload.search_type,
      search_config: {
        ...(currentSession.value?.search_config || {}),
        search_type: payload.search_type,
        similarity_threshold: payload.similarity_threshold,
        max_sources: payload.max_sources
      }
    }
    const idx = sessions.value.findIndex(
      (s) => (s.session_id || s.id) === sessionId
    )
    if (idx >= 0) {
      sessions.value[idx] = {
        ...sessions.value[idx],
        search_type: payload.search_type,
        search_config: {
          ...(sessions.value[idx].search_config || {}),
          search_type: payload.search_type,
          similarity_threshold: payload.similarity_threshold,
          max_sources: payload.max_sources
        }
      }
    }
    ElMessage.success('配置已更新')
    configDialogVisible.value = false
  } catch (error: any) {
    console.error('更新配置失败:', error)
    ElMessage.error(error?.response?.data?.detail || error?.message || '更新配置失败')
  } finally {
    savingConfig.value = false
  }
}

const normalizeSources = (sources: any): any[] => {
  if (!sources) return []
  if (typeof sources === 'string') {
    try {
      const parsed = JSON.parse(sources)
      return Array.isArray(parsed) ? parsed : []
    } catch (err) {
      console.warn('解析source_info失败:', err)
      return []
    }
  }
  return Array.isArray(sources) ? sources : []
}

const normalizeProcessingInfo = (info: any): Record<string, any> => {
  if (!info) return {}
  if (typeof info === 'string') {
    try {
      const parsed = JSON.parse(info)
      return parsed && typeof parsed === 'object' ? parsed : {}
    } catch (err) {
      console.warn('解析processing_info失败:', err)
      return {}
    }
  }
  return typeof info === 'object' ? info : {}
}

const escapeHtml = (str: string) =>
  str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

const renderMessageContent = (message: any) => {
  const raw = message?.content || ''
  const escaped = escapeHtml(raw)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br/>')

  if (!message?.source_info || !message.source_info.length) return escaped

  return escaped.replace(/\(来源(\d+)\)/g, (_match, numStr) => {
    const idx = Number(numStr) - 1
    if (idx >= 0 && idx < message.source_info.length) {
      const source = message.source_info[idx]
      const docId = source?.document_id
      if (docId) {
        const href = getDocumentLink(docId)
        return `<a class="content-source-link" href="${href}" target="_blank" rel="noopener">(来源${numStr})</a>`
      }
    }
    return `<span class="content-source-tag">(来源${numStr})</span>`
  })
}

const getDocumentLink = (docId: any): string => {
  if (!docId) return '#'
  return `/documents/${docId}`
}

onMounted(() => {
  loadSessions()
})
</script>

<style lang="scss" scoped>
.qa-page {
  .session-list {
    .session-item {
      padding: 14px;
      margin-bottom: 10px;
      cursor: pointer;
      border-radius: 10px;
      transition: background 0.25s ease, box-shadow 0.25s ease, transform 0.25s ease;
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(148, 163, 184, 0.16);
      box-shadow: 0 6px 18px rgba(15, 23, 42, 0.35);

      &:hover {
        background: rgba(59, 130, 246, 0.18);
        box-shadow: 0 10px 24px rgba(30, 64, 175, 0.35);
        transform: translateY(-2px);
      }

      &.active {
        background: linear-gradient(135deg, rgba(59, 130, 246, 0.28), rgba(37, 99, 235, 0.22));
        border-color: rgba(59, 130, 246, 0.55);
        box-shadow: 0 12px 28px rgba(37, 99, 235, 0.35);
      }

      .session-title {
        font-weight: 600;
        margin-bottom: 6px;
        color: #e2e8f0;
        font-size: 15px;
        letter-spacing: 0.2px;
      }

      .session-time {
        font-size: 12px;
        color: rgba(226, 232, 240, 0.72);
      }
    }
  }

  .chat-area {
    .chat-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .chat-messages {
      height: 500px;
      overflow-y: auto;
      margin-bottom: 20px;
      padding: 20px;

      .message {
        margin-bottom: 20px;

        .message-content {
          white-space: normal;
          word-break: break-word;

          .content-source-link {
            color: #60a5fa;
            text-decoration: none;

            &:hover {
              text-decoration: underline;
            }
          }

          .content-source-tag {
            color: rgba(148, 163, 184, 0.9);
          }
        }
 
        &.user-message {
          text-align: right;

          .message-content {
            background-color: #409eff;
            color: #fff;
            display: inline-block;
            padding: 10px 15px;
            border-radius: 8px;
          }
        }
 
        &.assistant-message {
          text-align: left;

          .message-content {
            background-color: rgba(15, 23, 42, 0.88);
            color: #e2e8f0;
            display: inline-block;
            padding: 12px 16px;
            border-radius: 12px;
            line-height: 1.6;
          }
        }

        .message-sources {
          margin-top: 10px;
          padding: 10px 12px;
          background-color: rgba(148, 163, 184, 0.1);
          border-radius: 10px;

          .source-title {
            font-size: 12px;
            color: rgba(226, 232, 240, 0.85);
            margin-bottom: 6px;
            font-weight: 600;
          }

          .source-list {
            list-style: none;
            padding: 0;
            margin: 0;
            display: flex;
            flex-direction: column;
            gap: 8px;
          }

          .source-item {
            display: flex;
            flex-direction: column;
            gap: 4px;
            color: rgba(203, 213, 225, 0.9);

            .source-doc {
              margin-left: 6px;
              font-weight: 600;

              a {
                color: #60a5fa;
                text-decoration: none;

                &:hover {
                  text-decoration: underline;
                }
              }

              .source-doc-id {
                margin-left: 4px;
                font-size: 12px;
                font-weight: 400;
                color: rgba(148, 163, 184, 0.9);
              }
            }

            .source-snippet {
              margin-left: 26px;
              font-size: 13px;
              color: rgba(226, 232, 240, 0.8);
              line-height: 1.5;
              white-space: pre-wrap;
            }
          }
        }
 
        .message-time {
          font-size: 12px;
          color: rgba(148, 163, 184, 0.9);
          margin-top: 5px;
        }
      }
    }

    .chat-input {
      .input-actions {
        margin-top: 10px;
        text-align: right;
      }
    }
  }
}

.threshold-control {
  display: flex;
  align-items: center;
  gap: 12px;

  :deep(.el-slider) {
    flex: 1;
  }
}

.config-form {
  .el-form-item {
    margin-bottom: 18px;
  }
}
</style>

