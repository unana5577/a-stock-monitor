import argparse
import json
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_holidays() -> set[str]:
    p = PROJECT_ROOT / "config/holidays.json"
    if not p.exists():
        return set()
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        return set(obj.get("holidays") or [])
    except Exception:
        return set()


def is_trading_session(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    d = now.strftime("%Y-%m-%d")
    if d in load_holidays():
        return False
    minutes = now.hour * 60 + now.minute
    return (570 <= minutes <= 690) or (780 <= minutes <= 900)


def append_jsonl(path: Path, record: dict) -> bool:
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


def fetch_eastmoney_minute(sym: str, day: str) -> list[dict]:
    import urllib.request, ssl
    code = sym[2:]
    market = "1" if sym.startswith("sh") else "0"
    secid = f"{market}.{code}"
    url = (
        f"https://push2.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}&fields1=f1,f2&fields2=f51,f52,f53,f54,f55,f56,f57"
        f"&klt=1&fqt=1&end=20500101&lmt=1500"
    )
    ctx = ssl.create_default_context()
    ctx.set_ciphers('DEFAULT')
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Referer": "https://quote.eastmoney.com/",
        "Accept": "*/*"
    })
    resp = urllib.request.urlopen(req, timeout=15, context=ctx)
    data = json.loads(resp.read())
    klines = (data.get("data") or {}).get("klines") or []
    records = []
    pre_close = fetch_tencent_prev_close(sym, day)
    for bar in klines:
        parts = bar.split(",")
        bar_day = parts[0].split(" ")[0]
        if bar_day != day:
            continue
        bar_time = parts[0].split(" ")[1][:5] if " " in parts[0] else parts[0][-5:]
        op = float(parts[1])
        close = float(parts[2])
        high = float(parts[3])
        low = float(parts[4])
        vol = float(parts[5]) * 100
        amt_raw = float(parts[6]) if len(parts) > 6 and parts[6] else 0
        amount = amt_raw if amt_raw > 0 else close * vol
        if pre_close is None:
            pre_close = op
        pct = round((close - pre_close) / pre_close * 100, 3) if pre_close and pre_close > 0 else 0
        records.append({
            "time": f"{day}T{bar_time}:00",
            "asOf": bar_time,
            "price": close,
            "pct": pct,
            "amount": round(amount, 2),
            "vol": int(vol),
            "open": op,
            "high": high,
            "low": low,
            "pre_close": pre_close,
        })
    return records


def fetch_sina_quotes(symbols: list[str]) -> dict[str, dict]:
    """直接按代码调新浪实时报价接口（不依赖 ETF 分类列表，绕开列表漏收问题）。

    必须带 Referer 头，否则新浪返回 403。返回 {symbol: record}。
    """
    import urllib.request

    url = "https://hq.sinajs.cn/list=" + ",".join(symbols)
    req = urllib.request.Request(url, headers={
        "Referer": "https://finance.sina.com.cn",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    })
    resp = urllib.request.urlopen(req, timeout=10)
    text = resp.read().decode("gbk", errors="replace")

    now = datetime.now()
    as_of = now.strftime("%H:%M")
    records: dict[str, dict] = {}
    for line in text.splitlines():
        # 格式: var hq_str_sh511130="30年国债ETF博时,开,昨收,现价,最高,最低,...,成交量,成交额,...,日期,时间";
        if "=" not in line:
            continue
        sym = line.split("hq_str_", 1)[1].split("=")[0].strip()
        payload = line.split("=", 1)[1].strip().strip('"').strip(";")
        parts = payload.split(",")
        if sym not in symbols or len(parts) < 32:
            continue
        try:
            name = parts[0]
            open_p = float(parts[1] or 0)
            pre_close = float(parts[2] or 0)
            price = float(parts[3] or 0)
            high = float(parts[4] or 0)
            low = float(parts[5] or 0)
            vol = float(parts[8] or 0)      # 成交量（股）
            amount = float(parts[9] or 0)   # 成交额（元）
            if price <= 0 or pre_close <= 0:
                continue
            pct = round((price - pre_close) / pre_close * 100, 3)
            records[sym] = {
                "time": now.isoformat(),
                "asOf": as_of,
                "name": name,
                "price": price,
                "pct": pct,
                "amount": round(amount, 2),
                "vol": vol,
                "open": open_p,
                "high": high,
                "low": low,
                "pre_close": pre_close,
            }
        except Exception:
            continue
    return records


def fetch_tencent_prev_close(sym: str, day: str) -> float | None:
    """从腾讯日 K 线取 day 之前最近的收盘价（不依赖本地日线文件的时效）。"""
    import urllib.request, json as _json

    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,,,20,qfq"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Referer": "https://gu.qq.com/",
        })
        k = _json.loads(urllib.request.urlopen(req, timeout=10).read()) \
            .get("data", {}).get(sym, {})
        rows = k.get("qfqday") or k.get("day") or []
        for r in reversed(rows):
            if str(r[0]) < day:
                return float(r[2])
    except Exception:
        pass
    return None


def fetch_tencent_minute(sym: str, day: str) -> list[dict]:
    """腾讯 m1 分钟 K 线回补（可取最近数个交易日；东财 kline 接口只给最近一天）。

    行格式: ["202611190931", 开, 收, 高, 低, 量(手), {}, 额(不可靠)]
    """
    import urllib.request, json as _json

    url = f"https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={sym},m1,,800"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Referer": "https://gu.qq.com/",
    })
    rows = _json.loads(urllib.request.urlopen(req, timeout=10).read()) \
        .get("data", {}).get(sym, {}).get("m1", [])

    # 昨收：优先腾讯日 K，回退本地日线文件
    prev_close = fetch_tencent_prev_close(sym, day)
    if prev_close is None:
        daily = PROJECT_ROOT / f"data/etf/daily/{sym}/daily.jsonl"
        if daily.exists():
            for line in reversed(daily.read_text(encoding="utf-8").splitlines()):
                if not line.strip():
                    continue
                try:
                    obj = _json.loads(line)
                except Exception:
                    continue
                if obj.get("date") and obj["date"] < day:
                    prev_close = float(obj.get("close", 0) or 0)
                    break

    day_str = day.replace("-", "")
    records = []
    for row in rows:
        time_raw = str(row[0])
        if not time_raw.startswith(day_str):
            continue
        as_of = f"{time_raw[8:10]}:{time_raw[10:12]}"
        op = float(row[1])
        close = float(row[2])
        high = float(row[3])
        low = float(row[4])
        vol = float(row[5]) * 100  # 手 -> 股
        if prev_close is None:
            prev_close = op
        pct = round((close - prev_close) / prev_close * 100, 3) if prev_close and prev_close > 0 else 0
        records.append({
            "time": f"{day}T{as_of}:00",
            "asOf": as_of,
            "price": close,
            "pct": pct,
            "amount": round(close * vol, 2),
            "vol": vol,
            "open": op,
            "high": high,
            "low": low,
            "pre_close": prev_close,
            "source": "tencent_backfill",
        })
    return records


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="")
    p.add_argument("--day", default=datetime.now().strftime("%Y-%m-%d"))
    p.add_argument("--force", action="store_true")
    p.add_argument("--backfill", action="store_true")
    args = p.parse_args()

    now = datetime.now()
    day = args.day or now.strftime("%Y-%m-%d")
    as_of = now.strftime("%H:%M")

    symbols = [s.strip() for s in str(args.symbols).split(",") if s.strip()]

    if args.backfill and symbols:
        wrote = []
        failed = []
        for sym in symbols:
            try:
                records = fetch_eastmoney_minute(sym, day)
                if not records:
                    # 东财 kline 只返回最近一个交易日，更早的日期走腾讯 m1 历史回补
                    records = fetch_tencent_minute(sym, day)
                if not records:
                    failed.append(sym)
                    continue
                out = PROJECT_ROOT / f"data/etf/minute/{sym}/{day}.jsonl"
                out.parent.mkdir(parents=True, exist_ok=True)
                with open(out, "w", encoding="utf-8") as f:
                    for rec in records:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                wrote.append(sym)
            except Exception:
                failed.append(sym)
        print(json.dumps({
            "ok": True, "day": day, "asOf": as_of,
            "wrote": wrote, "skipped": failed, "symbols": symbols,
            "mode": "backfill"
        }, ensure_ascii=False))
        return 0

    if not args.force and not is_trading_session(now):
        print(json.dumps({"ok": True, "skipped": True, "reason": "not_trading_session", "day": day, "asOf": as_of}))
        return 0

    if not symbols:
        print(json.dumps({"ok": True, "skipped": True, "reason": "empty_symbols", "day": day, "asOf": as_of}))
        return 0

    wrote = []
    skipped = []

    # 优先：新浪实时报价接口直连（不依赖分类列表，避免列表漏收个别 ETF 导致静默断更）
    quotes: dict[str, dict] = {}
    sina_error = None
    try:
        quotes = fetch_sina_quotes(symbols)
    except Exception as e:
        sina_error = str(e)

    df = None
    missing = [s for s in symbols if s not in quotes]
    if missing:
        # 兜底：新浪列表接口（akshare）。列表里没有的 symbol 会在此被 skip。
        try:
            import akshare as ak
            df = ak.fund_etf_category_sina(symbol="ETF基金")
        except Exception as e:
            print(json.dumps({
                "ok": False,
                "error": f"sina_quote_failed: {sina_error}; list_fallback_failed: {e}",
            }))
            return 1

    for sym in symbols:
        record = quotes.get(sym)
        if record is None:
            try:
                row = df[df["代码"] == sym]
                if row.empty:
                    skipped.append(sym)
                    continue
                row = row.iloc[0]
                record = {
                    "time": datetime.now().isoformat(),
                    "asOf": as_of,
                    "price": float(row["最新价"]),
                    "pct": float(row["涨跌幅"]),
                    "amount": float(row["成交额"]),
                    "vol": float(row["成交量"]),
                    "open": float(row["今开"]),
                    "high": float(row["最高"]),
                    "low": float(row["最低"]),
                    "pre_close": float(row["昨收"])
                }
            except Exception:
                skipped.append(sym)
                continue

        out = PROJECT_ROOT / f"data/etf/minute/{sym}/{day}.jsonl"
        ok = append_jsonl(out, record)
        if ok:
            wrote.append(sym)

    print(json.dumps({
        "ok": True,
        "day": day,
        "asOf": as_of,
        "wrote": wrote,
        "skipped": skipped,
        "symbols": symbols,
        "mode": "live"
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
