# A-Stock-Monitor 服务器部署与运维手册

本文档描述了 `a-stock-monitor` 项目在生产环境（阿里云 CentOS）的部署架构、运维流程及迭代指南。供后续开发 Agent 及运维人员参考。

## 1. 部署架构

### 核心组件
*   **运行环境**: Docker (Python 3.9 Slim)
*   **Web 服务器**: Nginx (宿主机) -> 反向代理 -> Docker 容器 (端口 8787)
*   **应用架构**:
    *   **后端 API**: Node.js (Express, `server.js`)
    *   **数据层**: Python (`fetch_sector_data.py`, `fetch_news.py`) 定时抓取，生成 JSON/CSV 文件
    *   **存储**: 本地文件系统 (`/data` 目录挂载到容器外)

### 目录结构 (服务器 `/opt/a-stock-monitor`)
```bash
/opt/a-stock-monitor/
├── .env                # 环境变量 (API Key 等)
├── data/               # [重要] 数据持久化目录 (挂载到容器内 /app/data)
├── lib/                # Python 共享库 (quant, utils)
├── Dockerfile          # 镜像构建文件
├── install_server.sh   # 一键部署/更新脚本
├── server.js           # Node.js 主服务
└── fetch_*.py          # Python 数据脚本
```

### 网络拓扑
*   **公网访问**: `http://astock.askyi.com.cn` (端口 80) -> Nginx
*   **Nginx 转发**: `proxy_pass http://172.17.0.1:8787` (Docker 网桥 IP)
*   **容器内部**: Node.js 监听 8787，Python 脚本后台运行

---

## 2. 运维操作指南

### 查看服务状态
```bash
# 查看容器运行状态
docker ps

# 查看实时日志 (Node.js + Python 输出)
docker logs -f a-stock-monitor --tail 100

# 查看 Nginx 状态
systemctl status nginx
```

### 手动触发数据更新
如果需要立即刷新数据（而不等待定时任务），可进入容器执行：
```bash
# 进入容器
docker exec -it a-stock-monitor /bin/bash

# 手动运行 Python 脚本
python fetch_sector_data.py rank          # 更新排行
python fetch_sector_data.py history_dynamic "半导体,..." 20  # 更新历史
```

### 修改环境变量
1.  编辑宿主机文件：`vim .env`
2.  重启容器生效：`docker restart a-stock-monitor`

---

## 3. 版本迭代与发布流程

### 场景 A：修改了代码 (Python/JS/HTML)
**流程**：本地开发 -> Git Push -> 服务器 Pull -> **重建镜像**

1.  **本地 (Local)**:
    ```bash
    git add .
    git commit -m "feat: update logic"
    git push
    ```

2.  **服务器 (Server)**:
    ```bash
    cd /opt/a-stock-monitor
    git pull
    
    # 执行一键更新脚本 (会自动构建镜像并重启容器)
    bash install_server.sh
    ```

### 场景 B：仅修改了配置 (Nginx)
**流程**：直接在服务器修改 -> 重载 Nginx
```bash
vim /etc/nginx/conf.d/astock.conf
nginx -s reload
```

### 场景 C：依赖变更 (requirements.txt / package.json)
**流程**：同场景 A。`install_server.sh` 会自动检测 Dockerfile 变化并重新 `pip install / npm install`。

---

## 4. 常见问题排查 (Troubleshooting)

| 现象 | 可能原因 | 检查/修复命令 |
| :--- | :--- | :--- |
| **502 Bad Gateway** | 容器挂了 / 防火墙拦截 | 1. `docker ps -a` 确认容器存活<br>2. `docker logs` 看报错<br>3. `curl 172.17.0.1:8787` 测试内网连通性 |
| **页面无数据/空白** | Python 脚本报错 / 缓存为空 | `docker logs` 查看是否有 Python Traceback<br>检查 `/data` 目录是否有文件 |
| **Git Pull 失败** | 网络连接 GitHub 超时 | 多试几次，或手动上传修改的文件 |
| **部署后代码未生效** | 忘记重建镜像 | 必须运行 `bash install_server.sh` 或手动 `docker build` |

---

## 5. 关键配置备份
*   **Nginx 配置**: `/etc/nginx/conf.d/astock.conf`
*   **环境变量**: `/opt/a-stock-monitor/.env`
*   **数据**: `/opt/a-stock-monitor/data/` (建议定期备份此目录)
