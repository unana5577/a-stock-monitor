const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 8782;
const API_BASE = 'http://127.0.0.1:8787';
const DEBUG_DIR = path.join(__dirname, '..', '..', 'online_debug_data', '0615');
const REAL_DATA_DIR = path.join(__dirname, '..', '..', 'data');
const USE_DEBUG = fs.existsSync(DEBUG_DIR);

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
};

function serveJson(res, obj) {
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(obj));
}

function readJsonlLines(filePath) {
  if (!fs.existsSync(filePath)) return [];
  const raw = fs.readFileSync(filePath, 'utf-8').trim();
  if (!raw) return [];
  return raw.split('\n').filter(Boolean).map(line => JSON.parse(line));
}

function serveDebugMinute(req, res) {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  const symbol = url.searchParams.get('symbol');
  if (!symbol) return false;

  const candidateDirs = [path.join(REAL_DATA_DIR, 'etf', 'minute', symbol)];
  if (USE_DEBUG) candidateDirs.push(path.join(DEBUG_DIR, 'etf', 'minute', symbol));

  for (const dir of candidateDirs) {
    if (!fs.existsSync(dir)) continue;
    const files = fs.readdirSync(dir).filter(f => f.endsWith('.jsonl')).sort();
    if (files.length === 0) continue;

    const latestFile = path.join(dir, files[files.length - 1]);
    const rows = readJsonlLines(latestFile);
    const preClose = rows.length > 0 ? rows[0].pre_close : null;
    const data = rows.map(r => ({
      time: r.time || r.asOf,
      price: r.price,
      pct: r.pct,
      amount: r.amount,
      vol: r.vol,
      open: r.open,
      high: r.high,
      low: r.low
    }));

    serveJson(res, { ok: true, pre_close: preClose, data, symbol });
    return true;
  }
  return false;
}

function buildDebugLifecycle() {
  const proxyCfg = JSON.parse(fs.readFileSync(require('path').join(__dirname, '..', '..', 'data', 'sector-proxy.json'), 'utf-8'));
  const etfCfg = proxyCfg.variants?.etf || {};
  const etfMeta = proxyCfg.etf_meta || {};

  const getDailyFile = (code) => {
    const realFile = path.join(REAL_DATA_DIR, 'etf', 'daily', code, 'daily.jsonl');
    if (fs.existsSync(realFile)) return realFile;
    const debugFile = path.join(DEBUG_DIR, 'etf', 'daily', code, 'daily.jsonl');
    if (fs.existsSync(debugFile)) return debugFile;
    return null;
  };

  const items = [];
  Object.entries(etfCfg).forEach(([name, code]) => {
    const dailyFile = getDailyFile(code);
    if (!dailyFile) return;
    const rows = readJsonlLines(dailyFile);
    if (rows.length < 25) return;

    const closes = rows.map(r => r.close).filter(c => c != null && isFinite(c));
    const pcts = rows.map(r => r.pct).filter(p => p != null && isFinite(p));

    let ma20sum = 0, cnt = 0;
    for (let i = closes.length - 20; i < closes.length; i++) { ma20sum += closes[i]; cnt++; }
    const ma20 = cnt > 0 ? ma20sum / cnt : closes[closes.length - 1];
    const lastClose = closes[closes.length - 1];
    const bias20 = ma20 ? +(((lastClose - ma20) / ma20) * 100).toFixed(2) : 0;

    let maxBias = bias20;
    for (let i = 19; i < closes.length; i++) {
      let s = 0, c = 0;
      for (let j = i - 19; j <= i; j++) { s += closes[j]; c++; }
      const m = c > 0 ? s / c : closes[i];
      if (!m) continue;
      const b = ((closes[i] - m) / m) * 100;
      if (b > maxBias) maxBias = b;
    }
    maxBias = +maxBias.toFixed(2);

    const recent5 = pcts.slice(-5);
    const upCount = recent5.filter(p => p > 0).length;
    let dongneng = '偏弱';
    if (upCount >= 4) dongneng = '强势向上';
    else if (upCount >= 3) dongneng = '偏强向上';
    else if (upCount >= 2) dongneng = '区间震荡';
    else dongneng = '偏弱向下';

    let advice = '持有';
    if (bias20 >= maxBias * 0.95) advice = '减仓/止盈';
    else if (bias20 <= 0 && recent5.every(p => p < 0)) advice = '观望';
    else if (dongneng.includes('向下') || dongneng === '偏弱') advice = '回避';

    const guili = `当前偏离 ${bias20 >= 0 ? '+' : ''}${bias20}%，历史极值 ${maxBias >= 0 ? '+' : ''}${maxBias}%`;
    const meta = etfMeta[name] || {};

    items.push({
      symbol: code,
      名称: name,
      操作建议: advice,
      动能: dongneng,
      乖离对比: guili,
      资金行为: upCount >= 3 ? '主力净流入' : '资金观望',
      热度占比: '—',
      归因说明: `${name}偏离20日均线${(bias20 >= 0 ? '+' : '') + bias20}%，处于历史${bias20 >= maxBias * 0.8 ? '高位' : bias20 >= 0 ? '中位' : '低位'}区间，近5日${upCount}涨${5 - upCount}跌。`,
      指标数据: { Bias_20: bias20, Bias_20_History_Max: maxBias || 1, Amount_Share_Pct: '—' },
      name: name + 'ETF',
      category: meta.category || '科技',
      sub_category: meta.sub_category || '硬件'
    });
  });

  return items;
}

function proxyApi(req, res) {
  const url = new URL(req.url, API_BASE);
  const headers = { ...req.headers };
  delete headers.host;
  const options = {
    hostname: '127.0.0.1',
    port: 8787,
    path: url.pathname + url.search,
    method: req.method,
    headers,
  };

  const proxy = http.request(options, (proxyRes) => {
    let body = '';
    proxyRes.on('data', chunk => body += chunk);
    proxyRes.on('end', () => {
      if (USE_DEBUG && url.pathname === '/api/m1/data/overview') {
        try {
          const original = JSON.parse(body);
          const warmup = original.warmup?.history || {};

          const debugEtfDir = path.join(DEBUG_DIR, 'etf', 'daily');
          if (fs.existsSync(debugEtfDir)) {
            const symbols = fs.readdirSync(debugEtfDir).filter(d => fs.statSync(path.join(debugEtfDir, d)).isDirectory());
            symbols.forEach(sym => {
              const dailyFile = path.join(debugEtfDir, sym, 'daily.jsonl');
              if (fs.existsSync(dailyFile)) {
                const rows = readJsonlLines(dailyFile);
                warmup[sym] = rows.map(r => ({ date: r.date, close: r.close, pct: r.pct, amount: r.amount }));
              }
            });
          }

          const realEtfDir = path.join(REAL_DATA_DIR, 'etf', 'daily');
          if (fs.existsSync(realEtfDir)) {
            const symbols = fs.readdirSync(realEtfDir).filter(d => fs.statSync(path.join(realEtfDir, d)).isDirectory());
            symbols.forEach(sym => {
              if (warmup[sym]) return;
              const dailyFile = path.join(realEtfDir, sym, 'daily.jsonl');
              if (fs.existsSync(dailyFile)) {
                const rows = readJsonlLines(dailyFile);
                warmup[sym] = rows.map(r => ({ date: r.date, close: r.close, pct: r.pct, amount: r.amount }));
              }
            });
          }

          const warmupFile = path.join(REAL_DATA_DIR, 'warmup', 'warmup-60.json');
          if (fs.existsSync(warmupFile)) {
            try {
              const rawWu = JSON.parse(fs.readFileSync(warmupFile, 'utf-8'));
              const wuHistory = rawWu.history || rawWu;
              Object.entries(wuHistory).forEach(([sym, rows]) => {
                if (!warmup[sym] && Array.isArray(rows) && rows.length > 0) {
                  warmup[sym] = rows.map(r => ({ date: r.date, close: r.close, pct: r.pct, amount: r.amount }));
                }
              });
            } catch (e) {}
          }

          original.warmup = { history: warmup };

          const lifecycleFile = path.join(REAL_DATA_DIR, 'lifecycle', 'lifecycle.json');
          if (fs.existsSync(lifecycleFile)) {
            const rawLc = JSON.parse(fs.readFileSync(lifecycleFile, 'utf-8'));
            const lcData = rawLc.data || rawLc;
            const origLifecycle = original.lifecycle?.data?.length ? original.lifecycle.data : [];
            const mergedLifecycle = [...origLifecycle];
            const origSyms = new Set(origLifecycle.map(i => i.symbol));
            (Array.isArray(lcData) ? lcData : []).forEach(item => {
              if (item.symbol && !origSyms.has(item.symbol)) mergedLifecycle.push(item);
            });
            original.lifecycle = { data: mergedLifecycle };
          }

          const intradayDir = path.join(REAL_DATA_DIR, 'lifecycle', 'intraday');
          const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' });
          const intradayFile = path.join(intradayDir, `etf_snapshot_${today}.jsonl`);
          if (!fs.existsSync(intradayFile)) {
            const altFile = path.join(DEBUG_DIR, 'lifecycle', 'intraday', `etf_snapshot_2026-06-15.jsonl`);
            if (fs.existsSync(altFile)) fs.copyFileSync(altFile, intradayFile);
          }
          if (fs.existsSync(intradayFile)) {
            try {
              const lines = readJsonlLines(intradayFile);
              if (lines.length > 0) {
                const lastSnap = lines[lines.length - 1];
                if (lastSnap.items) {
                  original.data = original.data || {};
                  original.data.intraday_snapshot = lastSnap;
                }
              }
            } catch (e) {}
          }

          res.writeHead(proxyRes.statusCode, { 'Content-Type': 'application/json; charset=utf-8' });
          res.end(JSON.stringify(original));
        } catch (e) {
          res.writeHead(proxyRes.statusCode, proxyRes.headers);
          res.end(body);
        }
      } else {
        res.writeHead(proxyRes.statusCode, proxyRes.headers);
        res.end(body);
      }
    });
  });

  proxy.on('error', () => {
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'api proxy unreachable' }));
  });

  if (req.method === 'POST' || req.method === 'PUT') {
    const bodyChunks = [];
    req.on('data', chunk => bodyChunks.push(chunk));
    req.on('end', () => {
      proxy.end(Buffer.concat(bodyChunks));
    });
  } else {
    req.pipe(proxy);
  }
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  const pathname = url.pathname;

  if (pathname.startsWith('/api/')) {
    if (USE_DEBUG && pathname === '/api/m1/data/minute' && serveDebugMinute(req, res)) return;
    proxyApi(req, res);
    return;
  }

  let filePath = pathname === '/' || pathname === '/etf' ? '/index.html' : pathname;
  filePath = path.join(__dirname, filePath);

  const ext = path.extname(filePath);
  const contentType = MIME[ext] || 'application/octet-stream';

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('Not Found');
      return;
    }
    res.writeHead(200, { 'Content-Type': contentType });
    res.end(data);
  });
});

server.listen(PORT, () => {
  console.log(`ETF page server on http://localhost:${PORT}${USE_DEBUG ? ' [DEBUG DATA]' : ''}`);
  if (USE_DEBUG) console.log('Debug data dir:', DEBUG_DIR);
});
