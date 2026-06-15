const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 8780;
const FRAME_PORT_BASE = parseInt(process.env.FRAME_PORT_BASE || '0', 10);

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
    if (FRAME_PORT_BASE > 0 && filePath.endsWith('.html')) {
      body = body.replace(/8781/g, String(FRAME_PORT_BASE));
      body = body.replace(/8782/g, String(FRAME_PORT_BASE + 1));
      body = body.replace(/8783/g, String(FRAME_PORT_BASE + 2));
      body = body.replace(/8784/g, String(FRAME_PORT_BASE + 3));
    }
    res.writeHead(200, { 'Content-Type': contentType });
    res.end(body);
  });
});

server.listen(PORT, () => {
  console.log(`Shell page on http://localhost:${PORT}`);
});
