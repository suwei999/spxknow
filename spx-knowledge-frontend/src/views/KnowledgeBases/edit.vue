<template>
  <el-card>
    <template #header>
      <span>编辑知识库</span>
    </template>

    <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入知识库名称" disabled />
      </el-form-item>

      <el-form-item label="描述" prop="description">
        <el-input v-model="form.description" type="textarea" :rows="4" placeholder="请输入知识库描述" />
      </el-form-item>

      <el-form-item label="分类" prop="category_id">
        <el-select v-model="form.category_id" placeholder="请选择分类" clearable :loading="loadingCategories">
          <el-option
            v-for="opt in categoryOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="状态" prop="is_active">
        <el-switch
          v-model="form.is_active"
          :active-value="true"
          :inactive-value="false"
          active-text="启用"
          inactive-text="禁用"
        />
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
import { getKnowledgeBaseDetail, updateKnowledgeBase, getCategories } from '@/api/modules/knowledge-bases'

const route = useRoute()
const router = useRouter()
const knowledgeBaseId = Number(route.params.id)

const form = ref({
  name: '',
  description: '',
  category_id: null as number | null,
  is_active: true,
  tags: [] as string[]
})

const rules = {
  name: [{ required: true, message: '请输入知识库名称', trigger: 'blur' }]
}

const loading = ref(false)
const loadingCategories = ref(false)
const categoryOptions = ref<{ label: string; value: number }[]>([])
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

const loadCategories = async () => {
  try {
    loadingCategories.value = true
    const res = await getCategories()
    const list = res?.data?.list ?? res?.data ?? []
    categoryOptions.value = list.map((c: any) => ({ label: c.name, value: c.id }))
  } catch (error) {
    // 忽略错误
  } finally {
    loadingCategories.value = false
  }
}

const handleSubmit = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid: boolean) => {
    if (valid) {
      loading.value = true
      try {
        // 仅提交允许修改的字段
        await updateKnowledgeBase(knowledgeBaseId, {
          description: form.value.description,
          category_id: form.value.category_id as number | undefined,
          is_active: form.value.is_active
        })
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
  loadCategories()
  loadDetail()
})
</script>

<style lang="scss" scoped>
.el-form {
  max-width: 800px;
}
</style>

