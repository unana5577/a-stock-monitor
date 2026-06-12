const ctx = require('../context');
ctx.install(global);

const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');

module.exports = function() {
  const handleRoute = async function(req, res) {
    const url = new URL(req.url, `http://${req.headers.host}`);

  if (url.pathname === '/api/m1/data/bazi' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        const data = JSON.parse(body || '{}');
        const gender = String(data.gender || '').trim();
        const birth = String(data.birth || '').trim();
        const place = String(data.place || '').trim();
        const placeDetail = String(data.placeDetail || '').trim();
        const trueSolar = Boolean(data.trueSolar);

        if (!birth) {
          res.statusCode = 400;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          return res.end(JSON.stringify({ ok: false, error: 'missing birth' }));
        }
        if (!place) {
          res.statusCode = 400;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          return res.end(JSON.stringify({ ok: false, error: 'missing place' }));
        }

        const script = path.join(__dirname, 'treasolo', 'm1_bazi.py');
        if (!fs.existsSync(script)) {
          res.statusCode = 500;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          return res.end(JSON.stringify({ ok: false, error: 'm1_bazi.py not found' }));
        }

        const pythonBin =
          process.env.PYTHON_BIN ||
          (fs.existsSync('/opt/homebrew/bin/python3') ? '/opt/homebrew/bin/python3' : 'python3');

        const args = [
          script,
          '--birth', birth,
          '--gender', gender,
          '--place', place,
          '--place_detail', placeDetail,
        ];
        if (trueSolar) args.push('--true_solar');

        execFile(pythonBin, args, { cwd: __dirname, timeout: 60000, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
          const out = String(stdout || '').trim();
          if (err) {
            res.statusCode = 500;
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            return res.end(JSON.stringify({ ok: false, error: (stderr || err.message || '').trim(), stdout: out }));
          }
          if (out && out.startsWith('{')) {
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            return res.end(out);
          }
          res.statusCode = 500;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          return res.end(JSON.stringify({ ok: false, error: 'invalid bazi output', stderr: (stderr || '').trim(), stdout: out }));
        });
      } catch (e) {
        res.statusCode = 400;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: e.message }));
      }
    });
    return;
  }

  if (url.pathname === '/api/m1/config/bazi_prompts' && req.method === 'GET') {
    try {
      const fp = path.join(__dirname, '八字', 'prompts.json');
      if (!fs.existsSync(fp)) {
        res.statusCode = 404;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'prompts not found' }));
        return;
      }
      const txt = fs.readFileSync(fp, 'utf8');
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.setHeader('Cache-Control', 'no-store');
      res.end(txt);
      return;
    } catch (e) {
      res.statusCode = 500;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: e.message }));
      return;
    }
  }

  if (url.pathname === '/api/m1/data/day_astro' && req.method === 'GET') {
    try {
      const day = String(url.searchParams.get('day') || '').trim();
      if (!day) {
        res.statusCode = 400;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'missing day' }));
        return;
      }

      const script = path.join(__dirname, 'treasolo', 'm1_day_astro.py');
      if (!fs.existsSync(script)) {
        res.statusCode = 500;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'm1_day_astro.py not found' }));
        return;
      }

      const pythonBin =
        process.env.PYTHON_BIN ||
        (fs.existsSync('/opt/homebrew/bin/python3') ? '/opt/homebrew/bin/python3' : 'python3');

      const args = [script, '--day', day];
      execFile(pythonBin, args, { cwd: __dirname, timeout: 60000, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
        const out = String(stdout || '').trim();
        if (err) {
          res.statusCode = 500;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: false, error: (stderr || err.message || '').trim(), stdout: out }));
          return;
        }
        if (out && out.startsWith('{')) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(out);
          return;
        }
        res.statusCode = 500;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'invalid day_astro output', stderr: (stderr || '').trim(), stdout: out }));
      });
      return;
    } catch (e) {
      res.statusCode = 500;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: e.message }));
      return;
    }
  }

  if (url.pathname === '/api/m1/data/astro_calendar' && req.method === 'GET') {
    try {
      const month = String(url.searchParams.get('month') || '').trim();
      const start = String(url.searchParams.get('start') || '').trim();
      const end = String(url.searchParams.get('end') || '').trim();

      if (!month && !(start && end)) {
        res.statusCode = 400;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'missing month or range' }));
        return;
      }

      const script = path.join(__dirname, 'treasolo', 'm1_astro_calendar.py');
      if (!fs.existsSync(script)) {
        res.statusCode = 500;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'm1_astro_calendar.py not found' }));
        return;
      }

      const pythonBin =
        process.env.PYTHON_BIN ||
        (fs.existsSync('/opt/homebrew/bin/python3') ? '/opt/homebrew/bin/python3' : 'python3');

      const args = [script];
      if (month) {
        args.push('--month', month);
      } else {
        args.push('--start', start, '--end', end);
      }

      execFile(pythonBin, args, { cwd: __dirname, timeout: 60000, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
        const out = String(stdout || '').trim();
        if (err) {
          res.statusCode = 500;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: false, error: (stderr || err.message || '').trim(), stdout: out }));
          return;
        }
        if (out && out.startsWith('{')) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(out);
          return;
        }
        res.statusCode = 500;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'invalid astro_calendar output', stderr: (stderr || '').trim(), stdout: out }));
      });
      return;
    } catch (e) {
      res.statusCode = 500;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: e.message }));
      return;
    }
  }
  // --- [M1 沙盒 BFF 路由结束] ---

    return false;
  };
  return handleRoute;
};
