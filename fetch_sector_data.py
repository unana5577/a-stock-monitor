import akshare as ak
import pandas as pd
import json
import sys
import os
import importlib.util
from datetime import datetime
from zoneinfo import ZoneInfo
from sector_lifecycle import analyze_sector, select_dynamic_benchmark

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
PROFILE_FILE = os.path.join("data", "sector-profile.json")
PROFILE_EXAMPLE_FILE = os.path.join("data", "sector-profile.example.json")
TRIGGER_RULES_FILE = os.path.join("data", "trigger-rules.json")
ROTATION_CALIB_PATH = os.path.join("data", "rotation-calibration.json")
ROTATION_REPORT_PATH = os.path.join("data", "rotation-backtest-report.json")
NEWS_DIR = os.path.join("data", "news")
DEFAULT_SECTORS = ["半导体", "云计算", "新能源", "商业航天", "创新药", "有色金属", "煤炭", "电力", "通讯设备"]
DEFAULT_BENCHMARK = "上证"
DEFAULT_GROUPS = {
    "科技:硬件": ["半导体", "通讯设备"],
    "科技:软件": ["云计算"],
    "资源:上游": ["有色金属", "煤炭", "电力"],
    "科技:成长": ["商业航天", "创新药"],
    "金融": ["银行"]
}

_FETCH_ERRORS = {"daily": {}, "minute": {}}

def _read_json_file(path):
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

def load_sector_groups():
    def normalize_groups(groups):
        out = {}
        if not isinstance(groups, dict):
            return out
        for k, v in groups.items():
            if not isinstance(v, list):
                continue
            name = str(k).strip()
            if not name:
                continue
            vals = []
            for x in v:
                s = str(x).strip()
                if not s:
                    continue
                if s not in vals:
                    vals.append(s)
            if vals:
                out[name] = vals
        return out

    def expand_prefixes(groups):
        out = {}
        for name, vals in groups.items():
            parts = [p.strip() for p in str(name).split(":") if p.strip()]
            if not parts:
                continue
            prefix = ""
            for i, part in enumerate(parts):
                prefix = part if i == 0 else f"{prefix}:{part}"
                if prefix not in out:
                    out[prefix] = []
                for s in vals:
                    if s not in out[prefix]:
                        out[prefix].append(s)
        return out

    obj = _read_json_file(PROFILE_FILE)
    groups = obj.get("groups") if isinstance(obj, dict) else None
    if not isinstance(groups, dict):
        obj = _read_json_file(PROFILE_EXAMPLE_FILE)
        groups = obj.get("groups") if isinstance(obj, dict) else None
    base = normalize_groups(groups)
    if base:
        expanded = expand_prefixes(base)
        if expanded:
            return expanded
        return base
    return expand_prefixes(DEFAULT_GROUPS)

def _latest_news_file():
    if not os.path.isdir(NEWS_DIR):
        return None
    files = []
    for name in os.listdir(NEWS_DIR):
        path = os.path.join(NEWS_DIR, name)
        if os.path.isdir(path):
            continue
        if not name.endswith(".json"):
            continue
        if len(name) < 10:
            continue
        files.append(path)
    if not files:
        return None
    files.sort()
    return files[-1]

def _load_news_items():
    path = _latest_news_file()
    if not path:
        return []
    obj = _read_json_file(path)
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict) and isinstance(obj.get("news"), list):
        return obj.get("news")
    return []

def _build_news_factor():
    items = _load_news_items()
    if not items:
        return {}
    weight = {"P0": 3.0, "P1": 2.0, "P2": 1.0, "P3": 0.5}
    out = {}
    for item in items:
        classify = item.get("classify") if isinstance(item, dict) else None
        if not isinstance(classify, dict):
            continue
        sector = str(classify.get("sector") or "").strip()
        if not sector:
            continue
        sentiment = _num(classify.get("sentiment"), 0.0)
        level = str(classify.get("level") or "")
        typ = str(classify.get("type") or "")
        w = weight.get(level, 1.0)
        score = sentiment * w
        title = str(item.get("title") or item.get("summary") or "").strip()
        tags = []
        if typ in ["地缘", "监管", "黑天鹅"]:
            tags.append(typ)
        if level == "P0" and sentiment < 0:
            tags.append("P0利空")
        entry = out.setdefault(sector, {"news_score": 0.0, "risk_tags": [], "titles": []})
        entry["news_score"] += score
        if title:
            entry["titles"].append({"title": title, "score": score})
        for t in tags:
            if t not in entry["risk_tags"]:
                entry["risk_tags"].append(t)
    for sector, entry in out.items():
        entry["news_score"] = round(float(entry["news_score"]), 3)
        titles = entry.get("titles") or []
        titles = sorted(titles, key=lambda x: abs(_num(x.get("score"), 0)), reverse=True)[:3]
        entry["top_titles"] = [t.get("title") for t in titles if t.get("title")]
        entry.pop("titles", None)
    return out

def _apply_news_gate(position, news_view):
    if not isinstance(position, dict):
        return position
    if not isinstance(news_view, dict):
        return position
    risk_tags = news_view.get("risk_tags") or []
    if not risk_tags:
        return position
    lo = _num(position.get("min"), 0.0)
    hi = _num(position.get("max"), 0.0)
    cap = 0.3 if "P0利空" in risk_tags or "黑天鹅" in risk_tags else 0.4
    hi = min(hi, cap)
    lo = min(lo, hi)
    position["min"] = round(float(_clamp(lo, 0.0, 1.0)), 2)
    position["max"] = round(float(_clamp(hi, 0.0, 1.0)), 2)
    return position

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
    return (datetime.now(ZoneInfo("Asia/Shanghai")) - pd.Timedelta(days=n)).strftime("%Y%m%d")

def _market_closed_now():
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if now.weekday() >= 5:
        return True
    if now.hour > 15:
        return True
    if now.hour == 15 and now.minute >= 30:
        return True
    return False

def _today_str():
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")

def _latest_cache_date(df):
    if df is None or df.empty or "date" not in df.columns:
        return None
    try:
        s = pd.to_datetime(df["date"], errors="coerce").dropna()
        if s.empty:
            return None
        return s.max().strftime("%Y-%m-%d")
    except:
        return None

def _need_cache_refresh(df):
    latest = _latest_cache_date(df)
    if not latest:
        return True
    return latest < _today_str()

def _build_daily_from_minute(series):
    if not series:
        return None
    vals = []
    for p in series:
        op = p.get("open")
        cl = p.get("close")
        if op is not None:
            vals.append(float(op))
        if cl is not None:
            vals.append(float(cl))
    if not vals:
        return None
    first = series[0]
    last = series[-1]
    date = str(last.get("time", "")).split(" ")[0] or str(first.get("time", "")).split(" ")[0]
    if not date:
        return None
    op = first.get("open") if first.get("open") is not None else first.get("close")
    cl = last.get("close") if last.get("close") is not None else last.get("open")
    if op is None or cl is None:
        return None
    op = float(op)
    cl = float(cl)
    pct = None
    if op != 0:
        pct = round((cl - op) / op * 100, 2)
    return {
        "date": date,
        "open": op,
        "high": max(vals),
        "low": min(vals),
        "close": cl,
        "pct": pct,
        "amount": None,
        "volume": None,
        "turnover": None
    }

def _merge_today(history, daily):
    hist = history or []
    if not daily:
        return hist
    if not hist:
        return [daily]
    last = hist[-1]
    if last.get("date") == daily.get("date"):
        hist[-1] = daily
    elif last.get("date") and daily.get("date") and last.get("date") < daily.get("date"):
        hist.append(daily)
    return hist

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
        err = None
        try:
            df = ak.stock_board_industry_hist_em(symbol=sector_name, start_date=start_date, end_date=end_date, period="日k")
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            df = pd.DataFrame()
        if df.empty:
            try:
                df = ak.stock_board_concept_hist_em(symbol=sector_name, start_date=start_date, end_date=end_date, period="daily")
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                df = pd.DataFrame()
        if df.empty:
            if err:
                _FETCH_ERRORS["daily"][str(sector_name)] = err
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
    except Exception as e:
        _FETCH_ERRORS["daily"][str(sector_name)] = f"{type(e).__name__}: {e}"
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
    today_dt = datetime.now(ZoneInfo("Asia/Shanghai"))
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
    index_map = {
        "上证": {"symbol": "sh000001"},
        "深证": {"symbol": "sz399001"},
        "创业板": {"symbol": "sz399006"},
        "科创板": {"symbol": "000688"}
    }
    rows = []
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
                "pct": h.get("pct"),
                "amount": h.get("amount"),
                "volume": h.get("volume"),
                "turnover": h.get("turnover"),
                "open": h.get("open"),
                "high": h.get("high"),
                "low": h.get("low"),
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
                "pct": None,
                "amount": h.get("amount"),
                "volume": None,
                "turnover": None,
                "open": None,
                "high": None,
                "low": None,
                "close": None
            })
    if not rows:
        return df
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
    _FETCH_ERRORS["daily"].clear()
    _FETCH_ERRORS["minute"].clear()
    sectors = _normalize_sectors(sector_items)
    if not sectors:
        sectors = _normalize_sectors(DEFAULT_SECTORS)
    df = _load_cache()
    if df is None or df.empty or _need_cache_refresh(df):
        df = _update_sector_cache(sectors, ensure_days=indicator_days)
    histories = _build_histories_from_cache(df, sectors)
    df_with_bench = _append_benchmark_rows(df, days=max(indicator_days * 3, 60))
    indicators = _build_indicators_from_cache(df_with_bench, sectors, indicator_days)
    minutes = {}
    for item in sectors:
        display = item["display"]
        name = item["name"]
        series = get_sector_minute(name)
        daily = _build_daily_from_minute(series)
        histories[display] = _merge_today(histories.get(display) or [], daily)
        hist = histories.get(display) or []
        prev_close = hist[-1].get("close") if hist else None
        minutes[display] = {"series": series, "prevClose": prev_close}
    correlations = calculate_correlations(histories)
    latest = None
    for arr in histories.values():
        if not isinstance(arr, list) or not arr:
            continue
        d = arr[-1].get("date")
        if d and (latest is None or str(d) > str(latest)):
            latest = str(d)
    return {
        "history": histories,
        "indicators": indicators,
        "indicator_days": indicator_days,
        "minute": minutes,
        "correlations": correlations,
        "watch": [s["display"] for s in sectors],
        "latest_date": latest,
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "source_errors": _json_sanitize(_FETCH_ERRORS)
    }

def _build_lifecycle_df(df, sector_name, days=60):
    part = df[df["sector"] == sector_name].copy()
    if part.empty:
        return None
    part["date"] = pd.to_datetime(part["date"], errors="coerce")
    part = part.dropna(subset=["date"]).sort_values("date")
    if days is not None:
        part = part.tail(days)
    part["close"] = pd.to_numeric(part.get("close"), errors="coerce").fillna(0)
    part["amount"] = pd.to_numeric(part.get("amount"), errors="coerce").fillna(0)
    return part[["date", "close", "amount"]]

def _build_pool_benchmark(df, sector_displays, days=180):
    if df is None or df.empty:
        return None
    work = df[df["sector"].isin(sector_displays)].copy()
    if work.empty:
        return None
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.dropna(subset=["date"]).sort_values("date")
    if days is not None:
        work = work.tail(days * max(1, len(set(sector_displays))))
    pivot = work.pivot_table(index="date", columns="sector", values="close", aggfunc="last").sort_index()
    if pivot.empty:
        return None
    pivot = pivot.ffill().dropna(how="all")
    if pivot.empty or len(pivot) < 2:
        return None
    rets = pivot.pct_change().fillna(0)
    bench_ret = rets.mean(axis=1)
    bench_close = (bench_ret + 1).cumprod() * 100
    amt = pd.to_numeric(work["amount"], errors="coerce").fillna(0)
    amt_sum = work.assign(amount_num=amt).groupby("date")["amount_num"].sum().reindex(bench_close.index).fillna(0)
    out = pd.DataFrame({"date": bench_close.index, "close": bench_close.values, "amount": amt_sum.values})
    if days is not None:
        out = out.tail(days)
    return out

def get_sector_lifecycle(sector_items, days=60):
    sectors = _normalize_sectors(sector_items)
    if not sectors:
        sectors = _normalize_sectors(DEFAULT_SECTORS)
    df = _load_cache()
    if df is None or df.empty or _need_cache_refresh(df):
        df = _update_sector_cache(sectors, ensure_days=days)
    df_with_bench = _append_benchmark_rows(df, days=max(days, 60))
    bench_days = max(days, 60)
    benchmark_map = {
        "上证": _build_lifecycle_df(df_with_bench, "上证", bench_days),
        "深证": _build_lifecycle_df(df_with_bench, "深证", bench_days),
        "创业板": _build_lifecycle_df(df_with_bench, "创业板", bench_days),
        "科创板": _build_lifecycle_df(df_with_bench, "科创板", bench_days)
    }
    market_amount_df = _build_lifecycle_df(df_with_bench, "沪深成交额", None)
    if all(v is None for v in benchmark_map.values()):
        pool_bench = _build_pool_benchmark(df, [s["display"] for s in sectors], days=bench_days)
        if pool_bench is None or pool_bench.empty:
            return {"items": [], "watch": [s["display"] for s in sectors]}
        benchmark_map = {"池内等权": pool_bench}
        market_amount_df = pool_bench[["date", "amount"]].copy()
    items = []
    for item in sectors:
        display = item["display"]
        sector_df = _build_lifecycle_df(df_with_bench, display, bench_days)
        sector_full = _build_lifecycle_df(df_with_bench, display, None)
        if sector_df is None or sector_df.empty:
            continue
        bench_name, bench_corr = select_dynamic_benchmark(sector_df, benchmark_map, 60)
        if not bench_name:
            bench_name = DEFAULT_BENCHMARK if DEFAULT_BENCHMARK in benchmark_map else list(benchmark_map.keys())[0]
        bench_df = benchmark_map.get(bench_name)
        if bench_df is None:
            bench_df = benchmark_map.get(DEFAULT_BENCHMARK) if DEFAULT_BENCHMARK in benchmark_map else list(benchmark_map.values())[0]
        amount_df = market_amount_df if market_amount_df is not None else benchmark_map.get(DEFAULT_BENCHMARK)
        items.append(analyze_sector(sector_df, bench_df, display, bench_name, bench_corr, amount_df, sector_full))
    return {"items": items, "watch": [s["display"] for s in sectors]}

def _num(v, default=0.0):
    try:
        if v is None:
            return default
        x = float(v)
        return default if pd.isna(x) else x
    except:
        return default

def _clamp(v, lo, hi):
    try:
        x = float(v)
    except:
        x = lo
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x

def _score_to_probs(score, horizon_days):
    s = _clamp(score, -6, 8)
    k = 8.5 if horizon_days == 3 else 10.0
    up = 50 + s * k
    drawdown = 50 - s * (k * 0.75)
    rng = 60 - abs(s) * 7.5
    up = int(round(_clamp(up, 5, 95)))
    drawdown = int(round(_clamp(drawdown, 5, 95)))
    rng = int(round(_clamp(rng, 5, 90)))
    if up + rng + drawdown != 100:
        t = up + rng + drawdown
        if t <= 0:
            return {"up_prob": 33, "range_prob": 34, "drawdown_risk": 33}
        up = int(round(up / t * 100))
        drawdown = int(round(drawdown / t * 100))
        rng = 100 - up - drawdown
    return {"up_prob": up, "range_prob": rng, "drawdown_risk": drawdown}

def _score_bin_key(score, score_min, score_max, bin_size):
    s = _clamp(score, score_min, score_max)
    idx = int((s - score_min) // bin_size)
    lo = score_min + idx * bin_size
    hi = lo + bin_size
    lo = round(float(lo), 4)
    hi = round(float(hi), 4)
    if hi >= score_max:
        return f"[{lo},{round(float(score_max), 4)}]"
    return f"[{lo},{hi})"

def _load_rotation_calibration():
    obj = _read_json_file(ROTATION_CALIB_PATH)
    if not isinstance(obj, dict):
        return None
    bins = obj.get("bins")
    if not isinstance(bins, dict):
        return None
    return obj

def _pick_calibrated_prob(score, horizon, calib):
    if not calib:
        return None
    bins = calib.get("bins") or {}
    table = bins.get(horizon)
    if not isinstance(table, dict) or not table:
        return None
    score_min = calib.get("score_min", -6)
    score_max = calib.get("score_max", 8)
    bin_size = calib.get("bin_size", 1.0)
    key = _score_bin_key(score, score_min, score_max, bin_size)
    row = table.get(key)
    if not isinstance(row, dict):
        return None
    return {
        "up_prob": int(row.get("up_prob", 33)),
        "range_prob": int(row.get("range_prob", 34)),
        "drawdown_risk": int(row.get("drawdown_risk", 33))
    }

def _advice_to_action(advice):
    s = str(advice or "")
    if "建仓" in s or "试探" in s or "低吸" in s:
        return "建仓"
    if "持有" in s or "埋伏" in s:
        return "持有"
    if "减仓" in s or "止盈" in s:
        return "减仓"
    if "回避" in s or "离场" in s or "止损" in s:
        return "回避"
    if "观望" in s:
        return "观望"
    return "观望"

def _action_to_position(action, bias=0.0):
    base = {
        "建仓": [0.2, 0.5],
        "持有": [0.5, 0.8],
        "减仓": [0.2, 0.5],
        "观望": [0.0, 0.2],
        "回避": [0.0, 0.05]
    }.get(action, [0.0, 0.2])
    lo, hi = base[0] + bias, base[1] + bias
    lo = float(_clamp(lo, 0.0, 1.0))
    hi = float(_clamp(hi, 0.0, 1.0))
    if hi < lo:
        hi = lo
    return {"min": round(lo, 2), "max": round(hi, 2)}

def _risk_tags(momentum, behavior):
    tags = []
    m = str(momentum or "")
    b = str(behavior or "")
    if "向下" in m:
        tags.append("向下")
    if b in ["恐慌出逃", "资金撤退", "加速赶顶"]:
        tags.append(b)
    if b == "放量启动":
        tags.append("放量")
    return tags[:4]

DEFAULT_TRIGGER_RULES = {
    "params": {
        "min_share_change": 0.0
    },
    "texts": {
        "ma20_breakout_confirm": "站上MA20且资金热度转正",
        "ma20_reclaim_confirm": "回踩MA20不破且资金热度回升",
        "fund_recover_confirm": "资金热度转正且趋势不破",
        "ma20_breakdown_invalidate": "跌破MA20或资金行为转弱",
        "weakness_continue_invalidate": "跌破近期低点或继续弱势",
        "funds_bad_invalidate": "资金行为持续恶化"
    },
    "overrides": {
        "sector": {},
        "group": {}
    }
}

def _load_trigger_rules():
    base = json.loads(json.dumps(DEFAULT_TRIGGER_RULES, ensure_ascii=False))
    obj = _read_json_file(TRIGGER_RULES_FILE)
    if not isinstance(obj, dict):
        return base
    params = obj.get("params")
    if isinstance(params, dict):
        base["params"].update(params)
    texts = obj.get("texts")
    if isinstance(texts, dict):
        base["texts"].update(texts)
    overrides = obj.get("overrides")
    if isinstance(overrides, dict):
        for k in ["sector", "group"]:
            v = overrides.get(k)
            if isinstance(v, dict):
                base["overrides"][k].update(v)
    return base

def _build_triggers(item, groups=None, rules=None):
    rules = rules or _load_trigger_rules()
    ind = item.get("指标数据") or {}
    close = _num(ind.get("close"), 0.0)
    ma20 = _num(ind.get("ma20") or ind.get("MA20"), 0.0)
    ch = ind.get("Amount_Share_Change")
    behavior = str(item.get("资金行为") or "")
    params = dict(rules.get("params") or {})
    groups = groups or []
    sector_name = str(item.get("板块名称") or "").strip()
    group_overrides = rules.get("overrides", {}).get("group", {})
    for g in groups:
        if g in group_overrides:
            ov = group_overrides.get(g) or {}
            if isinstance(ov.get("params"), dict):
                params.update(ov.get("params"))
    sector_overrides = rules.get("overrides", {}).get("sector", {})
    if sector_name in sector_overrides:
        ov = sector_overrides.get(sector_name) or {}
        if isinstance(ov.get("params"), dict):
            params.update(ov.get("params"))
    min_share_change = _num(params.get("min_share_change"), 0.0)
    confirm_key = "ma20_breakout_confirm"
    invalidate_key = "weakness_continue_invalidate"
    if close and ma20:
        if close < ma20:
            confirm_key = "ma20_breakout_confirm"
            invalidate_key = "weakness_continue_invalidate"
        else:
            confirm_key = "ma20_reclaim_confirm"
            invalidate_key = "ma20_breakdown_invalidate"
    if ch is not None and not pd.isna(ch):
        if float(ch) <= 0:
            confirm_key = "fund_recover_confirm"
    if behavior in ["恐慌出逃", "资金撤退"]:
        invalidate_key = "funds_bad_invalidate"
    if ch is not None and not pd.isna(ch):
        if float(ch) <= min_share_change:
            confirm_key = "fund_recover_confirm"
    if sector_name in sector_overrides:
        ov = sector_overrides.get(sector_name) or {}
        if ov.get("confirm_key"):
            confirm_key = ov.get("confirm_key")
        if ov.get("invalidate_key"):
            invalidate_key = ov.get("invalidate_key")
    for g in groups:
        ov = group_overrides.get(g) or {}
        if ov.get("confirm_key"):
            confirm_key = ov.get("confirm_key")
        if ov.get("invalidate_key"):
            invalidate_key = ov.get("invalidate_key")
    texts = rules.get("texts") or {}
    confirm = texts.get(confirm_key, "")
    invalidate = texts.get(invalidate_key, "")
    return {"confirm": confirm, "invalidate": invalidate, "confirm_key": confirm_key, "invalidate_key": invalidate_key}

def _pick_horizon(momentum, behavior):
    m = str(momentum or "")
    b = str(behavior or "")
    if m in ["强势向上", "偏强向上"] and b in ["放量启动", "超跌反弹"]:
        return "3d"
    return "5d"

def _score_rotation_item(item):
    momentum_map = {
        "强势向上": 3,
        "偏强向上": 2,
        "中性震荡": 1,
        "弱势反弹": 1,
        "偏强向下": -1,
        "弱势向下": -2,
        "强势向下": -3
    }
    behavior_map = {
        "放量启动": 3,
        "横盘整理": 1,
        "超跌反弹": 1,
        "资金撤退": -1,
        "加速赶顶": -1,
        "恐慌出逃": -3
    }
    momentum = str(item.get("动能") or "").strip()
    behavior = str(item.get("资金行为") or "").strip()
    advice = str(item.get("操作建议") or "").strip()
    ind = item.get("指标数据") or {}
    a5 = _num(ind.get("alpha_5"), 0.0)
    a20 = _num(ind.get("alpha_20"), 0.0)
    ch = _num(ind.get("Amount_Share_Change"), 0.0)
    base = momentum_map.get(momentum, 0) + behavior_map.get(behavior, 0)
    score = base + a5 * 0.15 + a20 * 0.05 + ch * 2.0
    if advice:
        if "回避" in advice or "离场" in advice or "止损" in advice:
            score -= 4
        elif "止盈" in advice:
            score -= 1
    return round(float(score), 4)

def _mainline_priority(item):
    momentum = str(item.get("动能") or "").strip()
    behavior = str(item.get("资金行为") or "").strip()
    ind = item.get("指标数据") or {}
    a5 = _num(ind.get("alpha_5") or ind.get("Alpha_5"), 0.0)
    ch = _num(ind.get("Amount_Share_Change"), 0.0)
    if momentum in ["强势向上", "偏强向上"] and behavior == "放量启动":
        tier = 1
    elif momentum in ["强势向上", "偏强向上"] and behavior in ["横盘整理", "趋势延续"]:
        tier = 2
    elif momentum in ["中性震荡", "弱势反弹"] and a5 > 0 and ch > 0:
        tier = 3
    else:
        tier = 9
    return (tier, -a5, -ch)

def _index_state(df_with_bench, name, days=90):
    part = _build_lifecycle_df(df_with_bench, name, days)
    if part is None or part.empty:
        return None
    close = pd.to_numeric(part["close"], errors="coerce").fillna(0)
    ma20 = close.rolling(20).mean()
    ma20_last = _num(ma20.iloc[-1], 0.0) if len(ma20) else 0.0
    slope = 0.0
    if len(ma20) >= 6:
        slope = _num(ma20.iloc[-1], 0.0) - _num(ma20.iloc[-6], 0.0)
        slope = slope / 5.0
    pct = 0.0
    if len(close) >= 2 and _num(close.iloc[-2], 0.0) != 0:
        pct = (_num(close.iloc[-1], 0.0) / _num(close.iloc[-2], 1.0) - 1) * 100.0
    above_ma20 = bool(_num(close.iloc[-1], 0.0) > ma20_last) if ma20_last else False
    return {
        "name": name,
        "close": round(_num(close.iloc[-1], 0.0), 2),
        "pct": round(float(pct), 2),
        "ma20": round(float(ma20_last), 2) if ma20_last else 0,
        "ma20_slope": round(float(slope), 4),
        "above_ma20": above_ma20
    }

def get_sector_rotation(sector_items, days=90):
    calib = _load_rotation_calibration()
    sectors = _normalize_sectors(sector_items)
    if not sectors:
        sectors = _normalize_sectors(DEFAULT_SECTORS)
    sector_names = [s.get("display") for s in sectors if isinstance(s, dict) and s.get("display")]
    lifecycle = get_sector_lifecycle(sector_names, days=max(60, int(days or 0) or 90))
    items = lifecycle.get("items") or []
    for it in items:
        it["_score"] = _score_rotation_item(it)
        if "主线得分" in it:
            it.pop("主线得分", None)
    ranked = sorted(items, key=_mainline_priority)
    groups = load_sector_groups()
    by_name = {str(it.get("板块名称") or ""): it for it in items}
    group_rows = []
    sector_to_groups = {}
    for gname, glist in groups.items():
        hits = []
        for s in glist:
            it = by_name.get(str(s))
            if it:
                hits.append(it)
        if not hits:
            continue
        scores = [_num(it.get("_score"), 0.0) for it in hits]
        a5s = [_num((it.get("指标数据") or {}).get("alpha_5"), 0.0) for it in hits]
        chs = [_num((it.get("指标数据") or {}).get("Amount_Share_Change"), 0.0) for it in hits]
        group_rows.append({
            "组别": gname,
            "均值得分": round(float(sum(scores) / max(1, len(scores))), 4),
            "均值Alpha_5": round(float(sum(a5s) / max(1, len(a5s))), 2),
            "均值资金变化": round(float(sum(chs) / max(1, len(chs))), 4),
            "样本数": len(hits),
            "板块": [it.get("板块名称") for it in hits if it.get("板块名称")]
        })
        for it in hits:
            n = str(it.get("板块名称") or "").strip()
            if not n:
                continue
            sector_to_groups.setdefault(n, [])
            sector_to_groups[n].append(gname)
    group_rows.sort(key=lambda x: _num(x.get("均值得分"), -999), reverse=True)
    leader = group_rows[0].get("组别") if group_rows else None
    trigger_rules = _load_trigger_rules()
    news_factor = _build_news_factor()
    mainline = []
    for it in ranked:
        if len(mainline) >= 3:
            break
        if _mainline_priority(it)[0] >= 9:
            continue
        advice = str(it.get("操作建议") or "")
        if "回避" in advice or "止损" in advice or "离场" in advice:
            continue
        ind = it.get("指标数据") or {}
        score = _num(it.get("_score"), 0.0)
        prob3 = _pick_calibrated_prob(score, "3d", calib)
        prob5 = _pick_calibrated_prob(score, "5d", calib)
        source = "calibrated" if (prob3 and prob5) else "rule"
        if not prob3:
            prob3 = _score_to_probs(score, 3)
        if not prob5:
            prob5 = _score_to_probs(score, 5)
        action = _advice_to_action(it.get("操作建议"))
        horizon = _pick_horizon(it.get("动能"), it.get("资金行为"))
        tags = _risk_tags(it.get("动能"), it.get("资金行为"))
        sector_name = str(it.get("板块名称") or "").strip()
        gs = sector_to_groups.get(sector_name) or []
        triggers = _build_triggers(it, gs, trigger_rules)
        news_view = news_factor.get(sector_name) or {"news_score": 0.0, "risk_tags": [], "top_titles": []}
        mainline.append({
            "板块名称": it.get("板块名称"),
            "_score": it.get("_score"),
            "动能": it.get("动能"),
            "资金行为": it.get("资金行为"),
            "操作建议": it.get("操作建议"),
            "risk_tags": tags,
            "prob_view": {
                "3d": prob3,
                "5d": prob5,
                "source": source
            },
            "exec_view": {
                "action": action,
                "position": _action_to_position(action),
                "horizon_prefer": horizon
            },
            "triggers": triggers,
            "news_view": news_view,
            "Alpha_5": ind.get("alpha_5"),
            "Alpha_20": ind.get("alpha_20"),
            "Amount_Share": ind.get("amount_share"),
            "Amount_Share_Change": ind.get("Amount_Share_Change"),
            "基准指数": it.get("基准指数"),
            "相关性": it.get("相关性"),
            "归因说明": it.get("归因说明")
        })

    def kind(name):
        s = str(name or "")
        head = s.split(":", 1)[0]
        if "资源" in head:
            return "resource"
        if "硬件" in head:
            return "hw"
        if "软件" in head:
            return "sw"
        if "科技" in head:
            return "tech"
        return None

    resource_score = 0.0
    tech_score = 0.0
    hw_score = 0.0
    sw_score = 0.0
    for g in group_rows:
        k = kind(g.get("组别"))
        sc = _num(g.get("均值得分"), 0.0)
        if k == "resource":
            resource_score += sc
        elif k == "hw":
            hw_score += sc
            tech_score += sc
        elif k == "sw":
            sw_score += sc
            tech_score += sc
        elif k == "tech":
            tech_score += sc

    seesaw = "平衡"
    if resource_score - tech_score >= 0.6:
        seesaw = "资源强"
    elif tech_score - resource_score >= 0.6:
        seesaw = "科技强"
    diffusion = "同步"
    if hw_score - sw_score >= 0.5:
        diffusion = "硬件领先"
    elif sw_score - hw_score >= 0.5:
        diffusion = "软件补涨"

    for m in mainline:
        name = str(m.get("板块名称") or "").strip()
        gs = sector_to_groups.get(name) or []
        m["groups"] = gs
        bias = 0.0
        if seesaw == "科技强" and any(("科技" in g or "硬件" in g or "软件" in g or g.startswith("硬件") or g.startswith("软件")) for g in gs):
            bias += 0.1
        if seesaw == "资源强" and any(("资源" in g or g.startswith("资源")) for g in gs):
            bias += 0.1
        if diffusion == "硬件领先" and any(("硬件" in g or g.startswith("硬件")) for g in gs):
            bias += 0.05
        if diffusion == "软件补涨" and any(("软件" in g or g.startswith("软件")) for g in gs):
            bias += 0.05
        ev = m.get("exec_view") or {}
        action = ev.get("action")
        ev["position"] = _action_to_position(action, bias=bias)
        ev["position"] = _apply_news_gate(ev["position"], m.get("news_view"))
        m["exec_view"] = ev
    df = _load_cache()
    if df is None or df.empty or _need_cache_refresh(df):
        df = _update_sector_cache(sectors, ensure_days=max(60, int(days or 0) or 90))
    df_with_bench = _append_benchmark_rows(df, days=max(90, int(days or 0) or 90))
    idx_star = _index_state(df_with_bench, "科创板", days=max(60, int(days or 0) or 90))
    idx_gem = _index_state(df_with_bench, "创业板", days=max(60, int(days or 0) or 90))
    idx_sz = _index_state(df_with_bench, "深证", days=max(60, int(days or 0) or 90))
    resonance = False
    resonance_reason = "缺数据"
    if idx_star and idx_gem and idx_sz:
        ok = 0
        for it in [idx_star, idx_gem, idx_sz]:
            if it.get("above_ma20") and _num(it.get("ma20_slope"), 0.0) > 0:
                ok += 1
        resonance = ok >= 2
        resonance_reason = "三者中至少两者站上MA20且斜率转正" if resonance else "共振条件不足"
    latest = _latest_cache_date(df_with_bench) or _today_str()
    return {
        "day": latest,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "watch": lifecycle.get("watch") or [],
        "mainline": mainline,
        "groups": group_rows,
        "rotation": {
            "leader": leader,
            "seesaw": seesaw,
            "diffusion": diffusion,
            "resonance": resonance,
            "resonance_reason": resonance_reason
        },
        "indices": {
            "科创板": idx_star,
            "创业板": idx_gem,
            "深证": idx_sz
        },
        "items": ranked
    }

def get_rotation_sequence(sector_items, days=60):
    sectors = _normalize_sectors(sector_items)
    if not sectors:
        sectors = _normalize_sectors(DEFAULT_SECTORS)
    df = _load_cache()
    if df is None or df.empty or _need_cache_refresh(df):
        df = _update_sector_cache(sectors, ensure_days=max(180, int(days or 0) * 3))
    histories = _build_histories_from_cache(df, sectors)
    date_map = {}
    for name, arr in histories.items():
        for row in arr:
            d = row.get("date")
            pct = _num(row.get("pct"), None)
            if not d:
                continue
            date_map.setdefault(d, []).append({"sector": name, "pct": pct})
    dates = sorted(date_map.keys())
    if days:
        dates = dates[-int(days):]
    groups = load_sector_groups()
    sector_group = {}
    for gname, glist in groups.items():
        for s in glist:
            if s not in sector_group:
                sector_group[s] = gname
    daily = []
    for d in dates:
        rows = date_map.get(d) or []
        rows = [r for r in rows if r.get("pct") is not None]
        if not rows:
            continue
        rows.sort(key=lambda x: _num(x.get("pct"), -999), reverse=True)
        top = rows[0]
        sector = top.get("sector")
        label = sector_group.get(sector, sector)
        daily.append({"date": d, "sector": sector, "group": label, "pct": top.get("pct")})
    segments = []
    for row in daily:
        label = row.get("group")
        if not segments or segments[-1]["label"] != label:
            segments.append({"label": label, "days": 1, "from": row.get("date"), "to": row.get("date")})
        else:
            segments[-1]["days"] += 1
            segments[-1]["to"] = row.get("date")
    for seg in segments:
        seg["type"] = "主线段" if seg["days"] >= 3 else "题材段"
    return {
        "range": {"from": dates[0] if dates else None, "to": dates[-1] if dates else None},
        "segments": segments,
        "daily": daily,
        "generated_at": datetime.now().isoformat(timespec="seconds")
    }

def _future_return_at(df, idx, days):
    if df is None or df.empty:
        return None
    if idx + days >= len(df):
        return None
    try:
        c0 = float(df.iloc[idx]["close"])
        c1 = float(df.iloc[idx + days]["close"])
    except:
        return None
    if not c0:
        return None
    return (c1 - c0) / c0 * 100

def _build_benchmark_map(df_with_bench, days):
    benchmark_map = {
        "上证": _build_lifecycle_df(df_with_bench, "上证", days),
        "深证": _build_lifecycle_df(df_with_bench, "深证", days),
        "创业板": _build_lifecycle_df(df_with_bench, "创业板", days),
        "科创板": _build_lifecycle_df(df_with_bench, "科创板", days)
    }
    if all(v is None or v.empty for v in benchmark_map.values()):
        return None, None
    market_amount_df = _build_lifecycle_df(df_with_bench, "沪深成交额", None)
    return benchmark_map, market_amount_df

def _collect_rotation_samples(sectors, ensure_days, min_lookback=60):
    df = _load_cache()
    if df is None or df.empty or _need_cache_refresh(df):
        df = _update_sector_cache(sectors, ensure_days=ensure_days)
    if df is None or df.empty:
        return [], {}
    bench_days = max(60, int(ensure_days or 0) or 180)
    df_with_bench = _append_benchmark_rows(df, days=bench_days)
    benchmark_map, market_amount_df = _build_benchmark_map(df_with_bench, bench_days)
    if benchmark_map is None:
        pool_bench = _build_pool_benchmark(df_with_bench, [s["display"] for s in sectors], days=bench_days)
        if pool_bench is None or pool_bench.empty:
            return [], {}
        benchmark_map = {"池内等权": pool_bench}
        market_amount_df = pool_bench[["date", "amount"]].copy()
    samples = []
    top_by_date = {}
    for item in sectors:
        display = item["display"]
        sector_full = _build_lifecycle_df(df_with_bench, display, None)
        if sector_full is None or sector_full.empty:
            continue
        sector_full = sector_full.sort_values("date").reset_index(drop=True)
        if len(sector_full) < min_lookback + 6:
            continue
        for i in range(min_lookback, len(sector_full) - 5):
            cur = sector_full.iloc[:i+1]
            date = cur["date"].iloc[-1]
            date_str = _to_date_str(date)
            bench_name, bench_corr = select_dynamic_benchmark(cur, benchmark_map, 60)
            if not bench_name:
                bench_name = DEFAULT_BENCHMARK if DEFAULT_BENCHMARK in benchmark_map else list(benchmark_map.keys())[0]
            bench_full = benchmark_map.get(bench_name)
            if bench_full is None or bench_full.empty:
                continue
            bench_slice = bench_full[bench_full["date"] <= date]
            if bench_slice.empty:
                continue
            amount_slice = None
            if market_amount_df is not None and not market_amount_df.empty:
                amount_slice = market_amount_df[market_amount_df["date"] <= date]
            analysis = analyze_sector(cur, bench_slice, display, bench_name, bench_corr, amount_slice, cur)
            score = _score_rotation_item(analysis)
            ret3 = _future_return_at(sector_full, i, 3)
            ret5 = _future_return_at(sector_full, i, 5)
            if ret3 is None or ret5 is None:
                continue
            row = {"date": date_str, "sector": display, "score": score, "ret3": ret3, "ret5": ret5}
            samples.append(row)
            top_by_date.setdefault(date_str, [])
            top_by_date[date_str].append(row)
    return samples, top_by_date

def _build_calibration_table(samples, horizon, score_min, score_max, bin_size, up_th, down_th):
    table = {}
    cur = score_min
    while cur < score_max:
        key = _score_bin_key(cur + 0.0001, score_min, score_max, bin_size)
        table[key] = {"count": 0, "up": 0, "range": 0, "drawdown": 0}
        cur += bin_size
    for s in samples:
        score = s.get("score")
        ret = s.get("ret3") if horizon == "3d" else s.get("ret5")
        if ret is None:
            continue
        key = _score_bin_key(score, score_min, score_max, bin_size)
        if key not in table:
            table[key] = {"count": 0, "up": 0, "range": 0, "drawdown": 0}
        table[key]["count"] += 1
        if ret >= up_th:
            table[key]["up"] += 1
        elif ret <= -down_th:
            table[key]["drawdown"] += 1
        else:
            table[key]["range"] += 1
    out = {}
    for k, v in table.items():
        total = v["count"]
        if total <= 0:
            out[k] = {"count": 0, "up_prob": 33, "range_prob": 34, "drawdown_risk": 33}
            continue
        up = int(round(v["up"] / total * 100))
        dd = int(round(v["drawdown"] / total * 100))
        rng = 100 - up - dd
        out[k] = {"count": total, "up_prob": up, "range_prob": rng, "drawdown_risk": dd}
    return out

def _calc_drawdown(returns):
    if not returns:
        return 0.0
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        equity *= (1 + r / 100.0)
        if equity > peak:
            peak = equity
        dd = (equity / peak - 1) * 100.0
        if dd < max_dd:
            max_dd = dd
    return round(float(max_dd), 2)

def _build_rotation_report(samples, top_by_date):
    report = {"generated_at": datetime.now().isoformat(timespec="seconds"), "summary": {}}
    for horizon in ["3d", "5d"]:
        rets = [s.get("ret3") if horizon == "3d" else s.get("ret5") for s in samples if s.get("ret3") is not None and s.get("ret5") is not None]
        if not rets:
            report["summary"][horizon] = {"samples": 0}
            continue
        win = sum(1 for r in rets if r > 0)
        avg_ret = sum(rets) / len(rets)
        worst = min(rets)
        best = max(rets)
        report["summary"][horizon] = {
            "samples": len(rets),
            "win_rate": round(win / len(rets) * 100, 2),
            "avg_return": round(avg_ret, 3),
            "best_return": round(best, 3),
            "worst_return": round(worst, 3)
        }
    dates = sorted(top_by_date.keys())
    top_series = []
    last = None
    changes = 0
    for d in dates:
        rows = top_by_date.get(d) or []
        if not rows:
            continue
        top = sorted(rows, key=lambda x: _num(x.get("score"), -999), reverse=True)[0]
        top_series.append(top)
        if last and top.get("sector") != last.get("sector"):
            changes += 1
        last = top
    turnover = round(changes / max(1, len(top_series) - 1), 4) if top_series else 0.0
    report["turnover"] = turnover
    report["max_drawdown_5d"] = _calc_drawdown([t.get("ret5") for t in top_series if t.get("ret5") is not None])
    report["max_drawdown_3d"] = _calc_drawdown([t.get("ret3") for t in top_series if t.get("ret3") is not None])
    scores = [s.get("score") for s in samples if s.get("score") is not None]
    p90 = sorted(scores)[int(len(scores) * 0.9)] if scores else None
    for horizon in ["3d", "5d"]:
        fails = []
        for s in samples:
            if p90 is not None and _num(s.get("score"), 0) < p90:
                continue
            ret = s.get("ret3") if horizon == "3d" else s.get("ret5")
            if ret is None:
                continue
            if ret < 0:
                fails.append({"date": s.get("date"), "sector": s.get("sector"), "score": s.get("score"), "return": round(float(ret), 3)})
        fails = sorted(fails, key=lambda x: x.get("return", 0))[:10]
        report[f"failures_{horizon}"] = fails
    return report

def build_rotation_calibration(sector_items, ensure_days=240, bin_size=1.0, up_th=2.0, down_th=2.0):
    sectors = _normalize_sectors(sector_items)
    if not sectors:
        sectors = _normalize_sectors(DEFAULT_SECTORS)
    samples, top_by_date = _collect_rotation_samples(sectors, ensure_days=ensure_days)
    if not samples:
        return {"error": "no_samples"}
    scores = [s.get("score") for s in samples if s.get("score") is not None]
    score_min = round(min(scores), 2) if scores else -6
    score_max = round(max(scores), 2) if scores else 8
    if score_min >= score_max:
        score_min = -6
        score_max = 8
    score_min = float(max(score_min, -10))
    score_max = float(min(score_max, 10))
    table3 = _build_calibration_table(samples, "3d", score_min, score_max, bin_size, up_th, down_th)
    table5 = _build_calibration_table(samples, "5d", score_min, score_max, bin_size, up_th, down_th)
    calib = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "bin_size": float(bin_size),
        "score_min": float(score_min),
        "score_max": float(score_max),
        "thresholds": {"up": float(up_th), "down": float(down_th)},
        "bins": {"3d": table3, "5d": table5},
        "stats": {"samples": len(samples)}
    }
    os.makedirs(os.path.dirname(ROTATION_CALIB_PATH), exist_ok=True)
    with open(ROTATION_CALIB_PATH, "w", encoding="utf-8") as f:
        json.dump(calib, f, ensure_ascii=False)
    report = _build_rotation_report(samples, top_by_date)
    with open(ROTATION_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False)
    return {"calibration": ROTATION_CALIB_PATH, "report": ROTATION_REPORT_PATH, "samples": len(samples)}

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

def _json_sanitize(obj):
    if obj is None:
        return None
    if isinstance(obj, float):
        return None if pd.isna(obj) else obj
    if isinstance(obj, (int, str, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_sanitize(v) for v in obj]
    return obj

def get_sector_minute(sector_name):
    df = None
    try:
        df = ak.stock_board_industry_hist_min_em(symbol=sector_name, period="1")
    except Exception as e:
        _FETCH_ERRORS["minute"][str(sector_name)] = f"{type(e).__name__}: {e}"
        df = pd.DataFrame()
    if df is None or df.empty:
        try:
            df = ak.stock_board_concept_hist_min_em(symbol=sector_name, period="1")
        except Exception as e:
            _FETCH_ERRORS["minute"][str(sector_name)] = f"{type(e).__name__}: {e}"
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
        "科创板": {"symbol": "000688"}
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

def _pick_breadth_col(df):
    for c in df.columns:
        if str(c).strip() == "涨跌幅":
            return c
    for c in df.columns:
        if "涨跌幅" in str(c):
            return c
    return None

def _count_breadth(df):
    if df is None or df.empty:
        return None
    col = _pick_breadth_col(df)
    if not col:
        return None
    s = pd.to_numeric(df[col], errors="coerce")
    up = int((s > 0).sum())
    down = int((s < 0).sum())
    flat = int((s == 0).sum())
    total = int(s.notna().sum())
    return {"up": up, "down": down, "flat": flat, "total": total}

def get_market_breadth():
    try:
        from io import StringIO
        old_stderr = sys.stderr
        sys.stderr = StringIO()
        sh = ak.stock_sh_a_spot_em()
        sz = ak.stock_sz_a_spot_em()
        sys.stderr = old_stderr
        shc = _count_breadth(sh)
        szc = _count_breadth(sz)
        if shc and szc:
            return {
                "up": shc["up"] + szc["up"],
                "down": shc["down"] + szc["down"],
                "flat": shc["flat"] + szc["flat"],
                "total": shc["total"] + szc["total"]
            }
    except Exception:
        sys.stderr = sys.__stderr__
    try:
        from io import StringIO
        old_stderr = sys.stderr
        sys.stderr = StringIO()
        df = ak.stock_zh_a_spot_em()
        sys.stderr = old_stderr
        return _count_breadth(df)
    except Exception:
        sys.stderr = sys.__stderr__
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
        print(json.dumps(_json_sanitize(data), ensure_ascii=False))
    
    elif cmd == "breadth":
        data = get_market_breadth()
        print(json.dumps(_json_sanitize(data), ensure_ascii=False))
        
    elif cmd == "history":
        if len(sys.argv) >= 3:
            try:
                indicator_days = int(sys.argv[2])
            except:
                indicator_days = 20
        payload = get_sector_payload(DEFAULT_SECTORS, indicator_days)
        print(json.dumps(_json_sanitize(payload), ensure_ascii=False))
    elif cmd == "history_dynamic":
        raw = sys.argv[2] if len(sys.argv) >= 3 else ""
        items = _parse_sector_arg(raw)
        if len(sys.argv) >= 4:
            try:
                indicator_days = int(sys.argv[3])
            except:
                indicator_days = 20
        payload = get_sector_payload(items, indicator_days)
        print(json.dumps(_json_sanitize(payload), ensure_ascii=False))
    elif cmd == "lifecycle":
        if len(sys.argv) >= 3:
            try:
                indicator_days = int(sys.argv[2])
            except:
                indicator_days = 60
        payload = get_sector_lifecycle(DEFAULT_SECTORS, indicator_days)
        print(json.dumps(_json_sanitize(payload), ensure_ascii=False))
    elif cmd == "lifecycle_dynamic":
        raw = sys.argv[2] if len(sys.argv) >= 3 else ""
        items = _parse_sector_arg(raw)
        if len(sys.argv) >= 4:
            try:
                indicator_days = int(sys.argv[3])
            except:
                indicator_days = 60
        payload = get_sector_lifecycle(items, indicator_days)
        print(json.dumps(_json_sanitize(payload), ensure_ascii=False))
    elif cmd == "rotation":
        if len(sys.argv) >= 3:
            try:
                indicator_days = int(sys.argv[2])
            except:
                indicator_days = 90
        payload = get_sector_rotation(DEFAULT_SECTORS, indicator_days)
        print(json.dumps(_json_sanitize(payload), ensure_ascii=False))
    elif cmd == "rotation_dynamic":
        raw = sys.argv[2] if len(sys.argv) >= 3 else ""
        items = _parse_sector_arg(raw)
        if len(sys.argv) >= 4:
            try:
                indicator_days = int(sys.argv[3])
            except:
                indicator_days = 90
        payload = get_sector_rotation(items, indicator_days)
        print(json.dumps(_json_sanitize(payload), ensure_ascii=False))
    elif cmd == "rotation_sequence":
        raw = sys.argv[2] if len(sys.argv) >= 3 else ""
        items = _parse_sector_arg(raw)
        seq_days = 60
        if len(sys.argv) >= 4:
            try:
                seq_days = int(sys.argv[3])
            except:
                seq_days = 60
        payload = get_rotation_sequence(items, seq_days)
        print(json.dumps(_json_sanitize(payload), ensure_ascii=False))
    elif cmd == "rotation_calibrate":
        ensure_days = 240
        bin_size = 1.0
        if len(sys.argv) >= 3:
            try:
                ensure_days = int(sys.argv[2])
            except:
                ensure_days = 240
        if len(sys.argv) >= 4:
            try:
                bin_size = float(sys.argv[3])
            except:
                bin_size = 1.0
        payload = build_rotation_calibration(DEFAULT_SECTORS, ensure_days=ensure_days, bin_size=bin_size)
        print(json.dumps(_json_sanitize(payload), ensure_ascii=False))
    elif cmd == "daily_csv":
        out = build_daily_csv(days=days, out_path=out_path)
        print(json.dumps(_json_sanitize({"out": out}), ensure_ascii=False))

if __name__ == "__main__":
    main()
