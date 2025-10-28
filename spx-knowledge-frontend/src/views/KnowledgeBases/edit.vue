<template>
  <el-card>
    <template #header>
      <span>编辑知识库</span>
    </template>

    <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入知识库名称" />
      </el-form-item>

      <el-form-item label="描述" prop="description">
        <el-input v-model="form.description" type="textarea" :rows="4" placeholder="请输入知识库描述" />
      </el-form-item>

      <el-form-item label="分类" prop="category_id">
        <el-select v-model="form.category_id" placeholder="请选择分类" clearable>
          <el-option
            v-for="category in categories"
            :key="category.id"
            :label="category.name"
            :value="category.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="标签" prop="tags">
        <el-select
          v-model="form.tags"
          multiple
          filterable
          allow-create
          placeholder="请输入或选择标签"
        >
          <el-option
            v-for="tag in tags"
            :key="tag"
            :label="tag"
            :value="tag"
          />
        </el-select>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" @click="handleSubmit" :loading="loading">保存</el-button>
        <el-button @click="handleCancel">取消</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getKnowledgeBaseDetail, updateKnowledgeBase } from '@/api/modules/knowledge-bases'

const route = useRoute()
const router = useRouter()
const knowledgeBaseId = Number(route.params.id)

const form = ref({
  name: '',
  description: '',
  category_id: null as number | null,
  tags: [] as string[]
})

const rules = {
  name: [{ required: true, message: '请输入知识库名称', trigger: 'blur' }]
}

const loading = ref(false)
const categories = ref<any[]>([])
const tags = ref<string[]>([])
const formRef = ref()

const loadDetail = async () => {
  loading.value = true
  try {
    const res = await getKnowledgeBaseDetail(knowledgeBaseId)
    Object.assign(form.value, res.data)
  } catch (error) {
    ElMessage.error('加载详情失败')
  } finally {
    loading.value = false
  }
}

const handleSubmit = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid: boolean) => {
    if (valid) {
      loading.value = true
      try {
        await updateKnowledgeBase(knowledgeBaseId, form.value)
        ElMessage.success('保存成功')
        router.push(`/knowledge-bases/${knowledgeBaseId}`)
      } catch (error) {
        ElMessage.error('保存失败')
      } finally {
        loading.value = false
      }
    }
  })
}

const handleCancel = () => {
  router.back()
}

onMounted(() => {
  loadDetail()
})
</script>

<style lang="scss" scoped>
.el-form {
  max-width: 800px;
}
</style>

