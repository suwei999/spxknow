# 新功能实现总结

本文档总结了本次实现的所有高优先级功能，包括 API 接口、数据库表结构和使用说明。

## 目录

1. [搜索历史自动保存](#1-搜索历史自动保存)
2. [搜索结果高亮](#2-搜索结果高亮)
3. [批量删除文档](#3-批量删除文档)
4. [批量移动文档](#4-批量移动文档)
5. [批量标签管理](#5-批量标签管理)
6. [文档目录导航](#6-文档目录导航)
7. [个人数据统计](#7-个人数据统计)
8. [导出功能](#8-导出功能)

---

## 1. 搜索历史自动保存

### 功能说明
自动记录用户的搜索历史，支持查看、删除和清空操作。同时自动统计搜索热词。

### 数据库表

#### search_history（搜索历史表）
- `id` - 主键
- `user_id` - 用户ID（外键）
- `query_text` - 搜索关键词（最大500字符）
- `search_type` - 搜索类型（vector/keyword/hybrid/exact）
- `knowledge_base_id` - 知识库ID（可选）
- `result_count` - 结果数量
- `search_time_ms` - 搜索耗时（毫秒）
- `created_at` - 创建时间
- `updated_at` - 更新时间
- `is_deleted` - 软删除标记

#### search_hotwords（搜索热词表）
- `id` - 主键
- `keyword` - 关键词（唯一，最大200字符）
- `search_count` - 搜索次数
- `last_searched_at` - 最后搜索时间
- `created_at` - 首次搜索时间
- `updated_at` - 更新时间
- `is_deleted` - 软删除标记

### API 接口

#### 1.1 获取搜索历史
```
GET /api/v1/search/history
```

**查询参数：**
- `limit` (int, 可选): 返回数量，默认20
- `offset` (int, 可选): 偏移量，默认0

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "total": 10,
    "items": [
      {
        "id": 1,
        "query_text": "Python编程",
        "search_type": "hybrid",
        "knowledge_base_id": 1,
        "result_count": 15,
        "search_time_ms": 120,
        "created_at": "2025-01-23T10:00:00"
      }
    ]
  }
}
```

#### 1.2 删除单条搜索历史
```
DELETE /api/v1/search/history/{history_id}
```

#### 1.3 清空搜索历史
```
DELETE /api/v1/search/history
```

**响应示例：**
```json
{
  "code": 0,
  "message": "清空成功",
  "data": {
    "deleted_count": 10
  }
}
```

#### 1.4 获取搜索建议（已存在，已增强）
```
GET /api/v1/search/suggestions?q={query}
```

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "suggestions": ["Python编程", "Python基础", "Python高级"]
  }
}
```

### 自动保存机制
- 在 `POST /api/v1/search` 接口中自动保存搜索历史
- 记录搜索关键词、类型、知识库、结果数量、耗时等信息
- 自动更新搜索热词统计

### 测试要点
1. ✅ 执行搜索后，检查搜索历史是否自动保存
2. ✅ 验证搜索历史列表是否正确显示
3. ✅ 测试删除单条历史记录
4. ✅ 测试清空所有历史记录
5. ✅ 验证搜索热词统计是否自动更新

---

## 2. 搜索结果高亮

### 功能说明
在搜索结果中高亮显示匹配的关键词，提升用户体验。

### 实现方式
- 使用 OpenSearch 的 highlight 功能
- 高亮标签：`<mark>关键词</mark>`
- 支持多个高亮片段（最多3个，每个150字符）

### API 接口

#### 2.1 搜索接口（已增强）
```
POST /api/v1/search
GET /api/v1/search/mixed
```

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "total": 5,
    "items": [
      {
        "document_id": 1,
        "chunk_id": 10,
        "content": "这是原始内容...",
        "highlighted_content": "这是<mark>Python</mark>编程的<mark>基础</mark>内容...",
        "score": 0.95
      }
    ]
  }
}
```

### 测试要点
1. ✅ 执行搜索，检查返回结果中是否包含 `highlighted_content` 字段
2. ✅ 验证高亮内容是否正确标记关键词
3. ✅ 测试不同搜索类型（关键词、向量、混合）的高亮效果
4. ✅ 前端显示时，使用 `highlighted_content` 替代 `content` 显示

---

## 3. 批量删除文档

### 功能说明
支持一次性删除多个文档，提高操作效率。

### API 接口

#### 3.1 批量删除文档
```
POST /api/v1/documents/batch/delete
```

**请求体：**
```json
{
  "document_ids": [1, 2, 3, 4, 5]
}
```

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "deleted_count": 4,
    "failed_count": 1,
    "failed_ids": [5],
    "total": 5
  }
}
```

### 功能特性
- 数据隔离：只能删除当前用户的文档
- 硬删除：物理删除文档及相关数据（MinIO文件、OpenSearch索引）
- 批量处理：支持一次删除多个文档
- 错误处理：部分失败不影响其他文档的删除

### 测试要点
1. ✅ 测试批量删除多个文档
2. ✅ 验证删除后文档是否从列表中消失
3. ✅ 测试删除不存在的文档ID（应返回失败）
4. ✅ 测试删除其他用户的文档（应返回失败）
5. ✅ 验证 MinIO 文件和 OpenSearch 索引是否已删除

---

## 4. 批量移动文档

### 功能说明
支持将多个文档移动到指定知识库，并可同时更新分类。

### API 接口

#### 4.1 批量移动文档
```
POST /api/v1/documents/batch/move
```

**请求体：**
```json
{
  "document_ids": [1, 2, 3],
  "target_knowledge_base_id": 2,
  "target_category_id": 5
}
```

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "moved_count": 3,
    "failed_count": 0,
    "failed_ids": [],
    "total": 3
  }
}
```

### 功能特性
- 数据隔离：只能移动当前用户的文档
- 权限验证：验证目标知识库是否存在且属于当前用户
- 智能处理：如果文档已在目标知识库，只更新分类
- 批量处理：支持一次移动多个文档

### 测试要点
1. ✅ 测试批量移动文档到不同知识库
2. ✅ 测试同时更新分类
3. ✅ 验证移动后文档的知识库ID和分类ID是否正确
4. ✅ 测试移动到不存在的知识库（应返回错误）
5. ✅ 测试移动到其他用户的知识库（应返回错误）

---

## 5. 批量标签管理

### 功能说明
支持批量添加、删除和替换文档标签。

### API 接口

#### 5.1 批量添加标签
```
POST /api/v1/documents/batch/tags/add
```

**请求体：**
```json
{
  "document_ids": [1, 2, 3],
  "tags": ["重要", "待审核"]
}
```

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "updated_count": 3
  }
}
```

#### 5.2 批量删除标签
```
POST /api/v1/documents/batch/tags/remove
```

**请求体：**
```json
{
  "document_ids": [1, 2, 3],
  "tags": ["待审核"]
}
```

#### 5.3 批量替换标签
```
POST /api/v1/documents/batch/tags/replace
```

**请求体：**
```json
{
  "document_ids": [1, 2, 3],
  "tags": ["已完成", "已审核"]
}
```

### 功能特性
- 数据隔离：只能操作当前用户的文档
- 去重处理：添加标签时自动去重
- 批量操作：支持一次操作多个文档

### 测试要点
1. ✅ 测试批量添加标签（验证标签是否合并，是否去重）
2. ✅ 测试批量删除标签
3. ✅ 测试批量替换标签（验证旧标签是否被完全替换）
4. ✅ 验证标签变更后文档列表是否正确显示

---

## 6. 文档目录导航

### 功能说明
自动提取 PDF 和 Word 文档的目录结构，支持目录导航和文档内搜索。

### 数据库表

#### document_toc（文档目录表）
- `id` - 主键
- `document_id` - 文档ID（外键）
- `level` - 目录级别（1-6）
- `title` - 标题（最大500字符）
- `page_number` - 页码
- `position` - 位置（用于排序）
- `parent_id` - 父级目录ID（外键，支持层级结构）
- `created_at` - 创建时间
- `updated_at` - 更新时间
- `is_deleted` - 软删除标记

### API 接口

#### 6.1 获取文档目录
```
GET /api/v1/documents/{doc_id}/toc
```

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "toc": [
      {
        "id": 1,
        "level": 1,
        "title": "第一章 概述",
        "page_number": 1,
        "position": 0,
        "children": [
          {
            "id": 2,
            "level": 2,
            "title": "1.1 背景",
            "page_number": 2,
            "position": 1,
            "children": []
          }
        ]
      }
    ]
  }
}
```

#### 6.2 文档内搜索
```
GET /api/v1/documents/{doc_id}/search?query={关键词}&page={页码}
```

**查询参数：**
- `query` (string, 必填): 搜索关键词
- `page` (int, 可选): 指定页码（可选）

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "results": [
      {
        "page": 5,
        "position": 0.95,
        "context": "这是包含关键词的上下文...",
        "highlight": "这是包含<mark>关键词</mark>的上下文...",
        "chunk_id": 20
      }
    ],
    "total": 5
  }
}
```

### 自动提取机制
- 文档处理完成后自动提取目录
- 支持 PDF 书签提取
- 支持 Word 标题样式提取
- 提取失败不影响文档处理主流程

### 测试要点
1. ✅ 上传 PDF 文档，验证目录是否自动提取
2. ✅ 上传 Word 文档，验证目录是否自动提取
3. ✅ 调用目录接口，验证返回的目录结构是否正确
4. ✅ 测试文档内搜索功能
5. ✅ 验证目录导航是否支持跳转到指定页码

---

## 7. 个人数据统计

### 功能说明
提供个人数据统计功能，包括知识库、文档、使用情况、存储等统计信息。

### 数据库表

#### user_statistics（用户统计表）
- `id` - 主键
- `user_id` - 用户ID（外键）
- `stat_date` - 统计日期
- `stat_type` - 统计类型（daily/weekly/monthly）
- `knowledge_base_count` - 知识库数量
- `document_count` - 文档数量
- `total_file_size` - 总文件大小（字节）
- `search_count` - 搜索次数
- `qa_count` - 问答次数
- `upload_count` - 上传次数
- `storage_used` - 已用存储（字节）
- `storage_limit` - 存储限制（字节）
- `created_at` - 创建时间
- `updated_at` - 更新时间
- `is_deleted` - 软删除标记

#### document_type_statistics（文档类型统计表）
- `id` - 主键
- `user_id` - 用户ID（外键）
- `file_type` - 文件类型
- `count` - 数量
- `total_size` - 总大小
- `stat_date` - 统计日期
- `created_at` - 创建时间
- `updated_at` - 更新时间
- `is_deleted` - 软删除标记

### API 接口

#### 7.1 获取个人统计数据
```
GET /api/v1/statistics/personal?period={all|week|month|year}
```

**查询参数：**
- `period` (string, 可选): 统计周期，默认 "all"

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "knowledge_bases": {
      "total": 5,
      "active": 4,
      "total_documents": 50
    },
    "documents": {
      "total": 50,
      "by_type": {
        "pdf": 20,
        "docx": 15,
        "txt": 15
      },
      "by_status": {
        "completed": 45,
        "processing": 3,
        "failed": 2
      },
      "total_size": 104857600
    },
    "usage": {
      "total_searches": 120,
      "total_qa_sessions": 30,
      "total_uploads": 50,
      "last_active_date": "2025-01-23"
    },
    "storage": {
      "used": 104857600,
      "limit": 10737418240,
      "percentage": 0.98
    }
  }
}
```

#### 7.2 获取数据趋势
```
GET /api/v1/statistics/trends?metric={metric}&period={period}&start_date={date}&end_date={date}
```

**查询参数：**
- `metric` (string, 必填): 指标（document_count/search_count/upload_count）
- `period` (string, 可选): 周期（week/month/year），默认 "month"
- `start_date` (string, 可选): 开始日期（ISO格式）
- `end_date` (string, 可选): 结束日期（ISO格式）

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "metric": "document_count",
    "period": "month",
    "data": [
      {
        "date": "2025-01-01",
        "value": 10
      },
      {
        "date": "2025-01-02",
        "value": 12
      }
    ],
    "trend": "increasing",
    "growth_rate": 20.0
  }
}
```

#### 7.3 获取知识库使用热力图
```
GET /api/v1/statistics/knowledge-bases/heatmap
```

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "heatmap": [
      {
        "knowledge_base_id": 1,
        "name": "技术文档",
        "usage_count": 50,
        "document_count": 20,
        "last_used": "2025-01-23T10:00:00"
      }
    ]
  }
}
```

#### 7.4 获取搜索热词
```
GET /api/v1/statistics/search/hotwords?limit={limit}&period={period}
```

**查询参数：**
- `limit` (int, 可选): 返回数量，默认20，最大100
- `period` (string, 可选): 周期（day/week/month），默认 "week"

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "hotwords": [
      {
        "keyword": "Python",
        "count": 50,
        "trend": "increasing"
      },
      {
        "keyword": "机器学习",
        "count": 30,
        "trend": "stable"
      }
    ]
  }
}
```

### 测试要点
1. ✅ 测试获取个人统计数据（验证各项指标是否正确）
2. ✅ 测试不同统计周期（all/week/month/year）
3. ✅ 测试数据趋势接口（验证趋势计算是否正确）
4. ✅ 测试知识库热力图（验证使用频率排序）
5. ✅ 测试搜索热词接口（验证热词统计）

---

## 8. 导出功能

### 功能说明
支持导出知识库、文档和问答历史，支持多种格式（Markdown、JSON、CSV）。

### 数据库表

#### export_tasks（导出任务表）
- `id` - 主键
- `user_id` - 用户ID（外键）
- `export_type` - 导出类型（knowledge_base/document/qa_history）
- `target_id` - 目标ID（知识库ID/文档ID）
- `export_format` - 导出格式（markdown/pdf/json/csv）
- `status` - 状态（pending/processing/completed/failed）
- `file_path` - 导出文件路径（MinIO）
- `file_size` - 文件大小
- `error_message` - 错误信息
- `created_at` - 创建时间
- `updated_at` - 更新时间
- `completed_at` - 完成时间
- `is_deleted` - 软删除标记

### API 接口

#### 8.1 导出知识库
```
POST /api/v1/exports/knowledge-bases/{kb_id}/export
```

**请求体：**
```json
{
  "format": "markdown",
  "include_documents": true,
  "include_chunks": false
}
```

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task_id": 1,
    "status": "processing",
    "estimated_time": 30
  }
}
```

#### 8.2 导出文档
```
POST /api/v1/exports/documents/{doc_id}/export
```

**请求体：**
```json
{
  "format": "markdown",
  "include_chunks": true,
  "include_images": false
}
```

#### 8.3 批量导出文档
```
POST /api/v1/exports/documents/batch/export
```

**请求体：**
```json
{
  "document_ids": [1, 2, 3],
  "format": "markdown"
}
```

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "tasks": [
      {
        "document_id": 1,
        "task_id": 1,
        "status": "processing"
      }
    ],
    "total": 3
  }
}
```

#### 8.4 导出问答历史
```
POST /api/v1/exports/qa/history/export
```

**请求体：**
```json
{
  "format": "json",
  "session_id": 1,
  "start_date": "2025-01-01",
  "end_date": "2025-01-31"
}
```

#### 8.5 查询导出任务状态
```
GET /api/v1/exports/{task_id}
```

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task_id": 1,
    "status": "completed",
    "file_path": "exports/1/kb_1_20250123_120000.markdown",
    "file_size": 1048576,
    "download_url": "https://minio.example.com/...",
    "error_message": null,
    "created_at": "2025-01-23T10:00:00",
    "completed_at": "2025-01-23T10:00:30"
  }
}
```

#### 8.6 下载导出文件
```
GET /api/v1/exports/{task_id}/download
```

**响应：**
- Content-Type: 根据导出格式设置（application/json, text/markdown, text/csv）
- Content-Disposition: attachment; filename="export_{task_id}.{format}"

### 导出格式说明

#### Markdown 格式
- 知识库导出：包含知识库信息和文档列表
- 文档导出：包含文档信息和分块内容
- 支持标题层级和代码块

#### JSON 格式
- 结构化数据，包含完整的元数据
- 知识库导出：包含知识库对象和文档数组
- 文档导出：包含文档对象和分块数组

#### CSV 格式（仅问答历史）
- 表头：会话ID、问题、答案、创建时间
- 每行一条问答记录

### 功能特性
- 异步处理：导出任务异步执行，不阻塞请求
- 文件存储：导出文件存储在 MinIO
- 下载链接：提供24小时有效的预签名下载链接
- 错误处理：导出失败时记录错误信息

### 测试要点
1. ✅ 测试导出知识库（Markdown/JSON格式）
2. ✅ 测试导出单个文档
3. ✅ 测试批量导出文档
4. ✅ 测试导出问答历史（JSON/CSV格式）
5. ✅ 验证导出任务状态查询
6. ✅ 测试下载导出文件
7. ✅ 验证导出文件内容是否正确
8. ✅ 测试导出失败场景（权限不足、文件不存在等）

---

## 测试检查清单

### 通用测试项
- [ ] 所有接口都需要认证（Bearer Token）
- [ ] 数据隔离：用户只能访问自己的数据
- [ ] 错误处理：接口返回适当的错误码和错误信息
- [ ] 日志记录：关键操作都有日志记录

### 功能测试项
- [ ] 搜索历史自动保存功能
- [ ] 搜索结果高亮显示
- [ ] 批量删除文档功能
- [ ] 批量移动文档功能
- [ ] 批量标签管理功能
- [ ] 文档目录提取和导航
- [ ] 文档内搜索功能
- [ ] 个人数据统计功能
- [ ] 数据趋势分析
- [ ] 知识库使用热力图
- [ ] 搜索热词统计
- [ ] 知识库导出功能
- [ ] 文档导出功能
- [ ] 批量文档导出功能
- [ ] 问答历史导出功能

### 性能测试项
- [ ] 批量操作性能（100+文档）
- [ ] 导出大文件性能
- [ ] 统计查询性能

### 边界测试项
- [ ] 空数据场景
- [ ] 大量数据场景
- [ ] 并发操作场景
- [ ] 异常数据场景

---

## 注意事项

1. **数据库迁移**：所有迁移脚本已执行，表结构已创建
2. **依赖库**：确保安装了 `PyPDF2` 和 `python-docx`（用于目录提取）
3. **MinIO 配置**：导出功能需要 MinIO 存储服务
4. **异步任务**：导出功能当前为同步处理，大文件可能需要较长时间
5. **数据隔离**：所有接口都验证用户权限，确保数据安全

---

## 后续优化建议

1. **导出功能异步化**：使用 Celery 异步处理大文件导出
2. **PDF 目录提取优化**：改进页码获取逻辑，支持更复杂的 PDF 结构
3. **统计功能增强**：添加更多统计维度和可视化图表
4. **搜索历史优化**：添加搜索历史去重和智能推荐
5. **批量操作优化**：添加进度反馈和取消功能

---

## 联系与支持

如有问题或建议，请查看代码注释或联系开发团队。

