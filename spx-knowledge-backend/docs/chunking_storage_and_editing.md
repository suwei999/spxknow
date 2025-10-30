## 文档分块、存储与编辑方案（总结）

### 1. 总体目标
- 支持超大文档稳健解析与检索；
- 控制数据库体量，提升可运维性；
- 支持块级别编辑、版本管理与回滚；
- 向量检索效果与延迟可控。

---

### 2. 存储分层与职责
- OpenSearch（检索层）
  - 存可检索内容：`content`、`content_vector`、少量元字段（`document_id/chunk_id/...`）。
  - 图片索引单独存入 `images` 索引，字段含 OCR 文本与图片向量等。
  - 写入策略：bulk + 默认 `refresh=false`，阶段完成或调试时 `refresh=wait_for`。

- MinIO（真源/归档层）
  - 存原始文件与“分块全文”归档：每文档一个 `chunks.jsonl.gz`（一行一个分块）。
  - 作为重建索引、版本对比、审计的真实来源。

- MySQL（元数据/控制层）
  - 仅存最小元信息：`document_chunks(id, document_id, chunk_index, chunk_type, version, created_at, 状态/错误)`；不强制存大段 `content`。
  - 版本表：`document_versions`、`chunk_versions` 记录变更、注释、操作者；`documents.current_version_id` 指向当前版本。

> 结论：检索靠 OpenSearch，真源放 MinIO，控制与审计在 MySQL。

---

### 3. 向量化策略（不必对所有分块）
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

---

### 5. 版本管理与编辑
- 块级微改（PATCH）
  1) 生成新 `chunk_version`（记录 old_hash、新文本、`modified_by`、备注）；
  2) 切换 `document_chunks.chunk_version_id` 到新版本；
  3) 触发该块向量重算与 OS 单条更新；
  4) 记录 `operation_logs`。

- 重切分（Re-chunk）
  - 生成新 `document_version`；结构性变更仅重建变化块的向量与索引；
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
- 可检索内容进 OpenSearch，真源/归档进 MinIO；
- 块级版本与编辑保证可追溯、可回滚；
- 向量化按“必要且足够”执行，成本与延迟可控。


---

### 11. 检索策略（混合检索与精确匹配）
- 向量检索：基于 `documents.content_vector` 和 `images.image_vector` 的 KNN。
- 关键词检索：`documents.content` 与 `images.ocr_text/description` 的 text 字段；精确匹配走 keyword/term 过滤（如 `document_id`/`chunk_type`）。
- 混合检索：服务层融合接口并行跑 KNN 与 match，再做简单加权或 Reranker 排序；返回统一结果。

实现要点：
- 查询向量由 `VectorService.generate_embedding(query_text)` 生成；
- 关键词查询使用 `match`/`bool` 组合；
- 融合规则：`score = α * knn_score + (1-α) * bm25_score`，或接入 `bge-reranker`。

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


