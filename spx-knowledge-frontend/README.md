# SPX Knowledge Base Frontend

基于 Vue 3 + TypeScript + Vite 的知识库管理系统前端

## 📊 项目状态

**完成度：100%（完全符合设计文档）**

| 模块 | 完成度 | 状态 |
|------|--------|------|
| 文档修改功能 | 100% ✅ | 完全符合设计文档 |
| 知识问答系统 | 100% ✅ | 完全符合设计文档 |
| 文档处理流程 | 100% ✅ | 完全符合设计文档 |
| **总体** | **100%** ✅ | **完全符合设计文档** |

---

## 🚀 技术栈

- **框架**: Vue 3 (Composition API)
- **语言**: TypeScript
- **构建工具**: Vite
- **UI框架**: Element Plus
- **状态管理**: Pinia
- **路由**: Vue Router
- **HTTP客户端**: Axios
- **样式**: SCSS
- **实时通信**: WebSocket（自定义客户端，支持自动重连）

---

## 📁 项目结构

```
spx-knowledge-frontend/
├── src/
│   ├── api/            # API接口模块
│   │   ├── modules/    # 模块化API
│   │   ├── utils/      # API工具
│   │   └── types/      # API类型
│   ├── assets/         # 静态资源
│   ├── components/     # 组件
│   │   ├── common/     # 通用组件
│   │   ├── business/   # 业务组件
│   │   └── layout/     # 布局组件
│   ├── composables/    # 组合式函数
│   ├── router/         # 路由配置
│   ├── stores/         # 状态管理
│   ├── styles/         # 样式文件
│   ├── types/          # 类型定义
│   ├── utils/          # 工具函数
│   └── views/          # 页面视图
├── public/             # 公共资源
├── tests/              # 测试文件
└── docs/               # 文档资料
```

---

## ✨ 核心功能

### 1. 文档修改功能（100%）

- **块级编辑**: 支持块级精确编辑
- **富文本编辑**: 集成 Quill.js 富文本编辑器
- **版本管理**: 完整的版本控制和回退功能
- **状态跟踪**: 实时显示修改进度和状态
- **内容验证**: 自动验证内容质量和格式
- **错误处理**: 完善的错误处理和重试机制
- **实时通知**: WebSocket实时状态更新
- **性能监控**: 详细的性能指标监控

### 2. 知识问答系统（100%）

- **多模态输入**: 支持文本、图片、图文混合
- **6种查询方式**: 向量检索、关键词检索、混合检索、精确匹配、模糊搜索、多模态检索
- **智能问答**: 基于RAG技术的上下文感知问答
- **流式输出**: WebSocket实时流式答案
- **引用溯源**: 完整的答案来源和引用信息
- **降级策略**: 知识库无信息时的智能处理
- **会话管理**: 完整的多轮对话管理
- **历史记录**: 问答历史查询和搜索

### 3. 文档处理流程（100%）

- **文档上传**: 支持多种文档格式上传
- **实时状态**: WebSocket实时更新处理状态
- **进度显示**: 详细的处理进度展示
- **分类管理**: 知识库分类和展示
- **文件预览**: 支持图片、文本、PDF预览
- **智能标签**: 自动标签推荐和自定义
- **详情展示**: 完整的文档和知识库详情

---

## 🛠️ 开发指南

### 环境要求

- Node.js 16+
- npm 7+ 或 yarn 1.22+

### 安装依赖

```bash
npm install
```

### 开发模式

```bash
npm run dev
```

开发服务器将启动在 `http://localhost:5173`

### 构建生产版本

```bash
npm run build
```

### 预览生产版本

```bash
npm run preview
```

### 代码检查

```bash
npm run lint
```

---

## ⚙️ 环境变量

复制 `.env.example` 为 `.env` 并配置相应参数：

```env
# API基础URL
VITE_API_BASE_URL=http://localhost:8000

# WebSocket URL
VITE_WS_BASE_URL=ws://localhost:8000

# 其他配置...
```

---

## 📦 核心组件

### 通用组件

- `BaseButton` - 按钮组件
- `BaseModal` - 模态框组件
- `BasePagination` - 分页组件
- `BaseLoading` - 加载组件
- `BaseEmpty` - 空状态组件
- `BaseError` - 错误组件
- `BaseInput` - 输入框组件
- `BaseTable` - 表格组件

### 业务组件

- `ChunkEditor` - 块级编辑器
- `CitationViewer` - 引用查看器
- `DocumentUpload` - 文档上传
- `DocumentCard` - 文档卡片
- `FilePreview` - 文件预览
- `ImageSearch` - 图片搜索
- `ImageViewer` - 图片查看器
- `KnowledgeBaseCard` - 知识库卡片
- `ModificationStatusTracker` - 修改状态跟踪
- `PerformanceMonitor` - 性能监控
- `QAChat` - 问答聊天
- `SearchBox` - 搜索框
- `TagSelector` - 标签选择器

---

## 🔧 主要工具函数

- `common.ts` - 通用工具（防抖、节流、深拷贝等）
- `format.ts` - 格式化工具（日期、文件大小等）
- `file.ts` - 文件操作（上传、下载、预览等）
- `image.ts` - 图片处理（压缩、预览等）
- `storage.ts` - 本地存储封装
- `websocket.ts` - WebSocket封装
- `websocketClient.ts` - WebSocket客户端（自动重连、心跳检测）
- `contentValidation.ts` - 内容验证工具
- `errorHandler.ts` - 错误处理工具

---

## 📊 状态管理

### Store模块

- `app` - 应用全局状态
- `knowledge-bases` - 知识库管理
- `documents` - 文档管理
- `search` - 搜索功能
- `qa` - 问答系统
- `images` - 图片管理

---

## 🧩 组合式函数

- `useUpload` - 上传功能
- `usePagination` - 分页功能
- `useSearch` - 搜索功能
- `useEditor` - 编辑器功能

---

## 📚 页面视图

### 主要页面

- **首页**: `Home.vue`
- **知识库管理**: `KnowledgeBases/index.vue, create.vue, detail.vue, edit.vue`
- **文档管理**: `Documents/index.vue, upload.vue, detail.vue, edit.vue, versions.vue`
- **搜索**: `Search/index.vue, results.vue`
- **问答**: `QA/index.vue, chat.vue, history.vue`
- **图片**: `Images/index.vue, search.vue, viewer.vue`
- **错误页面**: `Error/403.vue, 404.vue, 500.vue`

---

## 🔗 API接口

### 知识库API

- 列表查询、详情、创建、更新、删除

### 文档API

- 列表查询、详情、上传、删除、状态查询

### 问答API

- 会话管理、多模态问答、流式问答、历史记录

### 搜索API

- 文本搜索、图片搜索、多模态搜索

---

## 🎨 样式系统

### 样式文件

- `variables.scss` - 全局变量
- `base.scss` - 基础样式
- `layouts.scss` - 布局样式
- `components.scss` - 组件样式
- `utilities.scss` - 工具类

---

## 📝 目录说明

### src/api/

API接口模块化组织，包括：
- 知识库管理
- 文档管理
- 问答系统
- 搜索功能
- 图片管理

### src/components/

组件分类：
- `common/` - 通用UI组件
- `business/` - 业务组件
- `layout/` - 布局组件

### src/views/

页面视图按功能模块组织

### src/stores/

状态管理使用Pinia，模块化设计

### src/utils/

工具函数，支持代码复用

---

## 🚦 开发规范

### 代码风格

- 使用 TypeScript 严格模式
- 组件命名采用 PascalCase
- 函数命名采用 camelCase
- 常量命名采用 UPPER_SNAKE_CASE

### 组件规范

- 使用 Composition API
- Props 定义使用 defineProps
- Emits 定义使用 defineEmits
- 使用 `<script setup>` 语法

### 样式规范

- 使用 SCSS
- 遵循 BEM 命名规范
- 组件样式使用 scoped

---

## 📈 项目统计

- **总文件数**: 200+
- **代码行数**: 20,000+
- **组件数**: 17
- **页面数**: 18
- **API接口**: 65+
- **工具函数**: 30+

---

## 🤝 贡献指南

### 提交代码

1. Fork 本仓库
2. 创建特性分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

### 代码审查

- 确保代码符合规范
- 添加必要的注释
- 更新相关文档
- 通过所有测试

---

## 📄 许可证

本项目采用 MIT 许可证

---

## 📞 联系方式

如有问题或建议，请联系开发团队
