#!/bin/bash

# A-Stock-Monitor Server Installation Script
# 自动检测环境并安装依赖（增强版：支持自动安装 Python 3.8）

set -e

echo "=== 开始安装 A-Stock-Monitor 服务端 ==="

# 1. 检查 Python 环境 (Akshare 需要 Python 3.8+)
echo "[1/5] 检查 Python 环境..."

# 检查当前 python3 版本
PYTHON_CMD="python3"
if command -v python3 &> /dev/null; then
    ver=$(python3 -c"import sys; print(sys.version_info.major, sys.version_info.minor)")
    major=$(echo $ver | cut -d' ' -f1)
    minor=$(echo $ver | cut -d' ' -f2)
    if [ "$major" -eq 3 ] && [ "$minor" -ge 8 ]; then
        echo "Python 版本符合要求: $major.$minor"
    else
        echo "当前 Python 版本 $major.$minor 过低，需要 3.8+。"
        PYTHON_CMD=""
    fi
else
    PYTHON_CMD=""
fi

# 如果默认 python 不满足，尝试寻找 python3.8 或 python3.9
if [ -z "$PYTHON_CMD" ]; then
    if command -v python3.8 &> /dev/null; then
        PYTHON_CMD="python3.8"
        echo "找到 python3.8，将使用此版本。"
    elif command -v python3.9 &> /dev/null; then
        PYTHON_CMD="python3.9"
        echo "找到 python3.9，将使用此版本。"
    fi
fi

# 如果仍然没有合适的 Python，尝试自动安装
if [ -z "$PYTHON_CMD" ]; then
    echo "未找到合适的 Python 3.8+，尝试自动安装..."
    
    if [ -f /etc/redhat-release ]; then
        # CentOS/RHEL/Alibaba Cloud Linux
        echo "检测到 RedHat 系系统，尝试通过 yum 安装 python38..."
        sudo yum install -y python38 python38-devel python38-pip || {
            echo "尝试启用 SCL 源安装..."
            sudo yum install -y centos-release-scl
            sudo yum install -y rh-python38 rh-python38-python-devel
            source /opt/rh/rh-python38/enable
            PYTHON_CMD="python3"
        }
        if [ -z "$PYTHON_CMD" ] && command -v python3.8 &> /dev/null; then
             PYTHON_CMD="python3.8"
        fi
    elif [ -f /etc/debian_version ]; then
        # Ubuntu/Debian
        echo "检测到 Debian 系系统，尝试通过 apt 安装 python3.8..."
        sudo apt-get update
        sudo apt-get install -y python3.8 python3.8-venv python3.8-dev
        PYTHON_CMD="python3.8"
    fi

    if [ -z "$PYTHON_CMD" ]; then
        echo "错误：无法自动安装 Python 3.8+。请手动安装 python3.8 后重试。"
        exit 1
    fi
fi

echo "使用 Python 命令: $PYTHON_CMD"

# 2. 创建虚拟环境 (避免污染系统环境)
echo "[2/5] 配置 Python 虚拟环境..."
# 如果 venv 目录存在但损坏，建议删除
if [ -d "venv" ] && [ ! -f "venv/bin/python" ]; then
    rm -rf venv
fi

if [ ! -d "venv" ]; then
    $PYTHON_CMD -m venv venv
    echo "虚拟环境已创建。"
else
    echo "虚拟环境已存在，跳过创建。"
fi

# 激活虚拟环境
source venv/bin/activate

# 验证虚拟环境 Python 版本
VENV_VER=$(python -c"import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "虚拟环境 Python 版本: $VENV_VER"

# 3. 安装 Python 依赖
echo "[3/5] 安装 Python 依赖 (可能需要几分钟)..."
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "错误：找不到 requirements.txt 文件！"
    exit 1
fi

# 4. 检查 Node.js 环境与 PM2
echo "[4/5] 检查 Node.js 与 PM2..."
if ! command -v node &> /dev/null; then
    echo "未检测到 Node.js，尝试安装..."
    curl -fsSL https://rpm.nodesource.com/setup_18.x | sudo bash -
    sudo yum install -y nodejs || sudo apt-get install -y nodejs
fi

if ! command -v pm2 &> /dev/null; then
    echo "安装 PM2 进程管理器..."
    sudo npm install -g pm2
fi

# 5. 数据预热 (关键：防止启动后页面空白)
echo "[5/6] 执行数据预热 (抓取初始数据)..."
# 确保使用虚拟环境的 python
$PWD/venv/bin/python fetch_sector_data.py history_dynamic "半导体,云计算,有色金属,煤炭" 20 || echo "预热 history 失败 (非致命)"
$PWD/venv/bin/python fetch_sector_data.py rank || echo "预热 rank 失败 (非致命)"
$PWD/venv/bin/python fetch_sector_data.py rotation || echo "预热 rotation 失败 (非致命)"

# 6. 配置环境与启动
echo "[6/6] 启动服务..."
if [ ! -f ".env" ]; then
    echo "检测到缺少 .env 文件，从 .env.example 复制..."
    cp .env.example .env
    echo "警告：请务必编辑 .env 文件填入 DEEPSEEK_API_KEY，否则 AI 功能不可用！"
fi

# 安装项目 Node 依赖
npm install --production

# 使用 PM2 启动
pm2 start ecosystem.config.js
pm2 save
# 设置开机自启
pm2 startup | grep "sudo" | bash || true

echo "=== 部署完成！ ==="
echo "1. 请确保在 .env 中填入了 Key: vim .env"
echo "2. 服务端口: 8787 (请在阿里云安全组放行此端口)"
echo "3. 查看日志: pm2 logs"
