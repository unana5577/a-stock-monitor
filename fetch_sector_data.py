import akshare as ak
import pandas as pd
import json
import sys
import os
import importlib.util
from datetime import datetime

# User-defined sector mapping
SECTOR_MAPPING = [
    {"name": "半导体", "display": "半导体", "code": "BK_半导体"},
    {"name": "云计算", "display": "云计算", "code": "BK_云计算"},
    {"name": "新能源", "display": "新能源", "code": "BK_新能源"},
    {"name": "商业航天", "display": "商业航天", "code": "BK_商业航天"},
    {"name": "创新药", "display": "创新药", "code": "BK_创新药"},
    {"name": "有色金属", "display": "有色金属", "code": "BK_有色金属"},
    {"name": "煤炭行业", "display": "煤炭", "code": "BK_煤炭"},
    {"name": "电力行业", "display": "电力", "code": "BK_电力"},
    {"name": "通信设备", "display": "通讯设备", "code": "BK_通讯设备"},
    {"name": "银行", "display": "银行", "code": "BK_银行"}
]

START_DATE = "20150527"
CACHE_FILE = os.path.join("data", "sector-cache.csv")
DEFAULT_SECTORS = ["半导体", "云计算", "新能源", "商业航天", "创新药", "有色金属", "煤炭", "电力", "通讯设备"]
DEFAULT_BENCHMARK = "上证"

def _load_quant_modules():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    base = os.path.join(root_dir, ".trae", "skills", "Quant_Sector_Analysis")
    if not os.path.exists(base):
        return None, None
    def load(name, filename):
        path = os.path.join(base, filename)
        if not os.path.exists(path):
            return None
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    return load("clean_local", "clean.py"), load("features_local", "features.py")

def _date_days_ago(n):
    return (datetime.now() - pd.Timedelta(days=n)).strftime("%Y%m%d")

def _market_closed_now():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    if now.hour > 15:
        return True
    if now.hour == 15 and now.minute >= 5:
        return True
    return False

def get_sector_history(sector_name, days=180):
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = START_DATE
        
        # Try Industry Board first
        try:
            df = ak.stock_board_industry_hist_em(symbol=sector_name, start_date=start_date, end_date=end_date, period="日k")
        except:
            df = pd.DataFrame()
            
        # If empty, try Concept Board
        if df.empty:
            try:
                df = ak.stock_board_concept_hist_em(symbol=sector_name, start_date=start_date, end_date=end_date, period="daily")
            except:
                pass
                
        if df.empty:
            return None

        # Process columns
        df = df.sort_values("日期", ascending=True)
        
        result = []
        for _, row in df.iterrows():
            result.append({
                "date": row["日期"],
                "open": row.get("开盘"),
                "high": row.get("最高"),
                "low": row.get("最低"),
                "close": row.get("收盘"),
                "pct": row.get("涨跌幅"),
                "amount": row.get("成交额"),
                "volume": row.get("成交量"),
                "turnover": row.get("换手率")
            })
        return result
    except Exception as e:
        return None

def get_sector_history_range(sector_name, start_date, end_date):
    try:
        try:
            df = ak.stock_board_industry_hist_em(symbol=sector_name, start_date=start_date, end_date=end_date, period="日k")
        except:
            df = pd.DataFrame()
        if df.empty:
            try:
                df = ak.stock_board_concept_hist_em(symbol=sector_name, start_date=start_date, end_date=end_date, period="daily")
            except:
                df = pd.DataFrame()
        if df.empty:
            return []
        df = df.sort_values("日期", ascending=True)
        result = []
        for _, row in df.iterrows():
            result.append({
                "date": _to_date_str(row["日期"]),
                "open": row.get("开盘"),
                "high": row.get("最高"),
                "low": row.get("最低"),
                "close": row.get("收盘"),
                "pct": row.get("涨跌幅"),
                "amount": row.get("成交额"),
                "volume": row.get("成交量"),
                "turnover": row.get("换手率")
            })
        return [r for r in result if r.get("date")]
    except:
        return []

def _parse_sector_arg(arg):
    if arg is None:
        return []
    try:
        parsed = json.loads(arg)
        if isinstance(parsed, list):
            return parsed
    except:
        pass
    return [s.strip() for s in str(arg).split(",") if s.strip()]

def _normalize_sectors(items):
    lookup = {}
    for it in SECTOR_MAPPING:
        lookup[it["name"]] = it
        lookup[it["display"]] = it
        lookup[it["code"]] = it
    out = []
    seen = set()
    for raw in items:
        s = str(raw).strip()
        if not s:
            continue
        item = lookup.get(s)
        if not item and s.startswith("BK_"):
            name = s.replace("BK_", "")
            item = {"name": name, "display": name, "code": s}
        if not item:
            item = {"name": s, "display": s, "code": f"BK_{s}"}
        key = item["display"]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out

def _load_cache(path=CACHE_FILE):
    cols = ["date", "sector", "code", "type", "pct", "amount", "volume", "turnover", "open", "high", "low", "close"]
    if not os.path.exists(path):
        return pd.DataFrame(columns=cols)
    try:
        df = pd.read_csv(path)
    except:
        return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df[cols]

def _save_cache(df, path=CACHE_FILE):
    if df is None or df.empty:
        return
    df = df.dropna(subset=["date", "sector"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["date", "sector"])
    df = df.sort_values(["date", "sector"])
    df.to_csv(path, index=False)

def _update_sector_cache(sectors, ensure_days=None):
    df = _load_cache()
    today_dt = datetime.now()
    today = today_dt.strftime("%Y%m%d")
    ensure_start = None
    if ensure_days:
        ensure_start = _date_days_ago(max(ensure_days * 3, 30))
    for item in sectors:
        display = item["display"]
        name = item["name"]
        code = item["code"]
        last_date = None
        part = pd.DataFrame()
        if not df.empty:
            part = df[df["sector"] == display]
            if not part.empty:
                last_date = part["date"].max()
        start_date = START_DATE
        if last_date:
            d = pd.to_datetime(last_date, errors="coerce")
            if pd.notna(d):
                start_date = (d + pd.Timedelta(days=1)).strftime("%Y%m%d")
        if ensure_start:
            if part.empty:
                start_date = ensure_start
            else:
                recent = part.copy()
                recent["date"] = pd.to_datetime(recent["date"], errors="coerce")
                recent = recent[recent["date"] >= pd.to_datetime(ensure_start)]
                need_refetch = False
                if recent["date"].dropna().nunique() < ensure_days:
                    need_refetch = True
                else:
                    for col in ["open", "high", "low", "close"]:
                        if col not in recent.columns or recent[col].isna().any():
                            need_refetch = True
                            break
                if need_refetch:
                    if ensure_start < start_date:
                        start_date = ensure_start
        if start_date > today:
            continue
        rows = get_sector_history_range(name, start_date, today)
        if not rows:
            continue
        new_df = pd.DataFrame([{
            "date": r.get("date"),
            "sector": display,
            "code": code,
            "type": "sector",
            "pct": r.get("pct"),
            "amount": r.get("amount"),
            "volume": r.get("volume"),
            "turnover": r.get("turnover"),
            "open": r.get("open"),
            "high": r.get("high"),
            "low": r.get("low"),
            "close": r.get("close")
        } for r in rows])
        if not new_df.empty:
            start_dt = pd.to_datetime(start_date, errors="coerce")
            if pd.notna(start_dt) and not df.empty:
                df = df.copy()
                df["_date_dt"] = pd.to_datetime(df["date"], errors="coerce")
                df = df[~((df["sector"] == display) & (df["_date_dt"] >= start_dt))]
                df = df.drop(columns=["_date_dt"])
            df = pd.concat([df, new_df], ignore_index=True)
    if not df.empty:
        df = df.drop_duplicates(subset=["date", "sector"], keep="last")
        _save_cache(df)
    return df

def _build_histories_from_cache(df, sectors):
    histories = {}
    for item in sectors:
        display = item["display"]
        part = df[df["sector"] == display].copy()
        if part.empty:
            histories[display] = []
            continue
        part["date"] = pd.to_datetime(part["date"], errors="coerce")
        part = part.dropna(subset=["date"]).sort_values("date")
        histories[display] = [{
            "date": d.strftime("%Y-%m-%d"),
            "open": r.get("open"),
            "high": r.get("high"),
            "low": r.get("low"),
            "close": r.get("close"),
            "pct": r.get("pct"),
            "amount": r.get("amount"),
            "volume": r.get("volume"),
            "turnover": r.get("turnover")
        } for d, r in zip(part["date"], part.to_dict(orient="records"))]
    return histories

def _append_benchmark_rows(df, days=60):
    hist = get_index_history("sh000001", days=days)
    if not hist:
        return df
    rows = []
    for h in hist:
        rows.append({
            "date": h.get("date"),
            "sector": DEFAULT_BENCHMARK,
            "code": "sh000001",
            "type": "index",
            "pct": h.get("pct"),
            "amount": h.get("amount"),
            "volume": h.get("volume"),
            "turnover": h.get("turnover"),
            "open": h.get("open"),
            "high": h.get("high"),
            "low": h.get("low"),
            "close": h.get("close")
        })
    bdf = pd.DataFrame(rows)
    if bdf.empty:
        return df
    return pd.concat([df, bdf], ignore_index=True)

def _build_indicators_from_cache(df, sectors, days=20):
    clean_mod, features_mod = _load_quant_modules()
    if not clean_mod or not features_mod:
        return {}
    work = df.copy()
    if "date" in work.columns:
        work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.dropna(subset=["date", "sector"])
    work = clean_mod.clean_for_features(work, DEFAULT_BENCHMARK)
    work["bench_name"] = DEFAULT_BENCHMARK
    work = features_mod.rolling_returns(work)
    work = features_mod.amount_share(work)
    work = features_mod.dynamic_benchmark_metrics(work, [DEFAULT_BENCHMARK])
    work["date_str"] = work["date"].dt.strftime("%Y-%m-%d")
    work = work.sort_values("date")
    indicators = {}
    for item in sectors:
        display = item["display"]
        part = work[work["sector"] == display]
        if part.empty:
            indicators[display] = []
            continue
        tail = part.tail(days)
        rows = []
        for _, r in tail.iterrows():
            price = r.get("close")
            alpha_10 = r.get("alpha_10")
            alpha_5 = r.get("alpha_5")
            alpha = alpha_10 if pd.notna(alpha_10) else alpha_5
            amount_share_pct = r.get("amount_share_pct")
            rows.append({
                "date": r.get("date_str"),
                "price": None if pd.isna(price) else float(price),
                "alpha": None if pd.isna(alpha) else float(round(alpha, 3)),
                "amount_share_pct": None if pd.isna(amount_share_pct) else float(round(amount_share_pct, 2)),
                "alpha_5": None if pd.isna(alpha_5) else float(round(alpha_5, 3)),
                "alpha_10": None if pd.isna(alpha_10) else float(round(alpha_10, 3))
            })
        indicators[display] = rows
    return indicators

def _lifecycle_stage(score):
    if score < 20:
        return "冰点"
    if score < 40:
        return "衰退"
    if score < 60:
        return "启动"
    if score < 80:
        return "主升"
    return "亢奋"

def calculate_lifecycle_score(cum20, dd10, pct, amount_share_pct, alpha_10=None, alpha_5=None):
    cum20 = float(cum20) if pd.notna(cum20) else 0
    dd10 = float(dd10) if pd.notna(dd10) else 0
    pct = float(pct) if pd.notna(pct) else 0
    share = float(amount_share_pct) if pd.notna(amount_share_pct) else 0
    if cum20 >= 0.15:
        base = 100
    elif cum20 >= 0.08:
        base = 80
    elif cum20 >= 0.03:
        base = 60
    elif cum20 >= -0.03:
        base = 40
    elif cum20 >= -0.08:
        base = 20
    else:
        base = 0
    if dd10 <= 0.05:
        dec = 0
    elif dd10 <= 0.10:
        dec = 10
    elif dd10 <= 0.20:
        dec = 25
    else:
        dec = 40
    if dd10 > 0.08:
        dec = dec * 2
    trend = max(0, base - dec)
    if share >= 1.2:
        flow = 100
    elif share >= 0.9:
        flow = 80
    elif share >= 0.6:
        flow = 60
    elif share >= 0.4:
        flow = 40
    elif share >= 0.2:
        flow = 20
    else:
        flow = 0
    if pct < 0:
        flow = max(0, flow - 10)
    alpha10 = None
    if pd.notna(alpha_10):
        alpha10 = float(alpha_10)
    alpha_val = alpha_10 if pd.notna(alpha_10) else alpha_5
    alpha_val = float(alpha_val) if pd.notna(alpha_val) else 0
    if alpha_val >= 3:
        alpha = 100
    elif alpha_val >= 1:
        alpha = 80
    elif alpha_val >= 0:
        alpha = 60
    elif alpha_val >= -1:
        alpha = 40
    elif alpha_val >= -3:
        alpha = 20
    else:
        alpha = 0
    penalty = 0
    blackhole = pct < 0 and share > 80
    if blackhole:
        flow = 0
        penalty -= 20
    if alpha10 is not None and alpha10 < -2:
        penalty -= 30
    score = 0.45 * trend + 0.30 * flow + 0.25 * alpha + penalty
    score = round(max(0, min(100, score)), 1)
    stage = _lifecycle_stage(score)
    if alpha10 is not None and alpha10 < -2 and stage in ["主升", "亢奋"]:
        stage = "启动"
    return {
        "score": score,
        "stage": stage,
        "trend": trend,
        "flow": flow,
        "alpha": alpha,
        "penalty": penalty
    }

def _normalize_amount_share(val):
    if pd.isna(val):
        return 0
    v = float(val)
    if v > 1.5:
        v = v / 100
    return v

def _stage_meta():
    return {
        "1": {
            "name": "冰点·无人问津",
            "logic": "Alpha 极负；Amount 跌至地量且波动极小，市场遗忘。",
            "intent": "弃庄，板块流动性枯竭。",
            "advice": "坚决空仓"
        },
        "2": {
            "name": "磨底·低位吸筹",
            "logic": "Alpha 负值收窄；出现红肥绿瘦（阳线放量，阴线极缩）。",
            "intent": "潜伏入场，悄悄低位拿货。",
            "advice": "左侧小仓埋伏"
        },
        "2.2": {
            "name": "双底·黄金坑",
            "logic": "二次探底不破前低，且二次探底量能更小，反弹分时稳步放量。",
            "intent": "技术性二次确认底价，彻底洗清不坚定筹码。",
            "advice": "分批加仓建仓"
        },
        "3": {
            "name": "异动·试盘确认",
            "logic": "脉冲式放量冲高后快速缩量回踩，不破前期低点。",
            "intent": "向上测试抛压，清理浮筹。",
            "advice": "建立轻仓底仓"
        },
        "4": {
            "name": "初始·强势启动",
            "logic": "Alpha 暴力转正；Amount 环比激增 >50%；站稳 5 日线。",
            "intent": "进攻号角，脱离成本区。",
            "advice": "重仓介入追强"
        },
        "5": {
            "name": "稳健·主升浪",
            "logic": "Alpha 持续为正；Amount 稳定在 30%-70% 黄金区。",
            "intent": "趋势自我强化，主力锁仓良好。",
            "advice": "持股待涨"
        },
        "6": {
            "name": "加速·极度亢奋",
            "logic": "Amount>90%；偏离均线过远（Bias_5>5%），连续大阳。",
            "intent": "情绪过热，吸引散户接盘。",
            "advice": "严格分批止盈"
        },
        "7.1": {
            "name": "滞涨·高位派发",
            "logic": "Amount 爆表但价格滞涨；出现长上影线或放量十字星。",
            "intent": "主力诱多出货，筹码交换。",
            "advice": "清仓离场"
        },
        "7.2": {
            "name": "双头·无影出货",
            "logic": "价格回前高无影线，但 Alpha 强度弱于前高，成交占比更高。",
            "intent": "假突破陷阱，利用买盘撤离。",
            "advice": "见前高必减/清仓"
        },
        "8": {
            "name": "洗盘·高位回踩",
            "logic": "极速缩量下跌；Alpha 保持在 0 轴附近；不破关键支撑位。",
            "intent": "强势板块的二次换手洗筹。",
            "advice": "二次确信买点"
        },
        "9": {
            "name": "衰退·黑洞崩塌",
            "logic": "放量大跌；Alpha 快速转负；跌破 10 日均线。",
            "intent": "机构砸盘，不计成本离场。",
            "advice": "坚决回避/止损"
        },
        "10": {
            "name": "阴跌·流动失血",
            "logic": "Alpha 持续恶化；Amount 逐日萎缩；阴火烧尽。",
            "intent": "漫漫阴跌路，资金持续流出。",
            "advice": "空仓观望"
        }
    }

def _red_fat_green_thin(pcts, ratios):
    red = 0
    green = 0
    for p, r in zip(pcts, ratios):
        if p > 0 and r >= 1.2:
            red += 1
        if p < 0 and r <= 0.7:
            green += 1
    return red >= 2 and green >= 2

def build_sector_stage_table(df, sector_name):
    meta = _stage_meta()
    part = df[df["sector"] == sector_name].copy()
    if part.empty:
        return []
    part["date"] = pd.to_datetime(part["date"], errors="coerce")
    part = part.dropna(subset=["date"]).sort_values("date")
    part["pct"] = pd.to_numeric(part["pct"], errors="coerce").fillna(0)
    part["amount"] = pd.to_numeric(part["amount"], errors="coerce").fillna(0)
    part["close"] = pd.to_numeric(part["close"], errors="coerce").ffill().fillna(0)
    part["amount_ma5"] = part["amount"].rolling(5).mean()
    part["amount_ratio"] = part["amount"] / part["amount_ma5"].replace(0, pd.NA)
    part["amount_ratio"] = part["amount_ratio"].fillna(0)
    part["ma5"] = part["close"].rolling(5).mean()
    part["ma10"] = part["close"].rolling(10).mean()
    part["bias_5"] = (part["close"] / part["ma5"] - 1) * 100
    part["low20"] = part["close"].rolling(20).min()
    part["high20"] = part["close"].rolling(20).max()
    part["share"] = part.get("amount_share_pct", 0).apply(_normalize_amount_share)
    part["alpha"] = part["alpha_10"]
    part.loc[pd.isna(part["alpha"]), "alpha"] = part["alpha_5"]
    part["alpha"] = pd.to_numeric(part["alpha"], errors="coerce").fillna(0)
    rows = []
    prev_high = None
    prev_low = None
    for i in range(len(part)):
        row = part.iloc[i]
        next_row = part.iloc[i + 1] if i + 1 < len(part) else None
        date_str = row["date"].strftime("%Y-%m-%d")
        pct = row["pct"]
        amount_ratio = row["amount_ratio"]
        alpha = row["alpha"]
        share = row["share"]
        close = row["close"]
        ma5 = row["ma5"]
        ma10 = row["ma10"]
        bias5 = row["bias_5"]
        low20 = row["low20"]
        high20 = row["high20"]
        if pd.notna(high20) and close >= high20 * 0.995:
            prev_high = {
                "date": row["date"],
                "price": close,
                "alpha": alpha,
                "share": share,
                "amount_ratio": amount_ratio
            }
        if pd.notna(low20) and close <= low20 * 1.005:
            prev_low = {
                "date": row["date"],
                "price": close,
                "amount_ratio": amount_ratio,
                "alpha": alpha
            }
        stage_id = "2"
        if pct <= -3 and alpha < 0 and pd.notna(ma10) and close < ma10 and amount_ratio >= 1.3:
            stage_id = "9"
        elif alpha <= -2 and amount_ratio <= 0.8 and pct < 0:
            stage_id = "10"
        elif abs(pct) <= 0.5 and amount_ratio <= 0.5 and alpha <= -2:
            stage_id = "1"
        elif prev_high and pd.notna(high20) and close >= prev_high["price"] * 0.995 and (row["date"] - prev_high["date"]).days <= 20 and (row["date"] - prev_high["date"]).days >= 5 and alpha < prev_high["alpha"] - 0.3 and share > prev_high["share"] and amount_ratio >= prev_high["amount_ratio"] * 1.1 and abs(pct) <= 1.5:
            stage_id = "7.2"
        elif pd.notna(high20) and close >= high20 * 0.97 and amount_ratio >= 1.5 and abs(pct) <= 1:
            stage_id = "7.1"
        elif share >= 0.9 and bias5 >= 5 and part["pct"].iloc[max(0, i - 2): i + 1].gt(0).sum() >= 2:
            stage_id = "6"
        elif amount_ratio <= 0.7 and abs(alpha) <= 0.5 and pd.notna(ma10) and close >= ma10 * 0.98:
            stage_id = "8"
        elif alpha > 0 and share >= 0.3 and share <= 0.7 and pd.notna(ma5) and pd.notna(ma10) and close > ma5 and ma5 > ma10:
            stage_id = "5"
        elif alpha >= 1 and amount_ratio >= 1.5 and pd.notna(ma5) and close >= ma5:
            stage_id = "4"
        else:
            if next_row is not None:
                next_pct = next_row["pct"]
                next_amount_ratio = next_row["amount_ratio"]
                if pct >= 2 and amount_ratio >= 1.8 and next_pct < 0 and next_amount_ratio <= 0.8 and pd.notna(low20) and close >= low20 * 1.05:
                    stage_id = "3"
            if stage_id == "2":
                if prev_low and (row["date"] - prev_low["date"]).days >= 5 and (row["date"] - prev_low["date"]).days <= 35 and close >= prev_low["price"] * 0.99 and close <= prev_low["price"] * 1.02 and amount_ratio <= prev_low["amount_ratio"] * 0.85 and alpha >= prev_low["alpha"] - 0.2:
                    if next_row is None:
                        stage_id = "2.2"
                    else:
                        next_pct = next_row["pct"]
                        next_amount_ratio = next_row["amount_ratio"]
                        if next_pct >= 0.3 and next_amount_ratio >= amount_ratio * 1.05:
                            stage_id = "2.2"
                else:
                    pcts = part["pct"].iloc[max(0, i - 4): i + 1].tolist()
                    ratios = part["amount_ratio"].iloc[max(0, i - 4): i + 1].tolist()
                    if not (alpha < 0 and _red_fat_green_thin(pcts, ratios)):
                        stage_id = "2"
        meta_row = meta.get(stage_id, meta["2"])
        rows.append({
            "日期": date_str,
            "阶段序号": stage_id,
            "阶段名称": meta_row["name"],
            "核心判定逻辑": meta_row["logic"],
            "主力意图识别": meta_row["intent"],
            "操盘策略建议": meta_row["advice"]
        })
    return rows

def get_sector_payload(sector_items, indicator_days=20):
    sectors = _normalize_sectors(sector_items)
    if not sectors:
        sectors = _normalize_sectors(DEFAULT_SECTORS)
    df = _load_cache()
    if df is None or df.empty or _market_closed_now():
        df = _update_sector_cache(sectors, ensure_days=indicator_days)
    histories = _build_histories_from_cache(df, sectors)
    df_with_bench = _append_benchmark_rows(df, days=max(indicator_days * 3, 60))
    indicators = _build_indicators_from_cache(df_with_bench, sectors, indicator_days)
    minutes = {}
    for item in sectors:
        display = item["display"]
        name = item["name"]
        hist = histories.get(display) or []
        prev_close = hist[-1].get("close") if hist else None
        series = get_sector_minute(name)
        minutes[display] = {"series": series, "prevClose": prev_close}
    correlations = calculate_correlations(histories)
    return {
        "history": histories,
        "indicators": indicators,
        "indicator_days": indicator_days,
        "minute": minutes,
        "correlations": correlations,
        "watch": [s["display"] for s in sectors]
    }

def _to_date_str(val):
    try:
        return pd.to_datetime(val).strftime("%Y-%m-%d")
    except:
        return None

def _build_daily_result(df, days):
    if df is None or df.empty:
        return None
    if "date" in df.columns:
        df = df.rename(columns={"date": "日期"})
    if "日期" not in df.columns:
        return None
    df = df.copy()
    df["日期"] = pd.to_datetime(df["日期"])
    df = df.sort_values("日期", ascending=True)
    df = df[df["日期"] >= pd.to_datetime(START_DATE)]
    if "涨跌幅" not in df.columns:
        if "收盘" in df.columns:
            df["涨跌幅"] = df["收盘"].pct_change() * 100
        else:
            df["涨跌幅"] = None
    if "成交额" not in df.columns:
        df["成交额"] = df.get("amount", 0)
    if "成交量" not in df.columns:
        df["成交量"] = df.get("volume", 0)
    if "换手率" not in df.columns:
        if "turnover" in df.columns:
            df["换手率"] = df["turnover"]
        else:
            df["换手率"] = None
    if "开盘" not in df.columns:
        df["开盘"] = df.get("open", None)
    if "最高" not in df.columns:
        df["最高"] = df.get("high", None)
    if "最低" not in df.columns:
        df["最低"] = df.get("low", None)
    result = []
    for _, row in df.iterrows():
        result.append({
            "date": row["日期"].strftime("%Y-%m-%d"),
            "open": row.get("开盘"),
            "high": row.get("最高"),
            "low": row.get("最低"),
            "close": row.get("收盘"),
            "pct": row.get("涨跌幅"),
            "amount": row.get("成交额"),
            "volume": row.get("成交量"),
            "turnover": row.get("换手率")
        })
    return result

def _find_col(df, names):
    for c in df.columns:
        lc = str(c).strip().lower()
        for n in names:
            if lc == n:
                return c
    for n in names:
        for c in df.columns:
            if n in str(c):
                return c
    return None

def get_sector_minute(sector_name):
    df = None
    try:
        df = ak.stock_board_industry_hist_min_em(symbol=sector_name, period="1")
    except:
        df = pd.DataFrame()
    if df is None or df.empty:
        try:
            df = ak.stock_board_concept_hist_min_em(symbol=sector_name, period="1")
        except:
            df = pd.DataFrame()
    if df is None or df.empty:
        return []
    time_col = _find_col(df, ["时间", "日期", "datetime", "time"])
    open_col = _find_col(df, ["开盘", "开盘价", "open"])
    close_col = _find_col(df, ["收盘", "收盘价", "close"])
    if not time_col or not open_col or not close_col:
        return []
    df = df.sort_values(time_col, ascending=True)
    out = []
    for _, row in df.iterrows():
        try:
            t = str(row[time_col])[:16]
            op = float(row[open_col])
            cl = float(row[close_col])
        except:
            continue
        out.append({"time": t, "open": op, "close": cl})
    if not out:
        return []
    last_day = str(out[-1]["time"]).split(" ")[0]
    if not last_day:
        return out
    return [p for p in out if str(p.get("time", "")).startswith(last_day)]

def get_index_history(symbol, days=180):
    df = None
    try:
        code = symbol.replace("sh", "").replace("sz", "")
        df = ak.index_zh_a_hist(symbol=code, period="daily", start_date=START_DATE, end_date=datetime.now().strftime("%Y%m%d"))
    except:
        df = None
    if df is None or df.empty:
        try:
            try:
                df = ak.stock_zh_index_daily_em(symbol=code, start_date=START_DATE, end_date=datetime.now().strftime("%Y%m%d"))
            except TypeError:
                df = ak.stock_zh_index_daily_em(symbol=code)
        except:
            df = None
    if df is None or df.empty:
        return None
    if "date" in df.columns and "日期" not in df.columns:
        df = df.rename(columns={"date": "日期"})
    if "close" in df.columns and "收盘" not in df.columns:
        df = df.rename(columns={"close": "收盘"})
    if "volume" in df.columns and "成交量" not in df.columns:
        df = df.rename(columns={"volume": "成交量"})
    if "amount" in df.columns and "成交额" not in df.columns:
        df = df.rename(columns={"amount": "成交额"})
    if "turnover" in df.columns and "换手率" not in df.columns:
        df = df.rename(columns={"turnover": "换手率"})
    df = _build_daily_result(df, days)
    if df:
        df = [d for d in df if d.get("date") and d.get("date") >= "2015-05-27"]
    return df

def get_futures_daily(symbol, days=180):
    df = None
    for s in [symbol, f"{symbol}0", f"{symbol}1"]:
        try:
            df = ak.futures_zh_daily_sina(symbol=s)
        except:
            df = None
        if df is not None and not df.empty:
            break
    if df is None or df.empty:
        return None
    if "date" in df.columns and "日期" not in df.columns:
        df = df.rename(columns={"date": "日期"})
    if "close" in df.columns and "收盘" not in df.columns:
        df = df.rename(columns={"close": "收盘"})
    if "volume" in df.columns and "成交量" not in df.columns:
        df = df.rename(columns={"volume": "成交量"})
    if "amount" in df.columns and "成交额" not in df.columns:
        df = df.rename(columns={"amount": "成交额"})
    if "turnover" in df.columns and "换手率" not in df.columns:
        df = df.rename(columns={"turnover": "换手率"})
    return _build_daily_result(df, days)

def build_daily_csv(days=180, out_path=None):
    if out_path is None:
        day = datetime.now().strftime("%Y%m%d")
        out_path = f"data/sector-daily-{day}.csv"
    rows = []
    for item in SECTOR_MAPPING:
        hist = get_sector_history(item["name"], days=days)
        if not hist:
            continue
        for h in hist:
            rows.append({
                "date": h.get("date"),
                "sector": item["display"],
                "code": item["code"],
                "type": "sector",
                "open": h.get("open"),
                "high": h.get("high"),
                "low": h.get("low"),
                "pct": h.get("pct"),
                "amount": h.get("amount"),
                "volume": h.get("volume"),
                "turnover": h.get("turnover"),
                "close": h.get("close")
            })

    index_map = {
        "上证": {"symbol": "sh000001"},
        "深证": {"symbol": "sz399001"},
        "创业板": {"symbol": "sz399006"},
        "科创板": {"symbol": "1B0680"}
    }
    index_hist = {}
    for name, item in index_map.items():
        hist = get_index_history(item["symbol"], days=days)
        if not hist:
            continue
        index_hist[name] = hist
        for h in hist:
            rows.append({
                "date": h.get("date"),
                "sector": name,
                "code": item["symbol"],
                "type": "index",
                "open": h.get("open"),
                "high": h.get("high"),
                "low": h.get("low"),
                "pct": h.get("pct"),
                "amount": h.get("amount"),
                "volume": h.get("volume"),
                "turnover": h.get("turnover"),
                "close": h.get("close")
            })
    market_rows = build_market_amount_rows(index_hist.get("上证"), index_hist.get("深证"))
    if market_rows:
        for h in market_rows:
            rows.append({
                "date": h.get("date"),
                "sector": "沪深成交额",
                "code": "SHSZ_TOTAL",
                "type": "market",
                "open": None,
                "high": None,
                "low": None,
                "pct": None,
                "amount": h.get("amount"),
                "volume": None,
                "turnover": None,
                "close": None
            })

    bond_map = {
        "10年国债": {"symbol": "T"},
        "30年国债": {"symbol": "TL"}
    }
    for name, item in bond_map.items():
        hist = get_futures_daily(item["symbol"], days=days)
        if not hist:
            continue
        for h in hist:
            rows.append({
                "date": h.get("date"),
                "sector": name,
                "code": item["symbol"],
                "type": "bond",
                "open": h.get("open"),
                "high": h.get("high"),
                "low": h.get("low"),
                "pct": h.get("pct"),
                "amount": h.get("amount"),
                "volume": h.get("volume"),
                "turnover": h.get("turnover"),
                "close": h.get("close")
            })

    if not rows:
        return None
    df = pd.DataFrame(rows)
    df = df.dropna(subset=["date", "sector"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["date", "sector"])
    df.to_csv(out_path, index=False)
    return out_path

def _read_minute_file(path):
    rows = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                arr = json.loads(line)
            except:
                continue
            if not isinstance(arr, list) or len(arr) < 3:
                continue
            t = arr[0]
            op = arr[1]
            cl = arr[2]
            rows.append((t, op, cl))
    if not rows:
        return None
    rows.sort(key=lambda x: x[0])
    first = rows[0][1]
    last = rows[-1][2]
    if first is None or last is None:
        return None
    if first == 0:
        pct = None
    else:
        pct = (last - first) / first * 100
    day = rows[-1][0].split(" ")[0]
    return {
        "date": day,
        "pct": pct,
        "amount": 0,
        "volume": 0,
        "turnover": 0
    }

def build_market_amount_rows(sh_hist, sz_hist):
    if not sh_hist and not sz_hist:
        return None
    rows = {}
    def add(hist):
        if not hist:
            return
        for h in hist:
            d = h.get("date")
            amt = h.get("amount")
            try:
                v = float(amt) if amt is not None else 0
            except:
                v = 0
            rows.setdefault(d, 0)
            rows[d] += v
    add(sh_hist)
    add(sz_hist)
    out = []
    for d, v in rows.items():
        out.append({"date": d, "amount": v if v > 0 else None})
    out.sort(key=lambda x: x["date"])
    return out

def build_daily_from_minute(code, data_dir="data"):
    items = []
    for name in os.listdir(data_dir):
        if not name.startswith("minute-") or f"-{code}.jsonl" not in name:
            continue
        path = os.path.join(data_dir, name)
        item = _read_minute_file(path)
        if item:
            items.append(item)
    items.sort(key=lambda x: x["date"])
    return items or None

def get_top_sectors_rank():
    try:
        # 1. Try real-time fund flow first (best data)
        try:
            # ak.stock_market_fund_flow_industry might be removed or renamed in new akshare versions
            # Use `stock_fund_flow_industry` if available or `stock_sector_fund_flow_rank`
            # Based on dir(ak), `stock_fund_flow_industry` exists.
            df_flow = ak.stock_fund_flow_industry(symbol="即时")
        except:
            # Fallback to older method or similar
            try:
                df_flow = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
            except:
                df_flow = None

        if df_flow is None or df_flow.empty:
            raise ValueError("No real-time flow data")

        # Sort by Change% descending
        df_flow["今日涨跌幅"] = pd.to_numeric(df_flow["今日涨跌幅"], errors='coerce')
        df_flow = df_flow.sort_values("今日涨跌幅", ascending=False)
        
        top10_up = df_flow.head(10)
        top10_down = df_flow.nsmallest(10, "今日涨跌幅")
        
        def format_rows(df_in):
            res = []
            for _, row in df_in.iterrows():
                res.append({
                    "name": row["名称"],
                    "pct": row["今日涨跌幅"], 
                    "net_inflow": row["主力净流入-净额"] 
                })
            return res
            
        return {
            "up": format_rows(top10_up),
            "down": format_rows(top10_down)
        }
    except Exception as e:
        # Fallback: Use basic industry rank (No Net Inflow)
        # This usually returns the latest available snapshot (e.g. Friday close if today is Sunday)
        try:
            df = ak.stock_board_industry_name_em()
            if df.empty: return {"up": [], "down": []}
            
            df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors='coerce')
            df = df.sort_values("涨跌幅", ascending=False)
            
            top10_up = df.head(10)
            top10_down = df.nsmallest(10, "涨跌幅")
            
            def format_rows_fallback(df_in):
                res = []
                for _, row in df_in.iterrows():
                    res.append({
                        "name": row["板块名称"],
                        "pct": row["涨跌幅"],
                        "net_inflow": None # Missing in this source
                    })
                return res
            
            return {
                "up": format_rows_fallback(top10_up),
                "down": format_rows_fallback(top10_down)
            }
        except:
            return {"up": [], "down": []}

def calculate_correlations(histories):
    # Prepare DataFrame for correlation
    data = {}
    for name, hist in histories.items():
        if not hist: continue
        dates = [h['date'] for h in hist]
        closes = [h['close'] for h in hist]
        s = pd.Series(closes, index=dates)
        data[name] = s
        
    if not data:
        return []

    df = pd.DataFrame(data)
    # df.fillna(method='ffill') is deprecated
    df = df.ffill().dropna()
    
    corr_matrix = df.corr(method='pearson')
    
    pairs = []
    columns = corr_matrix.columns
    mat = corr_matrix.to_numpy()
    for i in range(len(columns)):
        for j in range(i+1, len(columns)):
            c1 = columns[i]
            c2 = columns[j]
            val = mat[i, j]
            if val < -0.3: # Threshold for "Seesaw"
                pairs.append({
                    "pair": [c1, c2],
                    "val": round(val, 3)
                })
    
    pairs.sort(key=lambda x: x['val'])
    return pairs[:5]

def get_market_breadth():
    """
    Fetch market breadth (Advance/Decline count)
    Using ak.stock_zh_a_spot_em() is too slow (paginated).
    Alternative: ak.stock_sse_summary() and ak.stock_szse_summary()
    Or just use a faster spot interface if available.
    Trying ak.stock_sh_a_spot_em() and ak.stock_sz_a_spot_em() might be faster?
    Actually, let's try to get a quick snapshot.
    """
    try:
        # Optimistic approach: Use real-time simplified snapshot if possible.
        # But for now, let's just return a placeholder or try to fetch smaller chunks.
        # Actually, let's use the fund flow interface which might have summary.
        # No, fund flow is for money.
        
        # Fast method: use Shanghai and Shenzhen summary
        # ak.stock_sse_summary() -> type, item, value
        # ak.stock_szse_summary() -> 
        
        # Let's try ak.stock_zh_a_spot_em() but with specific columns to speed up? No.
        # Let's try to use `ak.stock_zh_a_spot_em` but it prints progress bar which corrupts JSON.
        # We must suppress stdout or use a different function.
        
        # Actually, `ak.stock_zh_a_spot_em` is just slow.
        # Let's try `ak.stock_info_sh_name_code` and `ak.stock_info_sz_name_code` to just get list?
        # No we need change %.
        
        # FASTEST WAY: 
        # Use `ak.stock_zh_a_spot_em` but silence it? No, it takes time.
        
        # Let's use `ak.stock_sse_summary()`
        # It usually contains "Total Listed", "Total Market Cap", etc. Not Up/Down count.
        
        # Let's fall back to a smaller sample or just skip if too slow.
        # Wait, for "Market Sentiment", maybe we just check the top 300 (HS300) as a proxy?
        # ak.stock_zh_index_spot_em(symbol="沪深300") -> components?
        
        # Let's try `ak.stock_zh_a_spot_em` again but accept it might take 5-10s.
        # To avoid progress bar affecting JSON, we need to capture stderr or silence it.
        # But it's too slow for UI.
        
        # Alternative: `ak.stock_zh_a_new_em()` is new stocks.
        
        # Let's try `ak.stock_zh_a_spot_em` but only first page? Not supported.
        
        # REVISED STRATEGY: 
        # Fetch `ak.stock_zh_a_spot_em` is the only way to get full market breadth in Akshare easily.
        # But we need to suppress the progress bar output to stdout!
        # The progress bar goes to stderr usually.
        
        # Let's try `ak.stock_zh_a_spot_em` again.
        pass
    except:
        pass

    # New Attempt: Use `ak.stock_zh_a_spot_em` but suppress output
    # And maybe cache it?
    
    # Actually, let's just return a dummy for now to verify UI, 
    # OR better: use a different source if possible. 
    # Let's try `ak.stock_zh_a_spot_em` but catch the progress bar.
    
    try:
        # Redirect stderr to devnull to hide progress bar
        import os
        
        # This function is known to be slow. 
        # Let's use `ak.stock_zh_a_spot_em`
        # Note: In recent Akshare, this might be faster or use `fast=True`?
        # No such param.
        
        # Let's try a different API: `ak.stock_sh_a_spot_em()` and `ak.stock_sz_a_spot_em()` separately?
        # Same underlying logic.
        
        # Let's try fetching just the Main Board?
        
        # For now, to make it work quickly:
        # We will use `ak.stock_zh_a_spot_em` but we need to ensure it doesn't break JSON.
        # And we accept the delay (async on client).
        
        # Capture stderr
        from io import StringIO
        old_stderr = sys.stderr
        sys.stderr = StringIO()
        
        df = ak.stock_zh_a_spot_em()
        
        sys.stderr = old_stderr
        
        if df.empty:
            return None
            
        # Ensure numeric
        df['涨跌幅'] = pd.to_numeric(df['涨跌幅'], errors='coerce')
        
        up = len(df[df['涨跌幅'] > 0])
        down = len(df[df['涨跌幅'] < 0])
        flat = len(df[df['涨跌幅'] == 0])
        
        return {
            "up": up,
            "down": down,
            "flat": flat,
            "total": len(df)
        }
    except Exception as e:
        sys.stderr = sys.__stderr__ # Restore just in case
        return None

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No command"}))
        return

    cmd = sys.argv[1]
    days = 180
    indicator_days = 20
    out_path = None
    if len(sys.argv) >= 3:
        try:
            days = int(sys.argv[2])
        except:
            days = 180
    if len(sys.argv) >= 4:
        out_path = sys.argv[3]
    
    if cmd == "rank":
        data = get_top_sectors_rank()
        print(json.dumps(data, ensure_ascii=False))
    
    elif cmd == "breadth":
        data = get_market_breadth()
        print(json.dumps(data, ensure_ascii=False))
        
    elif cmd == "history":
        if len(sys.argv) >= 3:
            try:
                indicator_days = int(sys.argv[2])
            except:
                indicator_days = 20
        payload = get_sector_payload(DEFAULT_SECTORS, indicator_days)
        print(json.dumps(payload, ensure_ascii=False))
    elif cmd == "history_dynamic":
        raw = sys.argv[2] if len(sys.argv) >= 3 else ""
        items = _parse_sector_arg(raw)
        if len(sys.argv) >= 4:
            try:
                indicator_days = int(sys.argv[3])
            except:
                indicator_days = 20
        payload = get_sector_payload(items, indicator_days)
        print(json.dumps(payload, ensure_ascii=False))
    elif cmd == "daily_csv":
        out = build_daily_csv(days=days, out_path=out_path)
        print(json.dumps({"out": out}, ensure_ascii=False))

if __name__ == "__main__":
    main()
