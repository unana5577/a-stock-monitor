#!/bin/bash
# 本地双版本对比: 旧骨架(8787 + 8781-8784) vs 新骨架(8788 + 8789-8792)
# 用法: bash start_dual.sh

set -e
ROOT=/Users/una5577/Documents/trae_projects/a-stock-monitor
NODE=/opt/homebrew/bin/node

echo "=== 关闭旧进程 ==="
lsof -ti :8780 -ti :8781 -ti :8782 -ti :8783 -ti :8784 -ti :8787 -ti :8788 -ti :8789 -ti :8790 -ti :8791 -ti :8792 -ti :8793 2>/dev/null | xargs kill 2>/dev/null || true
sleep 2

echo "=== [旧版本] 8787 API ==="
cd $ROOT && $NODE server.js &
sleep 5

echo "=== [旧版本] 4页面(8781-8784) ==="
$NODE pages/overview/server.js &
$NODE pages/etf/server.js &
$NODE pages/trade/server.js &
$NODE pages/astro/server.js &
sleep 2

echo "=== [旧版本] Shell(8780) ==="
PORT=8780 $NODE pages/shell/server.js &
sleep 2

echo "=== [新骨架] 8788 API ==="
PORT=8788 $NODE server/server.js &
sleep 5

echo "=== [新骨架] 4页面(8789-8792) → 8788 ==="
API_TARGET=http://127.0.0.1:8788 PORT=8789 $NODE pages/overview/server.js &
API_TARGET=http://127.0.0.1:8788 PORT=8790 $NODE pages/etf/server.js &
API_TARGET=http://127.0.0.1:8788 PORT=8791 $NODE pages/trade/server.js &
API_TARGET=http://127.0.0.1:8788 PORT=8792 $NODE pages/astro/server.js &
sleep 2

echo "=== [新骨架] Shell(8793) ==="
FRAME_PORT_BASE=8789 PORT=8793 $NODE pages/shell/server.js &
sleep 2

echo ""
echo "============================================"
echo "  旧版本: http://localhost:8780"
echo "  新骨架: http://localhost:8793"
echo "============================================"
echo ""
echo "验证 8787 vs 8788:"
for api in "api/m1/data/overview" "api/m1/data/breadth" "api/m1/data/volume_history"; do
  v7=$(curl -s --max-time 5 "http://127.0.0.1:8787/$api" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok'))")
  v8=$(curl -s --max-time 5 "http://127.0.0.1:8788/$api" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok'))")
  printf "  %-35s  8787:%-5s  8788:%-5s\n" "$api" "$v7" "$v8"
done
