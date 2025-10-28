<template>
  <div class="create-knowledge-base-page">
    <el-card>
      <template #header>
        <span>创建知识库</span>
      </template>

      <el-form :model="form" label-width="120px">
        <el-form-item label="知识库名称" required>
          <el-input v-model="form.name" placeholder="请输入知识库名称" />
        </el-form-item>

        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="4" placeholder="请输入描述" />
        </el-form-item>

        <el-form-item label="分类">
          <el-select v-model="form.category_id" placeholder="请选择分类">
            <el-option
              v-for="category in categories"
              :key="category.id"
              :label="category.name"
              :value="category.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="handleSubmit" :loading="saving">创建</el-button>
          <el-button @click="$router.back()">取消</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createKnowledgeBase, getCategories } from '@/api/modules/knowledge-bases'

const router = useRouter()
const saving = ref(false)
const categories = ref<any[]>([])

const form = ref({
  name: '',
  description: '',
  category_id: undefined as number | undefined
})

const loadCategories = async () => {
  try {
    const res = await getCategories()
    categories.value = res.data
  } catch (error) {
    ElMessage.error('加载分类列表失败')
  }
}

const handleSubmit = async () => {
  if (!form.value.name) {
    ElMessage.warning('请输入知识库名称')
    return
  }

  saving.value = true
  try {
    await createKnowledgeBase(form.value)
    ElMessage.success('创建成功')
    router.push('/knowledge-bases')
  } catch (error) {
    ElMessage.error('创建失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadCategories()
})
</script>

<style lang="scss" scoped>
.create-knowledge-base-page {
  max-width: 800px;
  margin: 0 auto;
}
</style>

