"""天时缓存生成 — 扩展版: 2024-09-01 ~ 2026-12-31"""
import json, os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from tyme4py.solar import SolarDay

TZ = ZoneInfo("Asia/Shanghai")
SYNODIC_MONTH_DAYS = 29.53058867
PHASE_NAMES = ["新月", "娥眉月", "上弦月", "盈凸月", "满月", "亏凸月", "下弦月", "残月"]
REF_NEW_MOON_UTC = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TIANGAN_WUXING = {"甲":"木","乙":"木","丙":"火","丁":"火","戊":"土","己":"土","庚":"金","辛":"金","壬":"水","癸":"水"}
DIZHI_WUXING = {"子":"水","丑":"土","寅":"木","卯":"木","辰":"土","巳":"火","午":"火","未":"土","申":"金","酉":"金","戌":"土","亥":"水"}

def moon_phase_index(dt):
    bj = datetime(dt.year, dt.month, dt.day, 12, 0, 0, tzinfo=TZ).astimezone(timezone.utc)
    days = (bj - REF_NEW_MOON_UTC).total_seconds() / 86400.0
    age = days % SYNODIC_MONTH_DAYS
    idx = int((age / SYNODIC_MONTH_DAYS) * 8.0 + 0.5) % 8
    return idx, float(age)

start = date(2024, 9, 1)
end = date(2026, 12, 31)
cur = start
lines = []

while cur <= end:
    sd = SolarDay.from_ymd(cur.year, cur.month, cur.day)
    scd = sd.get_sixty_cycle_day()
    ld = sd.get_lunar_day()
    lm = ld.get_lunar_month()
    phase_idx, moon_age = moon_phase_index(cur)
    jiazi = scd.get_name().replace("日", "")
    tg = jiazi[0] if jiazi else ""
    dz = jiazi[1] if len(jiazi) >= 2 else ""
    month_jiazi = scd.get_month().get_name()
    mtg = month_jiazi[0] if month_jiazi else ""
    mdz = month_jiazi[1] if len(month_jiazi) >= 2 else ""
    year_jiazi = scd.get_year().get_name()
    ytg = year_jiazi[0] if year_jiazi else ""
    ydz = year_jiazi[1] if len(year_jiazi) >= 2 else ""

    row = {
        "date": cur.isoformat(),
        "gzDay": jiazi, "tg": tg, "tgWx": TIANGAN_WUXING.get(tg, ""),
        "dz": dz, "dzWx": DIZHI_WUXING.get(dz, ""),
        "gzMonth": month_jiazi, "mtg": mtg, "mtgWx": TIANGAN_WUXING.get(mtg, ""),
        "mdz": mdz, "mdzWx": DIZHI_WUXING.get(mdz, ""),
        "gzYear": year_jiazi, "ytg": ytg, "ytgWx": TIANGAN_WUXING.get(ytg, ""),
        "ydz": ydz, "ydzWx": DIZHI_WUXING.get(ydz, ""),
        "lunarMonth": lm.get_name() if lm else "",
        "lunarDay": ld.get_name() if ld else "",
        "phaseIdx": phase_idx,
        "phaseName": PHASE_NAMES[phase_idx],
        "waxing": "盈" if phase_idx <= 3 else "亏",
        "moonAge": round(moon_age, 3),
        "weekday": cur.weekday(),
    }
    lines.append(json.dumps(row, ensure_ascii=False))
    cur += timedelta(days=1)

outdir = os.path.join(ROOT, "data", "astro")
os.makedirs(outdir, exist_ok=True)
outpath = os.path.join(outdir, "astro_calendar.jsonl")
with open(outpath, "w") as f:
    f.write("\n".join(lines) + "\n")
print(f"缓存: {outpath} | {len(lines)}天")
