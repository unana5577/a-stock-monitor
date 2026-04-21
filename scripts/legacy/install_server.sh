#!/bin/bash

# A-Stock-Monitor Server Installation Script (Docker Version)
# 自动检测 Docker 环境并一键部署

set -e

APP_NAME="a-stock-monitor"
PORT=8787

echo "=== 开始 Docker 部署 $APP_NAME ==="

# 1. 检查/安装 Docker
if ! command -v docker &> /dev/null; then
    echo "[1/3] 未检测到 Docker，正在自动安装..."
    if command -v curl &> /dev/null; then
        curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
    elif command -v wget &> /dev/null; then
        wget -qO- https://get.docker.com | bash -s docker --mirror Aliyun
    else
        echo "错误：请先安装 curl 或 wget"
        exit 1
    fi
    # 启动 Docker
    sudo systemctl start docker
    sudo systemctl enable docker
    echo "Docker 安装完成。"
else
    echo "[1/3] Docker 已安装。"
fi

# 2. 检查 .env
if [ ! -f ".env" ]; then
    echo "检测到缺少 .env 文件，从 .env.example 复制..."
    cp .env.example .env
    echo "警告：请务必编辑 .env 文件填入 API Key！"
fi

# 3. 构建并启动容器
echo "[2/3] 构建 Docker 镜像 (可能需要几分钟)..."
# 停止旧容器
if docker ps -a | grep -q "$APP_NAME"; then
    echo "停止旧容器..."
    docker stop $APP_NAME
    docker rm $APP_NAME
fi

# 构建
docker build -t $APP_NAME .

echo "[3/3] 启动容器..."
# 运行容器，映射端口，挂载 .env 和 data 目录(保证数据持久化)
docker run -d \
  --name $APP_NAME \
  --restart always \
  -p $PORT:8787 \
  -v "$PWD/.env:/app/.env" \
  -v "$PWD/data:/app/data" \
  $APP_NAME

echo "=== 部署完成！ ==="
echo "服务状态: $(docker ps -f name=$APP_NAME --format '{{.Status}}')"
echo "查看日志: docker logs -f $APP_NAME"
echo "访问地址: http://<服务器IP>:$PORT"
