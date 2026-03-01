#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python3 - <<'PY'
import json
import os
from datetime import datetime
import fetch_sector_data as f

watch_file = os.path.join("data", "sector-watch.json")
watch_list = []
if os.path.exists(watch_file):
    try:
        with open(watch_file, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
        watch_list = obj.get("watch_list") or obj.get("list") or obj.get("sectors") or []
    except Exception:
        watch_list = []
if not isinstance(watch_list, list):
    watch_list = []
payload = f.get_sector_rotation(watch_list, 120)
day = payload.get("day") or datetime.now().strftime("%Y-%m-%d")
fname = f"sector-rotation-{day.replace('-', '')}.json"
path = os.path.join("data", fname)
with open(path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=False)
print(path)
PY
