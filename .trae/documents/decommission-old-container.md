# 下线旧容器、统一使用新容器的迁移计划

## 总体目标

1. 用极轻量 socat 代理替代旧版 `a-stock-app:8787`，n8n 工作流 **一个不动**
2. 下线旧版页面 `a-stock-pages-old:8780-8783`
3. 激活天时实验页面 `astro:8784`（代码一直有，从未启动过）
4. 服务器只保留 `a-stock-v2` + `pages_v2` + `n8n` + socat 代理

## 架构对比

```
旧：                      新：
app:8787 (Node+Py)        socat proxy:8787 ──→ a-stock-v2:8788 ✅
pages_old:8780-83         删除                 pages_v2:8789-91,8793 ✅
astro:未上线               pages_v2 新增 8784  ✅
```

---

## 步骤清单

### 第 1 步：修复 astro 页面的硬编码端口

`pages/astro/server.js` L24：`port: 8787` 应改为动态读取 `API_TARGET` 环境变量解析的端口。

改为：

```js
const API_PORT = new URL(API_BASE).port || 8787;
// ...
hostname: new URL(API_BASE).hostname,
port: API_PORT,
```

### 第 2 步：pages_entrypoint.sh 增加 astro 页面

在 [pages_entrypoint.sh L13](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/deploy_configs/pages_entrypoint.sh#L13) 行后加一行：

```bash
PORT=8784 API_TARGET=$API_TARGET node pages/astro/server.js &
```

### 第 3 步：修改 docker-compose.yml

**`services.app`** 替换为 socat 代理：

```yaml
  app:
    image: alpine/socat:latest
    container_name: a-stock-app
    restart: unless-stopped
    ports:
      - "8787:8787"
    command: ["tcp-listen:8787,fork,reuseaddr", "tcp-connect:a-stock-v2:8788"]
```

**`services.pages_v2`** 端口映射增加 8784：

```yaml
    ports:
      - "8784:8784"     # 新增：天时实验
      - "8789:8789"
      - "8790:8790"
      - "8791:8791"
      - "8793:8793"
```

**删除 `services.pages_old` 整块**。

**保留不动**：`app_v2`、`n8n`。

### 第 4 步：同步文件 + 部署

```bash
# 1. scp 修改后的文件到服务器
scp deploy_configs/docker-compose.yml stock-server:/opt/a-stock-monitor/deploy_configs/
scp deploy_configs/pages_entrypoint.sh stock-server:/opt/a-stock-monitor/deploy_configs/
scp pages/astro/server.js stock-server:/opt/a-stock-monitor/pages/astro/server.js

# 2. 重建 pages_v2 + 切换 socat 代理
ssh stock-server "
  cd /opt/a-stock-monitor

  echo '=== 下掉旧容器 ==='
  docker compose -f deploy_configs/docker-compose.yml down app pages_old pages_v2

  echo '=== 重建新版容器 ==='
  docker compose -f deploy_configs/docker-compose.yml up -d --build app_v2 pages_v2 app

  sleep 3
  echo '=== 最终端口状态 ==='
  docker ps --format '{{.Names}}: {{.Ports}}'
"
```

### 第 5 步：验证

```bash
ssh stock-server "
  echo '=== 1. 8787 代理 → 8788 ==='
  curl -s http://127.0.0.1:8787/api/snapshot/latest | python3 -c 'import sys,json; print(\"8787 ok\" if \"sentiment\" in json.load(sys.stdin) else \"8787 fail\")'

  echo '=== 2. 8788 直接 ==='
  curl -s http://127.0.0.1:8788/api/snapshot/latest | python3 -c 'import sys,json; print(\"8788 ok\" if \"sentiment\" in json.load(sys.stdin) else \"8788 fail\")'

  echo '=== 3. n8n 内网 app:8787 ==='
  docker exec a-stock-n8n wget -q -T5 -O- http://app:8787/api/snapshot/latest | python3 -c 'import sys,json; print(\"n8n active\" if \"sentiment\" in json.load(sys.stdin) else \"n8n fail\")'

  echo '=== 4. 页面端口 ==='
  for port in 8789 8790 8791 8784 8793; do
    echo -n \"$port: \"
    curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$port/ | grep -q 200 && echo ok || echo fail
  done

  echo '=== 5. astro 天时页面 ==='
  curl -s http://127.0.0.1:8784/ | grep -c 'astro\|天时\|八字'
"
```

### 第 6 步：清理

```bash
ssh stock-server "
  docker rm a-stock-pages-old 2>/dev/null
  docker image prune -a
"
```

### 第 7 步：n8n 手动验证

在 n8n Web UI（15679 端口）中：
1. 手动触发 `M1-Breadth-Fetch`，确认执行成功
2. 手动触发 `M1-AI-Intraday-Report`，确认 AI 播报正常
3. 检查数据文件 `breadth-cache.jsonl`、`snapshot.jsonl` 有最新数据

---

## 后续：Phase 2 可选 — 逐步改 URL 去代理

| 优先级 | 工作流 | 原因 |
|--------|--------|------|
| 先改 | M1-Breadth-Fetch + M1-AI-Intraday-Report | 数据面最直观 |
| 后改 | M1-A/B/C/D/E/F/G/H/Market 等 | 后台采集，延迟改不影响 |

全部改为 8788 后，从 docker-compose 中删除 socat 代理即可。

---

## 风险评估

| 风险 | 缓解 |
|------|------|
| socat 镜像拉取失败 | 备选 `alpine:latest` + `apk add socat` 自建 |
| astro 页面跨域或 API 不通 | 修复后 API_BASE 从 env 读取，与 overview/etf/trade 一致 |
| pages_v2 rebuild 期间页面不可用 | 交易时间外操作（午休/收盘后） |

## 回滚

```bash
# 恢复 docker-compose.yml 中的 app 和 pages_old 完整配置
cd /opt/a-stock-monitor
git checkout -- deploy_configs/docker-compose.yml deploy_configs/pages_entrypoint.sh
docker compose -f deploy_configs/docker-compose.yml up -d --build app pages_old
```
