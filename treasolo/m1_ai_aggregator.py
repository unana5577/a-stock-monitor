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

def get_previous_trading_file(today_str: str, base_dir: str) -> str | None:
    """找最近一个交易日的文件（回退最近 10 天）"""
    from datetime import timedelta
    dt = datetime.strptime(today_str, "%Y-%m-%d")
    for i in range(1, 11):
        prev_dt = dt - timedelta(days=i)
        prev_day = prev_dt.strftime("%Y-%m-%d")
        if (PROJECT_ROOT / f"data/{base_dir}/{prev_day}.jsonl").exists():
            return prev_day
    return None

def run():
    day = datetime.now().strftime("%Y-%m-%d")
    asOf = datetime.now().strftime("%H:%M")
    
    print(f"[{asOf}] 正在生成 AI 盘中聚合快照...")
    
    is_stale = False
    stale_note = ""
    
    # 1. 情绪 (Breadth)
    breadth = load_jsonl_last(PROJECT_ROOT / "data/market/minute/breadth-cache.jsonl")
    breadth_data = {}
    if breadth:
        breadth_data = {
            "上涨家数": breadth.get("up", 0),
            "下跌家数": breadth.get("down", 0),
            "平盘家数": breadth.get("flat", 0)
        }
        # Verify the jsonl entry is from today
        dt_str = str(breadth.get("datetime", breadth.get("timestamp", "")))
        if dt_str[:10] != day and dt_str[:10]:
            is_stale = True
            stale_note = f"breadth 数据来自 {dt_str[:10]}，今日尚未更新"
    else:
        # Fallback to the archive if breadth-cache.jsonl is cleared
        day_nodash = day.replace("-", "")
        archive_path = PROJECT_ROOT / f"data/archive-{day_nodash}.jsonl"
        archive_records = load_jsonl_all(archive_path)
        if archive_records and len(archive_records[-1]) >= 24:
            last_record = archive_records[-1]
            try:
                up_cnt = int(last_record[22] or 0)
                down_cnt = int(last_record[23] or 0)
                if up_cnt > 0 or down_cnt > 0:
                    breadth_data = {
                        "上涨家数": up_cnt,
                        "下跌家数": down_cnt,
                        "平盘家数": 0
                    }
            except:
                pass
        
        # Fallback to breadth-cache.json (even stale, but tagged)
        if not breadth_data:
            snap_path = PROJECT_ROOT / "data/market/breadth-cache.json"
            if snap_path.exists():
                try:
                    with open(snap_path, "r") as f:
                        snap = json.load(f)
                        if "up" in snap:
                            cached_day = str(snap.get("updated", snap.get("timestamp", "")))[:10]
                            if cached_day != day:
                                breadth_data = {
                                    "上涨家数": snap.get("up", 0),
                                    "下跌家数": snap.get("down", 0),
                                    "平盘家数": snap.get("flat", 0)
                                }
                                is_stale = True
                                stale_note = f"breadth 数据来自 {cached_day}（上一交易日），今日尚未更新"
                                print(f"  ⚠️ 使用 stale breadth-cache.json {cached_day} 作为兜底")
                            else:
                                breadth_data = {
                                    "上涨家数": snap.get("up", 0),
                                    "下跌家数": snap.get("down", 0),
                                    "平盘家数": snap.get("flat", 0)
                                }
                except:
                    pass
        
    # 2. 量能 (Volume)
    amount_series = load_jsonl_all(PROJECT_ROOT / f"data/market/minute/amount/{day}.jsonl")
    amount_data = {}
    if amount_series:
        curr = amount_series[-1]
        amount_data = {
            "当前总成交额_亿": round(curr.get("market_amount", 0) / 1e8, 2),
            "当前时间": curr.get("asOf")
        }
    else:
        # No today's volume data — indicates pre-market / data delay
        print(f"  今日量能数据尚未生成 (data/market/minute/amount/{day}.jsonl)")
        
    # 3. 宽基与核心 ETF 走势 (近半小时)
    targets = {
        "上证指数": ("index", "sh000001"),
        "创业板指": ("index", "sz399006"),
        "10年期国债": ("etf", "sh511260"),
        "30年期国债": ("etf", "sh511130"),
        "证券板块": ("sector", "broker"),
        "银行板块": ("sector", "bank")
    }
    
    got_any_market = False
    market_data = {}
    for name, (category, code) in targets.items():
        filepath = PROJECT_ROOT / f"data/{category}/minute/{code}/{day}.jsonl"
        series = load_jsonl_all(filepath)
        if not series:
            # 尝试前一天的数据作为盘前参考
            prev_day = get_previous_trading_file(day, f"{category}/minute/{code}")
            if prev_day:
                filepath2 = PROJECT_ROOT / f"data/{category}/minute/{code}/{prev_day}.jsonl"
                series = load_jsonl_all(filepath2)
                if series and not got_any_market:
                    is_stale = True
                    if not stale_note:
                        stale_note = f"核心资产数据来自 {prev_day}（上一交易日），尚未开市"
        curr_pt, past_pt = get_minute_points(series, asOf, 30)
        
        if curr_pt and past_pt:
            got_any_market = True
            curr_price = curr_pt.get("price", 0)
            past_price = past_pt.get("price", 0)
            
            total_pct = curr_pt.get("pct")
            if total_pct is None and past_pt.get("price"):
                open_price = series[0].get("price", curr_price)
                total_pct = (curr_price - open_price) / open_price * 100 if open_price else 0
                
            half_hour_diff = (curr_price - past_price) / past_price * 100 if past_price else 0
            
            market_data[name] = {
                "早盘总涨跌幅_pct": round(total_pct, 2) if total_pct is not None else 0,
                "近半小时变化_pct": round(half_hour_diff, 2)
            }

    # 3.5. 抓取所有核心行业 ETF 的表现，并按照 tag 分类聚合
    proxy_file = PROJECT_ROOT / "data/sector-proxy.json"
    etf_sectors = {}
    if proxy_file.exists():
        with open(proxy_file, "r", encoding="utf-8") as f:
            proxy_data = json.load(f)
            etf_dict = proxy_data.get("variants", {}).get("etf", {})
            etf_meta = proxy_data.get("etf_meta", {})
            
            for etf_name, etf_code in etf_dict.items():
                meta = etf_meta.get(etf_name, {"category": "未分类", "sub_category": "未知"})
                cat = meta["category"]
                
                filepath = PROJECT_ROOT / f"data/etf/minute/{etf_code}/{day}.jsonl"
                series = load_jsonl_all(filepath)
                if not series:
                    prev_day = get_previous_trading_file(day, f"etf/minute/{etf_code}")
                    if prev_day:
                        series = load_jsonl_all(PROJECT_ROOT / f"data/etf/minute/{etf_code}/{prev_day}.jsonl")
                curr_pt, past_pt = get_minute_points(series, asOf, 30)
                
                if curr_pt and past_pt:
                    total_pct = curr_pt.get("pct", 0)
                    half_hour_diff = (curr_pt.get("price", 0) - past_pt.get("price", 0)) / past_pt.get("price", 1) * 100 if past_pt.get("price") else 0
                    
                    if cat not in etf_sectors:
                        etf_sectors[cat] = []
                    
                    etf_sectors[cat].append({
                        "名称": etf_name,
                        "细分": meta["sub_category"],
                        "总涨跌_pct": round(total_pct, 2),
                        "近半小时变化_pct": round(half_hour_diff, 2)
                    })
                    
    # 4. 组装 Payload
    payload = {
        "asOf": asOf,
        "date": day,
        "data_freshness": {
            "is_stale": is_stale,
            "note": stale_note if stale_note else "实时数据"
        },
        "情绪_Breadth": breadth_data,
        "量能_Volume": amount_data,
        "核心资产走势": market_data,
        "主线板块阵营": etf_sectors
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
