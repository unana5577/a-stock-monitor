import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def load_jsonl_last(filepath):
    if not filepath.exists(): return None
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
            if lines: return json.loads(lines[-1])
    except: pass
    return None

def load_jsonl_all(filepath):
    if not filepath.exists(): return []
    res = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                if line.strip(): res.append(json.loads(line))
    except: pass
    return res

def get_minute_points(series, current_time, lookback_minutes=30):
    """获取当前时间和 N 分钟前的数据点"""
    if not series: return None, None
    current_pt = None
    past_pt = None
    
    # 找到最新点 (<= current_time)
    for pt in reversed(series):
        if pt.get('asOf') <= current_time:
            current_pt = pt
            break
            
    if not current_pt: return None, None
    
    # 计算 target_past_time (简单的时间减法，忽略跨午休复杂逻辑，仅作近似)
    curr_h, curr_m = map(int, current_pt['asOf'].split(':'))
    past_m = curr_m - lookback_minutes
    past_h = curr_h
    if past_m < 0:
        past_m += 60
        past_h -= 1
        if past_h == 11 and past_m > 30: # 跨越午休 13:00 -> 11:30
            past_h = 11
            past_m = 30 - (30 - past_m) # 简单处理
    
    target_past = f"{past_h:02d}:{past_m:02d}"
    
    # 寻找最接近 target_past 的点
    for pt in reversed(series):
        if pt.get('asOf') <= target_past:
            past_pt = pt
            break
            
    # 如果没找到（比如刚开盘不到 30 分钟），就拿第一个点
    if not past_pt and series:
        past_pt = series[0]
        
    return current_pt, past_pt

def run():
    day = datetime.now().strftime("%Y-%m-%d")
    asOf = datetime.now().strftime("%H:%M")
    
    print(f"[{asOf}] 正在生成 AI 盘中聚合快照...")
    
    # 1. 情绪 (Breadth)
    breadth = load_jsonl_last(PROJECT_ROOT / "data/market/minute/breadth-cache.jsonl")
    breadth_data = {}
    if breadth:
        breadth_data = {
            "上涨家数": breadth.get("up", 0),
            "下跌家数": breadth.get("down", 0),
            "平盘家数": breadth.get("flat", 0)
        }
        
    # 2. 量能 (Volume)
    amount_series = load_jsonl_all(PROJECT_ROOT / f"data/market/minute/amount/{day}.jsonl")
    amount_data = {}
    if amount_series:
        curr = amount_series[-1]
        amount_data = {
            "当前总成交额_亿": round(curr.get("market_amount", 0) / 1e8, 2),
            "当前时间": curr.get("asOf")
        }
        # TODO: 昨日同时刻对比需要读昨天的分时，这里暂留框架
        
    # 3. 宽基与核心 ETF 走势 (近半小时)
    targets = {
        "上证指数": ("index", "sh000001"),
        "创业板指": ("index", "sz399006"),
        "10年期国债": ("etf", "sh511260"),
        "30年期国债": ("etf", "sh511130"),
        "证券板块": ("sector", "broker"),
        "银行板块": ("sector", "bank")
    }
    
    market_data = {}
    for name, (category, code) in targets.items():
        filepath = PROJECT_ROOT / f"data/{category}/minute/{code}/{day}.jsonl"
        series = load_jsonl_all(filepath)
        curr_pt, past_pt = get_minute_points(series, asOf, 30)
        
        if curr_pt and past_pt:
            # 对于 index 只有 price，对于 etf/sector 有 pct
            curr_price = curr_pt.get("price", 0)
            past_price = past_pt.get("price", 0)
            
            total_pct = curr_pt.get("pct")
            if total_pct is None and past_pt.get("price"):
                # 如果没有 pct (如 index)，我们用第一根 K 线近似开盘价算个大概
                open_price = series[0].get("price", curr_price)
                total_pct = (curr_price - open_price) / open_price * 100 if open_price else 0
                
            half_hour_diff = (curr_price - past_price) / past_price * 100 if past_price else 0
            
            market_data[name] = {
                "早盘总涨跌幅_pct": round(total_pct, 2) if total_pct is not None else 0,
                "近半小时变化_pct": round(half_hour_diff, 2)
            }

    # 4. 组装 Payload
    payload = {
        "asOf": asOf,
        "date": day,
        "情绪_Breadth": breadth_data,
        "量能_Volume": amount_data,
        "核心资产走势": market_data
    }
    
    # 5. 落盘
    out_dir = PROJECT_ROOT / "data/market/ai"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "snapshot.jsonl"
    
    with open(out_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        
    print(f"✅ 生成成功！已追加至: {out_file.relative_to(PROJECT_ROOT)}")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    run()
