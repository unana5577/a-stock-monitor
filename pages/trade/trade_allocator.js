"use strict";

const MARKET_ALLOCATION = {
  "上升": { "科技": 0.70, "资源": 0.30 },
  "震荡": { "科技": 0.50, "资源": 0.50 },
  "下跌": { "科技": 0.30, "资源": 0.70 },
};
const DEFAULT_ALLOCATION = { "科技": 0.50, "资源": 0.50 };

let _cachedState = null;
let _cacheTs = 0;
const CACHE_TTL = 120_000;

async function fetchMarketState() {
  const now = Date.now();
  if (_cachedState && (now - _cacheTs) < CACHE_TTL) return _cachedState;
  try {
    const r = await fetch("/api/m1/market_state");
    const j = await r.json();
    _cachedState = (j.ok && j.data && j.data.state) ? j.data.state : "震荡";
    _cacheTs = now;
  } catch {
    _cachedState = "震荡";
    _cacheTs = now;
  }
  return _cachedState;
}

function getAllocation() {
  const state = _cachedState || "震荡";
  return MARKET_ALLOCATION[state] || DEFAULT_ALLOCATION;
}

function applySectorCap(suggestions, equity) {
  const alloc = getAllocation();
  const sectorTotals = {};
  const sectorItems = {};

  suggestions.forEach(s => {
    const cat = s.category || "科技";
    if (!sectorTotals[cat]) { sectorTotals[cat] = 0; sectorItems[cat] = []; }
    const notional = s.notional || 0;
    sectorTotals[cat] += notional;
    sectorItems[cat].push(s);
  });

  for (const [cat, items] of Object.entries(sectorItems)) {
    const cap = (alloc[cat] || 0.50) * equity;
    const total = sectorTotals[cat];
    if (total <= cap || total <= 0 || cap <= 0) continue;

    const ratio = cap / total;
    items.forEach(s => {
      s.notional = Math.round(s.notional * ratio);
    });
  }

  return suggestions;
}

window.TradeAllocator = {
  fetchMarketState,
  getAllocation,
  applySectorCap,
  MARKET_ALLOCATION,
};
