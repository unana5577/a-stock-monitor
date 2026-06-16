#!/bin/bash
set -e

# Start 3 page modules pointing to 8788 API
# + Shell at 8793

cd /app

API_TARGET=http://a-stock-v2:8788

PORT=8789 API_TARGET=$API_TARGET node pages/overview/server.js &
PORT=8790 API_TARGET=$API_TARGET node pages/etf/server.js &
PORT=8791 API_TARGET=$API_TARGET node pages/trade/server.js &

sleep 2

FRAME_PORT_BASE=8789 PORT=8793 node pages/shell/server.js &

echo "Pages: overview=8789 etf=8790 trade=8791 shell=8793 → API=$API_TARGET"

wait
