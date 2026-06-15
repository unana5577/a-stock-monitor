const path = require('path');
const { execFile } = require('child_process');
const fs = require('fs');
const os = require('os');

module.exports = function() {
  const handleRoute = async function(req, res) {
    const url = new URL(req.url, `http://${req.headers.host}`);

    // POST /api/trade/ocr-positions — 截屏OCR提取持仓
    if (url.pathname === '/api/trade/ocr-positions' && req.method === 'POST') {
      try {
        const chunks = [];
        req.on('data', (c) => chunks.push(c));
        req.on('end', () => {
          const body = Buffer.concat(chunks).toString();
          let json;
          try { json = JSON.parse(body); } catch (e) {
            res.statusCode = 400;
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify({ ok: false, error: 'invalid json' }));
            return;
          }

          const imageData = json.image || '';
          if (!imageData || !imageData.startsWith('data:image/')) {
            res.statusCode = 400;
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify({ ok: false, error: 'missing image data' }));
            return;
          }

          // 解码 base64 → 临时文件
          const ext = imageData.match(/data:image\/(\w+)/)?.[1] || 'png';
          const tmpFile = path.join(os.tmpdir(), `trade_ocr_${Date.now()}.${ext}`);
          const b64 = imageData.split(',')[1];
          try {
            fs.writeFileSync(tmpFile, Buffer.from(b64, 'base64'));
          } catch (e) {
            res.statusCode = 500;
            res.end(JSON.stringify({ ok: false, error: 'write temp file failed' }));
            return;
          }

          const args = ['波段策略/ocr_positions.py', tmpFile];
          execFile('python3', args, {
            cwd: path.resolve(__dirname, '../..'),
            timeout: 30000,
            maxBuffer: 1024 * 1024
          }, (err, stdout, stderr) => {
            try { fs.unlinkSync(tmpFile); } catch (_) {}

            if (err) {
              res.statusCode = 500;
              res.setHeader('Content-Type', 'application/json; charset=utf-8');
              res.end(JSON.stringify({ ok: false, error: String(stderr || err.message).slice(0, 300) }));
              return;
            }
            try {
              const data = JSON.parse(stdout.trim());
              res.setHeader('Content-Type', 'application/json; charset=utf-8');
              res.end(JSON.stringify({ ok: true, data }));
            } catch (e) {
              res.statusCode = 500;
              res.end(JSON.stringify({ ok: false, error: 'parse error', raw: stdout.slice(0, 200) }));
            }
          });
        });
        return true;
      } catch (e) {
        res.statusCode = 500;
        res.end(JSON.stringify({ ok: false, error: e.message }));
        return true;
      }
    }

    return false;
  };
  return handleRoute;
};
