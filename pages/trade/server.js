const http = require('http')
const fs = require('fs')
const path = require('path')
const { execFile } = require('child_process')

const PORT = process.env.PORT || 8783
const API_HOST = process.env.API_TARGET || 'http://127.0.0.1:8787'
const ROOT = path.resolve(__dirname, '../..')

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'application/javascript; charset=utf-8',
  '.css':  'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png':  'image/png',
  '.svg':  'image/svg+xml',
}

function serveFile(res, filePath) {
  try {
    const ext = path.extname(filePath)
    const data = fs.readFileSync(filePath)
    res.setHeader('Content-Type', MIME[ext] || 'application/octet-stream')
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate')
    res.end(data)
  } catch {
    res.statusCode = 404
    res.end('404')
  }
}

function proxyToAPI(req, res) {
  const target = API_HOST + req.url
  const opts = require('url').parse(target)
  opts.method = req.method
  opts.headers = req.headers

  const proxy = http.request(opts, (pRes) => {
    res.writeHead(pRes.statusCode, pRes.headers)
    pRes.pipe(res)
  })
  proxy.on('error', () => {
    res.statusCode = 502
    res.setHeader('Content-Type', 'application/json; charset=utf-8')
    res.end(JSON.stringify({ ok: false, error: 'API unreachable (is :8787 running?)' }))
  })
  req.pipe(proxy)
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`)

  // /api/* → 转发到 8787
  if (url.pathname.startsWith('/api/')) {
    proxyToAPI(req, res)
    return
  }

  // Static files: serve from same directory as this server.js
  const dir = __dirname
  if (url.pathname === '/' || url.pathname === '/index.html') {
    serveFile(res, path.join(dir, 'index.html'))
    return
  }
  serveFile(res, path.join(dir, url.pathname))
})

server.listen(PORT, () => {
  console.log(`五阶段策略前端 → http://0.0.0.0:${PORT} (API → ${API_HOST})`)

  // 盘中快照定时器(每5分钟): 上线后可改为 n8n 工作流 M1-H-Stage-Snapshot
  const runSnapshot = () => {
    execFile('python3', ['波段策略/stage_runner.py', '--use-minute', '--output-snapshot'], {
      cwd: ROOT, timeout: 20000
    }, (err, stdout, stderr) => {
      if (err) console.error('[stage-snapshot]', String(stderr || err.message).slice(0, 100))
    })
  }
  runSnapshot()
  setInterval(runSnapshot, 5 * 60 * 1000)
})
