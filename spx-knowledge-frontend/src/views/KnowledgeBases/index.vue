<template>
  <div class="knowledge-bases-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>知识库管理</span>
          <el-button type="primary" @click="handleCreate">创建知识库</el-button>
        </div>
      </template>

      <el-table :data="knowledgeBases" v-loading="loading">
        <el-table-column prop="name" label="名称">
          <template #default="{ row }">
            <el-link type="primary" @click="handleDetail(row)">
              {{ row.name }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" show-overflow-tooltip />
        <el-table-column prop="category_name" label="分类">
          <template #default="{ row }">
            <el-tag v-if="row.category_name" type="info">
              {{ row.category_name }}
            </el-tag>
            <span v-else class="no-category">未分类</span>
          </template>
        </el-table-column>
        <el-table-column prop="document_count" label="文档数" width="100">
          <template #default="{ row }">
            <el-tag>{{ row.document_count || 0 }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'">
              {{ row.status === 'active' ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="handleEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        @current-change="loadData"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import { getKnowledgeBases, deleteKnowledgeBase } from '@/api/modules/knowledge-bases'
import type { KnowledgeBase } from '@/types'

const router = useRouter()

const knowledgeBases = ref<KnowledgeBase[]>([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)

const loadData = async () => {
  loading.value = true
  try {
    const res = await getKnowledgeBases({ page: page.value, size: size.value })
    knowledgeBases.value = res.data.items
    total.value = res.data.total
  } catch (error) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

const handleCreate = () => {
  router.push('/knowledge-bases/create')
}

const handleEdit = (row: KnowledgeBase) => {
  router.push(`/knowledge-bases/${row.id}/edit`)
}

const handleDelete = async (row: KnowledgeBase) => {
  try {
    await ElMessageBox.confirm('确定要删除该知识库吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    await deleteKnowledgeBase(row.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

onMounted(() => {
  loadData()
})
</script>

<style lang="scss" scoped>
.knowledge-bases-page {
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .no-category {
    color: #909399;
    font-size: 12px;
  }
}
</style>

