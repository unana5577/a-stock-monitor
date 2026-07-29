import argparse
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
 
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_ROOT = PROJECT_ROOT


def data_base() -> Path:
    return (DATA_ROOT / "data") if (DATA_ROOT / "data").exists() else DATA_ROOT


def data_path(*parts: str) -> Path:
    return data_base().joinpath(*parts)
 
 
def load_jsonl_all(p: Path) -> list[dict[str, Any]]:
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out
 
 
def load_json_last(p: Path) -> dict[str, Any] | None:
    if not p.exists():
        return None
    try:
        for line in reversed(p.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            return json.loads(line)
    except Exception:
        return None
    return None
 
 
def read_json(p: Path) -> dict[str, Any] | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
 
 
def parse_hhmm(day: str, hhmm: str) -> datetime | None:
    try:
        return datetime.strptime(f"{day} {hhmm}", "%Y-%m-%d %H:%M")
    except Exception:
        return None
 
 
def pick_point_at_or_before(series: list[dict[str, Any]], day: str, target_hhmm: str) -> dict[str, Any] | None:
    t = parse_hhmm(day, target_hhmm)
    if not t:
        return None
    best = None
    best_t = None
    for row in series:
        hhmm = str(row.get("asOf") or "")
        cur_t = parse_hhmm(day, hhmm)
        if not cur_t:
            continue
        if cur_t <= t and (best_t is None or cur_t > best_t):
            best = row
            best_t = cur_t
    return best
 
 
def safe_num(x: Any) -> float | None:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None
 
 
def infer_cum_mode(values: list[float]) -> str:
    xs = [float(v) for v in values if v is not None]
    if len(xs) < 5:
        return "unknown"
    dec = 0
    total = 0
    prev = xs[0]
    for v in xs[1:]:
        total += 1
        if v < prev - 1e-6:
            dec += 1
        prev = v
    if total <= 0:
        return "unknown"
    ratio_non_dec = 1 - dec / total
    if ratio_non_dec >= 0.98 and xs[-1] >= xs[0]:
        return "cum"
    return "inc"


def get_amt_value(row: dict[str, Any]) -> float | None:
    v = safe_num(row.get("amount"))
    if v is None:
        v = safe_num(row.get("vol"))
    if v is None:
        v = safe_num(row.get("volume"))
    return float(v) if v is not None else None


def minute_increments(series: list[dict[str, Any]], day: str, end_t: datetime, mode: str) -> list[float]:
    vals: list[tuple[datetime, float]] = []
    for row in series:
        hhmm = str(row.get("asOf") or "")
        t = parse_hhmm(day, hhmm)
        if not t or t > end_t:
            continue
        v = get_amt_value(row)
        if v is None:
            continue
        vals.append((t, float(v)))
    vals.sort(key=lambda x: x[0])
    if not vals:
        return []
    if mode != "cum":
        return [max(0.0, v) for _, v in vals]
    out: list[float] = []
    offset = 0.0
    prev_adj = vals[0][1]
    prev_cum = None
    for _, raw in vals:
        if raw < prev_adj * 0.5:
            offset += prev_adj
        adj = raw + offset
        if adj < prev_adj:
            adj = prev_adj
        prev_adj = adj
        if prev_cum is None:
            prev_cum = adj
            continue
        inc = adj - prev_cum
        if inc < 0:
            inc = 0.0
        out.append(float(inc))
        prev_cum = adj
    return out


def heat_from_recent60(increments: list[float]) -> tuple[str, float | None]:
    xs = [float(x) for x in increments if x is not None and x >= 0]
    if len(xs) < 20:
        return "平量", None
    xs = xs[-60:]
    half = len(xs) // 2
    if half <= 0 or len(xs) - half <= 0:
        return "平量", None
    avg1 = sum(xs[:half]) / float(half)
    avg2 = sum(xs[half:]) / float(len(xs) - half)
    if avg1 <= 0:
        return "平量", None
    ratio = float(avg2 / avg1)
    if ratio >= 1.2:
        return "放量", ratio
    if ratio <= 0.8:
        return "缩量", ratio
    return "平量", ratio


def cum_value_upto(series: list[dict[str, Any]], day: str, base_t: datetime, mode: str) -> float:
    vals: list[tuple[datetime, float]] = []
    for row in series:
        hhmm = str(row.get("asOf") or "")
        t = parse_hhmm(day, hhmm)
        if not t or t > base_t:
            continue
        v = get_amt_value(row)
        if v is None:
            continue
        vals.append((t, float(v)))
    vals.sort(key=lambda x: x[0])
    if not vals:
        return 0.0
    if mode == "cum":
        offset = 0.0
        prev_adj = vals[0][1]
        for _, raw in vals:
            if raw < prev_adj * 0.5:
                offset += prev_adj
            adj = raw + offset
            if adj < prev_adj:
                adj = prev_adj
            prev_adj = adj
        return float(prev_adj)
    s = 0.0
    for _, raw in vals:
        if raw > 0:
            s += raw
    return float(s)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    n = len(xs)
    if n == 1:
        return xs[0]
    pos = (n - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    w = pos - lo
    return xs[lo] * (1 - w) + xs[hi] * w


def load_daily_pct_thresholds(symbol: str, lookback_days: int = 120) -> tuple[float | None, float | None]:
    p = data_path("etf", "daily", symbol, "daily.jsonl")
    if not p.exists():
        return None, None
    vals: list[float] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        v = safe_num(obj.get("pct"))
        if v is None:
            continue
        if abs(v) > 30:
            continue
        vals.append(float(v))
    if len(vals) >= lookback_days:
        vals = vals[-lookback_days:]
    p80 = percentile(vals, 0.8)
    p10 = percentile(vals, 0.1)
    return p80, p10


def load_prev_daily_amount(symbol: str, day: str) -> float | None:
    p = data_path("etf", "daily", symbol, "daily.jsonl")
    if not p.exists():
        return None
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("date"):
            rows.append(obj)
    rows.sort(key=lambda x: str(x.get("date")))
    prev = None
    for r in rows:
        if str(r.get("date")) < day:
            prev = r
    if not prev:
        return None
    v = safe_num(prev.get("amount"))
    return float(v) if v is not None else None


def load_prev_daily_volume(symbol: str, day: str) -> float | None:
    p = data_path("etf", "daily", symbol, "daily.jsonl")
    if not p.exists():
        return None
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("date"):
            rows.append(obj)
    rows.sort(key=lambda x: str(x.get("date")))
    prev = None
    for r in rows:
        if str(r.get("date")) < day:
            prev = r
    if not prev:
        return None
    v = safe_num(prev.get("vol"))
    if v is None:
        v = safe_num(prev.get("volume"))
    if v is None:
        v = safe_num(prev.get("amount"))
    return float(v) if v is not None else None


def load_prev_daily_close(symbol: str, day: str) -> float | None:
    p = data_path("etf", "daily", symbol, "daily.jsonl")
    if not p.exists():
        return None
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("date"):
            rows.append(obj)
    rows.sort(key=lambda x: str(x.get("date")))
    prev = None
    for r in rows:
        if str(r.get("date")) < day:
            prev = r
    if not prev:
        return None
    v = safe_num(prev.get("close"))
    return float(v) if v is not None else None


def trading_elapsed_minutes(hhmm: str) -> int:
    try:
        h, m = hhmm.split(":")
        mins = int(h) * 60 + int(m)
    except Exception:
        return 0
    open_m = 9 * 60 + 30
    am_close = 11 * 60 + 30
    pm_open = 13 * 60
    pm_close = 15 * 60
    if mins <= open_m:
        return 0
    if mins <= am_close:
        return mins - open_m
    if mins < pm_open:
        return 120
    if mins <= pm_close:
        return 120 + (mins - pm_open)
    return 240


def price_zone_label(pct: float, p80: float | None, p10: float | None) -> str:
    strong = p80 if p80 is not None else 2.0
    weak = p10 if p10 is not None else -2.0
    if pct > strong:
        return "强势上涨"
    if pct > 1:
        return "正常上涨"
    if -1 <= pct <= 1:
        return "横盘"
    if pct >= weak:
        return "正常下跌"
    return "极端下跌"


def day_window_pcts(series: list[dict[str, Any]], day: str, end_hhmm: str) -> list[float]:
    end_t = parse_hhmm(day, end_hhmm)
    if not end_t:
        return []
    start_t = parse_hhmm(day, "09:30")
    out: list[float] = []
    for row in series:
        hh = str(row.get("asOf") or "")
        t = parse_hhmm(day, hh)
        if not t or t < (start_t or t) or t > end_t:
            continue
        v = safe_num(row.get("_pct_calc") if "_pct_calc" in row else row.get("pct"))
        if v is None:
            continue
        out.append(float(v))
    return out


def structure_label(series: list[dict[str, Any]], day: str, end_hhmm: str, pct_now: float) -> str:
    pcts = day_window_pcts(series, day, end_hhmm)
    if not pcts:
        return "结构未明"
    in_band_all = all((-1.0 <= v <= 1.0) for v in pcts)
    if in_band_all:
        return "窄幅震荡"
    mx = max(pcts)
    mn = min(pcts)
    if mx > 1.0 and mn < -1.0:
        last_hi = None
        last_lo = None
        for i, v in enumerate(pcts):
            if v > 1.0:
                last_hi = i
            if v < -1.0:
                last_lo = i
        if last_hi is not None and last_lo is not None:
            return "冲高回落" if last_hi > last_lo else "探底回升"
    if mx > 1.0:
        return "趋势上行" if pct_now > 1.0 else "冲高回落"
    if mn < -1.0:
        return "趋势下行" if pct_now < -1.0 else "探底回升"
    return "结构未明"


def support_judgement(pct_now: float, heat: str, is_persistent: bool) -> tuple[str, str]:
    if pct_now < 0:
        if heat == "放量":
            if pct_now <= -2:
                return "放量重挫（出货信号）", "大幅下跌且放量，主力出货迹象明显，警惕持续走弱。"
            if pct_now <= -1:
                if is_persistent:
                    return "放量下杀（出货延续）", "跌超1%且持续放量超过一小时，资金持续出逃。"
                return "放量下探（出货警示）", "回落过程中放量换手，有资金撤出迹象，需警惕是否为出货。"
            if is_persistent:
                return "放量横跌（派发确认）", "持续放量但未能收回跌幅，资金在高位派发。"
            return "分歧加大", "回落过程中放量换手，分歧加大。"
        if heat == "缩量":
            if pct_now <= -2:
                return "缩量阴跌（筹码松动）", "持续探底但成交清淡，筹码松动但未出现恐慌。"
            if is_persistent:
                return "抛压有限", "成交清淡，抛压有限。"
            return "承接待确认", "回落初期，承接力度仍需确认。"
        if is_persistent:
            if pct_now <= -1:
                return "弱势横盘（抛压持续）", "跌超1%后横盘运行，未见有效承接。"
            return "承接观察", "回落后横盘运行，需观察承接是否持续。"
        return "承接待确认", "回落初期，承接力度仍需确认。"
    return "方向未明", "水面附近运行，等待方向选择。"


def intraday_action(structure: str, zone: str, pct_now: float, heat: str, is_persistent: bool) -> str:
    if zone == "极端下跌":
        return "回避为主"
    if zone == "正常下跌":
        if is_persistent and heat in ("放量", "平量"):
            return "承接观察"
        return "谨慎观望"
    if zone == "强势上涨":
        if structure == "冲高回落":
            return "警惕回落"
        if is_persistent and heat == "放量":
            return "持有为主"
        if is_persistent and heat in ("缩量", "平量"):
            return "谨慎追高"
        return "追涨需确认"
    if zone == "正常上涨":
        if structure == "冲高回落":
            return "谨慎追高"
        if is_persistent:
            return "持有观察"
        return "观望确认"
    if zone == "横盘":
        if structure == "窄幅震荡":
            return "观望等待"
        if structure == "冲高回落":
            return "谨慎追高"
        if structure == "探底回升":
            return "观察承接"
        return "观望等待"
    return "观望等待"


def zone_duration_minutes(series: list[dict[str, Any]], day: str, asof: str, zone: str, p80: float | None, p10: float | None) -> int:
    base = parse_hhmm(day, asof)
    if not base:
        return 0
    start_limit = parse_hhmm(day, "10:00")
    if start_limit and base < start_limit:
        return 0
    last_t = None
    dur = 0
    for row in reversed(series):
        hhmm = str(row.get("asOf") or "")
        t = parse_hhmm(day, hhmm)
        if not t or t > base:
            continue
        if start_limit and t < start_limit:
            break
        v = safe_num(row.get("_pct_calc") if "_pct_calc" in row else row.get("pct"))
        if v is None:
            continue
        z = price_zone_label(float(v), p80, p10)
        if z != zone:
            break
        if last_t is None:
            last_t = t
            dur = 1
        else:
            step = int((last_t - t).total_seconds() // 60)
            if step <= 0:
                continue
            dur += step
            last_t = t
        if dur >= 240:
            break
    return dur


def fund_heat_label(est_ratio: float | None) -> str:
    if est_ratio is None:
        return "平量"
    if est_ratio >= 1.5:
        return "放量"
    if est_ratio <= 0.6:
        return "缩量"
    return "平量"


def structure_extremes_hint(series: list[dict[str, Any]], day: str, end_hhmm: str) -> str | None:
    pcts = day_window_pcts(series, day, end_hhmm)
    if not pcts:
        return None
    mx = max(pcts)
    mn = min(pcts)
    if mx > 1.0 and mn < -1.0:
        return f"日内高点{mx:.2f}%，低点{mn:.2f}%。"
    if mx > 1.0:
        return f"日内高点{mx:.2f}%。"
    if mn < -1.0:
        return f"日内低点{mn:.2f}%。"
    return None


def structure_meaning(struct: str) -> str:
    if struct == "窄幅震荡":
        return "全天围绕水面反复拉锯。"
    if struct == "冲高回落":
        return "冲高后回吐，需看回落中是否承接或派发。"
    if struct == "探底回升":
        return "下探后收回，需看承接是否持续。"
    if struct == "趋势上行":
        return "上行区间运行，趋势延续。"
    if struct == "趋势下行":
        return "下行区间运行，弱势延续。"
    return "分钟数据不足，暂不定性。"


def zone_phrase(zone: str) -> str:
    if zone == "横盘":
        return "当前仍在横盘区间。"
    if zone == "正常上涨":
        return "当前位于正常上涨区间。"
    if zone == "强势上涨":
        return "当前位于强势上涨区间。"
    if zone == "正常下跌":
        return "当前已回落至正常下跌区间。"
    if zone == "极端下跌":
        return "当前处于极端下跌区间，风险偏高。"
    return ""


def heat_phrase(heat: str, is_persistent: bool) -> str:
    dur = "已持续一小时以上" if is_persistent else ""
    if heat == "放量":
        return f"最近一小时成交放大，{dur}。" if dur else "最近一小时成交放大。"
    if heat == "缩量":
        return f"最近一小时成交转淡，{dur}。" if dur else "最近一小时成交转淡。"
    return f"最近一小时成交变化不大，{dur}。" if dur else "最近一小时成交变化不大。"


def judge_phrase(judge: str) -> str:
    if judge == "承接有力":
        return "回落中有承接。"
    if judge == "承接观察":
        return "承接仍在，继续观察持续性。"
    if judge == "承接待确认":
        return "承接力度仍需确认。"
    if judge == "抛压有限":
        return "抛压不大。"
    if judge == "流动性丧失":
        return "成交偏弱，流动性不足。"
    if judge == "派发风险":
        return "高位回吐，留意派发。"
    if judge == "分歧加大":
        return "放量但推进减弱，分歧加大。"
    if judge == "多空激战":
        return "放量拉锯，多空激战。"
    if judge == "方向未明":
        return "方向仍未明朗。"
    if judge == "主升延续":
        return "趋势延续。"
    return ""

def pct_at_or_before(series: list[dict[str, Any]], day: str, hhmm: str) -> float | None:
    row = pick_point_at_or_before(series, day, hhmm)
    if not row:
        return None
    v = safe_num(row.get("_pct_calc") if "_pct_calc" in row else row.get("pct"))
    return float(v) if v is not None else None


def hhmm_shift(day: str, hhmm: str, delta_min: int) -> str | None:
    base = parse_hhmm(day, hhmm)
    if not base:
        return None
    return (base + timedelta(minutes=delta_min)).strftime("%H:%M")


def window_peak_pct(series: list[dict[str, Any]], day: str, start_hhmm: str, end_hhmm: str) -> float | None:
    start_t = parse_hhmm(day, start_hhmm)
    end_t = parse_hhmm(day, end_hhmm)
    if not start_t or not end_t:
        return None
    best = None
    for row in series:
        hh = str(row.get("asOf") or "")
        t = parse_hhmm(day, hh)
        if not t or t < start_t or t > end_t:
            continue
        v = safe_num(row.get("_pct_calc") if "_pct_calc" in row else row.get("pct"))
        if v is None:
            continue
        fv = float(v)
        if best is None or fv > best:
            best = fv
    return float(best) if best is not None else None


def intraday_judgement(zone: str, is_persistent: bool, heat: str) -> tuple[str, str]:
    if zone == "正常下跌":
        if is_persistent and heat in ("放量", "平量"):
            return "低位承接有力（震荡洗盘）", "承接有力"
        if is_persistent and heat == "缩量":
            return "缩量横盘抗跌（洗盘中继）", "洗盘中继"
        return "正常回落（待确认）", "待确认"
    if zone == "极端下跌":
        if heat == "放量":
            return "放量破位（坚决规避）", "放量破位"
        return "缩量阴跌（流动性丧失）", "流动性丧失"
    if zone == "横盘":
        if is_persistent and heat == "放量":
            return "放量横盘分歧（多空激战）", "多空激战"
        if is_persistent and heat == "缩量":
            return "缩量窄幅震荡（方向未明）", "方向未明"
        return "平盘震荡", "震荡"
    if zone == "正常上涨":
        if is_persistent:
            return "温和上涨（主升延续）", "主升延续"
        return "盘中拉升（待确认）", "待确认"
    if zone == "强势上涨":
        if is_persistent and heat == "放量":
            return "涨速放缓", "分歧加大"
        if is_persistent and heat in ("缩量", "平量"):
            return "缩量强势逼空（高位锁仓）", "抛压有限"
        if (not is_persistent) and heat == "放量":
            return "极值冲高放量（警惕回落）", "派发风险"
        return "盘中拉升（待确认）", "待确认"
    return "盘中震荡", "震荡"


def intraday_reason_text(zone: str, is_persistent: bool, heat: str) -> str:
    if zone == "正常下跌":
        if is_persistent and heat in ("放量", "平量"):
            return "跌超1%但未破底线，资金在持续接盘。"
        if is_persistent and heat == "缩量":
            return "跌超1%后横盘运行，成交显著萎缩，流动性下降。"
        return "趋势未明，承接不明。"
    if zone == "极端下跌":
        if heat == "放量":
            return "跌破底线且放量，抛压集中释放，风险偏高。"
        return "跌破底线但成交清淡，流动性不足导致阴跌。"
    if zone == "横盘":
        if is_persistent and heat == "放量":
            return "水面附近长时间拉锯且放量换手，多空分歧加剧。"
        if is_persistent and heat == "缩量":
            return "水面附近长时间窄幅震荡，成交清淡，方向未明。"
        return "水面附近窄幅震荡。"
    if zone == "正常上涨":
        if is_persistent:
            return "温和推升且持续，趋势相对健康。"
        return "上行刚形成，仍需确认。"
    if zone == "强势上涨":
        if is_persistent and heat == "放量":
            return "强势区放量上行，资金推动延续。"
        if is_persistent and heat in ("缩量", "平量"):
            return "高位缩量且价格坚挺，抛压有限。"
        if (not is_persistent) and heat == "放量":
            return "快速冲高并放量，短线回落风险增加。"
        return "高位附近波动，尚未走稳。"
    return "盘中走势尚未形成有效定性。"
 
 
def build_table(rows: list[dict[str, Any]]) -> str:
    headers = ["ETF", "池", "pct", "结构", "操作建议", "资金行为", "归因说明"]
    md = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in rows:
        md.append(
            "| "
            + " | ".join(
                [
                    str(r.get("name") or "-"),
                    str(r.get("pool") or "-"),
                    str(r.get("pct") or "-"),
                    str(r.get("动能") or "-"),
                    str(r.get("操作建议") or "-"),
                    str(r.get("资金行为") or "-"),
                    str(r.get("归因说明") or "-"),
                ]
            )
            + " |"
        )
    return "\n".join(md)
 
 
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--day", default=datetime.now().strftime("%Y-%m-%d"))
    p.add_argument("--asof", default="")
    p.add_argument("--interval", type=int, default=5)
    p.add_argument("--persist", action="store_true")
    p.add_argument("--data_root", default="")
    args = p.parse_args()
 
    day = str(args.day)
    now = datetime.now()
    asof = str(args.asof).strip() or now.strftime("%H:%M")
    interval = int(args.interval)
    global DATA_ROOT
    if str(args.data_root).strip():
        DATA_ROOT = Path(str(args.data_root)).expanduser().resolve()
 
    proxy = read_json(PROJECT_ROOT / "data/sector-proxy.json") or {}
    etf_dict = (proxy.get("variants") or {}).get("etf") or {}
    etf_meta = proxy.get("etf_meta") or {}
 
    lifecycle = read_json(data_path("lifecycle", "lifecycle.json")) or {}
    lifecycle_items = lifecycle.get("data") or []
    lifecycle_map = {str(it.get("symbol")): it for it in lifecycle_items if it.get("symbol")}
 
    base_t_arg = parse_hhmm(day, asof)
    if not base_t_arg:
        print(f"DEBUG: base_t parsing failed for {day} {asof}")
        return 1

    rows: list[dict[str, Any]] = []
    series_cache: dict[str, list[dict[str, Any]]] = {}

    for name, symbol in etf_dict.items():
        symbol = str(symbol)
        meta = etf_meta.get(name) or {}
        sub = meta.get("sub_category") or ""
        series_file = data_path("etf", "minute", symbol, f"{day}.jsonl")
        series = load_jsonl_all(series_file)
        series_cache[symbol] = series
        prev_close = load_prev_daily_close(symbol, day)
        if prev_close is not None and prev_close > 0:
            for row in series:
                px = safe_num(row.get("price"))
                if px is None:
                    px = safe_num(row.get("close"))
                if px is None:
                    continue
                base_close = safe_num(row.get("pre_close"))
                if base_close is None or base_close <= 0:
                    base_close = float(prev_close)
                pct_from_price = (float(px) / float(base_close) - 1.0) * 100.0

                pct_field = safe_num(row.get("pct"))
                pct_field_val = float(pct_field) if pct_field is not None else None
                if pct_field_val is not None and abs(pct_field_val) > 30:
                    pct_field_val = None

                chosen = None
                if pct_field_val is not None and abs(pct_field_val) > 1e-9:
                    if abs(pct_field_val) <= 0.5 and abs(pct_from_price) >= 0.5:
                        chosen = pct_from_price
                    elif abs(pct_field_val - pct_from_price) >= 0.3:
                        chosen = pct_from_price
                    else:
                        chosen = pct_field_val
                else:
                    chosen = pct_from_price
                row["_pct_calc"] = float(chosen)
        cur = pick_point_at_or_before(series, day, asof)
        if not cur:
            continue
 
        asof_eff = str(cur.get("asOf") or "")
        cur_t = parse_hhmm(day, asof_eff)
        if not cur_t:
            continue
        base_t_sym = cur_t

        pct = safe_num(cur.get("_pct_calc") if "_pct_calc" in cur else cur.get("pct"))
        if pct is None:
            continue
        pct_val = float(pct)

        p80, p10 = load_daily_pct_thresholds(symbol, 120)
        zone = price_zone_label(pct_val, p80, p10)
        dur = zone_duration_minutes(series, day, asof_eff, zone, p80, p10)
        is_persistent = dur >= 60
        time_state = "持久" if is_persistent else "短暂"
        raw_vals = []
        for row in series:
            hhmm = str(row.get("asOf") or "")
            t = parse_hhmm(day, hhmm)
            if not t or t > base_t_sym:
                continue
            v = get_amt_value(row)
            if v is None:
                continue
            raw_vals.append(float(v))
        mode = infer_cum_mode(raw_vals)
        if mode == "unknown":
            mode = "cum"
        incs = minute_increments(series, day, base_t_sym, mode)
        heat, heat_ratio = heat_from_recent60(incs)
        intraday_status, fund_judge = intraday_judgement(zone, is_persistent, heat)
        dd = None
        dd_ratio = None
        if zone == "强势上涨" and is_persistent and heat == "放量":
            hhmm_30 = hhmm_shift(day, asof_eff, -30)
            hhmm_15 = hhmm_shift(day, asof_eff, -15)
            if hhmm_30 and hhmm_15:
                pct_30 = pct_at_or_before(series, day, hhmm_30)
                pct_15 = pct_at_or_before(series, day, hhmm_15)
                peak = window_peak_pct(series, day, hhmm_30, asof_eff)
                if pct_30 is not None and pct_15 is not None and peak is not None:
                    speed1 = (pct_15 - pct_30) / 15.0
                    speed2 = (pct_val - pct_15) / 15.0
                    dd = float(max(0.0, peak - pct_val))
                    dd_ratio = float(dd / peak) if peak != 0 else None
                    if speed1 > 0 and abs(speed2) <= 0.01 and dd_ratio is not None and dd_ratio >= 0.15:
                        intraday_status = "涨速放缓"
                        fund_judge = "分歧加剧"

        lci = lifecycle_map.get(symbol) or {}
        pool = "黄"
        try:
            bias = float(((lci.get("指标数据") or {}).get("Bias_20")) or 0)
            mx = float(((lci.get("指标数据") or {}).get("Bias_20_History_Max")) or 0)
            if lci.get("动能") == "强势向上" and mx != 0 and bias >= 0.9 * mx:
                pool = "红"
            elif lci.get("动能") in ("强势向上", "偏强向上"):
                pool = "绿"
        except Exception:
            pool = "黄"

        struct = structure_label(series, day, asof_eff, pct_val)
        behavior = f"{time_state}·{heat}"
        final_label = intraday_status
        if pct_val < 0:
            fund_judge, support_text = support_judgement(pct_val, heat, is_persistent)
            evidence_core = support_text
        else:
            evidence_core = intraday_reason_text(zone, is_persistent, heat)
            is_high = (zone == "强势上涨") or (struct == "冲高回落")
            if is_high:
                if "警惕回落" in final_label or struct == "冲高回落":
                    fund_judge = "派发风险" if heat in ("放量", "平量") else "抛压有限"
                elif "涨速放缓" in final_label:
                    fund_judge = "分歧加大"
                elif "高位锁仓" in final_label:
                    fund_judge = "抛压有限"
                else:
                    if fund_judge == "待确认":
                        fund_judge = "方向未明"
            elif zone == "横盘" and is_persistent and heat == "放量":
                fund_judge = "多空激战"
            elif zone == "横盘" and is_persistent and heat == "缩量":
                fund_judge = "方向未明"
            else:
                if fund_judge == "待确认":
                    fund_judge = "方向未明"

        if not fund_judge:
            fund_judge = "方向未明"

        head_struct = struct if struct else "结构未明"
        parts: list[str] = []

        def append_part(s: str | None) -> None:
            ss = (s or "").strip()
            if not ss:
                return
            for i, p in enumerate(parts):
                if p == ss:
                    return
                if ss in p:
                    return
                if p in ss:
                    parts[i] = ss
                    return
            parts.append(ss)

        append_part(structure_meaning(head_struct))
        append_part(structure_extremes_hint(series, day, asof_eff))
        append_part(heat_phrase(heat, is_persistent))
        append_part(judge_phrase(fund_judge))
        append_part(evidence_core)

        evidence = "".join(parts)
        if intraday_status.startswith("高位放量滞涨") and dd is not None and dd_ratio is not None:
            evidence = f"滞涨确认：近30分钟高点回撤{dd:.2f}%（{dd_ratio*100:.0f}%）。{evidence}"
 
        rows.append(
            {
                "name": name,
                "symbol": symbol,
                "category": meta.get("category") or "",
                "sub_category": sub,
                "asOf": asof_eff,
                "pct": round(pct_val, 2),
                "pool": pool,
                "操作建议": final_label,
                "动能": struct,
                "资金行为": behavior,
                "热度占比": fund_judge,
                "归因说明": evidence,
            }
        )
 
    rows.sort(key=lambda r: (safe_num(r.get("pct")) or 0.0), reverse=True)
 
    snapshot = {"date": day, "asOf": asof, "intervalMin": interval, "items": rows}
 
    if args.persist:
        out_dir = data_path("lifecycle", "intraday")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"etf_snapshot_{day}.jsonl"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
 
    print(build_table(rows))
 
    return 0
 
 
if __name__ == "__main__":
    raise SystemExit(main())
