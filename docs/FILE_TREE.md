# 项目文件路径树

> 更新时间：2026-03-19 19:50

## 核心文档结构

```
/Users/una5577/Documents/trae_projects/a-stock-monitor/
├── CLAUDE.md                                    # 项目规则
├── README.md
│
├── docs/                                        # 文档目录
│   ├── CLAUDE_LEADER.md                          # Leader 工作规范 ⭐
│   ├─��� agents/                                  # Agent 规范 ⭐
│   │   ├── agent_data.md                         # 数据Agent规范
│   │   ├── agent_business.md                     # 业务Agent规范
│   │   ├── agent_ui.md                           # UI Agent规范
│   │   ├── agent_cleanup.md                      # 清理Agent规范
│   │   ├── 2026-03-19_work_log.md               # 今日工作日志 ⭐
│   │   └── task_status.md                        # 任务状态总览 ⭐
│   │
│   └── FILE_TREE.md                              # 本文件
│
└── context/                                      # 需求/分析文档 ⭐
    ├── data-contract.md                          # 数据契约（正式版）
    ├── business-data-requirements.md              # 业务层数据需求
    ├── data-capability-assessment.md             # 数据系统能力评估
    ├── ui-data-requirements.md                   # 前端数据需求
    └── existing-system-analysis.md               # 现有系统分析
```

## 数据Agent 权限文件

```
可操作：
├── fetch_sector_data.py                         # 数据获取主模块
├── data_maintenance.py                          # 数据维护脚本
├── data/                                        # 数据目录
│   ├── minute_data/                             # 分时数据
│   ├── etf_daily/                               # ETF日线
│   ├── index_daily/                             # 指数日线
│   └── sector-history-warmup-60.json            # Warmup缓存
└── config/
    └── holidays.json                             # 节假日配置
```

## 业务Agent 权限文件

```
可操作：
├── sector_lifecycle/                            # 生命周期模块
│   └── ...
└── (业务层计算代码，待确认)
```

## UI_Agent 权限文件

```
可操作：
├── public/
│   ├── ui.js                                    # 前端主文件
│   └── index.html
└── (前端组件代码，待确认)
```

## 清理Agent 权限文件

```
可操作：
├── 根目录调试脚本（待确认）
└── (所有文件只读扫描)
```

---

**说明**：
- ⭐ 标记的是今日新增/更新的核心文档
- Agent权限文件需要进一步确认
- 所有待提交的修改需要Leader复核后提交
