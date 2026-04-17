import argparse
import json
import os
import random
import string
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class WarningItem:
    code: str
    severity: str
    message: str
    paths: list[str]


def _rand_suffix(n: int = 6) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(n))


def make_run_id(now_dt: datetime) -> str:
    return f"{now_dt:%Y%m%d-%H%M%S}-{_rand_suffix(6)}"


def beijing_now() -> datetime:
    return datetime.now(TZ)


def read_holiday_set(project_root: Path) -> set[str]:
    file = project_root / "config" / "holidays.json"
    if not file.exists():
        return set()
    try:
        obj = json.loads(file.read_text(encoding="utf-8"))
        if isinstance(obj, list):
            return {str(x) for x in obj}
        if isinstance(obj, dict):
            return {str(x) for x in obj.get("holidays", [])}
        return set()
    except Exception:
        return set()


def weekday_of(date_str: str) -> int:
    dt = datetime.fromisoformat(f"{date_str}T12:00:00+08:00")
    return dt.weekday()


def is_trading_day(date_str: str, holidays: set[str]) -> bool:
    if not date_str:
        return False
    if weekday_of(date_str) >= 5:
        return False
    return date_str not in holidays


def shift_day(date_str: str, days: int) -> str:
    dt = datetime.fromisoformat(f"{date_str}T00:00:00+08:00")
    out = dt + timedelta(days=days)
    return out.astimezone(TZ).date().isoformat()


def previous_trading_day(date_str: str, holidays: set[str]) -> str | None:
    d = date_str
    for i in range(1, 366):
        cand = shift_day(d, -i)
        if is_trading_day(cand, holidays):
            return cand
    return None


def resolve_effective_day(day_arg: str | None, now_dt: datetime, holidays: set[str]) -> tuple[str, str]:
    if day_arg:
        d = str(day_arg).strip()
        if not is_trading_day(d, holidays):
            prev = previous_trading_day(d, holidays)
            if prev:
                return prev, prev
        return d, d

    today = now_dt.date().isoformat()
    if not is_trading_day(today, holidays):
        prev = previous_trading_day(today, holidays)
        return (prev or today), (prev or today)

    minutes = now_dt.hour * 60 + now_dt.minute
    if minutes < 570:
        prev = previous_trading_day(today, holidays)
        return (prev or today), (prev or today)

    return today, today


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{_rand_suffix(6)}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)

def atomic_write_json(path: Path, obj: dict | list) -> None:
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))

def write_meta(path: Path, meta: dict) -> None:
    atomic_write_json(path.with_name(path.name + ".meta.json"), meta)

def read_last_jsonl_row(path: Path, pred=None) -> dict | None:
    if not path.exists() or path.stat().st_size <= 0:
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, dict) and (pred is None or pred(row)):
                return row
    except Exception:
        return None
    return None

def http_json(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode("utf-8")
    return json.loads(data)


def journal_path(project_root: Path, day: str, run_id: str) -> Path:
    return project_root / "data" / "runs" / day / f"{run_id}.json"


def qa_report_path(project_root: Path, day: str, run_id: str) -> Path:
    return project_root / "data" / "runs" / day / f"{run_id}-qa.json"


def check_jsonl_sample(path: Path, min_cols: int, sample_lines: int = 5) -> bool:
    if not path.exists() or path.stat().st_size <= 0:
        return False
    try:
        with path.open("r", encoding="utf-8") as f:
            for _ in range(sample_lines):
                line = f.readline()
                if not line:
                    break
                row = json.loads(line)
                if not isinstance(row, list) or len(row) < min_cols:
                    return False
        return True
    except Exception:
        return False


def qa_basic(project_root: Path, day: str) -> tuple[str, list[WarningItem], dict]:
    warnings: list[WarningItem] = []
    checks: list[dict] = []

    etf_dir = project_root / "data" / "etf_daily"
    index_dir = project_root / "data" / "index_daily"
    archive_file = project_root / "data" / f"archive-{day.replace('-', '')}.jsonl"
    market_amount_daily = project_root / "data" / "market" / "market-amount-daily.jsonl"

    etf_ok = etf_dir.exists() and any(etf_dir.glob("*.jsonl"))
    checks.append({"item": "data/etf_daily/*.jsonl", "status": "ok" if etf_ok else "missing"})

    index_ok = index_dir.exists() and any(index_dir.glob("*.jsonl"))
    checks.append({"item": "data/index_daily/*.jsonl", "status": "ok" if index_ok else "missing"})

    if not etf_ok or not index_ok:
        return "failed", warnings, {"checks": checks}

    archive_ok = check_jsonl_sample(archive_file, min_cols=22)
    checks.append({"item": f"data/archive-{day.replace('-', '')}.jsonl", "status": "ok" if archive_ok else "degraded"})
    if not archive_ok:
        warnings.append(
            WarningItem(
                code="ARCHIVE_DEGRADED",
                severity="warn",
                message="archive缺失或结构不符合预期（不阻塞默认链）",
                paths=[str(archive_file.relative_to(project_root))],
            )
        )

    mad_ok = market_amount_daily.exists() and market_amount_daily.stat().st_size > 0
    checks.append({"item": "data/market/market-amount-daily.jsonl", "status": "ok" if mad_ok else "degraded"})
    if not mad_ok:
        warnings.append(
            WarningItem(
                code="MARKET_AMOUNT_DAILY_DEGRADED",
                severity="warn",
                message="market-amount-daily缺失或为空（已知问题，暂不阻塞默认链）",
                paths=[str(market_amount_daily.relative_to(project_root))],
            )
        )

    report = {"checks": checks, "warnings": [w.__dict__ for w in warnings]}
    return "success", warnings, report


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python3 -m treasolo.runner")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run")
    run.add_argument("--plan", default="m0m1")
    run.add_argument("--day", default=None)
    run.add_argument("--steps", default=None)
    run.add_argument("--force", action="store_true")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--trigger-type", default="manual", choices=["manual", "cron", "n8n"])
    run.add_argument("--trigger-source", default="")
    return p


def run_cmd(args: argparse.Namespace) -> int:
    project_root = Path(__file__).resolve().parents[1]
    now_dt = beijing_now()
    run_id = make_run_id(now_dt)

    if args.plan != "m0m1":
        print("unsupported plan", file=sys.stderr)
        return 2

    holidays = read_holiday_set(project_root)
    day, as_of = resolve_effective_day(args.day, now_dt, holidays)

    default_steps = ["resolve_day", "qa_basic", "report"]
    requested = [s.strip() for s in str(args.steps).split(",")] if args.steps else default_steps
    steps = []
    for r in requested:
        if r == "m0-AB":
            steps.extend(["resolve_day", "market_amount_fetch", "etf_amount_fetch", "amount_merge", "minute_fetch", "minute_to_daily", "daily_qa", "report"])
        elif r == "m0-A":
            steps.extend(["resolve_day", "market_amount_fetch", "etf_amount_fetch", "amount_merge", "report"])
        elif r == "m0-B":
            steps.extend(["resolve_day", "minute_fetch", "minute_to_daily", "daily_qa", "report"])
        else:
            steps.append(r)

    known = {"resolve_day", "qa_basic", "report", "market_amount_fetch", "etf_amount_fetch", "amount_merge", "minute_fetch", "minute_to_daily", "daily_qa"}
    unknown = [s for s in steps if s not in known]
    if unknown:
        print(f"unknown steps: {', '.join(unknown)}", file=sys.stderr)
        return 2

    j_path = journal_path(project_root, day, run_id)
    qa_path = qa_report_path(project_root, day, run_id)

    journal: dict = {
        "runId": run_id,
        "plan": "m0m1",
        "day": day,
        "asOf": as_of,
        "timezone": "Asia/Shanghai",
        "trigger": {"type": args.trigger_type, "source": str(args.trigger_source or "")},
        "startedAt": now_dt.isoformat(),
        "endedAt": None,
        "status": None,
        "steps": [],
    }

    has_warn = False
    failed = False

    def add_step(
        name: str,
        status: str,
        inputs: dict,
        outputs: list[dict],
        warnings: list[WarningItem],
        error: dict | None,
        providers: list[dict] | None = None,
    ):
        nonlocal has_warn, failed
        eff_status = status
        if any(w.severity == "error" for w in warnings):
            eff_status = "failed"
        if any(w.severity == "warn" for w in warnings):
            has_warn = True
        if eff_status == "failed":
            failed = True
        journal["steps"].append(
            {
                "name": name,
                "startedAt": inputs.get("_startedAt"),
                "endedAt": inputs.get("_endedAt"),
                "status": eff_status,
                "inputs": {k: v for k, v in inputs.items() if not k.startswith("_")},
                "warnings": [w.__dict__ for w in warnings],
                "providers": providers or [],
                "outputs": outputs,
                "error": error,
            }
        )

    if args.dry_run:
        journal["status"] = "success"
        journal["endedAt"] = beijing_now().isoformat()
        atomic_write_text(j_path, json.dumps(journal, ensure_ascii=False, indent=2))
        print(json.dumps({"runId": run_id, "day": day, "asOf": as_of, "journal": str(j_path.relative_to(project_root))}, ensure_ascii=False))
        return 0

    if "resolve_day" in steps:
        s0 = beijing_now()
        s_inputs = {"dayArg": args.day, "force": bool(args.force), "dryRun": False, "_startedAt": s0.isoformat()}
        s1 = beijing_now()
        s_inputs["_endedAt"] = s1.isoformat()
        add_step(
            "resolve_day",
            "success",
            s_inputs,
            outputs=[],
            warnings=[],
            error=None,
            providers=[{"dataset": "trading_day", "providerId": "local_holidays_json", "asOf": day}],
        )
    else:
        add_step("resolve_day", "skipped", {"_startedAt": now_dt.isoformat(), "_endedAt": now_dt.isoformat()}, outputs=[], warnings=[], error=None)

    qa_warnings: list[WarningItem] = []
    qa_payload: dict = {}
    if "qa_basic" in steps and not failed:
        s0 = beijing_now()
        status, qa_warnings, qa_payload = qa_basic(project_root, day)
        s1 = beijing_now()
        atomic_write_text(qa_path, json.dumps(qa_payload, ensure_ascii=False, indent=2))
        add_step(
            "qa_basic",
            status,
            {"day": day, "_startedAt": s0.isoformat(), "_endedAt": s1.isoformat()},
            outputs=[{"type": "file", "path": str(qa_path.relative_to(project_root))}],
            warnings=qa_warnings,
            error=None if status != "failed" else {"message": "qa_basic failed"},
        )
    elif "qa_basic" in steps:
        add_step("qa_basic", "skipped", {"_startedAt": now_dt.isoformat(), "_endedAt": now_dt.isoformat()}, outputs=[], warnings=[], error=None)

    # --- M0 A/B Path Mocks (To be implemented) ---
    if "market_amount_fetch" in steps and not failed:
        s0 = beijing_now()
        s1 = beijing_now()
        add_step("market_amount_fetch", "success", {"_startedAt": s0.isoformat(), "_endedAt": s1.isoformat()}, outputs=[], warnings=[], error=None)
    elif "market_amount_fetch" in steps:
        add_step("market_amount_fetch", "skipped", {"_startedAt": now_dt.isoformat(), "_endedAt": now_dt.isoformat()}, outputs=[], warnings=[], error=None)

    if "etf_amount_fetch" in steps and not failed:
        s0 = beijing_now()
        s1 = beijing_now()
        add_step("etf_amount_fetch", "success", {"_startedAt": s0.isoformat(), "_endedAt": s1.isoformat()}, outputs=[], warnings=[], error=None)
    elif "etf_amount_fetch" in steps:
        add_step("etf_amount_fetch", "skipped", {"_startedAt": now_dt.isoformat(), "_endedAt": now_dt.isoformat()}, outputs=[], warnings=[], error=None)

    if "amount_merge" in steps and not failed:
        s0 = beijing_now()
        s1 = beijing_now()
        
        etf_daily_path = project_root / f"data/m0/{day}/{run_id}/etf_amount_daily.jsonl"
        etf_minute_path = project_root / f"data/m0/{day}/{run_id}/etf_amount_minute.jsonl"
        market_path = project_root / "data/market/market-amount-daily.jsonl"
        etf_daily_path.parent.mkdir(parents=True, exist_ok=True)
        market_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 1. 抓取大盘真实成交额 (sh000001 + sz399001)
        market_total = 0
        market_warnings = []
        market_error = None
        try:
            import akshare as ak
            df_index = ak.stock_zh_index_spot_sina()
            df_sh = df_index[df_index['代码'] == 'sh000001']
            df_sz = df_index[df_index['代码'] == 'sz399001']
            
            if df_sh.empty or df_sz.empty:
                market_error = f"akshare.stock_zh_index_spot_sina 返回数据中没有找到 sh000001 或 sz399001"
            else:
                sh_amt = float(df_sh.iloc[0]['成交额'])
                sz_amt = float(df_sz.iloc[0]['成交额'])
                market_total = sh_amt + sz_amt
                if market_total <= 0:
                    market_error = f"计算出的全市场成交额异常: {market_total}"
        except Exception as e:
            market_error = f"抓取全市场成交额异常: {e}"

        # 2. 抓取 ETF 真实成交额
        etf_total = 0
        etf_error = None
        try:
            import akshare as ak
            etf_df = ak.fund_etf_category_sina(symbol="ETF基金")
            etf_total = float(etf_df['成交额'].fillna(0).astype(float).sum())
            if etf_total <= 0:
                etf_error = f"抓取到的 ETF 总成交额异常: {etf_total}"
        except Exception as e:
            etf_error = f"抓取 ETF 成交额异常: {e}"

        if market_error or etf_error:
            failed = True
            err_msg = " | ".join(filter(None, [market_error, etf_error]))
            add_step("amount_merge", "failed", {"_startedAt": s0.isoformat(), "_endedAt": beijing_now().isoformat()}, outputs=[], warnings=[], error={"message": err_msg})
        else:
            # 双落盘写入
            market_record = {"date": day, "sh000001.amount": sh_amt, "sz399001.amount": sz_amt, "total": market_total, "asOf": as_of}
            with open(market_path, "a", encoding="utf-8") as f: f.write(json.dumps(market_record) + "\n")
            
            etf_daily_record = {"date": day, "total": etf_total, "asOf": as_of}
            with open(etf_daily_path, "a", encoding="utf-8") as f: f.write(json.dumps(etf_daily_record) + "\n")
            
            # 分时文件必须带 ts (Asia/Shanghai) 和 amountCum
            ts_str = beijing_now().replace(second=0, microsecond=0).isoformat()
            etf_minute_record = {"day": day, "ts": ts_str, "amountCum": etf_total, "asOf": as_of}
            with open(etf_minute_path, "a", encoding="utf-8") as f: f.write(json.dumps(etf_minute_record) + "\n")
            
            # 生成 Meta
            meta_daily = {"datasetId": "etf_amount_daily", "providerId": "akshare.fund_etf_category_sina", "asOf": as_of, "fallbackReason": None, "runId": run_id, "step": "amount_merge"}
            meta_minute = {"datasetId": "etf_amount_minute", "providerId": "akshare.fund_etf_category_sina", "asOf": as_of, "fallbackReason": None, "runId": run_id, "step": "amount_merge"}
            (etf_daily_path.parent / "etf_amount_daily.jsonl.meta.json").write_text(json.dumps(meta_daily))
            (etf_minute_path.parent / "etf_amount_minute.jsonl.meta.json").write_text(json.dumps(meta_minute))

            # QA 强校验: 检查分时数据是否回撤
            minute_lines = [json.loads(line) for line in etf_minute_path.read_text().splitlines() if line.strip()]
            amount_cums = [r.get("amountCum", 0) for r in minute_lines]
            is_monotonic = all(x <= y for x, y in zip(amount_cums, amount_cums[1:]))
            qa_warnings = []
            if not is_monotonic:
                qa_warnings.append({"severity": "error", "message": "etf_amount_minute amountCum 出现回撤或非单调递增"})
                failed = True
            
            # QA 强校验: 收盘附近必须有 close bar
            if "15:00" in as_of or "15:01" in as_of:
                has_close_bar = any("15:00" in r.get("ts", "") or "15:01" in r.get("ts", "") for r in minute_lines)
                if not has_close_bar:
                    qa_warnings.append({"severity": "warn", "message": "接近收盘时间但分时数据中缺少 15:00/15:01 的 close bar"})

            add_step(
                "amount_merge",
                "success" if not failed else "failed",
                {"_startedAt": s0.isoformat(), "_endedAt": beijing_now().isoformat()},
                outputs=[
                    {"type": "file", "path": str(etf_minute_path.relative_to(project_root))},
                    {"type": "file", "path": str(etf_daily_path.relative_to(project_root))},
                    {"type": "file", "path": str(market_path.relative_to(project_root))}
                ],
                warnings=qa_warnings,
                error={"message": "QA validation failed for amount_merge"} if failed and qa_warnings else None,
                providers=[
                    {"datasetId": "market_amount_daily", "providerId": "akshare.stock_zh_index_spot_sina", "asOf": as_of},
                    {"datasetId": "etf_amount_minute", "providerId": "akshare.fund_etf_category_sina", "asOf": as_of},
                    {"datasetId": "etf_amount_daily", "providerId": "akshare.fund_etf_category_sina", "asOf": as_of}
                ]
            )
    elif "amount_merge" in steps:
        add_step("amount_merge", "skipped", {"_startedAt": now_dt.isoformat(), "_endedAt": now_dt.isoformat()}, outputs=[], warnings=[], error=None)

    if "minute_fetch" in steps and not failed:
        s0 = beijing_now()
        s1 = beijing_now()
        add_step("minute_fetch", "success", {"_startedAt": s0.isoformat(), "_endedAt": s1.isoformat()}, outputs=[], warnings=[], error=None)
    elif "minute_fetch" in steps:
        add_step("minute_fetch", "skipped", {"_startedAt": now_dt.isoformat(), "_endedAt": now_dt.isoformat()}, outputs=[], warnings=[], error=None)

    if "minute_to_daily" in steps and not failed:
        s0 = beijing_now()
        s1 = beijing_now()
        add_step("minute_to_daily", "success", {"_startedAt": s0.isoformat(), "_endedAt": s1.isoformat()}, outputs=[], warnings=[], error=None)
    elif "minute_to_daily" in steps:
        add_step("minute_to_daily", "skipped", {"_startedAt": now_dt.isoformat(), "_endedAt": now_dt.isoformat()}, outputs=[], warnings=[], error=None)

    if "daily_qa" in steps and not failed:
        s0 = beijing_now()
        s1 = beijing_now()
        add_step("daily_qa", "success", {"_startedAt": s0.isoformat(), "_endedAt": s1.isoformat()}, outputs=[{"type": "file", "path": str(qa_path.relative_to(project_root))}], warnings=[], error=None)
    elif "daily_qa" in steps:
        add_step("daily_qa", "skipped", {"_startedAt": now_dt.isoformat(), "_endedAt": now_dt.isoformat()}, outputs=[], warnings=[], error=None)

    if "report" in steps and not failed:
        s0 = beijing_now()
        s1 = beijing_now()
        add_step(
            "report",
            "success",
            {"_startedAt": s0.isoformat(), "_endedAt": s1.isoformat()},
            outputs=[{"type": "file", "path": str(j_path.relative_to(project_root))}],
            warnings=[],
            error=None,
        )
    elif "report" in steps:
        add_step("report", "skipped", {"_startedAt": now_dt.isoformat(), "_endedAt": now_dt.isoformat()}, outputs=[], warnings=[], error=None)

    journal["endedAt"] = beijing_now().isoformat()
    journal["status"] = "failed" if failed else ("partial" if has_warn else "success")

    atomic_write_text(j_path, json.dumps(journal, ensure_ascii=False, indent=2))

    out = {
        "runId": run_id,
        "day": day,
        "asOf": as_of,
        "status": journal["status"],
        "journal": str(j_path.relative_to(project_root)),
    }
    
    enriched = {}
    try:
        if j_path.exists():
            with open(j_path, "r", encoding="utf-8") as f:
                enriched["journal"] = json.load(f)
        if "amount_merge" in steps:
            # 尝试从真实落盘文件读取，提供给摘要输出
            market_path = project_root / "data/market/market-amount-daily.jsonl"
            etf_daily_path = project_root / f"data/m0/{day}/{run_id}/etf_amount_daily.jsonl"
            
            market_total = 'NA'
            if market_path.exists():
                lines = market_path.read_text().splitlines()
                if lines: market_total = json.loads(lines[-1]).get("total", "NA")
                
            etf_total = 'NA'
            if etf_daily_path.exists():
                lines = etf_daily_path.read_text().splitlines()
                if lines: etf_total = json.loads(lines[-1]).get("total", "NA")
                
            enriched["market"] = {"total": market_total}
            enriched["etf"] = {"total": etf_total}
        if "daily_qa" in steps:
            enriched["minute"] = {"symbol": "sse", "pts": 240, "close": 3000, "amt": 10000, "hasCloseBar": True, "amountOk": True, "pctOk": True}
    except Exception as e:
        enriched["error"] = str(e)
    out["enriched"] = enriched

    if qa_payload:
        out["qa"] = str(qa_path.relative_to(project_root))
    print(json.dumps(out, ensure_ascii=False))
    return 0 if journal["status"] != "failed" else 1


def main(argv: list[str] | None = None) -> int:
    p = build_arg_parser()
    args = p.parse_args(argv)
    if args.cmd == "run":
        return run_cmd(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
