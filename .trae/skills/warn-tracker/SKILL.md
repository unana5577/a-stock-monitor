---
name: "warn-tracker"
description: "解释命令输出中的 WARN/漏洞/弃用提示并生成后续修复清单。出现 npm WARN、pip warning、systemd/nginx 警告或用户要求梳理告警时调用。"
---

# Warn Tracker

## 目标

在部署/安装/运行过程中出现警告（WARN）、漏洞提示（vulnerabilities）、弃用提示（deprecated）时：

1. 先解释这些提示是否阻塞当前目标（例如“服务能否跑起来”）
2. 给出风险级别与处理优先级
3. 生成一份明确的“后续修复待办清单”（可追加到本地运维文档）

## 输出格式

### 告警解释

- 来源：npm / pip / systemd / nginx / OS
- 是否阻塞：是/否（说明原因）
- 风险：安全/兼容/性能/维护成本
- 建议：立即处理/后续处理（说明理由）

### 待办清单（后续修复）

- 每条待办 ≤ 14 字，动词开头
- 按优先级排序：高 / 中 / 低
- 只列“需要做的事”，不列长解释

## 写入运维文档（可选）

如果仓库存在 `README.ops.md`（并已在 `.gitignore` 忽略），则将待办清单追加到：

- `README.ops.md` 的 “告警与待办” 小节

## 示例

输入：`npm WARN deprecated ...` + `2 vulnerabilities (1 moderate, 1 high)`

输出：

- 是否阻塞：否（不影响启动服务）
- 风险：中（后续需要升级依赖/修复漏洞）
- 待办：
  - 运行 npm audit
  - 评估 npm audit fix
  - 升级 eslint 依赖
  - 升级 glob 依赖
