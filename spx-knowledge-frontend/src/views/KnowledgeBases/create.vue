<template>
  <div class="create-knowledge-base-page">
    <el-card>
      <template #header>
        <span>创建知识库</span>
      </template>

      <el-form :model="form" :rules="rules" ref="formRef" label-width="120px">
        <el-form-item label="知识库名称" required>
          <el-input v-model="form.name" placeholder="请输入知识库名称" />
        </el-form-item>

        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="4" placeholder="请输入描述" />
        </el-form-item>

        <el-form-item label="分类" prop="categoryValue">
          <el-select
            v-model="form.categoryValue"
            filterable
            allow-create
            default-first-option
            clearable
            :loading="loadingCategories"
            placeholder="选择或输入分类"
          >
            <el-option
              v-for="opt in categoryOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
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
const loadingCategories = ref(false)
const categoryOptions = ref<{ label: string; value: number }[]>([])

const form = ref({
  name: '',
  description: '',
  // 可能为 number(已有分类 id) 或 string(新输入分类名)
  categoryValue: '' as number | string | ''
})

const formRef = ref()
const rules = {
  name: [{ required: true, message: '请输入知识库名称', trigger: 'blur' }],
  categoryValue: [{ validator: (_: any, v: any, cb: any) => {
    if (typeof v === 'number') return cb()
    if (typeof v === 'string' && v.trim()) return cb()
    cb(new Error('请选择或输入分类'))
  }, trigger: 'change' }]
} as any

const loadCategories = async () => {
  try {
    loadingCategories.value = true
    const res = await getCategories()
    const list = res?.data?.list ?? res?.data ?? []
    categoryOptions.value = list.map((c: any) => ({ label: c.name, value: c.id }))
  } catch (error) {
    ElMessage.error('加载分类列表失败')
  } finally {
    loadingCategories.value = false
  }
}

const handleSubmit = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    const payload: any = {
      name: form.value.name,
      description: form.value.description
    }
    const cv = form.value.categoryValue
    if (typeof cv === 'number') payload.category_id = cv
    else if (typeof cv === 'string' && cv.trim()) payload.category_name = cv.trim()

    await createKnowledgeBase(payload)
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

