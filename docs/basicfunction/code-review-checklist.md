# 前后端代码适配检查清单

## 检查结果总结

### ✅ 已适配的功能

#### 1. 搜索历史自动保存
- **后端**: ✅ 已实现自动保存（在搜索接口中）
- **前端**: ✅ 已实现历史显示和操作
- **API路径**: ✅ 一致
  - 获取历史: `GET /api/v1/search/history` ✅
  - 删除单条: `DELETE /api/v1/search/history/{history_id}` ✅
  - 清空历史: `DELETE /api/v1/search/history` ⚠️ **需要检查后端实现**

#### 2. 搜索结果高亮
- **后端**: ✅ 已返回 `highlighted_content` 字段
- **前端**: ✅ 已使用 `v-html` 显示高亮内容
- **数据格式**: ✅ 匹配（使用 `<mark>` 标签）

#### 3. 批量删除文档
- **后端**: ✅ `POST /api/v1/documents/batch/delete`
- **前端**: ✅ `batchDeleteDocuments(documentIds)`
- **请求格式**: ✅ 匹配
  - 后端期望: `{ document_ids: List[int] }`
  - 前端发送: `{ document_ids: number[] }` ✅
- **响应格式**: ✅ 匹配
  - 后端返回: `{ code: 0, data: { deleted_count, failed_count, failed_ids, total } }`
  - 前端处理: 正确解析 `res.code` 和 `res.data` ✅

#### 4. 批量移动文档
- **后端**: ✅ `POST /api/v1/documents/batch/move`
- **前端**: ✅ `batchMoveDocuments(data)`
- **请求格式**: ✅ 匹配
  - 后端期望: `{ document_ids, target_knowledge_base_id, target_category_id? }`
  - 前端发送: 完全匹配 ✅
- **响应格式**: ✅ 匹配

#### 5. 批量标签管理
- **后端**: ✅ 三个接口都已实现
  - `POST /api/v1/documents/batch/tags/add`
  - `POST /api/v1/documents/batch/tags/remove`
  - `POST /api/v1/documents/batch/tags/replace`
- **前端**: ✅ 三个API都已实现
- **请求格式**: ⚠️ **需要检查标签格式**
  - 后端期望: `{ document_ids: List[int], tags: List[str] }`
  - 前端发送: `tags` 可能是字符串或数组，需要统一

#### 6. 文档目录导航
- **后端**: ✅ `GET /api/v1/documents/{doc_id}/toc`
- **前端**: ✅ `getDocumentTOC(documentId)` API已添加
- **前端UI**: ❌ **未实现**（需要在 detail.vue 中添加）

#### 7. 文档内搜索
- **后端**: ✅ `GET /api/v1/documents/{doc_id}/search?query=xxx&page=xxx`
- **前端**: ✅ `searchInDocument(documentId, params)` API已添加
- **前端UI**: ❌ **未实现**（需要在 detail.vue 中添加）

---

## ⚠️ 发现的问题

### 问题1: 清空搜索历史接口
- **后端**: 需要检查是否有 `DELETE /api/v1/search/history` 实现
- **前端**: ✅ 已调用 `clearSearchHistory()`
- **状态**: 需要验证后端实现

### 问题2: 批量标签管理 - 标签格式
- **前端代码问题**: 
  ```typescript
  const tagsForm = ref({
    operation: 'add' as 'add' | 'remove' | 'replace',
    tags: [] as string[]  // 初始化为数组
  })
  ```
  但在输入框中，用户输入的是字符串（逗号分隔），需要转换：
  ```typescript
  const handleTagsInput = () => {
    if (typeof tagsForm.value.tags === 'string') {
      tagsForm.value.tags = tagsForm.value.tags.split(',').map(t => t.trim()).filter(Boolean)
    }
  }
  ```
- **问题**: `handleTagsInput` 只在 `@blur` 时调用，但提交时可能还是字符串
- **建议**: 在 `handleBatchTags` 中确保 `tags` 是数组

### 问题3: 文档目录和文档内搜索
- **API已实现**: ✅
- **前端UI未实现**: ❌
- **需要**: 在 `detail.vue` 中添加目录侧边栏和搜索功能

---

## 📋 详细检查清单

### 后端API检查

#### 搜索相关
- [x] `GET /api/v1/search/history` - 获取搜索历史
- [x] `DELETE /api/v1/search/history/{history_id}` - 删除单条历史
- [ ] `DELETE /api/v1/search/history` - 清空历史（需要检查）
- [x] 搜索接口自动保存历史
- [x] 搜索接口返回 `highlighted_content`

#### 文档批量操作
- [x] `POST /api/v1/documents/batch/delete` - 批量删除
- [x] `POST /api/v1/documents/batch/move` - 批量移动
- [x] `POST /api/v1/documents/batch/tags/add` - 批量添加标签
- [x] `POST /api/v1/documents/batch/tags/remove` - 批量删除标签
- [x] `POST /api/v1/documents/batch/tags/replace` - 批量替换标签

#### 文档目录和搜索
- [x] `GET /api/v1/documents/{doc_id}/toc` - 获取目录
- [x] `GET /api/v1/documents/{doc_id}/search` - 文档内搜索

### 前端API检查

#### 搜索相关
- [x] `getSearchHistory()` - 获取历史
- [x] `deleteSearchHistory(historyId)` - 删除单条
- [x] `clearSearchHistory()` - 清空历史
- [x] 搜索结果显示高亮内容

#### 文档批量操作
- [x] `batchDeleteDocuments(documentIds)` - 批量删除
- [x] `batchMoveDocuments(data)` - 批量移动
- [x] `batchAddTags(data)` - 批量添加标签
- [x] `batchRemoveTags(data)` - 批量删除标签
- [x] `batchReplaceTags(data)` - 批量替换标签

#### 文档目录和搜索
- [x] `getDocumentTOC(documentId)` - 获取目录
- [x] `searchInDocument(documentId, params)` - 文档内搜索

### 前端UI检查

#### 搜索页面
- [x] 搜索历史下拉显示
- [x] 搜索结果高亮显示
- [x] 历史记录点击搜索
- [x] 删除单条历史
- [x] 清空所有历史

#### 文档列表页面
- [x] 表格多选功能
- [x] 批量操作工具栏
- [x] 批量删除对话框
- [x] 批量移动对话框
- [x] 批量标签管理对话框

#### 文档详情页面
- [ ] 目录侧边栏（未实现）
- [ ] 文档内搜索（未实现）

---

## 🔧 需要修复的问题

### 1. 批量标签管理 - 标签格式转换

**文件**: `spx-knowledge-frontend/src/views/Documents/index.vue`

**问题**: 提交时 `tags` 可能是字符串

**修复**:
```typescript
const handleBatchTags = async () => {
  // 确保 tags 是数组
  let tagsArray: string[] = []
  if (Array.isArray(tagsForm.value.tags)) {
    tagsArray = tagsForm.value.tags
  } else if (typeof tagsForm.value.tags === 'string') {
    tagsArray = tagsForm.value.tags.split(',').map(t => t.trim()).filter(Boolean)
  }
  
  if (tagsArray.length === 0) {
    ElMessage.warning('请输入标签')
    return
  }
  
  // ... 其余代码使用 tagsArray
}
```

### 2. 清空搜索历史接口

**需要检查**: `spx-knowledge-backend/app/api/v1/routes/search.py`

**如果不存在，需要添加**:
```python
@router.delete("/history")
async def clear_search_history(
    request: Request,
    db: Session = Depends(get_db)
):
    """清空当前用户的所有搜索历史"""
    user_id = get_current_user_id(request)
    deleted_count = db.query(SearchHistory).filter(
        SearchHistory.user_id == user_id,
        SearchHistory.is_deleted == False
    ).update({"is_deleted": True})
    db.commit()
    return {
        "code": 0,
        "message": "清空成功",
        "data": {"deleted_count": deleted_count}
    }
```

---

## ✅ 适配良好的部分

1. **API路径**: 前后端路径完全一致
2. **请求格式**: 请求体结构匹配
3. **响应格式**: 统一使用 `{ code, message, data }` 格式
4. **错误处理**: 前端正确处理后端错误响应
5. **数据隔离**: 后端正确验证用户权限

---

## 📝 待实现功能

1. **文档目录导航UI** - 在 `detail.vue` 中添加
2. **文档内搜索UI** - 在 `detail.vue` 中添加
3. **统计页面** - 新建页面
4. **导出功能UI** - 在列表页添加导出按钮

---

## 🎯 建议

1. **立即修复**: 批量标签管理的标签格式转换问题
2. **验证**: 检查清空搜索历史接口是否存在
3. **后续实现**: 文档目录和文档内搜索的UI
4. **测试**: 完整测试所有批量操作功能

