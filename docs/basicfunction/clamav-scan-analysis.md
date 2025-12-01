# ClamAV 扫描机制分析

> 分析时间：2025-01-XX  
> 分析范围：文档上传流程中的 ClamAV 病毒扫描

## 1. 当前实现情况

### 1.1 扫描流程 ✅

**所有文档上传都会经过 ClamAV 检测**（如果启用）：

1. **上传入口**：`document_service.py:upload_document()`
   - 调用 `file_validation.validate_file(file)`

2. **验证流程**：`file_validation_service.py:validate_file()`
   - 步骤 1：文件格式验证
   - 步骤 2：文件大小验证
   - **步骤 3：安全扫描** ← 包含 ClamAV 检测
   - 步骤 4：文件哈希计算

3. **安全扫描**：`file_validation_service.py:scan_file_security()`
   - 检查 ClamAV 是否可用：`self.clamav.is_available()`
   - 如果可用，执行 ClamAV 病毒扫描：`self.clamav.scan_stream(file_content)`
   - 如果发现病毒，**直接拒绝上传**

### 1.2 扫描逻辑

```python
# file_validation_service.py:196-219
def scan_file_security(self, file: UploadFile) -> Dict[str, Any]:
    # 1. ClamAV病毒扫描（如果启用）
    virus_scan_result = None
    if self.clamav.is_available():  # ← 检查 ClamAV 是否可用
        logger.info("执行ClamAV病毒扫描")
        virus_scan_result = self.clamav.scan_stream(file_content)
        
        # 如果发现病毒，直接返回错误
        if virus_scan_result.get('status') == 'infected':
            threats = virus_scan_result.get('threats', [])
            logger.error(f"❌ 发现病毒: {threats}")
            raise CustomException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"文件包含病毒: {', '.join(threats)}"
            )
```

### 1.3 配置控制

**ClamAV 可以通过配置启用/禁用**：

```python
# settings.py:304-310
CLAMAV_ENABLED: bool = True  # ← 默认启用
CLAMAV_SOCKET_PATH: Optional[str] = None
CLAMAV_TCP_HOST: Optional[str] = "localhost"
CLAMAV_TCP_PORT: int = 3310
CLAMAV_SCAN_TIMEOUT: int = 60
CLAMAV_USE_TCP: bool = False
```

**环境变量**：
```bash
# env.example
CLAMAV_ENABLED=true  # 设置为 false 可禁用
```

## 2. 扫描行为分析

### 2.1 扫描触发条件

| 条件 | 行为 |
|------|------|
| `CLAMAV_ENABLED=true` 且 ClamAV 服务可用 | ✅ **执行扫描**，发现病毒则拒绝上传 |
| `CLAMAV_ENABLED=true` 但 ClamAV 服务不可用 | ⚠️ **跳过扫描**，记录警告，**不阻止上传** |
| `CLAMAV_ENABLED=false` | ⚠️ **跳过扫描**，不阻止上传 |

### 2.2 扫描失败处理

**如果 ClamAV 服务不可用**：
- 不会阻止文件上传
- 会记录警告日志
- 会继续执行恶意脚本检测（模式匹配）

```python
# clamav_service.py:188-193
if not self.client:
    return {
        'status': 'warning',
        'message': 'ClamAV服务未连接，跳过病毒扫描',
        'threats': [],
        'skip_scan': True
    }
```

### 2.3 扫描结果处理

| 扫描结果 | 行为 |
|---------|------|
| `status='safe'` | ✅ 允许上传 |
| `status='infected'` | ❌ **拒绝上传**，抛出异常 |
| `status='error'` | ⚠️ 记录错误，**不阻止上传** |
| `status='warning'` | ⚠️ 记录警告，**不阻止上传** |

## 3. 潜在问题

### 3.1 问题 1：ClamAV 不可用时仍允许上传 ⚠️

**当前行为**：
- 如果 ClamAV 服务不可用，会跳过扫描，但**不阻止上传**

**风险**：
- 恶意文件可能绕过病毒检测

**建议**：
- 考虑添加配置选项：`CLAMAV_REQUIRED=true`
- 如果 `CLAMAV_REQUIRED=true` 且 ClamAV 不可用，则拒绝上传

### 3.2 问题 2：大文件扫描限制 ⚠️

**当前实现**：
```python
# clamav_service.py:199-201
if len(file_data) > 25 * 1024 * 1024:  # 25MB限制
    logger.warning("文件超过流式扫描限制，改用文件扫描")
    return self._scan_large_file(file_data)
```

**问题**：
- 流式扫描有 25MB 限制
- 大文件需要临时保存到磁盘进行扫描
- 可能影响性能

### 3.3 问题 3：HTML 文件特殊处理 ⚠️

**当前行为**：
- HTML 文件也会经过 ClamAV 扫描
- 但 HTML 文件可能包含 JavaScript 代码，可能被误报

**建议**：
- HTML 文件扫描后，还需要进行恶意脚本检测（已实现）
- 恶意脚本检测不会阻止上传，只记录警告

## 4. 建议改进

### 4.1 添加 ClamAV 必需配置

**建议添加**：
```python
# settings.py
CLAMAV_REQUIRED: bool = False  # 如果为 true，ClamAV 不可用时拒绝上传
```

**修改 `scan_file_security()`**：
```python
if self.clamav.is_available():
    virus_scan_result = self.clamav.scan_stream(file_content)
    # ...
elif settings.CLAMAV_REQUIRED:
    # 如果 ClamAV 必需但不可用，拒绝上传
    raise CustomException(
        code=ErrorCode.VALIDATION_ERROR,
        message="ClamAV 服务不可用，无法进行安全扫描"
    )
```

### 4.2 改进错误处理

**当前**：ClamAV 扫描失败时，只记录警告，不阻止上传

**建议**：根据配置决定是否阻止上传

### 4.3 添加扫描统计

**建议添加**：
- 扫描成功/失败统计
- 病毒检测统计
- 扫描耗时统计

## 5. 总结

### 5.1 当前状态

- ✅ **所有文档上传都会经过 ClamAV 检测**（如果启用且可用）
- ✅ **发现病毒会拒绝上传**
- ⚠️ **ClamAV 不可用时不会阻止上传**（可能的安全风险）
- ✅ **支持通过配置启用/禁用 ClamAV**

### 5.2 扫描范围

**所有支持的文件类型都会扫描**：
- PDF
- DOCX
- PPTX
- XLSX
- TXT
- MD
- **HTML** ← 包括 HTML 文件
- CSV
- JSON
- XML

### 5.3 安全建议

1. **生产环境**：
   - 建议启用 ClamAV：`CLAMAV_ENABLED=true`
   - 建议设置 `CLAMAV_REQUIRED=true`（需要实现）
   - 确保 ClamAV 服务正常运行

2. **开发环境**：
   - 可以禁用 ClamAV：`CLAMAV_ENABLED=false`
   - 但需要注意安全风险

3. **HTML 文件**：
   - HTML 文件会经过 ClamAV 扫描
   - 还会进行恶意脚本检测（模式匹配）
   - 建议保持当前实现

---

**分析完成时间**：2025-01-XX  
**分析人**：AI Assistant  
**结论**：✅ **所有文档上传都会经过 ClamAV 检测（如果启用），但 ClamAV 不可用时不会阻止上传**

