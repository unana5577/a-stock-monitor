# 快速诊断参考手册

> 更新时间：2026-03-24

## 使用诊断工具

### 交互式诊断

```bash
python3 scripts/diagnose_issue.py
```

工具会引导你完成诊断步骤，自动分析结果，生成诊断报告。

---

## 症状→检查步骤快速参考

### 1. 前端不显示/显示错误

**快速检查**（3步）：
1. ✅ **Python测试** → 验证数据层/业务层
   ```bash
   python3 fetch_sector_data.py lifecycle 60
   ```
2. ✅ **HTTP接口测试** → 验证API层
   ```bash
   curl "http://localhost:8787/api/sector/lifecycle?days=60"
   ```
3. ✅ **查看日志** → 定位具体错误
   ```bash
   tail -30 server.log | grep -i "lifecycle\|验证"
   ```

**常见根因**：
- Python正常 + HTTP返回空 → **Layer 3 验证逻辑问题**
- Python正常 + HTTP正常 → **Layer 4 前端绑定问题**
- Python异常 → **Layer 1/2 数据/业务问题**

---

### 2. API接口返回空/错误

**快速检查**（3步）：
1. ✅ **检查warmup**
   ```bash
   cat data/sector-history-warmup-60.json | jq '.day'
   ```
2. ✅ **Python测试**
   ```bash
   python3 fetch_sector_data.py lifecycle 60
   ```
3. ✅ **HTTP详细测试**
   ```bash
   curl "http://localhost:8787/api/sector/lifecycle?days=60" | jq
   ```

**常见根因**：
- warmup日期过期 → **Layer 1 数据未更新**
- Python正常 + HTTP返回空 + reason: trading_day_mismatch → **Layer 3 验证逻辑**

---

### 3. 数据计算结果不对

**快速检查**（3步）：
1. ✅ **检查原始数据**
   ```bash
   tail -3 data/etf_daily/etf_512480.jsonl | jq
   ```
2. ✅ **检查warmup数据**
   ```bash
   cat data/sector-history-warmup-60.json | jq '.history | keys'
   ```
3. ✅ **测试公式计算**
   ```bash
   python3 -c "from fetch_sector_data import get_sector_lifecycle; import json; print(json.dumps(get_sector_lifecycle([], 60)['items'][0]['指标数据'], indent=2, ensure_ascii=False))"
   ```

**常见根因**：
- 原始数据异常 → **Layer 1 数据源问题**
- 原始数据正常 + 指标异常 → **Layer 2 公式问题**

---

### 4. 数据过期/缺失

**快速检查**（3步）：
1. ✅ **检查warmup日期**
   ```bash
   cat data/sector-history-warmup-60.json | jq '.day'
   ```
2. ✅ **检查定时任务**
   ```bash
   crontab -l | grep -E 'data_maintenance|warmup'
   ```
3. ✅ **查看更新日志**
   ```bash
   tail -50 logs/data_daily.log
   ```

**常见根因**：
- 无定时任务 → **调度层未配置**
- 有定时任务 + 更新失败 → **Layer 1 接口/更新问题**
- 有定时任务 + 最后更新时间过早 → **Layer 1 更新延迟**

---

## 诊断流程图

```
用户报问题
    ↓
选择症状类型
    ↓
执行3步检查（工具引导）
    ↓
自动分析结果
    ↓
📊 生成诊断报告
    ↓
🎯 定位根因 + 建议下一步
```

---

## 诊断报告位置

所有诊断报告保存在：
```
docs/diagnoses/
├─ 20260324_143022_前端不显示_显示错误.md
├─ 20260324_150105_API接口返回空_错误.md
└─ ...
```

---

## 常见问题快速定位表

| 症状 | 第一检查点 | 边界定位 | 典型根因 |
|------|-----------|---------|---------|
| lifecycle返回空 | Python直接调用 | Layer 3 | 验证逻辑用错日期 |
| 指标值异常 | 原始数据 | Layer 2 | 公式边界条件 |
| warmup过期 | crontab配置 | 调度层 | 定时任务未配置 |
| 分时缺失 | minute文件 | Layer 1 | 接口调用失败 |
| 前端不刷新 | F12 Network | Layer 4 | 轮询/缓存问题 |

---

## 相关工具

| 工具 | 功能 | 适用场景 |
|------|------|---------|
| `diagnose_issue.py` | 引导式诊断 | 所有问题 |
| `leader_daily_check.py` | 每日检查 | warmup+lifecycle |
| `verify_warmup_data.py` | warmup验证 | 数据完整性 |
| `verify_ai_data.py` | AI接口验证 | 接口健康 |

---

## 使用建议

1. **遇到问题时**，先运行 `diagnose_issue.py`
2. **不要跳过诊断**直接改代码
3. **保留诊断报告**，便于回顾和积累
4. **高频问题**可以补充到诊断流程中

---

**维护者**：Leader
