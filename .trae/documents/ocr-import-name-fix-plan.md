# OCR导入 + 新增ETF中文名 修复方案

## 诊断结论：代码漂移，不是颗粒问题

本次改动是多个 agent 接力完成，不同 agent 改动了不同文件的不同段落，
但上下游 `row_data["code"]` 写入和读取之间没有衔接上。"代码漂移"具体表现：

---

## 问题 1: OCR 6只ETF只识别4只 + 一键导入失败

### 根因：6位代码检测写了但下游没读（代码漂移）

```
波段策略/ocr_positions.py

Line 249-255 (我加的):
  row_data["code"] = f"sh{code_num}"    ← 写入 row_data

Line 294-297 (原始代码,未改动):
  code = NAME_TO_CODE.get(name, ...)    ← 读 NAME_TO_CODE 映射表
  pos = {"name": name}                  ← 完全忽略 row_data["code"]
```

**漂移链路**：
1. OCR文本扫到 "512480" → 检测为6位纯数字 → `row_data["code"] = "sh512480"`
2. OCR文本扫到 "科创半导体..." → `normalize_name()` → 查 `ETF_NAMES` 列表
3. "科创半导体设备ETF" 在 proxy 中是 `"科创半导体设备ETF鹏华"` → `normalize_name` 匹配失败 → 返回 None
4. `name = row_data.get("name")` → None → `if not name: continue` → 跳过整行
5. **即使 6 位代码已经识别到了，整行也被丢弃了**

另外 2 只缺失的 ETF 可能是：
- `normalize_name` 在 TOKEN_MAP 中也匹配不到（"科创半导体" 不在 token 映射中）
- OCR 文本被 EasyOCR 误识别为其他字符

### 修复 (ocr_positions.py，约 5 行)

**点 A**：`parse_positions` 中，`row_data["code"]` 优先于 `NAME_TO_CODE`：

```python
# Line 294-297 改为:
pos = {"name": name}
code = row_data.get("code") or NAME_TO_CODE.get(name, NAME_TO_CODE.get(name.replace("ETF",""), ""))
if code:
    pos["code"] = code
```

**点 B**：即使 `normalize_name` 返回 None，如果 6 位代码已识别，仍然保留该行：

```python
# Line 285-287 改为:
name = row_data.get("name")
code_from_ocr = row_data.get("code")
if not name and not code_from_ocr:
    continue
if not name:
    name = code_from_ocr  # 用代码兜底
```

**点 C**：TOKEN_MAP 增加 "科创半导体" 的变体匹配：

`load_etf_list()` 中 `token_map[base]` 对 "科创半导体" 这类长名会生成子串变体，但 `normalize_name` 先走 `ETF_NAMES` 精确包含匹配，再到 TOKEN_MAP 子串匹配。关键是 `ETF_NAMES` 中包含 proxy 的 key（如 `"科创半导体设备ETF鹏华"`），需要确保 `if full in raw` 匹配能命中 OCR 的实际输出文本。

---

## 问题 2: 新增ETF中文名 — 接口获取 vs 用户键入

### 根因：双写但不同步（代码漂移）

当前有两套取名字的逻辑，但**不同节点写入，互相不知道**：

| 节点 | 代码位置 | 行为 |
|------|----------|------|
| 前端 `onPosEditCodeInput` | `pages/trade/ui.js:283-289` | 调 `/api/trade/quote`（腾讯）→ 异步写入 `posEditName` + `symbolNames` |
| 后端 `POST /api/sector/manage` | `server/api/etf.js:140` | 调 `fetchQuoteName(code)`（腾讯）→ 写入 `variants.etf[displayName]` |
| 前端 `registerEtfViaApi` | `pages/trade/ui.js:213-240` | 调 POST → 不传 name，等后端返回后刷新 `symbolNames` |

**漂移表现**：
1. 用户在表单输入代码 `sh589020`
2. `onPosEditCodeInput` 发请求 `/api/trade/quote` → 异步返回名字
3. **但此时表单上仍显示了 "ETF名称" 输入框**，给用户"需要自己输入名称"的错觉
4. 用户可以不输入名称直接点确认 → `posEditName` 为空 → 后端注册正常（自己查腾讯）
5. 但如果 quote API 延迟 > 用户操作时间 → 名称未回填 → 持仓列表短暂显示代码

### 修复

**点 A**：删掉名称输入框，改为纯展示加载中/已获取状态：

`pages/trade/index.html` 中，原来输入框：
```html
<input v-model="posEditName" type="text" placeholder="例：新材料ETF" ...>
```
改为只读展示：
```html
<span v-if="posEditNameLoading" class="text-[10px] text-blue-500">正在获取名称...</span>
<span v-else-if="posEditName" class="text-[10px] text-green-600">名称：{{ posEditName }}（来自行情接口）</span>
<span v-else class="text-[10px] text-orange-400">名称将在注册时自动获取</span>
```

**点 B**：`onPosEditCodeInput` 增加 loading 状态：
```javascript
posEditNameLoading.value = true;
fetch(`/api/trade/quote?symbol=${lc}`).then(...).finally(() => {
    posEditNameLoading.value = false;
});
```

**点 C**：`confirmPosEdit` 不再依赖 `posEditName`，注册流程完全由后端获取名称。

---

## 改动清单

| # | 文件 | 改动 | 行数 |
|---|------|------|------|
| 1a | `波段策略/ocr_positions.py` | `parse_positions` row_data["code"] 优先于 NAME_TO_CODE | 1 |
| 1b | `波段策略/ocr_positions.py` | `normalize_name` 返回 None 但已有代码时不丢弃行 | 3 |
| 2a | `pages/trade/index.html` | 名称输入框改为只读展示 | 3 |
| 2b | `pages/trade/ui.js` | `onPosEditCodeInput` 加 loading 状态 `posEditNameLoading` | 3 |

---

## 为什么是漂移，不是颗粒问题

两者的根因是同一个模式：
- **Agent A** 在文件头部加了 6 位代码检测 → 写入 `row_data["code"]`
- **Agent A 或 Agent B** 没改到文件尾部 100 行外的位置组装代码 → 还是读 `NAME_TO_CODE`
- 中间没有人做**全文件扫描**确认上下游一致

**预防**：后续每个改动后做 `grep` 确认该字段在全文件的读写链完整。
