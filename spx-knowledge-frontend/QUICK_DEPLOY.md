# 🚀 快速部署到远程服务器

## 最快方式（3步完成）

### 1️⃣ 上传代码到服务器

```bash
# 方式A: Git 克隆（推荐）
ssh user@your-server
git clone <你的仓库地址>
cd spx-knowledge-frontend/spx-knowledge-frontend

# 方式B: 压缩上传
# 本地执行
tar -czf frontend.tar.gz spx-knowledge-frontend
scp frontend.tar.gz user@your-server:/tmp/
# 服务器执行
ssh user@your-server
cd /opt
tar -xzf /tmp/frontend.tar.gz
cd spx-knowledge-frontend
```

### 2️⃣ 修改后端地址

编辑 `docker/nginx/default.conf`，找到这一行：

```nginx
proxy_pass http://192.168.131.158:8081;
```

改成你的后端服务器地址：

```nginx
proxy_pass http://your-backend-server:8081;
```

### 3️⃣ 一键部署

**Linux/Mac 服务器：**
```bash
chmod +x deploy.sh
./deploy.sh http://your-backend-server:8081
```

**Windows 服务器：**
```powershell
.\deploy.ps1 -BackendUrl "http://your-backend-server:8081"
```

**手动部署：**
```bash
docker-compose build
docker-compose up -d
```

## ✅ 完成！

访问：`http://your-server-ip:3000`

---

## 📋 服务器准备（首次部署）

### 安装 Docker

**Ubuntu/Debian:**
```bash
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker $USER
```

**CentOS/RHEL:**
```bash
sudo yum install -y docker
sudo systemctl start docker
sudo systemctl enable docker
```

**验证安装:**
```bash
docker --version
docker-compose --version
```

### 开放端口

```bash
# Ubuntu/Debian
sudo ufw allow 3000/tcp

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=3000/tcp
sudo firewall-cmd --reload
```

---

## 🔧 常用操作

```bash
# 查看日志
docker-compose logs -f

# 重启服务
docker-compose restart

# 停止服务
docker-compose down

# 更新代码后重新部署
git pull
docker-compose build --no-cache
docker-compose up -d
```

---

## 🌐 生产环境建议

### 1. 使用域名和 HTTPS

配置外部 Nginx 反向代理，添加 SSL 证书：

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 2. 修改默认端口为 80

编辑 `docker-compose.yml`：

```yaml
ports:
  - "80:80"  # 改为 80 端口
```

### 3. 设置自动启动

`docker-compose.yml` 中已配置 `restart: always`，确保 Docker 服务开机自启：

```bash
sudo systemctl enable docker
```

---

## ❓ 常见问题

**Q: 无法访问？**
- 检查防火墙：`sudo ufw status`
- 检查容器状态：`docker-compose ps`
- 查看日志：`docker-compose logs`

**Q: 后端 API 请求失败？**
- 检查后端服务是否运行
- 检查 nginx 配置中的后端地址
- 检查服务器网络连通性：`curl http://backend-server:8081/health`

**Q: 如何更新代码？**
```bash
git pull
docker-compose build --no-cache
docker-compose up -d
```

---

## 📞 需要帮助？

查看详细文档：`deploy.md`

