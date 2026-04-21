#!/bin/bash
# Fetch and classify news for today
# Run this script periodically (e.g., every 10 minutes)

cd "$(dirname "$0")"

echo "Fetching news..."
python3 fetch_news.py

echo "Classifying news..."
python3 classify_news.py

echo "Done!"
