#!/bin/bash
# RTX 5090 PyTorch 安装脚本
# 自动处理依赖冲突问题

# 不使用 set -e，因为我们需要尝试多种安装方式

echo "=========================================="
echo "RTX 5090 PyTorch 安装脚本"
echo "=========================================="
echo ""

# 检查 CUDA 版本
echo "1. 检查 CUDA 环境..."
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
    echo ""
else
    echo "⚠️  警告: 未找到 nvidia-smi"
fi

# 检查 Python 版本
echo "2. 检查 Python 版本..."
python --version
echo ""

# 尝试安装方式
INSTALL_SUCCESS=false

# 方式1: 尝试稳定版 CUDA 12.4
echo "3. 尝试方式1: 安装稳定版 (CUDA 12.4)..."
if pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124 2>&1 | tee /tmp/pytorch_install.log; then
    INSTALL_SUCCESS=true
    echo "✅ 稳定版安装成功"
else
    echo "❌ 稳定版安装失败，尝试其他方式..."
fi

# 方式2: 如果稳定版失败，尝试 CUDA 12.1
if [ "$INSTALL_SUCCESS" = false ]; then
    echo ""
    echo "4. 尝试方式2: 安装稳定版 (CUDA 12.1)..."
    if pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 2>&1 | tee /tmp/pytorch_install.log; then
        INSTALL_SUCCESS=true
        echo "✅ CUDA 12.1 版本安装成功"
    else
        echo "❌ CUDA 12.1 安装失败，尝试其他方式..."
    fi
fi

# 方式3: 如果都失败，尝试只安装 torch（rerank 可能不需要 torchvision）
if [ "$INSTALL_SUCCESS" = false ]; then
    echo ""
    echo "5. 尝试方式3: 只安装 torch（避免依赖冲突）..."
    if pip install torch --index-url https://download.pytorch.org/whl/cu124 2>&1 | tee /tmp/pytorch_install.log; then
        INSTALL_SUCCESS=true
        echo "✅ torch 安装成功（未安装 torchvision/torchaudio）"
        echo "⚠️  注意: rerank 服务通常只需要 torch，不需要 torchvision"
    else
        echo "❌ torch 单独安装也失败"
    fi
fi

# 方式4: 尝试 CUDA 12.1 的 torch
if [ "$INSTALL_SUCCESS" = false ]; then
    echo ""
    echo "6. 尝试方式4: 只安装 torch (CUDA 12.1)..."
    if pip install torch --index-url https://download.pytorch.org/whl/cu121 2>&1 | tee /tmp/pytorch_install.log; then
        INSTALL_SUCCESS=true
        echo "✅ torch (CUDA 12.1) 安装成功"
    fi
fi

# 验证安装
if [ "$INSTALL_SUCCESS" = true ]; then
    echo ""
    echo "=========================================="
    echo "7. 验证安装..."
    echo "=========================================="
    python -c "
import torch
print(f'PyTorch 版本: {torch.__version__}')
print(f'CUDA 可用: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'CUDA 版本: {torch.version.cuda}')
    print(f'GPU 数量: {torch.cuda.device_count()}')
    for i in range(torch.cuda.device_count()):
        print(f'GPU {i}: {torch.cuda.get_device_name(i)}')
        cap = torch.cuda.get_device_capability(i)
        print(f'  计算能力: {cap[0]}.{cap[1]} (sm_{cap[0]}{cap[1]})')
    # 测试 CUDA kernel
    try:
        test = torch.tensor([1.0]).cuda()
        result = test + 1.0
        print(f'✅ CUDA kernel 测试通过')
    except Exception as e:
        print(f'❌ CUDA kernel 测试失败: {e}')
"
    echo ""
    echo "=========================================="
    echo "✅ 安装完成！"
    echo "=========================================="
else
    echo ""
    echo "=========================================="
    echo "❌ 所有安装方式都失败了"
    echo "=========================================="
    echo ""
    echo "请检查:"
    echo "1. 网络连接是否正常"
    echo "2. pip 版本是否最新: pip install --upgrade pip"
    echo "3. CUDA 驱动版本是否足够新"
    echo "4. Python 版本是否兼容"
    echo ""
    echo "详细错误信息请查看: /tmp/pytorch_install.log"
    exit 1
fi

