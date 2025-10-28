# 远程ClamAV配置指南

## 概述

ClamAV支持通过**TCP Socket**进行远程调用，这意味着：
- ✅ 可以在远程服务器上部署ClamAV
- ✅ 多个后端服务可以共享同一个ClamAV服务器
- ✅ 便于集中管理和更新病毒库

---

## 1. 远程ClamAV服务器配置

### Ubuntu系统

```bash
# 1. 安装ClamAV
sudo apt update
sudo apt install clamav clamav-daemon -y

# 2. 配置clamd.conf启用TCP
sudo nano /etc/clamav/clamd.conf

# 添加以下配置：
TCPSocket 3310
TCPAddr 0.0.0.0  # 监听所有接口，或者指定IP
AllowSupplementaryGroups Yes

# 3. 重启服务
sudo systemctl restart clamav-daemon

# 4. 检查端口监听
sudo netstat -tlnp | grep 3310
```

### Windows系统

```powershell
# 1. 编辑配置文件
notepad "C:\Program Files\ClamAV\conf\clamd.conf"

# 添加以下配置：
TCPSocket 3310
TCPAddr 0.0.0.0
AllowSupplementaryGroups Yes

# 2. 重启服务
net stop clamd
net start clamd

# 3. 检查端口
netstat -an | findstr 3310
```

---

## 2. 防火墙配置

### Ubuntu
```bash
# 开放3310端口
sudo ufw allow 3310/tcp

# 或者iptables
sudo iptables -A INPUT -p tcp --dport 3310 -j ACCEPT
```

### Windows
```powershell
# Windows防火墙
New-NetFirewallRule -DisplayName "ClamAV" -Direction Inbound -LocalPort 3310 -Protocol TCP -Action Allow
```

---

## 3. 后端配置

### 配置方式一：环境变量（推荐）

```bash
# .env 文件
CLAMAV_ENABLED=true
CLAMAV_SOCKET_PATH=           # 留空，不使用本地Socket
CLAMAV_USE_TCP=true           # 启用TCP模式
CLAMAV_TCP_HOST=192.168.1.100 # 远程ClamAV服务器IP
CLAMAV_TCP_PORT=3310
CLAMAV_SCAN_TIMEOUT=60
```

### 配置方式二：代码中指定

```python
from app.services.clamav_service import ClamAVService

# 使用远程ClamAV
clamav = ClamAVService(
    socket_path=None,           # 不使用本地Socket
    tcp_host='192.168.1.100',   # 远程服务器IP
    tcp_port=3310
)

result = clamav.scan_file('/path/to/file')
```

### 配置方式三：settings.py

```python
# app/config/settings.py
class Settings(BaseSettings):
    CLAMAV_ENABLED: bool = True
    CLAMAV_SOCKET_PATH: Optional[str] = None  # 不指定本地Socket
    CLAMAV_USE_TCP: bool = True               # 优先使用TCP
    CLAMAV_TCP_HOST: str = "192.168.1.100"    # 远程服务器
    CLAMAV_TCP_PORT: int = 3310
```

---

## 4. 连接优先级

系统会按以下优先级尝试连接：

```
1. 如果指定了 CLAMAV_SOCKET_PATH
   → 使用Unix Socket或Named Pipe

2. 如果 CLAMAV_USE_TCP=true
   → 使用TCP连接（可以是远程）

3. 如果 TCP_HOST 不是 localhost
   → 自动使用TCP连接远程

4. 否则
   → 根据操作系统自动选择本地Socket
```

---

## 5. 测试远程连接

### Python测试代码
```python
from app.services.clamav_service import ClamAVService

# 创建远程ClamAV服务
clamav = ClamAVService(
    socket_path=None,
    tcp_host='192.168.1.100',  # 远程服务器IP
    tcp_port=3310
)

# 检查连接
if clamav.is_available():
    info = clamav.get_service_info()
    print(f"连接成功: {info}")
    
    # 测试扫描
    result = clamav.scan_file('/etc/passwd')
    print(f"扫描结果: {result}")
else:
    print("ClamAV服务未连接")
```

### 命令行测试
```bash
# 使用clamdscan连接远程
clamdscan --host=192.168.1.100 --port=3310 /etc/passwd
```

---

## 6. Docker部署远程ClamAV

### docker-compose.yml
```yaml
version: '3.8'

services:
  clamav-server:
    image: clamav/clamav:latest
    hostname: clamav-server
    ports:
      - "3310:3310"  # 暴露TCP端口
    volumes:
      - clamav-data:/var/lib/clamav
      - ./clamd.conf:/etc/clamav/clamd.conf
    environment:
      - CLAMD_CONF_TCPSocket=3310
      - CLAMD_CONF_TCPAddr=0.0.0.0
    networks:
      - network1

  backend:
    build: .
    depends_on:
      - clamav-server
    environment:
      - CLAMAV_TCP_HOST=clamav-server
      - CLAMAV_TCP_PORT=3310
    networks:
      - network1

networks:
  network1:
    driver: bridge

volumes:
  clamav-data:
```

---

## 7. 安全考虑

### 1. 网络安全
```bash
# 只允许特定IP连接
# 在clamav服务器上配置iptables
sudo iptables -A INPUT -p tcp --dport 3310 -s 10.0.0.0/8 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 3310 -j DROP
```

### 2. 使用VPN
- 将ClamAV服务器放在内网
- 后端服务通过VPN访问

### 3. 加密通信（未来支持）
- ClamAV目前不直接支持TLS
- 可以通过VPN或SSH隧道实现加密

### SSH隧道方式
```bash
# 在本地创建SSH隧道
ssh -L 3310:localhost:3310 user@clamav-server

# 后端连接本地端口
CLAMAV_TCP_HOST=localhost
CLAMAV_TCP_PORT=3310
```

---

## 8. 性能优化

### 1. 连接池
```python
from app.services.clamav_service import ClamAVService

# 创建连接池
clamav_pool = []

for _ in range(5):  # 5个连接
    clamav = ClamAVService(
        socket_path=None,
        tcp_host='192.168.1.100',
        tcp_port=3310
    )
    clamav_pool.append(clamav)

# 使用连接池
import random
clamav = random.choice(clamav_pool)
result = clamav.scan_file('/path/to/file')
```

### 2. 异步扫描
```python
import asyncio
from app.services.clamav_service import ClamAVService

async def scan_file_async(file_path: str):
    """异步扫描文件"""
    clamav = ClamAVService(
        socket_path=None,
        tcp_host='192.168.1.100',
        tcp_port=3310
    )
    return clamav.scan_file(file_path)

# 批量异步扫描
async def batch_scan(files):
    tasks = [scan_file_async(f) for f in files]
    results = await asyncio.gather(*tasks)
    return results
```

---

## 9. 故障排除

### 无法连接远程服务器
```bash
# 1. 检查网络连通性
ping 192.168.1.100

# 2. 检查端口是否开放
telnet 192.168.1.100 3310

# 3. 检查防火墙
sudo iptables -L -n | grep 3310

# 4. 检查ClamAV服务
sudo systemctl status clamav-daemon
journalctl -u clamav-daemon -n 50
```

### 扫描超时
```python
# 增加超时时间
class Settings(BaseSettings):
    CLAMAV_SCAN_TIMEOUT: int = 120  # 增加到120秒
```

### 性能问题
```bash
# 1. 监控连接数
netstat -an | grep 3310 | wc -l

# 2. 监控CPU和内存
top -p $(pgrep clamd)

# 3. 增加ClamAV服务器资源
# 编辑 /etc/clamav/clamd.conf
MaxScanSize 200M
MaxFileSize 200M
MaxRecursion 10
MaxFiles 10000
```

---

## 10. 最佳实践

### 架构建议
```
┌─────────────────┐
│   用户上传文件   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     TCP     ┌──────────────────┐
│  后端服务(FastAPI) ──────────►│  ClamAV服务器     │
│                 │              │  192.168.1.100   │
│  端口: 8000     │              │  端口: 3310      │
└─────────────────┘              └──────────────────┘
```

### 配置建议
1. **开发环境**: 使用本地ClamAV（Socket方式）
2. **生产环境**: 使用远程ClamAV集群（TCP方式）
3. **容器环境**: 使用Docker网络连接

### 监控建议
1. 监控远程ClamAV服务的健康状态
2. 记录扫描成功率
3. 设置告警（连接失败、扫描超时）

---

## 11. 配置示例

### 本地模式（默认）
```env
CLAMAV_ENABLED=true
CLAMAV_SOCKET_PATH=/var/run/clamav/clamd.ctl
```

### 远程模式
```env
CLAMAV_ENABLED=true
CLAMAV_SOCKET_PATH=
CLAMAV_TCP_HOST=192.168.1.100
CLAMAV_TCP_PORT=3310
CLAMAV_USE_TCP=true
```

### Docker模式
```env
CLAMAV_ENABLED=true
CLAMAV_SOCKET_PATH=
CLAMAV_TCP_HOST=clamav-server
CLAMAV_TCP_PORT=3310
```

---

## 总结

✅ **支持的调用方式**:
- Unix Socket（Ubuntu本地）
- Named Pipe（Windows本地）
- TCP Socket（本地或远程）
- 自动检测和优先级

✅ **远程调用的优势**:
- 资源共享（多个后端共享一个ClamAV服务器）
- 集中管理（统一的病毒库更新）
- 易于扩展（独立扩展ClamAV服务器）

✅ **安全建议**:
- 使用内网IP
- 配置防火墙规则
- 使用VPN或SSH隧道

