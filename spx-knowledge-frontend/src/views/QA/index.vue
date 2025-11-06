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
            <span>智能问答</span>
          </template>

          <div class="chat-messages" ref="messagesRef">
            <div 
              v-for="message in messages" 
              :key="message.id"
              class="message"
              :class="{ 'user-message': message.type === 'user', 'assistant-message': message.type === 'assistant' }">
              <div class="message-content">{{ message.content }}</div>
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
              <el-upload
                :before-upload="handleUploadImage"
                :show-file-list="false"
                accept="image/*"
              >
                <el-button>上传图片</el-button>
              </el-upload>
              <el-button type="primary" @click="handleSendQuestion" :loading="answering">
                发送
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { createQASession, getQASessions, getQASessionDetail, askQuestion } from '@/api/modules/qa'
import { formatDateTime } from '@/utils/format'

const messages = ref<any[]>([])
const sessions = ref<any[]>([])
const currentSession = ref<any>(null)
const inputText = ref('')
const answering = ref(false)
const messagesRef = ref<HTMLElement>()

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
    const session = res.data
    
    if (!session) {
      console.warn('会话详情为空')
      return
    }
    
    // 清空当前消息
    messages.value = []
    
    // 从会话详情中提取历史问答对（添加数据验证）
    if (session.questions && Array.isArray(session.questions) && session.questions.length > 0) {
      session.questions.forEach((qa: any, index: number) => {
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
          messages.value.push({
            id: `a_${qa.question_id || `temp_${index}`}`,
            type: 'assistant',
            content: qa.answer_content,
            created_at: qa.created_at || new Date().toISOString()
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

  try {
    const res = await askQuestion(currentSession.value.session_id || currentSession.value.id, {
      text_content: question,
      input_type: 'text',
      search_type: 'hybrid'
    })

    // 添加助手回答到消息列表
    messages.value.push({
      id: `a_${questionId}`,
      type: 'assistant',
      content: res.data.answer_content || res.data.answer || '暂无回答',
      created_at: new Date().toISOString(),
      source_info: res.data.source_info,
      processing_info: res.data.processing_info
    })

    await nextTick()
    scrollToBottom()
    
    // 重新加载会话消息以同步历史记录（延迟一下，确保后端保存完成）
    setTimeout(async () => {
      await loadMessages(currentSession.value.session_id || currentSession.value.id)
    }, 500)
  } catch (error: any) {
    console.error('问答失败:', error)
    ElMessage.error(error?.response?.data?.detail || '回答失败')
    // 移除用户问题（因为失败）
    messages.value.pop()
  } finally {
    answering.value = false
  }
}

const handleUploadImage = async (file: File) => {
  if (!currentSession.value) {
    ElMessage.warning('请先创建或选择会话')
    return false
  }

  // 检查文件类型
  if (!file.type.startsWith('image/')) {
    ElMessage.error('请上传图片文件')
    return false
  }

  // 检查文件大小（限制10MB）
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.error('图片大小不能超过10MB')
    return false
  }

  answering.value = true

  try {
    const res = await askQuestion(currentSession.value.session_id || currentSession.value.id, {
      image_file: file,
      input_type: 'image',
      search_type: 'hybrid'
    })

    // 添加用户消息（显示图片）
    messages.value.push({
      id: `img_${Date.now()}`,
      type: 'user',
      content: `[图片] ${file.name}`,
      image_url: URL.createObjectURL(file),
      created_at: new Date().toISOString()
    })

    // 添加助手回答
    messages.value.push({
      id: `a_${Date.now()}`,
      type: 'assistant',
      content: res.data.answer_content || res.data.answer || '暂无回答',
      created_at: new Date().toISOString(),
      source_info: res.data.source_info,
      processing_info: res.data.processing_info
    })

    await nextTick()
    scrollToBottom()
    
    // 重新加载会话消息以同步历史记录（延迟一下，确保后端保存完成）
    setTimeout(async () => {
      await loadMessages(currentSession.value.session_id || currentSession.value.id)
    }, 500)
    
    ElMessage.success('图片上传成功')
  } catch (error: any) {
    console.error('图片问答失败:', error)
    ElMessage.error(error?.response?.data?.detail || '图片问答失败')
  } finally {
    answering.value = false
  }

  return false // 阻止自动上传
}

const scrollToBottom = () => {
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

onMounted(() => {
  loadSessions()
})
</script>

<style lang="scss" scoped>
.qa-page {
  .session-list {
    .session-item {
      padding: 12px;
      margin-bottom: 8px;
      cursor: pointer;
      border-radius: 4px;
      transition: background-color 0.3s;

      &:hover {
        background-color: #f5f5f5;
      }

      &.active {
        background-color: #e6f7ff;
      }

      .session-title {
        font-weight: 500;
        margin-bottom: 4px;
      }

      .session-time {
        font-size: 12px;
        color: #999;
      }
    }
  }

  .chat-area {
    .chat-messages {
      height: 500px;
      overflow-y: auto;
      margin-bottom: 20px;
      padding: 20px;

      .message {
        margin-bottom: 20px;

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
            background-color: #f5f5f5;
            display: inline-block;
            padding: 10px 15px;
            border-radius: 8px;
          }
        }

        .message-time {
          font-size: 12px;
          color: #999;
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
</style>

