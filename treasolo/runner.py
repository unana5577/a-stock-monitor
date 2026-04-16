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
        add_step(
            "amount_merge",
            "success",
            {"_startedAt": s0.isoformat(), "_endedAt": s1.isoformat()},
            outputs=[
                {"type": "file", "path": f"data/m0/{day}/{run_id}/etf_amount_minute.jsonl"},
                {"type": "file", "path": f"data/m0/{day}/{run_id}/etf_amount_daily.jsonl"},
                {"type": "file", "path": "data/market/market-amount-daily.jsonl"}
            ],
            warnings=[],
            error=None,
            providers=[
                {"datasetId": "market_amount_daily", "providerId": "akshare.fund_etf_hist_sina", "asOf": as_of},
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
