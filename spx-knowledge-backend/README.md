# SPX Knowledge Base 后端

## 📋 项目简介

基于FastAPI的知识库系统后端，支持文档上传、解析、向量化、知识问答等核心功能。

## ✨ 核心功能

- ✅ **文档处理** - 支持9种格式，智能分块，向量化
- ✅ **文档修改** - 块级编辑，版本管理，一致性保证
- ✅ **知识问答** - 多模态输入，智能降级，引用溯源
- ✅ **图片搜索** - 以图找图，以文找图
- ✅ **数据一致性** - MySQL/OpenSearch/Redis三端一致

## 🚀 快速开始

### 环境要求

- Python 3.9+
- MySQL 8.0+
- OpenSearch 2.x
- MinIO
- Redis
- Ollama

### 安装依赖

```bash
pip install -r requirements/base.txt
```

### 配置环境

复制 `.env.example` 为 `.env` 并配置参数。

### 启动服务

```bash
# 启动FastAPI
uvicorn app.main:app --reload

# 启动Celery Worker
celery -A app.tasks.celery_app worker --loglevel=info
```

## 📚 相关文档

- [后端开发总结报告](./后端开发总结报告.md)
- [开发完整报告](./README_开发报告.md)
- [前后端接口对比报告](./前后端API接口对比报告.md)

## 📊 项目统计

- **API接口**: 100+ 个
- **服务类**: 20+ 个  
- **数据模型**: 15+ 个
- **功能完成度**: 100%

## 🎯 系统状态

✅ **生产就绪**

---

**项目状态**: ✅ 开发完成  
**最后更新**: 2024年1月
