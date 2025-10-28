# OpenSearch IK中文分词插件安装说明

## 📋 说明

OpenSearch 2.x 版本需要手动安装 IK 中文分词插件，Docker Compose 启动后需要手动安装。

---

## 🚀 安装步骤

### 1. 启动OpenSearch容器

```bash
docker-compose -f docker/docker-compose.middleware.yml up -d opensearch
```

### 2. 进入容器安装IK插件

```bash
# 进入容器
docker exec -it spx-knowledge-opensearch bash

# 安装IK插件 (OpenSearch 2.11.0对应 Elasticsearch 8.11.0)
bin/opensearch-plugin install -b https://github.com/medcl/elasticsearch-analysis-ik/releases/download/v8.11.0/elasticsearch-analysis-ik-8.11.0.zip

# 退出容器
exit
```

### 3. 重启容器使插件生效

```bash
docker restart spx-knowledge-opensearch
```

### 4. 验证插件安装

```bash
# 查看已安装的插件
curl http://localhost:9200/_cat/plugins

# 测试分词功能
curl -X POST "http://localhost:9200/_analyze" -H 'Content-Type: application/json' -d'
{
  "analyzer": "ik_max_word",
  "text": "中文分词测试"
}'
```

---

## ✅ 预期输出

安装成功后，`_cat/plugins` 应显示：
```
analysis-ik 8.11.0
```

---

## 🐳 自动化方案 (可选)

如果想要自动安装，可以使用以下Dockerfile：

```dockerfile
FROM opensearchproject/opensearch:2.11.0

# 安装IK插件
RUN bin/opensearch-plugin install -b https://github.com/medcl/elasticsearch-analysis-ik/releases/download/v8.11.0/elasticsearch-analysis-ik-8.11.0.zip
```

然后修改docker-compose.yml使用build而不是image。

---

**注意事项**:
- OpenSearch 2.x 对应 Elasticsearch 8.x，需要安装 v8.11.0版本的IK插件
- 安装插件后必须重启容器才能生效
- 插件安装完成后会占用额外存储空间

