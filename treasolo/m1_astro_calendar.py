import argparse
import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from tyme4py.solar import SolarDay


TZ = ZoneInfo("Asia/Shanghai")
SYNODIC_MONTH_DAYS = 29.53058867
PHASE_NAMES = ["新月", "娥眉月", "上弦月", "盈凸月", "满月", "亏凸月", "下弦月", "残月"]
REF_NEW_MOON_UTC = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)


def moon_phase_index(dt: date) -> tuple[int, float]:
    bj = datetime(dt.year, dt.month, dt.day, 12, 0, 0, tzinfo=TZ).astimezone(timezone.utc)
    days = (bj - REF_NEW_MOON_UTC).total_seconds() / 86400.0
    age = days % SYNODIC_MONTH_DAYS
    idx = int((age / SYNODIC_MONTH_DAYS) * 8.0 + 0.5) % 8
    return idx, float(age)


def parse_day(s: str) -> date:
    v = str(s or "").strip()
    if not v:
        raise ValueError("missing_day")
    try:
        y, m, d = v[:10].split("-")
        return date(int(y), int(m), int(d))
    except Exception as e:
        raise ValueError("invalid_day") from e


def parse_month(s: str) -> tuple[int, int]:
    v = str(s or "").strip()
    if not v:
        raise ValueError("missing_month")
    try:
        y, m = v[:7].split("-")
        yy = int(y)
        mm = int(m)
        if mm < 1 or mm > 12:
            raise ValueError("invalid_month")
        return yy, mm
    except Exception as e:
        raise ValueError("invalid_month") from e


def month_range(y: int, m: int) -> tuple[date, date]:
    start = date(y, m, 1)
    if m == 12:
        end = date(y + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(y, m + 1, 1) - timedelta(days=1)
    return start, end


def day_payload(d: date) -> dict:
    sd = SolarDay.from_ymd(d.year, d.month, d.day)
    scd = sd.get_sixty_cycle_day()

    ld = sd.get_lunar_day()
    lunar_month = ld.get_lunar_month()
    phase_idx, moon_age_days = moon_phase_index(d)
    waxing = "盈" if phase_idx <= 3 else "亏"

    return {
        "date": f"{d.year:04d}-{d.month:02d}-{d.day:02d}",
        "sixtyCycleDay": scd.get_name().replace("日", ""),
        "sixtyCycleMonth": scd.get_month().get_name(),
        "lunarMonth": lunar_month.get_name() if lunar_month else "",
        "lunarDay": ld.get_name() if ld else "",
        "phaseIndex": phase_idx,
        "phaseName": PHASE_NAMES[phase_idx] if 0 <= phase_idx < len(PHASE_NAMES) else "",
        "moonAgeDays": round(moon_age_days, 3),
        "waxingWaning": waxing,
    }


def build_days(start: date, end: date) -> list[dict]:
    if end < start:
        return []
    out = []
    cur = start
    while cur <= end:
        out.append(day_payload(cur))
        cur = cur + timedelta(days=1)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--month", default="")
    p.add_argument("--start", default="")
    p.add_argument("--end", default="")
    args = p.parse_args()

    month = str(args.month or "").strip()
    if month:
        y, m = parse_month(month)
        start, end = month_range(y, m)
        days = build_days(start, end)
        out = {
            "ok": True,
            "month": f"{y:04d}-{m:02d}",
            "start": days[0]["date"] if days else f"{start.year:04d}-{start.month:02d}-{start.day:02d}",
            "end": days[-1]["date"] if days else f"{end.year:04d}-{end.month:02d}-{end.day:02d}",
            "days": days,
        }
        print(json.dumps(out, ensure_ascii=False))
        return 0

    start_s = str(args.start or "").strip()
    end_s = str(args.end or "").strip()
    if not start_s or not end_s:
        raise ValueError("missing_range")

    start = parse_day(start_s)
    end = parse_day(end_s)
    days = build_days(start, end)
    out = {
        "ok": True,
        "start": start_s[:10],
        "end": end_s[:10],
        "days": days,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
