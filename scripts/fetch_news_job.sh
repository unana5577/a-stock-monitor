#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python3 fetch_news.py
python3 classify_news.py
