<template>
  <div class="search-page">
    <el-card>
      <template #header>
        <span>搜索</span>
      </template>

      <el-form :model="searchForm" @submit.prevent="handleSearch">
        <el-form-item>
          <el-input
            v-model="searchForm.query"
            placeholder="请输入搜索关键词..."
            size="large"
            @keyup.enter="handleSearch"
          >
            <template #append>
              <el-button @click="handleSearch">搜索</el-button>
            </template>
          </el-input>
        </el-form-item>

        <el-form-item>
          <el-radio-group v-model="searchForm.search_type">
            <el-radio label="vector">向量搜索</el-radio>
            <el-radio label="keyword">关键词搜索</el-radio>
            <el-radio label="hybrid">混合搜索</el-radio>
            <el-radio label="exact">精确匹配</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-button type="text" @click="showAdvanced = !showAdvanced">
          高级搜索
        </el-button>

        <el-collapse-transition>
          <div v-show="showAdvanced">
            <el-form-item label="知识库">
              <el-select v-model="searchForm.knowledge_base_id" placeholder="全部">
                <el-option label="全部" :value="undefined" />
                <el-option
                  v-for="kb in knowledgeBases"
                  :key="kb.id"
                  :label="kb.name"
                  :value="kb.id"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="分类">
              <el-select v-model="searchForm.category_id" placeholder="全部">
                <el-option label="全部" :value="undefined" />
                <!-- TODO: 加载分类 -->
              </el-select>
            </el-form-item>

            <el-form-item label="相似度阈值">
              <el-slider v-model="searchForm.similarity_threshold" :min="0" :max="1" :step="0.1" />
            </el-form-item>
          </div>
        </el-collapse-transition>
      </el-form>

      <div v-if="results.length > 0" class="search-results">
        <el-divider>搜索结果 ({{ total }})</el-divider>

        <el-card
          v-for="item in results"
          :key="item.id"
          class="result-item"
          @click="handleItemClick(item)"
        >
          <div class="result-title">{{ item.title || item.content?.substring(0, 100) }}</div>
          <div class="result-content">{{ item.content }}</div>
          <div class="result-meta">
            <el-tag size="small">{{ item.source_type }}</el-tag>
            <span class="similarity">相似度: {{ (item.similarity * 100).toFixed(1) }}%</span>
          </div>
        </el-card>

        <el-pagination
          v-model:current-page="page"
          v-model:page-size="size"
          :total="total"
          @current-change="handleSearch"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { search } from '@/api/modules/search'
import { getKnowledgeBases } from '@/api/modules/knowledge-bases'
import type { KnowledgeBase } from '@/types'

const searchForm = reactive({
  query: '',
  search_type: 'hybrid',
  knowledge_base_id: undefined as number | undefined,
  category_id: undefined as number | undefined,
  similarity_threshold: 0.7
})

const showAdvanced = ref(false)
const results = ref<any[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const page = ref(1)
const size = ref(20)
const total = ref(0)

const handleSearch = async () => {
  if (!searchForm.query.trim()) {
    ElMessage.warning('请输入搜索关键词')
    return
  }

  try {
    const res = await search({
      ...searchForm,
      page: page.value,
      size: size.value
    })
    const payload: any = (res && (res as any).data !== undefined) ? (res as any).data : res
    const list: any[] = Array.isArray(payload) ? payload : (payload?.results || [])
    results.value = list
    total.value = Array.isArray(payload) ? payload.length : (payload?.total || 0)
  } catch (error) {
    ElMessage.error('搜索失败')
  }
}

const handleItemClick = (item: any) => {
  if (item.document_id) {
    window.open(`/documents/${item.document_id}`, '_blank')
  }
}

// 加载知识库列表
;(async () => {
  try {
    const res = await getKnowledgeBases({ page: 1, size: 100 })
    knowledgeBases.value = res.data.items
  } catch (error) {
    console.error('加载知识库列表失败')
  }
})()
</script>

<style lang="scss" scoped>
.search-page {
  .search-results {
    margin-top: 20px;

    .result-item {
      margin-bottom: 20px;
      cursor: pointer;
      transition: box-shadow 0.3s;

      &:hover {
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
      }

      .result-title {
        font-weight: 500;
        margin-bottom: 8px;
      }

      .result-content {
        color: #666;
        margin-bottom: 8px;
      }

      .result-meta {
        display: flex;
        justify-content: space-between;
        align-items: center;

        .similarity {
          color: #999;
          font-size: 12px;
        }
      }
    }
  }
}
</style>

