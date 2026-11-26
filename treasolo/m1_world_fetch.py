"""外盘指数分钟采集: 日经225 / 韩国KOSPI / 恒生指数

数据源: 东方财富 (Phase 0 验证: 2026-11-25 与新华社/腾讯三方数值一致)
  - 新浪 int_* 全球指数代码存在陈旧数据(日经差1.2万点), 已淘汰
  - 仅用标准库 urllib, 零第三方依赖(生产容器 python3 无 requests 也能跑)

采集模式(2026-11-26 重构): 全天分时对账
  - 旧模式(逐分钟追加现价)的问题: 东财间歇限流 → 单分钟 no_quote → 曲线永久断点,
    且 Yahoo 境内不可用/腾讯无日韩代码, 无兜底
  - 新模式: 每次运行调 trends2 拉全天分钟序列, 与 jsonl 对账补齐缺失分钟,
    单次失败/单分钟缺口下一轮自动愈合 (最终一致)
  - 日经午休(北京时间10:30-11:30) trends 自然无 bar, 无需特殊处理

落盘: data/world/minute/{SYM}/{day}.jsonl  格式 {time, asOf, price, pct, pre_close}
  - 与 data/index/minute 同构, 额外自带 pre_close/pct (API validPt 兜底直接可用)
调度: n8n 每分钟调用; 仅市场在交易窗口内才发起请求
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 东财 push2 必须直连, 清除本地代理
for _k in list(os.environ):
    if _k.lower().endswith("_proxy"):
        del os.environ[_k]

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 内部代码 -> 东财市场代码/显示名/采集窗口(北京时间分钟数, 收盘后多留20分钟确保收盘bar落盘)
WORLD_MARKETS = {
    "N225": {"em": "100.N225", "name": "日经225", "window": (480, 860)},
    "KS11": {"em": "100.KS11", "name": "韩国KOSPI", "window": (480, 890)},
    "HSI": {"em": "100.HSI", "name": "恒生指数", "window": (570, 980)},
}

# 东财镜像域名(限流时轮换)
EM_HOSTS = ["push2his.eastmoney.com", "1.push2his.eastmoney.com", "99.push2his.eastmoney.com"]


def load_holidays() -> set[str]:
    p = PROJECT_ROOT / "config/holidays.json"
    if not p.exists():
        return set()
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        return set(obj.get("holidays") or [])
    except Exception:
        return set()


def is_weekend(now: datetime) -> bool:
    return now.weekday() >= 5


def _http_get_json(url: str, params: dict, timeout: int = 10) -> dict:
    """urllib 直连版 GET(零第三方依赖, 生产容器/任意 python3 都能跑)"""
    from urllib.parse import urlencode
    import urllib.request

    # ProxyHandler({}) 强制直连, 不读 *_proxy 环境变量
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(
        f"{url}?{urlencode(params)}",
        headers={"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"},
    )
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def _em_get(path: str, params: dict, timeout: int = 12) -> dict:
    """东财 GET: 镜像域名轮换 + 递增退避(1s/2s/3s), 应对间歇性限流"""
    last_err: Exception = RuntimeError("em_unreachable")
    for attempt in range(3):
        host = EM_HOSTS[attempt % len(EM_HOSTS)]
        try:
            return _http_get_json(f"https://{host}{path}", params, timeout=timeout)
        except Exception as e:  # noqa: BLE001 - 网络异常统一退避重试
            last_err = e
            time.sleep(1 + attempt)
    raise last_err


def fetch_em_trends(sym: str) -> dict | None:
    """东财 trends2 全天分钟序列, 返回 {pre_close, date, points: [(asOf, price)]} 或 None

    bar 格式: "2026-11-26 08:00,开,收,高,低,量,额,均价"  → 取第3列(close)作现价
    午间休市时段自然无 bar; prePrice 为昨收(2026-11-26 实测与腾讯/新浪一致)
    """
    meta = WORLD_MARKETS[sym]
    d = _em_get("/api/qt/stock/trends2/get",
                params={"secid": meta["em"], "fields1": "f1,f2,f3,f4,f5,f6,f7,f8",
                        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
                        "iscr": 0, "ndays": 1})
    data = d.get("data") or {}
    bars = data.get("trends") or []
    pre_close = data.get("prePrice") or data.get("preClose")
    if not bars or not pre_close:
        return None

    points: list[tuple[str, str, float]] = []  # (date, asOf, price)
    for bar in bars:
        parts = bar.split(",")
        if len(parts) < 3:
            continue
        date_part, time_part = parts[0].split(" ")
        price = float(parts[2])
        if price > 0:
            points.append((date_part, time_part, price))
    if not points:
        return None
    return {"pre_close": round(float(pre_close), 3),
            "date": points[0][0],
            "points": points}


def append_jsonl(path: Path, record: dict) -> bool:
    """按 asOf 去重追加(文件末行 asOf 相同则跳过)"""
    if path.exists():
        try:
            last = path.read_text(encoding="utf-8").splitlines()[-1].strip()
            if last:
                obj = json.loads(last)
                if obj.get("asOf") == record.get("asOf"):
                    return False
        except Exception:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return True


def reconcile_day(sym: str, day: str, trends: dict) -> dict:
    """把 trends 全天序列与当日 jsonl 对账, 补齐缺失分钟; 返回统计"""
    out_path = PROJECT_ROOT / f"data/world/minute/{sym}/{day}.jsonl"
    existing: set[str] = set()
    if out_path.exists():
        try:
            for line in out_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    existing.add(json.loads(line).get("asOf"))
        except Exception:
            pass

    pre_close = trends["pre_close"]
    wrote, seen = 0, 0
    path = out_path
    path.parent.mkdir(parents=True, exist_ok=True)
    for date_part, as_of, price in trends["points"]:
        if date_part != day or as_of in existing:
            continue
        seen += 1
        record = {
            "time": f"{day}T{as_of}:00",
            "asOf": as_of,
            "price": price,
            "pct": round((price - pre_close) / pre_close * 100, 4),
            "pre_close": pre_close,
        }
        # 直接追加(不对账逐条去重, existing 已排除; 但末行同分钟防重仍保留)
        if append_jsonl(path, record):
            wrote += 1
    return {"sym": sym, "wrote": wrote, "total_bars": len(trends["points"]),
            "existing": len(existing), "pre_close": pre_close}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default=",".join(WORLD_MARKETS.keys()))
    p.add_argument("--day", default="")
    p.add_argument("--force", action="store_true", help="跳过交易窗口校验(补当日数据/测试用)")
    args = p.parse_args()

    now = datetime.now()
    day = args.day or now.strftime("%Y-%m-%d")
    as_of = now.strftime("%H:%M")
    if not args.force and is_weekend(now):
        print(json.dumps({"ok": True, "skipped": True, "reason": "weekend", "day": day, "asOf": as_of}))
        return 0

    today_minutes = now.hour * 60 + now.minute
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    # 所有市场都不在采集窗口时直接跳过, 不发起网络请求
    in_window = [s for s in symbols
                 if s in WORLD_MARKETS
                 and WORLD_MARKETS[s]["window"][0] <= today_minutes <= WORLD_MARKETS[s]["window"][1]]
    if not args.force and not in_window:
        print(json.dumps({"ok": True, "skipped": True, "reason": "no_market_in_window",
                          "day": day, "asOf": as_of}))
        return 0

    results, skipped = [], []
    for sym in in_window:
        try:
            trends = fetch_em_trends(sym)
        except Exception as e:
            skipped.append({"sym": sym, "reason": f"fetch_failed: {type(e).__name__}"})
            continue
        if not trends:
            skipped.append({"sym": sym, "reason": "no_trends"})
            continue
        if trends["date"] != day:
            skipped.append({"sym": sym, "reason": "stale_day", "trend_date": trends["date"]})
            continue
        results.append(reconcile_day(sym, day, trends))
        time.sleep(0.5)

    total_new = sum(r["wrote"] for r in results)
    print(json.dumps({"ok": True, "day": day, "asOf": as_of,
                      "wrote_total": total_new,
                      "detail": results, "skipped": skipped},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
