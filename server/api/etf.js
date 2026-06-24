const ctx = require('../context');
ctx.install(global);
const fs = require('fs');
const { execFile } = require('child_process');
const path = require('path');

async function readBody(req) {
  return new Promise((resolve) => {
    const chunks = [];
    req.on('data', (chunk) => { chunks.push(chunk); });
    req.on('end', () => { resolve(Buffer.concat(chunks).toString()); });
  });
}

function readEtfMapFromProxy() {
  const raw = readJsonFileSafe(PROXY_FILE) || {};
  const map = {};
  for (const [name, code] of Object.entries(raw.variants?.etf || {})) {
    map[code] = {
      api_name: name,
      category: raw.etf_meta?.[name]?.category || '科技',
      sub_category: raw.etf_meta?.[name]?.sub_category || '硬件',
      hidden: raw.etf_meta?.[name]?.hidden || false
    };
  }
  return map;
}

function fetchQuoteName(code) {
  return new Promise((resolve) => {
    const tencentUrl = `http://qt.gtimg.cn/q=${code}`;
    execFile('python3', ['-c',
`import urllib.request, json, sys
req = urllib.request.Request('${tencentUrl}', headers={'Referer':'https://finance.qq.com'})
try:
    resp = urllib.request.urlopen(req, timeout=5)
    text = resp.read().decode('gbk')
    parts = text.split('~')
    if len(parts) >= 10:
        name = parts[1].strip()
        print(json.dumps({'ok':True,'name':name}))
    else:
        print(json.dumps({'ok':False,'error':'no data'}))
except Exception as e:
    print(json.dumps({'ok':False,'error':str(e)}))
    `], { cwd: path.resolve(__dirname, '../..'), timeout: 10000, maxBuffer: 1024 * 1024 }, (err, stdout, stderr) => {
      if (err) { resolve(null); return; }
      try {
        const d = JSON.parse(stdout.trim());
        resolve(d.ok ? d.name : null);
      } catch (e) { resolve(null); }
    });
  });
}

function triggerBackfillPipeline(code) {
  return new Promise((resolve) => {
    const scripts = [
      ['treasolo/m1_backfill.py', '--symbol', code, '--missing-window-days', '30', '--apply-fix', '--write', '--expect-start', '2025-05-01'],
      ['treasolo/m1_minute_fetch_etf.py', '--symbols', code, '--force'],
      ['treasolo/m1_warmup.py'],
      ['treasolo/m1_lifecycle.py']
    ];
    let idx = 0;
    function next() {
      if (idx >= scripts.length) return resolve();
      const args = scripts[idx++];
      execFile('python3', args, { cwd: path.resolve(__dirname, '../..'), timeout: 120000, maxBuffer: 10 * 1024 * 1024 }, (err) => {
        if (err) console.error(`[backfill] ${args[0]} failed:`, err.message);
        setTimeout(next, 2000);
      });
    }
    next();
  });
}

module.exports = function() {
  const handleRoute = async function(req, res) {
    const url = new URL(req.url, `http://${req.headers.host}`);

    if (url.pathname === '/api/sector/manage' && req.method === 'GET') {
      const etfs = readEtfMapFromProxy();
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, etfs }));
      return true;
    }

    if (url.pathname === '/api/sector/manage' && req.method === 'POST') {
      try {
        const raw = await readBody(req);
        const body = raw ? JSON.parse(raw) : {};
        let { code, category, sub_category, hidden } = body;
        const isBackfillOnly = url.searchParams.get('action') === 'backfill';

        if (!code) {
          res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
          res.end(JSON.stringify({ ok: false, error: 'code 不能为空' }));
          return true;
        }
        if (!/^(sh|sz)\d{6}$/.test(code)) {
          res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
          res.end(JSON.stringify({ ok: false, error: '代码格式错误，应为 sh/sz + 6位数字' }));
          return true;
        }

        if (isBackfillOnly) {
          await triggerBackfillPipeline(code);
          const etfs = readEtfMapFromProxy();
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: true, action: 'backfill_triggered', etfs }));
          return true;
        }

        const cfg = readJsonFileSafe(PROXY_FILE) || {};
        if (!cfg.variants) cfg.variants = {};
        if (!cfg.variants.etf) cfg.variants.etf = {};
        if (!cfg.etf_meta) cfg.etf_meta = {};

        let existingName = null;
        for (const [n, c] of Object.entries(cfg.variants.etf)) {
          if (c === code) { existingName = n; break; }
        }

        if (existingName) {
          const meta = cfg.etf_meta[existingName] || {};
          if (category) meta.category = category;
          if (sub_category) meta.sub_category = sub_category;
          if (typeof hidden === 'boolean') meta.hidden = hidden;
          cfg.etf_meta[existingName] = meta;
          cfg.updated_at = new Date().toISOString();
          fs.writeFileSync(PROXY_FILE, JSON.stringify(cfg, null, 2));

          const etfs = readEtfMapFromProxy();
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: true, action: 'updated', api_name: existingName, etfs }));
          return true;
        }

        if (!category) category = '科技';
        if (!sub_category) sub_category = '硬件';

        const name = await fetchQuoteName(code);
        const displayName = name || code;

        cfg.variants.etf[displayName] = code;
        cfg.etf_meta[displayName] = { category, sub_category, hidden: false };
        cfg.updated_at = new Date().toISOString();
        fs.writeFileSync(PROXY_FILE, JSON.stringify(cfg, null, 2));

        await triggerBackfillPipeline(code);

        const etfs = readEtfMapFromProxy();
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: true, action: 'created', api_name: displayName, etfs }));
      } catch (e) {
        console.error('ETF manage POST error:', e.message);
        res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ ok: false, error: 'bad request', detail: e.message }));
      }
      return true;
    }

    if (url.pathname === '/api/sector/manage' && req.method === 'DELETE') {
      const code = url.searchParams.get('code');
      if (!code) {
        res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ ok: false, error: 'missing code' }));
        return true;
      }

      const cfg = readJsonFileSafe(PROXY_FILE) || {};
      let deletedName = null;
      if (cfg.variants && cfg.variants.etf) {
        for (const [n, c] of Object.entries(cfg.variants.etf)) {
          if (c === code) {
            deletedName = n;
            delete cfg.variants.etf[n];
            break;
          }
        }
      }
      if (deletedName && cfg.etf_meta) {
        delete cfg.etf_meta[deletedName];
      }
      if (deletedName) {
        cfg.updated_at = new Date().toISOString();
        fs.writeFileSync(PROXY_FILE, JSON.stringify(cfg, null, 2));
      }

      const etfs = readEtfMapFromProxy();
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, action: deletedName ? 'deleted' : 'not_found', code, etfs }));
      return true;
    }

    return false;
  };
  return handleRoute;
};
