# ClamAV 安装和使用指南

## 1. Ubuntu系统安装

### 1.1 使用apt安装（推荐）
```bash
# 更新包列表
sudo apt update

# 安装ClamAV
sudo apt install clamav clamav-daemon -y

# 更新病毒库
sudo freshclam

# 启动服务
sudo systemctl start clamav-daemon
sudo systemctl enable clamav-daemon

# 检查服务状态
sudo systemctl status clamav-daemon
```

### 1.2 验证安装
```bash
# 检查版本
clamscan --version

# 检查守护进程
clamdscan --version

# 测试扫描
clamdscan /etc/passwd
```

### 1.3 配置Socket（用于Python调用）
```bash
# 编辑配置文件
sudo nano /etc/clamav/clamd.conf

# 确保以下配置已启用：
# LocalSocket /var/run/clamav/clamd.ctl
# FixStaleSocket yes
# TCPSocket 3310
# TCPAddr 127.0.0.1

# 重启服务
sudo systemctl restart clamav-daemon
```

---

## 2. Windows系统安装

### 2.1 下载安装
1. 访问ClamAV官方网站: https://www.clamav.net/downloads
2. 下载Windows安装包: `ClamAV-0.x.x-win-x64.msi`
3. 运行安装程序，按默认设置安装

### 2.2 配置服务
```powershell
# 安装路径通常是: C:\Program Files\ClamAV

# 1. 编辑配置文件
# 打开: C:\Program Files\ClamAV\conf\clamd.conf
# 取消注释并修改:
# LocalSocket \\.\pipe\clamd
# FixStaleSocket yes

# 2. 注册为Windows服务
cd "C:\Program Files\ClamAV"
clamd.exe --install

# 3. 启动服务
net start clamd

# 4. 更新病毒库
freshclam.exe
```

### 2.3 使用命令行工具
```powershell
# 添加ClamAV到PATH
# 添加到系统环境变量: C:\Program Files\ClamAV

# 测试扫描
clamscan C:\Windows\System32\notepad.exe
```

---

## 3. Python调用方式

### 3.1 安装python-clamd
```bash
# Ubuntu
pip install python-clamd

# Windows
pip install python-clamd
```

### 3.2 Socket方式调用（推荐）

#### Ubuntu: Unix Socket
```python
import clamd

# 连接到Unix Socket
cd = clamd.ClamdUnixSocket()

# 扫描文件
result = cd.scan('/path/to/file')
print(result)
```

#### Windows: Named Pipe
```python
import clamd

# 连接到Named Pipe
cd = clamd.ClamdUnixSocket(socketpath=r'\\.\pipe\clamd')

# 扫描文件
result = cd.scan('C:\\path\\to\\file')
print(result)
```

### 3.3 TCP方式调用

```python
import clamd

# 连接到TCP服务（需要clamd.conf中配置TCP）
cd = clamd.ClamdNetworkSocket('localhost', 3310)

# 扫描文件
result = cd.scan('/path/to/file')
print(result)
```

### 3.4 直接命令调用

```python
import subprocess

def scan_file(file_path):
    """直接调用clamdscan命令"""
    try:
        # Ubuntu/Windows通用
        result = subprocess.run(
            ['clamdscan', file_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # 检查返回码（0=安全，1=发现病毒）
        if result.returncode == 0:
            return {'status': 'safe', 'message': result.stdout}
        elif 'FOUND' in result.stdout:
            return {'status': 'infected', 'message': result.stdout}
        else:
            return {'status': 'error', 'message': result.stderr}
    except subprocess.TimeoutExpired:
        return {'status': 'timeout', 'message': 'Scan timeout'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}
```

---

## 4. 集成到后端服务

### 4.1 创建ClamAV服务类

```python
# app/services/clamav_service.py
import clamd
import subprocess
import platform
from pathlib import Path
from app.core.logging import logger
from app.core.exceptions import CustomException, ErrorCode

class ClamAVService:
    """ClamAV反病毒扫描服务"""
    
    def __init__(self):
        self.socket_path = self._get_socket_path()
        self.client = None
        self._connect()
    
    def _get_socket_path(self):
        """根据操作系统获取Socket路径"""
        system = platform.system()
        
        if system == "Linux":
            # Ubuntu/Unix
            return "/var/run/clamav/clamd.ctl"
        elif system == "Windows":
            # Windows Named Pipe
            return r'\\.\pipe\clamd'
        else:
            return None
    
    def _connect(self):
        """连接到ClamAV守护进程"""
        try:
            if self.socket_path:
                self.client = clamd.ClamdUnixSocket(self.socket_path)
            else:
                # 使用网络Socket
                self.client = clamd.ClamdNetworkSocket('localhost', 3310)
            
            # 测试连接
            response = self.client.ping()
            if response != 'PONG':
                raise Exception("ClamAV连接失败")
            
            logger.info("ClamAV服务连接成功")
            
        except Exception as e:
            logger.error(f"ClamAV服务连接失败: {e}")
            self.client = None
    
    def scan_file(self, file_path: str) -> dict:
        """
        扫描文件
        
        返回:
        {
            'status': 'safe' | 'infected' | 'error',
            'message': str,
            'threats': list  # if infected
        }
        """
        try:
            if not self.client:
                logger.warning("ClamAV未连接，跳过病毒扫描")
                return {
                    'status': 'warning',
                    'message': 'ClamAV服务未连接',
                    'skip_scan': True
                }
            
            logger.info(f"开始病毒扫描: {file_path}")
            
            # 使用clamd扫描
            result = self.client.scan(file_path)
            
            # 解析结果
            status = result.get(file_path)
            
            if status is None:
                return {
                    'status': 'error',
                    'message': '无法获取扫描结果'
                }
            
            if status[0] == 'OK':
                logger.info(f"文件安全: {file_path}")
                return {
                    'status': 'safe',
                    'message': '文件安全',
                    'threats': []
                }
            elif status[0] == 'FOUND':
                threats = status[1]
                logger.warning(f"发现威胁: {file_path}, {threats}")
                return {
                    'status': 'infected',
                    'message': f'发现威胁: {threats}',
                    'threats': threats
                }
            else:
                return {
                    'status': 'error',
                    'message': f'扫描异常: {status[0]}',
                    'threats': []
                }
                
        except Exception as e:
            logger.error(f"病毒扫描错误: {e}")
            # 不抛出异常，允许服务继续运行
            return {
                'status': 'error',
                'message': str(e),
                'threats': []
            }
    
    def scan_stream(self, file_data: bytes) -> dict:
        """
        扫描文件流（内存扫描）
        
        参数:
        - file_data: 文件字节数据
        
        返回:
        {
            'status': 'safe' | 'infected' | 'error',
            'message': str,
            'threats': list
        }
        """
        try:
            if not self.client:
                return {
                    'status': 'warning',
                    'message': 'ClamAV服务未连接',
                    'skip_scan': True
                }
            
            # 使用clamd进行流式扫描
            result = self.client.instream(file_data)
            
            if result['stream'][0] == 'OK':
                return {
                    'status': 'safe',
                    'message': '文件安全',
                    'threats': []
                }
            elif result['stream'][0] == 'FOUND':
                return {
                    'status': 'infected',
                    'message': f"发现威胁: {result['stream'][1]}",
                    'threats': [result['stream'][1]]
                }
            else:
                return {
                    'status': 'error',
                    'message': '扫描异常',
                    'threats': []
                }
                
        except Exception as e:
            logger.error(f"流式扫描错误: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'threats': []
            }
    
    def update_database(self):
        """更新病毒库"""
        try:
            logger.info("开始更新ClamAV病毒库")
            
            if platform.system() == "Windows":
                # Windows使用freshclam.exe
                subprocess.run(['freshclam.exe'], check=True)
            else:
                # Linux使用freshclam
                subprocess.run(['sudo', 'freshclam'], check=True)
            
            logger.info("病毒库更新完成")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"病毒库更新失败: {e}")
        except Exception as e:
            logger.error(f"病毒库更新错误: {e}")
```

### 4.2 集成到文件验证服务

```python
# 修改 app/services/file_validation_service.py

from app.services.clamav_service import ClamAVService

class FileValidationService:
    def __init__(self):
        self.magic = magic.Magic(mime=True)
        self.clamav = ClamAVService()  # 初始化ClamAV服务
    
    def scan_file_security(self, file: UploadFile) -> Dict[str, Any]:
        """安全扫描 - 包括病毒扫描"""
        try:
            # 保存到临时文件
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                tmp_path = tmp_file.name
                shutil.copyfileobj(file.file, tmp_file)
            
            # 1. ClamAV病毒扫描
            virus_scan = self.clamav.scan_file(tmp_path)
            
            # 2. 恶意脚本检测
            script_scan = self._detect_malicious_scripts(tmp_path, file.content_type)
            
            # 清理临时文件
            os.unlink(tmp_path)
            
            return {
                "clean": virus_scan['status'] == 'safe' and script_scan['safe'],
                "virus_scan": virus_scan,
                "script_scan": script_scan,
                "recommendation": self._get_security_recommendation(virus_scan, script_scan)
            }
            
        except Exception as e:
            logger.error(f"安全扫描错误: {e}")
            return {
                "clean": True,  # 默认信任，避免阻塞系统
                "virus_scan": {"status": "error", "message": str(e)},
                "script_scan": {"safe": True},
                "recommendation": "扫描失败，请手动验证文件"
            }
    
    def _detect_malicious_scripts(self, file_path: str, content_type: str) -> dict:
        """检测恶意脚本"""
        malicious_patterns = []
        
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            
            # 检测可疑关键字
            suspicious_keywords = [
                b'eval(', b'exec(', b'system(', b'cmd.exe',
                b'powershell', b'wscript', b'javascript:',
                b'ActiveXObject', b'CreateObject',
                b'Shell.Exec', b'WScript.Shell'
            ]
            
            found_keywords = []
            for keyword in suspicious_keywords:
                if keyword.lower() in content.lower():
                    found_keywords.append(keyword.decode('utf-8', errors='ignore'))
            
            return {
                "safe": len(found_keywords) == 0,
                "found_keywords": found_keywords,
                "content_type": content_type
            }
            
        except Exception as e:
            logger.error(f"脚本检测错误: {e}")
            return {"safe": True}
```

---

## 5. Docker部署方式

### 5.1 Dockerfile（包含ClamAV）

```dockerfile
FROM ubuntu:22.04

# 安装依赖
RUN apt-get update && apt-get install -y \
    clamav \
    clamav-daemon \
    python3 \
    python3-pip

# 创建配置
RUN mkdir -p /var/run/clamav

# 配置ClamAV
COPY clamd.conf /etc/clamav/clamd.conf

# 更新病毒库
RUN freshclam

# 启动ClamAV守护进程
CMD ["clamd"]
```

### 5.2 docker-compose.yml

```yaml
version: '3.8'

services:
  backend:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - clamav
    environment:
      - CLAMAV_HOST=clamav
      - CLAMAV_PORT=3310
  
  clamav:
    image: clamav/clamav:latest
    ports:
      - "3310:3310"
    volumes:
      - clamav-data:/var/lib/clamav
    environment:
      - CLAMD_CONF_CustomConfig=/etc/clamav/clamd.conf

volumes:
  clamav-data:
```

---

## 6. 配置和优化

### 6.1 性能优化
```bash
# 编辑 /etc/clamav/clamd.conf

# 增加扫描超时
ScanTimeout 120

# 增加扫描大小限制
MaxScanSize 100M

# 启用启发式扫描
DetectBrokenExecutables yes

# 启用PUA检测（可能有害的应用）
DetectPUA yes
```

### 6.2 自动更新病毒库
```bash
# 创建定时任务
sudo crontab -e

# 每天凌晨3点更新病毒库
0 3 * * * freshclam --quiet
```

---

## 7. 测试和验证

### 7.1 测试脚本
```python
# test_clamav.py
from app.services.clamav_service import ClamAVService

def test_clamav():
    service = ClamAVService()
    
    # 测试干净文件
    result = service.scan_file('/etc/passwd')
    print(f"干净文件扫描: {result}")
    
    # 测试病毒签名（EICAR测试文件）
    eicar = b'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'
    result = service.scan_stream(eicar)
    print(f"病毒检测: {result}")
    
    assert result['status'] == 'infected'
    print("✅ ClamAV工作正常")

if __name__ == '__main__':
    test_clamav()
```

### 7.2 EICAR测试文件
```bash
# 创建EICAR测试文件
echo 'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' > eicar.txt

# 扫描测试
clamdscan eicar.txt

# 预期输出：FOUND

# 删除测试文件
rm eicar.txt
```

---

## 8. 注意事项

### 8.1 性能考虑
- ClamAV扫描会消耗一定的CPU和内存
- 大型文件扫描可能需要较长时间
- 建议：限制扫描文件大小，异步处理大文件

### 8.2 误报处理
- 保持病毒库最新以减少误报
- 提供白名单机制
- 记录误报并上报

### 8.3 故障处理
- ClamAV服务不可用时，是否阻塞上传？
  - 建议：记录警告但允许继续（避免单点故障）
- 扫描超时的处理策略
- 定期检查服务健康状态

---

## 9. 总结

**推荐部署方式**:
- **开发/测试**: 直接调用clamdscan命令
- **生产环境**: 使用clamd守护进程 + python-clamd库

**跨平台兼容性**:
- ✅ Ubuntu: Unix Socket
- ✅ Windows: Named Pipe
- ✅ 网络Socket: 通用

**最佳实践**:
1. 定期更新病毒库
2. 监控扫描性能
3. 实现扫描超时机制
4. 提供用户友好的错误提示

