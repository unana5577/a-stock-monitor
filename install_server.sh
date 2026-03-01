#!/bin/bash

# A-Stock-Monitor Server Installation Script
# 自动检测环境并安装依赖

set -e

echo "=== 开始安装 A-Stock-Monitor 服务端 ==="

# 1. 检查 Python 环境
echo "[1/5] 检查 Python 环境..."
if ! command -v python3 &> /dev/null; then
    echo "未检测到 python3，尝试安装..."
    if [ -f /etc/redhat-release ]; then
        sudo yum install -y python3 python3-devel
    elif [ -f /etc/debian_version ]; then
        sudo apt-get update && sudo apt-get install -y python3 python3-dev python3-venv
    else
        echo "无法自动安装 Python3，请手动安装后重试。"
        exit 1
    fi
else
    echo "Python3 已安装: $(python3 --version)"
fi

# 2. 创建虚拟环境 (避免污染系统环境)
echo "[2/5] 配置 Python 虚拟环境..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "虚拟环境已创建。"
else
    echo "虚拟环境已存在，跳过创建。"
fi

# 激活虚拟环境
source venv/bin/activate

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

# 5. 配置环境与启动
echo "[5/5] 启动服务..."
if [ ! -f ".env" ]; then
    echo "检测到缺少 .env 文件，从 .env.example 复制..."
    cp .env.example .env
    echo "请后续编辑 .env 文件填入 API Key (可选)"
fi

# 安装项目 Node 依赖
npm install --production

# 使用 PM2 启动
pm2 start ecosystem.config.js
pm2 save
# 设置开机自启 (根据系统不同可能需要手动运行输出的命令)
pm2 startup | grep "sudo" | bash || true

echo "=== 部署完成！ ==="
echo "服务已在后台运行，使用 'pm2 status' 查看状态。"
echo "日志查看: 'pm2 logs'"
echo "如需修改配置，请编辑 .env 文件后运行 'pm2 restart all'"
