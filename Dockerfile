# 使用官方 Python 3.9 轻量版作为基础镜像 (自带 gcc 等基础工具)
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 设置时区为上海
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 换源加速 (阿里云源)
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list

# 安装系统依赖 + Node.js (需要支持 ?? / ?. 等语法，避免旧版 node 报错)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libffi-dev \
    curl \
    ca-certificates \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# 升级 pip
RUN pip install --no-cache-dir --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/

# 复制依赖文件
COPY requirements.txt .
COPY package.json .

# 安装 Python 依赖 (指定源加速)
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 安装 Node 依赖 (使用淘宝源)
RUN npm config set registry https://registry.npmmirror.com && \
    npm install --production

# 复制项目代码
COPY . .

# 暴露端口
EXPOSE 8787

# 启动命令 (仅启动Node.js服务)
CMD node server.js
