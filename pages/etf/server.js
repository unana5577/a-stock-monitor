const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 8782;
const API_BASE = 'http://127.0.0.1:8787';
const DEBUG_DIR = path.join(__dirname, '..', '..', 'online_debug_data');
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

  const dir = path.join(DEBUG_DIR, 'etf', 'minute', symbol);
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
          const etfDir = path.join(DEBUG_DIR, 'etf', 'daily');
          if (fs.existsSync(etfDir)) {
            const warmup = original.warmup?.history || {};
            const symbols = fs.readdirSync(etfDir).filter(d => fs.statSync(path.join(etfDir, d)).isDirectory());
            symbols.forEach(sym => {
              const dailyFile = path.join(etfDir, sym, 'daily.jsonl');
              if (fs.existsSync(dailyFile)) {
                const rows = readJsonlLines(dailyFile);
                warmup[sym] = rows.map(r => ({ date: r.date, close: r.close, pct: r.pct, amount: r.amount }));
              }
            });
            original.warmup = { history: warmup };
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
