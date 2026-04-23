# 归一分析：新增 ETF 纳入全局资产池（需求草案）
 
## 背景与目标
 
“归一分析（Normalized Analysis）”模块需要支持盘中临时添加任意 ETF 进行对比，同时新增 ETF 必须纳入全局资产池，确保后续 **Warmup + Lifecycle** 计算链路同步覆盖，避免“后面的工作流/模块为空”。
 
目标：
 
- 前端采用“方案 2”：一级分类 + 二级分类 + 输入 ETF 代码（支持名称/代码搜索联想）
- 同时支持：**当日分时（1日）** + **60 个交易日（日线）** 的归一曲线
- 新增 ETF 后自动进入全局资产池，触发 **daily 补齐** 与 **Warmup/Lifecycle 刷新**
 
非目标：
 
- 本文不定义具体 UI 像素级稿
- 本文不确定外部数据源优先级（由现有实现复用）
 
## 口径与规则
 
### 数据维度
 
- 分时（corrDays = 1）：交易分钟槽位 240（09:30-11:30 + 13:00-15:00），以北京时间为准
- 日线（corrDays = 5/20/60）：最近 N 个交易日的 close/pct 序列
 
### 60 日线的起始日期（发行时间未知）
 
不应固定从 2025-01-01 强制加载。
 
规则建议：
 
- 默认目标：最近 **60 个交易日**
- 若本地日线不足 60 条，则触发 backfill/ensure 从数据源补齐
- 后端记录 `first_available_date`（该 ETF 实际最早可用日），不足 60 天时返回 `data_incomplete=true` 并携带 `first_available_date` 给前端提示
- 允许设置系统级回补下限：`min_backfill_date = 2025-01-01`（仅用于限制回补跨度，实际以 `first_available_date` 为准）
 
### 缺失点处理
 
- 分时对齐以时间槽位 `HH:MM` 为主；缺失分钟以 `null` 表示缺失（不横向平推）
- 日线不足窗口时，以“实际可用条数”渲染并提示，不强行补空
 
## 全局资产池接入闭环（必须）
 
新增 ETF 不能只服务归一分析，还必须保证：
 
- `warmup-60.json` 包含新增 ETF 的数据（否则“上涨周期统计”等模块无法显示）
- `lifecycle.json` 包含新增 ETF 的生命周期阶段与建议（否则“生命周期/建议”等模块为空）
 
## 执行步骤（端到端）
 
### Step 0｜确定资产结构
 
- 资产字段：`symbol`、`name`（可选自动识别）、`category_l1`、`category_l2`、`enabled`、`created_at`、`updated_at`、`first_available_date`、`notes`（可选）
- 交易日与时区规则统一：Asia/Shanghai
 
### Step 1｜新增资产入口（前端方案 2）
 
- 输入组：`一级分类`（下拉）+ `二级分类`（级联下拉）+ `代码/名称输入`（联想）+ `添加`
- 提交 payload：`{ category_l1, category_l2, symbol }`（可带 name）
 
### Step 2｜后端校验与写入全局资产池（落盘）
 
- 校验 `symbol` 格式：`sh|sz` + 6 位数字
- 可用性验证：能拉到基本信息与至少一段日线/分钟数据（拿到 `name`、`first_available_date`）
- 写入全局配置（建议复用既有文件结构）：
  - `data/sector-proxy.json`：写入 ETF 映射与元信息（分类）
  - 如有需要同步：`data/sector-profile.json`（绑定/分组）
- 幂等：重复添加同一 symbol 仅更新分类/名称，不重复写入
 
### Step 3｜即时可用的数据查询（不等后台任务）
 
添加成功后，前端立即请求：
 
- 分时：`minute(symbol, day)` 用于 corrDays=1
- 日线：`daily(symbol, limit=60)` 用于 corrDays=60（以及 5/20）
 
返回需携带：
 
- 分时：`asOf`（HH:MM）+ `pre_close`
- 日线：`asOfDate`（YYYY-MM-DD）+ `first_available_date`（如不足窗口）
 
### Step 4｜触发 ensure/backfill 动作流（异步）
 
后端异步触发（不阻塞 UI）：
 
- 补齐 daily：至少 60 个交易日；建议补到 120~250 个交易日供 lifecycle 稳定计算
- 盘中补 minute（受控）：若当天 minute 文件不存在/过短，可限频补抓一次
- 产出 runId（可观测）：便于追踪状态与失败原因
 
### Step 5｜触发 Warmup 刷新
 
在 daily 补齐完成后触发：
 
- 生成/更新 `data/warmup/warmup-60.json`（必须包含新增 ETF）
 
### Step 6｜触发 Lifecycle 刷新
 
Warmup 更新后立即触发：
 
- 生成/更新 `data/lifecycle/lifecycle.json`（必须包含新增 ETF 的阶段/建议）
 
### Step 7｜前端刷新后置模块
 
- 归一分析：立即渲染分时/日线
- Warmup/Lifecycle：轮询 `updated_at` 或基于 runId 查询，完成后刷新依赖模块（上涨周期统计、生命周期建议等），避免空白
 
### Step 8｜运维与一致性
 
- minute 过期清理：保留 T-3（按现有 cleanup 逻辑）
- daily 永久保留，不参与清理
- AI/追加型日志按行截断（保留最近 N 天）不影响该需求
 
## 后端接口（建议最小集合）
 
元数据/选择器：
 
- `GET /api/assets/taxonomy`：返回一级/二级分类树
- `GET /api/assets/etfs/search?q=...`：代码/名称联想
- `POST /api/assets/etfs`：新增 ETF（写入资产池，返回 ok + basic meta）
 
数据查询：
 
- `GET /api/assets/etfs/:symbol/minute?day=YYYY-MM-DD`
- `GET /api/assets/etfs/:symbol/daily?limit=60`
 
动作流：
 
- `POST /api/assets/etfs/:symbol/ensure`：异步补齐 daily/minute，并触发 warmup/lifecycle（或返回 runId）
 
## 前端验收点
 
- 可添加任意 ETF（合法/非法/无数据分别有明确反馈）
- 当日分时对齐 240 槽位，缺失点不乱连
- 60 日线可显示；新 ETF 不足 60 天能提示起始日与实际样本数
- 新增 ETF 后，Warmup/Lifecycle 相关模块不为空（刷新后能看到新增 ETF）
 
