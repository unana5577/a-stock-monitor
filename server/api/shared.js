const ctx = require('../context');
ctx.install(global);

const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');
const crypto = require('crypto');

module.exports = function() {
  const handleRoute = async function(req, res) {
    const url = new URL(req.url, `http://${req.headers.host}`);

  if (url.pathname === '/api/prompt/stock-daily') {
    try {
      const txt = fs.readFileSync(PROMPT_PATH, 'utf-8');
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ text: txt }));
    } catch (e) {
      res.writeHead(500);
      res.end('prompt read error');
    }
    return true;
  }
  if (url.pathname === '/api/prompt/sector-analysis') {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ text: SECTOR_PROMPT }));
    return true;
  }
  if (url.pathname === '/api/ai/report' && req.method === 'GET') {
    const day = url.searchParams.get('day') || latestTradingDay();
    const force = url.searchParams.get('force') === 'true';
    
    // 把核心处理逻辑封装为异步函数
    const handleReport = async () => {
      // 如果要求强刷，立刻拉起脚本重新生成一次，并等待执行完成
      if (force) {
        try {
          await new Promise((resolve, reject) => {
            const env = Object.assign({}, process.env);
            execFile('python3', ['treasolo/m1_ai_aggregator.py'], { env }, (err) => {
              if (err) return reject(err);
              execFile('python3', ['treasolo/m1_ai_reporter.py'], { env }, (err2) => {
                if (err2) return reject(err2);
                resolve();
              });
            });
          });
        } catch (e) {
          console.error('[AI Force Refresh Error]', e);
        }
      }
      
      const p = path.join(__dirname, `data/market/ai/report.jsonl`);
      if (!fs.existsSync(p)) {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, msg: 'no report found' }));
        return true;
      }
      
      try {
        const lines = fs.readFileSync(p, 'utf-8').split('\n').filter(Boolean);
        const reports = [];
        for (let line of lines) {
          try {
            const obj = JSON.parse(line);
            if (obj.date === day) reports.push(obj);
          } catch(e) {}
        }
        
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        if (reports.length === 0) {
          res.end(JSON.stringify({ ok: false, msg: 'no report for today' }));
        } else {
          res.end(JSON.stringify({ ok: true, data: reports[reports.length - 1] }));
        }
      } catch(e) {
        res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ ok: false, error: e.message }));
      }
    };
    
    // 直接返回 Promise 的结果
    handleReport();
    return true;
  }
  
  if (url.pathname === '/api/ai/debug' && req.method === 'POST') {
    try {
      const raw = await readBody(req);
      const body = raw ? JSON.parse(raw) : {};
      const prompt = body.prompt || fs.readFileSync(PROMPT_PATH, 'utf-8');
      const snap = readLatestArchivePayload() || await buildSnapshotPayload();
      // 调试：打印喂给AI的关键数据
      console.log('[AI Debug] 喂给AI的数据:', JSON.stringify({
        upCount: snap?.sentiment?.upCount,
        downCount: snap?.sentiment?.downCount,
        volume: snap?.sentiment?.volume,
        volumeStr: snap?.sentiment?.volumeStr,
        indices: snap?.indices ? Object.keys(snap.indices) : []
      }));
      const text = await callBailian(prompt, snap);
      lastAiText = text || '';
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ text }));
    } catch (e) {
      const msg = String(e?.message || '');
      const code = msg.includes('missing_key') ? 401 : 500;
      res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: code === 401 ? '缺少API Key' : '调用失败' }));
    }
    return true;
  }
  if (url.pathname === '/api/ai/sector-debug' && req.method === 'POST') {
    try {
      const raw = await readBody(req);
      const body = raw ? JSON.parse(raw) : {};
      const prompt = body.prompt || SECTOR_PROMPT;
      const execPy = (cmd) => new Promise((resolve, reject) => {
        execFile('python3', ['fetch_sector_data.py', cmd], getExecOptions(), (err, stdout) => {
          if (err) return reject(err);
          const out = (stdout || '').trim();
          if (!out) return resolve({});
          try { resolve(JSON.parse(out)); } catch (e) { resolve({}); }
        });
      });
      const [historyData, rankData] = await Promise.all([execPy('history'), execPy('rank')]);
      const input = { history: historyData.history || {}, rank: rankData || {} };
      const text = await callBailian(prompt, input);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ text }));
    } catch (e) {
      const msg = String(e?.message || '');
      const code = msg.includes('missing_key') ? 401 : 500;
      res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: code === 401 ? '缺少API Key' : '调用失败' }));
    }
    return true;
  }
  if (url.pathname === '/api/ai/sector-analysis') {
    const aiReportPath = path.join(__dirname, 'data/market/ai/etf_report.jsonl');
    let reportData = null;
    
    if (fs.existsSync(aiReportPath)) {
      try {
        const lines = fs.readFileSync(aiReportPath, 'utf8').trim().split('\n').filter(Boolean);
        if (lines.length > 0) {
          reportData = JSON.parse(lines[lines.length - 1]);
        }
      } catch (e) {
        console.error('Failed to parse etf_report.jsonl', e);
      }
    }
    
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    if (reportData) {
      res.end(JSON.stringify(reportData));
    } else {
      res.end(JSON.stringify({ text: "暂无今日 AI 板块轮动解析数据，等待自动化任务触发..." }));
    }
    return true;
  }
  if (url.pathname === '/api/market/amount_daily/backfill') {
    const start = url.searchParams.get('start') || '2025-05-19';
    const startDay = start.includes('-') ? start : `${start.slice(0, 4)}-${start.slice(4, 6)}-${start.slice(6, 8)}`;
    const out = await backfillMarketAmountDaily(startDay);
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify(out));
    return true;
  }
  if (url.pathname === '/api/market/amount_daily') {
    const map = readMarketAmountDailyMap();
    const start = url.searchParams.get('start') || '';
    const end = url.searchParams.get('end') || '';
    const items = Array.from(map.values())
      .sort((a, b) => String(a.day).localeCompare(String(b.day)))
      .filter(v => (!start || v.day >= start) && (!end || v.day <= end))
      .map(v => ({ day: v.day, total: v.total, sh: v.sh, sz: v.sz }));
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ ok: true, items }));
    return true;
  }

  // --- [M1 沙盒 BFF 路由] ---
  if (url.pathname === '/api/runner/run' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        const data = JSON.parse(body || '{}');
        const args = ['-m', 'treasolo.runner', 'run', '--plan', data.plan || 'm0m1', '--trigger-type', data.triggerType || 'n8n', '--trigger-source', data.triggerSource || 'n8n-http'];
        if (data.day) args.push('--day', data.day);
        if (data.steps) args.push('--steps', data.steps);
        
        execFile('python3', args, { cwd: __dirname, timeout: 60000, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
          const lines = (stdout || '').trim().split('\n');
          const outRaw = lines[lines.length - 1]; // runner's last line is the JSON
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          // 只要输出了合法的 JSON，就算 runner 内部 failed（exit code 1），也返回 200 给 n8n
          if (outRaw && outRaw.startsWith('{')) {
            res.end(outRaw);
          } else {
            res.statusCode = 500;
            res.end(JSON.stringify({ error: 'runner failed', stderr: stderr || outRaw, stdout }));
          }
        });
      } catch (e) {
        res.statusCode = 400;
        res.end(JSON.stringify({ error: e.message }));
      }
    });
    return true;
  }

  if (url.pathname === '/api/runner/journal') {
    const rel = String(url.searchParams.get('path') || '').trim();
    if (!rel || rel.includes('..') || !rel.startsWith('data/runs/')) {
      res.statusCode = 400;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: 'invalid path' }));
      return true;
    }
    const abs = path.join(__dirname, rel);
    if (!fs.existsSync(abs)) {
      res.statusCode = 404;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: 'not found', path: rel }));
      return true;
    }
    try {
      const obj = JSON.parse(fs.readFileSync(abs, 'utf8'));
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, journal: obj }));
      return true;
    } catch (e) {
      res.statusCode = 500;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: e.message, path: rel }));
      return true;
    }
  }

  if (url.pathname === '/api/runner/file') {
    const rel = String(url.searchParams.get('path') || '').trim();
    if (!rel || rel.includes('..') || !(rel.startsWith('data/m0/') || rel.startsWith('data/market/') || rel.startsWith('data/runs/'))) {
      res.statusCode = 400;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: 'invalid path' }));
      return true;
    }
    const abs = path.join(__dirname, rel);
    if (!fs.existsSync(abs)) {
      res.statusCode = 404;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: 'not found', path: rel }));
      return true;
    }
    try {
      const txt = fs.readFileSync(abs, 'utf8');
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, path: rel, text: txt }));
      return true;
    } catch (e) {
      res.statusCode = 500;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: e.message, path: rel }));
      return true;
    }
  }

  if (url.pathname === '/api/market/etf_amount_total') {
    const refresh = url.searchParams.get('refresh') === '1';
    let updated = null;
    if (refresh) {
      updated = await refreshEtfAmountTotalViaPython();
    }
    const map = readEtfAmountTotalMap();
    const items = Array.from(map.values())
      .sort((a, b) => String(a.day).localeCompare(String(b.day)));
    const latest = items.length ? items[items.length - 1] : null;
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ ok: true, updated, latest, items }));
    return true;
  }
  // 市场日期 API
  if (url.pathname === '/api/market/date') {
    const parts = getBeijingParts();
    const marketDate = getMarketDate();
    const isOpen = isInTradingTime(parts);
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ date: marketDate, isOpen, parts }));
    return true;
  }
  if (url.pathname === '/api/snapshot') {
    const snap = await buildSnapshotPayload();
    warmupDay(snap.day || latestTradingDay());
    const needAi = url.searchParams.get('ai') !== '0';
    snap.aiText = needAi ? await ensureAiText(snap) : (lastAiText || '');
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify(snap));
    return true;
  }
  if (url.pathname === '/api/snapshot/latest') {
    const forceRefresh = url.searchParams.get('refresh') === '1';
    let snap = readLatestArchivePayload();
    const missing = !snap || !isNum(snap.bonds?.gov?.pct) || !isNum(snap.sectors?.bank?.pct) || !isNum(snap.sectors?.broker?.pct) || !isNum(snap.sectors?.insure?.pct);
    const stale = forceRefresh || !snap || !isNum(snap.ts) || (now() - snap.ts > CACHE_TTL_MS);
    // 午休时间也需要获取当日数据
    const needFresh = isMarketOpenNow() || isLunchBreakNow();
    if (stale || missing) {
      let fresh = null;
      try {
        if (needFresh) fresh = await withTimeout(buildSnapshotPayload(), 6000);
      } catch (e) {
        fresh = null;
      }
      if (fresh) {
        warmupDay(fresh.day || latestTradingDay());
        const needAi = url.searchParams.get('ai') !== '0';
        fresh.aiText = needAi ? await ensureAiText(fresh) : (lastAiText || '');
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify(fresh));
        return true;
      }
      const fallback = lastGoodSnapshot.payload || snap;
      if (fallback) {
        const fixed = repairSnapshot(fallback);
        const needAi = url.searchParams.get('ai') !== '0';
        fixed.aiText = needAi ? await ensureAiText(fixed) : (lastAiText || '');
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify(fixed));
        // 开盘时间或午休时间都触发后台更新
        if (needFresh) {
          buildSnapshotPayload().then((v) => {
            if (!v) return;
            lastGoodSnapshot.payload = v;
            lastGoodSnapshot.ts = v.ts || now();
            archiveSnapshot(v);
          }).catch(() => {});
        }
        return true;
      }
    }
    snap = repairSnapshot(snap);
    if (snap?.sentiment) {
      const baseDay = latestTradingDay();
      const open = isMarketOpenNow();
      const day = open ? (snap.day || baseDay) : baseDay;
      if (!open) snap.day = day;
      warmupDay(day);
      snap.sentiment.volumeCmp = buildVolumeCompare(day, snap.sentiment.volume || null);
      ensureVolumeFile(day);
      snap.sentiment.volumeSeries = readVolumeSeries(day);
      const t1Day = findPreviousTradingDay(day);
      let volumeSeriesYday = [];
      const missingList = [];
      if (t1Day && isUsableVolumeDay(t1Day)) {
        ensureVolumeFile(t1Day);
        volumeSeriesYday = readVolumeSeries(t1Day);
      } else if (t1Day) {
        missingList.push('t1_volume');
      }
      if (snap.sentiment.volumeCmp?.data_incomplete) missingList.push(...(snap.sentiment.volumeCmp?.missing || []));
      snap.sentiment.volumeSeriesYday = volumeSeriesYday;
      snap.sentiment.t1_day = t1Day || null;
      snap.sentiment.data_incomplete = missingList.length > 0;
      snap.sentiment.missing = Array.from(new Set(missingList));
    }
    if (snap && snap.bonds && isNum(snap.bonds.t2603?.price) && isNum(snap.bonds.tl2603?.price)) {
      lastGoodSnapshot.payload = snap;
      lastGoodSnapshot.ts = snap.ts || now();
    }
    if (!snap) {
      res.writeHead(503, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Service temporarily unavailable' }));
      return true;
    }
    const needAi = url.searchParams.get('ai') !== '0';
    snap.aiText = needAi ? await ensureAiText(snap) : (lastAiText || '');
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify(snap));
    return true;
  }
  if (url.pathname === '/api/data/health') {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    const health = await execPythonJson(['treasolo/get_data_health.py'], 30000);
    if (!health) {
      res.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'Failed to get data health status' }));
      return true;
    }
    res.end(JSON.stringify(health));
    return true;
  }
  if (url.pathname === '/api/data/monitoring') {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    const monitoring = await execPythonJson(['treasolo/get_data_monitoring.py'], 30000);
    if (!monitoring) {
      res.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'Failed to get data monitoring status' }));
      return true;
    }
    res.end(JSON.stringify(monitoring));
    return true;
  }
  if (url.pathname === '/health') {
    res.setHeader('Content-Type', 'application/json');
    const mt = lastGoodMinute.get('t');
    const mtl = lastGoodMinute.get('tl');
    res.end(JSON.stringify({
      ok: true,
      source: 'Ashare+Tencent',
      bonds: {
        t: isNum(lastGoodSnapshot.payload?.bonds?.t2603?.price),
        tl: isNum(lastGoodSnapshot.payload?.bonds?.tl2603?.price),
        lastSnapshotTs: lastGoodSnapshot.ts || null,
        lastMinuteT: mt?.series?.length || 0,
        lastMinuteTl: mtl?.series?.length || 0
      }
    }));
    return true;
  }
  if (url.pathname === '/api/market/status') {
    const parts = getBeijingParts();
    const today = parts?.date || null;
    const weekday = today ? getBeijingWeekday(today) : null;
    const tradingDay = today ? isTradingDay(today) : false;
    const marketOpen = isMarketOpenNow();
    const afterClose = isAfterCloseNow();
    let reason = 'unknown';
    if (!parts || !today) reason = 'time_unavailable';
    else if (!tradingDay) reason = (weekday === 0 || weekday === 6) ? 'weekend' : 'holiday';
    else if (marketOpen) reason = 'open';
    else if (afterClose) reason = 'after_close';
    else reason = 'pre_market';
    const strategy = marketOpen ? 'realtime_fetch' : 'cache_only';
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({
      now: today,
      minutes: parts?.minutes ?? null,
      weekday,
      trading_day: tradingDay,
      market_open: marketOpen,
      after_close: afterClose,
      trade_day: latestTradingDay(),
      reason,
      strategy
    }));
    return true;
  }

  if (url.pathname === '/api/news') {
    const day = normalizeDateParam(url.searchParams.get('date'));
    if (!day) {
      res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'invalid date, expected YYYY-MM-DD' }));
      return true;
    }
    const sector = String(url.searchParams.get('sector') || '').trim();
    const level = String(url.searchParams.get('level') || '').trim();
    const rawLimit = Number(url.searchParams.get('limit'));
    const limit = Number.isFinite(rawLimit) ? Math.min(500, Math.max(1, Math.floor(rawLimit))) : 50;

    const allNews = readNewsByDate(day);
    const filteredNews = allNews.filter((item) => {
      if (sector && item?.classify?.sector !== sector) return false;
      if (level && item?.classify?.level !== level) return false;
      return true;
    });

    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({
      date: day,
      total: allNews.length,
      filtered: filteredNews.length,
      news: filteredNews.slice(0, limit)
    }));
    return true;
  }

  if (url.pathname === '/api/news/heat') {
    const day = normalizeDateParam(url.searchParams.get('date'));
    if (!day) {
      res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'invalid date, expected YYYY-MM-DD' }));
      return true;
    }
    const allNews = readNewsByDate(day);
    const heat = buildNewsHeat(allNews);
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({
      date: day,
      total_news: allNews.length,
      by_type: heat.byType,
      by_sector: heat.bySector,
      by_sentiment: heat.bySentiment,
      by_level: heat.byLevel,
      by_type_sentiment: heat.byTypeSentiment,
      by_sector_sentiment: heat.bySectorSentiment
    }));
    return true;
  }

  if (url.pathname === '/api/watch-stocks') {
    if (req.method === 'POST') {
      try {
        const raw = await readBody(req);
        const body = raw ? JSON.parse(raw) : {};
        const incoming = body?.stock || body?.code || body?.symbol || '';
        const code = normalizeStockCode(incoming);
        if (!code) {
          res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
          res.end(JSON.stringify({ error: 'stock code is required' }));
          return true;
        }
        const list = readWatchStocks();
        if (!list.includes(code)) list.push(code);
        const saved = writeWatchStocks(list);
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ total: saved.length, watch_stocks: saved }));
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ error: 'bad request' }));
      }
      return true;
    }
    const list = readWatchStocks();
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ total: list.length, watch_stocks: list }));
    return true;
  }

  if (url.pathname === '/api/calendar') {
    const month = normalizeMonthParam(url.searchParams.get('date'));
    if (!month) {
      res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'invalid date, expected YYYY-MM' }));
      return true;
    }
    const events = readCalendarEvents().filter((item) => {
      const day = String(item?.date || '').trim();
      return day.startsWith(`${month}-`);
    });
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ month, total: events.length, events }));
    return true;
  }

  if (url.pathname === '/api/sector/rank') {
    const day = latestTradingDay();
    const cacheFile = cacheJsonPath('sector-rank', day);
    const cached = readJsonCache(cacheFile);
    if (cached) {
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(cached);
      return true;
    }
    execFile('python3', ['fetch_sector_data.py', 'rank'], getExecOptions(), (err, stdout) => {
      if (err) {
        console.error(err);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: "Failed to fetch sector rank" }));
        return true;
      }
      const out = (stdout || '').trim();
      if (out && isJsonText(out)) writeJsonCache(cacheFile, out);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(out || '{}');
    });
    return true;
  }

  if (url.pathname === '/api/sector/history') {
    const realtime = url.searchParams.get('rt') === '1';
    const sectorsParam = url.searchParams.get('sectors');
    const daysParam = url.searchParams.get('days');
    const days = Number.isFinite(Number(daysParam)) ? Math.max(1, Number(daysParam)) : 20;
    const hasExplicitSectors = !!(sectorsParam && sectorsParam.trim());
    const list = hasExplicitSectors ? sectorsParam.trim() : readWatchList().join(',');
    // 交易日内（含午休）使用实际日期，非交易日使用最近交易日
    const parts = getBeijingParts();
    const today = parts ? parts.date : new Date().toISOString().slice(0, 10);
    const day = isTradingDaySession() ? today : latestTradingDay();
    const cacheFile = !realtime ? sectorCacheFile('sector-history', day, list, days) : null;
    const cfg = readSectorProxyConfig();
    if (cfg.force_etf) {
      const names = list.split(',').map(s => s.trim()).filter(Boolean);
      const variant = 'etf';
      const proxyMap = (cfg.variants && (cfg.variants[variant] || {})) || {};
      const missingNames = names.filter(n => !proxyMap[n]);
      const history = {};
      const minute = {};
      for (const name of names) {
        const code = proxyMap[name] || null;
        if (!code) continue;
        const res = await fetchTencentDaily(code, days);
        history[name] = (res?.data || []).map(r => ({
          date: r.date,
          open: r.open,
          high: r.high,
          low: r.low,
          close: r.close,
          pct: r.pct,
          amount: r.amount,
          volume: r.volume,
          turnover: r.turnover
        }));
        const m = await fetchAshareMinute(code);
        minute[name] = { series: m?.data || [], prevClose: m?.prevClose ?? null };
      }
      const normalized = normalizeHistoryPayloadToDay({ day, history, indicators: {}, minute, correlations: [], watch: names, variant, data_incomplete: missingNames.length > 0, missing: missingNames, source: 'etf_proxy' }, day);
      const payload = JSON.stringify(normalized);
      if (cacheFile && payload && isJsonText(payload)) writeJsonCache(cacheFile, payload);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(payload);
      return true;
    }
    let staleCached = null;
    if (cacheFile) {
      const cached = readJsonCache(cacheFile);
      if (cached) {
        try {
          const p = JSON.parse(cached);
          const history = p?.history || {};
          let latest = null;
          Object.values(history).forEach((arr) => {
            if (!Array.isArray(arr) || !arr.length) return;
            const d = arr[arr.length - 1]?.date;
            if (d && (!latest || d > latest)) latest = d;
          });
          const gap = latest ? dateDiffDays(day, latest) : null;
          const tooOld = gap != null && gap > 2;
          if (latest && !tooOld && String(latest).localeCompare(day) >= 0) {
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(cached);
            return true;
          }
          // 交易日内（含午休）不使用缓存，获取实时数据
          const inSession = isTradingDaySession();
          if (!realtime && !tooOld && isAfterCloseNow()) {
            staleCached = cached;
          } else if (!realtime && !tooOld && !inSession) {
            // 非交易时段才使用缓存
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(cached);
            warmupSectorCache('history_dynamic', list, days, cacheFile);
            return true;
          } else if (tooOld) {
            staleCached = cached;
          }
        } catch (e) {
          console.error(e);
        }
      }
    }
    if (!hasExplicitSectors) {
      const fallbackFile = findLatestCacheFile('sector-history');
      if (fallbackFile) {
        const cached = readJsonCache(fallbackFile);
        if (cached) {
          try {
            const p = JSON.parse(cached);
            const history = p?.history || {};
            let latest = null;
            Object.values(history).forEach((arr) => {
              if (!Array.isArray(arr) || !arr.length) return;
              const d = arr[arr.length - 1]?.date;
              if (d && (!latest || d > latest)) latest = d;
            });
            const gap = latest ? dateDiffDays(day, latest) : null;
            const tooOld = gap != null && gap > 2;
            const inSession = isTradingDaySession();
            if (!realtime && !tooOld && isAfterCloseNow()) {
              staleCached = cached;
            } else if (!realtime && !tooOld && !inSession) {
              // 非交易时段才使用fallback缓存
              res.setHeader('Content-Type', 'application/json; charset=utf-8');
              res.end(cached);
              if (cacheFile) warmupSectorCache('history_dynamic', list, days, cacheFile);
              return true;
            } else if (tooOld) {
              staleCached = cached;
            }
          } catch (e) {
            console.error(e);
          }
        }
      }
    }
    const useDynamic = list && list.trim();
    const args = ['fetch_sector_data.py', useDynamic ? 'history_dynamic' : 'history'];
    if (useDynamic) {
      args.push(list);
      args.push(String(days));
    } else {
      args.push(String(days));
    }
    const inTradingSession = isTradingDaySession();
    if (!inTradingSession) {
      if (staleCached) {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(staleCached);
        return true;
      }
      const opts = { ...getExecOptions(), env: { ...getExecOptions().env || process.env, CACHE_ONLY: '1' } };
    execFile('python3', args, opts, (err, stdout) => {
        const out = (stdout || '').trim();
        if (!err && out && isJsonText(out)) {
          if (cacheFile) writeJsonCache(cacheFile, out);
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(out);
          return true;
        }
        const names = list.split(',').map(s => s.trim()).filter(Boolean);
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ day, history: {}, indicators: {}, minute: {}, correlations: [], watch: names, data_incomplete: true, reason: 'market_closed' }));
      });
      return true;
    }
    execFile('python3', args, getExecOptions(), (err, stdout) => {
      if (err) {
        console.error(err);
        if (staleCached) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(staleCached);
          if (cacheFile) warmupSectorCache('history_dynamic', list, days, cacheFile);
          return true;
        }
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: "Failed to fetch sector history" }));
        return true;
      }
      const out = (stdout || '').trim();
      if (cacheFile && out && isJsonText(out)) writeJsonCache(cacheFile, out);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(out || '{}');
    });
    return true;
  }

  if (url.pathname === '/api/sector/warmup') {
    const sectorsParam = url.searchParams.get('sectors');
    const daysParam = url.searchParams.get('days');
    const startParam = url.searchParams.get('start');
    const endParamRaw = url.searchParams.get('end');
    const endTradingDay = latestTradingDay();
    const endParam = (endParamRaw && endParamRaw.trim()) ? endParamRaw.trim() : endTradingDay;
    let days = Number.isFinite(Number(daysParam)) ? Math.max(10, Number(daysParam)) : 60;
    if (startParam && endParam) {
      try {
        const start = new Date(String(startParam).trim());
        const end = new Date(String(endParam).trim());
        const delta = Math.ceil((end.getTime() - start.getTime()) / (24 * 3600 * 1000)) + 1;
        if (Number.isFinite(delta) && delta > 0) days = Math.max(10, delta);
      } catch (e) {
        void e;
      }
    }
    const list = sectorsParam && sectorsParam.trim() ? sectorsParam.trim() : readWatchList().join(',');
    const day = endParam;
    const historyCache = sectorCacheFile('sector-history', day, list, days);
    const lifecycleCache = sectorCacheFile('sector-lifecycle', day, list, days);
    const rotationCache = sectorCacheFile('sector-rotation', day, list, Math.max(90, days));
    const status = {
      history: warmupSectorCache('history_dynamic', list, days, historyCache),
      lifecycle: warmupSectorCache('lifecycle_dynamic', list, days, lifecycleCache),
      rotation: warmupSectorCache('rotation_dynamic', list, Math.max(90, days), rotationCache)
    };
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ day, start: startParam || null, end: endParam, status, days }));
    return true;
  }

  if (url.pathname === '/api/sector/proxy') {
    if (req.method === 'GET') {
      const dir = path.join(__dirname, 'data');
      fs.mkdirSync(dir, { recursive: true });
      let json = readJsonFileSafe(PROXY_FILE);
      if (!json || typeof json !== 'object') {
        json = {
          default_variant: 'etf',
          force_etf: false,
          variants: {
            etf: {
              "半导体": "sz159995",
              "云计算": "sh516510",
              "新能源": "sh516160",
              "商业航天": "sh563530",
              "创新药": "sz159992",
              "有色金属": "sh512400",
              "通讯设备": "sh515050"
            },
            index: {
              "半导体": "sh000990",
              "云计算": "sh000941",
              "新能源": "sh000941",
              "商业航天": "BK0963",
              "创新药": "sz399989",
              "有色金属": "sh000819",
              "通讯设备": "sh000997"
            }
          },
          updated_at: new Date().toISOString()
        };
        fs.writeFileSync(PROXY_FILE, JSON.stringify(json, null, 2));
      }
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify(readSectorProxyConfig()));
      return true;
    }
    if (req.method === 'POST') {
      const raw = await readBody(req);
      let body = {};
      try { body = raw ? JSON.parse(raw) : {}; } catch (e) { body = {}; }
      const dir = path.join(__dirname, 'data');
      fs.mkdirSync(dir, { recursive: true });
      const cur = readJsonFileSafe(PROXY_FILE) || {};
      const next = {
        default_variant: String(body.default_variant || cur.default_variant || 'etf'),
        force_etf: typeof body.force_etf === 'boolean' ? body.force_etf : !!cur.force_etf,
        variants: Object.assign({}, cur.variants || {}, body.variants || {}),
        updated_at: new Date().toISOString()
      };
      fs.writeFileSync(PROXY_FILE, JSON.stringify(next, null, 2));
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify(next));
      return true;
    }
    res.writeHead(405, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'method_not_allowed' }));
    return true;
  }

  if (url.pathname === '/api/sector/force_etf') {
    if (req.method !== 'POST') {
      res.writeHead(405, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'method_not_allowed' }));
      return true;
    }
    const raw = await readBody(req);
    let body = {};
    try { body = raw ? JSON.parse(raw) : {}; } catch (e) { body = {}; }
    const dir = path.join(__dirname, 'data');
    fs.mkdirSync(dir, { recursive: true });
    const cur = readJsonFileSafe(PROXY_FILE) || {};
    const force = typeof body.force_etf === 'boolean' ? body.force_etf : true;
    const next = {
      default_variant: String(cur.default_variant || 'etf'),
      force_etf: force,
      variants: Object.assign({}, cur.variants || {}),
      updated_at: new Date().toISOString()
    };
    fs.writeFileSync(PROXY_FILE, JSON.stringify(next, null, 2));
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify(next));
    return true;
  }

  if (url.pathname === '/api/sector/history_proxy') {
    const sectorsParam = url.searchParams.get('sectors');
    const daysParam = url.searchParams.get('days');
    const force = url.searchParams.get('force') === '1';
    const days = Number.isFinite(Number(daysParam)) ? Math.max(10, Number(daysParam)) : 60;
    const list = sectorsParam && sectorsParam.trim() ? sectorsParam.trim() : readWatchList().join(',');
    const names = list.split(',').map(s => s.trim()).filter(Boolean);
    const day = latestTradingDay();
    const cacheFile = sectorCacheFile('sector-history-proxy', day, list, days);
    const cfg = readSectorProxyConfig();
    const variant = cfg.force_etf ? 'etf' : (cfg.default_variant || 'etf');
    const proxyMap = (cfg.variants && (cfg.variants[variant] || {})) || {};
    const missingNames = names.filter(n => !proxyMap[n]);
    const allowFetch = force || isMarketOpenNow();
    if (!allowFetch) {
      // ✅ 在检查缓存之前先检查warmup文件
      const warmupFile = path.join(__dirname, 'data', `sector-history-warmup-60.json`);
      if (fs.existsSync(warmupFile)) {
        try {
          const txt = fs.readFileSync(warmupFile, 'utf-8');
          if (txt && isJsonText(txt)) {
            const obj = JSON.parse(txt);
            obj.variant = obj.variant || variant;
            obj.data_incomplete = missingNames.length > 0;
            obj.missing = missingNames;
            obj.source = 'etf_proxy_warmup';
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify(obj));
            return true;
          }
        } catch (e) {
          console.error('Warmup读取错误:', e);
        }
      }
      const cached = readJsonCache(cacheFile);
      if (cached) {
        try {
          const obj = JSON.parse(cached);
          const normalized = normalizeHistoryPayloadToDay(obj, day);
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify(normalized));
        } catch (e) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(cached);
        }
        return true;
      }
      const latestCached = findLatestCacheFileOnOrBefore('sector-history-proxy', day);
      if (latestCached) {
        const txt = readJsonCache(latestCached);
        if (txt) {
          try {
            const obj = JSON.parse(txt);
            const normalized = normalizeHistoryPayloadToDay(obj, day);
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify(normalized));
          } catch (e) {
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(txt);
          }
          return true;
        }
      }
      const fallbackFile = findLatestCacheFileOnOrBefore('sector-history', null);
      if (fallbackFile) {
        const txt = readJsonCache(fallbackFile);
        if (txt && isJsonText(txt)) {
          try {
            const obj = JSON.parse(txt);
            const normalized = normalizeHistoryPayloadToDay(obj, day);
            normalized.variant = variant;
            normalized.data_incomplete = true;
            normalized.missing = missingNames;
            normalized.source = 'fallback_index';
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify(normalized));
            return true;
          } catch (e) {
            void e;
          }
        }
      }
      // 没有缓存数据且非交易时间，返回空数据
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ day, history: {}, indicators: {}, minute: {}, correlations: [], watch: names, variant, data_incomplete: true, missing: missingNames, reason: 'market_closed', source: 'etf_proxy' }));
      return true;
    }
    const history = {};
    const minute = {};
    const fetchOne = async (name) => {
      const code = proxyMap[name] || null;
      if (!code) return;
      const res = await fetchTencentDaily(code, days);
      const arr = (res?.data || []).map(r => ({
        date: r.date,
        open: r.open,
        high: r.high,
        low: r.low,
        close: r.close,
        pct: r.pct,
        amount: r.amount,
        volume: r.volume,
        turnover: r.turnover
      }));
      history[name] = arr;

      // ETF分时数据获取
      const cleanCode = code.replace(/sh|sz|SH|SZ/g, '');
      const isETF = /^\d{6}$/.test(cleanCode) && ['5', '1'].includes(cleanCode[0]);
      let m;
      if (isETF) {
        // ETF分时数据
        try {
          const pyResult = await new Promise((resolve) => {
            execFile('python3', ['fetch_sector_data.py', 'etf-minute', code], { timeout: 30000 }, (err, stdout, stderr) => {
              if (err) {
                console.error(`ETF minute error for ${code}:`, err, stderr);
                resolve({ data: [], prevClose: null });
              } else {
                try {
                  const parsed = JSON.parse(stdout);
                  resolve(parsed);
                } catch (e) {
                  console.error(`ETF minute parse error for ${code}:`, e);
                  resolve({ data: [], prevClose: null });
                }
              }
            });
          });
          // 转换数据格式
          m = {
            data: (pyResult.data || []).map(item => ({
              time: item.time,
              close: item.price,
              price: item.price
            })),
            prevClose: pyResult.prevClose ?? null
          };
        } catch (e) {
          console.error(`ETF minute fetch failed for ${code}:`, e);
          m = { data: [], prevClose: null };
        }
      } else {
        // 板块分时数据
        m = await fetchAshareMinute(code);
      }
      minute[name] = { series: m?.data || [], prevClose: m?.prevClose ?? null };
    };
    try {
      for (const n of names) { await fetchOne(n); }
      const normalized = normalizeHistoryPayloadToDay({ day, history, indicators: {}, minute, correlations: [], watch: names, variant, data_incomplete: missingNames.length > 0, missing: missingNames, source: 'etf_proxy' }, day);
      const payload = JSON.stringify(normalized);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(payload);
      if (payload && isJsonText(payload)) writeJsonCache(cacheFile, payload);
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'proxy_history_failed' }));
    }
    return true;
  }

  if (url.pathname === '/api/sector/rotation_proxy') {
    const sectorsParam = url.searchParams.get('sectors');
    const daysParam = url.searchParams.get('days');
    const force = url.searchParams.get('force') === '1';
    const days = Number.isFinite(Number(daysParam)) ? Math.max(30, Number(daysParam)) : 90;
    const list = sectorsParam && sectorsParam.trim() ? sectorsParam.trim() : readWatchList().join(',');
    const names = list.split(',').map(s => s.trim()).filter(Boolean);
    const day = latestTradingDay();
    const cacheFile = sectorCacheFile('sector-rotation-proxy', day, list, days);
    const cfg = readSectorProxyConfig();
    const variant = cfg.force_etf ? 'etf' : (cfg.default_variant || 'etf');
    const proxyMap = (cfg.variants && (cfg.variants[variant] || {})) || {};
    const missingNames = names.filter(n => !proxyMap[n]);
    const allowFetch = force || isMarketOpenNow();
    if (!allowFetch) {
      const cached = readJsonCache(cacheFile);
      if (cached) {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(cached);
        return true;
      }
      const latestCached = findLatestCacheFileOnOrBefore('sector-rotation-proxy', day);
      if (latestCached) {
        const txt = readJsonCache(latestCached);
        if (txt) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(txt);
          return true;
        }
      }
      const fallbackFile = findLatestCacheFileOnOrBefore('sector-rotation', day);
      if (fallbackFile) {
        const txt = readJsonCache(fallbackFile);
        if (txt && isJsonText(txt)) {
          try {
            const obj = JSON.parse(txt);
            obj.variant = variant;
            obj.data_incomplete = true;
            obj.missing = missingNames;
            obj.source = 'fallback_index';
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify(obj));
            return true;
          } catch (e) {
            void e;
          }
        }
      }
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ day, mainline: [], groups: {}, reason: 'market_closed', data_incomplete: true, variant, missing: missingNames, source: 'etf_proxy' }));
      return true;
    }
    const seriesMap = {};
    const fetchOne = async (name) => {
      const code = proxyMap[name] || null;
      if (!code) return;
      const res = await fetchTencentDaily(code, days);
      seriesMap[name] = res?.data || [];
    };
    const pctChange = (arr, k) => {
      if (!Array.isArray(arr) || arr.length <= k) return null;
      const a = Number(arr[arr.length - 1]?.close);
      const b = Number(arr[arr.length - 1 - k]?.close);
      if (!Number.isFinite(a) || !Number.isFinite(b) || b === 0) return null;
      return +(((a - b) / b) * 100).toFixed(2);
    };
    const avg = (xs) => {
      const arr = xs.filter((n) => Number.isFinite(Number(n))).map(Number);
      if (!arr.length) return null;
      const s = arr.reduce((p, c) => p + c, 0);
      return +(s / arr.length).toFixed(2);
    };
    const volChange = (arr) => {
      if (!Array.isArray(arr) || arr.length < 21) return null;
      const last5 = arr.slice(-5).map(r => Number(r.volume));
      const last20 = arr.slice(-20, -5).map(r => Number(r.volume));
      const a = avg(last5);
      const b = avg(last20);
      if (!Number.isFinite(a) || !Number.isFinite(b) || b === 0) return null;
      return +(((a - b) / b) * 100).toFixed(2);
    };
    const momentumTag = (c5, c20) => {
      const a = Number(c5), b = Number(c20);
      if (Number.isFinite(a) && Number.isFinite(b)) {
        if (a >= 2 && b >= 4) return '强势向上';
        if (a >= 1 && b >= 2) return '偏强向上';
        if (a <= -1 && b <= -2) return '向下';
        return '中性震荡';
      }
      return '中性震荡';
    };
    const behaviorTag = (v) => {
      const x = Number(v);
      if (!Number.isFinite(x)) return '横盘整理';
      if (x >= 10) return '放量启动';
      if (x <= -10) return '缩量回落';
      return '趋势延续';
    };
    try {
      for (const n of names) { await fetchOne(n); }
      const items = [];
      let latest = null;
      names.forEach((name) => {
        const arr = seriesMap[name] || [];
        if (!arr.length) return;
        const lastDate = arr[arr.length - 1]?.date;
        if (lastDate && (!latest || lastDate > latest)) latest = lastDate;
        const c5 = pctChange(arr, 5);
        const c20 = pctChange(arr, 20);
        const vchg = volChange(arr);
        const score = (Number(c5) || 0) * 1.5 + (Number(c20) || 0) * 1.0 + (Number(vchg) || 0) * 0.1;
        const momentum = momentumTag(c5, c20);
        const behavior = behaviorTag(vchg);
        let advice = '观望';
        if (momentum === '强势向上') advice = '建仓';
        else if (momentum === '偏强向上') advice = '持有';
        else if (momentum === '向下') advice = '减仓';
        items.push({
          "板块名称": name,
          "动能": momentum,
          "资金行为": behavior,
          "操作建议": advice,
          "指标数据": { "alpha_5": c5, "alpha_20": c20, "Amount_Share_Change": null },
          "_score": +score.toFixed(3)
        });
      });
      const ranked = items.slice().sort((a, b) => (Number(b?._score) || 0) - (Number(a?._score) || 0));
      const mainline = ranked.slice(0, 3).map((it) => {
        const ind = it["指标数据"] || {};
        return {
          "板块名称": it["板块名称"],
          "动能": it["动能"],
          "资金行为": it["资金行为"],
          "操作建议": it["操作建议"],
          "Alpha_5": ind.alpha_5,
          "Alpha_20": ind.alpha_20
        };
      });
      const profile = readSectorProfile();
      const groups = profile.groups || {};
      const grpScores = {};
      Object.keys(groups).forEach((n) => {
        const g = groups[n];
        const it = items.find(x => x["板块名称"] === n);
        if (!it) return;
        const v = Number(it?._score) || 0;
        grpScores[g] = (grpScores[g] || 0) + v;
      });
      const resVsTech = (grpScores['资源'] || 0) - ((grpScores['硬件'] || 0) + (grpScores['软件'] || 0));
      const seesaw = resVsTech > 0.6 ? '资源强' : (resVsTech < -0.6 ? '科技强' : '平衡');
      const diffusion = (grpScores['硬件'] || 0) - (grpScores['软件'] || 0);
      const diffusionTag = diffusion > 0.5 ? '硬件领先' : (diffusion < -0.5 ? '软件补涨' : '同步');
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      const payload = JSON.stringify({
        day: latest || latestTradingDay(),
        rotation: { leader: mainline[0]?.['板块名称'] || '-', seesaw, diffusion: diffusionTag, resonance: false, resonance_reason: '' },
        mainline,
        variant,
        watch: names,
        data_incomplete: missingNames.length > 0,
        missing: missingNames,
        source: 'etf_proxy'
      });
      res.end(payload);
      if (payload && isJsonText(payload)) writeJsonCache(cacheFile, payload);
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'rotation_proxy_failed' }));
    }
    return true;
  }

  if (url.pathname === '/api/sector/rotation/intraday') {
    const view = (url.searchParams.get('view') || '').trim() === 'detail' ? 'detail' : 'summary';
    const sectorsParam = url.searchParams.get('sectors');
    const daysParam = url.searchParams.get('days');
    const days = Number.isFinite(Number(daysParam)) ? Math.max(1, Number(daysParam)) : 20;
    const list = sectorsParam && sectorsParam.trim() ? sectorsParam.trim() : readWatchList().join(',');
    const day = latestTradingDay();
    const marketOpen = isMarketOpenNow();
    const intradayFile = intradayRotationPath(day, view);
    const cachedText = readJsonCache(intradayFile);
    if (cachedText) {
      try {
        const age = now() - fs.statSync(intradayFile).mtimeMs;
        if (!marketOpen || age < INTRADAY_CACHE_TTL_MS) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(cachedText);
          return true;
        }
      } catch (e) {
        void e;
      }
    }
    const profile = readSectorProfile();
    const groups = profile.groups || {};
    if (!marketOpen && lastIntradayRotation.payload && lastIntradayRotation.day === day) {
      const bars = lastIntradayRotation.payload?.bars || [];
      if (Array.isArray(bars) && bars.length) {
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ day, ts: lastIntradayRotation.ts, intraday: lastIntradayRotation.payload }));
      return true;
      }
    }
    try {
      const historyCache = sectorCacheFile('sector-history', day, list, days);
      const lifecycleCache = sectorCacheFile('sector-lifecycle', day, list, Math.max(20, days));
      let hist = null;
      let life = null;
      const cachedHistory = readJsonCache(historyCache);
      if (cachedHistory) {
        try { hist = JSON.parse(cachedHistory); } catch (e) { hist = null; }
      }
      if (!hist) {
        const alt = findLatestSectorHistoryCache(day);
        if (alt) {
          try { hist = JSON.parse(alt); } catch (e) { hist = null; }
        }
      }
      const cachedLifecycle = readJsonCache(lifecycleCache);
      if (cachedLifecycle) {
        try { life = JSON.parse(cachedLifecycle); } catch (e) { life = null; }
      }
      const cfg = readSectorProxyConfig();
      const variant = cfg.force_etf ? 'etf' : (cfg.default_variant || 'etf');
      const proxyMap = (cfg.variants && cfg.variants[variant]) || {};
      if (!hist || !hist.minute || !Object.keys(hist.minute || {}).length) {
        const minute = {};
        const names = list.split(',').map(s => s.trim()).filter(Boolean);
        if (marketOpen) {
          for (const n of names) {
            const code = proxyMap[n] || null;
            if (!code) continue;
            const m = await fetchAshareMinute(code);
            minute[n] = { series: m?.data || [], prevClose: m?.prevClose ?? null };
          }
        }
        if (!hist) hist = {};
        hist.minute = minute;
        hist.watch = names;
      }
      if (!hist) {
        hist = await execPythonJson(['fetch_sector_data.py', 'history_dynamic', list, String(days)], 90000);
        if (hist) writeJsonCache(historyCache, JSON.stringify(hist));
      }
      if (!life) {
        life = await execPythonJson(['fetch_sector_data.py', 'lifecycle_dynamic', list, String(Math.max(20, days))], 90000);
        if (life) writeJsonCache(lifecycleCache, JSON.stringify(life));
      }
      const payload = buildIntradayBars(hist || {}, life || {}, groups, view);
      const leader = payload?.bars?.[0]?.group || '';
      let signal = payload.signal;
      let reason = payload.reason;
      const nowTs = now();
      if (leader && lastIntradayRotation.leader && leader !== lastIntradayRotation.leader) {
        if (nowTs - lastIntradayRotation.signalTs < INTRADAY_DEBOUNCE_MS) {
          signal = lastIntradayRotation.signal;
          reason = lastIntradayRotation.reason;
        } else {
          signal = `${leader}转强`;
          reason = payload.reason;
        }
      }
      payload.signal = signal;
      payload.reason = reason;
      lastIntradayRotation.payload = payload;
      lastIntradayRotation.ts = nowTs;
      lastIntradayRotation.day = day;
      lastIntradayRotation.leader = leader;
      lastIntradayRotation.signal = signal;
      lastIntradayRotation.reason = reason;
      lastIntradayRotation.signalTs = nowTs;
      const response = { day, ts: lastIntradayRotation.ts, intraday: payload };
      const responseText = JSON.stringify(response);
      writeJsonCache(intradayFile, responseText);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(responseText);
    } catch (e) {
      if (cachedText) {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(cachedText);
        return true;
      }
      const fallback = lastIntradayRotation.payload ? { day: lastIntradayRotation.day || day, ts: lastIntradayRotation.ts || now(), intraday: lastIntradayRotation.payload } : { day, ts: now(), intraday: { bars: [], signal: '数据缺失', reason: [] } };
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify(fallback));
    }
    return true;
  }

  if (url.pathname === '/api/sector/rotation/sequence') {
    const rt = url.searchParams.get('rt') === '1';
    const sectorsParam = url.searchParams.get('sectors');
    const daysParam = url.searchParams.get('days');
    const days = Number.isFinite(Number(daysParam)) ? Math.max(10, Number(daysParam)) : 60;
    const list = sectorsParam && sectorsParam.trim() ? sectorsParam.trim() : readWatchList().join(',');
    const day = latestTradingDay();
    if (!rt) {
      const cached = readRotationSequence(day);
      if (cached) {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(cached);
        return true;
      }
      const latest = readLatestRotationSequence();
      if (latest) {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(latest);
        return true;
      }
    }
    const file = rotationSequencePath(day);
    const payload = await execPythonJson(['fetch_sector_data.py', 'rotation_sequence', list, String(days)], 90000);
    if (payload) {
      const txt = JSON.stringify(payload);
      writeJsonCache(file, txt);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(txt);
      return true;
    }
    const latest = readLatestRotationSequence();
    if (latest) {
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(latest);
      return true;
    }
    res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'sequence_failed' }));
    return true;
  }
  if (url.pathname === '/api/sector/lifecycle_proxy') {
    url.pathname = '/api/sector/lifecycle';
  }
  if (url.pathname === '/api/sector/lifecycle') {
    const realtime = url.searchParams.get('rt') === '1';
    const sectorsParam = url.searchParams.get('sectors');
    const daysParam = url.searchParams.get('days');
    const force = url.searchParams.get('force') === '1';
    const days = Number.isFinite(Number(daysParam)) ? Math.max(1, Number(daysParam)) : 60;
    const list = sectorsParam && sectorsParam.trim() ? sectorsParam.trim() : readWatchList().join(',');
    const day = latestTradingDay();
    const cacheFile = !realtime ? sectorCacheFile('sector-lifecycle', day, list, days) : null;
    if (cacheFile) {
      const cached = readJsonCache(cacheFile);
      if (cached && isJsonText(cached)) {
        const obj = JSON.parse(cached);
        const dataDay = obj.day || '';

        // 盘后模式：交易时间内允许返回上一交易日数据
        const isMarketOpen = isMarketOpenNow();
        const parts = getBeijingParts();
        const minutes = parts && parts.minutes ? parts.minutes : 0;
        const isAfterWarmup = minutes >= 930; // 15:30之后

        let validationPassed = true;
        let expectedDay = null;

        if (isMarketOpen || !isAfterWarmup) {
          // 盘后模式：使用warmup的日期验证
          const warmupPath = path.join(__dirname, 'data', 'sector-history-warmup-60.json');
          if (fs.existsSync(warmupPath)) {
            try {
              const warmupData = JSON.parse(fs.readFileSync(warmupPath, 'utf-8'));
              expectedDay = warmupData.day || null;
              if (expectedDay && dataDay !== expectedDay) {
                console.warn(`[lifecycle] 缓存验证失败: 数据=${dataDay}, warmup=${expectedDay}`);
                validationPassed = false;
              }
            } catch (e) {
              // 忽略验证错误
            }
          }
        } else {
          // 非交易时间且15:30后：使用常规验证
          const today = latestTradingDay();
          if (dataDay !== today) {
            validationPassed = false;
            expectedDay = today;
          }
        }

        if (!validationPassed) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ day: expectedDay || dataDay, items: [], data_incomplete: true, reason: 'trading_day_mismatch' }));
          return true;
        }
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(cached);
        return true;
      }
    }
    const useDynamic = list && list.trim();
    const cfg = readSectorProxyConfig();
    const forceEnv = cfg.force_etf ? '1' : '0';
    const args = ['fetch_sector_data.py', useDynamic ? 'lifecycle_dynamic' : 'lifecycle'];
    if (useDynamic) {
      args.push(list);
      args.push(String(days));
    } else {
      args.push(String(days));
    }
    const allowFetch = force || isMarketOpenNow();
    if (!allowFetch) {
      if (!realtime) {
        const latestFile = findLatestCacheFileOnOrBefore('sector-lifecycle', null);
        if (latestFile) {
          const txt = readJsonCache(latestFile);
          if (txt && isJsonText(txt)) {
            const obj = JSON.parse(txt);
            const dataDay = obj.day || '';
            const today = latestTradingDay();
            if (dataDay === today) {
              res.setHeader('Content-Type', 'application/json; charset=utf-8');
              res.end(txt);
              return true;
            }
          }
        }
      }
      const opts = { ...getExecOptions(), env: { ...getExecOptions().env || process.env, CACHE_ONLY: '1', FORCE_SECTOR_ETF: forceEnv } };
      execFile('python3', args, opts, (err, stdout) => {
        const out = (stdout || '').trim();
        if (!err && out && isJsonText(out)) {
          const obj = JSON.parse(out);
          const dataDay = obj.day || '';
          const today = latestTradingDay();
          if (dataDay !== today) {
            console.warn(`交易日验证失败(CACHE_ONLY): 数据=${dataDay}, 预期=${today}`);
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify({ day: today, items: [], data_incomplete: true, reason: 'trading_day_mismatch' }));
            return true;
          }
          if (cacheFile) writeJsonCache(cacheFile, JSON.stringify(obj));
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify(obj));
          return true;
        }
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ day, items: [], data_incomplete: true, reason: 'market_closed' }));
      });
      return true;
    }
    const opts = { ...getExecOptions(), env: { ...getExecOptions().env || process.env, FORCE_SECTOR_ETF: forceEnv } };
    execFile('python3', args, opts, (err, stdout) => {
      if (err) {
        console.error(err);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: "Failed to fetch sector lifecycle" }));
        return true;
      }
      const out = (stdout || '').trim();
      if (out && isJsonText(out)) {
        const obj = JSON.parse(out);
        const dataDay = obj.day || '';

        // 盘后模式：交易时间内允许返回上一交易日数据
        // warmup在15:30更新，更新前都应显示上一交易日数据
        const isMarketOpen = isMarketOpenNow();
        const parts = getBeijingParts();
        const minutes = parts && parts.minutes ? parts.minutes : 0;
        const isAfterWarmup = minutes >= 930; // 15:30之后

        let validationPassed = true;
        let expectedDay = null;

        if (isMarketOpen || !isAfterWarmup) {
          // 盘后模式：使用warmup的日期验证
          const warmupPath = path.join(__dirname, 'data', 'sector-history-warmup-60.json');
          if (fs.existsSync(warmupPath)) {
            try {
              const warmupData = JSON.parse(fs.readFileSync(warmupPath, 'utf-8'));
              expectedDay = warmupData.day || null;
              if (expectedDay && dataDay !== expectedDay) {
                console.warn(`[lifecycle] 交易日验证: 数据=${dataDay}, warmup=${expectedDay}`);
                validationPassed = false;
              }
            } catch (e) {
              console.error(`[lifecycle] warmup读取失败: ${e.message}`);
            }
          }
        } else {
          // 非交易时间且15:30后：使用常规验证
          const today = latestTradingDay();
          if (dataDay !== today) {
            console.warn(`交易日验证失败: 数据=${dataDay}, 预期=${today}`);
            validationPassed = false;
            expectedDay = today;
          }
        }

        if (!validationPassed) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ day: expectedDay || dataDay, items: [], data_incomplete: true, reason: 'trading_day_mismatch' }));
          return true;
        }
        // 按评分排序并添加Top排名
        if (Array.isArray(obj.items)) {
          obj.items.sort((a, b) => (b._score || 0) - (a._score || 0));
          obj.items.forEach((item, idx) => {
            item._rank = idx + 1;
          });
        }
        if (cacheFile) writeJsonCache(cacheFile, JSON.stringify(obj));
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify(obj));
      } else {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end('{}');
      }
    });
    return true;
  }

  if (url.pathname === '/api/sector/lifecycle/frontend') {
    const today = new Date().toISOString().split('T')[0].replace(/-/g, '');
    const frontendFile = path.join(__dirname, 'logs', `operation_frontend_${today}.json`);

    // 尝试读取今天的文件
    if (fs.existsSync(frontendFile)) {
      const data = fs.readFileSync(frontendFile, 'utf-8');
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(data);
      return true;
    }

    // 如果今天的文件不存在，查找最新的文件
    const logsDir = path.join(__dirname, 'logs');
    if (fs.existsSync(logsDir)) {
      const files = fs.readdirSync(logsDir)
        .filter(f => f.startsWith('operation_frontend_') && f.endsWith('.json'))
        .sort()
        .reverse();

      if (files.length > 0) {
        const latestFile = path.join(logsDir, files[0]);
        const data = fs.readFileSync(latestFile, 'utf-8');
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(data);
        return true;
      }
    }

    // 如果没有任何文件，返回空结果
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ date: today, items: [] }));
    return true;
  }

  if (url.pathname === '/api/sector/rotation') {
    const realtime = url.searchParams.get('rt') === '1';
    const sectorsParam = url.searchParams.get('sectors');
    const daysParam = url.searchParams.get('days');
    const days = Number.isFinite(Number(daysParam)) ? Math.max(1, Number(daysParam)) : 90;
    const list = sectorsParam && sectorsParam.trim() ? sectorsParam.trim() : readWatchList().join(',');
    const day = latestTradingDay();
    if (!realtime) {
      const snap = readRotationSnapshot(day);
      if (snap) {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(snap);
        return true;
      }
      const latestFile = findLatestRotationSnapshot();
      if (latestFile) {
        const txt = fs.readFileSync(latestFile, 'utf-8').trim();
        if (txt) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(txt);
          return true;
        }
      }
    }
    const cacheFile = !realtime ? sectorCacheFile('sector-rotation', day, list, days) : null;
    if (cacheFile) {
      const cached = readJsonCache(cacheFile);
      if (cached) {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(cached);
        return true;
      }
    }
    const useDynamic = list && list.trim();
    const args = ['fetch_sector_data.py', useDynamic ? 'rotation_dynamic' : 'rotation'];
    if (useDynamic) {
      args.push(list);
      args.push(String(days));
    } else {
      args.push(String(days));
    }
    if (!isMarketOpenNow()) {
      const opts = { ...getExecOptions(), env: { ...getExecOptions().env || process.env, CACHE_ONLY: '1' } };
      execFile('python3', args, opts, (err, stdout) => {
        const out = (stdout || '').trim();
        if (!err && out && isJsonText(out)) {
          if (cacheFile) writeJsonCache(cacheFile, out);
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(out);
          return true;
        }
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ day, mainline: [], groups: {}, data_incomplete: true, reason: 'market_closed' }));
      });
      return true;
    }
    execFile('python3', args, getExecOptions(), (err, stdout) => {
      if (err) {
        console.error(err);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: "Failed to fetch sector rotation" }));
        return true;
      }
      const out = (stdout || '').trim();
      if (cacheFile && out && isJsonText(out)) writeJsonCache(cacheFile, out);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(out || '{}');
    });
    return true;
  }

  if (url.pathname === '/api/sector/profile') {
    if (req.method === 'POST') {
      try {
        const raw = await readBody(req);
        const body = raw ? JSON.parse(raw) : {};
        const groups = body?.groups || {};
        const customGroups = body?.custom_groups || [];
        const etfBindings = body?.etf_bindings || {};
        // 保存配置
        const payload = writeSectorProfile(groups, customGroups, etfBindings);
        // 同步 ETF 绑定到 sector-proxy.json
        updateSectorProxyEtfBindings(etfBindings);
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify(payload));
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ error: 'bad request' }));
      }
      return true;
    }
    const payload = readSectorProfile();
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify(payload));
    return true;
  }

  // ETF 代码验证接口
  if (url.pathname === '/api/sector/verify-etf') {
    const code = url.searchParams.get('code');
    if (!code) {
      res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'missing code parameter' }));
      return true;
    }
    // 格式验证
    if (!/^(sh|sz)\d{6}$/.test(code)) {
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ valid: false, code, error: '格式错误，应为 sh/sz + 6位数字' }));
      return true;
    }
    // 调用 Python 验证数据可用性
    const { execFile } = require('child_process');
    const pyCode = `
import sys
import json
try:
    import akshare as ak
    code = sys.argv[1]
    clean_code = code.replace('sh', '').replace('sz', '')
    df = ak.fund_etf_hist_em(symbol=clean_code, period="daily", start_date="20240101", end_date="21231231", adjust="qfq")
    if df is None or df.empty:
        print(json.dumps({"valid": False, "error": "无数据"}))
    else:
        count = len(df)
        start_date = str(df.iloc[0]['日期']) if '日期' in df.columns else str(df.index[0])
        print(json.dumps({"valid": True, "count": count, "start_date": start_date, "warning": ("数据不足300天" if count < 300 else None)}))
except Exception as e:
    print(json.dumps({"valid": False, "error": str(e)}))
`;
    execFile('python3', ['-c', pyCode, code], { timeout: 30000 }, (err, stdout, stderr) => {
      if (err) {
        console.error('ETF验证执行失败:', err, stderr);
      }
      let result = { valid: false, code, error: '验证失败' };
      try {
        if (stdout) {
          const parsed = JSON.parse(stdout.trim());
          result = { valid: parsed.valid, code, count: parsed.count, start_date: parsed.start_date, warning: parsed.warning, error: parsed.error };
        } else if (stderr) {
          result.error = '执行错误: ' + stderr.substring(0, 100);
        }
      } catch (e) {
        result.error = '解析失败: ' + (stdout || stderr || e.message).substring(0, 100);
      }
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify(result));
    });
    return true;
  }

  if (url.pathname === '/api/sector/watch-list') {
    if (req.method === 'POST') {
      try {
        const raw = await readBody(req);
        const body = raw ? JSON.parse(raw) : {};
        const list = writeWatchList(body?.watch_list || body?.list || body?.sectors || []);
        execFile('python3', ['fetch_sector_data.py', 'history_dynamic', list.join(','), '20'], () => {});
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ watch_list: list }));
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ error: 'bad request' }));
      }
      return true;
    }
    const list = readWatchList();
    execFile('python3', ['fetch_sector_data.py', 'history_dynamic', list.join(','), '20'], () => {});
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ watch_list: list }));
    return true;
  }

  if (url.pathname === '/api/market/breadth') {
    const day = latestTradingDay();

    // ⭐ 优先读取 breadth-cache.json（由 market_snapshot_sina.py 更新）
    const breadthCache = readBreadthCache();
    if (breadthCache && isNum(breadthCache.up) && isNum(breadthCache.down)) {
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, data: { ...breadthCache, day } }));
      return true;
    }

    // 备选方案：从 archive 数据读取
    const snap = readLatestArchivePayload();
    const snapUp = Number(snap?.sentiment?.upCount);
    const snapDown = Number(snap?.sentiment?.downCount);
    if (isNum(snapUp) && isNum(snapDown) && (snap?.day || day) === day) {
      const total = Number(snapUp || 0) + Number(snapDown || 0);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, data: { up: snapUp, down: snapDown, flat: 0, total, day } }));
      return true;
    }
    if (isMarketOpenNow()) {
      const rt = await fetchBreadthRealtime();
      if (rt && isNum(rt.up) && isNum(rt.down)) {
        const total = Number(rt.total || (rt.up + rt.down + (rt.flat || 0)) || 0);
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: true, data: { up: rt.up, down: rt.down, flat: rt.flat || 0, total, day } }));
        return true;
      }
    }
    const cacheFile = cacheJsonPath('market-breadth', day);
    const cached = readJsonCache(cacheFile);
    if (cached) {
      try {
        const obj = JSON.parse(cached);
        if (isNum(obj?.up) && isNum(obj?.down)) {
          if (!obj.day && !obj.date) obj.day = day;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: true, data: obj }));
          return true;
        }
      } catch (e) {
        console.error(e);
      }
    }
    execFile('python3', ['fetch_sector_data.py', 'breadth'], { ...getExecOptions(), timeout: 20000 }, (err, stdout) => {
      if (!err) {
        const out = (stdout || '').trim();
        if (out && isJsonText(out)) {
          const obj = JSON.parse(out);
          if (isNum(obj?.up) && isNum(obj?.down)) {
            obj.day = day;
            if (!isNum(obj.total)) obj.total = Number(obj.up || 0) + Number(obj.down || 0) + Number(obj.flat || 0);
            const payload = JSON.stringify(obj);
            writeJsonCache(cacheFile, payload);
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify({ ok: true, data: obj }));
            return true;
          }
        }
      } else {
        console.error(err);
      }
      const row = loadLatestBreadthRecord() || loadBreadthFromArchive(day);
      const sourceDay = (row && (row.day || row.date)) ? String(row.day || row.date) : null;
      const up = Number(row?.up || 0);
      const down = Number(row?.down || 0);
      const flat = Number(row?.flat || 0);
      const total = Number(row?.total || (up + down + flat) || 0);
      const obj = { up, down, flat, total, day, source_day: sourceDay, stale: !!(sourceDay && sourceDay !== day) };
      writeJsonCache(cacheFile, JSON.stringify(obj));
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, data: obj }));
    });
    return true;
  }

  if (url.pathname === '/api/signals') {
    const signals = buildSignalsFromBacktest();
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({
      generated_at: new Date().toISOString(),
      source: 'data/backtest_false_kill.json',
      count: signals.length,
      signals
    }));
    return true;
  }

  if (url.pathname === '/api/panic') {
    const day = latestTradingDay();
    let row = null;
    const snap = readLatestArchivePayload();
    const snapUp = Number(snap?.sentiment?.upCount);
    const snapDown = Number(snap?.sentiment?.downCount);
    if (isNum(snapUp) && isNum(snapDown) && (snap?.day || day) === day) {
      row = { up: snapUp, down: snapDown, total: snapUp + snapDown, day: snap?.day || day };
    } else if (isMarketOpenNow()) {
      row = await fetchBreadthRealtime();
      if (row && !row.day) row.day = day;
    }
    if (!row) {
      row = loadLatestBreadthRecord() || loadBreadthFromArchive(day);
    }
    const up = Number(row?.up || 0);
    const down = Number(row?.down || 0);
    const total = Number(row?.total || 0);
    const ratio = total > 0 ? down / total : 0;
    const isPanic = ratio > 0.65;
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({
      ratio,
      is_panic: isPanic,
      up,
      down,
      total
    }));
    return true;
  }

    return false; // No route matched
  };
  return handleRoute;
};
