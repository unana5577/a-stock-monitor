# M0+M1 规格草案（CLI Runner + 可观测性 + 时间口径收口）

适用范围：a-stock-monitor（仅 A 股，全部日期/交易时段按北京时间 Asia/Shanghai）

## 0. 本轮目标

### M0（平台止血）

把系统变成“可运行、可定位、可回退”：

- 单入口 CLI Runner：外部调度（cron/n8n/手动）只能调用一个入口
- Run Journal（运行账本）落盘：每次运行可追溯（跑了什么、卡在哪、产物在哪、用了哪个源、数据截至 asOf）
- 写入可靠：原子写入 + 产物分层，避免半截文件污染与不可回滚

### M1（时间/口径收口）

把“日期/交易日推导”彻底收口到北京时间逻辑，清理 UTC 推导残留，并统一 asOf 输出。

## 1. 非目标（本轮不做）

- 不做 n8n 全面替代 cron（M2 之后再评估）
- 不做“接口注册表/主备路由”全面重构（M2 再做；M0/M1 只做最小防呆与可追溯）
- 不做策略/指标大改、商业化拆分、止盈止损回测（暂缓池）

## 2. 术语定义

- Runner（单入口执行器）：把散落脚本/任务收口到一个 CLI 命令入口，统一参数与错误返回。
- Step（步骤）：Runner 的最小可观测单元；每步必须可重复执行且有明确产物。
- Run Journal（运行账本）：每次 run 的落盘状态，记录每个 step 的 start/end/status/error/outputs。
- asOf（数据截至标识）：数据真实覆盖到哪个交易日/时间点；发生回退或不完整时必须显式提供。
- 原子写入：先写入临时文件，通过校验后 rename 替换正式文件，保证读者永远读到“完整文件”。

## 3. Runner CLI 形态（v0）

### 3.1 命令行接口（拟定）

后续实现为：

```bash
python3 -m treasolo.runner run --plan m0m1 [--day YYYY-MM-DD] [--steps step1,step2] [--force] [--dry-run]
```

约束：

- day 未提供：使用“最近交易日”（北京时间）作为 day
- steps 未提供：按计划默认 step 顺序执行
- dry-run：只生成将执行的 step 清单与目标产物路径，不写文件
- force：允许覆盖/重算衍生产物（原始采集层默认不覆盖）

### 3.2 Step 列表（拟定，M0/M1 必含）

最终以实现时对齐为准，本轮先锁定名称与职责边界：

- resolve_day：计算 effective day/asOf（北京时间交易日序列，不得 UTC 推导）
- snapshot_refresh（可选）：触发一次快照/分时关键文件刷新（若当前链路需要）
- market_amount_daily_backfill（可选）：聚合/回补市场成交额日线（用于概览口径）
- warmup（可选）：预热关键缓存（避免前端第一次请求超慢/返回空）
- qa_basic：基础自检（交易日、文件存在性、字段完整性、asOf 标注）
- report：汇总输出（本次 runId、各 step 产物路径、关键指标、失败原因）

备注：这些 step 允许内部复用现有脚本（data_maintenance.py、scripts/*.py、server.js 内部函数调用等），但外部只看 step。

### 3.3 默认执行链（v1，确认版）

不带 `--steps` 时，默认只跑“观测闭环”，不改业务数据：

- resolve_day → qa_basic → report

说明：

- 任何会写入业务数据的 step（例如成交额日汇总、日线维护、分钟维护、warmup）都不进入默认链，必须显式 `--steps` 选择，并且每次执行前走“单任务确认模板”。

### 3.4 关键数据文件（v1，确认版）

qa_basic 的第一批“关键文件”仅做检查与标注，不负责修复：

- data/etf_daily/*.jsonl：ETF 日线历史（目前口径正确，用作分时 pct 昨收与回测/对账基础）
- data/index_daily/*.jsonl：指数日线历史（上证/深证/创业板/科创等，用于概览与成交额日汇总的基准序列）
- data/archive-YYYYMMDD.jsonl：快照归档（由服务端按交易日追加写入；用于回放/兜底/AI 输入的一部分数据来源）
- data/market/market-amount-daily.jsonl：市场成交额“按日汇总”序列（目前已知可能有错，qa_basic 需要能识别并标注为 degraded，不阻塞 M0/M1 默认链）

## 4. Run Journal（运行账本）规范（v0）

### 4.1 落盘位置

```text
data/runs/<day>/<runId>.json
```

### 4.1.1 保留策略（确认版）

- 默认保留 30 天：以 `startedAt` 为准裁剪
- 裁剪动作不进入 M0 默认链，作为可选维护 step（后续实现）

### 4.2 JSON Schema（v0）

```json
{
  "runId": "20260415-153000-<rand>",
  "plan": "m0m1",
  "day": "YYYY-MM-DD",
  "asOf": "YYYY-MM-DD",
  "timezone": "Asia/Shanghai",
  "trigger": { "type": "manual|cron|n8n", "source": "string" },
  "startedAt": "2026-04-15T15:30:00+08:00",
  "endedAt": "2026-04-15T15:30:10+08:00",
  "status": "success|failed|partial",
  "steps": [
    {
      "name": "resolve_day",
      "startedAt": "2026-04-15T15:30:00+08:00",
      "endedAt": "2026-04-15T15:30:00+08:00",
      "status": "success|failed|skipped",
      "inputs": { "dayArg": null, "force": false, "dryRun": false },
      "warnings": [
        {
          "code": "ARCHIVE_SUSPECT",
          "severity": "degraded",
          "message": "archive存在可疑点位或异常值（不阻塞默认链）",
          "paths": ["data/archive-YYYYMMDD.jsonl"]
        }
      ],
      "providers": [
        { "dataset": "trading_day", "providerId": "local_holidays_json", "asOf": "YYYY-MM-DD" }
      ],
      "outputs": [
        { "type": "file", "path": "data/runs/<day>/<runId>.json" }
      ],
      "error": null
    }
  ]
}
```

### 4.3 设计约束

- 任何 step 失败：必须写入 error（message、stack 或 stderr 摘要、建议动作）
- outputs 必须可定位：至少列出关键文件路径（便于回滚与对账）
- providers 是最小“数据血缘”占位：先记录 dataset/providerId/asOf，后续 M2 才扩展为完整注册表
- run.status 与 step.status 使用三态：run 为 success|failed|partial；step 为 success|failed|skipped
- degraded 用 step.warnings 表达，不额外引入 degraded 状态枚举
  - 约定：若存在 severity=degraded 的 warnings 且无 step failed，则 run.status = partial

### 4.4 runId 规范（确认版）

- 格式：YYYYMMDD-HHMMSS-<6位随机>
- 目的：可读、低冲突、可作为目录/文件名的一部分

## 5. 回滚规范（v0）

### 5.1 代码回滚

- 每个任务开始前：创建里程碑（commit/tag）作为回滚点
- 口径类改动：必须提供开关（配置或参数），允许快速切旧逻辑

### 5.2 数据回滚

- 原始采集层与衍生层分离：优先回滚衍生层
- 衍生产物写入必须原子化
- runId 关联产物：允许“回滚到某次 run 的产物集合”（至少能恢复到上一次成功产物）

## 6. 验收（M0/M1）

### M0 验收

- 任意一次 Runner 执行都生成 Run Journal，且能看出卡点/错误原因/产物路径
- Runner 支持指定 steps 重跑，且不会把文件写坏（原子写入）
- 能从 Run Journal 快速定位“定时没跑/跑到哪一步停了”

### M1 验收

- 禁止使用 UTC ISO 推导交易日：所有 day/asOf 由北京时间逻辑决定
- 非交易日/非交易时段：day 按交易日序列回退且提供 asOf
- 概览成交额口径符合项目规则（快照累计 vs 历史日汇总序列）
