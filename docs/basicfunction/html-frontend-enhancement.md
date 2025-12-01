# HTML 前端功能增强建议

> 检查时间：2025-01-XX  
> 检查范围：前端对 HTML 文档的支持情况

## 1. 当前前端支持情况

### 1.1 已实现的功能 ✅

1. **HTML 文件预览** ✅
   - 位置：`detail.vue:82-88`
   - 实现：使用 iframe 直接显示 HTML 文件
   - 状态：✅ 已实现

2. **HTML 文件类型识别** ✅
   - 位置：`detail.vue:252-257`
   - 实现：`isHtml` 计算属性正确识别 HTML 文件
   - 状态：✅ 已实现

3. **分块类型显示** ✅
   - 位置：`detail.vue:106`
   - 实现：分块列表显示 `chunk_type` 字段
   - 状态：✅ 已实现（基础功能）

4. **目录导航** ✅
   - 位置：`detail.vue:141-160`
   - 实现：支持目录树显示和导航
   - 状态：✅ 已实现

### 1.2 可以优化的功能 ⚠️

1. **分块类型显示优化** ⚠️
   - 当前：直接显示 `chunk_type` 值（如 `heading_section`、`code_block`）
   - 建议：使用更友好的中文标签显示

2. **分块元数据显示** ⚠️
   - 当前：分块详情对话框只显示图片分块的元数据
   - 建议：显示 HTML 特有的元数据（`heading_level`、`heading_path`、`code_language` 等）

3. **代码块高亮显示** ⚠️
   - 当前：代码块使用 `<pre>` 标签显示，无语法高亮
   - 建议：使用 highlight.js 进行代码高亮（已引入）

## 2. 建议的优化方案

### 2.1 分块类型显示优化

**当前实现**：
```vue
<el-table-column prop="chunk_type" label="类型" width="120" />
```

**建议优化**：
```vue
<el-table-column label="类型" width="120">
  <template #default="{ row }">
    <el-tag :type="getChunkTypeTagType(row.chunk_type)" size="small">
      {{ getChunkTypeLabel(row.chunk_type) }}
    </el-tag>
  </template>
</el-table-column>
```

**添加函数**：
```typescript
const getChunkTypeLabel = (chunkType: string): string => {
  const map: Record<string, string> = {
    'text': '文本',
    'table': '表格',
    'image': '图片',
    'heading_section': '标题章节',
    'code_block': '代码块',
    'semantic_block': '语义块',
    'list': '列表',
    'paragraph': '段落'
  }
  return map[chunkType] || chunkType
}

const getChunkTypeTagType = (chunkType: string): string => {
  const map: Record<string, string> = {
    'text': 'info',
    'table': 'warning',
    'image': 'success',
    'heading_section': 'primary',
    'code_block': 'danger',
    'semantic_block': '',
    'list': 'info',
    'paragraph': ''
  }
  return map[chunkType] || 'info'
}
```

### 2.2 分块详情对话框优化

**当前实现**：
```vue
<div v-if="currentChunk && currentChunk.chunk_type === 'image'">
  <!-- 图片显示 -->
</div>
<pre v-else class="chunk-content">{{ currentChunk?.content || '' }}</pre>
```

**建议优化**：
```vue
<template #default>
  <!-- 图片分块 -->
  <div v-if="currentChunk && currentChunk.chunk_type === 'image'">
    <img
      v-if="currentChunk.image_url"
      class="chunk-image"
      :src="currentChunk.image_url"
      alt="分块图片"
    />
    <div class="chunk-meta" v-if="currentChunk.meta">
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="图片路径">{{ currentChunk.image_path || '—' }}</el-descriptions-item>
        <el-descriptions-item label="图片ID">{{ currentChunk.image_id || '—' }}</el-descriptions-item>
      </el-descriptions>
    </div>
  </div>
  
  <!-- 代码块分块 -->
  <div v-else-if="currentChunk && currentChunk.chunk_type === 'code_block'">
    <div class="chunk-meta" v-if="currentChunk.meta">
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="代码语言">
          {{ getChunkMeta(currentChunk, 'code_language') || '未知' }}
        </el-descriptions-item>
      </el-descriptions>
    </div>
    <div class="chunk-code-content" v-html="highlightCode(currentChunk?.content, getChunkMeta(currentChunk, 'code_language'))"></div>
  </div>
  
  <!-- HTML 特有分块（标题章节、语义块、列表） -->
  <div v-else-if="currentChunk && isHtmlChunk(currentChunk)">
    <div class="chunk-meta" v-if="currentChunk.meta">
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="分块类型">
          {{ getChunkTypeLabel(currentChunk.chunk_type) }}
        </el-descriptions-item>
        <el-descriptions-item v-if="getChunkMeta(currentChunk, 'heading_level')" label="标题层级">
          H{{ getChunkMeta(currentChunk, 'heading_level') }}
        </el-descriptions-item>
        <el-descriptions-item v-if="getChunkMeta(currentChunk, 'heading_path')?.length" label="标题路径">
          {{ getChunkMeta(currentChunk, 'heading_path')?.join(' > ') || '—' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="getChunkMeta(currentChunk, 'semantic_tag')" label="语义标签">
          {{ getChunkMeta(currentChunk, 'semantic_tag') }}
        </el-descriptions-item>
        <el-descriptions-item v-if="getChunkMeta(currentChunk, 'list_type')" label="列表类型">
          {{ getChunkMeta(currentChunk, 'list_type') }}
        </el-descriptions-item>
      </el-descriptions>
    </div>
    <pre class="chunk-content">{{ currentChunk?.content || '' }}</pre>
  </div>
  
  <!-- 其他分块 -->
  <pre v-else class="chunk-content">{{ currentChunk?.content || '' }}</pre>
</template>
```

**添加辅助函数**：
```typescript
const getChunkMeta = (chunk: any, key: string): any => {
  if (!chunk?.meta) return null
  try {
    const meta = typeof chunk.meta === 'string' ? JSON.parse(chunk.meta) : chunk.meta
    return meta[key]
  } catch {
    return null
  }
}

const isHtmlChunk = (chunk: any): boolean => {
  const htmlChunkTypes = ['heading_section', 'code_block', 'semantic_block', 'list', 'paragraph']
  return htmlChunkTypes.includes(chunk?.chunk_type)
}

const highlightCode = (code: string, language?: string): string => {
  if (!code) return ''
  try {
    if (language && hljs.getLanguage(language)) {
      return hljs.highlight(code, { language }).value
    }
    return hljs.highlightAuto(code).value
  } catch {
    return escapeHtml(code)
  }
}
```

### 2.3 样式优化

**添加样式**：
```scss
.chunk-code-content {
  padding: 16px;
  background: #f5f5f5;
  border-radius: 4px;
  overflow-x: auto;
  
  :deep(pre) {
    margin: 0;
    padding: 0;
    background: transparent;
  }
  
  :deep(code) {
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
    font-size: 14px;
    line-height: 1.6;
  }
}

.chunk-meta {
  margin-bottom: 16px;
}
```

## 3. 实施建议

### 3.1 优先级

1. **高优先级**：
   - 分块类型显示优化（用户体验提升）
   - 代码块高亮显示（功能完善）

2. **中优先级**：
   - 分块元数据显示（信息展示）

3. **低优先级**：
   - 样式优化（视觉优化）

### 3.2 实施步骤

1. **第一步**：优化分块类型显示
   - 添加 `getChunkTypeLabel()` 和 `getChunkTypeTagType()` 函数
   - 修改分块列表的 `chunk_type` 列显示

2. **第二步**：优化分块详情对话框
   - 添加 `getChunkMeta()` 和 `isHtmlChunk()` 函数
   - 添加代码块高亮显示
   - 添加 HTML 特有元数据显示

3. **第三步**：样式优化
   - 添加代码块样式
   - 优化元数据显示样式

## 4. 总结

### 4.1 当前状态

- ✅ HTML 预览功能已实现
- ✅ HTML 文件类型识别已实现
- ✅ 基础分块显示已实现
- ⚠️ 分块类型显示可以优化
- ⚠️ 分块元数据显示可以优化
- ⚠️ 代码块高亮可以优化

### 4.2 优化建议

前端代码**不需要修改**即可支持 HTML 文档的基本功能，但可以通过以下优化提升用户体验：

1. **分块类型显示优化**：使用更友好的中文标签
2. **分块元数据显示**：显示 HTML 特有的元数据
3. **代码块高亮**：使用 highlight.js 进行语法高亮

这些优化都是**可选的**，不影响 HTML 文档的基本功能。

---

**检查完成时间**：2025-01-XX  
**检查人**：AI Assistant  
**结论**：✅ **前端已支持 HTML 文档的基本功能，建议进行可选优化以提升用户体验**

