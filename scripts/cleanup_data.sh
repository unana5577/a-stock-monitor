#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

KEEP_DAYS_CACHE="${KEEP_DAYS_CACHE:-30}"
KEEP_DAYS_NEWS="${KEEP_DAYS_NEWS:-30}"

if [[ ! -d "data" ]]; then
  exit 0
fi

find "data" -maxdepth 1 -type f \( \
  -name 'archive-*.jsonl' -o \
  -name 'minute-*.jsonl' -o \
  -name 'overview-history-*.json' -o \
  -name 'market-breadth-*.json' -o \
  -name 'sector-*.json' -o \
  -name 'rotation-sequence-*.json' -o \
  -name 'intraday-rotation-*.json' -o \
  -name 'volume-*.jsonl' \
  \) -mtime +"$KEEP_DAYS_CACHE" -print -delete

if [[ -d "data/news" ]]; then
  find "data/news" -maxdepth 1 -type f -name '*.json' -mtime +"$KEEP_DAYS_NEWS" -print -delete
fi
