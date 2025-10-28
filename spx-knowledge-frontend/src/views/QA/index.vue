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
               :key="session.id"
               :class="{ active: currentSession?.id === session.id }"
               @click="selectSession(session)">
            <div class="session-title">{{ session.title }}</div>
            <div class="session-time">{{ formatDateTime(session.created_at) }}</div>
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
              @keydown.enter="handleSendQuestion"
            />
            <div class="input-actions">
              <el-button @click="handleUploadImage">上传图片</el-button>
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
import { createQASession, getQASessions, askQuestion } from '@/api/modules/qa'
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
    sessions.value = res.data
    if (sessions.value.length > 0 && !currentSession.value) {
      selectSession(sessions.value[0])
    }
  } catch (error) {
    ElMessage.error('加载会话列表失败')
  }
}

const selectSession = (session: any) => {
  currentSession.value = session
  loadMessages(session.id)
}

const loadMessages = async (sessionId: string) => {
  // TODO: 加载会话消息
}

const handleCreateSession = async () => {
  try {
    const res = await createQASession({ knowledge_base_id: 1 })
    sessions.value.unshift(res.data)
    selectSession(res.data)
    ElMessage.success('会话创建成功')
  } catch (error) {
    ElMessage.error('创建会话失败')
  }
}

const handleSendQuestion = async () => {
  if (!inputText.value.trim()) return

  if (!currentSession.value) {
    await handleCreateSession()
  }

  const question = inputText.value
  messages.value.push({
    id: Date.now(),
    type: 'user',
    content: question,
    created_at: new Date().toISOString()
  })

  inputText.value = ''
  answering.value = true

  try {
    const res = await askQuestion(currentSession.value.id, {
      text_content: question,
      input_type: 'text',
      search_type: 'hybrid'
    })

    messages.value.push({
      id: Date.now() + 1,
      type: 'assistant',
      content: res.data.answer,
      created_at: new Date().toISOString()
    })

    await nextTick()
    scrollToBottom()
  } catch (error) {
    ElMessage.error('回答失败')
  } finally {
    answering.value = false
  }
}

const handleUploadImage = () => {
  ElMessage.info('图片上传功能待开发')
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

