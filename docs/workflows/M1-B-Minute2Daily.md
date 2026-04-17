# 工作流登记卡：M1-B-Minute2Daily

- **用途一句话**: 每天盘后（15:01），用分时文件最后一条价格合成当天的最终日线，提供极致实时的大盘走势。
- **数据源 (Provider/Dataset)**: 
  - `providerId`: `minute_to_daily` (本地合成，无外部接口依赖)
  - `datasetId`: `index_daily` (宽基指数日线)
- **计算方式 (公式/口径)**:
  - 提取 `data/market/minute/<symbol>/<day>.jsonl` 的最后一条记录（通常是 15:00）。
  - 提取 `data/m1/index/<symbol>/daily.jsonl` 的最后一条记录作为昨收 (`prev_close`)。
  - `pct = (current_close - prev_close) / prev_close * 100`，保留两位小数。
- **产物路径**: `data/m1/index/<symbol>/daily.jsonl` (含同名 `.meta.json`)
- **验收标准**:
  - 15:01 执行后，四大宽基指数的日线文件尾部成功追加当日数据。
  - `.meta.json` 中的 `endDate` 为今日，`providerId` 为 `minute_to_daily`。
- **人类摘要示例**:
  ```text
  M1-B ✅ day=2026-04-17 symbol=sh000001
  合并生成了 2026-04-17 的日线: close=4051.43, pct=-0.1%
  ```