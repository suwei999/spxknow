<template>
  <header class="app-header">
    <div class="header-left">
      <el-icon :size="20" @click="handleToggleSidebar">
        <Menu />
      </el-icon>
      <h1 class="app-title">{{ appTitle }}</h1>
    </div>
    <div class="header-right">
      <span>用户信息</span>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAppStore } from '@/stores/modules/app'
import { Menu } from '@element-plus/icons-vue'

const emit = defineEmits(['toggle-sidebar'])

const appStore = useAppStore()
const appTitle = computed(() => appStore.appTitle)

const handleToggleSidebar = () => {
  emit('toggle-sidebar')
}
</script>

<style lang="scss" scoped>
.app-header {
  height: 60px;
  padding: 0 20px;
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #e4e7ed;

  .header-left {
    display: flex;
    align-items: center;
    gap: 12px;

    .el-icon {
      cursor: pointer;
      transition: all 0.3s ease;
      padding: 8px;
      border-radius: 8px;

      &:hover {
        background: rgba(64, 158, 255, 0.2);
        color: #409eff;
      }
    }

    .app-title {
      font-size: 18px;
      font-weight: 600;
      margin: 0;
      background: linear-gradient(135deg, #409eff 0%, #67c23a 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
  }

  .header-right {
    display: flex;
    align-items: center;
    color: rgba(255, 255, 255, 0.7);
  }
}
</style>

