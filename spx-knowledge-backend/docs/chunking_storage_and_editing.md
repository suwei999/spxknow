## 文档分块、存储与编辑方案（总结）

### 1. 总体目标
- 支持超大文档稳健解析与检索；
- 控制数据库体量，提升可运维性；
- 支持块级别编辑、版本管理与回滚；
- 向量检索效果与延迟可控。

---

### 2. 存储分层与职责
- OpenSearch（检索层）
  - 存可检索内容：`content`（完整文本内容，用于快速文本/BL25检索）、`content_vector`（向量，用于KNN语义检索）、少量元字段（`document_id/chunk_id/knowledge_base_id/category_id/chunk_type/tags/created_at`）。
  - 图片索引单独存入 `images` 索引，字段含 `ocr_text`（用于文本检索）、`image_vector`（图片向量）等。
  - 写入策略：bulk + 默认 `refresh=false`，阶段完成或调试时 `refresh=wait_for`。
  - **重要**：`content` 字段必须完整存储到 OpenSearch，以支持快速关键词/BM25检索；仅存储向量会导致文本检索性能差。

- MinIO（真源/归档层）
  - 存原始文件与“分块全文”归档：每文档一个 `chunks.jsonl.gz`（一行一个分块）。
  - 作为重建索引、版本对比、审计的真实来源。

- MySQL（元数据/控制层）
  - 仅存最小元信息：`document_chunks(id, document_id, chunk_index, chunk_type, version, chunk_version_id, created_at, 状态/错误)`；默认不强制存大段 `content`（见配置）。
  - 版本表：`document_versions`、`chunk_versions` 记录变更、注释、操作者；`documents.current_version_id` 指向当前版本；`document_chunks.chunk_version_id` 指向块的当前版本。

> 结论：检索靠 OpenSearch，真源放 MinIO，控制与审计在 MySQL。

---

### 3. 智能分块策略（当前实现）

#### 3.1 分块算法
当前实现采用**基于段落边界 + 固定大小限制**的分块策略：

**分块流程**：
1. **段落分割**：按双换行符（`\n\n`）将文本分割为段落
2. **累积合并**：逐个段落累积，直到接近 `chunk_size` 上限
3. **智能切分**：
   - 超过大小限制时，保存当前累积块，开始新块
   - 保留 `chunk_overlap` 重叠（取前一块末尾的 overlap 字符）
   - 超长段落（单段超过 chunk_size）：按句号（`。`）进一步分割
   - 超长句子：强制按字符切分（最后手段）
4. **过滤优化**：移除空块和小于 `min_size` 的碎片块

**三种策略配置**（仅参数不同，算法一致）：
- **semantic（语义策略）**：`chunk_size=1000`，`overlap=200`，`min_size=100`
- **structure（结构策略）**：`chunk_size=1500`，`overlap=150`，`min_size=200`
- **fixed（固定策略）**：`chunk_size=512`，`overlap=50`，`min_size=100`

#### 3.2 未来增强方向（可选）
- **真正的语义分块**：基于句子向量相似度，在语义边界处切分
- **结构感知分块**：识别标题层级（H1/H2/H3），按章节/小节边界分块
- **递归分块**：Markdown/HTML等结构化文档，按文档树结构递归分块

#### 3.3 向量化策略（不必对所有分块）
- 过滤与限额
  - 长度阈值：过短/过长跳过或二次切分；
  - 类型/噪声过滤：页眉页脚、目录、代码、版权页等可跳过；
  - 去重：hash/相似度去重；
  - 上限：按文档/租户设置最大向量数（如 ≤ 3k）。

- 重要度优先
  - 标题/小结/含关键术语块优先；正文按打分选前 N。

- 延迟/分批
  - 先向量化前 K 块保证可用，后台继续补齐；失败自动重试、幂等。

---

### 4. 图片处理与索引
- 解析提取图片二进制 → 上传 MinIO（路径：`documents/<yyyy>/<mm>/<doc_XXXX>/images/...`）→ 记录 URL 与 sha256 去重；
- 生成缩略图并存 MinIO；
- MySQL `document_images` 落库（`image_type/width/height/ocr_text/status/...`）；
- OpenSearch `images` 索引存图片向量与 OCR 文本，支持图/文检索。

#### 4.0 图片去重处理逻辑
**相同图片（SHA256相同）的处理策略**：
1. **MySQL存储去重**：
   - `create_image_from_bytes` 方法首先计算图片的SHA256哈希
   - 查询数据库，如果已存在相同SHA256的图片记录，直接返回已有记录
   - 如果不存在，才执行上传MinIO、生成缩略图、OCR识别、创建数据库记录等操作
   - **结果**：相同图片在MySQL中只有一条记录，不重复存储

2. **向量生成优化**：
   - 对于已存在的图片（通过SHA256判断），从OpenSearch获取已有向量
   - 如果OpenSearch中已有512维向量，直接复用，**不重复生成向量**
   - 如果向量不存在或维度不正确，才调用CLIP模型生成新向量
   - **结果**：相同图片不重复生成向量，节省计算资源

3. **MinIO存储去重**：
   - 图片路径使用SHA256哈希作为文件名：`documents/{doc_id}/images/{sha256}{ext}`
   - 相同SHA256的图片会覆盖已存在的文件（实际是同一文件）
   - **结果**：MinIO中相同图片只存储一份，节省存储空间

4. **OpenSearch索引更新**：
   - 即使图片已存在，仍需要更新OpenSearch索引
   - 更新索引中的 `document_id`、`knowledge_base_id` 等字段，反映图片与当前文档的关联关系
   - **注意**：同一图片可能出现在多个文档中，索引会更新为最后一次索引时的文档关联

**去重效果总结**：
- ✅ **MySQL**：相同图片只有一条记录（通过SHA256去重）- **已实现**
- ✅ **MinIO**：相同图片只存储一份（通过SHA256路径去重）- **已实现**
- ✅ **向量生成**：相同图片复用已有向量（不重复生成）- **已实现**
- ✅ **OpenSearch**：索引会更新为最新文档关联（支持多文档关联）- **已实现**（每次索引时更新 document_id、page_number、coordinates）

#### 4.0.1 位置信息保证机制
**位置信息的存储策略**：

1. **图片/表格位置信息**：
   - **提取来源**：从 Unstructured 解析结果中提取 `page_number` 和 `coordinates`（x, y, width, height）
   - **存储位置**：
     - **OpenSearch**：存储在 `images` 索引的 `page_number` 和 `coordinates` 字段（用于检索和定位）
     - **MySQL**：存储在 `document_images.metadata` JSON 字段中（用于持久化）
   - **索引更新**：每次索引时，即使图片已存在（SHA256相同），也会更新位置信息（`page_number`、`coordinates`），确保位置信息与当前文档一致
   - **多文档支持**：同一图片（SHA256相同）在不同文档中的位置信息独立存储和更新

2. **文本分块位置信息**：
   - **顺序保证**：`chunk_index` 字段保存分块在文档中的顺序（从0开始递增）
   - **存储位置**：
     - **MySQL**：`document_chunks.chunk_index` 字段（用于排序和查询）
     - **OpenSearch**：`metadata` 中包含 `chunk_index`（用于检索结果排序）
     - **MinIO**：`chunks.jsonl.gz` 中按 `index` 顺序存储（保持原始顺序）
   - **位置还原**：通过 `chunk_index` 排序，可以还原分块在文档中的原始顺序

3. **元素间相对位置（关键问题）**：
   - **当前实现的问题**：
     - 文本元素和图片元素在解析时被分离处理：
       * 所有文本元素的文本内容被拼接成字符串（`text_content`）
       * 图片被单独提取到 `images` 列表
     - 分块时只对文本字符串进行分块，**丢失了图片与文本的相对位置关系**
     - 无法精确确定图片应该插入到哪个文本分块之前/之后
   - **现有位置信息**：
     - 图片的 `page_number` 和 `coordinates` 记录其在文档中的精确位置
     - 文本分块的 `chunk_index` 记录其在文档中的顺序
     - **但两者之间没有直接的关联关系**（无法通过 `chunk_index` 和 `page_number` 精确确定图片应该插入的位置）
   - **上下文信息**：
     - 图片的 `description` 字段存储图片前后的文本内容（由 Unstructured 提取）
     - 可以用于语义关联，但无法精确确定插入位置

**位置信息的还原机制**：

1. **按页码还原**：
   - 查询特定页码的所有图片：`page_number = X`
   - 查询特定页码的所有分块：通过 `page_number` 在 metadata 中查询

2. **按坐标还原**：
   - 图片的 `coordinates` 字段（x, y, width, height）精确记录其在页面中的位置
   - 可以用于在文档渲染时精确定位图片

3. **按顺序还原**：
   - 文本分块通过 `chunk_index` 排序，还原文档中的原始顺序
   - 图片通过 `page_number` + `coordinates.y` 排序，还原在页面中的垂直位置

4. **文档结构还原**：
   - **MinIO 真源**：`chunks.jsonl.gz` 按 `index` 顺序存储，保证可以完全还原文档结构
   - **OpenSearch 检索**：检索结果按 `chunk_index` 或 `page_number` 排序，保证结果顺序与原文一致
   - **MySQL 元数据**：通过 `chunk_index` 和位置信息（存储在 metadata JSON 中），可以还原文档的层次结构

**注意事项**：
- ✅ **去重时的位置信息**：图片去重（SHA256相同）时，虽然图片实体只有一个，但每个文档中的位置信息（`page_number`、`coordinates`）会独立存储和更新 - **已实现**（每次索引时更新位置信息）
- ⚠️ **分块后的位置精度（已知限制）**：
  - **当前状态**：文本分块后，单个分块可能跨越多页，但**当前实现中未存储分块的页码信息**
  - **原因**：当前分块策略（`chunk_text`）只处理纯文本字符串，在文本提取阶段（`_process_parsed_elements`）已将元素拼接成字符串，丢失了原始元素的页码信息
  - **影响范围**：无法精确查询"特定页码的所有分块"，只能通过 `chunk_index` 排序还原顺序
  - **未来改进方向**：
    - 改进分块策略：在分块时记录每个段落/句子来自哪个页码范围
    - 存储 `page_number_start` 和 `page_number_end` 到 `metadata` JSON 中
    - 或者在 MinIO 的 `chunks.jsonl.gz` 中记录每个分块的页码范围

#### 4.0.2 前端文档还原能力评估
**当前实现能否100%还原原文档？**

说明：已在 4.0.3「方案1实现：记录元素顺序索引」落地，现已支持按 `element_index` 100% 还原原文档顺序。以下内容为“改造前”的评估，保留用于对比。

❌ **不能100%还原**，存在以下限制：

1. **图片与文本的相对位置丢失**：
   - **问题**：在解析阶段，文本和图片被分离处理，分块时丢失了相对位置关系
   - **影响**：无法精确确定图片应该插入到哪个文本分块之前/之后
   - **当前可用方案**：
     * 通过 `page_number` 和 `coordinates.y` 排序图片
     * 通过 `chunk_index` 排序文本分块
     * **近似还原**：可以按页码分组，在同一页码内按坐标排序，但无法精确到字符级别

2. **文本分块没有页码信息**：
   - **问题**：文本分块只保留了 `chunk_index`，没有页码范围
   - **影响**：无法精确判断图片是在某个分块的开始还是结束位置

3. **改进方案（需要修改代码）**：
   - **方案1：记录元素顺序索引**（推荐）
     * 在 `_process_parsed_elements` 中，为每个元素（文本/图片）记录其在原始 `elements` 列表中的索引（`element_index`）
     * 图片保存 `element_index` 到 `metadata` JSON 中
     * 分块时，记录每个文本分块覆盖的 `element_index` 范围
     * 前端展示时：按 `element_index` 排序所有元素（文本分块+图片），实现100%还原
   
   - **方案2：建立图片与分块关联**
     * 分块时，根据文本内容和图片的 `description` 字段，匹配图片所属的分块
     * 在 `document_images` 表中添加 `chunk_id` 字段，关联到最近的文本分块
     * 或者添加 `insert_after_chunk_index` 字段，记录图片应该插入到哪个分块之后
   
   - **方案3：保存完整的元素序列**
     * 在 MinIO 中保存原始 `elements` 列表（带位置信息）
     * 前端展示时，从 MinIO 读取原始元素序列，而不是从分块重构

**当前可用方案（近似还原）**：
- 按 `page_number` 分组
- 在同一页码内，文本分块按 `chunk_index` 排序，图片按 `coordinates.y` 排序
- 交叉合并文本和图片，**可以达到近似还原**，但不能保证100%准确

**结论（改造前）**：要实现100%还原原文档顺序，需要修改代码，添加元素顺序索引或建立图片与分块的关联关系。

当前状态：已实现✅（见 4.0.3 方案1实现）。

#### 4.0.3 方案1实现：记录元素顺序索引（已实现✅）

**实现细节**：

1. **解析阶段记录 element_index**：
   - 在 `_process_parsed_elements` 中，遍历 `elements` 时记录每个元素在原始列表中的索引（`element_index`）
   - 文本元素：记录 `element_index` 和文本在 `text_content` 中的位置范围，生成 `text_element_index_map`
   - 图片元素：在 `image_info` 中保存 `element_index`
   - 表格元素：在 `table_info` 中保存 `element_index`

2. **分块阶段保留 element_index 范围**：
   - 改进 `chunk_text` 方法，接收 `text_element_index_map` 参数
   - 根据分块在文本中的位置范围，通过 `_get_element_index_range` 计算每个分块覆盖的 `element_index_start` 和 `element_index_end`
   - 返回格式：`List[Dict]` 包含 `{'content': str, 'element_index_start': int, 'element_index_end': int}`

3. **存储阶段保存 element_index**：
   - **文本分块**：
     * MySQL：在 `document_chunks.metadata` JSON 中保存 `element_index_start` 和 `element_index_end`
     * MinIO：在 `chunks.jsonl.gz` 中保存 `element_index_start` 和 `element_index_end`
     * OpenSearch：在 `metadata` 中保存（用于检索）
   - **图片**：
     * MySQL：在 `document_images.metadata` JSON 中保存 `element_index`
     * OpenSearch：在 `images` 索引中保存 `element_index` 字段（用于排序和还原）

4. **API接口提供100%还原**：
   - 新增 `GET /documents/{document_id}/elements` 接口
   * 获取所有文本分块和图片，按 `element_index` 排序
   * 返回格式：混合列表，包含 `type: 'chunk'|'image'` 和对应的 `element_index`
   * 支持 `include_content` 参数控制是否返回完整内容
   * **实现100%还原原文档顺序**

**使用示例**：
```python
# 前端调用API
GET /api/v1/documents/123/elements?include_content=true

# 响应示例
{
  "status": "success",
  "data": {
    "document_id": "123",
    "total_elements": 15,
    "elements_with_index": 15,  # 所有元素都有element_index
    "elements_without_index": 0,
    "elements": [
      {
        "type": "chunk",
        "element_index": 0,
        "element_index_start": 0,
        "element_index_end": 2,
        "chunk_id": 1001,
        "chunk_index": 0,
        "content": "第一段文本..."
      },
      {
        "type": "image",
        "element_index": 3,
        "image_id": 2001,
        "image_path": "documents/.../image.png",
        ...
      },
      {
        "type": "chunk",
        "element_index": 4,
        "element_index_start": 4,
        "element_index_end": 6,
        "chunk_id": 1002,
        "chunk_index": 1,
        "content": "第二段文本..."
      }
    ]
  }
}

# 前端按 elements 数组顺序渲染，即可100%还原原文档
```

**优势**：
- ✅ 100%还原原文档顺序（按 `element_index` 排序）
- ✅ 向后兼容（没有 `element_index` 的元素仍可正常处理）
- ✅ 支持文档部分内容修改（通过 `element_index` 精确定位）
- ✅ 最小改动（只增加字段，不改变现有逻辑）

**注意事项**：
- `element_index` 从 0 开始，对应 Unstructured 解析返回的 `elements` 列表索引
- 文本分块的 `element_index_start` 和 `element_index_end` 可能相同（单个元素）或不同（多个元素合并）
- 如果图片或分块没有 `element_index`（旧数据），仍可按原有逻辑排序（向后兼容）

#### 4.1 图片向量模型选择
**推荐方案：CLIP模型（ViT-B/32）**
- **向量维度**：512维（与OpenSearch索引配置一致）
- **优势**：
  - 支持图像-文本对齐，适合图文联合检索
  - 多模态理解能力强，语义检索效果好
  - 性能稳定，推理速度快
  - 开源模型，无需额外API费用
- **实现方式**：使用本地CLIP模型（`open-clip`，ViT-B/32，512维）

#### 4.2 向量维度说明
**什么是向量维度？**
- 向量维度表示用多少个数值（浮点数）来描述一张图片或一段文本的特征
- 例如：512维向量 = `[0.123, -0.456, 0.789, ..., 0.234]`（共512个数字）
- 每个数值代表图片在某个特征维度上的"强度"或"特征值"

**维度是否越高越好？**
- **不是！** 维度需要平衡多个因素：
  1. **表达能力**：维度越高，理论上能表达更细微的特征差异
  2. **存储成本**：维度越高，存储空间越大（512维 × 4字节 = 2KB/图片）
  3. **计算成本**：维度越高，向量相似度计算越慢（KNN搜索复杂度增加）
  4. **检索精度**：维度过高可能导致"维度灾难"，检索效果反而下降
  5. **模型训练**：需要更多数据训练高维模型，过拟合风险增加

**为什么选择512维？**
- **经过验证的平衡点**：CLIP模型在512维下已达到很好的检索精度
- **性能最优**：512维的向量计算速度快，内存占用合理
- **广泛支持**：大多数向量数据库和检索系统都优化了512维向量
- **实际效果**：对于图像检索任务，512维已经足够表达图片的语义特征

**维度对比示例**：
| 维度 | 表达能力 | 存储成本 | 计算速度 | 推荐度 |
|------|---------|---------|---------|--------|
| 128维 | 一般 | 低 | 快 | ⭐⭐⭐ |
| **512维** | **优秀** | **中等** | **快** | **⭐⭐⭐⭐⭐** |
| 768维 | 很好 | 中等 | 中等 | ⭐⭐⭐⭐ |
| 1024维 | 优秀 | 高 | 慢 | ⭐⭐⭐ |
| 2048维 | 优秀 | 很高 | 很慢 | ⭐⭐ |

**结论**：512维是图像向量检索的最佳平衡点，既能保证检索精度，又能控制计算和存储成本。

---

### 5. 版本管理与编辑
- 块级微改（PATCH）
  1) 生成新 `chunk_version`（记录 old_hash、新文本、`modified_by`、备注）；
  2) 分配递增的 `version_number`（基于当前块版本+1），切换 `document_chunks.chunk_version_id` 到新版本；
  3) 触发该块向量重算与 OS 单条更新；
  4) 记录 `operation_logs`。

- 重切分（Re-chunk）
  - 生成新 `document_version`；通过对比新旧分块（基于内容 hash 或文本相似度）识别“变化块清单”，仅重建变化块的向量与索引；
  - `documents.current_version_id` 切换；
  - 历史版本可回滚与对比。

- 版本清理
  - 保留最近 N 个版本；更老版本归档到冷存；提供“合并版本”工具。

---

### 6. 前端展示与交互
- 列表：当前版本的块分页/虚拟滚动；显示序号、片段、状态、版本、修改人时间；
- 搜索：从 OS 返回命中与高亮；
- 操作：编辑、历史、回滚、重向量化、删除块；
- 版本选择器：切换 `version_id` 查看不同版本内容。

---

### 7. API 设计（示例）
- `GET /api/documents/{id}/chunks?page,size,version_id`
- `GET /api/documents/{id}/chunks/{chunk_id}?version_id`
- `PATCH /api/documents/{id}/chunks/{chunk_id}`  body: `{ content, version_comment }`
- `POST /api/documents/{id}/rechunk`  body: `{ scope, page_range?, strategy?, version_comment }`
- `GET /api/documents/{id}/versions`
- `POST /api/documents/{id}/versions/{version_id}/switch`

---

### 8. 配置建议
- `STORE_CHUNK_TEXT_IN_DB=false`（轻量模式）
  - 含义：当为 false 时，`document_chunks.content` 不持久化正文（可为空/空串）；展示与编辑按需回退从 MinIO 读取对应块文本；版本内容保存在 `chunk_versions.content`。
- `ENABLE_DOCX_REPAIR=true`、`ENABLE_OFFICE_TO_PDF=true`、`SOFFICE_PATH`（解析稳健）
- `POPPLER_PATH`、`TESSERACT_PATH`、`TESSDATA_PREFIX`（PDF hi_res 依赖）
- `OLLAMA_BASE_URL`、`OLLAMA_MODEL`、`OLLAMA_EMBEDDING_MODEL`（向量/生成）

---

### 9. 监控与运营
- 每日统计：块数、OS 文档数、MinIO 容量、失败重试；超阈告警；
- 一键重建索引：从 MinIO `chunks.jsonl.gz` 回灌 OS（模型或 mapping 调整时使用）。

---

### 10. 取舍结论
- 超大文档不把分块正文长期存 MySQL，避免体量膨胀；
- **可检索内容（文本+向量）完整存储到 OpenSearch**，实现快速检索；真源/归档进 MinIO；
- 块级版本与编辑保证可追溯、可回滚；
- 向量化按“必要且足够”执行，成本与延迟可控。

**存储策略总结**：
- MySQL：仅元数据（不存正文，除非配置 `STORE_CHUNK_TEXT_IN_DB=true`）
- MinIO：真源归档（`chunks.jsonl.gz`，用于回灌与审计）
- OpenSearch：完整检索内容（`content` 文本 + `content_vector` 向量，用于快速检索）


---

### 11. 检索策略（混合检索与精确匹配）
- **向量检索（语义检索）**：基于 `documents.content_vector` 和 `images.image_vector` 的 KNN。
- **关键词检索（文本检索）**：基于 `documents.content` 字段使用 BM25 算法（`match`/`multi_match`），`images` 索引基于 `ocr_text`/`description` 字段；精确匹配使用 `term`/`keyword` 过滤（如 `document_id`/`chunk_type`）。
- **混合检索**：服务层并行执行 KNN 向量检索与 BM25 关键词检索，按权重融合得分，返回统一结果。

实现要点：
- 查询向量由 `VectorService.generate_embedding(query_text)` 生成；
- 关键词查询使用 OpenSearch 的 `match`/`bool` 组合，直接检索 `content` 字段（已完整存储）；
- 融合规则：`score = α * knn_score + (1-α) * bm25_score`，或接入 `bge-reranker`；
- **性能优化**：文本内容存储在 OpenSearch 中，避免每次检索都回查 MinIO，大幅提升检索速度。

---

### 12. 块级编辑与回滚
- PATCH 块：更新块内容，写入 `chunk_versions`，切换当前指针；重算向量并单条更新 OS。
- 历史/回滚：读取 `chunk_versions` 历史，选择版本回滚并刷新 OS。

---

### 13. 版本管理
- `document_versions` 管理全文重切分版本；
- Re-chunk 仅对变化块重建向量与索引；完成后切换 `documents.current_version_id`；
- 提供版本列表与切换 API；
- 回灌工具：从 MinIO 的 `chunks.jsonl.gz` 重建 OS（模型/映射调整时使用）。


