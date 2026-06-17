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

    // GET /api/trade/quote?symbol=sh515880 — 行情接口(腾讯源), 返回 name/price/pct
    if (url.pathname === '/api/trade/quote' && req.method === 'GET') {
      const symbol = url.searchParams.get('symbol') || '';
      if (!/^(sh|sz)\d{6}$/.test(symbol)) {
        res.statusCode = 400;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'invalid symbol' }));
        return true;
      }
      const tencentUrl = `http://qt.gtimg.cn/q=${symbol}`;
      execFile('python3', ['-c', `
import urllib.request, json, sys
req = urllib.request.Request('${tencentUrl}', headers={'Referer':'https://finance.qq.com'})
try:
    resp = urllib.request.urlopen(req, timeout=5)
    text = resp.read().decode('gbk')
    parts = text.split('~')
    if len(parts) >= 10:
        name = parts[1].strip()
        price = float(parts[3] or 0)
        pct = float(parts[32] or 0)
        print(json.dumps({'ok':True,'symbol':'${symbol}','name':name,'price':price,'pct':pct}))
    else:
        print(json.dumps({'ok':False,'error':'no data'}))
except Exception as e:
    print(json.dumps({'ok':False,'error':str(e)}))
      `], { cwd: path.resolve(__dirname, '../..'), timeout: 10000, maxBuffer: 1024 * 1024 }, (err, stdout, stderr) => {
        if (err) {
          res.statusCode = 502;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: false, error: 'upstream unreachable' }));
          return;
        }
        try {
          const data = JSON.parse(stdout.trim());
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify(data));
        } catch (e) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: false, error: 'parse error' }));
        }
      });
      return true;
    }

    // GET /api/trade/entry_tiers — 返回每只ETF的分批挂单价
    if (url.pathname === '/api/trade/entry_tiers' && req.method === 'GET') {
      try {
        const cfg = readSectorProxyConfig();
        const tiers = {};
        if (cfg.variants && cfg.variants.etf) {
          Object.entries(cfg.variants.etf).forEach(([name, code]) => {
            const meta = (cfg.etf_meta && cfg.etf_meta[name]) || {};
            if (meta.entry_tiers) {
              tiers[code] = meta.entry_tiers;
            }
          });
        }
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: true, tiers }));
        return true;
      } catch (e) {
        res.statusCode = 500;
        res.end(JSON.stringify({ ok: false, error: e.message }));
        return true;
      }
    }

    // GET /api/trade/stage_snapshot — 读阶段快照(优先, ~5ms); fallback 到 stage_state
    if (url.pathname === '/api/trade/stage_snapshot' && req.method === 'GET') {
      try {
        const sp = path.resolve(__dirname, '..', '..', 'data', 'stage', 'snapshot.json');
        if (fs.existsSync(sp)) {
          const data = JSON.parse(fs.readFileSync(sp, 'utf-8'));
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: true, data }));
          return true;
        }

        // fallback: execFile stage_runner
        const day = url.searchParams.get('day') || 'today';
        const syms = url.searchParams.get('symbols') || '';
        const args = ['波段策略/stage_runner.py', '--day', day];
        if (syms) args.push('--symbols', syms);
        execFile('python3', args, {
          cwd: path.resolve(__dirname, '../..'), timeout: 15000, maxBuffer: 1024 * 1024
        }, (err, stdout, stderr) => {
          if (err) {
            res.statusCode = 500;
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify({ ok: false, error: String(stderr || err.message) }));
            return;
          }
          try {
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify({ ok: true, data: JSON.parse(stdout.trim()) }));
          } catch (e) {
            res.statusCode = 500;
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify({ ok: false, error: 'parse error' }));
          }
        });
        return true;
      } catch (e) {
        res.statusCode = 500;
        res.end(JSON.stringify({ ok: false, error: e.message }));
        return true;
      }
    }

    // POST /api/trade/run-stage-snapshot — n8n 工作流 M1-H 调用, 执行 stage_runner --use-minute --output-snapshot
    if (url.pathname === '/api/trade/run-stage-snapshot' && req.method === 'POST') {
      const args = ['波段策略/stage_runner.py', '--use-minute', '--output-snapshot'];
      execFile('python3', args, {
        cwd: path.resolve(__dirname, '../..'), timeout: 30000, maxBuffer: 1024 * 1024
      }, (err, stdout, stderr) => {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({
          ok: !err,
          stdout: (stdout || '').trim().split('\n'),
          stderr: stderr
        }));
      });
      return true;
    }

    return false;
  };
  return handleRoute;
};
