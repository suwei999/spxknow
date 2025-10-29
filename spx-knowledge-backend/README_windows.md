# Windows 安装指南

## 安装所有依赖

```bash
pip install -r requirements.txt
```

### 依赖说明

- **filetype**: 文件类型检测（纯 Python，跨平台）
- **clamd**: ClamAV 病毒扫描（可选，需要 ClamAV 服务）
- 其他依赖已自动管理

## 中间件服务

### 启动中间件（MySQL、MinIO、Redis、OpenSearch）

```bash
cd spx-knowledge-backend
docker-compose -f docker/docker-compose.middleware.yml up -d
```

详细说明见 [中间件服务使用指南.md](中间件服务使用指南.md)

## 启动服务

```bash
python app.py
```

服务将在 http://localhost:8000 启动，并自动打开浏览器到 API 文档页面。

