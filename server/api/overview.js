const ctx = require('../context');
ctx.install(global);

const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');

module.exports = function() {
  const handleRoute = async function(req, res) {
    const url = new URL(req.url, `http://${req.headers.host}`);

  if (url.pathname === '/api/overview/history') {
    const day = latestTradingDay();
    const cacheFile = cacheJsonPath('overview-history', day);
    let cached = readJsonCache(cacheFile);
    if (!cached) {
      const latestCache = findLatestCacheFile('overview-history');
      if (latestCache) cached = readJsonCache(latestCache);
    }
    if (cached) {
      try {
        const p = JSON.parse(cached);
        if (p?.rev === OVERVIEW_CACHE_REV) {
          const last = lastDateInSeries(p?.series?.sse);
          const volLast = lastDateInSeries(p?.volume);
          if (last && last >= day && volLast !== day && p?.series?.sse?.length && p.series.sse.some(x => x.amount > 0)) {
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(cached);
            return true;
          }
        }
      } catch (e) {
        console.error(e);
      }
    }
    if (!isMarketOpenNow()) {
      if (cached) {
        try {
          const p = JSON.parse(cached);
          const hasVol = Array.isArray(p?.volume) && p.volume.length;
          if (!hasVol && p?.rev === OVERVIEW_CACHE_REV) {
            const map = readMarketAmountDailyMap();
            const vol = Array.from(map.values())
              .map(v => ({ date: v.day, amount: v.total }))
              .filter(x => x?.date && x.date < day);
            if (vol.length) {
              p.volume = vol;
              cached = JSON.stringify(p);
              if (p?.day === day) writeJsonCache(cacheFile, cached);
            }
          }
        } catch (e) {
          void e;
        }
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(cached);
        return true;
      }
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ day, series: {}, volume: [], rev: OVERVIEW_CACHE_REV }));
      return true;
    }
    const payload = await buildOverviewHistoryPayload(day);
    if (payload) {
      try {
        const p = JSON.parse(payload);
        if (p?.series?.sse?.length) writeJsonCache(cacheFile, payload);
      } catch (e) {
        console.error(e);
      }
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(payload);
      return true;
    }
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ day, series: {}, volume: [], rev: OVERVIEW_CACHE_REV }));
    return true;
  }
  if (url.pathname === '/api/m1/data/breadth' && req.method === 'GET') {
    try {
      const breadthPath = path.join(__dirname, 'data/market/minute/breadth-cache.jsonl');
      let data = [];
      if (fs.existsSync(breadthPath)) {
        const lines = fs.readFileSync(breadthPath, 'utf8').trim().split('\n');
        data = lines.filter(l => l).map(l => {
          try { return JSON.parse(l); } catch(e) { return null; }
        }).filter(Boolean);
      }
      
      // 如果分时缓存被清空（例如盘后），则尝试读取快照兜底
      if (data.length === 0) {
        const latest = loadLatestBreadthRecord() || loadBreadthFromArchive(latestTradingDay());
        if (latest && typeof latest.upCount === 'number') {
          data.push({
             ok: true,
             up: latest.upCount,
             down: latest.downCount,
             flat: latest.flatCount || 0,
             total: latest.upCount + latest.downCount + (latest.flatCount || 0)
          });
        } else {
          // fallback to old breadth-cache.json if archive not found
          const snapPath = path.join(__dirname, 'data/market/breadth-cache.json');
          if (fs.existsSync(snapPath)) {
            try {
              const snap = JSON.parse(fs.readFileSync(snapPath, 'utf8'));
              if (snap && typeof snap.up === 'number') {
                data.push(snap);
              }
            } catch(e) {}
          }
        }
      }
      
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, data }));
    } catch (e) {
      res.statusCode = 500;
      res.end(JSON.stringify({ ok: false, error: e.message }));
    }
    return true;
  }

  if (url.pathname === '/api/m1/data/volume_history' && req.method === 'GET') {
    try {
      const getBeijingDate = () => {
        const d = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }));
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const date = String(d.getDate()).padStart(2, '0');
        return `${year}-${month}-${date}`;
      };
      
      const dailyPath = path.join(__dirname, 'data/market/daily/amount/daily.jsonl');
      const todayStr = getBeijingDate();
      const minutePath = path.join(__dirname, `data/market/minute/amount/${todayStr}.jsonl`);
      
      let dailyData = [];
      let minuteData = [];
      let minuteYdayData = [];

      // Read daily history
      if (fs.existsSync(dailyPath)) {
        const lines = fs.readFileSync(dailyPath, 'utf8').trim().split('\n');
        dailyData = lines.filter(l => l).map(l => {
          try { return JSON.parse(l); } catch(e) { return null; }
        }).filter(Boolean);
      }

      // Find strictly T-1 trading day
      let ydayStr = null;
      if (dailyData.length > 0) {
        // If the last daily record is today, T-1 is the second to last
        const lastDay = dailyData[dailyData.length - 1].date;
        if (lastDay >= todayStr && dailyData.length > 1) {
          ydayStr = dailyData[dailyData.length - 2].date;
        } else if (lastDay < todayStr) {
          ydayStr = lastDay;
        }
      }

      // Read today's intraday minute data
      if (fs.existsSync(minutePath)) {
        const lines = fs.readFileSync(minutePath, 'utf8').trim().split('\n');
        minuteData = lines.filter(l => l).map(l => {
          try { return JSON.parse(l); } catch(e) { return null; }
        }).filter(Boolean);
      }

      // Read yesterday's intraday minute data for Plan B forecasting
      if (ydayStr) {
        const ydayMinutePath = path.join(__dirname, `data/market/minute/amount/${ydayStr}.jsonl`);
        if (fs.existsSync(ydayMinutePath)) {
          const lines = fs.readFileSync(ydayMinutePath, 'utf8').trim().split('\n');
          minuteYdayData = lines.filter(l => l).map(l => {
            try { return JSON.parse(l); } catch(e) { return null; }
          }).filter(Boolean);
        }
      }

      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, data: dailyData, minute: minuteData, minuteYday: minuteYdayData, ydayStr }));
    } catch (e) {
      res.statusCode = 500;
      res.end(JSON.stringify({ ok: false, error: e.message }));
    }
    return true;
  }

  if (url.pathname === '/api/m1/data/overview' && req.method === 'GET') {
    try {
      const getBeijingNow = () => new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }));
      const formatDay = (d) => {
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const date = String(d.getDate()).padStart(2, '0');
        return `${year}-${month}-${date}`;
      };
      const parseDayFromIntradayFile = (filename) => {
        const m = filename.match(/^etf_snapshot_(\d{4}-\d{2}-\d{2})\.jsonl$/);
        return m ? m[1] : null;
      };
      const readSnapshotFromFile = (filePath, cutoffAsOf) => {
        try {
          const lines = fs.readFileSync(filePath, 'utf8').trim().split('\n').filter(Boolean);
          if (lines.length === 0) return null;
          if (!cutoffAsOf) {
            return JSON.parse(lines[lines.length - 1]);
          }
          let best = null;
          for (let i = 0; i < lines.length; i++) {
            let obj = null;
            try { obj = JSON.parse(lines[i]); } catch (e) { obj = null; }
            if (!obj) continue;
            const asOf = obj.asOf;
            if (!asOf) continue;
            if (asOf <= cutoffAsOf) best = obj;
          }
          if (best) return best;
          return JSON.parse(lines[lines.length - 1]);
        } catch (e) {
          return null;
        }
      };
      
      const warmupPath = path.join(__dirname, 'data/warmup/warmup-60.json');
      const lifecyclePath = path.join(__dirname, 'data/lifecycle/lifecycle.json');
      const dailyAmountPath = path.join(__dirname, 'data/market/daily/amount/daily.jsonl');
      
      const nowBj = getBeijingNow();
      const todayStr = formatDay(nowBj);
      const intradayDir = path.join(__dirname, 'data', 'lifecycle', 'intraday');
      const intradayPathToday = path.join(intradayDir, `etf_snapshot_${todayStr}.jsonl`);

      let warmup = null;
      let lifecycle = null;
      let market_amount = null;
      let intraday_snapshot = null;

      if (fs.existsSync(warmupPath)) {
        warmup = JSON.parse(fs.readFileSync(warmupPath, 'utf8'));
      }
      if (fs.existsSync(lifecyclePath)) {
        lifecycle = JSON.parse(fs.readFileSync(lifecyclePath, 'utf8'));
      }
      if (fs.existsSync(dailyAmountPath)) {
        // 读取最后一行
        const lines = fs.readFileSync(dailyAmountPath, 'utf8').trim().split('\n').filter(Boolean);
        if (lines.length > 0) {
          try {
            market_amount = JSON.parse(lines[lines.length - 1]);
          } catch (e) {}
        }
      }
      const hhmm = nowBj.toTimeString().slice(0, 5);
      const cutoffAsOf = hhmm >= '15:00' ? '15:00' : null;
      if (fs.existsSync(intradayPathToday)) {
        intraday_snapshot = readSnapshotFromFile(intradayPathToday, cutoffAsOf);
      }
      if (!intraday_snapshot && fs.existsSync(intradayDir)) {
        try {
          const files = fs.readdirSync(intradayDir).filter(f => parseDayFromIntradayFile(f));
          const days = files.map(f => parseDayFromIntradayFile(f)).filter(Boolean).sort();
          const lastDay = days.length ? days[days.length - 1] : null;
          if (lastDay) {
            const p = path.join(intradayDir, `etf_snapshot_${lastDay}.jsonl`);
            if (fs.existsSync(p)) intraday_snapshot = readSnapshotFromFile(p, '15:00');
          }
        } catch (e) {}
      }

      const policyPath = path.join(__dirname, '波段策略', 'data', `policy_${todayStr}.json`);
      let policy = null;
      if (fs.existsSync(policyPath)) {
        try { policy = JSON.parse(fs.readFileSync(policyPath, 'utf8')); } catch (e) {}
      }
      const marketStatePath = path.join(__dirname, '波段策略', 'data', 'market_state.json');
      let marketState = null;
      if (fs.existsSync(marketStatePath)) {
        try { marketState = JSON.parse(fs.readFileSync(marketStatePath, 'utf8')); } catch (e) {}
      }

      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, warmup, lifecycle, market_amount, intraday_snapshot, policy, marketState }));
    } catch (e) {
      res.statusCode = 500;
      res.end(JSON.stringify({ ok: false, error: e.message }));
    }
    return true;
  }

  if (url.pathname === '/api/m1/policy' && req.method === 'GET') {
    try {
      const today = url.searchParams.get('day') || new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }))
        .toISOString().slice(0, 10);
      const policyPath = path.join(__dirname, '波段策略', 'data', `policy_${today}.json`);
      if (fs.existsSync(policyPath)) {
        const policy = JSON.parse(fs.readFileSync(policyPath, 'utf8'));
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify(policy));
      } else {
        res.statusCode = 503;
        res.end(JSON.stringify({ ok: false, error: 'policy data not yet generated', day: today }));
      }
    } catch (e) {
      res.statusCode = 500;
      res.end(JSON.stringify({ ok: false, error: e.message }));
    }
    return true;
  }

  if (url.pathname === '/api/m1/market_state' && req.method === 'GET') {
    try {
      const pythonBin = 'python3';
      execFile(pythonBin, ['-c',
        'import sys,os; sys.path.insert(0,os.getcwd()); from 波段策略.market_state import get_effective_state; import json; print(json.dumps(get_effective_state(),ensure_ascii=False))'
      ], { cwd: path.resolve(__dirname, '../..'), timeout: 10000, maxBuffer: 1024 * 1024 }, (err, stdout, stderr) => {
        if (err) {
          res.statusCode = 500;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: false, error: String(stderr || err.message) }));
          return true;
        }
        try {
          const data = JSON.parse(stdout.trim());
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: true, data }));
        } catch (e) {
          res.statusCode = 500;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: false, error: 'parse error' }));
        }
      });
    } catch (e) {
      res.statusCode = 500;
      res.end(JSON.stringify({ ok: false, error: e.message }));
    }
    return true;
  }

  if (url.pathname === '/api/m1/market_state' && req.method === 'POST') {
    try {
      const body = await readBody(req);
      const state = String(body.state || '').trim();
      if (!['震荡', '上升', '下跌'].includes(state)) {
        res.statusCode = 400;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'invalid state, use: 震荡/上升/下跌' }));
        return true;
      }
      const pythonBin = 'python3';
      execFile(pythonBin, ['-c',
        `import sys,os; sys.path.insert(0,os.getcwd()); from 波段策略.market_state import apply_user_override; import json; print(json.dumps(apply_user_override("${state}"),ensure_ascii=False))`
      ], { cwd: path.resolve(__dirname, '../..'), timeout: 10000, maxBuffer: 1024 * 1024 }, (err, stdout, stderr) => {
        if (err) {
          res.statusCode = 500;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: false, error: String(stderr || err.message) }));
          return true;
        }
        try {
          const data = JSON.parse(stdout.trim());
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: true, data }));
        } catch (e) {
          res.statusCode = 500;
          res.end(JSON.stringify({ ok: false, error: 'parse error' }));
        }
      });
    } catch (e) {
      res.statusCode = 500;
      res.end(JSON.stringify({ ok: false, error: e.message }));
    }
    return true;
  }

  if (url.pathname === '/api/m1/market_state' && req.method === 'DELETE') {
    try {
      const pythonBin = 'python3';
      execFile(pythonBin, ['-c',
        'import sys,os; sys.path.insert(0,os.getcwd()); from 波段策略.market_state import clear_user_override; import json; print(json.dumps(clear_user_override(),ensure_ascii=False))'
      ], { cwd: path.resolve(__dirname, '../..'), timeout: 10000, maxBuffer: 1024 * 1024 }, (err, stdout, stderr) => {
        if (err) {
          res.statusCode = 500;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: false, error: String(stderr || err.message) }));
          return true;
        }
        try {
          const data = JSON.parse(stdout.trim());
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: true, data }));
        } catch (e) {
          res.statusCode = 500;
          res.end(JSON.stringify({ ok: false, error: 'parse error' }));
        }
      });
    } catch (e) {
      res.statusCode = 500;
      res.end(JSON.stringify({ ok: false, error: e.message }));
    }
    return true;
  }

  if (url.pathname === '/api/m1/ranged_strategy' && req.method === 'GET') {
    try {
      const pythonBin = 'python3';
      execFile(pythonBin, ['-c',
        'import sys,os; sys.path.insert(0,os.getcwd()); from 波段策略.ranged_strategy import compute_signals; import json; print(json.dumps(compute_signals(),ensure_ascii=False))'
      ], { cwd: path.resolve(__dirname, '../..'), timeout: 15000, maxBuffer: 1024 * 1024 }, (err, stdout, stderr) => {
        if (err) {
          res.statusCode = 500;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: false, error: String(stderr || err.message) }));
          return true;
        }
        try {
          const data = JSON.parse(stdout.trim());
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: true, data }));
        } catch (e) {
          res.statusCode = 500;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: false, error: 'parse error: ' + e.message }));
        }
      });
    } catch (e) {
      res.statusCode = 500;
      res.end(JSON.stringify({ ok: false, error: e.message }));
    }
    return true;
  }

  if (url.pathname === '/api/m1/ranged_strategy/execute' && req.method === 'POST') {
    try {
      const body = await readBody(req);
      const sym = String(body.symbol || '').trim();
      const signalType = String(body.signal_type || '').trim();
      if (!sym || !signalType) {
        res.statusCode = 400;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'symbol and signal_type required' }));
        return true;
      }
      const pythonBin = 'python3';
      execFile(pythonBin, ['-c',
        `import sys,os; sys.path.insert(0,os.getcwd()); from 波段策略.ranged_strategy import execute_signal; import json; print(json.dumps(execute_signal("${sym.replace(/"/g,'\\"')}","${signalType.replace(/"/g,'\\"')}"),ensure_ascii=False))`
      ], { cwd: path.resolve(__dirname, '../..'), timeout: 10000, maxBuffer: 1024 * 1024 }, (err, stdout, stderr) => {
        if (err) {
          res.statusCode = 500;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: false, error: String(stderr || err.message) }));
          return true;
        }
        try {
          const data = JSON.parse(stdout.trim());
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify(data));
        } catch (e) {
          res.statusCode = 500;
          res.end(JSON.stringify({ ok: false, error: 'parse error' }));
        }
      });
    } catch (e) {
      res.statusCode = 500;
      res.end(JSON.stringify({ ok: false, error: e.message }));
    }
    return true;
  }

  if (url.pathname === '/api/m1/ranged_strategy/reset' && req.method === 'POST') {
    try {
      let capital = 100000;
      try {
        const body = await readBody(req);
        capital = Number(body.total_capital) || 100000;
      } catch (e) { /* use default */ }
      const pythonBin = 'python3';
      execFile(pythonBin, ['-c',
        `import sys,os; sys.path.insert(0,os.getcwd()); from 波段策略.ranged_strategy import reset_ranged_state; import json; print(json.dumps(reset_ranged_state(${capital}),ensure_ascii=False))`
      ], { cwd: path.resolve(__dirname, '../..'), timeout: 10000, maxBuffer: 1024 * 1024 }, (err, stdout, stderr) => {
        if (err) {
          res.statusCode = 500;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: false, error: String(stderr || err.message) }));
          return true;
        }
        try {
          const data = JSON.parse(stdout.trim());
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: true, data }));
        } catch (e) {
          res.statusCode = 500;
          res.end(JSON.stringify({ ok: false, error: 'parse error' }));
        }
      });
    } catch (e) {
      res.statusCode = 500;
      res.end(JSON.stringify({ ok: false, error: e.message }));
    }
    return true;
  }

  if (url.pathname === '/api/m1/data/minute' && req.method === 'GET') {
    const symbol = url.searchParams.get('symbol');
    const getBeijingDate = () => {
      const d = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }));
      const year = d.getFullYear();
      const month = String(d.getMonth() + 1).padStart(2, '0');
      const date = String(d.getDate()).padStart(2, '0');
      return `${year}-${month}-${date}`;
    };
    
    // 如果没有传 day，默认取今天
    let day = url.searchParams.get('day') || getBeijingDate();
    
    if (!symbol) {
      res.statusCode = 400;
      return res.end(JSON.stringify({ ok: false, error: 'missing symbol parameter' }));
    }

    try {
      let minutePath = path.join(__dirname, `data/index/minute/${symbol}/${day}.jsonl`);
      if (!fs.existsSync(minutePath)) {
        minutePath = path.join(__dirname, `data/etf/minute/${symbol}/${day}.jsonl`);
      }
      if (!fs.existsSync(minutePath) && ['bank', 'broker', 'insure'].includes(symbol)) {
        minutePath = path.join(__dirname, `data/sector/minute/${symbol}/${day}.jsonl`);
      }

      let data = [];
      let pre_close = null;
      let name = symbol;
      let source_day = day;

      if (fs.existsSync(minutePath)) {
        const lines = fs.readFileSync(minutePath, 'utf8').trim().split('\n');
        data = lines.filter(l => l).map(l => {
          try { return JSON.parse(l); } catch(e) { return null; }
        }).filter(Boolean);
      }

      // 从 daily 数据中获取严谨的昨收价 (T-1 close)
      let dailyPath = path.join(__dirname, `data/index/daily/${symbol}/daily.jsonl`);
      if (!fs.existsSync(dailyPath)) {
        dailyPath = path.join(__dirname, `data/etf/daily/${symbol}/daily.jsonl`);
      }
      if (!fs.existsSync(dailyPath)) {
        dailyPath = path.join(__dirname, `data/etf/${symbol}/daily.jsonl`);
      }
      if (!fs.existsSync(dailyPath) && ['bank', 'broker', 'insure'].includes(symbol)) {
        dailyPath = path.join(__dirname, `data/sector/daily/${symbol}/daily.jsonl`);
      }

      if (fs.existsSync(dailyPath)) {
        try {
          const lines = fs.readFileSync(dailyPath, 'utf8').trim().split('\n');
          const dailyData = lines.filter(l => l).map(l => {
            try { return JSON.parse(l); } catch(e) { return null; }
          }).filter(Boolean);

          if (dailyData.length > 0) {
            const lastDay = dailyData[dailyData.length - 1];
            if (lastDay.date >= day && dailyData.length > 1) {
              // 如果最后一条已经是今天（或未来），则昨收是倒数第二条
              pre_close = dailyData[dailyData.length - 2].close;
            } else if (lastDay.date < day) {
              // 如果最后一条是今天之前，那它就是昨收
              pre_close = lastDay.close;
            } else {
              pre_close = lastDay.close;
            }
          }
        } catch (e) {
          console.error(`Failed to read daily.jsonl for ${symbol} pre_close:`, e.message);
        }
      }

      // 如果 daily 不存在或未能成功提取昨收，尝试从分时数据的第一条回退提取
      if (pre_close === null && data.length > 0) {
        // Find the first valid data point with a pre_close
        const validPt = data.find(pt => pt && pt.pre_close !== undefined);
        if (validPt) {
          pre_close = validPt.pre_close;
        }
      }
      
      // 临时清洗已经落盘的脏数据 (清理 09:30 前或者 price 为 0.0 的集合竞价数据)
      if (data.length > 0) {
          data = data.filter(pt => pt && pt.price > 0 && pt.asOf >= '09:30');
      }

      // 如果数据存在，确保 pct 字段有值，如果没有，通过 pre_close 临时计算
      if (data.length > 0 && pre_close !== null) {
          data.forEach(pt => {
              if (pt.pct === undefined || pt.pct === 0) {
                  pt.pct = Number(((pt.price - pre_close) / pre_close * 100).toFixed(4));
              }
          });
      }

      // ETF 分时数据自带 pre_close 和 pct，大盘指数的分时数据可能没有，统一在这里补充基准
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, symbol, name, day, source_day, pre_close, data }));
    } catch (e) {
      res.statusCode = 500;
      res.end(JSON.stringify({ ok: false, error: e.message }));
    }
    return true;
  }

  if (url.pathname === '/api/m1/run' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        const data = JSON.parse(body || '{}');
        let args = [];
        if (data.script === 'm1_minute_to_daily.py') {
          args = ['treasolo/m1_minute_to_daily.py', '--symbol', data.symbol];
          if (data.day) args.push('--day', data.day);
        } else if (data.script === 'm1_minute_fetch_indices.py') {
          args = ['treasolo/m1_minute_fetch_indices.py'];
          if (data.symbols) args.push('--symbols', data.symbols);
          if (data.day) args.push('--day', data.day);
          if (data.force) args.push('--force');
        } else if (data.script === 'm1_backfill.py') {
          args = ['treasolo/m1_backfill.py', '--symbol', data.symbol, '--missing-window-days', '30'];
          if (data.applyFix) args.push('--apply-fix', '--write');
          if (data.expectEnd) args.push('--expect-end', data.expectEnd);
        } else if (data.script === 'm1_minute_fetch_etf.py') {
          args = ['treasolo/m1_minute_fetch_etf.py'];
          if (data.symbols) args.push('--symbols', data.symbols);
          if (data.day) args.push('--day', data.day);
          if (data.force) args.push('--force');
        } else if (data.script === 'm1_minute_fetch_sector.py') {
          args = ['treasolo/m1_minute_fetch_sector.py'];
          if (data.force) args.push('--force');
        } else if (data.script === 'm1_minute_to_daily_etf.py') {
          args = ['treasolo/m1_minute_to_daily_etf.py', '--symbol', data.symbol];
          if (data.day) args.push('--day', data.day);
        } else if (data.script === 'cleanup_minute_files.py') {
          args = ['treasolo/cleanup_minute_files.py'];
          if (data.keepDays) args.push('--keep-days', String(data.keepDays));
          if (data.apply) args.push('--apply');
        } else if (data.script === 'm1_market_amount.py') {
          args = ['treasolo/m1_market_amount.py'];
          if (data.day) args.push('--day', data.day);
        } else if (data.script === 'breadth_manager.py') {
          args = ['treasolo/breadth_manager.py', data.cmd || 'spot'];
        } else if (data.script === 'm1_warmup.py') {
          args = ['treasolo/m1_warmup.py'];
        } else if (data.script === 'm1_lifecycle.py') {
          args = ['treasolo/m1_lifecycle.py'];
        } else if (data.script === 'm1_ai_aggregator.py') {
          args = ['treasolo/m1_ai_aggregator.py'];
        } else if (data.script === 'm1_ai_reporter.py') {
          args = ['treasolo/m1_ai_reporter.py'];
        } else if (data.script === 'm1_etf_intraday_features.py' || data.script === 'analysis/m1_etf_intraday_features.py') {
          args = ['treasolo/analysis/m1_etf_intraday_features.py'];
          if (data.args) args.push(...data.args);
        } else if (data.script === 'm1_etf_ai_reporter.py') {
          args = ['treasolo/m1_etf_ai_reporter.py'];
        } else {
          res.statusCode = 400;
          return res.end(JSON.stringify({ error: 'unknown script' }));
        }
        
        execFile('python3', args, { cwd: path.resolve(__dirname, '../..'), timeout: 120000, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({
            ok: !err,
            stdout: (stdout || '').trim().split('\n'),
            stderr: stderr
          }));
        });
      } catch (e) {
        res.statusCode = 400;
        res.end(JSON.stringify({ error: e.message }));
      }
    });
    return true;
  }

  // ── /api/m1/stage_state — 五阶段策略实时状态 (V2) ──
  if (url.pathname === '/api/m1/stage_state' && req.method === 'GET') {
    try {
      const day = url.searchParams.get('day') || 'today';
      const syms = url.searchParams.get('symbols') || '';
      const args = ['波段策略/stage_runner.py', '--day', day];
      if (syms) args.push('--symbols', syms);

      execFile('python3', args, { cwd: path.resolve(__dirname, '../..'), timeout: 15000, maxBuffer: 1024 * 1024 }, (err, stdout, stderr) => {
        if (err) {
          res.statusCode = 500;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: false, error: String(stderr || err.message) }));
          return true;
        }
        try {
          const data = JSON.parse(stdout.trim());
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: true, data }));
        } catch (e) {
          res.statusCode = 500;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: false, error: 'parse error', raw: stdout.slice(0, 200) }));
        }
      });
    } catch (e) {
      res.statusCode = 500;
      res.end(JSON.stringify({ ok: false, error: e.message }));
    }
    return true;
  }

    return false;
  };
  return handleRoute;
};
