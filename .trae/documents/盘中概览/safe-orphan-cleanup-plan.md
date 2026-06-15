# 安全落盘清理方案 — 分阶段零风险推进

## 核心原则

> **不在任何阶段直接改线上的旧 8787。每次改动只影响一个环境，验证通过才进入下一阶段。**

---

## 阶段 1：只改新骨架（8788），零风险

### 操作

修改 `server/context.js` + `server/api/shared.js`（只在这两个文件）：

1. `loadMinuteSeries()` 改从结构化目录读
2. 删除 `minuteFilePath()` / `findLatestMinuteFile()` / `prevCloseFromMinuteFile()` 三个函数
3. 删除 `/api/minute/<code>` 路由块

### 为什么零风险

- 新骨架跑在 8788，**没有 n8n 工作流调它**
- 没有前端页面直接调它
- 改错了大不了 `git checkout server/` 回滚

### 验证

```bash
node server/server.js &
curl http://127.0.0.1:8788/health
curl http://127.0.0.1:8788/api/snapshot
curl http://127.0.0.1:8788/api/m1/data/overview
curl http://127.0.0.1:8788/api/m1/data/minute?symbol=sh000001
```

**此阶段不 touch 旧 server.js、不 touch 数据文件、不 touch 服务器。**

---

## 阶段 2：本地全量模拟 — 用线上数据跑本地全套

### 事前准备

```bash
# rsync 当天数据到本地（已有 SSH 密钥，一句就能执行）
rsync -avz stock-server:/opt/a-stock-monitor/data/ ./data/ --exclude='runtime/'
```

### 操作

1. 本地同时启动 8787（旧 server.js，改过）和 8788（新骨架，改过）
2. 跑同样的 curl 测试脚本，对比两个端口返回的 JSON 是否一致
3. 重点是 `/api/snapshot`, `/api/panic`, `/api/m1/data/overview`, `/api/m1/data/breadth` — 这些依赖 archive / loadMinuteSeries 的路由

### 验证标准

- 两个端口返回的字段结构一致
- 数值（价格、成交额、涨跌家数）在合理误差范围内
- 没有任何端口崩溃

### 此阶段不改服务器。

---

## 阶段 3：改旧 server.js — 先备份一把

### 操作

```bash
# 在服务器上备份一份当前运行中的 server.js
ssh stock-server "cp /opt/a-stock-monitor/server.js /opt/a-stock-monitor/server.js.bak.$(date +%Y%m%d_%H%M%S)"
```

然后再通过 rsync 把本地改过的 `server.js` 推到服务器：

```bash
rsync -avz server.js stock-server:/opt/a-stock-monitor/server.js
```

### 回滚方案

如果出问题：

```bash
# 秒级回滚：切回备份文件，重启容器
ssh stock-server "cp /opt/a-stock-monitor/server.js.bak.xxx /opt/a-stock-monitor/server.js && cd /opt/a-stock-monitor && bash install_server.sh"
```

### 验证

重启后立即 curl 关键路由确认 200。

---

## 阶段 4：清理残留在线的散落文件

在阶段 3 上线并确认稳定后（至少一个完整交易日），手动执行：

```bash
ssh stock-server "cd /opt/a-stock-monitor && python3 treasolo/cleanup_minute_files.py --keep-days 3 --apply"
```

此步可安全执行因为 cleanup 脚本只删 `data/minute-*.jsonl` 等已被证明无人消费的文件。

---

## 总时间线

| 阶段 | 影响环境 | 时间 | 风险 |
|------|---------|------|------|
| 1: 改新骨架 | 本地 8788 | 30 分钟 | 零（8788 未上线） |
| 2: 本地对比验证 | 本地 8787+8788 | 15 分钟 | 零 |
| 3: 推旧 server.js | 服务器 8787 | 5 分钟（+回滚随时） | 低（有热备份） |
| 4: 清理散落文件 | 服务器 data/ | 1 分钟 | 零（cleanup dry-run 先确认） |

**不需要你同时做任何事情，三个阶段我可以独立推进，每次结束给你一份验证报告。**
