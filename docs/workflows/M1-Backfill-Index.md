# 工作流登记卡：M1-Backfill-Index

- **用途一句话**: 每天盘后（18:00 / 09:00），通过权威接口兜底验证或回补大盘指数历史日线，确保数据 100% 精确。
- **数据源 (Provider/Dataset)**: 
  - `providerId`: `hybrid(local_legacy + akshare.tx)` (本地旧数据优先，缺失或偏差用 `akshare` 腾讯日线接口)
  - `datasetId`: `index_daily` (宽基指数日线)
- **计算方式 (公式/口径)**:
  - 读取现有的 `data/m1/index/<symbol>/daily.jsonl`，检查最后一天是否为预期的交易日（如今天）。
  - 若有缺失，请求官方日线接口，按 `(今日close - 昨日close) / 昨日close * 100` 重算 `pct`。
  - 过滤异常的 `amount`、`volume` 列。
- **产物路径**: `data/m1/index/<symbol>/daily.jsonl` (含同名 `.meta.json`)
- **验收标准**:
  - 执行后，四大宽基指数的日线文件包含到今日的连续、准确数据。
  - 缺失天数（如 4-16）成功从接口拉回并追加。
  - `.meta.json` 更新 `providerId`。
- **人类摘要示例**:
  ```text
  M1-Backfill ✅ day=2026-04-17 symbol=sh000001
  [接口拉取] 成功获取增量日线数据并更新至: 2026-04-17
  ```