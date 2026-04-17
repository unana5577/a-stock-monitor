# TODO 总表（M0+M1 执行清单，M2 暂缓池）

规则：动手做任何一条前，必须先与你确认“范围/验收/影响面/回滚点”。

## A. M0（平台止血：编排 + 可观测性 + 可回滚）

- M0-001 定义 Runner 计划与 step 列表（定稿到文档）
  - 验收：step 名称/职责/产物路径清晰且与现有链路能对上
- M0-002 定义 Run Journal schema（字段、落盘路径、状态枚举）
  - 验收：能回答“跑了没/卡哪/产物在哪/用了哪个源/asOf”
- M0-003 选定 Runner 实现位置与入口形式（Python module：`python3 -m treasolo.runner ...`）
  - 验收：本地可直接运行并输出 help/usage
- M0-004 实现 `resolve_day`（北京时间交易日推导 + holidays）
  - 验收：周末/节假日/盘前均回退到最近交易日；严禁 UTC 推导
- M0-005 实现 Runner 执行框架（runId、step 生命周期、错误处理、dry-run）
  - 验收：任意失败都有 Run Journal；dry-run 不写文件
- M0-006 落盘 Run Journal（`data/runs/<day>/<runId>.json`）
  - 验收：重复运行不覆盖旧 run；结构稳定
- M0-007 产物分层规范落地（原始采集 vs 衍生计算 vs 报告）
  - 验收：至少把“报告/衍生聚合”从“原始采集”隔离开
- M0-008 原子写入工具函数（temp → 校验 → rename）
  - 验收：中断/失败不会留下半截正式文件
- M0-009 接入 1 条“最小闭环任务链”到 Runner
  - 建议闭环：resolve_day → qa_basic → report（先不碰大规模数据写入）
  - 验收：闭环跑通且可重复执行
- M0-010 将“关键数据更新任务”逐步纳入 Runner（只纳入入口，不改业务逻辑）
  - 候选：market_snapshot_sina、market_amount_daily_backfill、data_maintenance（日线）、warmup
  - 验收：同任务从 Runner 运行和原方式运行结果一致
- M0-011 提供“查询最近运行状态”的命令（CLI 子命令或读取 latest）
  - 验收：一条命令能看到最近 N 次 run 的状态摘要
- M0-012 n8n 可视化工作流（Execute Command 触发 Runner + 读取 Run Journal/QA）
  - 验收：不手动跑命令，n8n Executions 可查看每次运行的 step 状态与 warnings

## B. M1（时间/口径收口：北京时间 + asOf 一致性）

- M1-001 全仓扫描 UTC 推导交易日的代码点（`toISOString().split('T')[0]` 等）
  - 验收：列出文件/函数/风险说明，给你确认替换方案
- M1-002 server.js：替换关键链路的 “today/day” 推导为北京时间工具函数
  - 验收：关键 API（minute/snapshot/overview）在临界时间不再错日
- M1-003 public/ui.js：核对前端“交易时段判断/午休规则”是否使用本地时间导致漂移
  - 验收：前端展示日期与后端 day/asOf 一致
- M1-004 统一 API 的 asOf 字段命名与语义（asOf/asof 一致策略）
  - 验收：前端能统一展示“数据截至：YYYY-MM-DD”
- M1-005 概览成交额口径自检（快照累计 vs 历史日汇总）
  - 验收：满足项目规则：快照成交额为沪深主板累计；历史成交额为日汇总序列
- M1-006 加入 qa_basic 检查项（交易日、asOf、文件存在性、关键字段）
  - 验收：qa_basic 产出 JSON 报告，异常明确可定位

## C. M2（暂缓池：M0/M1 验收通过后再开工）

- M2-001 午休时段状态保持（11:30-13:00 保留上午曲线不回退）（任务板 #6）
- M2-002 普通 ETF 分时 pct 字段补齐（任务板 #22）
- M2-003 板块分时 pct 字段补齐（任务板 #23）
- M2-004 15:00 收盘后 ETF 日线优先策略（任务板 #7）
- M2-005 18:00-21:00 ETF 日线对账覆盖（任务板 #8）
- M2-006 市场成交额历史文件修复/重建（任务板 #10）
- M2-007 AI 实时接口数据溯源与超时治理（任务板 #11）
- M2-008 archive 60 交易日缺口回补策略与执行（任务板 #12）
- M2-009 “接口注册表/主备路由”体系化（对应 handoff 文档的 Registry/Lineage）
- M2-010 repo tidy：cleanup_plan + .gitignore 收敛 + 去跟踪产物（需你确认删除名单）

## D. 永久规则（做任何改动都必须满足）

- 全部日期/交易时段/分钟对齐按 Asia/Shanghai
- 非交易时段 day 一律以“最近交易日”作为 day，T-1/T-2 按交易日序列递推
- 缓存必须落盘可追溯：缺失后端自检并自动补齐，不得只在 UI 提示缺失
