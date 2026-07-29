---
name: "download-data"
description: "从股票监控服务器下载数据到本地指定文件夹，用于回测分析。保持服务器 data/ 目录结构。Invoke when user asks to download data, download market data, download ETF data, or download for backtesting."
---

# 数据下载 Skill

## 触发条件
当用户提到"下载数据"、"下载 ETF 数据"、"下载大盘数据"、"下载回测数据"、"download data" 时调用。

## 下载内容

保持和服务器 `data/` 目录一致的结构：

```
<目标文件夹>/
├── index/daily/       # 大盘指数日线（上证/深证/科创/沪深300/中证1000/创业板）
├── etf/daily/         # ETF 日线
├── etf/minute/        # ETF 分时（按代码分目录）
├── etf/meta/          # ETF 分类元数据 (sector-proxy.json)
├── market/            # 市场数据（breadth/snapshot/ai）
└── market/minute/     # 市场分时（breadth-cache.jsonl）
```

## 执行步骤

1. 确认目标文件夹（默认 `<项目根目录>/online_debug_data`）
2. SSH 到服务器 `stock-server`（139.224.251.15）
3. 在服务器上打包所有 `data/` 目录（排除 `node_modules/` 等非数据文件）
4. SCP 下载到本地目标文件夹
5. 解压保持目录结构

## 命令模板

```bash
# 1. 服务器端打包
ssh stock-server "cd /opt/a-stock-monitor && tar czf /tmp/stock_data.tar.gz \
  data/index/daily/ \
  data/etf/daily/ \
  data/etf/minute/ \
  data/etf/meta/ \
  data/sector-proxy.json \
  data/market/ \
  data/market/minute/"

# 2. 下载
scp stock-server:/tmp/stock_data.tar.gz /tmp/

# 3. 解压到目标文件夹
mkdir -p <目标文件夹>
tar xzf /tmp/stock_data.tar.gz -C <目标文件夹> --strip-components=1

# 4. 列出结构
find <目标文件夹> -type f | head -30
```

## 注意事项
- 分时数据文件较多，打包可能需要 10-30 秒
- 下载完成后清理服务器临时文件：`ssh stock-server "rm -f /tmp/stock_data.tar.gz"`
- 如果只需部分数据（如仅 ETF 日线），调整 tar 路径即可
