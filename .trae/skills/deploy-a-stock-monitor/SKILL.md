---
name: "deploy-a-stock-monitor"
description: "用方案A（SCP/RSYNC）把本地代码同步到服务器并重建/重启Docker容器。用户说“用A发布/同步到服务器/服务器git拉不动”时调用。"
---

# A-Stock-Monitor 方案A发布（无 Git Pull）

目标：在服务器无法 `git pull`（GitHub 访问失败）时，把本地仓库代码同步到服务器 `/opt/a-stock-monitor`，然后执行 `bash install_server.sh` 完成镜像重建与容器重启。

## 适用场景

- 服务器报 `fatal: unable to access ... Empty reply from server`
- 需要让前端/后端改动立刻在服务器生效
- 运维手册约定目录为 `/opt/a-stock-monitor`，容器名 `a-stock-monitor`

## 前置条件（需要向用户确认/收集）

- 服务器 SSH 信息：`host`、`user`、可选 `ssh key` 路径
- 服务器代码目录：默认 `/opt/a-stock-monitor`
- 是否允许重建镜像并重启容器（会短暂中断服务）
- 端口策略
  - 默认 `install_server.sh` 固定映射 `8787:8787`
  - 如需 `8788`，需要在服务器修改 `install_server.sh` 的 `PORT=8787`，或手动 `docker run -p 8788:8787 ...`

## 安全约束（必须遵守）

- 不上传 `.env`（避免覆盖服务器密钥）
- 不上传 `data/`（避免覆盖线上数据）
- 不上传 `.git/`、`node_modules/`、`__pycache__/` 等无关目录

## 执行流程（给用户可直接复制的命令）

将下列变量替换为用户真实值：

- `HOST=你的服务器IP或域名`
- `USER=root或其他用户`
- `REMOTE_DIR=/opt/a-stock-monitor`

### 1) 确认本地处于项目根目录

```bash
pwd
ls
```

### 2) 建立服务器目录

```bash
ssh ${USER}@${HOST} "mkdir -p ${REMOTE_DIR}"
```

如需指定私钥：

```bash
ssh -i /path/to/key ${USER}@${HOST} "mkdir -p ${REMOTE_DIR}"
```

### 3) 同步代码到服务器（推荐 rsync）

```bash
rsync -avz \
  --exclude '.git/' \
  --exclude 'data/' \
  --exclude '.env' \
  --exclude 'node_modules/' \
  --exclude '**/__pycache__/' \
  --exclude '**/*.pyc' \
  ./ \
  ${USER}@${HOST}:${REMOTE_DIR}/
```

如需指定私钥：

```bash
rsync -avz -e "ssh -i /path/to/key" \
  --exclude '.git/' \
  --exclude 'data/' \
  --exclude '.env' \
  --exclude 'node_modules/' \
  --exclude '**/__pycache__/' \
  --exclude '**/*.pyc' \
  ./ \
  ${USER}@${HOST}:${REMOTE_DIR}/
```

### 4) 服务器端重建镜像并重启容器

```bash
ssh ${USER}@${HOST} "cd ${REMOTE_DIR} && bash install_server.sh"
```

### 5) 验证

```bash
ssh ${USER}@${HOST} "docker ps -a | grep a-stock-monitor || true"
ssh ${USER}@${HOST} "docker logs -f a-stock-monitor --tail 120"
```

健康检查（如容器内或宿主机可 curl）：

```bash
ssh ${USER}@${HOST} "curl -s http://127.0.0.1:8787/health || true"
```

## 常见失败与处理

- `rsync: command not found`
  - 在服务器安装 rsync，或改用 scp（体积大但能用）
- `Permission denied (publickey)`
  - 确认 SSH key、用户、服务器 `sshd` 配置
- 启动后页面仍是旧版本
  - 确认 `install_server.sh` 已运行完成且容器为最新启动时间
  - 确认 Nginx/浏览器缓存，必要时硬刷新

## 助手在本地可做的自动化（当用户允许时）

- 自动列出本次变更文件清单（用于最小化同步范围）
- 自动生成 rsync/ssh 命令（带正确排除项）
- 同步后提示用户在服务器执行的验证命令与预期输出
