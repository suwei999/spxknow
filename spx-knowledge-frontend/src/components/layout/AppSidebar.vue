<template>
  <aside class="app-sidebar" :class="{ collapsed }">
    <el-menu
      :default-active="activeMenu"
      :collapse="collapsed"
      router
      :collapse-transition="false"
    >
      <el-menu-item index="/home">
        <el-icon><House /></el-icon>
        <span>首页</span>
      </el-menu-item>
      
      <el-menu-item index="/knowledge-bases">
        <el-icon><Collection /></el-icon>
        <span>知识库</span>
      </el-menu-item>
      
      <el-menu-item index="/documents">
        <el-icon><Document /></el-icon>
        <span>文档管理</span>
      </el-menu-item>
      
      <el-menu-item index="/search">
        <el-icon><Search /></el-icon>
        <span>搜索</span>
      </el-menu-item>
      
      <el-menu-item index="/qa">
        <el-icon><ChatLineRound /></el-icon>
        <span>智能问答</span>
      </el-menu-item>
      
      <el-menu-item index="/images">
        <el-icon><Picture /></el-icon>
        <span>图片管理</span>
      </el-menu-item>
      
      <el-menu-item index="/observability">
        <el-icon><DataBoard /></el-icon>
        <span>运维诊断</span>
      </el-menu-item>
    </el-menu>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  House,
  Collection,
  Document,
  Search,
  ChatLineRound,
  Picture,
  DataBoard
} from '@element-plus/icons-vue'

interface Props {
  collapsed?: boolean
}

defineProps<Props>()

const route = useRoute()

const activeMenu = computed(() => route.path)
</script>

<style lang="scss" scoped>
.app-sidebar {
  width: 240px;
  height: 100%;
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(10px);
  border-right: 1px solid rgba(255, 255, 255, 0.1);
  transition: width 0.3s;

  &.collapsed {
    width: 64px;
  }

  :deep(.el-menu) {
    background: transparent;
    border-right: none;
    color: #e4e7ed;

    .el-menu-item {
      color: rgba(255, 255, 255, 0.7);
      transition: all 0.3s ease;

      &:hover {
        background: rgba(64, 158, 255, 0.2);
        color: #409eff;
      }

      &.is-active {
        background: rgba(64, 158, 255, 0.2);
        color: #409eff;
        border-right: 3px solid #409eff;
      }
    }
  }
}
</style>

