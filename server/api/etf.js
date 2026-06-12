const ctx = require('../context');
ctx.install(global);
const fs = require('fs');

async function readBody(req) {
  return new Promise((resolve) => {
    const chunks = [];
    req.on('data', (chunk) => { chunks.push(chunk); });
    req.on('end', () => { resolve(Buffer.concat(chunks).toString()); });
  });
}

module.exports = function() {
  const handleRoute = async function(req, res) {
    const url = new URL(req.url, `http://${req.headers.host}`);

    if (url.pathname === '/api/sector/manage' && req.method === 'GET') {
      const cfg = readSectorProxyConfig();
      const etfs = {};

      if (cfg.variants && cfg.variants.etf) {
        Object.entries(cfg.variants.etf).forEach(([name, code]) => {
          const meta = (cfg.etf_meta && cfg.etf_meta[name]) || {};
          etfs[name] = {
            code,
            category: meta.category || '科技',
            sub_category: meta.sub_category || '硬件'
          };
        });
      }

      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, etfs }));
      return true;
    }

    if (url.pathname === '/api/sector/manage' && req.method === 'POST') {
      try {
        const raw = await readBody(req);
        const body = raw ? JSON.parse(raw) : {};
        const { name, code, category, sub_category } = body;

        if (!name || !code || !category || !sub_category) {
          res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
          res.end(JSON.stringify({ ok: false, error: 'name/code/category/sub_category 不能为空' }));
          return true;
        }
        if (!/^(sh|sz)\d{6}$/.test(code)) {
          res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
          res.end(JSON.stringify({ ok: false, error: '代码格式错误' }));
          return true;
        }

        const cfg = readJsonFileSafe(PROXY_FILE) || {};
        if (!cfg.variants) cfg.variants = {};
        if (!cfg.variants.etf) cfg.variants.etf = {};
        if (!cfg.etf_meta) cfg.etf_meta = {};

        const existed = cfg.variants.etf[name];
        cfg.variants.etf[name] = code;
        cfg.etf_meta[name] = { category, sub_category };
        cfg.updated_at = new Date().toISOString();

        fs.writeFileSync(PROXY_FILE, JSON.stringify(cfg, null, 2));

        const etfs = {};
        Object.entries(cfg.variants.etf).forEach(([n, c]) => {
          const meta = cfg.etf_meta[n] || {};
          etfs[n] = { code: c, category: meta.category || '科技', sub_category: meta.sub_category || '硬件' };
        });

        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: true, action: existed ? 'updated' : 'created', etfs }));
      } catch (e) {
        console.error('ETF manage POST error:', e.message);
        res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ ok: false, error: 'bad request', detail: e.message }));
      }
      return true;
    }

    if (url.pathname === '/api/sector/manage' && req.method === 'DELETE') {
      const name = url.searchParams.get('name');
      if (!name) {
        res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ ok: false, error: 'missing name' }));
        return true;
      }

      const cfg = readJsonFileSafe(PROXY_FILE) || {};
      if (cfg.variants && cfg.variants.etf) delete cfg.variants.etf[name];
      if (cfg.etf_meta) delete cfg.etf_meta[name];
      cfg.updated_at = new Date().toISOString();
      fs.writeFileSync(PROXY_FILE, JSON.stringify(cfg, null, 2));

      const etfs = {};
      if (cfg.variants && cfg.variants.etf) {
        Object.entries(cfg.variants.etf).forEach(([n, c]) => {
          const meta = (cfg.etf_meta && cfg.etf_meta[n]) || {};
          etfs[n] = { code: c, category: meta.category || '科技', sub_category: meta.sub_category || '硬件' };
        });
      }

      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, action: 'deleted', name, etfs }));
      return true;
    }

    return false;
  };
  return handleRoute;
};
