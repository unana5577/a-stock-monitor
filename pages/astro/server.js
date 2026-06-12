const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 8784;
const API_BASE = 'http://127.0.0.1:8787';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
};

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
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res);
  });

  proxy.on('error', () => {
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'api proxy unreachable' }));
  });

  req.pipe(proxy);
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  const pathname = url.pathname;

  if (pathname.startsWith('/api/')) {
    proxyApi(req, res);
    return;
  }

  let filePath = pathname === '/' || pathname === '/astro' ? '/index.html' : pathname;
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
  console.log(`Astro page server on http://localhost:${PORT}`);
});
