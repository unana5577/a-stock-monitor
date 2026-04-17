# 失败记忆库 (Known Issues)

> **原则**: Append-only (只增不减)，每次排查出有价值的故障，必须记录 Symptom、Root cause、Fix/Regression。

## 2026-04-17: 东财接口被封导致大盘金额数量级错乱

- **Symptom**: `data/index_daily/index_000001.jsonl` 中，最近几天的 `amount` (成交额) 字段从原本的几千亿变成了几千万，且 4-16 数据缺失。
- **Root cause**: 历史代码 (`scripts/market_snapshot_sina.py` 或同类旧脚本) 强依赖东方财富的某个未授权接口。近期该接口对爬虫进行了封禁或返回假数据，导致旧日线文件写入了极其荒谬的数字。
- **Fix**:
  - M1 阶段彻底放弃 `index_000001.jsonl` 作为主文件，将其降级为只读的 Legacy 历史库。
  - 新增 `m1_backfill_index.py` 脚本，从 `akshare` 腾讯日线接口拉取准确数据。
  - 指数的日线数据中**强制剔除 amount 列**，pct 由 close 自行重算，落盘至隔离的新目录 `data/m1/index/sh000001/daily.jsonl`。
- **Regression**: 以后任何指数日线的计算，都不允许使用不可靠接口的 amount 字段；全市场的真实总成交额由 M0-A 独立计算并提供。