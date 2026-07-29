# deploy-a-stock-monitor

**Description:** 用方案A（SCP/RSYNC）把本地代码同步到服务器并重建/重启Docker容器。用户说"用A发布/同步到服务器/服务器git拉不动"时调用。

## 适用场景

- 服务器报 `fatal: unable to access ... Empty reply from server`
- 需要让前端/后端改动立刻在服务器生效
- 运维手册约定目录为 `/opt/a-stock-monitor`

## 前置条件

- 服务器 SSH 信息：`stock-server`（已配置在 `~/.ssh/config`）
- 服务器代码目录：`/opt/a-stock-monitor`
- Docker Compose 文件：`deploy_configs/docker-compose.yml`

## 安全约束

- 不上传 `.env`
- 不上传 `data/`
- 不上传 `.git/`、`node_modules/`、`__pycache__/` 等

## 容器架构（5个服务）

| Service | Container Name | Ports | 用途 |
|---------|---------------|-------|------|
| app | a-stock-app | 8787 | 线上主力后端 (server.js) |
| app_v2 | a-stock-v2 | 8788 | 新骨架后端 (server/server.js) |
| pages_v2 | a-stock-pages-v2 | 8789-8793 | 新Shell页面 |
| pages_old | a-stock-pages-old | 8780-8783 | 旧Shell页面 |
| n8n | a-stock-n8n | 15679 | 工作流调度 |

## 文件变更 → 容器矩阵（自动匹配）

| 变更文件路径模式 | 需要重建的 services |
|-----------------|-------------------|
| `server.js` | `app` |
| `server/api/*.js` | `app_v2` |
| `server/*.js` (含 server/server.js) | `app_v2` |
| `treasolo/**/*.py` | `app` + `app_v2` |
| `波段策略/**/*.py` | `app` + `app_v2` |
| `pages/**/*` | `pages_v2` + `pages_old` |
| `deploy_configs/**/*` | 全部 (`app` `app_v2` `pages_v2` `pages_old`) |
| `.env` | 无需重建（volume 挂载或 env_file） |
| `data/**/*` | 无需重建（volume 挂载） |

## 执行流程

### 步骤 1：确认变更文件

```bash
git diff --name-only HEAD~1
```

### 步骤 2：根据变更文件确定受影响容器

对照容器矩阵，列出需要重建的 services，用逗号分隔。

例如只改了 `pages/etf/index.html` → `pages_v2,pages_old`
改了 `server.js` + `treasolo/m1_lifecycle.py` → `app,app_v2`
改了 `deploy_configs/docker-compose.yml` → `app,app_v2,pages_v2,pages_old`

### 步骤 3：rsync 变更文件到服务器

```bash
rsync -avz \
  <changed_file1> \
  <changed_file2> \
  ... \
  stock-server:/opt/a-stock-monitor/<对应路径>/
```

### 步骤 4：服务器端重建并重启受影响容器

```bash
ssh stock-server "
  docker stop <container1> <container2> 2>/dev/null;
  docker rm <container1> <container2> 2>/dev/null;
  cd /opt/a-stock-monitor && \
  docker compose -f deploy_configs/docker-compose.yml build --no-cache <service1> <service2> && \
  docker compose -f deploy_configs/docker-compose.yml up -d <service1> <service2> && \
  sleep 5
"
```

### 步骤 5：验证

API 验证（app/app_v2）：
```bash
ssh stock-server "curl -s --max-time 5 http://127.0.0.1:8787/m1 | grep -o '<title>[^<]*</title>'"
ssh stock-server "curl -s --max-time 5 http://127.0.0.1:8788/api/m1/data/overview | python3 -c 'import sys,json; print(json.load(sys.stdin).get(\"ok\"))'"
```

页面验证（pages）：
```bash
ssh stock-server "curl -s --max-time 3 http://127.0.0.1:8793/ | head -c 200"
```

容器状态：
```bash
ssh stock-server "docker ps --format '{{.Names}} {{.Status}}' | grep a-stock"
```

### 步骤 6：Git 提交

```bash
git add <changed_files>
git commit -m "<commit_message>"
git push
```

## 常见失败

- `docker compose build` 超时 → 等待 pip install 完成（首次构建较慢）
- 页面仍是旧版 → 确认 pages 容器已重建并 up，浏览器硬刷新
- app_v2 报路径错误 → 检查 `server/api/` 文件中 `path.join(__dirname, 'data/...')` 是否缺少 `'..', '..'`
- n8n 工作流报 400 → 确认 `server.js` 和 `server/api/overview.js` 的 `/api/m1/run` 分支都包含对应脚本名
- pct 不更新 → lifecycle 代码改了需要重建 `app` 容器（不是 volume），然后 n8n 重新触发
