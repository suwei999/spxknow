<template>
  <div class="home">
    <!-- 动态背景 -->
    <div class="animated-background">
      <div class="gradient-orb orb-1"></div>
      <div class="gradient-orb orb-2"></div>
      <div class="gradient-orb orb-3"></div>
    </div>

    <!-- 主要内容 -->
    <div class="home-container">
      <!-- 标题区域 -->
      <div class="hero-section">
        <div class="title-wrapper">
          <h1 class="main-title">
            <span class="title-word">SPX</span>
            <span class="title-word gradient-text">Knowledge</span>
            <span class="title-word">Base</span>
          </h1>
          <p class="subtitle">AI驱动的智能知识库系统</p>
        </div>

        <!-- 快速操作 -->
        <div class="quick-actions">
          <el-button 
            type="primary" 
            size="large" 
            @click="$router.push('/qa/chat')"
            class="action-btn"
          >
            <el-icon><ChatDotRound /></el-icon>
            <span>开始对话</span>
          </el-button>
          <el-button 
            size="large" 
            @click="$router.push('/knowledge-bases/create')"
            class="action-btn"
          >
            <el-icon><Plus /></el-icon>
            <span>创建知识库</span>
          </el-button>
        </div>
      </div>

      <!-- 特性展示 -->
      <div class="features-section">
        <h2 class="section-title">核心优势</h2>
        <div class="features-grid">
          <div class="feature-card" v-for="(feature, index) in features" :key="index">
            <div class="feature-icon" :class="`icon-${index + 1}`">
              <el-icon :size="48">
                <component :is="feature.icon" />
              </el-icon>
            </div>
            <h3>{{ feature.title }}</h3>
            <p>{{ feature.description }}</p>
          </div>
        </div>
      </div>

      <!-- 统计数据 -->
      <div class="stats-section">
        <div class="stat-item" v-for="(stat, index) in stats" :key="index">
          <div class="stat-value">{{ stat.value }}</div>
          <div class="stat-label">{{ stat.label }}</div>
        </div>
      </div>

      <!-- 最近活动 -->
      <div class="recent-section">
        <h2 class="section-title">最近操作</h2>
        <div class="recent-list">
          <div class="recent-item" v-for="(item, index) in recentActivities" :key="index">
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.text }}</span>
            <span class="time">{{ item.time }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { 
  ChatDotRound, 
  Plus, 
  Document, 
  Search, 
  CollectionTag,
  Lightning,
  DataAnalysis,
  Connection
} from '@element-plus/icons-vue'

const router = useRouter()

const features = ref([
  {
    icon: 'ChatDotRound',
    title: '智能对话',
    description: '基于RAG技术的AI问答系统，支持多模态输入，提供精准答案'
  },
  {
    icon: 'Lightning',
    title: '快速检索',
    description: '向量检索+关键词检索的混合搜索，毫秒级响应'
  },
  {
    icon: 'Document',
    title: '多格式支持',
    description: '支持PDF、Word、PPT、图片等多种格式，智能解析与索引'
  },
  {
    icon: 'DataAnalysis',
    title: '智能向量化',
    description: '基于Ollama的本地化向量化，保护数据安全'
  },
  {
    icon: 'CollectionTag',
    title: '知识分类',
    description: '智能标签推荐，多层次知识分类体系'
  },
  {
    icon: 'Connection',
    title: '实时同步',
    description: '文档修改实时向量化，知识库即时更新'
  }
])

const stats = ref([
  { value: '∞', label: '知识库' },
  { value: '0', label: '文档总数' },
  { value: '0', label: '问答次数' },
  { value: '100%', label: '系统状态' }
])

const recentActivities = ref([
  { icon: 'Document', text: '上传了新的文档', time: '2小时前' },
  { icon: 'ChatDotRound', text: '完成了一次对话', time: '5小时前' },
  { icon: 'CollectionTag', text: '创建了新的标签', time: '1天前' }
])

onMounted(() => {
  // 加载统计数据
  loadStats()
})

const loadStats = async () => {
  // TODO: 从API加载实际统计数据
  // const res = await getStats()
  // stats.value = res.data
}
</script>

<style lang="scss" scoped>
.home {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #16213e 100%);
  color: #ffffff;

  .animated-background {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    overflow: hidden;
    opacity: 0.6;

    .gradient-orb {
      position: absolute;
      border-radius: 50%;
      filter: blur(80px);
      animation: float 20s infinite ease-in-out;
    }

    .orb-1 {
      width: 400px;
      height: 400px;
      background: radial-gradient(circle, #409eff 0%, transparent 70%);
      top: -200px;
      left: -200px;
      animation-delay: 0s;
    }

    .orb-2 {
      width: 500px;
      height: 500px;
      background: radial-gradient(circle, #67c23a 0%, transparent 70%);
      bottom: -250px;
      right: -250px;
      animation-delay: 5s;
    }

    .orb-3 {
      width: 300px;
      height: 300px;
      background: radial-gradient(circle, #e6a23c 0%, transparent 70%);
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      animation-delay: 10s;
    }
  }

  .home-container {
    position: relative;
    z-index: 1;
    padding: 40px;
    max-width: 1400px;
    margin: 0 auto;
  }

  .hero-section {
    text-align: center;
    padding: 60px 0;
    margin-bottom: 80px;

    .title-wrapper {
      margin-bottom: 40px;
    }

    .main-title {
      font-size: 64px;
      font-weight: 700;
      margin: 0;
      line-height: 1.2;
      display: flex;
      justify-content: center;
      gap: 16px;
      flex-wrap: wrap;

      .title-word {
        display: inline-block;
        animation: fadeInUp 0.6s ease-out backwards;
        
        &:nth-child(1) {
          animation-delay: 0.1s;
        }
        &:nth-child(2) {
          animation-delay: 0.2s;
        }
        &:nth-child(3) {
          animation-delay: 0.3s;
        }
      }

      .gradient-text {
        background: linear-gradient(135deg, #409eff 0%, #67c23a 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
      }
    }

    .subtitle {
      font-size: 20px;
      color: rgba(255, 255, 255, 0.7);
      margin-top: 20px;
      animation: fadeInUp 0.6s ease-out 0.4s backwards;
    }

    .quick-actions {
      display: flex;
      justify-content: center;
      gap: 20px;
      margin-top: 40px;
      animation: fadeInUp 0.6s ease-out 0.5s backwards;

      .action-btn {
        padding: 12px 32px;
        font-size: 16px;
        border-radius: 8px;
        transition: all 0.3s ease;

        &:hover {
          transform: translateY(-2px);
          box-shadow: 0 8px 24px rgba(64, 158, 255, 0.3);
        }
      }
    }
  }

  .features-section {
    margin-bottom: 80px;

    .section-title {
      font-size: 32px;
      font-weight: 600;
      margin-bottom: 40px;
      text-align: center;
    }

    .features-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 30px;
    }

    .feature-card {
      background: rgba(255, 255, 255, 0.05);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 16px;
      padding: 32px;
      transition: all 0.3s ease;
      position: relative;
      overflow: hidden;

      &::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 2px;
        background: linear-gradient(90deg, transparent, #409eff, transparent);
        transform: translateX(-100%);
        transition: transform 0.6s ease;
      }

      &:hover {
        transform: translateY(-8px);
        background: rgba(255, 255, 255, 0.08);
        box-shadow: 0 12px 32px rgba(64, 158, 255, 0.2);

        &::before {
          transform: translateX(100%);
        }
      }

      .feature-icon {
        margin-bottom: 20px;
        width: 80px;
        height: 80px;
        border-radius: 16px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(64, 158, 255, 0.1);
        color: #409eff;
      }

      h3 {
        font-size: 20px;
        font-weight: 600;
        margin-bottom: 12px;
      }

      p {
        color: rgba(255, 255, 255, 0.7);
        line-height: 1.6;
        margin: 0;
      }
    }
  }

  .stats-section {
    display: flex;
    justify-content: space-around;
    background: rgba(255, 255, 255, 0.05);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 16px;
    padding: 40px;
    margin-bottom: 80px;

    .stat-item {
      text-align: center;

      .stat-value {
        font-size: 48px;
        font-weight: 700;
        background: linear-gradient(135deg, #409eff 0%, #67c23a 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 8px;
      }

      .stat-label {
        color: rgba(255, 255, 255, 0.7);
        font-size: 14px;
      }
    }
  }

  .recent-section {
    .section-title {
      font-size: 24px;
      font-weight: 600;
      margin-bottom: 24px;
    }

    .recent-list {
      background: rgba(255, 255, 255, 0.05);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 16px;
      padding: 20px;

      .recent-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 16px;
        margin-bottom: 8px;
        border-radius: 8px;
        transition: all 0.3s ease;

        &:hover {
          background: rgba(255, 255, 255, 0.05);
        }

        .time {
          margin-left: auto;
          color: rgba(255, 255, 255, 0.5);
          font-size: 12px;
        }
      }
    }
  }
}

@keyframes float {
  0%, 100% {
    transform: translate(0, 0);
  }
  25% {
    transform: translate(20px, -20px);
  }
  50% {
    transform: translate(-20px, 20px);
  }
  75% {
    transform: translate(20px, 20px);
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>

