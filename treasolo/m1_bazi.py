import argparse
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from tyme4py.solar import SolarDay, SolarTime


TZ = ZoneInfo("Asia/Shanghai")


def parse_birth(s: str) -> datetime:
    v = str(s or "").strip()
    if not v:
        raise ValueError("missing_birth")
    if len(v) == 10:
        v = v + "T12:00"
    if "T" not in v:
        v = v.replace(" ", "T")
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    else:
        dt = dt.astimezone(TZ)
    return dt


def day_of_year(dt: datetime) -> int:
    return int(dt.strftime("%j"))


def equation_of_time_minutes(dt: datetime) -> float:
    n = day_of_year(dt)
    b = 2.0 * math.pi * (n - 81) / 364.0
    return 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)


def strip_admin_suffix(s: str) -> str:
    v = str(s or "").strip()
    for suf in (
        "回族自治州",
        "哈萨克自治州",
        "蒙古自治州",
        "藏族自治州",
        "傣族自治州",
        "布依族苗族自治州",
        "苗族侗族自治州",
        "土家族苗族自治州",
        "朝鲜族自治州",
        "维吾尔自治区",
        "壮族自治区",
        "回族自治区",
        "自治区",
        "特别行政区",
        "地区",
        "盟",
        "市",
        "县",
        "区",
        "镇",
        "乡",
        "街道",
    ):
        if v.endswith(suf):
            v = v[: -len(suf)].strip()
    return v


def normalize_province_cn(s: str) -> str:
    v = str(s or "").strip()
    v = v.replace("特别行政区", "")
    v = v.replace("维吾尔自治区", "")
    v = v.replace("壮族自治区", "")
    v = v.replace("回族自治区", "")
    v = v.replace("自治区", "")
    v = v.replace("省", "")
    v = v.replace("市", "")
    return v.strip()


_CITY_GEO_CACHE: dict | None = None


def load_city_geo() -> dict:
    global _CITY_GEO_CACHE
    if isinstance(_CITY_GEO_CACHE, dict):
        return _CITY_GEO_CACHE
    base = Path(__file__).resolve().parent.parent
    fp = base / "data" / "geo" / "city_geo.json"
    if not fp.exists():
        _CITY_GEO_CACHE = {"idx": {}, "idx_city": {}}
        return _CITY_GEO_CACHE
    raw = fp.read_text(encoding="utf-8")
    arr = json.loads(raw) if raw else []
    idx = {}
    idx_city = {}
    if isinstance(arr, list):
        for r in arr:
            if not isinstance(r, dict):
                continue
            p = normalize_province_cn(r.get("province"))
            c = strip_admin_suffix(r.get("city"))
            a = strip_admin_suffix(r.get("area"))
            try:
                lng = float(r.get("lng"))
            except Exception:
                continue
            if p and c and a:
                idx[(p, c, a)] = lng
            if p and c and (p, c) not in idx_city:
                idx_city[(p, c)] = lng
    _CITY_GEO_CACHE = {"idx": idx, "idx_city": idx_city}
    return _CITY_GEO_CACHE


def lookup_lon_from_city_geo(place: str, detail: str) -> tuple[float | None, dict]:
    pv = str(place or "").strip()
    if not pv:
        return None, {"ok": False, "error": "missing_place"}
    if "-" in pv:
        p0, c0 = pv.split("-", 1)
    else:
        p0, c0 = pv, ""
    p = normalize_province_cn(p0)
    c = strip_admin_suffix(c0)
    d = strip_admin_suffix(str(detail or "").strip())
    db = load_city_geo()
    idx = db.get("idx") if isinstance(db, dict) else {}
    idx_city = db.get("idx_city") if isinstance(db, dict) else {}
    if p and c and d and (p, c, d) in idx:
        return float(idx[(p, c, d)]), {"ok": True, "source": "city_geo", "place": pv, "detail": d}
    if p and c and (p, c) in idx_city:
        return float(idx_city[(p, c)]), {"ok": True, "source": "city_geo", "place": pv, "detail": d or ""}
    return None, {"ok": False, "error": "not_found", "source": "city_geo", "place": pv, "detail": d}


def open_meteo_geocode(name: str) -> tuple[float | None, dict]:
    q = str(name or "").strip()
    if not q:
        return None, {"ok": False, "error": "empty_query"}
    urls = [
        f"https://geocoding-api.open-meteo.com/v1/search?name={quote(q)}&count=5&language=zh&format=json",
        f"https://geocoding-api.open-meteo.com/v1/search?name={quote(q)}&count=5&language=en&format=json",
    ]
    last_err = ""
    for u in urls:
        try:
            req = Request(u, headers={"User-Agent": "a-stock-monitor/1.0"})
            with urlopen(req, timeout=6) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(raw) if raw else {}
            results = data.get("results") or []
            if not isinstance(results, list) or not results:
                continue
            picked = None
            for r in results:
                if isinstance(r, dict) and r.get("country_code") == "CN":
                    picked = r
                    break
            if not picked:
                picked = results[0] if isinstance(results[0], dict) else None
            if not picked:
                continue
            lon = picked.get("longitude")
            lon_f = float(lon)
            return lon_f, {"ok": True, "source": "open-meteo", "query": q, "picked": picked}
        except Exception as e:
            last_err = str(e)
            continue
    return None, {"ok": False, "error": last_err or "not_found", "query": q, "source": "open-meteo"}


def apply_true_solar(dt: datetime, lon: float) -> tuple[datetime, float]:
    offset = (float(lon) - 120.0) * 4.0 + equation_of_time_minutes(dt)
    return dt + timedelta(minutes=offset), float(offset)


def compute_bazi(dt: datetime) -> dict:
    sd = SolarDay.from_ymd(dt.year, dt.month, dt.day)
    scd = sd.get_sixty_cycle_day()
    year_sc = scd.get_year().get_name()
    month_sc = scd.get_month().get_name()
    day_sc = scd.get_name().replace("日", "")
    st = SolarTime.from_ymd_hms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)
    hour_sc = st.get_sixty_cycle_hour().get_name().replace("时", "")
    return {
        "year": year_sc,
        "month": month_sc,
        "day": day_sc,
        "hour": hour_sc,
        "text": f"{year_sc} {month_sc} {day_sc} {hour_sc}",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--gender", default="")
    p.add_argument("--birth", required=True)
    p.add_argument("--place", default="")
    p.add_argument("--place_detail", default="")
    p.add_argument("--lon", default="")
    p.add_argument("--true_solar", action="store_true")
    args = p.parse_args()

    dt0 = parse_birth(args.birth)
    used_dt = dt0
    ts_meta = {"enabled": False}

    if bool(args.true_solar):
        lon_val = None
        geo_meta = {"ok": False}
        if str(args.lon or "").strip():
            try:
                lon_val = float(str(args.lon).strip())
                geo_meta = {"ok": True, "source": "manual"}
            except Exception:
                lon_val = None

        if lon_val is None:
            lon_val, geo_meta = lookup_lon_from_city_geo(args.place, args.place_detail)

        if lon_val is None:
            place = str(args.place or "").strip()
            detail = str(args.place_detail or "").strip()
            city = place.split("-", 1)[1].strip() if "-" in place else place
            candidates = [
                (f"{place} {detail}".replace("-", " ").strip() if detail else ""),
                (detail.strip() if detail else ""),
                (city.strip() if city else ""),
                (strip_admin_suffix(city) if city else ""),
                (strip_admin_suffix(detail) if detail else ""),
            ]
            seen = set()
            for c in candidates:
                cc = str(c or "").strip()
                if not cc or cc in seen:
                    continue
                seen.add(cc)
                lon_val, geo_meta = open_meteo_geocode(cc)
                if lon_val is not None:
                    break

        if lon_val is not None:
            used_dt, offset_min = apply_true_solar(dt0, lon_val)
            ts_meta = {
                "enabled": True,
                "applied": True,
                "lon": lon_val,
                "offsetMinutes": offset_min,
                "birthBeijing": dt0.strftime("%Y-%m-%dT%H:%M"),
                "birthTrueSolar": used_dt.strftime("%Y-%m-%dT%H:%M"),
                "geo": geo_meta,
            }
        else:
            ts_meta = {
                "enabled": True,
                "applied": False,
                "error": "geo_lookup_failed",
                "birthBeijing": dt0.strftime("%Y-%m-%dT%H:%M"),
                "geo": geo_meta,
            }

    payload = {
        "ok": True,
        "gender": str(args.gender or "").strip(),
        "birth": dt0.strftime("%Y-%m-%dT%H:%M"),
        "birthUsed": used_dt.strftime("%Y-%m-%dT%H:%M"),
        "place": str(args.place or "").strip(),
        "placeDetail": str(args.place_detail or "").strip(),
        "trueSolar": ts_meta,
        "bazi": compute_bazi(used_dt),
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

