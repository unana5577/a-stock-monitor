# n8n 可视化：Runner 可观测性（v1）

目标：让你不用手动跑命令，也能在 n8n 的 Executions 里看到每次运行的 runId、step 状态、warnings、产物路径。

## 0. 你会得到什么

- 一套“手动工作流”：用于日线确认、随时点一次就能看到 Run Journal/QA
- 一套“盘中工作流”：交易时段每 5 分钟跑一次“观测闭环”，非交易时段自动跳过

## 1. 工作流文件

- n8n-workflows/runner-observability.json（统一版，推荐）

兼容保留（如需拆分）：

- n8n-workflows/runner-observability-manual.json
- n8n-workflows/runner-observability-intraday.json

## 2. 前置条件

- n8n 在本机（Mac）运行
- runner 代码在本机仓库目录下：/Users/una5577/Documents/trae_projects/a-stock-monitor
- Python3 可用，且能执行：
  - python3 -m treasolo.runner run --plan m0m1

## 3. 导入步骤

1. 打开 n8n：http://localhost:5678
2. Import from File：
   - 导入 runner-observability.json
3. 打开工作流，检查节点参数：
   - Execute Command 的 cwd 与 command 是否符合你的本机路径

## 4. 使用方式

### 4.1 手动触发（用于日线确认）

- 打开工作流 Runner可观测性-统一
- 点击 Execute Workflow（会走“手动触发”分支）
- 在 Executions 里查看：
  - 执行Runner → 解析stdout → 读取RunJournal → 解码RunJournal

### 4.2 盘中定时（用于分时观测）

- 工作流默认 Active=true
- 说明：
  - 每 5 分钟触发一次
  - 只有北京时间 9:30-11:30 与 13:00-15:00 才会继续执行 Runner
  - 非交易时段会直接结束，不运行命令

## 5. 你在 n8n 里看什么

- Run Journal（运行账本）会落盘到：
  - data/runs/<day>/<runId>.json
- qa_basic 输出会落盘到：
  - data/runs/<day>/<runId>-qa.json
- n8n 会把 Run Journal JSON 解码出来放在节点输出里：
  - steps：每一步 success/failed/skipped
  - warnings：degraded 原因与对应文件路径

## 6. 失败日志（轻量）

盘中工作流只在 status=failed 时追加：

- logs/runner-observe-errors.log

partial（degraded）不写日志，避免噪声；你在 n8n Executions 里直接看 warnings 即可。
