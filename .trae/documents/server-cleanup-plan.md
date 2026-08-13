# 服务器文件清理计划

## 决策总结

| 类别 | 决策 |
|------|------|
| A 类（垃圾抽屉/__pycache__/.DS_Store） | 删 |
| B 类（根目录 Python 复本） | 删（treasolo/ 版为正确版本） |
| C 类（n8n JSON 复本） | **先上线正确工作流 → 验证 → 再删磁盘文件** |
| D 类（废弃脚本/配置） | 删 |
| E1 `server.js` | **留**（历史参考，改 Dockerfile CMD） |
| E2 `m1_sector_lifecycle.py` | 删（treasolo 版正确） |
| E3 `m1_files_audit.py` | 删（treasolo 版正确） |
| E4 `data_maintenance.py` | 删（旧版遗留，已被回补管线替代） |
| E5 `波段策略建议.md` | **删** |

---

## 步骤清单

### 第 1 步：清理 A + B + D + E2/E3/E4/E5（安全删除）

这些文件经过逐一排查，确认无引用或引用路径指向 treasolo/。

**服务器上执行**：
```bash
ssh stock-server "
cd /opt/a-stock-monitor

# A类
rm -rf 待清理垃圾文件/
rm -rf data.bad_20260506_105327/
rm -rf __pycache__/ data/__pycache__/
find . -name '.DS_Store' -delete
find . -name '__pycache__' -type d -not -path '*/node_modules/*' -exec rm -rf {} + 2>/dev/null

# B类：根目录 Python 复本（6个）
rm -f m1_backfill.py m1_minute_fetch_etf.py m1_lifecycle.py
rm -f m1_etf_intraday_features.py m1_ai_aggregator.py cleanup_minute_files.py

# D类：废弃配置
rm -f verify_v2.sh start_dual.sh ecosystem.config.js tsconfig.json global.d.ts
rm -f sector-proxy.json pages_entrypoint.sh pages_entrypoint_old.sh

# E2/E3/E4/E5
rm -f m1_sector_lifecycle.py m1_files_audit.py data_maintenance.py
rm -f 波段策略建议.md
echo 'Cleanup done'
"
```

### 第 2 步：本地同步删除并提交

这些文件在 git 中可能被 tracked，需要 `git rm`：
```bash
cd /Users/una5577/Documents/trae_projects/a-stock-monitor
# 删除本地对应文件并 git rm
```

### 第 3 步：Dockerfile 修改 — 默认 CMD 从旧 server.js 改为新 server/server.js

```diff
- CMD ["node", "server.js"]
+ CMD ["node", "server/server.js"]
```

这个改动是防御性的：即使将来有人 `docker run` 不传 command，也不会意外启动旧的 `server.js`。

### 第 4 步：C 类 — n8n 工作流上线（核心步骤）

n8n 数据库当前实际状态（7/29 排查）：

| 工作流 | 现状 | 需要做什么 |
|--------|------|-----------|
| M1-C | 硬编码 12 只 ETF + `app:8787` | 在 n8n 中导入 `n8n-workflows/M1-C-ETF-Minute-Fetch.json`（动态版 + 8788），停用旧版 |
| M1-D | **2 个活跃副本**（一个 8787 旧版、一个 8788 新版） | 停用 8787 旧版副本，保留 8788 新版 |
| M1-E | `app:8787` 旧版，3 个 HTTP 节点 | 导入 `n8n-workflows/M1-E-Backfill-Universal.json`（8788 版），停用旧版 |
| M1-Z | 只在 n8n 里有，磁盘文件在根目录 | 无需改动（8787 通过代理已通），但要把 JSON 移到 `n8n-workflows/` |

**第 4.1 步**：在 n8n Web UI（15679 端口）中操作
1. 停用旧 M1-C、M1-D（8787 副本）、M1-E
2. 导入 `n8n-workflows/M1-C-ETF-Minute-Fetch.json`，激活
3. 导入 `n8n-workflows/M1-E-Backfill-Universal.json`，激活
4. 停用 M1-D 的 8787 旧副本（保留 8788 新版）
5. 手动触发 M1-C + M1-E 各一次，确认执行成功

**第 4.2 步**：验证
```bash
ssh stock-server "
# 确认 ETF 列表返回 16 只（包含 sh588000/sz159995）
curl -s http://127.0.0.1:8788/api/sector/manage | python3 -c 'import sys,json; d=json.load(sys.stdin); etfs=d.get(\"etfs\",{}); print(\"ETF count:\", len([k for k,v in etfs.items() if not v.get(\"hidden\")]))'

# 确认 M1-C 能正常拉取分时
tail -3 /opt/a-stock-monitor/data/etf/minute/sh588000/2026-07-29.jsonl
"
```

### 第 5 步：C 类 — 验证通过后删除根目录 JSON

```bash
ssh stock-server "cd /opt/a-stock-monitor && rm -f M1-AI-Intraday-Report.json M1-C-ETF-Minute-Fetch.json M1-D-ETF-Minute2Daily.json M1-E-Backfill-Universal.json M1-Z-Audit-Files.json"
```

同时把 M1-Z-Audit-Files.json 从 n8n 导出到 `n8n-workflows/` 目录（保持完整）。

### 第 6 步：最终验证

```bash
ssh stock-server "
cd /opt/a-stock-monitor
echo '=== 根目录文件数量 ==='
ls -1 *.py *.json *.sh *.md 2>/dev/null | wc -l
echo '(应该只剩 node_modules, package.json 等必要文件)'
"
```

---

## 风险

| 步骤 | 风险 | 缓解 |
|------|------|------|
| 第 1 步删 B 类 | 某脚本通过旧 server.js 直接 execFile 调用根目录文件 | 已确认新 server 映射全部指向 treasolo/ |
| 第 4 步 n8n 操作 | 导入新工作流后 M1-C 动态清单 API 不响应 | 手动触发验证；失败则回退重新激活旧工作流 |
| 第 5 步删 JSON | M1-Z 磁盘文件消失 | 已提前从 n8n 导出到 n8n-workflows/ |

## 回滚

如果 M1-C/M1-E 新工作流出问题：
- n8n UI 中停用新工作流，重新激活旧工作流（旧版本仍在数据库中，只是被停用）
- 磁盘文件删了就没了，但 n8n 不看磁盘文件，不影响运行
