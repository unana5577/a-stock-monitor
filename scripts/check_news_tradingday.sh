#!/usr/bin/env bash
set -euo pipefail

BASE="${API_BASE:-http://localhost:8787}"
DATE="${1:-}"
SLOT="${2:-}"

if [ -z "${DATE}" ]; then
  DATE="$(curl -s "${BASE}/api/snapshot/latest?ai=0" | python3 - <<'PY'
import json,sys
try:
  data=json.load(sys.stdin)
  print(data.get("day",""))
except Exception:
  print("")
PY
)"
fi

if [ -z "${DATE}" ]; then
  echo "无法获取日期"
  exit 1
fi

NEWS_JSON="$(curl -s "${BASE}/api/news?date=${DATE}&limit=1")"
HEAT_JSON="$(curl -s "${BASE}/api/news/heat?date=${DATE}")"

NEWS_DATE="$(python3 - <<'PY'
import json,sys
data=json.loads(sys.stdin.read() or "{}")
print(data.get("date",""))
PY
<<<"${NEWS_JSON}")"

HEAT_DATE="$(python3 - <<'PY'
import json,sys
data=json.loads(sys.stdin.read() or "{}")
print(data.get("date",""))
PY
<<<"${HEAT_JSON}")"

echo "date=${DATE}"
echo "news.date=${NEWS_DATE}"
echo "heat.date=${HEAT_DATE}"

if [ -n "${SLOT}" ]; then
  SLOT_JSON="$(curl -s "${BASE}/api/news?date=${DATE}&time_slot=${SLOT}&limit=1")"
  SLOT_DATE="$(python3 - <<'PY'
import json,sys
data=json.loads(sys.stdin.read() or "{}")
print(data.get("date",""))
PY
<<<"${SLOT_JSON}")"
  SLOT_TOTAL="$(python3 - <<'PY'
import json,sys
data=json.loads(sys.stdin.read() or "{}")
print(data.get("total",""))
PY
<<<"${SLOT_JSON}")"
  echo "time_slot=${SLOT}"
  echo "slot.date=${SLOT_DATE}"
  echo "slot.total=${SLOT_TOTAL}"
fi
