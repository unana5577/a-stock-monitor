#!/usr/bin/env python3
"""
截屏OCR → 提取ETF持仓（detail=1 坐标版）
用法: python3 波段策略/ocr_positions.py <image_path>
输出: {"positions": [{"name": "通信ETF", "shares": 5000, "avgPrice": 1.45, "marketValue": 7600, "pnl": 350}, ...]}
"""

import sys, json, re, os

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)


def load_etf_list():
    """从 sector-proxy.json 读取 ETF 名称列表，生成名称匹配数据"""
    proxy_path = os.path.join(ROOT, "data", "sector-proxy.json")
    if not os.path.exists(proxy_path):
        return _DEFAULT_ETF_NAMES, _DEFAULT_ETF_LIST, _DEFAULT_TOKEN_MAP, {}

    try:
        with open(proxy_path) as f:
            cfg = json.load(f)
        variants = cfg.get("variants", {})
        etf_map = variants.get("etf", {})
        meta = cfg.get("etf_meta", {})

        if not etf_map:
            return _DEFAULT_ETF_NAMES, _DEFAULT_ETF_LIST, _DEFAULT_TOKEN_MAP, {}

        etf_list = []
        token_map = {}
        name_to_code = {}
        for name, code in etf_map.items():
            m = meta.get(name, {})
            if m.get("hidden"):
                continue
            # 规范化为大写 ETF 后缀
            norm_name = name.upper().replace("ETF", "ETF") if name.upper().endswith("ETF") else name + "ETF"
            base = norm_name.replace("ETF", "")
            etf_list.append(base)
            etf_list.append(norm_name)
            name_to_code[norm_name] = code
            name_to_code[base] = code
            variants_list = [norm_name, base]
            for i in range(len(base)):
                for j in range(i + 2, min(i + 5, len(base) + 1)):
                    variants.append(base[i:j])
            token_map[base] = sorted(set(variants), key=len, reverse=True)

        if not etf_list:
            return _DEFAULT_ETF_NAMES, _DEFAULT_ETF_LIST, _DEFAULT_TOKEN_MAP, {}

        return _DEFAULT_ETF_NAMES + etf_list, etf_list, {**_DEFAULT_TOKEN_MAP, **token_map}, name_to_code
    except Exception:
        return _DEFAULT_ETF_NAMES, _DEFAULT_ETF_LIST, _DEFAULT_TOKEN_MAP, {}


_DEFAULT_ETF_LIST = [
    "通信ETF", "半导体ETF", "创新药ETF", "游戏ETF", "新能源ETF",
    "云计算ETF", "机器人ETF", "商业航天ETF", "有色金属ETF",
    "通信", "半导体", "创新药", "游戏", "新能源",
    "云计算", "机器人", "商业航天", "有色金属",
]

_DEFAULT_ETF_NAMES = list(_DEFAULT_ETF_LIST)

_DEFAULT_TOKEN_MAP = {
    "通信": ["通信", "通", "信"],
    "半导体": ["半导体", "半导", "半导本"],
    "创新药": ["创新药", "创新"],
    "游戏": ["游戏"],
    "新能源": ["新能源", "新能"],
    "云计算": ["云计算", "云计"],
    "机器人": ["机器人", "机器"],
    "商业航天": ["商业航天", "商业航"],
    "有色金属": ["有色金属", "有色金", "有色"],
}

ETF_NAMES, _ETF_DISPLAY, TOKEN_MAP, NAME_TO_CODE = load_etf_list()


def normalize_name(raw):
    """OCR模糊匹配 → ETF全名"""
    for full in ETF_NAMES:
        if full in raw:
            if full.upper().endswith("ETF"):
                return full
            return full + "ETF"

    t = raw.replace("ETF", "").replace("etf", "").replace("巳", "").replace("已", "")
    for keyword, variants in TOKEN_MAP.items():
        for v in variants:
            if len(v) >= 2 and v in t:
                return keyword + "ETF"

    return None

def ocr_table(image_path):
    import easyocr
    reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
    results = reader.readtext(image_path, detail=1)
    # results: [([[x1,y1],[x2,y2],[x3,y3],[x4,y4]], 'text', confidence), ...]
    # 过滤低置信度
    items = []
    for box, text, conf in results:
        if conf < 0.2:
            continue
        t = str(text).strip()
        if not t:
            continue
        cx = (box[0][0] + box[2][0]) / 2
        cy = (box[0][1] + box[2][1]) / 2
        w = box[2][0] - box[0][0]
        h = box[2][1] - box[0][1]
        items.append({"text": t, "cx": cx, "cy": cy, "w": w, "h": h, "conf": conf})
    return items

def group_rows(items, y_gap=20):
    """按 Y 坐标分组, 同一行的 Y 差 < y_gap"""
    if not items:
        return []
    sorted_items = sorted(items, key=lambda it: it["cy"])
    rows = []
    current_row = [sorted_items[0]]
    for it in sorted_items[1:]:
        if abs(it["cy"] - current_row[-1]["cy"]) < y_gap:
            current_row.append(it)
        else:
            rows.append(sorted(current_row, key=lambda x: x["cx"]))
            current_row = [it]
    rows.append(sorted(current_row, key=lambda x: x["cx"]))
    return rows

def find_header_row(rows):
    """找列头行: 包含"市值"或"盈亏"或"成本"或"现价"等"""
    keywords = ["市值", "盈亏", "成本", "现价", "份额", "持仓", "可用", "数量", "均价", "价格"]
    best_score = 0
    best_row = None
    for row in rows:
        full = " ".join([it["text"] for it in row])
        score = sum(1 for kw in keywords if kw in full)
        if score > best_score:
            best_score = score
            best_row = row
    return best_row

def parse_number(t):
    """从 OCR 文字提取数字，处理千分位格式"""
    t = t.replace(",", "").replace("，", "").replace(" ", "")
    # 处理持股格式 "5000/5000" → 取第一个
    if "/" in t:
        parts = t.split("/")
        for p in parts:
            v = parse_number(p)
            if v is not None and v > 0:
                return v
        return None
    # 处理缺失前导零: ".080" → 补 "0.080"
    if t.startswith(".") and t[1:].isdigit():
        t = "0" + t
    # 处理多个小数点(欧式千分位): "7.600.00" → 7600.00
    dots = t.count(".")
    if dots > 1:
        last_dot = t.rfind(".")
        t = t[:last_dot].replace(".", "") + t[last_dot:]

    m = re.search(r'([+-]?\d+\.?\d*)', t)
    if not m:
        return None
    try:
        return float(m.group(1))
    except:
        return None

def column_type(text):
    """根据列头文字判断列类型"""
    t = text.replace(" ", "")
    if any(kw in t for kw in ["市值"]):
        return "marketValue"
    if any(kw in t for kw in ["盈亏率", "涨跌幅", "收益率", "幅度", "收益%", "盈亏%"]):
        return "pnlPct"
    if any(kw in t for kw in ["盈亏", "收益", "浮动"]):
        return "pnl"
    if any(kw in t for kw in ["现价", "最新价", "当前价", "市价", "股价"]):
        return "price"
    if any(kw in t for kw in ["成本", "均价", "持仓价", "买入价", "成本价"]):
        return "avgPrice"
    if any(kw in t for kw in ["持仓", "可用", "数量", "份额", "股数", "持股"]):
        return "shares"
    if any(kw in t for kw in ["名称", "证券", "代码", "标的", "简称"]):
        return "name"
    return None

def build_column_map(header_row):
    """从列头行生成 X 范围 → 列类型的映射，用相邻列中点分区"""
    cols_raw = []
    for item in header_row:
        ctype = column_type(item["text"])
        if ctype:
            cols_raw.append({"type": ctype, "cx": item["cx"]})

    if not cols_raw:
        return []

    sorted_cols = sorted(cols_raw, key=lambda c: c["cx"])

    cols = []
    for i, c in enumerate(sorted_cols):
        prev_cx = sorted_cols[i - 1]["cx"] if i > 0 else -9999
        next_cx = sorted_cols[i + 1]["cx"] if i < len(sorted_cols) - 1 else 99999
        cols.append({
            "type": c["type"],
            "x_min": (prev_cx + c["cx"]) / 2,
            "x_max": (c["cx"] + next_cx) / 2,
            "cx": c["cx"],
        })
    return cols

def assign_columns(cols, item):
    """给一个 OCR item 分配列类型"""
    cx = item["cx"]
    best = None
    best_dist = 999999
    for col in cols:
        if col["x_min"] <= cx <= col["x_max"]:
            return col["type"]
        dist = abs(cx - col["cx"])
        if dist < best_dist:
            best_dist = dist
            best = col["type"]
    if best and best_dist < 200:
        return best
    return None

def parse_positions(items):
    rows = group_rows(items)
    header_row = find_header_row(rows)
    if not header_row:
        return []

    cols = build_column_map(header_row)
    positions = []

    for row in rows:
        if row == header_row:
            continue

        row_data = {}
        expanded = []
        for item in row:
            # 处理合并单元格: "+1,040.00 +6.77%" → 拆成两个独立 cell
            t = item["text"]
            if re.search(r'[+-]?\d[\d,.]*\s+[+-]', t):
                parts = re.split(r'\s+(?=[+-]\d)', t, 1)
                for i, p in enumerate(parts):
                    if p.strip():
                        expanded.append({**item, "text": p.strip(), "cx": item["cx"] - 40 + i * 80})
            else:
                expanded.append(item)

        for item in expanded:
            ctype = assign_columns(cols, item)
            if ctype is None:
                name = normalize_name(item["text"])
                if name:
                    row_data["name"] = name
                continue

            if ctype == "name":
                name = normalize_name(item["text"])
                if name:
                    row_data["name"] = name
            else:
                val = parse_number(item["text"])
                if val is not None:
                    row_data[ctype] = val

        name = row_data.get("name")
        if not name:
            continue

        shares = row_data.get("shares")
        avg_price = row_data.get("avgPrice")
        market_value = row_data.get("marketValue")
        pnl = row_data.get("pnl")

        pos = {"name": name}
        code = NAME_TO_CODE.get(name, NAME_TO_CODE.get(name.replace("ETF",""), ""))
        if code:
            pos["code"] = code
        if shares and shares > 0:
            pos["shares"] = int(shares)

        if avg_price and avg_price > 0.01:
            pos["avgPrice"] = round(avg_price, 3)
        elif market_value and pos.get("shares") and pos["shares"] > 0:
            pos["avgPrice"] = round(market_value / pos["shares"], 3)

        if market_value and market_value > 0:
            pos["marketValue"] = round(market_value, 2)
        if pnl is not None:
            pos["pnl"] = round(pnl, 2)

        if pos.get("shares") or pos.get("avgPrice") or pos.get("marketValue"):
            positions.append(pos)

    # 如果坐标法没识别到，回退: 按 ETF 名 + 后面数字
    if not positions:
        positions = fallback_parse(items)

    return positions

def fallback_parse(items):
    """无列头时的兜底: 找 ETF 名 → 往后找两个数字（份额 + 价格）"""
    sorted_items = sorted(items, key=lambda it: (it["cy"], it["cx"]))
    full = " ".join([it["text"] for it in sorted_items])
    positions = []
    seen = set()

    for keyword in ETF_NAMES:
        if "ETF" not in keyword:
            continue
        name = keyword
        if name in seen:
            continue
        idx = full.find(name)
        if idx < 0:
            continue

        rest = full[idx + len(name):]
        nums = re.findall(r'([+-]?\d[\d,.]*\.?\d*)', rest)
        parsed = []
        for n in nums[:5]:
            n_clean = n.replace(",", "").replace("，", "")
            dots = n_clean.count(".")
            if dots > 1:
                ld = n_clean.rfind(".")
                n_clean = n_clean[:ld].replace(".", "") + n_clean[ld:]
            if n_clean.startswith(".") and n_clean[1:].isdigit():
                n_clean = "0" + n_clean
            try:
                v = float(n_clean)
                parsed.append(v)
            except:
                pass

        if not parsed:
            continue

        shares = None
        avg_price = None
        for v in parsed:
            if v >= 100 and v % 100 == 0 and v <= 100000000:
                shares = int(v)
                break
        if shares is None:
            for v in parsed:
                if v >= 100:
                    shares = int(v)
                    break
        for v in parsed:
            if 0.3 < v < 50 and v != shares:
                avg_price = round(v, 3)
                break

        if shares or avg_price:
            seen.add(name)
            positions.append({"name": name, "shares": shares or 0, "avgPrice": avg_price or 0})

    return positions

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: ocr_positions.py <image_path>"}, ensure_ascii=False))
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.exists(path):
        print(json.dumps({"error": f"file not found: {path}"}, ensure_ascii=False))
        sys.exit(1)

    try:
        items = ocr_table(path)
        positions = parse_positions(items)
        raw_texts = sorted(set(it["text"] for it in items if it["conf"] > 0.3))
        print(json.dumps({
            "positions": positions,
            "raw_texts": raw_texts,
        }, ensure_ascii=False))
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(json.dumps({"error": str(e)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
