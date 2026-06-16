const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 8780;
const FRAME_PORT_BASE = parseInt(process.env.FRAME_PORT_BASE || '8781', 10);

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
};

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  let filePath = url.pathname === '/' ? '/index.html' : url.pathname;
  filePath = path.join(__dirname, filePath);

  const ext = path.extname(filePath);
  const contentType = MIME[ext] || 'application/octet-stream';

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('Not Found');
      return;
    }
    let body = data.toString('utf8');
    if (filePath.endsWith('.html')) {
      body = body.replace('</head>', `<script>window.__FRAME_BASE=${FRAME_PORT_BASE}</script></head>`);
    }
    res.writeHead(200, { 'Content-Type': contentType });
    res.end(body);
  });
});

server.listen(PORT, () => {
  console.log(`Shell page on http://localhost:${PORT} (frame_base=${FRAME_PORT_BASE})`);
});
