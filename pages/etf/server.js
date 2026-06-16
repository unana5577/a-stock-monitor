const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 8782;
const API_BASE = process.env.API_TARGET || 'http://127.0.0.1:8787';
const API_URL = new URL(API_BASE);
const API_HOST = API_URL.hostname;
const API_PORT = parseInt(API_URL.port, 10) || 8787;
const REAL_DATA_DIR = path.join(__dirname, '..', '..', 'data');
const USE_DEBUG = true;

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

  const dir = path.join(REAL_DATA_DIR, 'etf', 'minute', symbol);
  if (!fs.existsSync(dir)) return false;

  const files = fs.readdirSync(dir).filter(f => f.endsWith('.jsonl')).sort();
  if (files.length === 0) return false;

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

function proxyApi(req, res) {
  const url = new URL(req.url, API_BASE);
  const headers = { ...req.headers };
  delete headers.host;
  const options = {
    hostname: API_HOST,
    port: API_PORT,
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

          const realEtfDir = path.join(REAL_DATA_DIR, 'etf', 'daily');
          if (fs.existsSync(realEtfDir)) {
            const symbols = fs.readdirSync(realEtfDir).filter(d => fs.statSync(path.join(realEtfDir, d)).isDirectory());
            symbols.forEach(sym => {
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
  console.log(`ETF page server on http://localhost:${PORT}`);
});
