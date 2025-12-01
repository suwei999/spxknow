# HTML 文档上传解析与分块方案

> 目标：为 `.html` / `.htm` 文件提供稳定的上传、解析、分块与索引闭环，实现与 PDF / Word / TXT / Markdown / Excel / PPTX 一致的文档入库体验，充分利用 HTML 的语义结构（标题层级、段落、表格、列表、链接、图片等）提升分块质量和检索准确性。

## 1. 适用场景与输入约束

| 项目 | 建议 |
| --- | --- |
| 支持的后缀 | `.html`、`.htm`（可配置白名单） |
| 文件大小 | 默认 10 MB，可在配置中调整（HTML 可能包含大量内联资源） |
| 编码 | 自动检测（优先从 `<meta charset>` 或 HTTP 响应头获取，fallback 到 UTF-8） |
| HTML 标准 | 支持 HTML5、XHTML 1.0/1.1，自动处理不规范的 HTML（BeautifulSoup 容错） |
| 内联资源 | 支持提取 `<img>` 标签的图片（base64 或 URL），外部链接记录到 metadata |
| 脚本与样式 | 自动去除 `<script>`、`<style>`、`<noscript>` 等非内容标签 |
| 表单元素 | 提取表单标签和属性，但不处理交互逻辑 |
| 特殊标签 | 支持 `<article>`、`<section>`、`<header>`、`<footer>`、`<nav>` 等语义标签 |

## 2. 解析流程

### 2.1 整体流程

1. **上传**：沿用现有 `POST /api/documents/upload` 接口，记录文件类型 `html`。
2. **文件验证**：检查是否为有效的 HTML 格式（包含 `<html>` 标签或可解析的 HTML 片段）。
3. **编码检测**：
   - 优先从 `<meta charset="...">` 标签获取编码
   - 其次从 HTTP Content-Type 响应头（如果从 URL 下载）
   - 最后使用 `charset-normalizer` 自动检测
   - 统一转换为 UTF-8 处理
4. **HTML 解析**：
   - 使用 `BeautifulSoup4` 或 `lxml` 解析 HTML
   - 自动修复不规范的 HTML（BeautifulSoup 容错模式）
   - 提取 DOM 树结构
5. **内容提取**：
   - 按 DOM 顺序提取内容
   - 提取标题层级（`<h1>` ~ `<h6>`）
   - 提取段落文本（`<p>`、`<div>`、`<span>` 等）
   - 提取表格（`<table>` 转换为结构化数据）
   - 提取列表（`<ul>`、`<ol>`、`<dl>`）
   - 提取链接（`<a>` 标签的文本和 URL）
   - 提取图片（`<img>` 标签的图片数据）
   - 提取代码块（`<pre>`、`<code>`）
   - 提取引用块（`<blockquote>`）
6. **结构化组织**：
   - 按 DOM 顺序组织内容
   - 保留标题层级关系
   - 建立元素之间的关联（如列表项、表格行等）

### 2.2 详细解析步骤

#### 步骤 1：加载 HTML 文件
```python
from bs4 import BeautifulSoup
import charset_normalizer

# 检测编码
with open(file_path, 'rb') as f:
    raw_bytes = f.read()
encoding = detect_encoding(raw_bytes)  # 从 meta 标签或自动检测
html_text = raw_bytes.decode(encoding)
```

#### 步骤 2：解析 HTML DOM
```python
# 使用 BeautifulSoup 解析（容错模式）
soup = BeautifulSoup(html_text, 'html.parser')  # 或 'lxml'（更快但需要额外依赖）

# 移除无用标签
for tag in soup(['script', 'style', 'noscript', 'meta', 'link', 'head']):
    tag.decompose()  # 完全移除标签及其内容
```

#### 步骤 3：提取文本内容
- **标题文本**：从 `<h1>` ~ `<h6>` 标签中提取，记录层级（1-6）
- **段落文本**：从 `<p>`、`<div>`、`<span>`、`<article>`、`<section>` 等标签中提取
- **列表文本**：从 `<ul>`、`<ol>`、`<dl>` 及其子项中提取，保留列表结构
- **代码文本**：从 `<pre>`、`<code>` 标签中提取，保留代码格式
- **引用文本**：从 `<blockquote>` 标签中提取

#### 步骤 4：提取表格
- 识别 `<table>` 标签
- 提取表头（`<thead>` 或第一行 `<tr>`）
- 提取数据行（`<tbody>` 中的 `<tr>`）
- 构建标准 `table_data` 结构：
  ```python
  {
      "cells": [[...], [...]],  # 单元格数据（第一行通常是表头）
      "rows": int,              # 行数
      "columns": int,           # 列数
      "structure": "html_extracted",  # 结构标识
      "html": "<table>...</table>"   # 原始 HTML（可选，用于保留格式）
  }
  ```
- 生成 `table_text`：制表符分隔的文本格式（用于检索）
- 记录表格在文档中的位置（`element_index`）

#### 步骤 5：提取图片
- 识别 `<img>` 标签
- 提取图片源：
  - **Base64 图片**：从 `src` 属性中提取 `data:image/...;base64,...` 格式的图片
  - **URL 图片**：记录图片 URL（后续可下载，但不在解析阶段处理）
- 提取图片属性：`alt`、`title`、`width`、`height`
- 对于 Base64 图片，解码为二进制数据
- 对于 URL 图片，记录 URL 到 metadata，暂不下载（可选：在图片处理阶段下载）

#### 步骤 6：提取链接
- 识别 `<a>` 标签
- 提取链接文本和 URL（`href` 属性）
- 记录到 metadata 中（用于后续分析，不单独成块）

#### 步骤 7：处理特殊结构
- **表单元素**：提取 `<form>`、`<input>`、`<textarea>` 等标签的文本和属性
- **语义标签**：识别 `<article>`、`<section>`、`<header>`、`<footer>`、`<nav>` 等，作为分块边界提示
- **内联样式**：提取 `style` 属性（可选，用于元数据）

## 3. 分块策略

HTML 文档的分块策略应充分利用 HTML 的语义结构，同时考虑内容连续性和检索需求。

### 3.1 分块原则

| 分块类型 | 场景 | 构造方式 |
| --- | --- | --- |
| **标题级分块** | 有明确标题层级（`<h1>` ~ `<h6>`） | 以标题为边界，将标题及其后续内容（直到下一个同级或更高级标题）作为一个分块，数据库 `chunks.chunk_type` 为 `text`，metadata 中记录 `chunk_type: "heading_section"`，包含：标题 + 段落文本（不包括表格和代码块） |
| **语义块分块** | 使用 `<article>`、`<section>` 等语义标签 | 每个语义块作为一个独立分块，metadata 中记录 `chunk_type: "semantic_block"` 和 `semantic_tag`（如 "article"、"section"） |
| **多段落合并** | 连续的主题相关段落 | 如果相邻段落没有明确标题分隔，且总内容 < `chunk_max`，则合并为一块 |
| **表格分块** | 所有表格 | 表格单独成块，数据库 `chunks.chunk_type` 为 `table`，metadata 记录 `element_index`、`table_id`、`table_group_uid`、`n_rows`、`n_cols`。表格数据存储在 `document_tables` 表中，通过 `table_id` 懒加载 |
| **代码块分块** | 代码块（`<pre>`、`<code>`） | 代码块单独成块，数据库 `chunks.chunk_type` 为 `text`，metadata 中记录 `chunk_type: "code_block"` 和 `code_language`（如果可识别） |
| **列表分块** | 长列表（> 500 字） | 列表单独成块，metadata 中记录 `chunk_type: "list"` 和 `list_type`（"ul"、"ol"、"dl"） |
| **滑动窗口** | 超大内容块（> `chunk_max` 字符） | 使用滑动窗口（默认 1000 字，overlap 200 字）切分 |

### 3.2 分块优先级（由高到低）

1. **表格边界**：每个表格单独成块（保留完整性）
2. **代码块边界**：每个代码块单独成块（保留代码格式）
3. **标题边界**：有明确标题的章节作为分块候选
4. **语义标签边界**：`<article>`、`<section>` 等语义标签作为分块边界
5. **列表边界**：长列表单独成块
6. **段落边界**：多个段落合并
7. **滑动窗口**：超大内容使用窗口切分

### 3.3 分块元数据

每个分块应包含以下元数据（与现有 DOCX/PDF 分块格式保持一致）：

```json
{
  "element_index_start": 1,      // 分块起始元素索引（文本块必需）
  "element_index_end": 5,         // 分块结束元素索引（文本块必需）
  "doc_order_start": 0,          // 分块起始文档顺序（文本块必需）
  "doc_order_end": 4,            // 分块结束文档顺序（文本块必需）
  "chunk_index": 0,              // 分块索引（必需）
  "page_number": null,           // HTML 无页码概念，始终为 null
  "coordinates": null,           // HTML 无坐标概念，始终为 null
  "line_start": null,            // 行号起始（HTML 通常为 null，除非保留源码行号）
  "line_end": null,              // 行号结束（HTML 通常为 null）
  "section_hint": null,          // 段落提示（可选）
  
  // HTML 特有字段（可选，存储在 meta 中）
  "heading_level": 2,            // 所属标题层级（1-6，仅标题级分块）
  "heading_path": ["文档标题", "第一章", "1.1 小节"],  // 标题路径（用于目录）
  "chunk_type": "heading_section",  // HTML 特有分块类型：heading_section（标题章节）、semantic_block（语义块）、code_block（代码块）、list（列表）、paragraph（段落）
  "semantic_tag": "article",     // 语义标签名称（仅语义块）
  "code_language": "python",      // 代码语言（仅代码块）
  "list_type": "ul",             // 列表类型（仅列表块）
  "has_table": false,            // 是否包含表格
  "has_images": true,             // 是否包含图片引用
  "has_links": true,             // 是否包含链接
  "link_refs": [                 // 链接引用列表（可选）
    {"text": "链接文本", "url": "https://example.com"}
  ],
  "image_refs": [],              // 图片引用列表（图片 ID 或 URL，后续回填）
  "image_id": null,              // 图片 ID（后续回填，仅图片块）
  "image_path": null,            // 图片路径（后续回填，仅图片块）
  
  // 表格块特有字段（仅表格块，存储在 meta 中）
  "element_index": 5,            // 表格元素索引（表格块必需，替代 element_index_start/end）
  "table_id": "abc123...",       // 表格 UID（必需，用于从 document_tables 表懒加载表格数据）
  "table_group_uid": "abc123...", // 表格组 UID（必需，用于分片表格，不分片时与 table_id 相同）
  "n_rows": 10,                  // 表格行数
  "n_cols": 5,                   // 表格列数
  "table_data": {...}            // 可选：完整的表格数据（旧数据可能包含，新设计使用懒加载）
}
```

**注意**：
- `chunk_type` 字段在数据库的 `chunks.chunk_type` 列中存储，值为 `text`、`table` 或 `image`
- HTML 特有的元数据（如 `heading_level`、`heading_path`、`chunk_type` 等）存储在 `chunks.meta` JSON 字段中
- **文本块**：必须包含 `element_index_start/end` 和 `doc_order_start/end`，用于关联原始元素
- **表格块**：使用 `element_index`（单个值）替代 `element_index_start/end`，必须包含 `table_id` 和 `table_group_uid`
- **图片块**：使用 `element_index`（单个值），`image_id` 和 `image_path` 在图片处理完成后回填
- **表格存储**：表格数据存储在 `document_tables` 表中，分块 metadata 中只存储 `table_id` 用于懒加载

### 3.4 分块示例

**场景 1：标题级分块**
```html
<h1>项目介绍</h1>
<p>这是一个关于...</p>
<p>系统采用微服务架构...</p>
→ 生成 1 个分块（标题 + 段落）
```

**场景 2：包含表格的章节**
```html
<h2>性能对比</h2>
<p>以下是性能数据对比：</p>
<table>
  <tr><th>项目</th><th>值</th></tr>
  <tr><td>性能</td><td>100%</td></tr>
</table>
→ 生成 2 个分块：
   - 文本块：标题 + 段落介绍
   - 表格块：完整表格
```

**场景 3：代码块**
```html
<h2>示例代码</h2>
<pre><code class="python">
def hello():
    print("Hello")
</code></pre>
→ 生成 2 个分块：
   - 文本块：标题
   - 代码块：代码内容（保留格式）
```

**场景 4：语义块**
```html
<article>
  <h1>文章标题</h1>
  <p>文章内容...</p>
</article>
→ 生成 1 个分块（整个 article 作为一个分块）
```

## 4. 元信息与存储

### 4.1 文档级元数据

| 字段 | 说明 | 示例 |
| --- | --- | --- |
| `heading_count` | 标题总数（按层级统计） | `{"h1": 5, "h2": 20, "h3": 50}` |
| `heading_structure` | 标题结构列表（用于目录提取） | `[{"level": 1, "title": "文档标题", "position": 0}, ...]` |
| `table_count` | 表格总数 | `3` |
| `image_count` | 图片总数（Base64 + URL） | `15` |
| `link_count` | 链接总数 | `25` |
| `code_block_count` | 代码块总数 | `5` |
| `list_count` | 列表总数 | `10` |
| `semantic_tags` | 使用的语义标签列表 | `["article", "section", "header", "footer"]` |
| `has_forms` | 是否包含表单 | `true` |
| `html_version` | HTML 版本（如果可识别） | `"HTML5"` |
| `encoding` | 检测到的编码 | `"utf-8"` |
| `base_url` | 基础 URL（如果从 URL 下载） | `"https://example.com"` |

### 4.2 分块级元数据

| 字段 | 说明 |
| --- | --- |
| `chunk_type` | 分块类型：存储在数据库 `chunks.chunk_type` 列，值为 `text`、`table` 或 `image`；HTML 特有的类型（如 `heading_section`、`code_block` 等）存储在 `meta` JSON 中 |
| `heading_level` | 所属标题层级（1-6，仅标题级分块） |
| `heading_path` | 标题路径（用于目录和导航） |
| `semantic_tag` | 语义标签名称（仅语义块） |
| `code_language` | 代码语言（仅代码块） |
| `list_type` | 列表类型（仅列表块） |
| `table_index` | 如果是表格块，记录表格在文档中的索引（已废弃，使用 `table_id`） |
| `table_id` | 表格 UID（必需，用于从 `document_tables` 表懒加载表格数据） |
| `table_group_uid` | 表格组 UID（必需，用于分片表格，不分片时与 `table_id` 相同） |
| `n_rows` | 表格行数（表格块必需） |
| `n_cols` | 表格列数（表格块必需） |
| `table_data` | 完整的表格数据（可选，新设计使用懒加载，旧数据可能包含） |
| `has_links` | 是否包含链接 |
| `link_refs` | 链接引用列表（`[{"text": str, "url": str}]`） |
| `has_images` | 是否包含图片引用 |
| `image_refs` | 图片引用列表（图片 ID 或 URL，可选） |
| `image_id` | 图片 ID（后续回填，由 ImageService 处理） |
| `image_path` | 图片路径（后续回填，由 ImageService 处理） |

### 4.3 存储结构

**文档级元数据**：写入 `documents.meta`（JSON 格式）

```json
{
  "text_length": 5000,
  "element_count": 50,
  "heading_count": {"h1": 5, "h2": 20, "h3": 50},
  "heading_structure": [
    {"level": 1, "title": "文档标题", "position": 0},
    {"level": 2, "title": "第一章", "position": 1}
  ],
  "table_count": 3,
  "image_count": 15,
  "link_count": 25,
  "code_block_count": 5,
  "list_count": 10,
  "semantic_tags": ["article", "section"],
  "has_forms": false,
  "html_version": "HTML5",
  "encoding": "utf-8"
}
```

**分块级元数据**：写入 `chunks.meta`（JSON 格式）

```json
{
  "element_index_start": 1,
  "element_index_end": 5,
  "doc_order_start": 0,
  "doc_order_end": 4,
  "chunk_index": 0,
  "page_number": null,
  "coordinates": null,
  "line_start": null,
  "line_end": null,
  "section_hint": null,
  
  // HTML 特有字段
  "heading_level": 2,
  "heading_path": ["文档标题", "第一章"],
  "chunk_type": "heading_section",
  "has_links": true,
  "link_refs": [
    {"text": "参考链接", "url": "https://example.com"}
  ],
  "has_images": true,
  "image_refs": []
}

// 表格块示例（chunks.meta）
{
  "element_index": 5,
  "chunk_index": 2,
  "page_number": null,
  "table_id": "abc123def456...",
  "table_group_uid": "abc123def456...",
  "n_rows": 10,
  "n_cols": 5
}

// 代码块示例（chunks.meta）
{
  "element_index_start": 10,
  "element_index_end": 10,
  "doc_order_start": 9,
  "doc_order_end": 9,
  "chunk_index": 3,
  "chunk_type": "code_block",
  "code_language": "python"
}
```

**注意**：
- `chunks.chunk_type` 列存储的是 `text`、`table` 或 `image`（与现有格式一致）
- HTML 特有的 `chunk_type` 值（如 `heading_section`、`code_block` 等）存储在 `chunks.meta` JSON 中
- `image_id` 和 `image_path` 在图片处理完成后回填到分块元数据中

## 5. 错误处理与用户提示

| 场景 | 行为 |
| --- | --- |
| 不支持的文件格式 | 在验证阶段抛出 `DocumentParseError`，提示"请使用 .html 或 .htm 格式" |
| 受损的 HTML 文件 | BeautifulSoup 自动修复，记录警告日志，提示用户部分内容可能丢失 |
| 编码检测失败 | 默认使用 UTF-8，记录警告日志 |
| 图片提取失败 | 记录警告日志，继续处理其他内容，在 metadata 中标记缺失的图片 |
| 表格解析失败 | 回退到文本提取模式，尝试提取表格中的文本内容 |
| 超大 HTML 文件 | 对于超大文件（> 10MB），采用流式处理，逐块解析，避免一次性加载 |
| 外部资源依赖 | 对于 URL 图片和外部链接，记录到 metadata，但不阻塞解析流程 |

## 6. API / 任务设计

### 6.1 上传入口

沿用现有 `POST /api/documents/upload` 接口：
- 文件类型自动识别为 `html`（通过文件扩展名或 MIME 类型）
- 文件验证：通过 `FileValidationService` 验证文件格式
- 可选参数（通过 `Document.meta` 传递）：
  - `base_url`：基础 URL（用于解析相对链接和图片 URL）
  - `extract_external_images`：是否下载外部图片，默认 `false`（仅提取 Base64 图片）
  - `preserve_html_structure`：是否保留原始 HTML 结构，默认 `true`
  - `remove_scripts`：是否移除脚本标签，默认 `true`

**上传流程**：
1. 文件上传到 MinIO 对象存储
2. 文件信息保存到 `documents` 表
3. 触发异步任务 `process_document_task` 处理文档

### 6.2 解析任务集成

在 `document_tasks.process_document_task` 中新增 HTML 处理分支：

**步骤 1**：在文件类型判断部分添加 `is_html` 判断：
```python
file_suffix = (document.original_filename or '').split('.')[-1].lower()
file_type = (document.file_type or '').lower()
is_docx = file_suffix == 'docx' or file_type == 'docx'
is_pdf = file_suffix == 'pdf' or file_type == 'pdf'
is_txt = file_suffix in ('txt', 'log') or file_type == 'txt'
is_md = file_suffix in ('md', 'markdown', 'mkd') or file_type in ('md', 'markdown')
is_excel = file_suffix in ('xlsx', 'xls', 'xlsb', 'csv') or file_type in ('excel', 'xlsx', 'xls', 'csv')
is_pptx = file_suffix == 'pptx' or file_type == 'pptx'
is_html = file_suffix in ('html', 'htm') or file_type in ('html', 'htm')  # 新增
if not (is_docx or is_pdf or is_txt or is_md or is_excel or is_pptx or is_html):  # 更新条件
    raise Exception("当前处理流程仅支持 DOCX / PDF / TXT / MD / Excel / PPTX / HTML 文档")
```

**步骤 2**：在文件顶部导入 HtmlService：
```python
from app.services.html_service import HtmlService  # 新增导入
```

**步骤 3**：在解析分支中添加 HTML 处理：
```python
elif is_pptx:
    logger.info(f"[任务ID: {task_id}] 步骤4/7: 使用 PptxService 解析 PowerPoint 文档")
    parser = PptxService(db)
    parse_result = parser.parse_document(parsed_file_path)
elif is_html:
    logger.info(f"[任务ID: {task_id}] 步骤4/7: 使用 HtmlService 解析 HTML 文档")
    parser = HtmlService(db)
    # HTML 解析不需要额外选项（与 DOCX/PDF 一致）
    parse_result = parser.parse_document(parsed_file_path)
elif is_md:
    logger.info(f"[任务ID: {task_id}] 步骤4/7: 使用 MarkdownService 解析 Markdown 文档")
    parser = MarkdownService(db)
    parse_result = parser.parse_document(parsed_file_path)
else:
    logger.info(f"[任务ID: {task_id}] 步骤4/7: 使用 TxtService 解析纯文本文档")
    parser = TxtService(db)
    parse_result = parser.parse_document(parsed_file_path)
```

**步骤 4**：在预览生成判断中，HTML 可以生成 HTML 预览（直接使用原始文件）：
```python
# 在 document_tasks.py 中（已实现，无需修改）
# HTML 文件可以直接在浏览器中预览，无需转换
# 如果需要，可以生成 PDF 预览（使用 headless browser 或 wkhtmltopdf）
```

**完整处理流程**：
1. ✅ 文件类型判断（添加 `is_html`）
2. ✅ 文件下载到临时目录
3. ✅ 文档解析（调用 `HtmlService.parse_document`）
4. ✅ 元数据更新（HTML 信息写入 `document.meta`）
5. ✅ 预览生成（HTML 文件可以直接预览，或生成 PDF 预览）
6. ✅ 分块处理（复用现有分块逻辑）
7. ✅ 表格处理（写入 `document_tables` 表）
8. ✅ 图片处理（保存 Base64 图片、OCR、向量化、索引）
9. ✅ 向量化（生成文本向量）
10. ✅ 索引（写入 OpenSearch）
11. ✅ 目录提取（从标题结构构建）

### 6.3 预览生成

**重要说明**：HTML 文件的在线预览功能**不需要 LibreOffice**，也**不需要任何转换**。

#### 6.3.1 HTML 预览方式

HTML 文件可以直接在浏览器中预览，有两种方式：

1. **直接 iframe 预览**（推荐，默认方式）：
   - 前端直接使用 `document.file_path` 生成的 MinIO 签名 URL
   - 在 iframe 中直接显示 HTML 内容
   - **无需任何转换或额外依赖**
   - 前端代码已支持（`isText` 判断中包含 `html` 类型）

2. **PDF 预览**（可选，不推荐）：
   - 如果需要 PDF 预览，可以使用 headless browser（如 Playwright、Selenium）或 `wkhtmltopdf` 转换为 PDF
   - 但通常不需要，因为 HTML 可以直接预览

#### 6.3.2 前端预览实现

前端已有相关支持，HTML 文件会被识别为文本类型，可以直接在 iframe 中显示：

```typescript
// 前端代码（detail.vue）
const isText = computed(() => {
  // HTML 文件包含在文本类型中
  return /\.(txt|json|xml|csv|log|conf|ini|yaml|yml|sh|bat|py|js|ts|html|css)(\?|$)/i.test(...)
})

// HTML 预览显示
<iframe
  v-else-if="isText"
  class="preview-frame"
  :src="previewUrl"
  frameborder="0"
  referrerpolicy="no-referrer"
/>
```

#### 6.3.3 预览生成流程

**在 `document_tasks.py` 中**：
- HTML 文件**不需要**预览生成步骤
- 直接使用原始 HTML 文件即可
- 前端会自动识别并显示

```python
# 在 document_tasks.py 中（HTML 文件无需预览生成）
# HTML 文件可以直接预览，不需要转换
# if is_html:
#     # 无需任何处理，直接使用原始文件
#     pass
```

#### 6.3.4 与 LibreOffice 的关系

**LibreOffice 的作用**：
- LibreOffice 仅用于 **Office 文档**（DOCX、PPTX、XLSX）转换为 PDF 预览
- HTML 文件**不需要 LibreOffice**

**对比**：
- ✅ **HTML 预览**：直接使用原始文件，无需转换，无需 LibreOffice
- ✅ **Office 预览**：需要 LibreOffice 转换为 PDF（可选，不影响解析）
- ✅ **PDF 预览**：直接使用原始文件，无需转换

#### 6.3.5 预览状态

HTML 文件的预览状态：
- **预览可用**：文件上传完成后即可预览（无需等待转换）
- **预览方式**：iframe 直接显示 HTML 内容
- **预览质量**：完整保留原始 HTML 样式和交互（如果 HTML 中包含 JavaScript，会在 iframe 中执行）

### 6.4 HtmlService 接口设计

**文件位置**：`spx-knowledge-backend/app/services/html_service.py`

```python
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from bs4 import BeautifulSoup, Tag, NavigableString
from app.core.logging import logger

class HtmlService:
    """HTML 文档解析服务，输出结构与 DOCX/PDF 解析保持一致。"""
    
    def __init__(self, db: Session):
        self.db = db
        self.detected_encoding: Optional[str] = None
        self.encoding_confidence: Optional[float] = None
    
    def parse_document(self, file_path: str) -> Dict[str, Any]:
        """
        解析 HTML 文档
        
        Args:
            file_path: HTML 文件路径
            
        Returns:
            返回结构（与 DocxService 保持一致）:
            {
                "text_content": str,  # 合并后的完整文本
                "ordered_elements": List[Dict],  # 有序元素列表
                "filtered_elements_light": List[Dict],  # 过滤后的轻量元素
                "text_element_index_map": List[Dict],  # 文本元素索引映射
                "tables": List[Dict],  # 表格列表
                "images": List[Dict],  # 图片列表（必须包含 data 和 bytes 字段）
                "images_binary": List[Dict],  # 图片二进制列表（可选，用于兼容）
                "metadata": Dict,  # 元数据
                "is_converted_pdf": False,  # HTML 不需要 PDF 转换
                "converted_pdf_path": None  # HTML 不需要 PDF 转换
            }
        """
        # 实现细节见 7.2 核心方法设计
        pass
    
    def _load_html(self, file_path: str) -> str:
        """加载 HTML 文件并检测编码"""
        pass
    
    def _parse_html(self, html_text: str) -> BeautifulSoup:
        """解析 HTML DOM"""
        pass
    
    def _extract_elements(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """提取所有元素（按 DOM 顺序）"""
        pass
    
    def _extract_text_from_element(self, element: Tag) -> str:
        """从元素中提取文本"""
        pass
    
    def _extract_table_data(self, table: Tag) -> Optional[Dict[str, Any]]:
        """提取表格数据"""
        # 返回标准 table_data 结构
        pass
    
    def _extract_images(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """提取 HTML 中的图片"""
        # 返回包含 data 和 bytes 字段的图片列表（仅 Base64 图片）
        pass
    
    def _extract_links(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """提取链接（用于 metadata）"""
        pass
    
    def _build_heading_structure(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """构建标题结构（用于目录提取）"""
        pass
```

**关键实现要点**：
1. 所有方法必须处理异常，避免单个元素错误导致整个文档解析失败
2. `element_index` 从 1 开始递增，确保唯一性
3. `doc_order` 按元素出现顺序递增
4. 图片必须同时包含 `data` 和 `bytes` 字段（仅 Base64 图片）
5. 表格必须包含完整的 `table_data` 结构
6. 元数据必须包含 `element_count` 字段

### 6.5 元数据处理

解析完成后，HTML 特有的元数据需要写入 `document.meta`：

```python
# 在 document_tasks.py 中（解析完成后）
parse_metadata = parse_result.get('metadata', {}) or {}
doc_meta = document.meta or {}
doc_meta = doc_meta.copy() if isinstance(doc_meta, dict) else {}

# 更新通用元数据
doc_meta.update({
    "text_length": len(text_content),
    "element_count": elements_count,
})

# 更新 HTML 特有元数据
for key in ("heading_count", "heading_structure", "table_count", 
            "image_count", "link_count", "code_block_count", 
            "list_count", "semantic_tags", "has_forms", 
            "html_version", "encoding", "base_url"):
    if parse_metadata.get(key) is not None:
        doc_meta[key] = parse_metadata[key]

document.meta = doc_meta
db.commit()
```

### 6.6 输出格式示例

```python
# ordered_elements 示例（文本元素）
{
    "type": "text",
    "text": "文档标题\n\n这是一个关于...",
    "element_index": 1,  # 从 1 开始
    "doc_order": 0,
    "category": "Title",  # 或 "NarrativeText"
    "style": "",  # 样式名称（可选）
    "length": 100,  # 文本长度
    # HTML 特有字段（可选）
    "heading_level": 1,
    "heading_path": ["文档标题"],
    "tag_name": "h1"
}

# ordered_elements 示例（表格元素）
{
    "type": "table",
    "element_index": 5,
    "doc_order": 4,
    "tag_name": "table"
}

# ordered_elements 示例（图片元素）
{
    "type": "image",
    "element_index": 2,
    "doc_order": 1,
    "tag_name": "img",
    "image_ext": ".png"
}

# tables 示例（tables 列表中的项）
{
    "element_index": 5,
    "doc_order": 4,
    "table_data": {
        "cells": [["列1", "列2"], ["值1", "值2"]],  # 必需：单元格数据
        "rows": 2,      # 必需：行数
        "columns": 2,   # 必需：列数
        "structure": "html_extracted",  # 可选：结构标识
        "html": "<table>...</table>"    # 可选：原始 HTML
    },
    "table_text": "列1\t列2\n值1\t值2",  # 必需：制表符分隔的文本（用于检索）
    "page_number": None  # HTML 没有页码概念，始终为 None
}

# images 示例（必须同时包含 data 和 bytes 字段，仅 Base64 图片）
{
    "data": bytes,      # 图片二进制数据
    "bytes": bytes,     # 图片二进制数据（与 data 相同，用于兼容）
    "element_index": 2, # 元素索引（必需，用于关联图片分块）
    "doc_order": 5,     # 文档顺序
    "page_number": None,  # HTML 无页码概念
    "image_ext": ".png",  # 图片扩展名
    "width": 800,        # 图片宽度（可选）
    "height": 600,       # 图片高度（可选）
    "alt": "图片描述",    # alt 文本（可选）
    "url": None          # 如果是 Base64 图片，url 为 None；如果是 URL 图片，记录 URL（但不在 images 列表中）
}
```

## 7. 实现细节

### 7.1 依赖库

#### 必需依赖

主要依赖 `beautifulsoup4`（用于 HTML 解析）和 `lxml`（可选，更快的解析器）：

```bash
pip install beautifulsoup4 lxml
```

**依赖包清单**：
- ✅ `beautifulsoup4>=4.12.0` - HTML 解析（**需要添加到 `requirements/base.txt`**）
- ✅ `lxml>=4.9.0` - 快速 HTML/XML 解析器（可选，但推荐，**需要添加到 `requirements/base.txt`**）
- ✅ `charset-normalizer>=3.2.0` - 编码检测（**已在 `requirements/base.txt` 中**）

**注意**：所有文档解析相关的依赖包都应添加到 `requirements/base.txt` 中：
```
# Document Processing
unstructured>=0.10.0
openpyxl>=3.1.0
pandas>=2.0.0
xlrd>=2.0.0
python-docx>=1.1.0      # DOCX 解析
python-pptx>=1.0.0       # PPTX 解析
beautifulsoup4>=4.12.0   # HTML 解析（新增）
lxml>=4.9.0              # HTML/XML 快速解析器（新增，可选但推荐）
```

#### 可选依赖（预览功能）

**重要说明**：HTML 文件预览**不需要任何额外依赖**。

**Headless Browser**（仅用于生成 PDF 预览，可选且不推荐）：
- `playwright>=1.40.0` 或 `selenium>=4.15.0`
- 或 `wkhtmltopdf`（需要系统安装）
- **注意**：HTML 可以直接预览，通常不需要转换为 PDF

**总结**：
- ✅ **内容解析**：只需 `beautifulsoup4` 和 `lxml`，无需浏览器，无需 LibreOffice
- ✅ **在线预览**：HTML 文件可以直接在浏览器中预览（使用 iframe），**无需转换，无需 LibreOffice**
- ✅ **PDF 预览**：需要 headless browser（可选功能，通常不需要）
- ❌ **不需要 LibreOffice**：LibreOffice 仅用于 Office 文档转换，HTML 不需要

### 7.2 核心方法设计

```python
class HtmlService:
    def parse_document(self, file_path: str) -> Dict[str, Any]:
        """主解析方法"""
        
    def _load_html(self, file_path: str) -> str:
        """加载 HTML 文件并检测编码"""
        
    def _parse_html(self, html_text: str) -> BeautifulSoup:
        """解析 HTML DOM"""
        
    def _extract_elements(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """提取所有元素（按 DOM 顺序）"""
        
    def _extract_text_from_element(self, element: Tag) -> str:
        """从元素中提取文本"""
        
    def _extract_table_data(self, table: Tag) -> Optional[Dict[str, Any]]:
        """提取表格数据"""
        
    def _extract_images(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """提取 HTML 中的图片（仅 Base64）"""
        
    def _extract_links(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """提取链接（用于 metadata）"""
        
    def _build_heading_structure(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """构建标题结构（用于目录提取）"""
        
    def _detect_encoding(self, raw_bytes: bytes) -> None:
        """检测编码（从 meta 标签或自动检测）"""
```

### 7.3 文本提取逻辑

1. **标题提取**：
   - 识别 `<h1>` ~ `<h6>` 标签
   - 提取标题文本，记录层级（1-6）
   - 构建标题路径（用于目录）

2. **段落提取**：
   - 识别 `<p>`、`<div>`、`<span>`、`<article>`、`<section>` 等标签
   - 提取文本内容，保留换行关系
   - 跳过已处理的标题和表格

3. **列表提取**：
   - 识别 `<ul>`、`<ol>`、`<dl>` 标签
   - 提取列表项文本，保留列表结构
   - 记录列表类型（有序/无序/定义列表）

4. **代码块提取**：
   - 识别 `<pre>`、`<code>` 标签
   - 提取代码内容，保留格式
   - 识别代码语言（从 `class` 属性，如 `class="language-python"`）

5. **表格提取**：
   - 识别 `<table>` 标签
   - 提取表头（`<thead>` 或第一行 `<tr>`）
   - 提取数据行（`<tbody>` 中的 `<tr>`）
   - 构建标准 `table_data` 结构（包含 `cells`、`rows`、`columns`）
   - 生成 `table_text`：制表符分隔的文本格式（用于检索和向量化）
   - **注意**：表格数据在 `document_tasks.py` 中会写入 `document_tables` 表，并生成 `table_uid` 和 `table_group_uid`

### 7.4 图片处理

1. **图片识别**：
   - 识别 `<img>` 标签
   - 检查 `src` 属性

2. **图片提取**：
   - **Base64 图片**：从 `data:image/...;base64,...` 格式中提取并解码
   - **URL 图片**：记录 URL 到 metadata，暂不下载（可选：在图片处理阶段下载）
   - 提取图片属性：`alt`、`title`、`width`、`height`

3. **图片存储**：
   - Base64 图片的二进制数据在解析阶段提取，存储在 `images` 列表中
   - 在 `document_tasks.py` 的图片处理阶段，通过 `ImageService` 保存到 MinIO
   - 图片元数据保存到 `document_images` 表
   - 图片向量化后索引到 OpenSearch
   - 最后回填 `image_id` 和 `image_path` 到对应的图片分块 metadata 中
   - URL 图片可以记录到 metadata，但不阻塞解析流程

### 7.5 链接处理

1. **链接提取**：
   - 识别 `<a>` 标签
   - 提取链接文本和 URL（`href` 属性）
   - 处理相对链接（如果有 `base_url`）

2. **链接存储**：
   - 链接信息记录到文档级 metadata 中
   - 不单独成块，但可以在分块 metadata 中标记 `has_links` 和 `link_refs`

### 7.6 编码检测

1. **优先级**：
   - 从 `<meta charset="...">` 标签获取编码
   - 从 `<meta http-equiv="Content-Type" content="text/html; charset=...">` 获取编码
   - 使用 `charset-normalizer` 自动检测
   - 默认使用 UTF-8

2. **编码转换**：
   - 统一转换为 UTF-8 处理
   - 记录原始编码到 metadata

## 8. 目录提取（可选增强）

### 8.1 HTML 标题大纲提取

HTML 文件包含标题层级信息，可以提取为目录结构：

```python
def _extract_outline(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """
    提取 HTML 标题大纲（目录结构）
    基于 <h1> ~ <h6> 标签构建层级关系
    """
    outline = []
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    
    for heading in headings:
        level = int(heading.name[1])  # h1 -> 1, h2 -> 2, ...
        title = heading.get_text(strip=True)
        if title:
            outline.append({
                "level": level,
                "title": title,
                "position": len(outline),
                "tag_name": heading.name
            })
    
    return outline
```

### 8.2 与 DocumentTOCService 集成

需要在 `DocumentTOCService` 中实现 `extract_toc_from_html` 方法：

**在 `app/services/document_toc_service.py` 中添加**：
```python
async def extract_toc_from_html(self, document_id: int, heading_structure: List[Dict[str, Any]]) -> List[DocumentTOC]:
    """
    从 HTML 标题结构提取目录
    
    Args:
        document_id: 文档ID
        heading_structure: 标题结构列表，格式：[{"level": 1, "title": "标题", "position": 0, "tag_name": "h1"}, ...]
    
    Returns:
        目录项列表
    """
    try:
        toc_items = []
        level_stack = []  # [(level, toc_item), ...]
        
        for heading in heading_structure:
            level = heading.get('level', 1)
            title = heading.get('title', '').strip()
            if not title:
                continue
            
            # 构建层级关系
            parent_id = None
            while level_stack and level_stack[-1][0] >= level:
                level_stack.pop()
            
            if level_stack:
                parent_id = level_stack[-1][1].id
            
            # 创建目录项
            toc_item = DocumentTOC(
                document_id=document_id,
                level=level,
                title=title[:500],  # 限制长度
                position=len(toc_items),
                parent_id=parent_id,
                page_number=None,  # HTML 无页码概念
                slide_number=None,  # HTML 无幻灯片概念
            )
            toc_items.append(toc_item)
            level_stack.append((level, toc_item))
        
        # 批量保存
        if toc_items:
            self.db.add_all(toc_items)
            self.db.commit()
            logger.info(f"HTML目录提取成功: 文档ID={document_id}, 目录项数={len(toc_items)}")
        
        return toc_items
    except Exception as e:
        logger.error(f"HTML目录提取失败: {e}", exc_info=True)
        self.db.rollback()
        return []
```

**在 `document_tasks.py` 中调用**（在索引阶段，步骤 6/7）：
```python
# 在目录提取部分添加
if is_html and document.file_path:
    doc_meta = document.meta or {}
    if isinstance(doc_meta, str):
        import json as _json
        try:
            doc_meta = _json.loads(doc_meta)
        except Exception:
            doc_meta = {}
    heading_structure = doc_meta.get('heading_structure', [])
    if heading_structure:
        toc_items = asyncio.run(toc_service.extract_toc_from_html(document_id, heading_structure))
        if toc_items:
            logger.info(f"[任务ID: {task_id}] HTML目录提取成功，共 {len(toc_items)} 个目录项")
    else:
        logger.debug(f"[任务ID: {task_id}] HTML文件无标题结构，跳过目录提取")
```

## 9. 测试用例建议

### 9.1 单元测试

- 测试单页 HTML 的文本提取
- 测试表格提取和转换
- 测试图片提取（Base64 和 URL）
- 测试链接提取
- 测试标题层级提取
- 测试代码块提取
- 测试列表提取
- 测试空 HTML 处理
- 测试不规范的 HTML 容错

### 9.2 集成测试

- 测试完整的 HTML 文档解析流程
- 测试不同 HTML 版本（HTML4、HTML5、XHTML）
- 测试包含大量图片的 HTML 文件
- 测试包含复杂表格的 HTML 文件
- 测试包含表单的 HTML 文件
- 测试受损 HTML 的容错处理

### 9.3 边界情况测试

- 空 HTML 文件（只有 `<html></html>`）
- 超大 HTML 文件（> 10 MB）
- 包含特殊字符的文本
- 包含大量嵌套标签的 HTML
- 包含内联样式的 HTML
- 编码检测失败的情况
- Base64 图片解码失败的情况

## 10. 性能优化建议

1. **流式处理**：对于超大 HTML 文件，采用流式解析，逐块处理，避免一次性加载
2. **图片延迟处理**：URL 图片不阻塞解析流程，记录到 metadata 后异步处理
3. **缓存机制**：对于重复解析的 HTML 文件，可以缓存解析结果
4. **并行处理**：对于多个 HTML 文件的解析，可以并行处理（但需注意线程安全）
5. **DOM 优化**：使用 `lxml` 解析器（比 `html.parser` 更快）

## 11. 与其他格式的一致性

确保 HTML 解析器的输出格式与 DOCX、PDF、Markdown 等解析器保持一致：

- ✅ `text_content`: 完整的文本内容（字符串）
- ✅ `ordered_elements`: 有序元素列表（统一格式）
  - 每个元素必须包含 `type`（`text`、`table`、`image`）、`element_index`、`doc_order`
  - 文本元素包含 `text` 字段
  - 表格元素包含 `table_data` 引用
  - 图片元素包含图片引用信息
- ✅ `filtered_elements_light`: 轻量过滤元素列表
  - 格式：`[{"category": str, "text": str, "element_index": int, "doc_order": int}]`
- ✅ `text_element_index_map`: 文本元素索引映射
  - 格式：`[{"element_index": int, "element_type": str, "doc_order": int, "page_number": None, "coordinates": None}]`
- ✅ `tables`: 表格列表（统一格式）
  - 每个表格包含 `element_index`、`table_data`（含 `cells`、`rows`、`columns`、`structure`、`html`）、`table_text`、`page_number`（HTML 为 `None`）、`doc_order`
  - `table_data.cells` 是二维数组，第一行通常是表头
  - `table_text` 是制表符分隔的文本，用于检索和向量化
  - 表格数据会在 `document_tasks.py` 中写入 `document_tables` 表，生成 `table_uid` 和 `table_group_uid`
- ✅ `images`: 图片列表（统一格式）
  - 每个图片必须包含 `data` 和 `bytes` 字段（二进制数据，仅 Base64 图片）
  - 必须包含 `element_index`（用于关联图片分块）
  - 包含 `doc_order`、`page_number`（HTML 为 `None`）
- ✅ `images_binary`: 图片二进制列表（可选，用于兼容）
- ✅ `metadata`: 元数据字典
  - 必须包含 `element_count` 字段
  - 可包含 HTML 特有的元数据（如 `heading_count`、`heading_structure`、`link_count` 等）

**关键一致性要求**：
1. 所有元素必须有唯一的 `element_index`，从 1 开始递增
2. 所有元素必须有 `doc_order`，用于排序
3. 图片必须同时包含 `data` 和 `bytes` 字段（仅 Base64 图片）
4. 表格必须包含完整的 `table_data` 结构
5. 分块元数据必须包含 `element_index_start/end` 和 `doc_order_start/end`

这样可以确保后续的分块、向量化、索引等流程无需修改即可支持 HTML 格式。

## 12. 后续扩展

### 12.1 支持 XHTML 格式（已支持）

XHTML 是 XML 格式的 HTML，BeautifulSoup 可以自动处理。

### 12.2 支持 HTML 片段（可选）

如果上传的是 HTML 片段（不包含 `<html>` 标签），可以自动包装为完整 HTML 文档。

### 12.3 支持外部资源下载（可选）

- 下载外部图片并保存到 MinIO
- 下载外部 CSS 和 JavaScript 文件（用于完整预览）
- 处理相对链接和绝对链接

### 12.4 支持动态内容（可选）

- 使用 headless browser（如 Playwright）执行 JavaScript 后提取内容
- 处理单页应用（SPA）的动态生成内容

### 12.5 支持 HTML 邮件（可选）

- 识别 HTML 邮件格式
- 提取邮件元数据（发件人、收件人、主题等）
- 提取邮件正文和附件

## 13. 总结

HTML 解析器的实现将：
1. ✅ 完整提取 HTML 内容（文本、表格、图片、链接、代码块等）
2. ✅ 保持与现有文档解析流程的一致性
3. ✅ 充分利用 HTML 语义结构进行智能分块
4. ✅ 提供丰富的元数据支持检索和展示
5. ✅ 具备良好的错误处理和容错能力
6. ✅ 支持多种 HTML 标准和格式

通过实现 HTML 解析器，系统将支持更多类型的 Web 内容，提升知识库的覆盖范围和使用价值。

