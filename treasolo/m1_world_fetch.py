"""外盘指数分钟采集: 日经225 / 韩国KOSPI / 恒生指数

数据源: 东方财富 push2 clist (Phase 0 验证: 2026-11-25 与新华社/腾讯三方数值一致)
  - 日经225 57011.62/-2.78% KOSPI 4697.51/-6.16% HSI 21966.01/-1.14% 全部正确
  - 新浪 int_* 全球指数代码存在陈旧数据(日经差1.2万点), 已淘汰
本地代理注意: 东财必须直连, 脚本内清除 *_proxy 环境变量

落盘: data/world/minute/{SYM}/{day}.jsonl  格式 {time, asOf, price, pct, pre_close}
  - 与 data/index/minute 同构, 额外自带 pre_close/pct (API validPt 兜底直接可用)
新鲜度: 依赖东财 f124 时间戳, >15min 未更新视为休市(海外假日/午休自动跳过)
调度: n8n 每分钟调用, 交易时段内每市场各自判断是否写入
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

# 内部代码 -> 东财市场代码/显示名/采集窗口(北京时间分钟数, 含收盘后10分钟补点)
WORLD_MARKETS = {
    "N225": {"em": "100.N225", "name": "日经225", "window": (480, 850)},
    "KS11": {"em": "100.KS11", "name": "韩国KOSPI", "window": (480, 880)},
    "HSI": {"em": "100.HSI", "name": "恒生指数", "window": (570, 970)},
}
FRESHNESS_SECONDS = 15 * 60
# 午间休市(北京时间分钟数, 左闭右开): 日经 10:30-11:30, 恒生 12:00-13:00
LUNCH_BREAKS = {
    "N225": [(630, 690)],
    "HSI": [(720, 780)],
}


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


def fetch_em_quotes() -> dict[str, dict]:
    """东财行情, 返回 {内部代码: {price, pct, chg, pre_close, ts}}

    主源: stock/get 单品接口(逐市场, 稳定)
    备源: clist 批量接口(偶发限流 RemoteDisconnected, 仅作兜底)
    数值核对(2026-11-25): N225 57011.62/-2.78% 昨收58644.63 与新华社一致;
    KS11 4697.51/-6.16%; HSI 21966.01/-1.14% 昨收22219.65 与腾讯qt.gtimg一致
    """
    import requests

    sess = requests.Session()
    sess.proxies = {"http": None, "https": None}
    headers = {"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"}

    out = {}
    for key, meta in WORLD_MARKETS.items():
        got = None
        # 主源: stock/get 单品
        for attempt in range(3):
            try:
                r = sess.get("https://push2.eastmoney.com/api/qt/stock/get",
                             params={"secid": meta["em"], "fltt": 1, "invt": 2,
                                     "fields": "f43,f60,f86,f169,f170"},
                             timeout=10, headers=headers)
                d = r.json().get("data") or {}
                if d.get("f43") and d.get("f60"):
                    got = {"price": round(float(d["f43"]) / 100, 3),
                           "chg": round(float(d.get("f169") or 0) / 100, 3),
                           "pct": round(float(d.get("f170") or 0) / 100, 4),
                           "pre_close": round(float(d["f60"]) / 100, 3),
                           "ts": int(d["f86"])}
                    break
            except Exception:
                time.sleep(1)
        if got:
            out[key] = got

    # 备源: clist 批量, 补齐主源失败的市场
    missing = [k for k in WORLD_MARKETS if k not in out]
    if missing:
        try:
            fs = ",".join(f"i:{WORLD_MARKETS[k]['em']}" for k in missing)
            r = sess.get("https://push2.eastmoney.com/api/qt/clist/get",
                         params={"np": 2, "fltt": 1, "invt": 2, "fs": fs, "pn": 1, "pz": 50,
                                 "po": 1, "fid": "f12", "fields": "f12,f13,f14,f2,f3,f4,f18,f124"},
                         timeout=10, headers=headers)
            diff = (r.json().get("data") or {}).get("diff")
            if isinstance(diff, dict):
                diff = list(diff.values())
            em_to_key = {m["em"]: k for k in missing for m in [WORLD_MARKETS[k]]}
            for it in (diff or []):
                k = em_to_key.get(f"{it.get('f13')}.{it.get('f12')}")
                if k and it.get("f2") and it.get("f18"):
                    out[k] = {"price": round(float(it["f2"]) / 100, 3),
                              "chg": round(float(it["f4"]) / 100, 3),
                              "pct": round(float(it["f3"]) / 100, 4),
                              "pre_close": round(float(it["f18"]) / 100, 3),
                              "ts": int(it["f124"])}
        except Exception:
            pass
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default=",".join(WORLD_MARKETS.keys()))
    p.add_argument("--day", default="")
    p.add_argument("--force", action="store_true", help="跳过交易窗口与新鲜度校验(补数据/测试用)")
    args = p.parse_args()

    now = datetime.now()
    day = args.day or now.strftime("%Y-%m-%d")
    as_of = now.strftime("%H:%M")
    if not args.force and is_weekend(now):
        print(json.dumps({"ok": True, "skipped": True, "reason": "weekend", "day": day, "asOf": as_of}))
        return 0

    today_minutes = now.hour * 60 + now.minute

    # 所有市场都不在采集窗口时直接跳过, 不发起网络请求
    in_window = [s for s in [x.strip() for x in args.symbols.split(",") if x.strip()]
                 if s in WORLD_MARKETS
                 and WORLD_MARKETS[s]["window"][0] <= today_minutes <= WORLD_MARKETS[s]["window"][1]]
    if not args.force and not in_window:
        print(json.dumps({"ok": True, "skipped": True, "reason": "no_market_in_window",
                          "day": day, "asOf": as_of}))
        return 0

    try:
        quotes = fetch_em_quotes()
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"fetch_failed: {e}", "day": day, "asOf": as_of}))
        return 1

    wrote, skipped = [], []
    for sym in [s.strip() for s in args.symbols.split(",") if s.strip()]:
        meta = WORLD_MARKETS.get(sym)
        q = quotes.get(sym)
        if not meta or not q or q["price"] <= 0:
            skipped.append({"sym": sym, "reason": "no_quote"})
            continue

        # 新鲜度: f124 必须 ≤15min 且是今天的行情(海外假日/午休自动跳过)
        fresh = (now.timestamp() - q["ts"]) <= FRESHNESS_SECONDS
        today_quote = datetime.fromtimestamp(q["ts"]).strftime("%Y-%m-%d") == day
        if not args.force and not (fresh and today_quote):
            skipped.append({"sym": sym, "reason": "stale_quote", "ts": q["ts"]})
            continue

        # 交易窗口判断(收盘后10分钟内仍补点, 确保收盘价落盘)
        w_start, w_end = meta["window"]
        if not args.force and not (w_start <= today_minutes <= w_end):
            skipped.append({"sym": sym, "reason": "out_of_window"})
            continue

        # 午间休市: 行情冻结, 不写平线
        if not args.force and any(s <= today_minutes < e for s, e in LUNCH_BREAKS.get(sym, [])):
            skipped.append({"sym": sym, "reason": "lunch_break"})
            continue

        out = PROJECT_ROOT / f"data/world/minute/{sym}/{day}.jsonl"
        record = {
            "time": now.isoformat(),
            "asOf": as_of,
            "price": q["price"],
            "pct": q["pct"],
            "pre_close": q["pre_close"],
        }
        if append_jsonl(out, record):
            wrote.append(sym)
        else:
            skipped.append({"sym": sym, "reason": "dup_asOf"})

    print(json.dumps({"ok": True, "day": day, "asOf": as_of, "wrote": wrote, "skipped": skipped},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
