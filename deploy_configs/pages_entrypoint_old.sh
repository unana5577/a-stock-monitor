#!/bin/bash
set -e

cd /app

API_TARGET=http://a-stock-app:8787
FRAME_PORT_BASE=8781

PORT=8781 API_TARGET=$API_TARGET node pages/overview/server.js &
PORT=8782 API_TARGET=$API_TARGET node pages/etf/server.js &
PORT=8783 API_TARGET=$API_TARGET node pages/trade/server.js &

sleep 2

FRAME_PORT_BASE=$FRAME_PORT_BASE PORT=8780 node pages/shell/server.js &

echo "OldPages: overview=8781 etf=8782 trade=8783 shell=8780 -> API=$API_TARGET"

wait
