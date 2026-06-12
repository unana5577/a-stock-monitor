const http = require('http');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');
const crypto = require('crypto');

const ctx = require('./context');

const routes = [
  require('./api/shared')(),
  require('./api/overview')(),
  require('./api/astro')(),
  require('./api/etf')(),
  require('./api/trade')(),
];

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  res.setHeader('Access-Control-Max-Age', '86400');
  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // 1. Route dispatch — stop if response already ended
  for (const handle of routes) {
    if (res.writableEnded) break;
    try {
      await handle(req, res);
    } catch (e) {
      console.error('Route error:', e.message);
    }
  }
  if (res.writableEnded) return;

  // 2. Static file serving
  const pathname = url.pathname || '/';
  const mappedPath =
    pathname === '/' ? '/index.html'
      : (pathname === '/m1' || pathname === '/m1/') ? '/index_m1.html'
      : pathname;
  let filePath = path.join(__dirname, '..', 'public', mappedPath);
  const ext = path.extname(filePath);

  if (!fs.existsSync(filePath)) {
    res.writeHead(404);
    res.end('Not Found');
    return;
  }

  const contentTypeMap = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.woff2': 'font/woff2',
  };
  res.setHeader('Content-Type', contentTypeMap[ext] || 'application/octet-stream');
  fs.createReadStream(filePath).pipe(res);
});

server.listen(ctx.PORT, () => {
  console.log(`proxy server on http://localhost:${ctx.PORT} [Ashare+Tencent]`);
});
