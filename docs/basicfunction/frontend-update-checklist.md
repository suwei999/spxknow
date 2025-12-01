# 前端代码更新清单

本文档列出了需要在前端添加或更新的功能，以支持后端新实现的API。

## 需要更新的功能

### ✅ 已实现（无需更新）
- 搜索历史获取接口（`getSearchHistory`）
- 搜索建议接口（`getSearchSuggestions`）
- 文档预览接口（`getDocumentPreview`）
- 批量上传接口（`batchUploadDocuments`）

### ❌ 需要新增的功能

---

## 1. 搜索历史自动保存

### 状态
后端已自动保存，前端需要添加UI显示

### 需要添加的API接口
```typescript
// src/api/modules/search.ts
// 已存在：getSearchHistory, deleteSearchHistory
// 需要添加：
export const clearSearchHistory = () => {
  return request({
    url: '/search/history',
    method: 'delete'
  })
}
```

### 需要更新的页面
- `src/views/Search/index.vue`
  - 添加搜索历史侧边栏或下拉列表
  - 显示最近搜索记录
  - 支持点击历史记录快速搜索
  - 支持删除单条历史
  - 支持清空所有历史

### UI建议
- 在搜索框下方显示搜索历史（最多10条）
- 添加"清空历史"按钮
- 每条历史记录显示搜索关键词、时间、结果数量

---

## 2. 搜索结果高亮

### 状态
后端已返回 `highlighted_content`，前端需要显示

### 需要更新的页面
- `src/views/Search/index.vue` 或 `src/views/Search/results.vue`

### 更新内容
```vue
<template>
  <!-- 搜索结果项 -->
  <div class="search-result-item">
    <!-- 优先显示高亮内容，如果没有则显示原始内容 -->
    <div 
      class="result-content" 
      v-html="item.highlighted_content || item.content"
    />
  </div>
</template>

<style>
/* 高亮样式 */
.result-content :deep(mark) {
  background-color: #ffeb3b;
  padding: 2px 4px;
  border-radius: 2px;
  font-weight: 500;
}
</style>
```

### 注意事项
- 使用 `v-html` 时需要确保内容安全（后端已转义）
- 如果没有 `highlighted_content`，回退到 `content`

---

## 3. 批量删除文档

### 需要添加的API接口
```typescript
// src/api/modules/documents.ts
export const batchDeleteDocuments = (documentIds: number[]) => {
  return request({
    url: '/documents/batch/delete',
    method: 'post',
    data: { document_ids: documentIds }
  })
}
```

### 需要更新的页面
- `src/views/Documents/index.vue`

### 更新内容
1. 添加表格多选功能
2. 添加批量操作工具栏
3. 添加批量删除按钮
4. 实现批量删除逻辑

```vue
<template>
  <el-table 
    :data="documents" 
    v-loading="loading"
    @selection-change="handleSelectionChange"
  >
    <!-- 添加选择列 -->
    <el-table-column type="selection" width="55" />
    
    <!-- 其他列... -->
  </el-table>
  
  <!-- 批量操作工具栏 -->
  <div v-if="selectedDocuments.length > 0" class="batch-toolbar">
    <span>已选择 {{ selectedDocuments.length }} 项</span>
    <el-button type="danger" @click="handleBatchDelete">批量删除</el-button>
    <el-button @click="clearSelection">取消选择</el-button>
  </div>
</template>

<script setup lang="ts">
const selectedDocuments = ref<Document[]>([])

const handleSelectionChange = (selection: Document[]) => {
  selectedDocuments.value = selection
}

const handleBatchDelete = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedDocuments.value.length} 个文档吗？`,
      '批量删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const documentIds = selectedDocuments.value.map(d => d.id)
    const res = await batchDeleteDocuments(documentIds)
    
    if (res.code === 0) {
      ElMessage.success(`成功删除 ${res.data.deleted_count} 个文档`)
      if (res.data.failed_count > 0) {
        ElMessage.warning(`${res.data.failed_count} 个文档删除失败`)
      }
      clearSelection()
      loadData()
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('批量删除失败')
    }
  }
}

const clearSelection = () => {
  selectedDocuments.value = []
}
</script>
```

---

## 4. 批量移动文档

### 需要添加的API接口
```typescript
// src/api/modules/documents.ts
export const batchMoveDocuments = (data: {
  document_ids: number[]
  target_knowledge_base_id: number
  target_category_id?: number
}) => {
  return request({
    url: '/documents/batch/move',
    method: 'post',
    data
  })
}
```

### 需要更新的页面
- `src/views/Documents/index.vue`

### 更新内容
1. 在批量操作工具栏添加"批量移动"按钮
2. 添加移动对话框（选择目标知识库和分类）
3. 实现批量移动逻辑

```vue
<template>
  <!-- 批量操作工具栏 -->
  <div v-if="selectedDocuments.length > 0" class="batch-toolbar">
    <span>已选择 {{ selectedDocuments.length }} 项</span>
    <el-button @click="showMoveDialog = true">批量移动</el-button>
    <el-button type="danger" @click="handleBatchDelete">批量删除</el-button>
  </div>
  
  <!-- 批量移动对话框 -->
  <el-dialog v-model="showMoveDialog" title="批量移动文档" width="500px">
    <el-form :model="moveForm">
      <el-form-item label="目标知识库">
        <el-select v-model="moveForm.target_knowledge_base_id" placeholder="请选择知识库">
          <el-option
            v-for="kb in knowledgeBases"
            :key="kb.id"
            :label="kb.name"
            :value="kb.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="目标分类（可选）">
        <el-select v-model="moveForm.target_category_id" placeholder="请选择分类" clearable>
          <el-option
            v-for="cat in categories"
            :key="cat.id"
            :label="cat.name"
            :value="cat.id"
          />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showMoveDialog = false">取消</el-button>
      <el-button type="primary" @click="handleBatchMove">确定</el-button>
    </template>
  </el-dialog>
</template>
```

---

## 5. 批量标签管理

### 需要添加的API接口
```typescript
// src/api/modules/documents.ts
export const batchAddTags = (data: {
  document_ids: number[]
  tags: string[]
}) => {
  return request({
    url: '/documents/batch/tags/add',
    method: 'post',
    data
  })
}

export const batchRemoveTags = (data: {
  document_ids: number[]
  tags: string[]
}) => {
  return request({
    url: '/documents/batch/tags/remove',
    method: 'post',
    data
  })
}

export const batchReplaceTags = (data: {
  document_ids: number[]
  tags: string[]
}) => {
  return request({
    url: '/documents/batch/tags/replace',
    method: 'post',
    data
  })
}
```

### 需要更新的页面
- `src/views/Documents/index.vue`

### 更新内容
1. 在批量操作工具栏添加"批量标签"按钮
2. 添加标签管理对话框（支持添加、删除、替换）
3. 实现批量标签管理逻辑

---

## 6. 文档目录导航

### 需要添加的API接口
```typescript
// src/api/modules/documents.ts
export const getDocumentTOC = (documentId: number) => {
  return request({
    url: `/documents/${documentId}/toc`,
    method: 'get'
  })
}

export const searchInDocument = (documentId: number, params: {
  query: string
  page?: number
}) => {
  return request({
    url: `/documents/${documentId}/search`,
    method: 'get',
    params
  })
}
```

### 需要更新的页面
- `src/views/Documents/detail.vue` 或新建 `src/views/Documents/viewer.vue`

### 更新内容
1. 添加文档目录侧边栏
2. 显示目录树形结构
3. 支持点击目录项跳转到对应页码
4. 添加文档内搜索功能

```vue
<template>
  <div class="document-viewer">
    <!-- 目录侧边栏 -->
    <el-aside width="300px" class="toc-sidebar">
      <div class="toc-header">目录</div>
      <el-tree
        :data="toc"
        :props="{ children: 'children', label: 'title' }"
        @node-click="handleTocClick"
      />
      
      <!-- 文档内搜索 -->
      <div class="document-search">
        <el-input
          v-model="searchQuery"
          placeholder="在文档内搜索..."
          @keyup.enter="handleDocumentSearch"
        >
          <template #append>
            <el-button @click="handleDocumentSearch">搜索</el-button>
          </template>
        </el-input>
        <div v-if="searchResults.length > 0" class="search-results">
          <div
            v-for="result in searchResults"
            :key="result.chunk_id"
            class="search-result-item"
            @click="handleSearchResultClick(result)"
          >
            <div v-html="result.highlight" />
            <div class="result-page">第 {{ result.page }} 页</div>
          </div>
        </div>
      </div>
    </el-aside>
    
    <!-- 文档内容区域 -->
    <el-main>
      <iframe :src="previewUrl" class="document-preview" />
    </el-main>
  </div>
</template>
```

---

## 7. 个人数据统计

### 需要添加的API接口
```typescript
// src/api/modules/statistics.ts (新建文件)
import request from '../utils/request'

export const getPersonalStatistics = (params?: { period?: string }) => {
  return request({
    url: '/statistics/personal',
    method: 'get',
    params
  })
}

export const getTrends = (params: {
  metric: 'document_count' | 'search_count' | 'upload_count'
  period?: string
  start_date?: string
  end_date?: string
}) => {
  return request({
    url: '/statistics/trends',
    method: 'get',
    params
  })
}

export const getKnowledgeBaseHeatmap = () => {
  return request({
    url: '/statistics/knowledge-bases/heatmap',
    method: 'get'
  })
}

export const getSearchHotwords = (params?: {
  limit?: number
  period?: string
}) => {
  return request({
    url: '/statistics/search/hotwords',
    method: 'get',
    params
  })
}
```

### 需要创建的页面
- `src/views/Statistics/index.vue` (新建)

### 页面内容
1. 个人数据概览卡片（知识库数、文档数、存储使用等）
2. 数据趋势图表（使用 ECharts 或类似库）
3. 知识库使用热力图
4. 搜索热词展示

---

## 8. 导出功能

### 需要添加的API接口
```typescript
// src/api/modules/exports.ts (新建文件)
import request from '../utils/request'

export const exportKnowledgeBase = (kbId: number, data: {
  format: 'markdown' | 'json'
  include_documents?: boolean
  include_chunks?: boolean
}) => {
  return request({
    url: `/exports/knowledge-bases/${kbId}/export`,
    method: 'post',
    data
  })
}

export const exportDocument = (docId: number, data: {
  format: 'markdown' | 'json'
  include_chunks?: boolean
  include_images?: boolean
}) => {
  return request({
    url: `/exports/documents/${docId}/export`,
    method: 'post',
    data
  })
}

export const batchExportDocuments = (data: {
  document_ids: number[]
  format: 'markdown' | 'json'
}) => {
  return request({
    url: '/exports/documents/batch/export',
    method: 'post',
    data
  })
}

export const exportQAHistory = (data: {
  format: 'json' | 'csv'
  session_id?: number
  start_date?: string
  end_date?: string
}) => {
  return request({
    url: '/exports/qa/history/export',
    method: 'post',
    data
  })
}

export const getExportTask = (taskId: number) => {
  return request({
    url: `/exports/${taskId}`,
    method: 'get'
  })
}

export const downloadExportFile = (taskId: number) => {
  return request({
    url: `/exports/${taskId}/download`,
    method: 'get',
    responseType: 'blob'
  })
}
```

### 需要更新的页面
- `src/views/Documents/index.vue` - 添加导出按钮
- `src/views/KnowledgeBases/index.vue` - 添加导出按钮
- `src/views/QA/index.vue` - 添加导出按钮（如果存在）

### 更新内容
1. 在文档列表添加"导出"按钮（单个和批量）
2. 在知识库列表添加"导出"按钮
3. 添加导出任务管理页面（可选）
4. 实现导出进度显示和下载

---

## 优先级建议

### 高优先级（核心功能）
1. ✅ **搜索结果高亮** - 提升用户体验，简单易实现
2. ✅ **批量删除文档** - 常用功能，提高操作效率
3. ✅ **搜索历史显示** - 提升搜索体验

### 中优先级（重要功能）
4. ✅ **批量移动文档** - 常用功能
5. ✅ **文档目录导航** - 提升文档阅读体验
6. ✅ **批量标签管理** - 提高管理效率

### 低优先级（增强功能）
7. ✅ **个人数据统计** - 数据可视化，需要图表库
8. ✅ **导出功能** - 需要处理异步任务和下载

---

## 实现建议

### 1. 搜索结果高亮（最简单）
- 修改搜索结果显示组件
- 使用 `v-html` 显示 `highlighted_content`
- 添加 CSS 样式美化高亮效果

### 2. 批量操作（文档管理）
- 在文档列表页面添加表格多选
- 添加批量操作工具栏
- 实现批量删除、移动、标签管理

### 3. 搜索历史（搜索页面）
- 在搜索框下方或侧边显示历史记录
- 支持点击历史快速搜索
- 支持删除和清空操作

### 4. 文档目录（文档详情页）
- 在文档详情页添加目录侧边栏
- 使用 Element Plus 的 Tree 组件
- 实现目录点击跳转

### 5. 统计页面（新建页面）
- 创建统计页面路由
- 使用 ECharts 或类似库绘制图表
- 展示各项统计数据

### 6. 导出功能（各列表页）
- 在相关页面添加导出按钮
- 实现导出对话框
- 处理导出任务状态和下载

---

## 注意事项

1. **API 响应格式**：确保前端正确处理后端返回的 `{ code, message, data }` 格式
2. **错误处理**：所有 API 调用都需要添加错误处理
3. **加载状态**：异步操作需要显示加载状态
4. **用户反馈**：操作成功/失败需要显示提示消息
5. **数据隔离**：确保只显示当前用户的数据
6. **权限验证**：前端需要验证用户登录状态

---

## 快速开始

建议按以下顺序实现：

1. **第一步**：搜索结果高亮（30分钟）
   - 修改搜索结果显示
   - 添加高亮样式

2. **第二步**：批量删除（1小时）
   - 添加表格多选
   - 实现批量删除功能

3. **第三步**：搜索历史（1小时）
   - 添加历史记录显示
   - 实现历史操作

4. **第四步**：批量移动和标签（2小时）
   - 实现批量移动对话框
   - 实现批量标签管理

5. **第五步**：文档目录（2小时）
   - 添加目录侧边栏
   - 实现目录导航

6. **第六步**：统计和导出（3-4小时）
   - 创建统计页面
   - 实现导出功能

---

## 测试要点

每个功能实现后，需要测试：

1. ✅ API 调用是否正常
2. ✅ 数据是否正确显示
3. ✅ 错误处理是否完善
4. ✅ 用户体验是否良好
5. ✅ 边界情况是否处理

---

## 参考代码

可以参考现有的批量上传功能实现：
- `src/views/Documents/upload.vue` - 批量上传实现
- `src/api/modules/documents.ts` - API 调用示例

