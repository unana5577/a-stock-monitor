const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');
const crypto = require('crypto');

// Try to load .env file
const envPath = path.join(__dirname, '.env');
if (fs.existsSync(envPath)) {
  const content = fs.readFileSync(envPath, 'utf-8');
  content.split('\n').forEach(line => {
    const parts = line.split('=');
    if (parts.length >= 2) {
      const key = parts[0].trim();
      const val = parts.slice(1).join('=').trim();
      if (key && val && !process.env[key]) {
        process.env[key] = val;
      }
    }
  });
}

const ai = require('./ai');

const PORT = process.env.PORT || 8787;
const CACHE_TTL_MS = 30_000;  // 修改为30秒，确保每分钟都能获取最新数据
const OVERVIEW_CACHE_REV = 2;
const PROXY_FILE = path.join(__dirname, 'data', 'sector-proxy.json');
const HOLIDAY_FILE = path.join(__dirname, 'config', 'holidays.json');

const cache = new Map();
const now = () => Date.now();
let lastAiText = '';
const lastGoodSnapshot = { payload: null, ts: 0 };
const lastGoodMinute = new Map();
let lastWarmupDay = '';
const lastIntradayRotation = { payload: null, ts: 0, day: '', leader: '', signal: '', reason: [], signalTs: 0 };
const INTRADAY_DEBOUNCE_MS = 10 * 60 * 1000;
const INTRADAY_CACHE_TTL_MS = 2 * 60 * 1000;
let lastDailyBackfillDay = '';

function isNum(v) {
  return typeof v === 'number' && !Number.isNaN(v);
}

function pickNum(...vals) {
  for (const v of vals) {
    if (isNum(v)) return v;
  }
  return null;
}

function pad2(n) {
  return String(n).padStart(2, '0');
}

function minuteKey(d) {
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

function minuteKeyBeijing(d) {
  try {
    const fmt = new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Shanghai',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
    const parts = fmt.formatToParts(d);
    const map = {};
    parts.forEach((p) => {
      if (p.type !== 'literal') map[p.type] = p.value;
    });
    const hh = map.hour;
    const mm = map.minute;
    if (!hh || !mm) return minuteKey(d);
    return `${hh}:${mm}`;
  } catch (e) {
    return minuteKey(d);
  }
}

function minuteToNumber(t) {
  if (!t || !t.includes(':')) return null;
  const [h, m] = t.split(':').map(n => parseInt(n, 10));
  if (!Number.isFinite(h) || !Number.isFinite(m)) return null;
  return h * 60 + m;
}

function timeToMinuteKey(t) {
  if (!t) return null;
  const s = String(t);
  if (s.includes(' ')) {
    const parts = s.split(' ');
    return parts[1] || null;
  }
  if (s.includes('T')) {
    const parts = s.split('T');
    return (parts[1] || '').slice(0, 5) || null;
  }
  if (s.length >= 5 && s[2] === ':') return s.slice(0, 5);
  return s;
}

function isTradingMinute(t) {
  const n = minuteToNumber(t);
  if (n == null) return false;
  return (n >= 570 && n <= 690) || (n >= 780 && n <= 900);
}

function ensureBondMirror(bonds) {
  if (!bonds) return bonds;
  if (!bonds.t && bonds.t2603) {
    bonds.t = { price: bonds.t2603.price || null, pct: bonds.t2603.pct || null };
  }
  if (!bonds.tl && bonds.tl2603) {
    bonds.tl = { price: bonds.tl2603.price || null, pct: bonds.tl2603.pct || null };
  }
  if (!bonds.t2603 && bonds.t) {
    bonds.t2603 = { price: bonds.t.price || null, pct: bonds.t.pct || null, series: [] };
  }
  if (!bonds.tl2603 && bonds.tl) {
    bonds.tl2603 = { price: bonds.tl.price || null, pct: bonds.tl.pct || null, series: [] };
  }
  return bonds;
}

function mergeBond(target, source) {
  if (!target) return source;
  if (!source) return target;
  return {
    price: isNum(target.price) ? target.price : source.price,
    pct: isNum(target.pct) ? target.pct : source.pct,
    series: target.series || source.series || []
  };
}

function repairSnapshot(snap) {
  if (!snap) return snap;
  snap.bonds = ensureBondMirror(snap.bonds || {});
  const tOk = isNum(snap.bonds?.t2603?.price) || isNum(snap.bonds?.t?.price);
  const tlOk = isNum(snap.bonds?.tl2603?.price) || isNum(snap.bonds?.tl?.price);
  if ((!tOk || !tlOk) && lastGoodSnapshot.payload?.bonds) {
    const src = ensureBondMirror(lastGoodSnapshot.payload.bonds || {});
    snap.bonds.t2603 = mergeBond(snap.bonds.t2603, src.t2603);
    snap.bonds.tl2603 = mergeBond(snap.bonds.tl2603, src.tl2603);
    snap.bonds.t = mergeBond(snap.bonds.t, src.t);
    snap.bonds.tl = mergeBond(snap.bonds.tl, src.tl);
    snap.bonds.gov = mergeBond(snap.bonds.gov, src.gov);
  }
  if (lastGoodSnapshot.payload) {
    const srcSectors = lastGoodSnapshot.payload.sectors || {};
    snap.sectors = snap.sectors || {};
    if (!isNum(snap.sectors?.bank?.pct) && isNum(srcSectors?.bank?.pct)) {
      snap.sectors.bank = { ...(snap.sectors.bank || {}), pct: srcSectors.bank.pct };
    }
    if (!isNum(snap.sectors?.broker?.pct) && isNum(srcSectors?.broker?.pct)) {
      snap.sectors.broker = { ...(snap.sectors.broker || {}), pct: srcSectors.broker.pct };
    }
    if (!isNum(snap.sectors?.insure?.pct) && isNum(srcSectors?.insure?.pct)) {
      snap.sectors.insure = { ...(snap.sectors.insure || {}), pct: srcSectors.insure.pct };
    }
    if (!isNum(snap.bonds?.gov?.pct) && isNum(lastGoodSnapshot.payload.bonds?.gov?.pct)) {
      snap.bonds.gov = { ...(snap.bonds.gov || {}), pct: lastGoodSnapshot.payload.bonds.gov.pct };
    }
  }
  snap.bonds = ensureBondMirror(snap.bonds);
  snap.sentiment = snap.sentiment || {};
  const etfMap = readEtfAmountTotalMap();
  const etfBaseDay = latestTradingDay();
  const etfDay = isMarketOpenNow() ? (snap.day || etfBaseDay) : etfBaseDay;
  const etfRow = pickEtfAmountTotal(etfMap, etfDay);
  const etfAmountWan = etfRow ? normalizeEtfTotalToWan(etfRow.total) : null;
  const totalAmountWan = isNum(snap.sentiment.volume) && snap.sentiment.volume > 0 ? snap.sentiment.volume : null;
  const etfShare = (etfAmountWan != null && totalAmountWan != null) ? etfAmountWan / totalAmountWan : null;
  snap.sentiment.etfAmount = etfAmountWan;
  snap.sentiment.etfAmountStr = etfAmountWan ? (etfAmountWan / 10000).toFixed(1) + '亿' : '-';
  snap.sentiment.etfSharePct = etfShare != null ? +((etfShare * 100).toFixed(2)) : null;
  snap.sentiment.etfAsOf = etfRow ? etfRow.day : null;
  return snap;
}

function warmupDay(day) {
  if (!day || day === lastWarmupDay) return;
  lastWarmupDay = day;
  const codes = ['sse','szi','gem','star','hs300','csi2000','avg','bank','broker','insure','gov','t','tl'];
  (async () => {
    ensureVolumeFile(day);
    await Promise.all(codes.map(code => loadMinuteSeries(day, code, minuteEmMap(code))));
  })();
}

function get(url) {
  return new Promise((resolve, reject) => {
    const lib = url.startsWith('https') ? https : http;
    const req = lib.get(url, { 
      headers: { 'User-Agent': 'Mozilla/5.0' } 
    }, (res) => {
      let data = [];
      res.on('data', (chunk) => data.push(chunk));
      res.on('end', () => resolve({ status: res.statusCode, data: Buffer.concat(data).toString() }));
    });
    req.on('error', reject);
    req.setTimeout(5000, () => req.destroy(new Error('timeout')));
  });
}

function postJson(url, headers, body) {
  return new Promise((resolve, reject) => {
    const lib = url.startsWith('https') ? https : http;
    const payload = JSON.stringify(body || {});
    const req = lib.request(url, { 
      method: 'POST',
      headers: {
        'User-Agent': 'Mozilla/5.0',
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
        ...headers
      }
    }, (res) => {
      let data = [];
      res.on('data', (chunk) => data.push(chunk));
      res.on('end', () => resolve({ status: res.statusCode, data: Buffer.concat(data).toString() }));
    });
    req.on('error', reject);
    req.setTimeout(15000, () => req.destroy(new Error('timeout')));
    req.write(payload);
    req.end();
  });
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', (c) => {
      size += c.length;
      if (size > 1e6) { req.destroy(); reject(new Error('body too large')); return; }
      chunks.push(c);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString()));
    req.on('error', reject);
  });
}

const PROMPT_PATH = path.join(__dirname, 'prompts', 'stock-daily.txt');
const SECTOR_PROMPT = `你是A股板块轮动分析师。只基于输入数据做判断，不做收益承诺，不使用夸张词。输出必须中文、简洁、可直接推送。
数据由系统抓取后注入给你，你不能自行联网或补充外部数据。若字段缺失，需明确说明“数据缺失”。

输入数据
- history：9个关注板块的近180个交易日数据（收盘、涨跌幅、成交额）
- rank：当日板块涨跌幅榜前十

分析目标
1. 跷跷板分析：寻找明显负相关板块对，优先“资源类”与“成长类”的资金切换线索
2. 共振分析：寻找明显正相关的板块群，判断是否存在合力
3. 轮动规律：结合180天历史与当日榜单，给出轮动顺序与节奏
4. 主线趋势：判断当前是否存在主线板块

输出格式
【跷跷板分析】一句话结论+关键板块
【共振分析】一句话结论+关键板块
【轮动规律】一句话结论+节奏判断
【主线趋势】一句话结论+主线判断`;

const ASHARE_URL = 'https://raw.githubusercontent.com/mpquant/Ashare/main/Ashare.py';
const ASHARE_PATH = path.join(__dirname, 'data', 'Ashare.py');

function runPython(code, args = []) {
  return new Promise((resolve, reject) => {
    execFile('python3', ['-c', code, ...args], { timeout: 8000 }, (err, stdout) => {
      if (err) return reject(err);
      resolve(stdout.toString());
    });
  });
}

function execPythonJson(args, timeout = 30000) {
  return new Promise((resolve) => {
    execFile('python3', args, { timeout, cwd: __dirname, maxBuffer: 10 * 1024 * 1024 }, (err, stdout) => {
      if (err) return resolve(null);
      const out = (stdout || '').toString().trim();
      if (!out) return resolve(null);
      try {
        if (isJsonText(out)) return resolve(JSON.parse(out));
        const idx = out.indexOf('{');
        const alt = idx >= 0 ? out.slice(idx) : out;
        if (!isJsonText(alt)) return resolve(null);
        return resolve(JSON.parse(alt));
      } catch (e) {
        return resolve(null);
      }
    });
  });
}

async function withTimeout(promise, ms) {
  let timer = null;
  try {
    return await Promise.race([
      promise,
      new Promise((resolve) => {
        timer = setTimeout(() => resolve(null), ms);
      })
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

async function ensureAshareFile() {
  if (fs.existsSync(ASHARE_PATH)) return ASHARE_PATH;
  const dir = path.dirname(ASHARE_PATH);
  fs.mkdirSync(dir, { recursive: true });
  const { status, data } = await get(ASHARE_URL);
  if (status !== 200 || !data) throw new Error('download failed');
  fs.writeFileSync(ASHARE_PATH, data);
  return ASHARE_PATH;
}

async function fetchAshareMinute(symbol) {
  const key = `ashare:${symbol}`;
  const hit = cache.get(key);
  if (hit && now() - hit.t < CACHE_TTL_MS) return hit.v;
  try {
    const file = await ensureAshareFile();
    const script = `
import importlib.util, sys, json
path = sys.argv[1]
symbol = sys.argv[2]
spec = importlib.util.spec_from_file_location("Ashare", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
def find_col(d, name):
    for c in d.columns:
        if str(c).lower() == name:
            return c
    return None
prev_close = None
try:
    dfd = mod.get_price(symbol, frequency='1d', count=2)
    if dfd is not None and not getattr(dfd, 'empty', False):
        dfd = dfd.reset_index()
        close_col_d = find_col(dfd, 'close')
        if close_col_d is not None:
            if len(dfd) >= 2:
                prev_close = float(dfd.iloc[-2][close_col_d])
            else:
                prev_close = float(dfd.iloc[-1][close_col_d])
except Exception:
    prev_close = None
df = mod.get_price(symbol, frequency='1m', count=240)
if df is None or getattr(df, 'empty', False):
    print(json.dumps({"series": [], "prevClose": prev_close}, ensure_ascii=False))
    raise SystemExit(0)
df = df.reset_index()
time_col = None
for c in df.columns:
    lc = str(c).lower()
    if lc in ['datetime','date','time']:
        time_col = c
        break
if time_col is None:
    time_col = df.columns[0]
open_col = find_col(df, 'open')
close_col = find_col(df, 'close')
if open_col is None or close_col is None:
    print(json.dumps({"series": [], "prevClose": prev_close}, ensure_ascii=False))
    raise SystemExit(0)
def fmt(t):
    s = str(t)
    return s[:16] if len(s) >= 16 else s
res = []
for _, row in df.iterrows():
    res.append({
        "time": fmt(row[time_col]),
        "open": float(row[open_col]),
        "close": float(row[close_col])
    })
print(json.dumps({"series": res, "prevClose": prev_close}, ensure_ascii=False))
`;
    const output = await runPython(script, [file, symbol]);
    const payload = output ? JSON.parse(output) : { series: [], prevClose: null };
    const rawArr = Array.isArray(payload) ? payload : (payload.series || []);
    const prevClose = payload && !Array.isArray(payload) ? payload.prevClose : null;
    
    // Determine date from data or default to today
    let arr = rawArr;
    let day = (new Date()).toISOString().split('T')[0];

    if (rawArr.length > 0 && rawArr[rawArr.length - 1]?.time) {
      // Extract date from the LAST data point (handles cross-day data)
      const datePart = rawArr[rawArr.length - 1].time.split(' ')[0];
      if (datePart && /^\d{4}-\d{2}-\d{2}$/.test(datePart)) {
        day = datePart;
        // Filter to ensure data consistency (all points from same day)
        arr = rawArr.filter(p => p?.time && String(p.time).startsWith(day));
      }
    }

    const res = { date: day, data: arr, prevClose: prevClose || null };
    cache.set(key, { t: now(), v: res });
    return res;
  } catch (e) {
    return { date: null, data: [], prevClose: null };
  }
}

// 2. Tencent Snapshot
async function fetchSnapshot(codes) {
  const url = `http://qt.gtimg.cn/q=${codes}`;
  try {
    const { status, data } = await get(url);
    if (status !== 200) return {};
    
    const parts = data.split(';').filter(Boolean);
    const result = {};
    
    const parseAmount = (vals) => {
      const raw = Number(vals[37]);
      const rawOk = Number.isFinite(raw) && raw > 0;
      let alt = null;
      const mixed = vals[35] || '';
      if (mixed && mixed.includes('/')) {
        const seg = mixed.split('/');
        const maybe = Number(seg[2]);
        if (Number.isFinite(maybe) && maybe > 0) {
          alt = maybe > 1e10 ? maybe / 10000 : maybe;
        }
      }
      if (Number.isFinite(alt) && alt > 0) {
        if (!rawOk) return alt;
        const ratio = alt / raw;
        if (!Number.isFinite(ratio) || ratio < 0.5 || ratio > 2) return alt;
      }
      return rawOk ? raw : null;
    };

    parts.forEach(line => {
      if (!line.includes('=')) return;
      const [left, right] = line.split('=');
      const code = left.split('_')[1]; 
      const vals = right.replace(/"/g, '').split('~');
      
      if (vals.length > 30) {
        result[code] = {
          name: vals[1],
          price: parseFloat(vals[3]),
          pct: parseFloat(vals[32]), 
          vol: parseFloat(vals[6]), 
          amount: parseAmount(vals)
        };
      }
    });
    return result;
  } catch (e) {
    return {};
  }
}

async function fetchEastmoneySnapshot(secids) {
  const result = {};
  await Promise.all(secids.map(async (secid) => {
    const url = `https://push2.eastmoney.com/api/qt/stock/get?secid=${secid}&fields=f43,f170,f58,f60`;
    try {
      const { status, data } = await get(url);
      if (status !== 200) return;
      const json = JSON.parse(data);
      if (!json.data) return;
      const pct = json.data.f170 != null ? +(json.data.f170 / 100).toFixed(2) : null;
      const price = json.data.f43 != null ? +(json.data.f43 / 100).toFixed(2) : null;
      const prevClose = json.data.f60 != null ? +(json.data.f60 / 100).toFixed(2) : null;
      result[secid] = { name: json.data.f58, pct, price, prevClose };
    } catch (e) {
      return;
    }
  }));
  return result;
}


async function fetchEastmoneyMinute(secid) {
  const key = `em1m:${secid}`;
  const hit = cache.get(key);
  if (hit && now() - hit.t < CACHE_TTL_MS) return hit.v;
  const url = `https://push2.eastmoney.com/api/qt/stock/kline/get?secid=${secid}&fields1=f1,f2&fields2=f51,f52,f53,f54,f55,f56&klt=1&fqt=1&end=20500101&lmt=240`;
  try {
    const { status, data } = await get(url);
    if (status !== 200) throw new Error('status ' + status);
    const json = JSON.parse(data);
    const kl = json?.data?.klines || [];
    const arr = kl.map((row) => {
      const parts = row.split(',');
      return { time: parts[0]?.slice(0,16), open: +parts[1], close: +parts[2] };
    }).filter(p => p.time);
    const today = (new Date()).toISOString().split('T')[0];
    const filtered = arr.filter(p => p?.time && String(p.time).startsWith(today));
    const res = { date: today, data: filtered, prevClose: null };
    cache.set(key, { t: now(), v: res });
    return res;
  } catch (e) {
    return { date: null, data: [], prevClose: null };
  }
}

async function fetchEastmoneyBreadth() {
  const url = 'https://push2.eastmoney.com/api/qt/stock/get?secid=1.000001&fields=f104,f105,f106';
  try {
    const { status, data } = await get(url);
    if (status !== 200) return null;
    const json = JSON.parse(data);
    const up = Number(json?.data?.f104);
    const down = Number(json?.data?.f105);
    const flat = Number(json?.data?.f106);
    // 非交易时间返回0/0/100，需要排除这种情况
    if (!isNum(up) || !isNum(down) || (up === 0 && down === 0)) return null;
    const total = Number.isFinite(flat) ? up + down + flat : up + down;
    return { up, down, flat: Number.isFinite(flat) ? flat : 0, total };
  } catch (e) {
    return null;
  }
}

async function fetchBreadthViaPython() {
  return new Promise((resolve) => {
    execFile('python3', ['fetch_sector_data.py', 'breadth'], { ...getExecOptions(), timeout: 20000 }, (err, stdout) => {
      if (err) return resolve(null);
      const out = (stdout || '').trim();
      if (!out || !isJsonText(out)) return resolve(null);
      try {
        const obj = JSON.parse(out);
        if (!isNum(obj?.up) || !isNum(obj?.down)) return resolve(null);
        if (!isNum(obj.total)) obj.total = Number(obj.up || 0) + Number(obj.down || 0) + Number(obj.flat || 0);
        resolve(obj);
      } catch (e) {
        resolve(null);
      }
    });
  });
}

async function fetchBreadthRealtime() {
  const em = await fetchEastmoneyBreadth();
  if (em) return em;
  return await fetchBreadthViaPython();
}

async function fetchEastmoneyDaily(secid, limit = 180) {
  const key = `em1d:${secid}:${limit}`;
  const hit = cache.get(key);
  if (hit && now() - hit.t < CACHE_TTL_MS) return hit.v;
  const url = `https://push2.eastmoney.com/api/qt/stock/kline/get?secid=${secid}&fields1=f1,f2&fields2=f51,f52,f53,f54,f55,f56,f57,f59,f60,f61&klt=101&fqt=1&end=20500101&lmt=${limit}`;
  try {
    const { status, data } = await get(url);
    if (status !== 200) throw new Error('status ' + status);
    const json = JSON.parse(data);
    const kl = json?.data?.klines || [];
    const arr = kl.map((row) => {
      const parts = row.split(',');
      return {
        date: parts[0],
        open: Number(parts[1]),
        close: Number(parts[2]),
        high: Number(parts[3]),
        low: Number(parts[4]),
        volume: Number(parts[5]),
        amount: Number(parts[6]),
        pct: Number(parts[8])
      };
    }).filter(p => p.date);
    const res = { date: arr.length ? arr[arr.length - 1]?.date : null, data: arr };
    cache.set(key, { t: now(), v: res });
    return res;
  } catch (e) {
    return { date: null, data: [] };
  }
}

async function fetchTencentDaily(code, limit = 180) {
  // ⚠️ CRITICAL: ETF检测 - 6位数字，5开头(上交所)或1开头(深交所)
  // ETF使用本地持久化数据（warmup文件或ETF日线文件），指数使用index_daily，板块代码使用腾讯API
  const cleanCode = code.replace(/sh|sz|SH|SZ/g, '');
  const isETF = /^\d{6}$/.test(cleanCode) && ['5', '1'].includes(cleanCode[0]);
  // 指数代码检测
  const isIndex = /^\d{6}$/.test(cleanCode) && ['000001', '399001', '399006', '000688'].includes(cleanCode);

  if (isIndex) {
    // ✅ 指数：从本地持久化文件读取
    const indexFile = path.join(__dirname, 'data', 'index_daily', `index_${cleanCode}.jsonl`);
    if (fs.existsSync(indexFile)) {
      try {
        let data = [];
        const lines = fs.readFileSync(indexFile, 'utf-8').split('\n').filter(Boolean);
        for (const line of lines) {
          try {
            const item = JSON.parse(line);
            if (item.date) data.push(item);
          } catch (e) {
            // 忽略JSON解析错误
          }
        }
        data.sort((a, b) => a.date.localeCompare(b.date));
        if (data.length > limit) {
          data = data.slice(-limit);
        }
        const res = { date: data[0]?.date || null, data };
        cache.set(`tx1d:${code}:${limit}`, { t: now(), v: res });
        return res;
      } catch (e) {
        console.error('指数本地文件读取失败:', e);
      }
    }
    // 指数无本地数据，继续使用腾讯API
  }

  if (isETF) {
    const cfg = readSectorProxyConfig();
    const proxyMap = (cfg.variants && (cfg.variants.etf || {})) || {};
    const sectorName = Object.keys(proxyMap).find(name => proxyMap[name] === code);

    // ✅ 方法1: 从固定名称的warmup文件读取
    const warmupFile = path.join(__dirname, 'data', `sector-history-warmup-60.json`);
    if (fs.existsSync(warmupFile)) {
      try {
        const txt = fs.readFileSync(warmupFile, 'utf-8');
        const obj = JSON.parse(txt);

        if (sectorName && obj.history && obj.history[sectorName]) {
          let data = obj.history[sectorName];
          if (data.length > limit) {
            data = data.slice(-limit);
          }
          const res = { date: data[0]?.date || null, data };
          cache.set(`tx1d:${code}:${limit}`, { t: now(), v: res });
          return res;
        }
      } catch (e) {
        console.error('ETF warmup读取失败:', e);
      }
    }

    // ✅ 方法2: fallback到直接读取ETF日线文件
    const etfFile = path.join(__dirname, 'data', 'etf_daily', `etf_${cleanCode}.jsonl`);
    if (fs.existsSync(etfFile)) {
      try {
        let data = [];
        const lines = fs.readFileSync(etfFile, 'utf-8').split('\n').filter(Boolean);
        for (const line of lines) {
          try {
            const item = JSON.parse(line);
            if (item.date) data.push(item);
          } catch (e) {
            // 忽略JSON解析错误
          }
        }
        data.sort((a, b) => a.date.localeCompare(b.date));
        if (data.length > limit) {
          data = data.slice(-limit);
        }
        const res = { date: data[0]?.date || null, data };
        cache.set(`tx1d:${code}:${limit}`, { t: now(), v: res });
        return res;
      } catch (e) {
        console.error('ETF本地文件读取失败:', e);
      }
    }

    // ETF没有任何本地数据，返回空
    return { date: null, data: [] };
  }

  // 板块代码：使用腾讯API
  const key = `tx1d:${code}:${limit}`;
  const hit = cache.get(key);
  if (hit && now() - hit.t < CACHE_TTL_MS) return hit.v;
  const url = `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${code},day,,,${limit},qfq`;
  try {
    const { status, data } = await get(url);
    if (status !== 200) throw new Error('status ' + status);
    const json = JSON.parse(data);
    const klines = json?.data?.[code]?.day || [];
    const arr = klines.map((row) => {
      const open = Number(row[1]);
      const close = Number(row[2]);
      const pct = open ? +(((close - open) / open) * 100).toFixed(2) : null;
      return {
        date: normalizeDateStr(row[0]),
        open,
        close,
        high: Number(row[3]),
        low: Number(row[4]),
        volume: Number(row[5]),
        amount: null,
        pct
      };
    });
    const res = { date: arr.length ? arr[arr.length - 1]?.date : null, data: arr };
    cache.set(key, { t: now(), v: res });
    return res;
  } catch (e) {
    return { date: null, data: [] };
  }
}

function pctOfDay(arr) {
  if (!arr || !arr.length) return null;
  const first = arr[0]?.open;
  const last = arr[arr.length - 1]?.close;
  if (!first || !last) return null;
  return +(((last - first) / first) * 100).toFixed(2);
}

function toNumber(v) {
  if (v === null || v === undefined || v === '-') return null;
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  return n;
}

function normalizeBondPrice(price) {
  if (price === null || price === undefined) return null;
  const n = Number(price);
  if (!Number.isFinite(n)) return null;
  if (n > 500) return +((n / 10).toFixed(2));
  return n;
}

function deriveFromSeries(series, prevClose) {
  if (!series || !series.length) return { price: null, pct: null };
  const firstBar = series[0] || null;
  const lastBar = series[series.length - 1] || null;
  const open0 = toNumber(firstBar?.open);
  const close0 = toNumber(firstBar?.close);
  const firstPx = pickNum(open0, close0);
  const last = pickNum(toNumber(lastBar?.close), toNumber(lastBar?.open));
  const prev = toNumber(prevClose);
  let first = pickNum(prev, firstPx);
  if (isNum(prev) && prev > 0 && isNum(firstPx) && firstPx > 0) {
    const ratio = firstPx / prev;
    if (!Number.isFinite(ratio) || ratio < 0.5 || ratio > 2) {
      first = firstPx;
    }
  }
  if (first == null || last == null) return { price: last || null, pct: null };
  let pct = first ? +(((last - first) / first) * 100).toFixed(2) : null;
  if (pct != null && Number.isFinite(pct) && Math.abs(pct) > 30) pct = null;
  return { price: last || null, pct };
}

function archiveSnapshot(payload) {
  const day = (payload.day || '').replace(/-/g, '');
  if (!day) return;
  const dir = path.join(__dirname, 'data');
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, `archive-${day}.jsonl`);
  const latest = latestTradingDay();
  if (latest && `${latest.replace(/-/g, '')}` > day && fs.existsSync(file) && process.env.ALLOW_HISTORY_WRITE !== '1') return;
  const row = [
    payload.ts,
    toNumber(payload.indices?.sse?.price), toNumber(payload.indices?.sse?.pct),
    toNumber(payload.indices?.szi?.price), toNumber(payload.indices?.szi?.pct),
    toNumber(payload.indices?.gem?.price), toNumber(payload.indices?.gem?.pct),
    toNumber(payload.indices?.star?.price), toNumber(payload.indices?.star?.pct),
    toNumber(payload.indices?.hs300?.price), toNumber(payload.indices?.hs300?.pct),
    toNumber(payload.indices?.csi2000?.price), toNumber(payload.indices?.csi2000?.pct),
    toNumber(payload.sectors?.bank?.pct), toNumber(payload.sectors?.broker?.pct), toNumber(payload.sectors?.insure?.pct),
    toNumber(payload.bonds?.gov?.pct),
    toNumber(payload.bonds?.t2603?.price), toNumber(payload.bonds?.t2603?.pct),
    toNumber(payload.bonds?.tl2603?.price), toNumber(payload.bonds?.tl2603?.pct),
    toNumber(payload.sentiment?.volume), toNumber(payload.sentiment?.upCount), toNumber(payload.sentiment?.downCount),
    toNumber(payload.indices?.avg?.price), toNumber(payload.indices?.avg?.pct)
  ];
  fs.appendFile(file, JSON.stringify(row) + '\n', () => {});
}

function minuteFilePath(day, code) {
  const d = day.replace(/-/g, '');
  const dir = path.join(__dirname, 'data');
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, `minute-${d}-${code}.jsonl`);
}

function runtimeMinuteFilePath(day, code) {
  const d = day.replace(/-/g, '');
  const dir = path.join(__dirname, 'runtime', 'minute');
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, `minute-${d}-${code}.jsonl`);
}

function findLatestRuntimeMinuteFile(code) {
  const dir = path.join(__dirname, 'runtime', 'minute');
  if (!fs.existsSync(dir)) return null;
  const files = fs.readdirSync(dir).filter(f => f.startsWith('minute-') && f.endsWith(`-${code}.jsonl`));
  if (!files.length) return null;
  files.sort();
  return path.join(dir, files[files.length - 1]);
}

function volumeFilePath(day) {
  const d = day.replace(/-/g, '');
  const dir = path.join(__dirname, 'data');
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, `volume-${d}.jsonl`);
}

function marketAmountDailyPath() {
  const dir = path.join(__dirname, 'data', 'market');
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, 'market-amount-daily.jsonl');
}

function readMarketAmountDailyMap() {
  const file = marketAmountDailyPath();
  if (!fs.existsSync(file)) return new Map();
  const txt = fs.readFileSync(file, 'utf-8').trim();
  if (!txt) return new Map();
  const map = new Map();
  for (const line of txt.split('\n')) {
    if (!line) continue;
    try {
      const row = JSON.parse(line);
      if (!Array.isArray(row) || row.length < 2) continue;
      const day = String(row[0] || '');
      const total = Number(row[1]);
      const sh = row.length >= 3 ? Number(row[2]) : null;
      const sz = row.length >= 4 ? Number(row[3]) : null;
      if (!day || !Number.isFinite(total)) continue;
      map.set(day, { day, total, sh: Number.isFinite(sh) ? sh : null, sz: Number.isFinite(sz) ? sz : null });
    } catch (e) {
      void e;
    }
  }
  return map;
}

async function backfillMarketAmountDaily(startDay) {
  const start = String(startDay || '').trim();
  if (!start) return { ok: false, error: 'missing startDay' };
  const obj = await execPythonJson(['scripts/backfill_market_amount_daily.py', start], 180000);
  if (!obj || obj.ok !== true) return obj || { ok: false, error: 'backfill failed' };
  const map = readMarketAmountDailyMap();
  return { ok: true, startDay: start, rows: obj.rows ?? map.size, totalDays: map.size, path: obj.path || marketAmountDailyPath() };
}

function etfAmountTotalPath() {
  const dir = path.join(__dirname, 'data', 'market');
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, 'etf-amount-total.jsonl');
}

function breadthCachePath() {
  const dir = path.join(__dirname, 'data', 'market');
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, 'breadth-cache.json');
}

function readBreadthCache() {
  const file = breadthCachePath();
  if (!fs.existsSync(file)) return null;
  try {
    const txt = fs.readFileSync(file, 'utf8').trim();
    if (!txt) return null;
    const data = JSON.parse(txt);
    // 兼容 { ok: true, data: {...} } 格式
    if (data.data && typeof data.data === 'object') {
        return data.data;
    }
    return data;
  } catch (e) {
    return null;
  }
}

function readEtfAmountTotalMap() {
  const file = etfAmountTotalPath();
  if (!fs.existsSync(file)) return new Map();
  const txt = fs.readFileSync(file, 'utf-8').trim();
  if (!txt) return new Map();
  const map = new Map();
  for (const line of txt.split('\n')) {
    if (!line) continue;
    try {
      const row = JSON.parse(line);
      if (!Array.isArray(row) || row.length < 2) continue;
      const day = String(row[0] || '');
      const total = Number(row[1]);
      const count = row.length >= 3 ? Number(row[2]) : null;
      if (!day || !Number.isFinite(total) || total <= 0) continue;
      map.set(day, { day, total, count: Number.isFinite(count) ? count : null });
    } catch (e) {
      void e;
    }
  }
  return map;
}

function pickEtfAmountTotal(map, day) {
  const d = String(day || '').trim();
  if (!d || !(map instanceof Map) || !map.size) return null;
  if (map.has(d)) return map.get(d);
  const keys = Array.from(map.keys()).sort();
  let pick = null;
  for (const k of keys) {
    if (k <= d) pick = k;
    else break;
  }
  return pick ? map.get(pick) : null;
}

function normalizeEtfTotalToWan(raw) {
  const v = Number(raw);
  if (!Number.isFinite(v) || v <= 0) return null;
  if (v > 1e10) return v / 10000;
  return v;
}

function appendEtfAmountTotalRow(day, total, count) {
  const d = String(day || '').trim();
  const t = Number(total);
  if (!d || !Number.isFinite(t) || t <= 0) return false;
  const map = readEtfAmountTotalMap();
  if (map.has(d)) return false;
  map.set(d, { day: d, total: t, count: Number.isFinite(Number(count)) ? Number(count) : null });
  const rows = Array.from(map.values())
    .sort((a, b) => String(a.day).localeCompare(String(b.day)))
    .map(v => JSON.stringify([v.day, v.total, v.count ?? null]));
  fs.writeFileSync(etfAmountTotalPath(), rows.join('\n') + '\n');
  return true;
}

async function refreshEtfAmountTotalViaPython(dayOverride) {
  const day = String(dayOverride || latestTradingDay());
  const obj = await execPythonJson(['scripts/etf_amount_total_sina.py', day], 60000);
  if (!obj || obj.ok !== true) return null;
  const d = String(obj.date || day);
  const total = Number(obj.total_amount);
  const count = Number(obj.count);
  if (!d || !Number.isFinite(total) || total <= 0) return null;
  appendEtfAmountTotalRow(d, total, Number.isFinite(count) ? count : null);
  return { day: d, total, count: Number.isFinite(count) ? count : null };
}

function latestTradingDay() {
  const parts = getBeijingParts();
  if (!parts) return new Date().toISOString().slice(0, 10);
  let base = parts.date;
  if (!isTradingDay(base)) {
    while (!isTradingDay(base)) {
      base = shiftBeijingDate(base, -1);
    }
  }
  const preMarket = !isMarketOpenNow() && !isAfterCloseNow();
  const baseWeekday = getBeijingWeekday(base);
  if (preMarket) base = shiftBeijingDate(base, baseWeekday === 1 ? -3 : -1);
  const useLocal = preMarket;
  const local = useLocal ? latestLocalTradingDayOnOrBefore(base) : null;
  return local || base;
}

function isTrustedTradingDayFile(file) {
  const base = path.basename(file || '');
  if (base.startsWith('archive-') && base.endsWith('.jsonl')) return true;
  if (base.startsWith('volume-') && base.endsWith('.jsonl')) return true;
  if (base.startsWith('overview-history-') && base.endsWith('.json')) return true;
  return false;
}

function latestLocalTradingDayOnOrBefore(maxDay) {
  if (!maxDay) return null;
  const maxKey = maxDay.replace(/-/g, '');
  const dir = path.join(__dirname, 'data');
  if (!fs.existsSync(dir)) return null;
  const files = fs.readdirSync(dir);
  let best = null;
  for (const f of files) {
    if (!isTrustedTradingDayFile(f)) continue;
    const full = path.join(dir, f);
    if (!fs.statSync(full).isFile()) continue;
    const d = parseDayFromFilename(f);
    if (!d) continue;
    if (!isWeekdayDate(d)) continue;
    const key = d.replace(/-/g, '');
    if (key > maxKey) continue;
    if (!best || key > best.replace(/-/g, '')) best = d;
  }
  return best;
}

// 模拟时间（用于测试），格式: { date: '2026-03-10', hour: 14, minute: 0 }
let mockTime = null;

// 构建传递给 Python 的环境变量选项
function getExecOptions() {
  const opts = { timeout: 180000, maxBuffer: 20 * 1024 * 1024, cwd: __dirname };
  if (mockTime && mockTime.date) {
    opts.env = {
      ...process.env,
      MOCK_TIME_DATE: mockTime.date,
      MOCK_TIME_HOUR: String(mockTime.hour),
      MOCK_TIME_MINUTE: String(mockTime.minute || 0)
    };
  }
  return opts;
}

function getBeijingParts() {
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    weekday: 'short',
    hour12: false
  });
  const parts = fmt.formatToParts(new Date());
  const map = {};
  parts.forEach((p) => {
    if (p.type !== 'literal') map[p.type] = p.value;
  });
  const date = `${map.year}-${map.month}-${map.day}`;
  const minutes = Number(map.hour) * 60 + Number(map.minute);
  const weekMap = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  const weekday = Object.prototype.hasOwnProperty.call(weekMap, map.weekday) ? weekMap[map.weekday] : null;
  return { date, minutes, weekday };
}

function getBeijingWeekday(dateStr) {
  if (!dateStr) return null;
  const dt = new Date(`${dateStr}T12:00:00+08:00`);
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    weekday: 'short'
  });
  const parts = fmt.formatToParts(dt);
  const map = {};
  parts.forEach((p) => {
    if (p.type !== 'literal') map[p.type] = p.value;
  });
  const weekMap = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  return Object.prototype.hasOwnProperty.call(weekMap, map.weekday) ? weekMap[map.weekday] : null;
}

function isTradingDay(dateStr) {
  const d = String(dateStr || '').trim();
  if (!d) return false;
  const weekday = getBeijingWeekday(d);
  if (weekday === 0 || weekday === 6) return false;
  const holidays = readHolidaySet();
  if (holidays.has(d)) return false;
  return true;
}

// 获取当前市场日期（非交易时段回退到上一交易日）
function getMarketDate() {
  const today = getBeijingParts().date;
  if (isTradingDay(today)) return today;
  return getPreviousTradingDay(today);
}

// 获取上一交易日
function getPreviousTradingDay(dateStr) {
  let d = dateStr;
  for (let i = 1; i <= 10; i++) {
    d = shiftBeijingDate(dateStr, -i);
    if (isTradingDay(d)) return d;
  }
  return null;
}

// 判断当前是否在交易时段
function isInTradingTime(parts) {
  if (!parts) return false;
  if (parts.weekday === 0 || parts.weekday === 6) return false;
  const m = parts.minutes;
  return (m >= 570 && m <= 690) || (m >= 780 && m <= 900);
}

function shiftBeijingDate(dateStr, days) {
  const d = new Date(`${dateStr}T00:00:00+08:00`);
  d.setDate(d.getDate() + days);
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  });
  return fmt.format(d);
}

function isWeekdayDate(dateStr) {
  return isTradingDay(dateStr);
}

function dateDiffDays(a, b) {
  if (!a || !b) return null;
  const da = new Date(`${a}T00:00:00+08:00`);
  const db = new Date(`${b}T00:00:00+08:00`);
  const diff = Math.floor((da.getTime() - db.getTime()) / 86400000);
  if (!Number.isFinite(diff)) return null;
  return diff;
}

function cacheJsonPath(prefix, day) {
  const d = day.replace(/-/g, '');
  const dir = path.join(__dirname, 'data');
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, `${prefix}-${d}.json`);
}

function normalizeSectorKey(list) {
  const arr = Array.isArray(list) ? list : String(list || '').split(',');
  const uniq = Array.from(new Set(arr.map(s => String(s || '').trim()).filter(Boolean)));
  uniq.sort();
  return uniq.join(',');
}

function sectorCacheFile(prefix, day, list, days) {
  const key = normalizeSectorKey(list);
  const hash = crypto.createHash('md5').update(key).digest('hex').slice(0, 10);
  return cacheJsonPath(`${prefix}-${days}-${hash}`, day);
}

function rotationSnapshotPath(day) {
  const d = day.replace(/-/g, '');
  return path.join(__dirname, 'data', `sector-rotation-${d}.json`);
}

function readRotationSnapshot(day) {
  const file = rotationSnapshotPath(day);
  if (!fs.existsSync(file)) return null;
  const txt = fs.readFileSync(file, 'utf-8').trim();
  return txt || null;
}

function findLatestRotationSnapshot() {
  const dir = path.join(__dirname, 'data');
  if (!fs.existsSync(dir)) return null;
  const files = fs.readdirSync(dir).filter(f => /^sector-rotation-\d{8}\.json$/.test(f));
  if (!files.length) return null;
  files.sort();
  return path.join(dir, files[files.length - 1]);
}

function rotationSequencePath(day) {
  const d = day.replace(/-/g, '');
  return path.join(__dirname, 'data', `rotation-sequence-${d}.json`);
}

function readRotationSequence(day) {
  const file = rotationSequencePath(day);
  if (!fs.existsSync(file)) return null;
  const txt = fs.readFileSync(file, 'utf-8').trim();
  return txt || null;
}

function readLatestRotationSequence() {
  const dir = path.join(__dirname, 'data');
  if (!fs.existsSync(dir)) return null;
  const files = fs.readdirSync(dir).filter(f => /^rotation-sequence-\d{8}\.json$/.test(f));
  if (!files.length) return null;
  files.sort();
  const file = path.join(dir, files[files.length - 1]);
  const txt = fs.readFileSync(file, 'utf-8').trim();
  return txt || null;
}

function intradayRotationPath(day, view) {
  const d = day.replace(/-/g, '');
  const tag = view === 'detail' ? 'detail' : 'summary';
  return path.join(__dirname, 'data', `intraday-rotation-${tag}-${d}.json`);
}

function findLatestSectorHistoryCache(day) {
  const d = day.replace(/-/g, '');
  const dir = path.join(__dirname, 'data');
  if (!fs.existsSync(dir)) return null;
  const files = fs.readdirSync(dir).filter(f => f.startsWith('sector-history-') && f.endsWith(`-${d}.json`));
  if (!files.length) return null;
  files.sort();
  const file = path.join(dir, files[files.length - 1]);
  return readJsonCache(file);
}

function readJsonCache(file) {
  if (!fs.existsSync(file)) return null;
  const txt = fs.readFileSync(file, 'utf-8').trim();
  return txt || null;
}

function parseDayFromFilename(file) {
  const base = path.basename(file || '');
  const m2 = base.match(/(\d{4})-(\d{2})-(\d{2})/);
  if (m2) return `${m2[1]}-${m2[2]}-${m2[3]}`;
  const m = base.match(/(\d{8})/);
  if (!m) return null;
  return `${m[1].slice(0, 4)}-${m[1].slice(4, 6)}-${m[1].slice(6, 8)}`;
}

function normalizeDateStr(raw) {
  const txt = String(raw || '').trim();
  if (!txt) return '';
  if (/^\d{4}-\d{2}-\d{2}$/.test(txt)) return txt;
  if (/^\d{8}$/.test(txt)) return `${txt.slice(0, 4)}-${txt.slice(4, 6)}-${txt.slice(6, 8)}`;
  return txt;
}

function findLatestCacheFileOnOrBefore(prefix, day) {
  const dir = path.join(__dirname, 'data');
  if (!fs.existsSync(dir)) return null;
  const max = String(day || '').replace(/-/g, '');
  const files = fs.readdirSync(dir).filter(f => f.startsWith(`${prefix}-`) && f.endsWith('.json'));
  if (!files.length) return null;
  let best = null;
  let bestKey = null;
  for (const f of files) {
    const d = parseDayFromFilename(f);
    if (!d) continue;
    const key = d.replace(/-/g, '');
    if (max && key > max) continue;
    if (!bestKey || key > bestKey) {
      bestKey = key;
      best = path.join(dir, f);
    }
  }
  return best;
}

function trimHistoryToDay(history, day) {
  if (!history || !day) return history;
  const out = {};
  Object.entries(history).forEach(([name, arr]) => {
    if (!Array.isArray(arr)) return;
    out[name] = arr.filter((r) => {
      const d = normalizeDateStr(r?.date);
      return !d || d <= day;
    });
  });
  return out;
}

function normalizeHistoryPayloadToDay(payload, day) {
  if (!payload || !day) return payload;
  const history = trimHistoryToDay(payload.history || {}, day);
  let latest = null;
  Object.values(history).forEach((arr) => {
    if (!Array.isArray(arr) || !arr.length) return;
    const d = normalizeDateStr(arr[arr.length - 1]?.date);
    if (d && (!latest || d > latest)) latest = d;
  });
  return {
    ...payload,
    day: payload.day || latest || day,
    latest_date: payload.latest_date || latest || null,
    history
  };
}

function isHistoryCacheFile(file) {
  const base = path.basename(file || '');
  return [
    'overview-history-',
    'sector-history-',
    'sector-lifecycle-',
    'sector-rotation-',
    'rotation-sequence-',
    'market-breadth-',
    'intraday-rotation-',
    'sector-analysis-ai-'
  ].some(p => base.startsWith(p));
}

function writeJsonCache(file, jsonText) {
  if (!jsonText) return;
  if (file && isHistoryCacheFile(file) && process.env.ALLOW_HISTORY_WRITE !== '1') {
    const day = parseDayFromFilename(file);
    const latest = latestTradingDay();
    if (day && latest && day < latest && fs.existsSync(file)) return;
  }
  fs.writeFileSync(file, jsonText);
}

function findLatestCacheFile(prefix) {
  const dir = path.join(__dirname, 'data');
  if (!fs.existsSync(dir)) return null;
  const files = fs.readdirSync(dir).filter(f => f.startsWith(`${prefix}-`) && f.endsWith('.json'));
  if (!files.length) return null;
  files.sort();
  return path.join(dir, files[files.length - 1]);
}

function warmupSectorCache(cmd, list, days, cacheFile) {
  const cached = readJsonCache(cacheFile);
  if (cached) return 'cached';
  execFile('python3', ['fetch_sector_data.py', cmd, list, String(days)], getExecOptions(), (err, stdout) => {
    if (err) return;
    const out = (stdout || '').trim();
    if (out && isJsonText(out)) writeJsonCache(cacheFile, out);
  });
  return 'queued';
}

function isJsonText(text) {
  try {
    JSON.parse(text);
    return true;
  } catch (e) {
    return false;
  }
}

function readJsonFileSafe(file) {
  if (!file || !fs.existsSync(file)) return null;
  try {
    const txt = fs.readFileSync(file, 'utf-8').trim();
    if (!txt) return null;
    return JSON.parse(txt);
  } catch (e) {
    return null;
  }
}

function readHolidaySet() {
  const cfg = readJsonFileSafe(HOLIDAY_FILE);
  const list = Array.isArray(cfg?.holidays) ? cfg.holidays : [];
  return new Set(list.map(s => String(s || '').trim()).filter(Boolean));
}

function readSectorProxyConfig() {
  const base = readJsonFileSafe(PROXY_FILE) || {};
  const variants = base.variants && typeof base.variants === 'object' ? base.variants : {};
  const defaultVariant = String(base.default_variant || 'etf').trim() || 'etf';
  return {
    ...base,
    variants,
    default_variant: defaultVariant,
    force_etf: !!base.force_etf
  };
}

function todayStr() {
  return (new Date()).toISOString().slice(0, 10);
}

function normalizeDateParam(raw) {
  const date = String(raw || '').trim();
  if (!date) return todayStr();
  return /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : null;
}

function normalizeMonthParam(raw) {
  const month = String(raw || '').trim();
  if (!month) return null;
  return /^\d{4}-\d{2}$/.test(month) ? month : null;
}

function newsFilePath(day) {
  // 新闻数据路径已迁移到 data/news/
  return path.join(__dirname, 'data/news', `${day}.json`);
}

function toSentimentLabel(v) {
  if (v === 1 || v === '1') return '利好';
  if (v === -1 || v === '-1') return '利空';
  return '中性';
}

function normalizeNewsItem(item, idx) {
  const classify = item?.classify && typeof item.classify === 'object' ? item.classify : {};
  const sentiment = Number(classify.sentiment);
  const sentimentVal = Number.isFinite(sentiment) ? sentiment : 0;
  const relatedStocksRaw = Array.isArray(item?.related_stocks) ? item.related_stocks : [];
  const relatedStocks = [];
  const stockSeen = new Set();
  relatedStocksRaw.forEach((stock) => {
    const val = String(stock || '').trim();
    if (!val || stockSeen.has(val)) return;
    stockSeen.add(val);
    relatedStocks.push(val);
  });
  const combinedText = `${item?.title || ''} ${item?.content || item?.summary || ''}`;
  let country = String(item?.country || '').trim();
  if (!country) {
    if (combinedText.includes('美国') || combinedText.includes('美联储') || combinedText.includes('美股')) country = '美国';
    else if (combinedText.includes('日本') || combinedText.includes('日经') || combinedText.includes('日本央行')) country = '日本';
    else country = '中国';
  }
  const out = {
    news_id: item?.news_id || item?.id || `news-${idx + 1}`,
    title: item?.title || '',
    content: item?.content || item?.summary || '',
    source: item?.source || '',
    url: item?.url || item?.source_url || '',
    publish_time: item?.publish_time || item?.crawl_time || item?.fetch_time || '',
    related_stocks: relatedStocks,
    country,
    classify: {
      type: classify?.type || null,
      sector: classify?.sector || null,
      sentiment: sentimentVal,
      level: classify?.level || null
    }
  };
  return out;
}

function readNewsByDate(day) {
  const file = newsFilePath(day);
  const json = readJsonFileSafe(file);
  let list = [];
  if (Array.isArray(json)) {
    list = json;
  } else if (json && typeof json === 'object' && Array.isArray(json.news)) {
    list = json.news;
  }
  if (!Array.isArray(list)) return [];
  return list.map((item, idx) => normalizeNewsItem(item, idx));
}

function buildNewsHeat(items) {
  const byType = {};
  const bySector = {};
  const bySentiment = { '利好': 0, '中性': 0, '利空': 0 };
  const byLevel = {};
  // 按类型分组的情绪统计
  const byTypeSentiment = {};
  // 按行业分组的情绪统计
  const bySectorSentiment = {};
  (items || []).forEach((item) => {
    const type = item?.classify?.type;
    const sector = item?.classify?.sector;
    const level = item?.classify?.level;
    const sentimentLabel = toSentimentLabel(item?.classify?.sentiment);
    if (type) {
      byType[type] = (byType[type] || 0) + 1;
      // 按类型统计情绪
      if (!byTypeSentiment[type]) {
        byTypeSentiment[type] = { '利好': 0, '中性': 0, '利空': 0 };
      }
      byTypeSentiment[type][sentimentLabel] = (byTypeSentiment[type][sentimentLabel] || 0) + 1;
    }
    if (sector) {
      bySector[sector] = (bySector[sector] || 0) + 1;
      // 按行业统计情绪
      if (!bySectorSentiment[sector]) {
        bySectorSentiment[sector] = { '利好': 0, '中性': 0, '利空': 0 };
      }
      bySectorSentiment[sector][sentimentLabel] = (bySectorSentiment[sector][sentimentLabel] || 0) + 1;
    }
    bySentiment[sentimentLabel] = (bySentiment[sentimentLabel] || 0) + 1;
    if (level) byLevel[level] = (byLevel[level] || 0) + 1;
  });
  return { byType, bySector, bySentiment, byLevel, byTypeSentiment, bySectorSentiment };
}

function buildSignalsFromBacktest() {
  const file = path.join(__dirname, 'data', 'backtest_false_kill.json');
  const json = readJsonFileSafe(file);
  const sectors = json?.sectors;
  if (!sectors || typeof sectors !== 'object') return [];

  return Object.entries(sectors).map(([sector, sectorStats]) => {
    const actionStats = sectorStats?.action_stats || {};
    const longCount = Number(actionStats?.long?.count || 0);
    const falseKillCount = Number(actionStats?.false_kill?.count || 0);
    const neutralCount = Number(actionStats?.neutral?.count || 0);
    const avoidCount = Number(actionStats?.avoid?.count || 0);

    // Keep API output in required domain: long / false_kill / neutral
    const candidates = [
      { signal: 'long', count: longCount },
      { signal: 'false_kill', count: falseKillCount },
      { signal: 'neutral', count: neutralCount + avoidCount }
    ];
    candidates.sort((a, b) => b.count - a.count);

    return {
      sector,
      signal: candidates[0]?.signal || 'neutral'
    };
  });
}

function loadLatestBreadthRecord() {
  const dir = path.join(__dirname, 'data');
  const directCandidates = [
    path.join(dir, 'market-breadth.json'),
    path.join(dir, 'market_breadth.json')
  ];

  for (const file of directCandidates) {
    const json = readJsonFileSafe(file);
    if (!json) continue;
    if (Array.isArray(json.records) && json.records.length > 0) {
      return json.records[json.records.length - 1];
    }
    if (typeof json.up === 'number' || typeof json.down === 'number' || typeof json.total === 'number') {
      return json;
    }
  }

  if (!fs.existsSync(dir)) return null;
  const files = fs.readdirSync(dir)
    .filter(f => f.startsWith('market-breadth-') && f.endsWith('.json'))
    .sort();
  if (!files.length) return null;
  const latest = readJsonFileSafe(path.join(dir, files[files.length - 1]));
  return latest || null;
}

function loadBreadthFromArchive(day) {
  if (!day) return null;
  const file = path.join(__dirname, 'data', `archive-${day.replace(/-/g, '')}.jsonl`);
  if (!fs.existsSync(file)) return null;
  const txt = fs.readFileSync(file, 'utf-8').trim();
  if (!txt) return null;
  const line = txt.split('\n').slice(-1)[0];
  if (!line) return null;
  try {
    const row = JSON.parse(line);
    if (!Array.isArray(row) || row.length < 24) return null;
    const up = Number(row[22] || 0);
    const down = Number(row[23] || 0);
    if (!Number.isFinite(up) || !Number.isFinite(down)) return null;
    return { day, up, down, flat: 0, total: up + down };
  } catch (e) {
    return null;
  }
}

const WATCH_FILE = path.join(__dirname, 'data', 'sector-watch.json');
const PROFILE_FILE = path.join(__dirname, 'data', 'sector-profile.json');
const DEFAULT_WATCH_LIST = ['云计算', '半导体', '有色金属'];
// 分类完全自定义，不限制名称和数量
function normalizeWatchList(list) {
  if (!Array.isArray(list)) return [];
  const out = [];
  const seen = new Set();
  list.forEach((s) => {
    const v = String(s || '').trim();
    if (!v || seen.has(v)) return;
    seen.add(v);
    out.push(v);
  });
  return out;
}

function writeWatchList(list) {
  const dir = path.join(__dirname, 'data');
  fs.mkdirSync(dir, { recursive: true });
  const out = normalizeWatchList(list);
  fs.writeFileSync(WATCH_FILE, JSON.stringify({ watch_list: out }));
  return out;
}

function readWatchList() {
  const dir = path.join(__dirname, 'data');
  fs.mkdirSync(dir, { recursive: true });
  if (!fs.existsSync(WATCH_FILE)) return writeWatchList(DEFAULT_WATCH_LIST);
  const txt = fs.readFileSync(WATCH_FILE, 'utf-8').trim();
  if (!txt) return writeWatchList(DEFAULT_WATCH_LIST);
  try {
    const json = JSON.parse(txt);
    const list = normalizeWatchList(json?.watch_list || json?.list || json?.sectors);
    if (!list.length) return writeWatchList(DEFAULT_WATCH_LIST);
    return list;
  } catch (e) {
    return writeWatchList(DEFAULT_WATCH_LIST);
  }
}

function normalizeProfileGroups(groups) {
  const out = {};
  if (!groups || typeof groups !== 'object') return out;
  Object.entries(groups).forEach(([k, v]) => {
    const name = String(k || '').trim();
    const group = String(v || '').trim();
    if (!name || !group) return;
    // 不限制分类名称，任何非空字符串都接受
    out[name] = group;
  });
  return out;
}

function writeSectorProfile(groups, customGroups, etfBindings) {
  const dir = path.join(__dirname, 'data');
  fs.mkdirSync(dir, { recursive: true });
  const normalized = normalizeProfileGroups(groups);
  // 自定义分类列表：去重、过滤空值
  const normalizedCustomGroups = Array.isArray(customGroups)
    ? [...new Set(customGroups.map(g => String(g || '').trim()).filter(Boolean))]
    : [];
  // ETF绑定：验证格式
  const normalizedEtfBindings = {};
  if (etfBindings && typeof etfBindings === 'object') {
    Object.entries(etfBindings).forEach(([k, v]) => {
      const name = String(k || '').trim();
      const code = String(v || '').trim();
      if (!name || !code) return;
      // 简单格式验证：sh/sz + 6位数字
      if (!/^(sh|sz)\d{6}$/.test(code)) return;
      normalizedEtfBindings[name] = code;
    });
  }
  const payload = {
    groups: normalized,
    custom_groups: normalizedCustomGroups,
    etf_bindings: normalizedEtfBindings,
    updated_at: new Date().toISOString()
  };
  fs.writeFileSync(PROFILE_FILE, JSON.stringify(payload, null, 2));
  return payload;
}

function readSectorProfile() {
  const dir = path.join(__dirname, 'data');
  fs.mkdirSync(dir, { recursive: true });
  if (!fs.existsSync(PROFILE_FILE)) return writeSectorProfile({}, [], {});
  const json = readJsonFileSafe(PROFILE_FILE);
  if (!json || typeof json !== 'object') return writeSectorProfile({}, [], {});
  const groups = normalizeProfileGroups(json.groups || json);
  // 向后兼容：如果没有 custom_groups，返回空数组
  const customGroups = Array.isArray(json.custom_groups) ? json.custom_groups : [];
  // 向后兼容：如果没有 etf_bindings，返回空对象
  const etfBindings = json.etf_bindings || {};
  const updated = json.updated_at || new Date().toISOString();
  return { groups, custom_groups: customGroups, etf_bindings: etfBindings, updated_at: updated };
}

// 更新 sector-proxy.json 的 ETF 映射
function updateSectorProxyEtfBindings(etfBindings) {
  try {
    const cfg = readJsonFileSafe(PROXY_FILE) || {};
    if (!cfg.variants) cfg.variants = {};
    if (!cfg.variants.etf) cfg.variants.etf = {};
    // 合并新的 ETF 绑定
    Object.entries(etfBindings).forEach(([name, code]) => {
      if (name && code && /^(sh|sz)\d{6}$/.test(code)) {
        cfg.variants.etf[name] = code;
      }
    });
    cfg.updated_at = new Date().toISOString();
    fs.writeFileSync(PROXY_FILE, JSON.stringify(cfg, null, 2));
    return true;
  } catch (e) {
    console.error('更新 sector-proxy.json 失败:', e);
    return false;
  }
}

function pickMinutePct(series) {
  if (!Array.isArray(series) || !series.length) return null;
  const first = series[0];
  const last = series[series.length - 1];
  const base = Number(first?.open || first?.close);
  const end = Number(last?.close || last?.open);
  if (!isNum(base) || !isNum(end) || base === 0) return null;
  return +(((end - base) / base) * 100).toFixed(2);
}

function buildIntradayBars(histPayload, lifePayload, profileGroups, view) {
  const rawWatch = Array.isArray(histPayload?.watch) ? histPayload.watch : [];
  const fallbackWatch = Array.isArray(lifePayload?.watch) ? lifePayload.watch : readWatchList();
  const watch = rawWatch.length ? rawWatch : fallbackWatch;
  const minutes = histPayload?.minute || {};
  const history = histPayload?.history || {};
  const items = Array.isArray(lifePayload?.items) ? lifePayload.items : [];
  const heatMap = new Map();
  items.forEach((it) => {
    const name = String(it?.['板块名称'] || '').trim();
    const ch = it?.['指标数据']?.['Amount_Share_Change'];
    if (name && isNum(Number(ch))) heatMap.set(name, Number(ch));
  });
  const groupMap = profileGroups || {};
  const rows = [];
  watch.forEach((name) => {
    const series = minutes?.[name]?.series || [];
    const todayPct = pickMinutePct(series);
    const hist = history?.[name] || [];
    const latestPct = hist.length ? Number(hist[hist.length - 1]?.pct) : null;
    const pct = isNum(todayPct) ? todayPct : (isNum(latestPct) ? latestPct : null);
    const heat = heatMap.has(name) ? heatMap.get(name) : null;
    let group = String(groupMap[name] || '').trim();
    // 视图与缺省分组处理：未分类也纳入展示，避免空图
    const GROUP_OPTIONS = ['资源', '科技', '金融', '消费', '医药', '未分类'];
    if (view === 'detail') {
      if (!GROUP_OPTIONS.includes(group)) group = '未分类';
    } else {
      if (group === '资源') group = '资源';
      else if (group === '硬件' || group === '软件') group = '科技';
      else {
        // 简单启发式：根据名称猜测分组，否则归入未分类
        if (/有色|煤炭|电力|钢铁|稀土|石油|化工/.test(name)) group = '资源';
        else if (/半导体|芯片|硬件|设备|通讯设备/.test(name)) group = '科技';
        else if (/云计算|软件|AI|人工智能|数字化|数据/.test(name)) group = '科技';
        else group = '未分类';
      }
    }
    rows.push({ name, group, pct, heat });
  });
  const groups = {};
  rows.forEach((r) => {
    groups[r.group] = groups[r.group] || [];
    groups[r.group].push(r);
  });
  const bars = Object.entries(groups).map(([group, list]) => {
    const pctVals = list.map(i => i.pct).filter(v => isNum(v));
    const heatVals = list.map(i => i.heat).filter(v => isNum(v));
    const pct = pctVals.length ? +(pctVals.reduce((a, b) => a + b, 0) / pctVals.length).toFixed(2) : null;
    const heat = heatVals.length ? +(heatVals.reduce((a, b) => a + b, 0) / heatVals.length).toFixed(3) : null;
    const top = list
      .filter(i => isNum(i.pct))
      .sort((a, b) => b.pct - a.pct)
      .slice(0, 3)
      .map(i => ({ name: i.name, pct: i.pct }));
    return { group, today_pct: pct, heat_change: heat, top };
  });
  bars.sort((a, b) => {
    if (!isNum(a.today_pct) && !isNum(b.today_pct)) return 0;
    if (!isNum(a.today_pct)) return 1;
    if (!isNum(b.today_pct)) return -1;
    const diff = b.today_pct - a.today_pct;
    if (Math.abs(diff) > 0.2) return diff;
    if (!isNum(a.heat_change) && !isNum(b.heat_change)) return 0;
    if (!isNum(a.heat_change)) return 1;
    if (!isNum(b.heat_change)) return -1;
    return b.heat_change - a.heat_change;
  });
  const leader = bars.length ? bars[0] : null;
  const signal = leader ? `${leader.group}偏强` : '盘中结构暂无结论';
  const reason = [];
  if (leader && isNum(leader.today_pct)) reason.push(`均值涨跌 ${leader.today_pct}%`);
  if (leader && isNum(leader.heat_change)) reason.push(`热度变化 ${leader.heat_change}`);
  return { bars, signal, reason };
}

const WATCH_STOCKS_FILE = path.join(__dirname, 'data', 'watch_stocks.json');
const CALENDAR_FILE = path.join(__dirname, 'data', 'calendar.json');

function normalizeStockCode(code) {
  const v = String(code || '').trim();
  if (!v) return '';
  return v.toUpperCase();
}

function readWatchStocks() {
  const dir = path.join(__dirname, 'data');
  fs.mkdirSync(dir, { recursive: true });
  if (!fs.existsSync(WATCH_STOCKS_FILE)) {
    fs.writeFileSync(WATCH_STOCKS_FILE, JSON.stringify({ watch_stocks: [] }, null, 2));
    return [];
  }
  const json = readJsonFileSafe(WATCH_STOCKS_FILE);
  const list = Array.isArray(json?.watch_stocks) ? json.watch_stocks : (Array.isArray(json) ? json : []);
  const out = [];
  const seen = new Set();
  list.forEach((item) => {
    const code = normalizeStockCode(item);
    if (!code || seen.has(code)) return;
    seen.add(code);
    out.push(code);
  });
  return out;
}

function writeWatchStocks(list) {
  const dir = path.join(__dirname, 'data');
  fs.mkdirSync(dir, { recursive: true });
  const out = [];
  const seen = new Set();
  (Array.isArray(list) ? list : []).forEach((item) => {
    const code = normalizeStockCode(item);
    if (!code || seen.has(code)) return;
    seen.add(code);
    out.push(code);
  });
  fs.writeFileSync(
    WATCH_STOCKS_FILE,
    JSON.stringify({ watch_stocks: out, updated_at: new Date().toISOString() }, null, 2)
  );
  return out;
}

function readCalendarEvents() {
  const dir = path.join(__dirname, 'data');
  fs.mkdirSync(dir, { recursive: true });
  if (!fs.existsSync(CALENDAR_FILE)) {
    fs.writeFileSync(CALENDAR_FILE, JSON.stringify({ events: [] }, null, 2));
    return [];
  }
  const json = readJsonFileSafe(CALENDAR_FILE);
  if (Array.isArray(json)) return json;
  if (Array.isArray(json?.events)) return json.events;
  return [];
}

function readMinuteFile(file) {
  if (!fs.existsSync(file)) return { arr: [], lastTime: null };
  const txt = fs.readFileSync(file, 'utf-8').trim();
  if (!txt) return { arr: [], lastTime: null };
  const lines = txt.split('\n');
  const arr = lines.map((line) => {
    const row = JSON.parse(line);
    return { time: row[0], open: row[1], close: row[2] };
  });
  const lastTime = arr.length ? arr[arr.length - 1].time : null;
  return { arr, lastTime };
}

function prevCloseFromMinuteFile(day, code) {
  if (!day || !code) return null;
  const pickLast = (arr) => {
    if (!arr || !arr.length) return null;
    const last = arr[arr.length - 1];
    return pickNum(toNumber(last?.close), toNumber(last?.open));
  };
  const main = readMinuteFile(minuteFilePath(day, code)).arr;
  const runtime = readMinuteFile(runtimeMinuteFilePath(day, code)).arr;
  const merged = mergeMinuteSeries(main, runtime);
  const out = pickLast(merged);
  return isNum(out) ? out : null;
}

function mergeMinuteSeries(...seriesList) {
  const map = new Map();
  seriesList.forEach((series) => {
    (series || []).forEach((p) => {
      if (!p?.time) return;
      map.set(p.time, p);
    });
  });
  return Array.from(map.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([, p]) => p);
}

function readVolumeFile(file) {
  if (!fs.existsSync(file)) return [];
  const txt = fs.readFileSync(file, 'utf-8').trim();
  if (!txt) return [];
  return txt.split('\n').map((line) => {
    const row = JSON.parse(line);
    return { time: row[0], volume: row[1] };
  });
}

function readArchiveVolumeSeries(day) {
  if (!day) return [];
  const file = path.join(__dirname, 'data', `archive-${day.replace(/-/g, '')}.jsonl`);
  if (!fs.existsSync(file)) return [];
  const txt = fs.readFileSync(file, 'utf-8').trim();
  if (!txt) return [];
  const map = new Map();
  const lines = txt.split('\n');
  for (const line of lines) {
    if (!line) continue;
    const row = JSON.parse(line);
    if (!Array.isArray(row) || row.length < 22) continue;
    const ts = row[0];
    const vol = row[21];
    if (!isNum(ts) || !isNum(vol)) continue;
    let key = minuteKeyBeijing(new Date(ts));
    if (!isTradingMinute(key)) {
      const n = minuteToNumber(key);
      if (n != null && n > 900) key = '15:00';
      else continue;
    }
    map.set(key, vol);
  }
  if (!map.size) return [];
  return Array.from(map.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([time, volume]) => ({ time, volume }));
}

function readVolumeSeries(day) {
  if (!day) return [];
  const file = volumeFilePath(day);
  const series = readVolumeFile(file).filter(p => isTradingMinute(p?.time));
  const arch = readArchiveVolumeSeries(day);
  const isToday = day === latestTradingDay();
  if (isToday && series.length) return series;
  if (!arch.length) return series;
  const map = new Map();
  series.forEach((p) => {
    if (p?.time && isNum(p.volume)) map.set(p.time, p.volume);
  });
  arch.forEach((p) => {
    if (p?.time && isNum(p.volume)) map.set(p.time, p.volume);
  });
  const out = Array.from(map.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([time, volume]) => ({ time, volume }));
  if (out.length > series.length) {
    const rows = out.map(p => JSON.stringify([p.time, p.volume])).join('\n');
    fs.writeFileSync(file, rows + '\n');
  }
  return out;
}

function appendVolumePoint(file, time, volume) {
  if (!isNum(volume) || !time) return;

  // 读取现有数据，检查时间点是否已存在
  if (fs.existsSync(file)) {
    const txt = fs.readFileSync(file, 'utf-8').trim();
    if (txt) {
      const lines = txt.split('\n');
      for (let i = lines.length - 1; i >= Math.max(0, lines.length - 5); i--) {
        try {
          const row = JSON.parse(lines[i]);
          if (row && row[0] === time) {
            // 时间点已存在，更新数据（如果成交额更大）
            if (volume > row[1]) {
              lines[i] = JSON.stringify([time, volume]);
              fs.writeFileSync(file, lines.join('\n') + '\n');
            }
            return;
          }
        } catch (e) {
          // 忽略解析错误
        }
      }
    }
  }

  // 时间点不存在，追加新数据
  fs.appendFileSync(file, JSON.stringify([time, volume]) + '\n');
}

function hasTradingPoint(arr) {
  if (!arr || !arr.length) return false;
  for (const p of arr) {
    if (isTradingMinute(timeToMinuteKey(p.time))) return true;
  }
  return false;
}

function isMarketOpenNow() {
  const parts = getBeijingParts();
  if (!parts) return false;
  if (!isTradingDay(parts.date)) return false;
  const minutes = parts.minutes;
  const morning = minutes >= 570 && minutes <= 690;
  const afternoon = minutes >= 780 && minutes <= 900;
  return morning || afternoon;
}

function isAfterCloseNow() {
  const parts = getBeijingParts();
  if (!parts) return false;
  if (!isTradingDay(parts.date)) return false;
  const minutes = parts.minutes;
  // 下午收盘后：15:00之后（900分钟）
  return minutes >= 900;
}

// 判断是否在午休时间（11:30-13:00）
function isLunchBreakNow() {
  const parts = getBeijingParts();
  if (!parts) return false;
  if (!isTradingDay(parts.date)) return false;
  const minutes = parts.minutes;
  // 午休：11:30-13:00（690-780分钟）
  return minutes >= 690 && minutes < 780;
}

// 判断是否在交易日内（9:30-15:00，含午休）
function isTradingDaySession() {
  const parts = getBeijingParts();
  if (!parts) return false;
  if (!isTradingDay(parts.date)) return false;
  const minutes = parts.minutes;
  return minutes >= 570 && minutes <= 900; // 9:30-15:00
}

function buildVolumeFromArchive(day) {
  if (!day) return false;
  const file = path.join(__dirname, 'data', `archive-${day.replace(/-/g, '')}.jsonl`);
  if (!fs.existsSync(file)) return false;
  const target = volumeFilePath(day);
  const latest = latestTradingDay();
  if (latest && day < latest && fs.existsSync(target) && process.env.ALLOW_HISTORY_WRITE !== '1') return true;
  const txt = fs.readFileSync(file, 'utf-8').trim();
  if (!txt) return false;
  const map = new Map();
  const lines = txt.split('\n');
  for (const line of lines) {
    if (!line) continue;
    const row = JSON.parse(line);
    if (!Array.isArray(row) || row.length < 22) continue;
    const ts = row[0];
    const vol = row[21];
    if (!isNum(ts) || !isNum(vol)) continue;
    let key = minuteKeyBeijing(new Date(ts));
    if (!isTradingMinute(key)) {
      const n = minuteToNumber(key);
      if (n != null && n > 900) key = '15:00';
      else continue;
    }
    map.set(key, vol);
  }
  if (!map.size) return false;
  const out = [];
  const keys = Array.from(map.keys()).sort();
  for (const k of keys) {
    out.push(JSON.stringify([k, map.get(k)]));
  }
  if (!out.length) return false;
  fs.writeFileSync(target, out.join('\n') + '\n');
  return true;
}

function ensureVolumeFile(day) {
  if (!day) return false;
  const file = volumeFilePath(day);
  if (fs.existsSync(file)) {
    const txt = fs.readFileSync(file, 'utf-8').trim();
    if (txt) {
      const arr = readVolumeFile(file);
      if (hasTradingPoint(arr) && arr.length >= 30) return true;
    }
  }
  return buildVolumeFromArchive(day);
}

function isUsableVolumeDay(day) {
  if (!day) return false;
  const file = volumeFilePath(day);
  if (!fs.existsSync(file)) {
    buildVolumeFromArchive(day);
  }
  if (!fs.existsSync(file)) return false;
  const arr = readVolumeFile(file);
  return hasTradingPoint(arr) && arr.length >= 30;
}

function findPreviousTradingDay(day) {
  if (!day) return null;
  const currentDayStr = day.replace(/-/g, '');
  const dir = path.join(__dirname, 'data');
  if (!fs.existsSync(dir)) return null;
  
  // Look for volume-*.jsonl files first
  const files = fs.readdirSync(dir)
    .filter(f => f.startsWith('volume-') && f.endsWith('.jsonl'))
    .map(f => {
      const m = f.match(/volume-(\d{8})\.jsonl/);
      return m ? m[1] : null;
    })
    .filter(d => d && d < currentDayStr)
    .sort()
    .reverse();
    
  if (files.length > 0) {
    const d = files[0];
    return `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)}`;
  }
  
  // Fallback to archive-*.jsonl if no volume files found
  const archives = fs.readdirSync(dir)
    .filter(f => f.startsWith('archive-') && f.endsWith('.jsonl'))
    .map(f => {
      const m = f.match(/archive-(\d{8})\.jsonl/);
      return m ? m[1] : null;
    })
    .filter(d => d && d < currentDayStr)
    .sort()
    .reverse();

  if (archives.length > 0) {
    const d = archives[0];
    return `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)}`;
  }

  return null;
}

function buildVolumeCompare(day, volume) {
  const marketOpen = isMarketOpenNow();
  const nowTime = marketOpen ? minuteKeyBeijing(new Date()) : '15:00';
  if (day && marketOpen) appendVolumePoint(volumeFilePath(day), nowTime, volume);

  const ydayStrict = day ? findPreviousTradingDay(day) : null;
  const yday = ydayStrict;

  // 获取昨日全天成交额（优先使用日线数据）
  let yVolFullDay = null;

  // 1. 优先从日线数据文件读取
  try {
    const amountDailyFile = path.join(__dirname, 'data', 'market', 'market-amount-daily.jsonl');
    if (fs.existsSync(amountDailyFile)) {
      const txt = fs.readFileSync(amountDailyFile, 'utf8').trim();
      const lines = txt.split('\n');
      if (lines.length > 0) {
        // 找到昨日或最接近的日期
        for (let i = lines.length - 1; i >= 0; i--) {
          const row = JSON.parse(lines[i]);
          const rowDate = row[0];  // 日期
          const rowAmount = row[1];  // 总成交额（元）

          if (rowDate < day) {
            yVolFullDay = rowAmount / 10000;  // 转换为万元
            break;
          }
        }
      }
    }
  } catch (e) {
    // 忽略错误，继续使用备用方法
  }

  // 2. 备用：从分时文件的15:00数据读取
  if (!isNum(yVolFullDay) && yday) {
    ensureVolumeFile(yday);
    const yArr = readVolumeSeries(yday);
    if (yArr.length > 0) {
      const yLastPoint = yArr[yArr.length - 1];
      if (yLastPoint && isNum(yLastPoint.volume) && yLastPoint.volume > 0) {
        yVolFullDay = yLastPoint.volume;  // 使用昨日15:00的成交额
      }
    }
  }

  // 计算预估成交额（交易时间内）或实际成交额（收盘后）
  let estimatedVolume = null;
  let lastMinuteDelta = null;

  if (isNum(volume) && volume > 0) {
    const volumeFile = volumeFilePath(day);
    if (fs.existsSync(volumeFile)) {
      const arr = readVolumeFile(volumeFile);

      // 去重数据（按时间）
      const uniqueMap = new Map();
      for (const p of arr) {
        if (!p || !isNum(p.volume)) continue;
        // 只保留每个时间点的最大成交额
        const existing = uniqueMap.get(p.time);
        if (!existing || p.volume > existing.volume) {
          uniqueMap.set(p.time, p);
        }
      }
      const uniqueArr = Array.from(uniqueMap.values()).sort((a, b) => a.time.localeCompare(b.time));

      // 检查是否已收盘（有15:00的数据）
      const hasClosed = uniqueArr.some(p => p.time === '15:00');

      if (hasClosed) {
        // 收盘后，使用实际全天成交额
        const closePoint = uniqueArr.find(p => p.time === '15:00');
        if (closePoint && isNum(closePoint.volume)) {
          estimatedVolume = closePoint.volume;
        }
      } else if (marketOpen && uniqueArr.length >= 2) {
        // 交易时间内，计算预估成交额
        const lastPoint = uniqueArr[uniqueArr.length - 1];
        const prevPoint = uniqueArr[uniqueArr.length - 2];

        if (lastPoint && prevPoint && isNum(lastPoint.volume) && isNum(prevPoint.volume)) {
          lastMinuteDelta = lastPoint.volume - prevPoint.volume;

          // 如果最后一分钟增量 <= 0，使用最近5分钟的平均增量
          if (lastMinuteDelta <= 0 && uniqueArr.length >= 6) {
            const recentPoints = uniqueArr.slice(-6);  // 最近6个点（5分钟）
            let totalDelta = 0;
            let validPoints = 0;

            for (let i = 1; i < recentPoints.length; i++) {
              const delta = recentPoints[i].volume - recentPoints[i - 1].volume;
              if (delta > 0) {
                totalDelta += delta;
                validPoints++;
              }
            }

            if (validPoints > 0) {
              lastMinuteDelta = totalDelta / validPoints;  // 平均增量
            }
          }

          // 只有当最后一分钟增量 > 0 时才预测
          if (lastMinuteDelta > 0) {
            // 计算剩余交易分钟数
            const elapsedMinutes = uniqueArr.length;  // 已请求的累计分钟数
            const remainingMinutes = 240 - elapsedMinutes;

            // 预估成交额 = 当前累计 + (最后一分钟增量 × 剩余分钟数)
            estimatedVolume = volume + (lastMinuteDelta * remainingMinutes);
          }
        }
      }
    }
  }

  // 计算增量预测（仅当有预估成交额时）
  let deltaPredicted = null;
  let pctPredicted = null;
  let dirPredicted = null;

  if (isNum(estimatedVolume) && isNum(yVolFullDay) && yVolFullDay > 0) {
    deltaPredicted = estimatedVolume - yVolFullDay;
    pctPredicted = (estimatedVolume / yVolFullDay - 1) * 100;
    dirPredicted = deltaPredicted >= 0 ? '预估增量' : '预估缩量';
  }

  const missing = (!isNum(yVolFullDay) || yVolFullDay === 0) ? ['t1_volume'] : [];
  const data_incomplete = missing.length > 0;

  // 兼容旧字段（使用预估数据）
  const volumeDelta = isNum(deltaPredicted) ? deltaPredicted : null;
  const volumePct = isNum(pctPredicted) ? pctPredicted : null;
  const volumeDir = dirPredicted;
  const yVol = yVolFullDay;

  return {
    time: nowTime,
    asOf: yday || null,
    data_incomplete,
    missing,

    // 兼容旧字段
    dir: volumeDir,
    pct: volumePct,
    delta: volumeDelta,
    yday: yVol,

    // 新增字段：预估成交额相关
    estimatedVolume,           // 预估全天成交额（万元）
    estimatedVolumeYi: isNum(estimatedVolume) ? +(estimatedVolume / 10000).toFixed(2) : null,  // 预估全天成交额（亿元）
    deltaPredicted,            // 预估增量（万元）
    deltaPredictedYi: isNum(deltaPredicted) ? +(deltaPredicted / 10000).toFixed(2) : null,    // 预估增量（亿元）
    pctPredicted: isNum(pctPredicted) ? +pctPredicted.toFixed(2) : null,  // 预估增量百分比
    dirPredicted,              // 预估增量方向
    ydayFull: yVolFullDay,     // 昨日全天成交额（万元）
    ydayFullYi: isNum(yVolFullDay) ? +(yVolFullDay / 10000).toFixed(2) : null,  // 昨日全天成交额（亿元）

    // 辅助字段
    currentVolume: volume,     // 当前累计成交额（万元）
    currentVolumeYi: isNum(volume) ? +(volume / 10000).toFixed(2) : null,  // 当前累计成交额（亿元）
    lastMinuteDelta,           // 最后一分钟增量（万元）
    lastMinuteDeltaYi: isNum(lastMinuteDelta) ? +(lastMinuteDelta / 10000).toFixed(2) : null  // 最后一分钟增量（亿元）
  };
}

function appendMinuteFile(file, data, lastTime) {
  if (!data || !data.length) return;
  const rows = [];
  for (const p of data) {
    if (!p?.time) continue;
    if (lastTime && p.time <= lastTime) continue;
    rows.push(JSON.stringify([p.time, p.open, p.close]));
  }
  if (!rows.length) return;
  fs.appendFileSync(file, rows.join('\n') + '\n');
}

function writeMinuteFile(file, data) {
  if (!data || !data.length) return;
  const rows = [];
  for (const p of data) {
    if (!p?.time) continue;
    rows.push(JSON.stringify([p.time, p.open, p.close]));
  }
  if (!rows.length) return;
  fs.writeFileSync(file, rows.join('\n') + '\n');
}

async function loadMinuteSeries(day, code, secid) {
  const dataFile = minuteFilePath(day, code);
  const runtimeFile = runtimeMinuteFilePath(day, code);
  const dataArr = readMinuteFile(dataFile).arr;
  let runtimeArr = readMinuteFile(runtimeFile).arr;
  let series = mergeMinuteSeries(dataArr, runtimeArr);
  if (!series.length && secid) {
    const emMinute = await fetchEastmoneyMinute(secid);
    if (emMinute?.data?.length) {
      writeMinuteFile(runtimeFile, emMinute.data);
      runtimeArr = readMinuteFile(runtimeFile).arr;
      series = mergeMinuteSeries(dataArr, runtimeArr);
    }
  }
  if (!series.length) {
    const latestRuntime = findLatestRuntimeMinuteFile(code);
    if (latestRuntime) series = readMinuteFile(latestRuntime).arr;
  }
  if (!series.length) {
    const latestFile = findLatestMinuteFile(code);
    if (latestFile) series = readMinuteFile(latestFile).arr;
  }
  return series;
}

function findLatestMinuteFile(code) {
  const dir = path.join(__dirname, 'data');
  if (!fs.existsSync(dir)) return null;
  const files = fs.readdirSync(dir).filter(f => f.startsWith('minute-') && f.endsWith(`-${code}.jsonl`));
  if (!files.length) return null;
  files.sort();
  return path.join(dir, files[files.length - 1]);
}

function dayFromMinuteFile(file) {
  const base = path.basename(file);
  const m = base.match(/minute-(\d{8})-/);
  if (!m) return null;
  const d = m[1];
  return `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)}`;
}

function minuteCodeMap(code) {
  const map = {
    sse: 'sh000001',
    szi: 'sz399001',
    gem: 'sz399006',
    star: 'sh000680',
    hs300: 'sh000300',
    csi2000: 'sh932000',
    avg: 'sh000001',
    gov: 'sh000012',
    t: 'sh511260',
    tl: 'sh511130',
    bank: 'bk0475',
    broker: 'bk0473',
    insure: 'bk0474'
  };
  return map[code] || null;
}

function minuteTxMap(code) {
  const map = {
    sse: 'sh000001',
    szi: 'sz399001',
    gem: 'sz399006',
      star: 'sh000680',
      hs300: 'sh000300',
      csi2000: 'sh932000',
      t: 'sh511260',
      tl: 'sh511130'
    };
  return map[code] || null;
}

function minuteEmMap(code) {
  const map = {
    sse: '1.000001',
    szi: '0.399001',
    gem: '0.399006',
    star: '1.000680',
    hs300: '1.000300',
    gov: '1.000012',
    csi2000: '2.932000',
    avg: '2.830000',
    t: '1.511260',
    tl: '1.511130',
    bank: '90.BK0475',
    broker: '90.BK0473',
    insure: '90.BK0474'
  };
  return map[code] || null;
}

function pickPrevCloseFromDaily(list, day) {
  if (!Array.isArray(list) || !day) return null;
  const prev = list
    .filter(d => d?.date && d.date < day && isNum(d.close))
    .sort((a, b) => b.date.localeCompare(a.date))[0];
  return isNum(prev?.close) ? prev.close : null;
}

async function fetchPrevCloseForMinute(code, day) {
  const txCode = minuteTxMap(code);
  if (txCode) {
    const daily = await fetchTencentDaily(txCode, 10);
    const prevClose = pickPrevCloseFromDaily(daily?.data || [], day);
    if (isNum(prevClose)) return prevClose;
  }
  const emCode = minuteEmMap(code);
  if (emCode) {
    const daily = await fetchEastmoneyDaily(emCode, 10);
    const prevClose = pickPrevCloseFromDaily(daily?.data || [], day);
    if (isNum(prevClose)) return prevClose;
  }
  return null;
}

function mergeDailyVolume(sse, szi) {
  const map = new Map();
  const add = (series) => {
    (series || []).forEach((p) => {
      if (!p?.date || !isNum(p.amount)) return;
      if (p.amount <= 0) return;
      const v = map.get(p.date) || 0;
      if (v > 0) {
        const ratio = p.amount / v;
        if (ratio < 0.1 || ratio > 10) return;
      }
      map.set(p.date, v + p.amount);
    });
  };
  add(sse);
  add(szi);
  return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0])).map(([date, amount]) => ({ date, amount }));
}

function lastDateInSeries(arr) {
  if (!arr || !arr.length) return null;
  return arr[arr.length - 1]?.date || null;
}

function trimDailyOutlier(arr) {
  if (!arr || arr.length < 2) return arr || [];
  const prev = arr[arr.length - 2];
  const last = arr[arr.length - 1];
  const prevClose = toNumber(prev?.close);
  const lastClose = toNumber(last?.close);
  if (!isNum(prevClose) || !isNum(lastClose) || prevClose <= 0) return arr;
  const ratio = lastClose / prevClose;
  if (ratio < 0.6 || ratio > 1.6) return arr.slice(0, -1);
  return arr;
}

function buildDailyFromMinuteSeries(series, day, prevClose) {
  if (!series || !series.length) return null;
  const filtered = day ? series.filter(p => p?.time && String(p.time).startsWith(day)) : series;
  if (!filtered.length) return null;
  const sorted = filtered.slice().sort((a, b) => (a.time || '').localeCompare(b.time || ''));
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  const vals = [];
  sorted.forEach((p) => {
    if (isNum(p.open)) vals.push(p.open);
    if (isNum(p.close)) vals.push(p.close);
  });
  if (!vals.length) return null;
  const open = isNum(first.open) ? first.open : first.close;
  const close = isNum(last.close) ? last.close : last.open;
  if (!isNum(open) || !isNum(close)) return null;
  const date = day || String(last.time || '').split(' ')[0];
  let pct = null;
  if (isNum(prevClose) && prevClose !== 0) {
    pct = +(((close - prevClose) / prevClose) * 100).toFixed(2);
  } else if (open !== 0) {
    pct = +(((close - open) / open) * 100).toFixed(2);
  }
  return { date, open, high: Math.max(...vals), low: Math.min(...vals), close, pct, volume: null, amount: null };
}

async function buildOverviewHistoryPayload(day, includeTodayVolume = false) {
  const keys = ['sse', 'szi', 'gem', 'star', 'hs300', 'csi2000', 'avg', 't', 'tl', 'bank', 'broker', 'insure'];
  const pairs = await Promise.all(keys.map(async (k) => {
    const secid = minuteEmMap(k);
    if (secid) {
      const daily = await fetchEastmoneyDaily(secid, 180);
      if (daily?.data?.length) return [k, daily.data];
    }
    const txCode = minuteTxMap(k);
    if (txCode) {
      const daily = await fetchTencentDaily(txCode, 180);
      if (daily?.data?.length) return [k, daily.data];
    }
    return [k, []];
  }));
  const series = {};
  pairs.forEach(([k, v]) => { series[k] = trimDailyOutlier(v || []); });
  const minutePairs = await Promise.all(keys.map(async (k) => {
    const secid = minuteEmMap(k);
    const minuteSeries = await loadMinuteSeries(day, k, secid);
    return [k, minuteSeries];
  }));
  const minuteMap = {};
  minutePairs.forEach(([k, v]) => { minuteMap[k] = v || []; });
  Object.entries(minuteMap).forEach(([k, v]) => {
    const arr = series[k] || [];
    const last = lastDateInSeries(arr);
    const lastClose = arr.length ? toNumber(arr[arr.length - 1]?.close) : null;
    const prevClose = (() => {
      if (!arr.length) return null;
      if (last === day) return toNumber(arr[arr.length - 2]?.close);
      return toNumber(arr[arr.length - 1]?.close);
    })();
    const todayDaily = buildDailyFromMinuteSeries(v, day, prevClose);
    if (!todayDaily) return;
    const todayClose = toNumber(todayDaily.close);
    if (isNum(lastClose) && lastClose > 0 && isNum(todayClose)) {
      const ratio = todayClose / lastClose;
      if (ratio < 0.6 || ratio > 1.6) return;
    }
    if (!last || last < day) {
      series[k] = arr.concat([todayDaily]);
    } else if (last === day) {
      if (includeTodayVolume && isNum(arr[arr.length - 1]?.amount) && !isNum(todayDaily.amount)) return;
      arr[arr.length - 1] = todayDaily;
      series[k] = arr;
    }
  });
  let volume = mergeDailyVolume(series.sse, series.szi).filter(p => p?.date && (includeTodayVolume ? p.date <= day : p.date < day));
  if (!volume.length) {
    const map = readMarketAmountDailyMap();
    volume = Array.from(map.values())
      .map(v => ({ date: v.day, amount: v.total }))
      .filter(p => p?.date && (includeTodayVolume ? p.date <= day : p.date < day));
  }
  return JSON.stringify({ day, series, volume, rev: OVERVIEW_CACHE_REV });
}

// 查找缺失的交易日数据
function findMissingArchiveDays(checkFromDay) {
  const dir = path.join(__dirname, 'data');
  if (!fs.existsSync(dir)) return [];

  const files = fs.readdirSync(dir).filter(f => /^archive-\d{8}\.jsonl$/.test(f));
  const existingDates = new Set(files.map(f => {
    const m = f.match(/archive-(\d{8})/);
    if (!m) return null;
    const d = m[1];
    return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`;
  }).filter(Boolean));

  const today = latestTradingDay();
  const missingDays = [];
  let current = checkFromDay;

  while (current <= today) {
    // 使用现有的 isTradingDay() 函数检查是否是交易日
    if (isTradingDay(current) && !existingDates.has(current)) {
      missingDays.push(current);
    }
    current = shiftBeijingDate(current, 1);
  }

  return missingDays;
}

// 补全指定日期的归档数据
async function backfillArchiveDay(day) {
  try {
    console.log(`[补全数据] 开始补全 ${day} 的日线数据...`);

    // 获取上证指数的日线数据
    const dailyData = await fetchTencentDaily('sh000001', 30);
    if (!dailyData?.data?.length) {
      console.log(`[补全数据] ⚠️  ${day} 无法获取日线数据`);
      return false;
    }

    // 查找指定日期的日线
    const dayData = dailyData.data.find(d => d.date === day);
    if (!dayData || !dayData.close || dayData.close <= 0) {
      console.log(`[补全数据] ⚠️  ${day} 无日线数据（可能是节假日）`);
      return false;
    }

    // 构建快照payload，只包含日线数据
    const payload = {
      day: day,
      series: {
        sse: dailyData.data.slice(0, 60) // 取最近60天日线
      },
      ts: Date.now()
    };

    // 手动写入归档文件（只写入一行日线数据）
    const dir = path.join(__dirname, 'data');
    const file = path.join(dir, `archive-${day.replace(/-/g, '')}.jsonl`);
    const row = [
      payload.ts,
      dayData.close, // sse price
      dayData.pct ? parseFloat(dayData.pct) : null, // sse pct
      null, null, null, null, null, null, null, null, // 其他指数
      null, null, null, // bank, broker, insure
      null, // gov
      null, null, null, null, null, // bond prices
      dayData.amount, // volume
      null, null // up/down count
    ];
    fs.appendFileSync(file, JSON.stringify(row) + '\n');

    console.log(`[补全数据] ✅ ${day} 日线数据补全完成`);
    return true;
  } catch (e) {
    console.error(`[补全数据] ❌ ${day} 补全失败:`, e.message);
    return false;
  }
}

// 启动时自动补全缺失数据
async function backfillMissingDataOnStartup() {
  try {
    const today = latestTradingDay();
    // 检查最近 30 天内是否有缺失数据
    const checkFromDay = shiftBeijingDate(today, -30);

    const missingDays = findMissingArchiveDays(checkFromDay);

    if (missingDays.length === 0) {
      console.log('[启动检查] ✅ 最近30天数据完整，无需补全');
      return;
    }

    console.log(`[启动检查] 发现 ${missingDays.length} 个缺失的交易日:`, missingDays);

    // 依次补全每个缺失的日期
    let successCount = 0;
    for (const day of missingDays) {
      const success = await backfillArchiveDay(day);
      if (success) successCount++;

      // 避免请求过于频繁，每个日期之间暂停 1 秒
      await new Promise(resolve => setTimeout(resolve, 1000));
    }

    console.log(`[启动检查] 补全完成: ${successCount}/${missingDays.length} 个日期成功`);
  } catch (e) {
    console.error('[启动检查] 补全数据时出错:', e);
  }
}

function backfillVolumeIfNeeded(day) {
  if (!day) return;
  const list = [day, findPreviousTradingDay(day)].filter(Boolean);
  list.forEach((d) => {
    if (!isUsableVolumeDay(d)) ensureVolumeFile(d);
  });
}

async function backfillOverviewHistoryIfNeeded() {
  const parts = getBeijingParts();
  if (!parts) return;
  if (isMarketOpenNow()) return;
  const isWeekend = parts.weekday === 0 || parts.weekday === 6;
  if (!isAfterCloseNow() && !isWeekend) return;
  const day = latestTradingDay();
  if (lastDailyBackfillDay === day) return;
  backfillVolumeIfNeeded(day);
  const cacheFile = cacheJsonPath('overview-history', day);
  const cached = readJsonCache(cacheFile);
  if (cached) {
    try {
      const p = JSON.parse(cached);
      const last = lastDateInSeries(p?.series?.sse);
      const hasVol = Array.isArray(p?.volume) && p.volume.length;
      if (p?.rev === OVERVIEW_CACHE_REV && last === day && hasVol) {
        lastDailyBackfillDay = day;
        return;
      }
    } catch (e) {
      console.error(e);
    }
  }
  const payload = await buildOverviewHistoryPayload(day, true);
  if (!payload) return;
  try {
    const p = JSON.parse(payload);
    if (p?.series?.sse?.length) {
      writeJsonCache(cacheFile, payload);
      lastDailyBackfillDay = day;
    }
  } catch (e) {
    console.error(e);
  }
}

function readLatestArchivePayload() {
  const baseDay = latestTradingDay();
  const base = (baseDay || (new Date()).toISOString().split('T')[0]).replace(/-/g, '');
  const dir = path.join(__dirname, 'data');
  let pick = base;
  const baseFile = path.join(dir, `archive-${base}.jsonl`);
  if (!fs.existsSync(baseFile) && fs.existsSync(dir)) {
    const files = fs.readdirSync(dir).filter(f => /^archive-\d{8}\.jsonl$/.test(f));
    files.sort();
    for (const f of files) {
      const m = f.match(/^archive-(\d{8})\.jsonl$/);
      const d = m ? m[1] : null;
      if (d && d <= base) pick = d;
    }
  }
  const day = `${pick.slice(0, 4)}-${pick.slice(4, 6)}-${pick.slice(6, 8)}`;
  const file = path.join(dir, `archive-${pick}.jsonl`);
  if (!fs.existsSync(file)) return null;
  const txt = fs.readFileSync(file, 'utf-8').trim();
  if (!txt) return null;
  const line = txt.split('\n').slice(-1)[0];
  if (!line) return null;
  const row = JSON.parse(line);
  if (!Array.isArray(row) || row.length < 22) return null;
  const [
    ts,
    ssePrice, ssePct,
    sziPrice, sziPct,
    gemPrice, gemPct,
    starPrice, starPct,
    hs300Price, hs300Pct,
    csi2000Price, csi2000Pct,
    bankPct, brokerPct, insurePct,
    govPct,
    tPrice, tPct,
    tlPrice, tlPct,
    volume, upCount, downCount
  ] = row;
  const avgPrice = row.length >= 26 ? row[24] : null;
  const avgPct = row.length >= 26 ? row[25] : null;
  const tPriceNorm = normalizeBondPrice(tPrice);
  const tlPriceNorm = normalizeBondPrice(tlPrice);
  const volumeCmp = isNum(volume) ? buildVolumeCompare(day, volume) : null;
  ensureVolumeFile(day);
  const volumeSeries = readVolumeSeries(day);
  const t1Day = findPreviousTradingDay(day);
  let volumeSeriesYday = [];
  const missing = [];
  if (t1Day && isUsableVolumeDay(t1Day)) {
    ensureVolumeFile(t1Day);
    volumeSeriesYday = readVolumeSeries(t1Day);
  } else if (t1Day) {
    missing.push('t1_volume');
  }
  if (volumeCmp?.data_incomplete) missing.push(...(volumeCmp?.missing || []));
  const payload = {
    day,
    indices: {
      sse: { price: ssePrice || null, pct: ssePct || null, series: [] },
      szi: { price: sziPrice || null, pct: sziPct || null, series: [] },
      gem: { price: gemPrice || null, pct: gemPct || null, series: [] },
      star: { price: starPrice || null, pct: starPct || null, series: [] },
      hs300: { price: hs300Price || null, pct: hs300Pct || null, series: [] },
      csi2000: { price: csi2000Price || null, pct: csi2000Pct || null, series: [] },
      avg: { price: avgPrice || null, pct: avgPct || null, series: [] }
    },
    bonds: {
      gov: { pct: govPct || null, series: [] },
      tl2603: { price: tlPriceNorm || null, pct: tlPct || null, series: [] },
      t2603: { price: tPriceNorm || null, pct: tPct || null, series: [] },
      tl: { price: tlPriceNorm || null, pct: tlPct || null },
      t: { price: tPriceNorm || null, pct: tPct || null }
    },
    sectors: {
      bank: { pct: bankPct || null, series: [] },
      broker: { pct: brokerPct || null, series: [] },
      insure: { pct: insurePct || null, series: [] }
    },
    sentiment: {
      volume: volume || 0,
      volumeStr: volume ? (volume / 10000).toFixed(1) + '亿' : '-',
      upCount: upCount || '-',
      downCount: downCount || '-',
      volumeCmp,
      volumeSeries,
      volumeSeriesYday,
      t1_day: t1Day || null,
      data_incomplete: missing.length > 0,
      missing: Array.from(new Set(missing))
    },
    ts: ts || Date.now()
  };
  payload.aiBrief = ai.analyze(payload);
  return payload;
}

function readLatestArchiveVolume(day) {
  if (!day) return null;
  const file = path.join(__dirname, 'data', `archive-${day.replace(/-/g, '')}.jsonl`);
  if (!fs.existsSync(file)) return null;
  const txt = fs.readFileSync(file, 'utf-8').trim();
  if (!txt) return null;
  const line = txt.split('\n').slice(-1)[0];
  if (!line) return null;
  const row = JSON.parse(line);
  if (!Array.isArray(row) || row.length < 22) return null;
  const vol = row[21];
  return isNum(vol) ? vol : null;
}

async function buildSnapshotPayload() {
  // 先确定市场日期
  const todayTradingDay = latestTradingDay();
  const marketOpenNow = isMarketOpenNow();
  let marketDate = todayTradingDay;

  // 优先读取本地分时文件
  const [sseSeries, sziSeries, gemSeries, starSeries, hs300Series] = await Promise.all([
    loadMinuteSeries(marketDate, 'sse', '1.000001'),
    loadMinuteSeries(marketDate, 'szi', '0.399001'),
    loadMinuteSeries(marketDate, 'gem', '0.399006'),
    loadMinuteSeries(marketDate, 'star', '1.000680'),
    loadMinuteSeries(marketDate, 'hs300', '1.000300')
  ]);

  // 判断是否需要调用API（本地文件不存在或不是最新）
  const needApiCall = marketOpenNow && (!sseSeries.length || sseSeries.length < 50);

  // 只在需要时调用API
  let sse = { date: null, data: [] };
  let szi = { date: null, data: [] };
  let gem = { date: null, data: [] };
  let star = { date: null, data: [] };
  let hs300 = { date: null, data: [] };
  let tEtf = { date: null, data: [], prevClose: null };
  let tlEtf = { date: null, data: [], prevClose: null };

  if (needApiCall) {
    [sse, szi, gem, star, hs300, tEtf, tlEtf] = await Promise.all([
      fetchAshareMinute('sh000001'),
      fetchAshareMinute('sz399001'),
      fetchAshareMinute('sz399006'),
      fetchAshareMinute('sh000680'),
      fetchAshareMinute('sh000300'),
      fetchAshareMinute('sh511260'),
      fetchAshareMinute('sh511130')
    ]);
    // 更新marketDate（如果有API返回的日期）
    if (sse.date && sse.date > marketDate) marketDate = sse.date;
  }

  const snaps = await fetchSnapshot('sh000001,sz399001,sz399006,sh000680,sh000300,sh000012,sz399106,sh511260,sh511130');
  const em = await fetchEastmoneySnapshot(['90.BK0475', '90.BK0473', '90.BK0474', '2.932000', '2.830000', '1.000012']);

  if (!marketOpenNow) {
    marketDate = todayTradingDay;
  } else if (marketDate < todayTradingDay) {
    marketDate = todayTradingDay;
  }
  if (isAfterCloseNow()) {
    const etfMap = readEtfAmountTotalMap();
    if (!etfMap.has(marketDate)) {
      refreshEtfAmountTotalViaPython(marketDate).catch(() => {});
    }
  }

  // 使用API数据覆盖本地数据（如果有）
  const finalSseSeries = (sse.date === marketDate && sse.data?.length) ? sse.data : sseSeries;
  const finalSziSeries = (szi.date === marketDate && szi.data?.length) ? szi.data : sziSeries;
  const finalGemSeries = (gem.date === marketDate && gem.data?.length) ? gem.data : gemSeries;
  const finalStarSeries = (star.date === marketDate && star.data?.length) ? star.data : starSeries;
  const finalHs300Series = (hs300.date === marketDate && hs300.data?.length) ? hs300.data : hs300Series;

  // Get previous trading day volume via Tencent API as fallback
  try {
    await fetchTencentDaily('sh000001', 5);
  } catch (e) {
    console.error(e);
  }

  const tSeries = Array.isArray(tEtf?.data) ? tEtf.data : [];
  const tlSeries = Array.isArray(tlEtf?.data) ? tlEtf.data : [];
  const fixPrevClose = (prev, series) => {
    const first = Array.isArray(series) && series.length ? pickNum(toNumber(series[0]?.open), toNumber(series[0]?.close)) : null;
    if (!isNum(prev) || !isNum(first) || prev <= 0) return null;
    const ratio = first / prev;
    if (!Number.isFinite(ratio) || ratio < 0.9 || ratio > 1.1) return null;
    return prev;
  };
  const tPrev = fixPrevClose(tEtf?.prevClose ?? null, tSeries);
  const tlPrev = fixPrevClose(tlEtf?.prevClose ?? null, tlSeries);
  const avgSeries = await loadMinuteSeries(marketDate, 'avg', '2.830000');
  const csi2000Series = await loadMinuteSeries(marketDate, 'csi2000', '2.932000');

  const tDerived = deriveFromSeries(tSeries, tPrev);
  const tlDerived = deriveFromSeries(tlSeries, tlPrev);
  const tSnapPrice = snaps['sh511260']?.price || null;
  const tlSnapPrice = snaps['sh511130']?.price || null;
  const tSnapPct = snaps['sh511260']?.pct || null;
  const tlSnapPct = snaps['sh511130']?.pct || null;
  const tFinal = { price: pickNum(tDerived.price, tSnapPrice), pct: pickNum(tDerived.pct, tSnapPct) };
  const tlFinal = { price: pickNum(tlDerived.price, tlSnapPrice), pct: pickNum(tlDerived.pct, tlSnapPct) };
  const szAmount = pickNum(snaps['sz399001']?.amount, snaps['sz399106']?.amount);
  const amountList = [snaps['sh000001']?.amount, szAmount];
  const totalAmountRaw = amountList.reduce((sum, v) => sum + (isNum(v) ? v : 0), 0);
  const totalAmountFromSnapshot = isNum(totalAmountRaw) && totalAmountRaw > 0;
  let totalAmount = isNum(totalAmountRaw) ? totalAmountRaw : 0;
  if (!isNum(totalAmount) || totalAmount <= 0) {
    const fallback = pickNum(lastGoodSnapshot.payload?.sentiment?.volume, readLatestArchiveVolume(marketDate));
    if (isNum(fallback) && fallback > 0) totalAmount = fallback;
  }
  const avgPrice = em['2.830000']?.price || null;
  const avgPct = em['2.830000']?.pct || null;
  
  // Recalculate avg price/pct from series if snapshot is missing
  const avgDerived = deriveFromSeries(avgSeries, em['2.830000']?.prevClose || null);
  const avgPriceFinal = avgPrice || avgDerived.price || null;
  const avgPctFinal = avgPct || avgDerived.pct || null;
  
  const csi2000Derived = deriveFromSeries(csi2000Series, em['2.932000']?.prevClose || null);
  const csi2000PriceFinal = em['2.932000']?.price || csi2000Derived.price || null;
  const csi2000PctFinal = em['2.932000']?.pct || csi2000Derived.pct || null;

  const volumeSeries = readVolumeSeries(marketDate);
  let volumeSeriesYday = [];
  let breadth = await fetchBreadthRealtime();
  // ���果获取到实时数据，写入缓存文件
  if (breadth && isNum(breadth?.up) && isNum(breadth?.down)) {
    try {
      const file = breadthCachePath();
      fs.writeFileSync(file, JSON.stringify(breadth), 'utf8');
    } catch (e) {
      console.error('写入涨跌家数缓存失败:', e);
    }
  } else {
    // 如果没有获取到实时数据，尝试从缓存读取
    const cacheFile = cacheJsonPath('market-breadth', marketDate);
    const cached = readJsonCache(cacheFile);
    if (cached && isJsonText(cached)) {
      try {
        const obj = JSON.parse(cached);
        if (isNum(obj?.up) && isNum(obj?.down)) breadth = obj;
      } catch (e) {
        void e;
      }
    }
  }
  let upCount = isNum(breadth?.up) ? breadth.up : null;
  let downCount = isNum(breadth?.down) ? breadth.down : null;
  if (!isNum(upCount) || !isNum(downCount)) {
    const row = loadLatestBreadthRecord() || loadBreadthFromArchive(marketDate);
    const up = Number(row?.up);
    const down = Number(row?.down);
    if (Number.isFinite(up) && Number.isFinite(down) && up > 0 && down > 0) {
      upCount = up;
      downCount = down;
    }
  }
  if (isAfterCloseNow() && volumeSeries.length && !totalAmountFromSnapshot) {
    const lastVol = volumeSeries[volumeSeries.length - 1]?.volume;
    if (isNum(lastVol) && lastVol > 0) {
      if (!isNum(totalAmount) || totalAmount <= 0) {
        totalAmount = lastVol;
      } else {
        const ratio = lastVol / totalAmount;
        if (Number.isFinite(ratio) && ratio >= 0.7 && ratio <= 1.3) totalAmount = lastVol;
      }
    }
  }
  const volumeCmp = buildVolumeCompare(marketDate, totalAmount);
  const t1Day = findPreviousTradingDay(marketDate);
  const missingList = [];
  if (t1Day && isUsableVolumeDay(t1Day)) {
    ensureVolumeFile(t1Day);
    volumeSeriesYday = readVolumeSeries(t1Day);
  } else if (t1Day) {
    missingList.push('t1_volume');
  }
  if (volumeCmp?.data_incomplete) missingList.push(...(volumeCmp?.missing || []));
  const etfMap = readEtfAmountTotalMap();
  const etfRow = pickEtfAmountTotal(etfMap, marketDate);
  const etfAmountWan = etfRow ? normalizeEtfTotalToWan(etfRow.total) : null;
  const etfSharePct = (etfAmountWan != null && isNum(totalAmount) && totalAmount > 0) ? +((etfAmountWan / totalAmount) * 100).toFixed(2) : null;

  const bankSeries = await loadMinuteSeries(marketDate, 'bank', '90.BK0475');
  const brokerSeries = await loadMinuteSeries(marketDate, 'broker', '90.BK0473');
  const insureSeries = await loadMinuteSeries(marketDate, 'insure', '90.BK0474');
  const govSeries = await loadMinuteSeries(marketDate, 'gov', '1.000012');
  const bankDerived = deriveFromSeries(bankSeries, em['90.BK0475']?.prevClose || null);
  const brokerDerived = deriveFromSeries(brokerSeries, em['90.BK0473']?.prevClose || null);
  const insureDerived = deriveFromSeries(insureSeries, em['90.BK0474']?.prevClose || null);
  const govDerived = deriveFromSeries(govSeries, em['1.000012']?.prevClose || null);
  const bankPctFinal = pickNum(em['90.BK0475']?.pct, bankDerived.pct);
  const brokerPctFinal = pickNum(em['90.BK0473']?.pct, brokerDerived.pct);
  const insurePctFinal = pickNum(em['90.BK0474']?.pct, insureDerived.pct);
  const bankPriceFinal = pickNum(em['90.BK0475']?.price, bankDerived.price);
  const brokerPriceFinal = pickNum(em['90.BK0473']?.price, brokerDerived.price);
  const insurePriceFinal = pickNum(em['90.BK0474']?.price, insureDerived.price);
  const govPctFinal = pickNum(snaps['sh000012']?.pct, govDerived.pct);
  const payload = {
    day: marketDate,
    indices: {
      sse: { price: snaps['sh000001']?.price || finalSseSeries.at(-1)?.close, pct: snaps['sh000001']?.pct || pctOfDay(finalSseSeries), series: finalSseSeries },
      szi: { price: snaps['sz399001']?.price || finalSziSeries.at(-1)?.close, pct: snaps['sz399001']?.pct || pctOfDay(finalSziSeries), series: finalSziSeries },
      gem: { price: snaps['sz399006']?.price || finalGemSeries.at(-1)?.close, pct: snaps['sz399006']?.pct || pctOfDay(finalGemSeries), series: finalGemSeries },
      star: { price: snaps['sh000680']?.price || finalStarSeries.at(-1)?.close, pct: snaps['sh000680']?.pct || pctOfDay(finalStarSeries), series: finalStarSeries },
      hs300: { price: snaps['sh000300']?.price || finalHs300Series.at(-1)?.close, pct: snaps['sh000300']?.pct || pctOfDay(finalHs300Series), series: finalHs300Series },
      csi2000: { price: csi2000PriceFinal, pct: csi2000PctFinal, series: csi2000Series },
      avg: { price: avgPriceFinal, pct: avgPctFinal, series: avgSeries }
    },
    bonds: {
      gov: { pct: govPctFinal, series: govSeries },
      tl2603: { price: tlFinal.price, pct: tlFinal.pct, series: tlSeries },
      t2603: { price: tFinal.price, pct: tFinal.pct, series: tSeries },
      tl: { price: tlFinal.price, pct: tlFinal.pct },
      t: { price: tFinal.price, pct: tFinal.pct }
    },
    sectors: {
      bank: { price: bankPriceFinal, pct: bankPctFinal, series: bankSeries },
      broker: { price: brokerPriceFinal, pct: brokerPctFinal, series: brokerSeries },
      insure: { price: insurePriceFinal, pct: insurePctFinal, series: insureSeries }
    },
    sentiment: {
      volume: totalAmount || 0,
      volumeStr: totalAmount ? (totalAmount / 10000).toFixed(1) + '亿' : '-',
      volumeCmp,
      etfAmount: etfAmountWan,
      etfAmountStr: etfAmountWan ? (etfAmountWan / 10000).toFixed(1) + '亿' : '-',
      etfSharePct,
      etfAsOf: etfRow ? etfRow.day : null,
      volumeSeries,
      volumeSeriesYday,
      t1_day: t1Day || null,
      data_incomplete: missingList.length > 0,
      missing: Array.from(new Set(missingList)),
      upCount: upCount || '-',
      downCount: downCount || '-'
    },
    ts: Date.now()
  };
  
  // Inject AI Analysis
  payload.aiBrief = ai.analyze(payload);
  archiveSnapshot(payload);
  if (isNum(payload.bonds?.t2603?.price) && isNum(payload.bonds?.tl2603?.price)) {
    lastGoodSnapshot.payload = payload;
    lastGoodSnapshot.ts = now();
  }
  
  return payload;
}

async function callBailian(prompt, data) {
  // 1. 优先支持 DeepSeek 官方 API (如果配置了 DEEPSEEK_API_KEY)
  if (process.env.DEEPSEEK_API_KEY) {
    const apiKey = process.env.DEEPSEEK_API_KEY;
    const model = process.env.DEEPSEEK_MODEL || 'deepseek-chat';
    const baseUrl = process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com';
    const url = `${baseUrl}/chat/completions`;
    
    const body = {
      model,
      messages: [
        { role: 'system', content: prompt },
        { role: 'user', content: `输入数据：\n${JSON.stringify(data)}` }
      ],
      temperature: 0.2,
      stream: false
    };
    
    const { status, data: text } = await postJson(url, { Authorization: `Bearer ${apiKey}` }, body);
    if (status !== 200) throw new Error(`deepseek_api_error_${status}`);
    const json = text ? JSON.parse(text) : {};
    return json?.choices?.[0]?.message?.content || '';
  }

  // 2. 降级使用阿里云百炼 (DashScope)
  const apiKey = process.env.DASHSCOPE_API_KEY || process.env.BAILIAN_API_KEY || '';
  if (!apiKey) throw new Error('missing_key');
  const model = process.env.BAILIAN_MODEL || 'deepseek-v3.2';
  const url = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions';
  const body = {
    model,
    messages: [
      { role: 'system', content: prompt },
      { role: 'user', content: `输入数据：\n${JSON.stringify(data)}` }
    ],
    temperature: 0.2,
    stream: false,
    enable_thinking: false
  };
  const { status, data: text } = await postJson(url, { Authorization: `Bearer ${apiKey}` }, body);
  if (status !== 200) throw new Error(`api_error_${status}`);
  const json = text ? JSON.parse(text) : {};
  return json?.choices?.[0]?.message?.content || '';
}

async function ensureAiText(snap) {
  const apiKey = process.env.DASHSCOPE_API_KEY || process.env.BAILIAN_API_KEY || '';
  if (!apiKey) return lastAiText || '';
  try {
    const prompt = fs.readFileSync(PROMPT_PATH, 'utf-8');
    const text = await callBailian(prompt, snap);
    if (text) {
      lastAiText = text;
      return text;
    }
    return lastAiText || '';
  } catch (e) {
    return lastAiText || '';
  }
}

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
  
  if (url.pathname === '/api/prompt/stock-daily') {
    try {
      const txt = fs.readFileSync(PROMPT_PATH, 'utf-8');
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ text: txt }));
    } catch (e) {
      res.writeHead(500);
      res.end('prompt read error');
    }
    return;
  }
  if (url.pathname === '/api/prompt/sector-analysis') {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ text: SECTOR_PROMPT }));
    return;
  }
  if (url.pathname === '/api/ai/debug' && req.method === 'POST') {
    try {
      const raw = await readBody(req);
      const body = raw ? JSON.parse(raw) : {};
      const prompt = body.prompt || fs.readFileSync(PROMPT_PATH, 'utf-8');
      const snap = readLatestArchivePayload() || await buildSnapshotPayload();
      // 调试：打印喂给AI的关键数据
      console.log('[AI Debug] 喂给AI的数据:', JSON.stringify({
        upCount: snap?.sentiment?.upCount,
        downCount: snap?.sentiment?.downCount,
        volume: snap?.sentiment?.volume,
        volumeStr: snap?.sentiment?.volumeStr,
        indices: snap?.indices ? Object.keys(snap.indices) : []
      }));
      const text = await callBailian(prompt, snap);
      lastAiText = text || '';
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ text }));
    } catch (e) {
      const msg = String(e?.message || '');
      const code = msg.includes('missing_key') ? 401 : 500;
      res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: code === 401 ? '缺少API Key' : '调用失败' }));
    }
    return;
  }
  if (url.pathname === '/api/ai/sector-debug' && req.method === 'POST') {
    try {
      const raw = await readBody(req);
      const body = raw ? JSON.parse(raw) : {};
      const prompt = body.prompt || SECTOR_PROMPT;
      const execPy = (cmd) => new Promise((resolve, reject) => {
        execFile('python3', ['fetch_sector_data.py', cmd], getExecOptions(), (err, stdout) => {
          if (err) return reject(err);
          const out = (stdout || '').trim();
          if (!out) return resolve({});
          try { resolve(JSON.parse(out)); } catch (e) { resolve({}); }
        });
      });
      const [historyData, rankData] = await Promise.all([execPy('history'), execPy('rank')]);
      const input = { history: historyData.history || {}, rank: rankData || {} };
      const text = await callBailian(prompt, input);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ text }));
    } catch (e) {
      const msg = String(e?.message || '');
      const code = msg.includes('missing_key') ? 401 : 500;
      res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: code === 401 ? '缺少API Key' : '调用失败' }));
    }
    return;
  }
  if (url.pathname === '/api/ai/sector-analysis') {
    const day = latestTradingDay();
    const cacheFile = cacheJsonPath('sector-analysis-ai', day);
    const cached = readJsonCache(cacheFile);
    if (cached) {
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(cached);
      return;
    }
    const execPy = (cmd) => new Promise((resolve, reject) => {
      execFile('python3', ['fetch_sector_data.py', cmd], (err, stdout) => {
        if (err) return reject(err);
        const out = (stdout || '').trim();
        if (!out) return resolve({});
        try { resolve(JSON.parse(out)); } catch (e) { resolve({}); }
      });
    });
    try {
      const [historyData, rankData] = await Promise.all([execPy('history'), execPy('rank')]);
      const input = { history: historyData.history || {}, rank: rankData || {} };
      const text = await callBailian(SECTOR_PROMPT, input);
      const payload = JSON.stringify({ text });
      if (text) writeJsonCache(cacheFile, payload);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(payload);
    } catch (e) {
      const msg = String(e?.message || '');
      const code = msg.includes('missing_key') ? 401 : 500;
      res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: code === 401 ? '缺少API Key' : '调用失败' }));
    }
    return;
  }
  if (url.pathname.startsWith('/api/minute/')) {
    const code = url.pathname.split('/').pop();

    // ETF分时数据检测：6位数字，5开头(上交所)或1开头(深交所)
    const isETF = /^\d{6}$/.test(code) && ['5', '1'].includes(code[0]);

    if (isETF) {
      // ETF分时数据：优先使用本地文件
      const etfCode = code[0] === '5' ? `sh${code}` : `sz${code}`;

      // 缓存和返回逻辑（优先本地文件）
      const targetDay = latestTradingDay();
      const dataFile = minuteFilePath(targetDay, code);
      const runtimeFile = runtimeMinuteFilePath(targetDay, code);
      const { arr: dataArr } = readMinuteFile(dataFile);
      const runtimeRead = readMinuteFile(runtimeFile);
      let merged = mergeMinuteSeries(dataArr, runtimeRead.arr);

      // 只有在本地数据不足且在交易时间时，才调用Python接口
      const marketOpen = isMarketOpenNow();
      const needRefresh = marketOpen && (!merged.length || merged.length < 50);

      if (needRefresh) {
        let data = { data: [], prevClose: null };
        try {
          const execOpts = getExecOptions();
          execOpts.timeout = 30000;
          data = await new Promise((resolve) => {
            execFile('python3', ['fetch_sector_data.py', 'etf-minute', etfCode], execOpts, (err, stdout, stderr) => {
              if (err) {
                console.error(`ETF minute error for ${etfCode}:`, err, stderr);
                resolve({ data: [], prevClose: null });
              } else {
                try {
                  const parsed = JSON.parse(stdout);
                  resolve(parsed);
                } catch (e) {
                  console.error(`ETF minute parse error for ${etfCode}:`, e);
                  resolve({ data: [], prevClose: null });
                }
              }
            });
          });

          if (data.data && data.data.length) {
            if (!runtimeRead.arr.length || (runtimeRead.arr[0]?.time && data.data[0]?.time && data.data[0].time < runtimeRead.arr[0].time)) {
              writeMinuteFile(runtimeFile, data.data);
            } else {
              appendMinuteFile(runtimeFile, data.data, runtimeRead.lastTime);
            }
            merged = mergeMinuteSeries(dataArr, readMinuteFile(runtimeFile).arr);
          }
        } catch (e) {
          console.error(`ETF minute fetch error for ${code}:`, e.message);
        }
      }

      merged = merged.filter(p => isTradingMinute(timeToMinuteKey(p?.time)));
      const todayFiltered = merged.filter(p => p?.time && String(p.time).startsWith(targetDay) && isTradingMinute(timeToMinuteKey(p?.time)));
      if (todayFiltered.length) merged = todayFiltered;

      // 优先从ETF日线文件获取昨收价
      let prevClose = null;
      try {
        const etfDailyFile = path.join(__dirname, 'data', 'etf_daily', `etf_${code}.jsonl`);
        if (fs.existsSync(etfDailyFile)) {
          const content = fs.readFileSync(etfDailyFile, 'utf-8').split('\n').filter(l => l.trim());
          if (content.length >= 1) {
            const lastRow = JSON.parse(content[content.length - 1]);
            if (lastRow.date < targetDay) {
              prevClose = lastRow.close;
            }
          }
        }
      } catch (e) {
        console.error(`Failed to read ETF daily file for ${code}:`, e.message);
      }

      if (prevClose == null) {
        const t1 = findPreviousTradingDay(targetDay);
        const fallback = prevCloseFromMinuteFile(t1, code);
        if (isNum(fallback)) {
          prevClose = fallback;
        }
      }

      const day = targetDay;

      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ day, data: merged, prevClose }));
      return;
    }

    // 原有板块分时逻辑
    const mapped = minuteCodeMap(code);
    const emMapped = minuteEmMap(code);
    if (!mapped) {
      res.writeHead(404);
      res.end('not found');
      return;
    }

    const marketOpen = isMarketOpenNow();
    let data = { data: [], prevClose: null };
    try {
      if (marketOpen) {
        if (emMapped) {
          data = await fetchEastmoneyMinute(emMapped);
        } else {
          data = await fetchAshareMinute(mapped);
        }
        if (emMapped && (!data?.data || !data.data.length)) {
          const allowAshareFallback = ['sse', 'szi', 'gem', 'star', 'hs300', 'csi2000', 'gov', 't', 'tl'].includes(code);
          if (allowAshareFallback) {
            const alt = await fetchAshareMinute(mapped);
            if (alt?.data && alt.data.length) data = alt;
          }
        }
      }
    } catch (e) {
      console.error(`Error fetching minute data for ${code}:`, e.message);
    }

    let prevClose = data.prevClose || null;
    if (prevClose == null && emMapped && marketOpen) {
      try {
        const snap = await fetchEastmoneySnapshot([emMapped]);
        prevClose = snap[emMapped]?.prevClose || null;
      } catch (e) {
        console.error(e);
      }
    }
    const targetDay = latestTradingDay();
    let day = targetDay;
    let sourceDay = targetDay;
    let dataIncomplete = false;
    const dataFile = minuteFilePath(targetDay, code);
    const runtimeFile = runtimeMinuteFilePath(targetDay, code);
    const { arr: dataArr } = readMinuteFile(dataFile);
    const runtimeRead = readMinuteFile(runtimeFile);
    let merged = mergeMinuteSeries(dataArr, runtimeRead.arr);
    if (data.data && data.data.length) {
      if (!runtimeRead.arr.length || (runtimeRead.arr[0]?.time && data.data[0]?.time && data.data[0].time < runtimeRead.arr[0].time)) {
        writeMinuteFile(runtimeFile, data.data);
      } else {
        appendMinuteFile(runtimeFile, data.data, runtimeRead.lastTime);
      }
      merged = mergeMinuteSeries(dataArr, readMinuteFile(runtimeFile).arr);
    }
    merged = merged.filter(p => isTradingMinute(timeToMinuteKey(p?.time)));
    const todayFiltered = merged.filter(p => p?.time && String(p.time).startsWith(targetDay) && isTradingMinute(timeToMinuteKey(p?.time)));
    if (todayFiltered.length) {
      merged = todayFiltered;
    } else if (!marketOpen) {
      const latestRuntime = findLatestRuntimeMinuteFile(code);
      if (latestRuntime) {
        const { arr: fallbackArr } = readMinuteFile(latestRuntime);
        if (fallbackArr.length) {
          merged = fallbackArr;
          day = dayFromMinuteFile(latestRuntime) || day;
          sourceDay = day;
        }
      }
      if (!merged.length) {
        const latestFile = findLatestMinuteFile(code);
        if (latestFile) {
          const { arr: fallbackArr } = readMinuteFile(latestFile);
          if (fallbackArr.length) {
            merged = fallbackArr;
            day = dayFromMinuteFile(latestFile) || day;
            sourceDay = day;
          }
        }
      }
      if (!merged.length) dataIncomplete = true;
    }
    if (merged.length) {
      const lastTime = String(merged[merged.length - 1]?.time || '');
      const seriesDay = lastTime.includes(' ') ? lastTime.split(' ')[0] : (lastTime.includes('T') ? lastTime.split('T')[0] : '');
      if (seriesDay && seriesDay !== targetDay) {
        dataIncomplete = true;
        sourceDay = seriesDay;
        day = seriesDay;
      }
    }
    const last = merged.length ? (merged[merged.length - 1]?.close || merged[merged.length - 1]?.open) : null;
    if ((code === 't' || code === 'tl') && prevClose != null && merged.length) {
      const first = pickNum(toNumber(merged[0]?.open), toNumber(merged[0]?.close));
      if (first != null) {
        const ratio = first / prevClose;
        if (!Number.isFinite(ratio) || ratio < 0.9 || ratio > 1.1) prevClose = null;
      }
    }
    if ((code === 't' || code === 'tl') && last != null) {
      prevClose = normalizeBondPrice(prevClose);
      if (prevClose != null && prevClose > 500 && last < 200) {
        prevClose = +((prevClose / 10).toFixed(2));
      }
    }
    if (!merged.length) {
      const cached = lastGoodMinute.get(code);
      if (cached?.series?.length && (!marketOpen || cached.day === targetDay || cached.day <= targetDay)) {
        merged = cached.series;
        day = cached.day;
        sourceDay = cached.day || sourceDay;
        if (cached.day && cached.day !== targetDay) dataIncomplete = true;
        prevClose = cached.prevClose || prevClose;
      }
    } else if (!dataIncomplete) {
      lastGoodMinute.set(code, { day, series: merged, prevClose });
    }
    if (prevClose == null) {
      const cached = lastGoodMinute.get(code);
      if (cached?.prevClose != null) prevClose = cached.prevClose;
    }
    if (prevClose == null) {
      const indexMap = { sse: '000001', szi: '399001', gem: '399006', star: '000688' };
      const idx = indexMap[code];
      if (idx) {
        try {
          const file = path.join(__dirname, 'data', 'index_daily', `index_${idx}.jsonl`);
          if (fs.existsSync(file)) {
            const lines = fs.readFileSync(file, 'utf-8').split('\n').filter(Boolean);
            let pick = null;
            for (let i = lines.length - 1; i >= 0 && i >= lines.length - 50; i--) {
              const line = lines[i];
              if (!line) continue;
              try {
                const row = JSON.parse(line);
                if (row?.date && row.date < targetDay && isNum(row.close)) {
                  pick = row.close;
                  break;
                }
              } catch (e) {
                void e;
              }
            }
            if (isNum(pick) && merged.length) {
              const first = pickNum(toNumber(merged[0]?.open), toNumber(merged[0]?.close));
              if (first != null) {
                const ratio = first / pick;
                if (!Number.isFinite(ratio) || ratio < 0.5 || ratio > 2) pick = null;
              }
            }
            if (isNum(pick)) prevClose = pick;
          }
        } catch (e) {
          void e;
        }
      }
    }
    if (prevClose == null) {
      const t1 = findPreviousTradingDay(targetDay);
      const fallback = prevCloseFromMinuteFile(t1, code);
      if (isNum(fallback)) prevClose = fallback;
    }
    if (prevClose == null) {
      try {
        const fetched = await fetchPrevCloseForMinute(code, targetDay);
        if (isNum(fetched)) prevClose = fetched;
      } catch (e) {
        void e;
      }
    }
    merged.sort((a, b) => {
      const ta = String(a.time || '');
      const tb = String(b.time || '');
      const da = ta.includes(' ') ? ta.split(' ')[0] : (ta.includes('T') ? ta.split('T')[0] : day);
      const db = tb.includes(' ') ? tb.split(' ')[0] : (tb.includes('T') ? tb.split('T')[0] : day);
      if (da !== db) return da.localeCompare(db);
      const ma = timeToMinuteKey(ta) || ta;
      const mb = timeToMinuteKey(tb) || tb;
      return ma.localeCompare(mb);
    });
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ day, target_day: targetDay, source_day: sourceDay, data_incomplete: dataIncomplete, series: merged, latest: merged[merged.length - 1] || null, prevClose }));
    return;
  }
  if (url.pathname === '/api/overview/history') {
    const day = latestTradingDay();
    const cacheFile = cacheJsonPath('overview-history', day);
    let cached = readJsonCache(cacheFile);
    if (!cached) {
      const latestCache = findLatestCacheFile('overview-history');
      if (latestCache) cached = readJsonCache(latestCache);
    }
    if (cached) {
      try {
        const p = JSON.parse(cached);
        if (p?.rev === OVERVIEW_CACHE_REV) {
          const last = lastDateInSeries(p?.series?.sse);
          const volLast = lastDateInSeries(p?.volume);
          if (last && last >= day && volLast !== day && p?.series?.sse?.length && p.series.sse.some(x => x.amount > 0)) {
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(cached);
            return;
          }
        }
      } catch (e) {
        console.error(e);
      }
    }
    if (!isMarketOpenNow()) {
      if (cached) {
        try {
          const p = JSON.parse(cached);
          const hasVol = Array.isArray(p?.volume) && p.volume.length;
          if (!hasVol && p?.rev === OVERVIEW_CACHE_REV) {
            const map = readMarketAmountDailyMap();
            const vol = Array.from(map.values())
              .map(v => ({ date: v.day, amount: v.total }))
              .filter(x => x?.date && x.date < day);
            if (vol.length) {
              p.volume = vol;
              cached = JSON.stringify(p);
              if (p?.day === day) writeJsonCache(cacheFile, cached);
            }
          }
        } catch (e) {
          void e;
        }
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(cached);
        return;
      }
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ day, series: {}, volume: [], rev: OVERVIEW_CACHE_REV }));
      return;
    }
    const payload = await buildOverviewHistoryPayload(day);
    if (payload) {
      try {
        const p = JSON.parse(payload);
        if (p?.series?.sse?.length) writeJsonCache(cacheFile, payload);
      } catch (e) {
        console.error(e);
      }
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(payload);
      return;
    }
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ day, series: {}, volume: [], rev: OVERVIEW_CACHE_REV }));
    return;
  }
  if (url.pathname === '/api/market/amount_daily/backfill') {
    const start = url.searchParams.get('start') || '2025-05-19';
    const startDay = start.includes('-') ? start : `${start.slice(0, 4)}-${start.slice(4, 6)}-${start.slice(6, 8)}`;
    const out = await backfillMarketAmountDaily(startDay);
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify(out));
    return;
  }
  if (url.pathname === '/api/market/amount_daily') {
    const map = readMarketAmountDailyMap();
    const start = url.searchParams.get('start') || '';
    const end = url.searchParams.get('end') || '';
    const items = Array.from(map.values())
      .sort((a, b) => String(a.day).localeCompare(String(b.day)))
      .filter(v => (!start || v.day >= start) && (!end || v.day <= end))
      .map(v => ({ day: v.day, total: v.total, sh: v.sh, sz: v.sz }));
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ ok: true, items }));
    return;
  }
  if (url.pathname === '/api/m1/run' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        const data = JSON.parse(body || '{}');
        let args = [];
        if (data.script === 'm1_minute_to_daily.py') {
          args = ['treasolo/m1_minute_to_daily.py', '--symbol', data.symbol];
          if (data.day) args.push('--day', data.day);
        } else if (data.script === 'm1_minute_fetch_indices.py') {
          args = ['treasolo/m1_minute_fetch_indices.py'];
          if (data.symbols) args.push('--symbols', data.symbols);
          if (data.day) args.push('--day', data.day);
          if (data.force) args.push('--force');
        } else if (data.script === 'm1_backfill_index.py') {
          args = ['treasolo/m1_backfill_index.py', '--symbol', data.symbol, '--missing-window-days', '30'];
          if (data.applyFix) args.push('--apply-fix', '--write');
          if (data.expectEnd) args.push('--expect-end', data.expectEnd);
        } else if (data.script === 'm1_minute_fetch_etf.py') {
          args = ['treasolo/m1_minute_fetch_etf.py'];
          if (data.symbols) args.push('--symbols', data.symbols);
          if (data.day) args.push('--day', data.day);
          if (data.force) args.push('--force');
        } else if (data.script === 'm1_minute_to_daily_etf.py') {
          args = ['treasolo/m1_minute_to_daily_etf.py', '--symbol', data.symbol];
          if (data.day) args.push('--day', data.day);
        } else if (data.script === 'm1_market_amount.py') {
          args = ['treasolo/m1_market_amount.py'];
          if (data.day) args.push('--day', data.day);
        } else if (data.script === 'breadth_manager.py') {
          args = ['treasolo/breadth_manager.py', data.cmd || 'spot'];
        } else {
          res.statusCode = 400;
          return res.end(JSON.stringify({ error: 'unknown script' }));
        }
        
        execFile('python3', args, { cwd: __dirname, timeout: 120000, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({
            ok: !err,
            stdout: (stdout || '').trim().split('\n'),
            stderr: stderr
          }));
        });
      } catch (e) {
        res.statusCode = 400;
        res.end(JSON.stringify({ error: e.message }));
      }
    });
    return;
  }

  if (url.pathname === '/api/runner/run' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        const data = JSON.parse(body || '{}');
        const args = ['-m', 'treasolo.runner', 'run', '--plan', data.plan || 'm0m1', '--trigger-type', data.triggerType || 'n8n', '--trigger-source', data.triggerSource || 'n8n-http'];
        if (data.day) args.push('--day', data.day);
        if (data.steps) args.push('--steps', data.steps);
        
        execFile('python3', args, { cwd: __dirname, timeout: 60000, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
          const lines = (stdout || '').trim().split('\n');
          const outRaw = lines[lines.length - 1]; // runner's last line is the JSON
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          // 只要输出了合法的 JSON，就算 runner 内部 failed（exit code 1），也返回 200 给 n8n
          if (outRaw && outRaw.startsWith('{')) {
            res.end(outRaw);
          } else {
            res.statusCode = 500;
            res.end(JSON.stringify({ error: 'runner failed', stderr: stderr || outRaw, stdout }));
          }
        });
      } catch (e) {
        res.statusCode = 400;
        res.end(JSON.stringify({ error: e.message }));
      }
    });
    return;
  }

  if (url.pathname === '/api/runner/journal') {
    const rel = String(url.searchParams.get('path') || '').trim();
    if (!rel || rel.includes('..') || !rel.startsWith('data/runs/')) {
      res.statusCode = 400;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: 'invalid path' }));
      return;
    }
    const abs = path.join(__dirname, rel);
    if (!fs.existsSync(abs)) {
      res.statusCode = 404;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: 'not found', path: rel }));
      return;
    }
    try {
      const obj = JSON.parse(fs.readFileSync(abs, 'utf8'));
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, journal: obj }));
      return;
    } catch (e) {
      res.statusCode = 500;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: e.message, path: rel }));
      return;
    }
  }

  if (url.pathname === '/api/runner/file') {
    const rel = String(url.searchParams.get('path') || '').trim();
    if (!rel || rel.includes('..') || !(rel.startsWith('data/m0/') || rel.startsWith('data/market/') || rel.startsWith('data/runs/'))) {
      res.statusCode = 400;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: 'invalid path' }));
      return;
    }
    const abs = path.join(__dirname, rel);
    if (!fs.existsSync(abs)) {
      res.statusCode = 404;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: 'not found', path: rel }));
      return;
    }
    try {
      const txt = fs.readFileSync(abs, 'utf8');
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, path: rel, text: txt }));
      return;
    } catch (e) {
      res.statusCode = 500;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: e.message, path: rel }));
      return;
    }
  }

  if (url.pathname === '/api/market/etf_amount_total') {
    const refresh = url.searchParams.get('refresh') === '1';
    let updated = null;
    if (refresh) {
      updated = await refreshEtfAmountTotalViaPython();
    }
    const map = readEtfAmountTotalMap();
    const items = Array.from(map.values())
      .sort((a, b) => String(a.day).localeCompare(String(b.day)));
    const latest = items.length ? items[items.length - 1] : null;
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ ok: true, updated, latest, items }));
    return;
  }
  // 市场日期 API
  if (url.pathname === '/api/market/date') {
    const parts = getBeijingParts();
    const marketDate = getMarketDate();
    const isOpen = isInTradingTime(parts);
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ date: marketDate, isOpen, parts }));
    return;
  }
  if (url.pathname === '/api/snapshot') {
    const snap = await buildSnapshotPayload();
    warmupDay(snap.day || latestTradingDay());
    const needAi = url.searchParams.get('ai') !== '0';
    snap.aiText = needAi ? await ensureAiText(snap) : (lastAiText || '');
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify(snap));
    return;
  }
  if (url.pathname === '/api/snapshot/latest') {
    const forceRefresh = url.searchParams.get('refresh') === '1';
    let snap = readLatestArchivePayload();
    const missing = !snap || !isNum(snap.bonds?.gov?.pct) || !isNum(snap.sectors?.bank?.pct) || !isNum(snap.sectors?.broker?.pct) || !isNum(snap.sectors?.insure?.pct);
    const stale = forceRefresh || !snap || !isNum(snap.ts) || (now() - snap.ts > CACHE_TTL_MS);
    // 午休时间也需要获取当日数据
    const needFresh = isMarketOpenNow() || isLunchBreakNow();
    if (stale || missing) {
      let fresh = null;
      try {
        if (needFresh) fresh = await withTimeout(buildSnapshotPayload(), 6000);
      } catch (e) {
        fresh = null;
      }
      if (fresh) {
        warmupDay(fresh.day || latestTradingDay());
        const needAi = url.searchParams.get('ai') !== '0';
        fresh.aiText = needAi ? await ensureAiText(fresh) : (lastAiText || '');
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify(fresh));
        return;
      }
      const fallback = lastGoodSnapshot.payload || snap;
      if (fallback) {
        const fixed = repairSnapshot(fallback);
        const needAi = url.searchParams.get('ai') !== '0';
        fixed.aiText = needAi ? await ensureAiText(fixed) : (lastAiText || '');
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify(fixed));
        // 开盘时间或午休时间都触发后台更新
        if (needFresh) {
          buildSnapshotPayload().then((v) => {
            if (!v) return;
            lastGoodSnapshot.payload = v;
            lastGoodSnapshot.ts = v.ts || now();
            archiveSnapshot(v);
          }).catch(() => {});
        }
        return;
      }
    }
    snap = repairSnapshot(snap);
    if (snap?.sentiment) {
      const baseDay = latestTradingDay();
      const open = isMarketOpenNow();
      const day = open ? (snap.day || baseDay) : baseDay;
      if (!open) snap.day = day;
      warmupDay(day);
      snap.sentiment.volumeCmp = buildVolumeCompare(day, snap.sentiment.volume || null);
      ensureVolumeFile(day);
      snap.sentiment.volumeSeries = readVolumeSeries(day);
      const t1Day = findPreviousTradingDay(day);
      let volumeSeriesYday = [];
      const missingList = [];
      if (t1Day && isUsableVolumeDay(t1Day)) {
        ensureVolumeFile(t1Day);
        volumeSeriesYday = readVolumeSeries(t1Day);
      } else if (t1Day) {
        missingList.push('t1_volume');
      }
      if (snap.sentiment.volumeCmp?.data_incomplete) missingList.push(...(snap.sentiment.volumeCmp?.missing || []));
      snap.sentiment.volumeSeriesYday = volumeSeriesYday;
      snap.sentiment.t1_day = t1Day || null;
      snap.sentiment.data_incomplete = missingList.length > 0;
      snap.sentiment.missing = Array.from(new Set(missingList));
    }
    if (snap && snap.bonds && isNum(snap.bonds.t2603?.price) && isNum(snap.bonds.tl2603?.price)) {
      lastGoodSnapshot.payload = snap;
      lastGoodSnapshot.ts = snap.ts || now();
    }
    if (!snap) {
      res.writeHead(503, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Service temporarily unavailable' }));
      return;
    }
    const needAi = url.searchParams.get('ai') !== '0';
    snap.aiText = needAi ? await ensureAiText(snap) : (lastAiText || '');
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify(snap));
    return;
  }
  if (url.pathname === '/api/data/health') {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    const health = await execPythonJson(['scripts/get_data_health.py'], 30000);
    if (!health) {
      res.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'Failed to get data health status' }));
      return;
    }
    res.end(JSON.stringify(health));
    return;
  }
  if (url.pathname === '/api/data/monitoring') {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    const monitoring = await execPythonJson(['scripts/get_data_monitoring.py'], 30000);
    if (!monitoring) {
      res.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'Failed to get data monitoring status' }));
      return;
    }
    res.end(JSON.stringify(monitoring));
    return;
  }
  if (url.pathname === '/health') {
    res.setHeader('Content-Type', 'application/json');
    const mt = lastGoodMinute.get('t');
    const mtl = lastGoodMinute.get('tl');
    res.end(JSON.stringify({
      ok: true,
      source: 'Ashare+Tencent',
      bonds: {
        t: isNum(lastGoodSnapshot.payload?.bonds?.t2603?.price),
        tl: isNum(lastGoodSnapshot.payload?.bonds?.tl2603?.price),
        lastSnapshotTs: lastGoodSnapshot.ts || null,
        lastMinuteT: mt?.series?.length || 0,
        lastMinuteTl: mtl?.series?.length || 0
      }
    }));
    return;
  }
  if (url.pathname === '/api/market/status') {
    const parts = getBeijingParts();
    const today = parts?.date || null;
    const weekday = today ? getBeijingWeekday(today) : null;
    const tradingDay = today ? isTradingDay(today) : false;
    const marketOpen = isMarketOpenNow();
    const afterClose = isAfterCloseNow();
    let reason = 'unknown';
    if (!parts || !today) reason = 'time_unavailable';
    else if (!tradingDay) reason = (weekday === 0 || weekday === 6) ? 'weekend' : 'holiday';
    else if (marketOpen) reason = 'open';
    else if (afterClose) reason = 'after_close';
    else reason = 'pre_market';
    const strategy = marketOpen ? 'realtime_fetch' : 'cache_only';
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({
      now: today,
      minutes: parts?.minutes ?? null,
      weekday,
      trading_day: tradingDay,
      market_open: marketOpen,
      after_close: afterClose,
      trade_day: latestTradingDay(),
      reason,
      strategy
    }));
    return;
  }

  if (url.pathname === '/api/news') {
    const day = normalizeDateParam(url.searchParams.get('date'));
    if (!day) {
      res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'invalid date, expected YYYY-MM-DD' }));
      return;
    }
    const sector = String(url.searchParams.get('sector') || '').trim();
    const level = String(url.searchParams.get('level') || '').trim();
    const rawLimit = Number(url.searchParams.get('limit'));
    const limit = Number.isFinite(rawLimit) ? Math.min(500, Math.max(1, Math.floor(rawLimit))) : 50;

    const allNews = readNewsByDate(day);
    const filteredNews = allNews.filter((item) => {
      if (sector && item?.classify?.sector !== sector) return false;
      if (level && item?.classify?.level !== level) return false;
      return true;
    });

    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({
      date: day,
      total: allNews.length,
      filtered: filteredNews.length,
      news: filteredNews.slice(0, limit)
    }));
    return;
  }

  if (url.pathname === '/api/news/heat') {
    const day = normalizeDateParam(url.searchParams.get('date'));
    if (!day) {
      res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'invalid date, expected YYYY-MM-DD' }));
      return;
    }
    const allNews = readNewsByDate(day);
    const heat = buildNewsHeat(allNews);
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({
      date: day,
      total_news: allNews.length,
      by_type: heat.byType,
      by_sector: heat.bySector,
      by_sentiment: heat.bySentiment,
      by_level: heat.byLevel,
      by_type_sentiment: heat.byTypeSentiment,
      by_sector_sentiment: heat.bySectorSentiment
    }));
    return;
  }

  if (url.pathname === '/api/watch-stocks') {
    if (req.method === 'POST') {
      try {
        const raw = await readBody(req);
        const body = raw ? JSON.parse(raw) : {};
        const incoming = body?.stock || body?.code || body?.symbol || '';
        const code = normalizeStockCode(incoming);
        if (!code) {
          res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
          res.end(JSON.stringify({ error: 'stock code is required' }));
          return;
        }
        const list = readWatchStocks();
        if (!list.includes(code)) list.push(code);
        const saved = writeWatchStocks(list);
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ total: saved.length, watch_stocks: saved }));
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ error: 'bad request' }));
      }
      return;
    }
    const list = readWatchStocks();
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ total: list.length, watch_stocks: list }));
    return;
  }

  if (url.pathname === '/api/calendar') {
    const month = normalizeMonthParam(url.searchParams.get('date'));
    if (!month) {
      res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'invalid date, expected YYYY-MM' }));
      return;
    }
    const events = readCalendarEvents().filter((item) => {
      const day = String(item?.date || '').trim();
      return day.startsWith(`${month}-`);
    });
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ month, total: events.length, events }));
    return;
  }

  if (url.pathname === '/api/sector/rank') {
    const day = latestTradingDay();
    const cacheFile = cacheJsonPath('sector-rank', day);
    const cached = readJsonCache(cacheFile);
    if (cached) {
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(cached);
      return;
    }
    execFile('python3', ['fetch_sector_data.py', 'rank'], getExecOptions(), (err, stdout) => {
      if (err) {
        console.error(err);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: "Failed to fetch sector rank" }));
        return;
      }
      const out = (stdout || '').trim();
      if (out && isJsonText(out)) writeJsonCache(cacheFile, out);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(out || '{}');
    });
    return;
  }

  if (url.pathname === '/api/sector/history') {
    const realtime = url.searchParams.get('rt') === '1';
    const sectorsParam = url.searchParams.get('sectors');
    const daysParam = url.searchParams.get('days');
    const days = Number.isFinite(Number(daysParam)) ? Math.max(1, Number(daysParam)) : 20;
    const hasExplicitSectors = !!(sectorsParam && sectorsParam.trim());
    const list = hasExplicitSectors ? sectorsParam.trim() : readWatchList().join(',');
    // 交易日内（含午休）使用实际日期，非交易日使用最近交易日
    const parts = getBeijingParts();
    const today = parts ? parts.date : new Date().toISOString().slice(0, 10);
    const day = isTradingDaySession() ? today : latestTradingDay();
    const cacheFile = !realtime ? sectorCacheFile('sector-history', day, list, days) : null;
    const cfg = readSectorProxyConfig();
    if (cfg.force_etf) {
      const names = list.split(',').map(s => s.trim()).filter(Boolean);
      const variant = 'etf';
      const proxyMap = (cfg.variants && (cfg.variants[variant] || {})) || {};
      const missingNames = names.filter(n => !proxyMap[n]);
      const history = {};
      const minute = {};
      for (const name of names) {
        const code = proxyMap[name] || null;
        if (!code) continue;
        const res = await fetchTencentDaily(code, days);
        history[name] = (res?.data || []).map(r => ({
          date: r.date,
          open: r.open,
          high: r.high,
          low: r.low,
          close: r.close,
          pct: r.pct,
          amount: r.amount,
          volume: r.volume,
          turnover: r.turnover
        }));
        const m = await fetchAshareMinute(code);
        minute[name] = { series: m?.data || [], prevClose: m?.prevClose ?? null };
      }
      const normalized = normalizeHistoryPayloadToDay({ day, history, indicators: {}, minute, correlations: [], watch: names, variant, data_incomplete: missingNames.length > 0, missing: missingNames, source: 'etf_proxy' }, day);
      const payload = JSON.stringify(normalized);
      if (cacheFile && payload && isJsonText(payload)) writeJsonCache(cacheFile, payload);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(payload);
      return;
    }
    let staleCached = null;
    if (cacheFile) {
      const cached = readJsonCache(cacheFile);
      if (cached) {
        try {
          const p = JSON.parse(cached);
          const history = p?.history || {};
          let latest = null;
          Object.values(history).forEach((arr) => {
            if (!Array.isArray(arr) || !arr.length) return;
            const d = arr[arr.length - 1]?.date;
            if (d && (!latest || d > latest)) latest = d;
          });
          const gap = latest ? dateDiffDays(day, latest) : null;
          const tooOld = gap != null && gap > 2;
          if (latest && !tooOld && String(latest).localeCompare(day) >= 0) {
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(cached);
            return;
          }
          // 交易日内（含午休）不使用缓存，获取实时数据
          const inSession = isTradingDaySession();
          if (!realtime && !tooOld && isAfterCloseNow()) {
            staleCached = cached;
          } else if (!realtime && !tooOld && !inSession) {
            // 非交易时段才使用缓存
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(cached);
            warmupSectorCache('history_dynamic', list, days, cacheFile);
            return;
          } else if (tooOld) {
            staleCached = cached;
          }
        } catch (e) {
          console.error(e);
        }
      }
    }
    if (!hasExplicitSectors) {
      const fallbackFile = findLatestCacheFile('sector-history');
      if (fallbackFile) {
        const cached = readJsonCache(fallbackFile);
        if (cached) {
          try {
            const p = JSON.parse(cached);
            const history = p?.history || {};
            let latest = null;
            Object.values(history).forEach((arr) => {
              if (!Array.isArray(arr) || !arr.length) return;
              const d = arr[arr.length - 1]?.date;
              if (d && (!latest || d > latest)) latest = d;
            });
            const gap = latest ? dateDiffDays(day, latest) : null;
            const tooOld = gap != null && gap > 2;
            const inSession = isTradingDaySession();
            if (!realtime && !tooOld && isAfterCloseNow()) {
              staleCached = cached;
            } else if (!realtime && !tooOld && !inSession) {
              // 非交易时段才使用fallback缓存
              res.setHeader('Content-Type', 'application/json; charset=utf-8');
              res.end(cached);
              if (cacheFile) warmupSectorCache('history_dynamic', list, days, cacheFile);
              return;
            } else if (tooOld) {
              staleCached = cached;
            }
          } catch (e) {
            console.error(e);
          }
        }
      }
    }
    const useDynamic = list && list.trim();
    const args = ['fetch_sector_data.py', useDynamic ? 'history_dynamic' : 'history'];
    if (useDynamic) {
      args.push(list);
      args.push(String(days));
    } else {
      args.push(String(days));
    }
    const inTradingSession = isTradingDaySession();
    if (!inTradingSession) {
      if (staleCached) {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(staleCached);
        return;
      }
      const opts = { ...getExecOptions(), env: { ...getExecOptions().env || process.env, CACHE_ONLY: '1' } };
    execFile('python3', args, opts, (err, stdout) => {
        const out = (stdout || '').trim();
        if (!err && out && isJsonText(out)) {
          if (cacheFile) writeJsonCache(cacheFile, out);
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(out);
          return;
        }
        const names = list.split(',').map(s => s.trim()).filter(Boolean);
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ day, history: {}, indicators: {}, minute: {}, correlations: [], watch: names, data_incomplete: true, reason: 'market_closed' }));
      });
      return;
    }
    execFile('python3', args, getExecOptions(), (err, stdout) => {
      if (err) {
        console.error(err);
        if (staleCached) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(staleCached);
          if (cacheFile) warmupSectorCache('history_dynamic', list, days, cacheFile);
          return;
        }
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: "Failed to fetch sector history" }));
        return;
      }
      const out = (stdout || '').trim();
      if (cacheFile && out && isJsonText(out)) writeJsonCache(cacheFile, out);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(out || '{}');
    });
    return;
  }

  if (url.pathname === '/api/sector/warmup') {
    const sectorsParam = url.searchParams.get('sectors');
    const daysParam = url.searchParams.get('days');
    const startParam = url.searchParams.get('start');
    const endParamRaw = url.searchParams.get('end');
    const endTradingDay = latestTradingDay();
    const endParam = (endParamRaw && endParamRaw.trim()) ? endParamRaw.trim() : endTradingDay;
    let days = Number.isFinite(Number(daysParam)) ? Math.max(10, Number(daysParam)) : 60;
    if (startParam && endParam) {
      try {
        const start = new Date(String(startParam).trim());
        const end = new Date(String(endParam).trim());
        const delta = Math.ceil((end.getTime() - start.getTime()) / (24 * 3600 * 1000)) + 1;
        if (Number.isFinite(delta) && delta > 0) days = Math.max(10, delta);
      } catch (e) {
        void e;
      }
    }
    const list = sectorsParam && sectorsParam.trim() ? sectorsParam.trim() : readWatchList().join(',');
    const day = endParam;
    const historyCache = sectorCacheFile('sector-history', day, list, days);
    const lifecycleCache = sectorCacheFile('sector-lifecycle', day, list, days);
    const rotationCache = sectorCacheFile('sector-rotation', day, list, Math.max(90, days));
    const status = {
      history: warmupSectorCache('history_dynamic', list, days, historyCache),
      lifecycle: warmupSectorCache('lifecycle_dynamic', list, days, lifecycleCache),
      rotation: warmupSectorCache('rotation_dynamic', list, Math.max(90, days), rotationCache)
    };
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ day, start: startParam || null, end: endParam, status, days }));
    return;
  }

  if (url.pathname === '/api/sector/proxy') {
    if (req.method === 'GET') {
      const dir = path.join(__dirname, 'data');
      fs.mkdirSync(dir, { recursive: true });
      let json = readJsonFileSafe(PROXY_FILE);
      if (!json || typeof json !== 'object') {
        json = {
          default_variant: 'etf',
          force_etf: false,
          variants: {
            etf: {
              "半导体": "sz159995",
              "云计算": "sh516510",
              "新能源": "sh516160",
              "商业航天": "sh563530",
              "创新药": "sz159992",
              "有色金属": "sh512400",
              "通讯设备": "sh515050"
            },
            index: {
              "半导体": "sh000990",
              "云计算": "sh000941",
              "新能源": "sh000941",
              "商业航天": "BK0963",
              "创新药": "sz399989",
              "有色金属": "sh000819",
              "通讯设备": "sh000997"
            }
          },
          updated_at: new Date().toISOString()
        };
        fs.writeFileSync(PROXY_FILE, JSON.stringify(json, null, 2));
      }
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify(readSectorProxyConfig()));
      return;
    }
    if (req.method === 'POST') {
      const raw = await readBody(req);
      let body = {};
      try { body = raw ? JSON.parse(raw) : {}; } catch (e) { body = {}; }
      const dir = path.join(__dirname, 'data');
      fs.mkdirSync(dir, { recursive: true });
      const cur = readJsonFileSafe(PROXY_FILE) || {};
      const next = {
        default_variant: String(body.default_variant || cur.default_variant || 'etf'),
        force_etf: typeof body.force_etf === 'boolean' ? body.force_etf : !!cur.force_etf,
        variants: Object.assign({}, cur.variants || {}, body.variants || {}),
        updated_at: new Date().toISOString()
      };
      fs.writeFileSync(PROXY_FILE, JSON.stringify(next, null, 2));
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify(next));
      return;
    }
    res.writeHead(405, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'method_not_allowed' }));
    return;
  }

  if (url.pathname === '/api/sector/force_etf') {
    if (req.method !== 'POST') {
      res.writeHead(405, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'method_not_allowed' }));
      return;
    }
    const raw = await readBody(req);
    let body = {};
    try { body = raw ? JSON.parse(raw) : {}; } catch (e) { body = {}; }
    const dir = path.join(__dirname, 'data');
    fs.mkdirSync(dir, { recursive: true });
    const cur = readJsonFileSafe(PROXY_FILE) || {};
    const force = typeof body.force_etf === 'boolean' ? body.force_etf : true;
    const next = {
      default_variant: String(cur.default_variant || 'etf'),
      force_etf: force,
      variants: Object.assign({}, cur.variants || {}),
      updated_at: new Date().toISOString()
    };
    fs.writeFileSync(PROXY_FILE, JSON.stringify(next, null, 2));
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify(next));
    return;
  }

  if (url.pathname === '/api/sector/history_proxy') {
    const sectorsParam = url.searchParams.get('sectors');
    const daysParam = url.searchParams.get('days');
    const force = url.searchParams.get('force') === '1';
    const days = Number.isFinite(Number(daysParam)) ? Math.max(10, Number(daysParam)) : 60;
    const list = sectorsParam && sectorsParam.trim() ? sectorsParam.trim() : readWatchList().join(',');
    const names = list.split(',').map(s => s.trim()).filter(Boolean);
    const day = latestTradingDay();
    const cacheFile = sectorCacheFile('sector-history-proxy', day, list, days);
    const cfg = readSectorProxyConfig();
    const variant = cfg.force_etf ? 'etf' : (cfg.default_variant || 'etf');
    const proxyMap = (cfg.variants && (cfg.variants[variant] || {})) || {};
    const missingNames = names.filter(n => !proxyMap[n]);
    const allowFetch = force || isMarketOpenNow();
    if (!allowFetch) {
      // ✅ 在检查缓存之前先检查warmup文件
      const warmupFile = path.join(__dirname, 'data', `sector-history-warmup-60.json`);
      if (fs.existsSync(warmupFile)) {
        try {
          const txt = fs.readFileSync(warmupFile, 'utf-8');
          if (txt && isJsonText(txt)) {
            const obj = JSON.parse(txt);
            obj.variant = obj.variant || variant;
            obj.data_incomplete = missingNames.length > 0;
            obj.missing = missingNames;
            obj.source = 'etf_proxy_warmup';
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify(obj));
            return;
          }
        } catch (e) {
          console.error('Warmup读取错误:', e);
        }
      }
      const cached = readJsonCache(cacheFile);
      if (cached) {
        try {
          const obj = JSON.parse(cached);
          const normalized = normalizeHistoryPayloadToDay(obj, day);
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify(normalized));
        } catch (e) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(cached);
        }
        return;
      }
      const latestCached = findLatestCacheFileOnOrBefore('sector-history-proxy', day);
      if (latestCached) {
        const txt = readJsonCache(latestCached);
        if (txt) {
          try {
            const obj = JSON.parse(txt);
            const normalized = normalizeHistoryPayloadToDay(obj, day);
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify(normalized));
          } catch (e) {
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(txt);
          }
          return;
        }
      }
      const fallbackFile = findLatestCacheFileOnOrBefore('sector-history', null);
      if (fallbackFile) {
        const txt = readJsonCache(fallbackFile);
        if (txt && isJsonText(txt)) {
          try {
            const obj = JSON.parse(txt);
            const normalized = normalizeHistoryPayloadToDay(obj, day);
            normalized.variant = variant;
            normalized.data_incomplete = true;
            normalized.missing = missingNames;
            normalized.source = 'fallback_index';
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify(normalized));
            return;
          } catch (e) {
            void e;
          }
        }
      }
      // 没有缓存数据且非交易时间，返回空数据
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ day, history: {}, indicators: {}, minute: {}, correlations: [], watch: names, variant, data_incomplete: true, missing: missingNames, reason: 'market_closed', source: 'etf_proxy' }));
      return;
    }
    const history = {};
    const minute = {};
    const fetchOne = async (name) => {
      const code = proxyMap[name] || null;
      if (!code) return;
      const res = await fetchTencentDaily(code, days);
      const arr = (res?.data || []).map(r => ({
        date: r.date,
        open: r.open,
        high: r.high,
        low: r.low,
        close: r.close,
        pct: r.pct,
        amount: r.amount,
        volume: r.volume,
        turnover: r.turnover
      }));
      history[name] = arr;

      // ETF分时数据获取
      const cleanCode = code.replace(/sh|sz|SH|SZ/g, '');
      const isETF = /^\d{6}$/.test(cleanCode) && ['5', '1'].includes(cleanCode[0]);
      let m;
      if (isETF) {
        // ETF分时数据
        try {
          const pyResult = await new Promise((resolve) => {
            execFile('python3', ['fetch_sector_data.py', 'etf-minute', code], { timeout: 30000 }, (err, stdout, stderr) => {
              if (err) {
                console.error(`ETF minute error for ${code}:`, err, stderr);
                resolve({ data: [], prevClose: null });
              } else {
                try {
                  const parsed = JSON.parse(stdout);
                  resolve(parsed);
                } catch (e) {
                  console.error(`ETF minute parse error for ${code}:`, e);
                  resolve({ data: [], prevClose: null });
                }
              }
            });
          });
          // 转换数据格式
          m = {
            data: (pyResult.data || []).map(item => ({
              time: item.time,
              close: item.price,
              price: item.price
            })),
            prevClose: pyResult.prevClose ?? null
          };
        } catch (e) {
          console.error(`ETF minute fetch failed for ${code}:`, e);
          m = { data: [], prevClose: null };
        }
      } else {
        // 板块分时数据
        m = await fetchAshareMinute(code);
      }
      minute[name] = { series: m?.data || [], prevClose: m?.prevClose ?? null };
    };
    try {
      for (const n of names) { await fetchOne(n); }
      const normalized = normalizeHistoryPayloadToDay({ day, history, indicators: {}, minute, correlations: [], watch: names, variant, data_incomplete: missingNames.length > 0, missing: missingNames, source: 'etf_proxy' }, day);
      const payload = JSON.stringify(normalized);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(payload);
      if (payload && isJsonText(payload)) writeJsonCache(cacheFile, payload);
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'proxy_history_failed' }));
    }
    return;
  }

  if (url.pathname === '/api/sector/rotation_proxy') {
    const sectorsParam = url.searchParams.get('sectors');
    const daysParam = url.searchParams.get('days');
    const force = url.searchParams.get('force') === '1';
    const days = Number.isFinite(Number(daysParam)) ? Math.max(30, Number(daysParam)) : 90;
    const list = sectorsParam && sectorsParam.trim() ? sectorsParam.trim() : readWatchList().join(',');
    const names = list.split(',').map(s => s.trim()).filter(Boolean);
    const day = latestTradingDay();
    const cacheFile = sectorCacheFile('sector-rotation-proxy', day, list, days);
    const cfg = readSectorProxyConfig();
    const variant = cfg.force_etf ? 'etf' : (cfg.default_variant || 'etf');
    const proxyMap = (cfg.variants && (cfg.variants[variant] || {})) || {};
    const missingNames = names.filter(n => !proxyMap[n]);
    const allowFetch = force || isMarketOpenNow();
    if (!allowFetch) {
      const cached = readJsonCache(cacheFile);
      if (cached) {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(cached);
        return;
      }
      const latestCached = findLatestCacheFileOnOrBefore('sector-rotation-proxy', day);
      if (latestCached) {
        const txt = readJsonCache(latestCached);
        if (txt) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(txt);
          return;
        }
      }
      const fallbackFile = findLatestCacheFileOnOrBefore('sector-rotation', day);
      if (fallbackFile) {
        const txt = readJsonCache(fallbackFile);
        if (txt && isJsonText(txt)) {
          try {
            const obj = JSON.parse(txt);
            obj.variant = variant;
            obj.data_incomplete = true;
            obj.missing = missingNames;
            obj.source = 'fallback_index';
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify(obj));
            return;
          } catch (e) {
            void e;
          }
        }
      }
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ day, mainline: [], groups: {}, reason: 'market_closed', data_incomplete: true, variant, missing: missingNames, source: 'etf_proxy' }));
      return;
    }
    const seriesMap = {};
    const fetchOne = async (name) => {
      const code = proxyMap[name] || null;
      if (!code) return;
      const res = await fetchTencentDaily(code, days);
      seriesMap[name] = res?.data || [];
    };
    const pctChange = (arr, k) => {
      if (!Array.isArray(arr) || arr.length <= k) return null;
      const a = Number(arr[arr.length - 1]?.close);
      const b = Number(arr[arr.length - 1 - k]?.close);
      if (!Number.isFinite(a) || !Number.isFinite(b) || b === 0) return null;
      return +(((a - b) / b) * 100).toFixed(2);
    };
    const avg = (xs) => {
      const arr = xs.filter((n) => Number.isFinite(Number(n))).map(Number);
      if (!arr.length) return null;
      const s = arr.reduce((p, c) => p + c, 0);
      return +(s / arr.length).toFixed(2);
    };
    const volChange = (arr) => {
      if (!Array.isArray(arr) || arr.length < 21) return null;
      const last5 = arr.slice(-5).map(r => Number(r.volume));
      const last20 = arr.slice(-20, -5).map(r => Number(r.volume));
      const a = avg(last5);
      const b = avg(last20);
      if (!Number.isFinite(a) || !Number.isFinite(b) || b === 0) return null;
      return +(((a - b) / b) * 100).toFixed(2);
    };
    const momentumTag = (c5, c20) => {
      const a = Number(c5), b = Number(c20);
      if (Number.isFinite(a) && Number.isFinite(b)) {
        if (a >= 2 && b >= 4) return '强势向上';
        if (a >= 1 && b >= 2) return '偏强向上';
        if (a <= -1 && b <= -2) return '向下';
        return '中性震荡';
      }
      return '中性震荡';
    };
    const behaviorTag = (v) => {
      const x = Number(v);
      if (!Number.isFinite(x)) return '横盘整理';
      if (x >= 10) return '放量启动';
      if (x <= -10) return '缩量回落';
      return '趋势延续';
    };
    try {
      for (const n of names) { await fetchOne(n); }
      const items = [];
      let latest = null;
      names.forEach((name) => {
        const arr = seriesMap[name] || [];
        if (!arr.length) return;
        const lastDate = arr[arr.length - 1]?.date;
        if (lastDate && (!latest || lastDate > latest)) latest = lastDate;
        const c5 = pctChange(arr, 5);
        const c20 = pctChange(arr, 20);
        const vchg = volChange(arr);
        const score = (Number(c5) || 0) * 1.5 + (Number(c20) || 0) * 1.0 + (Number(vchg) || 0) * 0.1;
        const momentum = momentumTag(c5, c20);
        const behavior = behaviorTag(vchg);
        let advice = '观望';
        if (momentum === '强势向上') advice = '建仓';
        else if (momentum === '偏强向上') advice = '持有';
        else if (momentum === '向下') advice = '减仓';
        items.push({
          "板块名称": name,
          "动能": momentum,
          "资金行为": behavior,
          "操作建议": advice,
          "指标数据": { "alpha_5": c5, "alpha_20": c20, "Amount_Share_Change": null },
          "_score": +score.toFixed(3)
        });
      });
      const ranked = items.slice().sort((a, b) => (Number(b?._score) || 0) - (Number(a?._score) || 0));
      const mainline = ranked.slice(0, 3).map((it) => {
        const ind = it["指标数据"] || {};
        return {
          "板块名称": it["板块名称"],
          "动能": it["动能"],
          "资金行为": it["资金行为"],
          "操作建议": it["操作建议"],
          "Alpha_5": ind.alpha_5,
          "Alpha_20": ind.alpha_20
        };
      });
      const profile = readSectorProfile();
      const groups = profile.groups || {};
      const grpScores = {};
      Object.keys(groups).forEach((n) => {
        const g = groups[n];
        const it = items.find(x => x["板块名称"] === n);
        if (!it) return;
        const v = Number(it?._score) || 0;
        grpScores[g] = (grpScores[g] || 0) + v;
      });
      const resVsTech = (grpScores['资源'] || 0) - ((grpScores['硬件'] || 0) + (grpScores['软件'] || 0));
      const seesaw = resVsTech > 0.6 ? '资源强' : (resVsTech < -0.6 ? '科技强' : '平衡');
      const diffusion = (grpScores['硬件'] || 0) - (grpScores['软件'] || 0);
      const diffusionTag = diffusion > 0.5 ? '硬件领先' : (diffusion < -0.5 ? '软件补涨' : '同步');
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      const payload = JSON.stringify({
        day: latest || latestTradingDay(),
        rotation: { leader: mainline[0]?.['板块名称'] || '-', seesaw, diffusion: diffusionTag, resonance: false, resonance_reason: '' },
        mainline,
        variant,
        watch: names,
        data_incomplete: missingNames.length > 0,
        missing: missingNames,
        source: 'etf_proxy'
      });
      res.end(payload);
      if (payload && isJsonText(payload)) writeJsonCache(cacheFile, payload);
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'rotation_proxy_failed' }));
    }
    return;
  }

  if (url.pathname === '/api/sector/rotation/intraday') {
    const view = (url.searchParams.get('view') || '').trim() === 'detail' ? 'detail' : 'summary';
    const sectorsParam = url.searchParams.get('sectors');
    const daysParam = url.searchParams.get('days');
    const days = Number.isFinite(Number(daysParam)) ? Math.max(1, Number(daysParam)) : 20;
    const list = sectorsParam && sectorsParam.trim() ? sectorsParam.trim() : readWatchList().join(',');
    const day = latestTradingDay();
    const marketOpen = isMarketOpenNow();
    const intradayFile = intradayRotationPath(day, view);
    const cachedText = readJsonCache(intradayFile);
    if (cachedText) {
      try {
        const age = now() - fs.statSync(intradayFile).mtimeMs;
        if (!marketOpen || age < INTRADAY_CACHE_TTL_MS) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(cachedText);
          return;
        }
      } catch (e) {
        void e;
      }
    }
    const profile = readSectorProfile();
    const groups = profile.groups || {};
    if (!marketOpen && lastIntradayRotation.payload && lastIntradayRotation.day === day) {
      const bars = lastIntradayRotation.payload?.bars || [];
      if (Array.isArray(bars) && bars.length) {
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ day, ts: lastIntradayRotation.ts, intraday: lastIntradayRotation.payload }));
      return;
      }
    }
    try {
      const historyCache = sectorCacheFile('sector-history', day, list, days);
      const lifecycleCache = sectorCacheFile('sector-lifecycle', day, list, Math.max(20, days));
      let hist = null;
      let life = null;
      const cachedHistory = readJsonCache(historyCache);
      if (cachedHistory) {
        try { hist = JSON.parse(cachedHistory); } catch (e) { hist = null; }
      }
      if (!hist) {
        const alt = findLatestSectorHistoryCache(day);
        if (alt) {
          try { hist = JSON.parse(alt); } catch (e) { hist = null; }
        }
      }
      const cachedLifecycle = readJsonCache(lifecycleCache);
      if (cachedLifecycle) {
        try { life = JSON.parse(cachedLifecycle); } catch (e) { life = null; }
      }
      const cfg = readSectorProxyConfig();
      const variant = cfg.force_etf ? 'etf' : (cfg.default_variant || 'etf');
      const proxyMap = (cfg.variants && cfg.variants[variant]) || {};
      if (!hist || !hist.minute || !Object.keys(hist.minute || {}).length) {
        const minute = {};
        const names = list.split(',').map(s => s.trim()).filter(Boolean);
        if (marketOpen) {
          for (const n of names) {
            const code = proxyMap[n] || null;
            if (!code) continue;
            const m = await fetchAshareMinute(code);
            minute[n] = { series: m?.data || [], prevClose: m?.prevClose ?? null };
          }
        }
        if (!hist) hist = {};
        hist.minute = minute;
        hist.watch = names;
      }
      if (!hist) {
        hist = await execPythonJson(['fetch_sector_data.py', 'history_dynamic', list, String(days)], 90000);
        if (hist) writeJsonCache(historyCache, JSON.stringify(hist));
      }
      if (!life) {
        life = await execPythonJson(['fetch_sector_data.py', 'lifecycle_dynamic', list, String(Math.max(20, days))], 90000);
        if (life) writeJsonCache(lifecycleCache, JSON.stringify(life));
      }
      const payload = buildIntradayBars(hist || {}, life || {}, groups, view);
      const leader = payload?.bars?.[0]?.group || '';
      let signal = payload.signal;
      let reason = payload.reason;
      const nowTs = now();
      if (leader && lastIntradayRotation.leader && leader !== lastIntradayRotation.leader) {
        if (nowTs - lastIntradayRotation.signalTs < INTRADAY_DEBOUNCE_MS) {
          signal = lastIntradayRotation.signal;
          reason = lastIntradayRotation.reason;
        } else {
          signal = `${leader}转强`;
          reason = payload.reason;
        }
      }
      payload.signal = signal;
      payload.reason = reason;
      lastIntradayRotation.payload = payload;
      lastIntradayRotation.ts = nowTs;
      lastIntradayRotation.day = day;
      lastIntradayRotation.leader = leader;
      lastIntradayRotation.signal = signal;
      lastIntradayRotation.reason = reason;
      lastIntradayRotation.signalTs = nowTs;
      const response = { day, ts: lastIntradayRotation.ts, intraday: payload };
      const responseText = JSON.stringify(response);
      writeJsonCache(intradayFile, responseText);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(responseText);
    } catch (e) {
      if (cachedText) {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(cachedText);
        return;
      }
      const fallback = lastIntradayRotation.payload ? { day: lastIntradayRotation.day || day, ts: lastIntradayRotation.ts || now(), intraday: lastIntradayRotation.payload } : { day, ts: now(), intraday: { bars: [], signal: '数据缺失', reason: [] } };
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify(fallback));
    }
    return;
  }

  if (url.pathname === '/api/sector/rotation/sequence') {
    const rt = url.searchParams.get('rt') === '1';
    const sectorsParam = url.searchParams.get('sectors');
    const daysParam = url.searchParams.get('days');
    const days = Number.isFinite(Number(daysParam)) ? Math.max(10, Number(daysParam)) : 60;
    const list = sectorsParam && sectorsParam.trim() ? sectorsParam.trim() : readWatchList().join(',');
    const day = latestTradingDay();
    if (!rt) {
      const cached = readRotationSequence(day);
      if (cached) {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(cached);
        return;
      }
      const latest = readLatestRotationSequence();
      if (latest) {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(latest);
        return;
      }
    }
    const file = rotationSequencePath(day);
    const payload = await execPythonJson(['fetch_sector_data.py', 'rotation_sequence', list, String(days)], 90000);
    if (payload) {
      const txt = JSON.stringify(payload);
      writeJsonCache(file, txt);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(txt);
      return;
    }
    const latest = readLatestRotationSequence();
    if (latest) {
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(latest);
      return;
    }
    res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'sequence_failed' }));
    return;
  }
  if (url.pathname === '/api/sector/lifecycle_proxy') {
    url.pathname = '/api/sector/lifecycle';
  }
  if (url.pathname === '/api/sector/lifecycle') {
    const realtime = url.searchParams.get('rt') === '1';
    const sectorsParam = url.searchParams.get('sectors');
    const daysParam = url.searchParams.get('days');
    const force = url.searchParams.get('force') === '1';
    const days = Number.isFinite(Number(daysParam)) ? Math.max(1, Number(daysParam)) : 60;
    const list = sectorsParam && sectorsParam.trim() ? sectorsParam.trim() : readWatchList().join(',');
    const day = latestTradingDay();
    const cacheFile = !realtime ? sectorCacheFile('sector-lifecycle', day, list, days) : null;
    if (cacheFile) {
      const cached = readJsonCache(cacheFile);
      if (cached && isJsonText(cached)) {
        const obj = JSON.parse(cached);
        const dataDay = obj.day || '';

        // 盘后模式：交易时间内允许返回上一交易日数据
        const isMarketOpen = isMarketOpenNow();
        const parts = getBeijingParts();
        const minutes = parts && parts.minutes ? parts.minutes : 0;
        const isAfterWarmup = minutes >= 930; // 15:30之后

        let validationPassed = true;
        let expectedDay = null;

        if (isMarketOpen || !isAfterWarmup) {
          // 盘后模式：使用warmup的日期验证
          const warmupPath = path.join(__dirname, 'data', 'sector-history-warmup-60.json');
          if (fs.existsSync(warmupPath)) {
            try {
              const warmupData = JSON.parse(fs.readFileSync(warmupPath, 'utf-8'));
              expectedDay = warmupData.day || null;
              if (expectedDay && dataDay !== expectedDay) {
                console.warn(`[lifecycle] 缓存验证失败: 数据=${dataDay}, warmup=${expectedDay}`);
                validationPassed = false;
              }
            } catch (e) {
              // 忽略验证错误
            }
          }
        } else {
          // 非交易时间且15:30后：使用常规验证
          const today = latestTradingDay();
          if (dataDay !== today) {
            validationPassed = false;
            expectedDay = today;
          }
        }

        if (!validationPassed) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ day: expectedDay || dataDay, items: [], data_incomplete: true, reason: 'trading_day_mismatch' }));
          return;
        }
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(cached);
        return;
      }
    }
    const useDynamic = list && list.trim();
    const cfg = readSectorProxyConfig();
    const forceEnv = cfg.force_etf ? '1' : '0';
    const args = ['fetch_sector_data.py', useDynamic ? 'lifecycle_dynamic' : 'lifecycle'];
    if (useDynamic) {
      args.push(list);
      args.push(String(days));
    } else {
      args.push(String(days));
    }
    const allowFetch = force || isMarketOpenNow();
    if (!allowFetch) {
      if (!realtime) {
        const latestFile = findLatestCacheFileOnOrBefore('sector-lifecycle', null);
        if (latestFile) {
          const txt = readJsonCache(latestFile);
          if (txt && isJsonText(txt)) {
            const obj = JSON.parse(txt);
            const dataDay = obj.day || '';
            const today = latestTradingDay();
            if (dataDay === today) {
              res.setHeader('Content-Type', 'application/json; charset=utf-8');
              res.end(txt);
              return;
            }
          }
        }
      }
      const opts = { ...getExecOptions(), env: { ...getExecOptions().env || process.env, CACHE_ONLY: '1', FORCE_SECTOR_ETF: forceEnv } };
      execFile('python3', args, opts, (err, stdout) => {
        const out = (stdout || '').trim();
        if (!err && out && isJsonText(out)) {
          const obj = JSON.parse(out);
          const dataDay = obj.day || '';
          const today = latestTradingDay();
          if (dataDay !== today) {
            console.warn(`交易日验证失败(CACHE_ONLY): 数据=${dataDay}, 预期=${today}`);
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify({ day: today, items: [], data_incomplete: true, reason: 'trading_day_mismatch' }));
            return;
          }
          if (cacheFile) writeJsonCache(cacheFile, JSON.stringify(obj));
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify(obj));
          return;
        }
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ day, items: [], data_incomplete: true, reason: 'market_closed' }));
      });
      return;
    }
    const opts = { ...getExecOptions(), env: { ...getExecOptions().env || process.env, FORCE_SECTOR_ETF: forceEnv } };
    execFile('python3', args, opts, (err, stdout) => {
      if (err) {
        console.error(err);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: "Failed to fetch sector lifecycle" }));
        return;
      }
      const out = (stdout || '').trim();
      if (out && isJsonText(out)) {
        const obj = JSON.parse(out);
        const dataDay = obj.day || '';

        // 盘后模式：交易时间内允许返回上一交易日数据
        // warmup在15:30更新，更新前都应显示上一交易日数据
        const isMarketOpen = isMarketOpenNow();
        const parts = getBeijingParts();
        const minutes = parts && parts.minutes ? parts.minutes : 0;
        const isAfterWarmup = minutes >= 930; // 15:30之后

        let validationPassed = true;
        let expectedDay = null;

        if (isMarketOpen || !isAfterWarmup) {
          // 盘后模式：使用warmup的日期验证
          const warmupPath = path.join(__dirname, 'data', 'sector-history-warmup-60.json');
          if (fs.existsSync(warmupPath)) {
            try {
              const warmupData = JSON.parse(fs.readFileSync(warmupPath, 'utf-8'));
              expectedDay = warmupData.day || null;
              if (expectedDay && dataDay !== expectedDay) {
                console.warn(`[lifecycle] 交易日验证: 数据=${dataDay}, warmup=${expectedDay}`);
                validationPassed = false;
              }
            } catch (e) {
              console.error(`[lifecycle] warmup读取失败: ${e.message}`);
            }
          }
        } else {
          // 非交易时间且15:30后：使用常规验证
          const today = latestTradingDay();
          if (dataDay !== today) {
            console.warn(`交易日验证失败: 数据=${dataDay}, 预期=${today}`);
            validationPassed = false;
            expectedDay = today;
          }
        }

        if (!validationPassed) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ day: expectedDay || dataDay, items: [], data_incomplete: true, reason: 'trading_day_mismatch' }));
          return;
        }
        // 按评分排序并添加Top排名
        if (Array.isArray(obj.items)) {
          obj.items.sort((a, b) => (b._score || 0) - (a._score || 0));
          obj.items.forEach((item, idx) => {
            item._rank = idx + 1;
          });
        }
        if (cacheFile) writeJsonCache(cacheFile, JSON.stringify(obj));
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify(obj));
      } else {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end('{}');
      }
    });
    return;
  }

  if (url.pathname === '/api/sector/lifecycle/frontend') {
    const today = new Date().toISOString().split('T')[0].replace(/-/g, '');
    const frontendFile = path.join(__dirname, 'logs', `operation_frontend_${today}.json`);

    // 尝试读取今天的文件
    if (fs.existsSync(frontendFile)) {
      const data = fs.readFileSync(frontendFile, 'utf-8');
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(data);
      return;
    }

    // 如果今天的文件不存在，查找最新的文件
    const logsDir = path.join(__dirname, 'logs');
    if (fs.existsSync(logsDir)) {
      const files = fs.readdirSync(logsDir)
        .filter(f => f.startsWith('operation_frontend_') && f.endsWith('.json'))
        .sort()
        .reverse();

      if (files.length > 0) {
        const latestFile = path.join(logsDir, files[0]);
        const data = fs.readFileSync(latestFile, 'utf-8');
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(data);
        return;
      }
    }

    // 如果没有任何文件，返回空结果
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ date: today, items: [] }));
    return;
  }

  if (url.pathname === '/api/sector/rotation') {
    const realtime = url.searchParams.get('rt') === '1';
    const sectorsParam = url.searchParams.get('sectors');
    const daysParam = url.searchParams.get('days');
    const days = Number.isFinite(Number(daysParam)) ? Math.max(1, Number(daysParam)) : 90;
    const list = sectorsParam && sectorsParam.trim() ? sectorsParam.trim() : readWatchList().join(',');
    const day = latestTradingDay();
    if (!realtime) {
      const snap = readRotationSnapshot(day);
      if (snap) {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(snap);
        return;
      }
      const latestFile = findLatestRotationSnapshot();
      if (latestFile) {
        const txt = fs.readFileSync(latestFile, 'utf-8').trim();
        if (txt) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(txt);
          return;
        }
      }
    }
    const cacheFile = !realtime ? sectorCacheFile('sector-rotation', day, list, days) : null;
    if (cacheFile) {
      const cached = readJsonCache(cacheFile);
      if (cached) {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(cached);
        return;
      }
    }
    const useDynamic = list && list.trim();
    const args = ['fetch_sector_data.py', useDynamic ? 'rotation_dynamic' : 'rotation'];
    if (useDynamic) {
      args.push(list);
      args.push(String(days));
    } else {
      args.push(String(days));
    }
    if (!isMarketOpenNow()) {
      const opts = { ...getExecOptions(), env: { ...getExecOptions().env || process.env, CACHE_ONLY: '1' } };
      execFile('python3', args, opts, (err, stdout) => {
        const out = (stdout || '').trim();
        if (!err && out && isJsonText(out)) {
          if (cacheFile) writeJsonCache(cacheFile, out);
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(out);
          return;
        }
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ day, mainline: [], groups: {}, data_incomplete: true, reason: 'market_closed' }));
      });
      return;
    }
    execFile('python3', args, getExecOptions(), (err, stdout) => {
      if (err) {
        console.error(err);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: "Failed to fetch sector rotation" }));
        return;
      }
      const out = (stdout || '').trim();
      if (cacheFile && out && isJsonText(out)) writeJsonCache(cacheFile, out);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(out || '{}');
    });
    return;
  }

  if (url.pathname === '/api/sector/profile') {
    if (req.method === 'POST') {
      try {
        const raw = await readBody(req);
        const body = raw ? JSON.parse(raw) : {};
        const groups = body?.groups || {};
        const customGroups = body?.custom_groups || [];
        const etfBindings = body?.etf_bindings || {};
        // 保存配置
        const payload = writeSectorProfile(groups, customGroups, etfBindings);
        // 同步 ETF 绑定到 sector-proxy.json
        updateSectorProxyEtfBindings(etfBindings);
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify(payload));
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ error: 'bad request' }));
      }
      return;
    }
    const payload = readSectorProfile();
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify(payload));
    return;
  }

  // ETF 代码验证接口
  if (url.pathname === '/api/sector/verify-etf') {
    const code = url.searchParams.get('code');
    if (!code) {
      res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'missing code parameter' }));
      return;
    }
    // 格式验证
    if (!/^(sh|sz)\d{6}$/.test(code)) {
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ valid: false, code, error: '格式错误，应为 sh/sz + 6位数字' }));
      return;
    }
    // 调用 Python 验证数据可用性
    const { execFile } = require('child_process');
    const pyCode = `
import sys
import json
try:
    import akshare as ak
    code = sys.argv[1]
    clean_code = code.replace('sh', '').replace('sz', '')
    df = ak.fund_etf_hist_em(symbol=clean_code, period="daily", start_date="20240101", end_date="21231231", adjust="qfq")
    if df is None or df.empty:
        print(json.dumps({"valid": False, "error": "无数据"}))
    else:
        count = len(df)
        start_date = str(df.iloc[0]['日期']) if '日期' in df.columns else str(df.index[0])
        print(json.dumps({"valid": True, "count": count, "start_date": start_date, "warning": ("数据不足300天" if count < 300 else None)}))
except Exception as e:
    print(json.dumps({"valid": False, "error": str(e)}))
`;
    execFile('python3', ['-c', pyCode, code], { timeout: 30000 }, (err, stdout, stderr) => {
      if (err) {
        console.error('ETF验证执行失败:', err, stderr);
      }
      let result = { valid: false, code, error: '验证失败' };
      try {
        if (stdout) {
          const parsed = JSON.parse(stdout.trim());
          result = { valid: parsed.valid, code, count: parsed.count, start_date: parsed.start_date, warning: parsed.warning, error: parsed.error };
        } else if (stderr) {
          result.error = '执行错误: ' + stderr.substring(0, 100);
        }
      } catch (e) {
        result.error = '解析失败: ' + (stdout || stderr || e.message).substring(0, 100);
      }
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify(result));
    });
    return;
  }

  if (url.pathname === '/api/sector/watch-list') {
    if (req.method === 'POST') {
      try {
        const raw = await readBody(req);
        const body = raw ? JSON.parse(raw) : {};
        const list = writeWatchList(body?.watch_list || body?.list || body?.sectors || []);
        execFile('python3', ['fetch_sector_data.py', 'history_dynamic', list.join(','), '20'], () => {});
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ watch_list: list }));
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ error: 'bad request' }));
      }
      return;
    }
    const list = readWatchList();
    execFile('python3', ['fetch_sector_data.py', 'history_dynamic', list.join(','), '20'], () => {});
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ watch_list: list }));
    return;
  }

  if (url.pathname === '/api/market/breadth') {
    const day = latestTradingDay();

    // ⭐ 优先读取 breadth-cache.json（由 market_snapshot_sina.py 更新）
    const breadthCache = readBreadthCache();
    if (breadthCache && isNum(breadthCache.up) && isNum(breadthCache.down)) {
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, data: { ...breadthCache, day } }));
      return;
    }

    // 备选方案：从 archive 数据读取
    const snap = readLatestArchivePayload();
    const snapUp = Number(snap?.sentiment?.upCount);
    const snapDown = Number(snap?.sentiment?.downCount);
    if (isNum(snapUp) && isNum(snapDown) && (snap?.day || day) === day) {
      const total = Number(snapUp || 0) + Number(snapDown || 0);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, data: { up: snapUp, down: snapDown, flat: 0, total, day } }));
      return;
    }
    if (isMarketOpenNow()) {
      const rt = await fetchBreadthRealtime();
      if (rt && isNum(rt.up) && isNum(rt.down)) {
        const total = Number(rt.total || (rt.up + rt.down + (rt.flat || 0)) || 0);
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: true, data: { up: rt.up, down: rt.down, flat: rt.flat || 0, total, day } }));
        return;
      }
    }
    const cacheFile = cacheJsonPath('market-breadth', day);
    const cached = readJsonCache(cacheFile);
    if (cached) {
      try {
        const obj = JSON.parse(cached);
        if (isNum(obj?.up) && isNum(obj?.down)) {
          if (!obj.day && !obj.date) obj.day = day;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: true, data: obj }));
          return;
        }
      } catch (e) {
        console.error(e);
      }
    }
    execFile('python3', ['fetch_sector_data.py', 'breadth'], { ...getExecOptions(), timeout: 20000 }, (err, stdout) => {
      if (!err) {
        const out = (stdout || '').trim();
        if (out && isJsonText(out)) {
          const obj = JSON.parse(out);
          if (isNum(obj?.up) && isNum(obj?.down)) {
            obj.day = day;
            if (!isNum(obj.total)) obj.total = Number(obj.up || 0) + Number(obj.down || 0) + Number(obj.flat || 0);
            const payload = JSON.stringify(obj);
            writeJsonCache(cacheFile, payload);
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify({ ok: true, data: obj }));
            return;
          }
        }
      } else {
        console.error(err);
      }
      const row = loadLatestBreadthRecord() || loadBreadthFromArchive(day);
      const sourceDay = (row && (row.day || row.date)) ? String(row.day || row.date) : null;
      const up = Number(row?.up || 0);
      const down = Number(row?.down || 0);
      const flat = Number(row?.flat || 0);
      const total = Number(row?.total || (up + down + flat) || 0);
      const obj = { up, down, flat, total, day, source_day: sourceDay, stale: !!(sourceDay && sourceDay !== day) };
      writeJsonCache(cacheFile, JSON.stringify(obj));
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, data: obj }));
    });
    return;
  }

  if (url.pathname === '/api/signals') {
    const signals = buildSignalsFromBacktest();
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({
      generated_at: new Date().toISOString(),
      source: 'data/backtest_false_kill.json',
      count: signals.length,
      signals
    }));
    return;
  }

  if (url.pathname === '/api/panic') {
    const day = latestTradingDay();
    let row = null;
    const snap = readLatestArchivePayload();
    const snapUp = Number(snap?.sentiment?.upCount);
    const snapDown = Number(snap?.sentiment?.downCount);
    if (isNum(snapUp) && isNum(snapDown) && (snap?.day || day) === day) {
      row = { up: snapUp, down: snapDown, total: snapUp + snapDown, day: snap?.day || day };
    } else if (isMarketOpenNow()) {
      row = await fetchBreadthRealtime();
      if (row && !row.day) row.day = day;
    }
    if (!row) {
      row = loadLatestBreadthRecord() || loadBreadthFromArchive(day);
    }
    const up = Number(row?.up || 0);
    const down = Number(row?.down || 0);
    const total = Number(row?.total || 0);
    const ratio = total > 0 ? down / total : 0;
    const isPanic = ratio > 0.65;
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({
      ratio,
      is_panic: isPanic,
      up,
      down,
      total
    }));
    return;
  }

  // Static File Serving
  let filePath = path.join(__dirname, 'public', url.pathname === '/' ? 'index.html' : url.pathname);
  const ext = path.extname(filePath);
  const mimeTypes = {
    '.html': 'text/html',
    '.js': 'text/javascript',
    '.css': 'text/css',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpg',
  };

  fs.readFile(filePath, (err, content) => {
    if (err) {
      if (err.code === 'ENOENT') {
        res.writeHead(404);
        res.end('not found');
      } else {
        res.writeHead(500);
        res.end('server error: ' + err.code);
      }
    } else {
      const contentType = mimeTypes[ext] || 'application/octet-stream';
      res.writeHead(200, { 'Content-Type': contentType, 'Cache-Control': 'no-store' });
      res.end(content, 'utf-8');
    }
  });
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`proxy server on http://localhost:${PORT} [Ashare+Tencent]`);
});

// ============ 定时写入成交额任务 ============
// 每分钟准时写入一次成交额数据，确保数据完整性
setInterval(async () => {
  try {
    // 只在交易时间内执行
    if (!isMarketOpenNow()) return;

    const day = latestTradingDay();
    const nowTime = minuteKeyBeijing(new Date());

    // 获取当前成交额
    const snap = await buildSnapshotPayload();
    const volume = snap?.sentiment?.volume;

    if (!isNum(volume) || volume <= 0) return;

    // 写入成交额数据
    const file = volumeFilePath(day);
    appendVolumePoint(file, nowTime, volume);

    // 可选：输出日志（调试用）
    // console.log(`[VolumeTimer] ${day} ${nowTime}: ${volume / 10000}亿元`);
  } catch (e) {
    // 静默失败，避免刷屏
  }
}, 30 * 1000);  // 每30秒执行一次

// ============ 午休时数据持久化 ============
// 11:30收盘时，把runtime/minute/的分时数据复制到data/目录
setInterval(() => {
  const parts = getBeijingParts();
  if (!parts) return;
  if (parts.weekday === 0 || parts.weekday === 6) return;
  // 11:30 = 690分钟
  if (parts.minutes !== 690) return;

  const day = parts.date;
  const dayCompact = day.replace(/-/g, '');
  const runtimeDir = path.join(__dirname, 'runtime', 'minute');
  const dataDir = path.join(__dirname, 'data');

  // 需要持久化的分时code列表
  const codes = ['sse', 'szi', 'gem', 'star', 'hs300', 'csi2000', 'avg', 'gov', 't', 'tl', 'bank', 'broker', 'insure'];

  for (const code of codes) {
    const srcFile = path.join(runtimeDir, `minute-${dayCompact}-${code}.jsonl`);
    const dstFile = path.join(dataDir, `minute-${dayCompact}-${code}.jsonl`);
    try {
      if (fs.existsSync(srcFile)) {
        fs.copyFileSync(srcFile, dstFile);
        console.log(`[LunchSave] 午休数据已保存: ${dstFile}`);
      }
    } catch (e) {
      console.error(`[LunchSave] 保存失败 ${code}:`, e.message);
    }
  }
}, 60 * 1000);  // 每分钟检查一次

// 启动时的数据补全流程
setTimeout(async () => {
  console.log('=== 启动数据补全检查 ===');
  // 1. 先补全历史缺失数据
  await backfillMissingDataOnStartup();
  // 2. 再更新当天的概览历史数据
  await backfillOverviewHistoryIfNeeded();
  // 3. 检查并更新warmup（从本地ETF数据）
  await updateWarmupIfNeeded();
  console.log('=== 启动数据补全完成 ===');
}, 3000);

// 检查并更新warmup（从本地ETF持久化数据）
async function updateWarmupIfNeeded() {
  try {
    const days = 60;
    const warmupFile = path.join(__dirname, 'data', `sector-history-warmup-${days}.json`);
    const today = latestTradingDay();

    // 检查warmup文件是否存在
    if (!fs.existsSync(warmupFile)) {
      console.log(`[Warmup] 文件不存在，生成新文件...`);
      await regenerateWarmup(days);
      return;
    }

    // 读取warmup文件
    const content = fs.readFileSync(warmupFile, 'utf-8');
    let warmupData;
    try {
      warmupData = JSON.parse(content);
    } catch (e) {
      console.log(`[Warmup] 文件解析失败，重新生成...`);
      await regenerateWarmup(days);
      return;
    }

    const warmupDay = warmupData.day;
    const gap = warmupDay ? dateDiffDays(today, warmupDay) : null;

    // 判断是否需要更新：数据过期 或 收盘后且不是今天的数据
    const isAfterClose = isAfterCloseNow();
    const shouldUpdate = (gap != null && gap > 1) || (isAfterClose && warmupDay !== today);

    if (shouldUpdate) {
      console.log(`[Warmup] 数据需要更新 (${warmupDay} → ${today}, 差距${gap}天, 收盘后:${isAfterClose})，开始更新...`);
      await regenerateWarmup(days);
    } else {
      console.log(`[Warmup] ✅ 数据最新 (${warmupDay})，无需更新`);
    }
  } catch (e) {
    console.error('[Warmup] 检查失败:', e.message);
  }
}

// 重新生成warmup（从本地ETF数据）
async function regenerateWarmup(days) {
  return new Promise((resolve) => {
    const cfg = readSectorProxyConfig();
    const proxyMap = cfg.variants?.etf || {};
    const sectors = Object.keys(proxyMap).join(',');

    if (!sectors) {
      console.log('[Warmup] ⚠️ 没有配置ETF，跳过');
      resolve(false);
      return;
    }

    console.log(`[Warmup] 开始生成... sectors=${sectors}, days=${days}`);

    execFile('python3', ['fetch_sector_data.py', 'warmup', sectors, String(days)],
      getExecOptions(),
      (err, stdout, stderr) => {
        if (err) {
          console.error(`[Warmup] ❌ 生成失败:`, stderr || err.message);
          resolve(false);
        } else {
          console.log(`[Warmup] ✅ 生成成功`);
          resolve(true);
        }
      });
  });
}

// 定时任务：每分钟检查一次是否需要更新当天数据
setInterval(() => { backfillOverviewHistoryIfNeeded(); }, 60 * 1000);

// ============ 15:00后定时任务 ============
// 收盘后(15:00)自动执行日线成交额聚合和涨跌家持久化
setInterval(() => {
  const parts = getBeijingParts();
  if (!parts) return;
  if (parts.weekday === 0 || parts.weekday === 6) return;
  // 15:00 = 900分钟，延迟1分钟执行(15:01-15:05窗口)
  if (parts.minutes < 901 || parts.minutes > 905) return;

  const day = parts.date;
  console.log(`[15:00定时任务] 开始执行: ${day}`);

  // 1. 日线成交额聚合
  execFile('python3', ['scripts/backfill_market_amount_daily.py', day],
    { cwd: __dirname, timeout: 180000 },
    (err, stdout, stderr) => {
      if (err) {
        console.error(`[15:00] 日线成交额更新失败:`, stderr || err.message);
      } else {
        try {
          const result = JSON.parse(stdout);
          console.log(`[15:00] 日线成交额: ${result.ok ? '成功 ' + result.rows + '条' : '失败'}`);
        } catch (e) {
          console.log(`[15:00] 日线成交额: ${stdout.slice(0, 100)}`);
        }
      }
    });

  // 2. 涨跌家持久化
  execFile('python3', ['scripts/save_breadth_history.py'],
    { cwd: __dirname, timeout: 60000 },
    (err, stdout, stderr) => {
      if (err) {
        console.error(`[15:00] 涨跌家持久化失败:`, stderr || err.message);
      } else {
        try {
          const result = JSON.parse(stdout);
          console.log(`[15:00] 涨跌家持久化: ${result.ok ? '成功 ' + result.day : (result.exists ? '已存在' : '失败')}`);
        } catch (e) {
          console.log(`[15:00] 涨跌家持久化: ${stdout.slice(0, 100)}`);
        }
      }
    });

  // 3. ETF日线更新
  execFile('python3', ['-c', 'from data_maintenance import update_all_etf_data; update_all_etf_data()'],
    { cwd: __dirname, timeout: 180000 },
    (err, stdout, stderr) => {
      if (err) {
        console.error(`[15:00] ETF日线更新失败:`, stderr || err.message);
      } else {
        console.log(`[15:00] ETF日线更新:\n${stdout.slice(0, 200)}`);
      }
    });

  // 4. 指数日线更新
  execFile('python3', ['-c', 'from data_maintenance import update_all_index_data; update_all_index_data()'],
    { cwd: __dirname, timeout: 180000 },
    (err, stdout, stderr) => {
      if (err) {
        console.error(`[15:00] 指数日线更新失败:`, stderr || err.message);
      } else {
        console.log(`[15:00] 指数日线更新:\n${stdout.slice(0, 200)}`);
      }
    });

  // 5. 触发warmup更新（收盘后自动刷新）
  setTimeout(() => {
    updateWarmupIfNeeded();
  }, 10000);

}, 60 * 1000);  // 每分钟检查一次
