import argparse
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from tyme4py.solar import SolarDay


TZ = ZoneInfo("Asia/Shanghai")
SYNODIC_MONTH_DAYS = 29.53058867
PHASE_NAMES = ["新月", "娥眉月", "上弦月", "盈凸月", "满月", "亏凸月", "下弦月", "残月"]
REF_NEW_MOON_UTC = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)


def moon_phase_index(y: int, m: int, d: int) -> tuple[int, float]:
    bj = datetime(y, m, d, 12, 0, 0, tzinfo=TZ).astimezone(timezone.utc)
    days = (bj - REF_NEW_MOON_UTC).total_seconds() / 86400.0
    age = days % SYNODIC_MONTH_DAYS
    idx = int((age / SYNODIC_MONTH_DAYS) * 8.0 + 0.5) % 8
    return idx, float(age)


def parse_day(s: str) -> tuple[int, int, int]:
    v = str(s or "").strip()
    if not v:
        raise ValueError("missing_day")
    try:
        dt = datetime.fromisoformat(v[:10]).replace(tzinfo=TZ)
    except Exception as e:
        raise ValueError("invalid_day") from e
    return dt.year, dt.month, dt.day


def ganzhi_for_solar_day(y: int, m: int, d: int) -> dict:
    sd = SolarDay.from_ymd(y, m, d)
    scd = sd.get_sixty_cycle_day()
    return {
        "year": scd.get_year().get_name(),
        "month": scd.get_month().get_name(),
        "day": scd.get_name().replace("日", ""),
    }


def lunar_and_phase_for_solar_day(y: int, m: int, d: int) -> dict:
    sd = SolarDay.from_ymd(y, m, d)
    ld = sd.get_lunar_day()
    lunar_month = ld.get_lunar_month()
    phase_idx, moon_age_days = moon_phase_index(y, m, d)
    phase_day = ld.get_phase_day() if ld else None
    phase_day_text = ""
    if phase_day is not None:
        phase_day_text = phase_day.get_name() if hasattr(phase_day, "get_name") else str(phase_day)
    waxing = ""
    waxing = "盈" if phase_idx <= 3 else "亏"
    return {
        "lunarMonth": lunar_month.get_name() if lunar_month else "",
        "lunarDay": ld.get_name() if ld else "",
        "phaseIndex": phase_idx,
        "phaseName": PHASE_NAMES[phase_idx] if 0 <= phase_idx < len(PHASE_NAMES) else "",
        "phaseDay": phase_day_text,
        "moonAgeDays": round(moon_age_days, 3),
        "waxingWaning": waxing,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--day", required=True)
    args = p.parse_args()

    y, m, d = parse_day(args.day)
    ganzhi = ganzhi_for_solar_day(y, m, d)
    lunar = lunar_and_phase_for_solar_day(y, m, d)

    out = {
        "ok": True,
        "day": f"{y:04d}-{m:02d}-{d:02d}",
        "ganzhi": ganzhi,
        "lunar": lunar,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
