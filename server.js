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
const CACHE_TTL_MS = 60_000;
const OVERVIEW_CACHE_REV = 2;

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
    bonds.t = { price: bonds.t2603.price ?? null, pct: bonds.t2603.pct ?? null };
  }
  if (!bonds.tl && bonds.tl2603) {
    bonds.tl = { price: bonds.tl2603.price ?? null, pct: bonds.tl2603.pct ?? null };
  }
  if (!bonds.t2603 && bonds.t) {
    bonds.t2603 = { price: bonds.t.price ?? null, pct: bonds.t.pct ?? null, series: [] };
  }
  if (!bonds.tl2603 && bonds.tl) {
    bonds.tl2603 = { price: bonds.tl.price ?? null, pct: bonds.tl.pct ?? null, series: [] };
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

function execPythonJson(args, timeout = 8000) {
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
    
    if (rawArr.length > 0 && rawArr[0]?.time) {
      // Extract date from the first data point (format: YYYY-MM-DD HH:MM)
      const datePart = rawArr[0].time.split(' ')[0];
      if (datePart && /^\d{4}-\d{2}-\d{2}$/.test(datePart)) {
        day = datePart;
        // Filter to ensure data consistency (all points from same day)
        arr = rawArr.filter(p => p?.time && String(p.time).startsWith(day));
      }
    }

    const res = { date: day, data: arr, prevClose: prevClose ?? null };
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
    if (!isNum(up) || !isNum(down)) return null;
    const total = Number.isFinite(flat) ? up + down + flat : up + down;
    return { up, down, flat: Number.isFinite(flat) ? flat : 0, total };
  } catch (e) {
    return null;
  }
}

async function fetchBreadthViaPython() {
  return new Promise((resolve) => {
    execFile('python3', ['fetch_sector_data.py', 'breadth'], { timeout: 5000 }, (err, stdout) => {
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
        date: row[0],
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
  const first = prevClose ?? series[0]?.open ?? series[0]?.close;
  const last = series[series.length - 1]?.close ?? series[series.length - 1]?.open;
  if (first == null || last == null) return { price: last ?? null, pct: null };
  const pct = first ? +(((last - first) / first) * 100).toFixed(2) : null;
  return { price: last ?? null, pct };
}

function archiveSnapshot(payload) {
  const day = (payload.day || '').replace(/-/g, '');
  if (!day) return;
  const dir = path.join(__dirname, 'data');
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, `archive-${day}.jsonl`);
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

function latestTradingDay() {
  const parts = getBeijingParts();
  if (!parts) return new Date().toISOString().slice(0, 10);
  if (parts.weekday === 0) return shiftBeijingDate(parts.date, -2);
  if (parts.weekday === 6) return shiftBeijingDate(parts.date, -1);
  return parts.date;
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
  const weekday = weekMap[map.weekday] ?? null;
  return { date, minutes, weekday };
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

function writeJsonCache(file, jsonText) {
  if (!jsonText) return;
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
  execFile('python3', ['fetch_sector_data.py', cmd, list, String(days)], (err, stdout) => {
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
      type: classify?.type ?? null,
      sector: classify?.sector ?? null,
      sentiment: sentimentVal,
      level: classify?.level ?? null
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
const GROUP_OPTIONS = ['资源', '硬件', '软件'];

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
    if (!GROUP_OPTIONS.includes(group)) return;
    out[name] = group;
  });
  return out;
}

function writeSectorProfile(groups) {
  const dir = path.join(__dirname, 'data');
  fs.mkdirSync(dir, { recursive: true });
  const normalized = normalizeProfileGroups(groups);
  const payload = { groups: normalized, updated_at: new Date().toISOString() };
  fs.writeFileSync(PROFILE_FILE, JSON.stringify(payload, null, 2));
  return payload;
}

function readSectorProfile() {
  const dir = path.join(__dirname, 'data');
  fs.mkdirSync(dir, { recursive: true });
  if (!fs.existsSync(PROFILE_FILE)) return writeSectorProfile({});
  const json = readJsonFileSafe(PROFILE_FILE);
  if (!json || typeof json !== 'object') return writeSectorProfile({});
  const groups = normalizeProfileGroups(json.groups || json);
  const updated = json.updated_at || new Date().toISOString();
  return { groups, updated_at: updated };
}

function pickMinutePct(series) {
  if (!Array.isArray(series) || !series.length) return null;
  const first = series[0];
  const last = series[series.length - 1];
  const base = Number(first?.open ?? first?.close);
  const end = Number(last?.close ?? last?.open);
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
    let key = minuteKey(new Date(ts));
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
  let lastTime = null;
  if (fs.existsSync(file)) {
    const txt = fs.readFileSync(file, 'utf-8').trim();
    if (txt) {
      const lastLine = txt.split('\n').slice(-1)[0];
      if (lastLine) {
        const row = JSON.parse(lastLine);
        lastTime = row?.[0] || null;
      }
    }
  }
  if (lastTime === time) return;
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
  const day = parts.weekday;
  if (day === 0 || day === 6) return false;
  const minutes = parts.minutes;
  const morning = minutes >= 570 && minutes <= 690;
  const afternoon = minutes >= 780 && minutes <= 900;
  return morning || afternoon;
}

function isAfterCloseNow() {
  const parts = getBeijingParts();
  if (!parts) return false;
  const day = parts.weekday;
  if (day === 0 || day === 6) return false;
  const minutes = parts.minutes;
  return minutes >= 930;
}

function findVolumeAtOrBefore(arr, time) {
  if (!arr.length || !time) return null;
  const target = minuteToNumber(time);
  if (target == null) return null;
  let best = null;
  for (const p of arr) {
    const t = minuteToNumber(p.time);
    if (t == null || t > target) continue;
    if (!best || t > minuteToNumber(best.time)) best = p;
  }
  return best;
}

function findArchiveVolumeAtOrBefore(day, time) {
  if (!day || !time) return null;
  const file = path.join(__dirname, 'data', `archive-${day.replace(/-/g, '')}.jsonl`);
  if (!fs.existsSync(file)) return null;
  const txt = fs.readFileSync(file, 'utf-8').trim();
  if (!txt) return null;
  const target = minuteToNumber(time);
  if (target == null) return null;
  let bestTime = null;
  let bestVol = null;
  const lines = txt.split('\n');
  for (const line of lines) {
    if (!line) continue;
    const row = JSON.parse(line);
    if (!Array.isArray(row) || row.length < 22) continue;
    const ts = row[0];
    const vol = row[21];
    if (!isNum(ts) || !isNum(vol)) continue;
    const t = minuteToNumber(minuteKey(new Date(ts)));
    if (t == null || t > target) continue;
    if (bestTime == null || t > bestTime) {
      bestTime = t;
      bestVol = vol;
    }
  }
  return bestVol;
}

function findLastNonZeroVolume(arr) {
  if (!arr || !arr.length) return null;
  for (let i = arr.length - 1; i >= 0; i -= 1) {
    const v = arr[i]?.volume;
    if (isNum(v) && v > 0) return v;
  }
  return null;
}

function findArchiveLastNonZeroVolume(day) {
  if (!day) return null;
  const file = path.join(__dirname, 'data', `archive-${day.replace(/-/g, '')}.jsonl`);
  if (!fs.existsSync(file)) return null;
  const txt = fs.readFileSync(file, 'utf-8').trim();
  if (!txt) return null;
  const lines = txt.split('\n');
  let last = null;
  for (const line of lines) {
    if (!line) continue;
    const row = JSON.parse(line);
    if (!Array.isArray(row) || row.length < 22) continue;
    const vol = row[21];
    if (isNum(vol) && vol > 0) last = vol;
  }
  return last;
}

function buildVolumeFromArchive(day) {
  if (!day) return false;
  const file = path.join(__dirname, 'data', `archive-${day.replace(/-/g, '')}.jsonl`);
  if (!fs.existsSync(file)) return false;
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
    const key = minuteKey(new Date(ts));
    map.set(key, vol);
  }
  if (!map.size) return false;
  const out = [];
  const keys = Array.from(map.keys()).sort();
  for (const k of keys) {
    out.push(JSON.stringify([k, map.get(k)]));
  }
  if (!out.length) return false;
  fs.writeFileSync(volumeFilePath(day), out.join('\n') + '\n');
  return true;
}

function ensureVolumeFile(day) {
  if (!day) return false;
  const file = volumeFilePath(day);
  if (fs.existsSync(file)) {
    const txt = fs.readFileSync(file, 'utf-8').trim();
    if (txt) {
      const arr = readVolumeFile(file);
      if (hasTradingPoint(arr)) return true;
    }
  }
  return buildVolumeFromArchive(day);
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

function buildVolumeCompare(day, volume, manualYVol) {
  const nowTime = minuteKey(new Date());
  if (day && isMarketOpenNow()) appendVolumePoint(volumeFilePath(day), nowTime, volume);
  
  // Use findPreviousTradingDay instead of simple day-1
  const yday = day ? findPreviousTradingDay(day) : null;
  
  if (yday) ensureVolumeFile(yday);
  const yArr = yday ? readVolumeSeries(yday) : [];
  const yPoint = findVolumeAtOrBefore(yArr, nowTime);
  let yVol = yPoint?.volume ?? null;
  if (!isNum(yVol) && yday) {
    yVol = findArchiveVolumeAtOrBefore(yday, nowTime);
  }
  if (!isNum(yVol) || yVol === 0) {
    yVol = findLastNonZeroVolume(yArr) ?? (yday ? findArchiveLastNonZeroVolume(yday) : null);
  }
  
  // Fallback to manualYVol if local file lookup failed
  if ((!isNum(yVol) || yVol === 0) && isNum(manualYVol)) {
    yVol = manualYVol;
  }

  const volumeDelta = (isNum(volume) && isNum(yVol)) ? volume - yVol : null;
  const volumePct = (isNum(volumeDelta) && isNum(yVol) && yVol !== 0) ? +((volumeDelta / yVol) * 100).toFixed(2) : null;
  const volumeDir = volumeDelta == null ? null : (volumeDelta >= 0 ? '增量' : '缩量');
  return { dir: volumeDir, pct: volumePct, delta: volumeDelta, yday: yVol, time: nowTime };
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
    star: 'sh000688',
    hs300: 'sh000300',
    csi2000: 'sh932000',
    avg: 'sh000001',
    gov: 'sh000012',
    t: 'T2603',
    tl: 'TL2603',
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
      star: 'sh000688',
      hs300: 'sh000300',
      csi2000: 'sz399303'
    };
  return map[code] || null;
}

function minuteEmMap(code) {
  const map = {
    sse: '1.000001',
    szi: '0.399001',
    gem: '0.399006',
    star: '1.000688',
    hs300: '1.000300',
    gov: '1.000012',
    t: '8.110130',
    tl: '8.140130',
    csi2000: '2.932000',
    avg: '2.830000',
    bank: '90.BK0475',
    broker: '90.BK0473',
    insure: '90.BK0474'
  };
  return map[code] || null;
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

async function buildOverviewHistoryPayload(day) {
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
      arr[arr.length - 1] = todayDaily;
      series[k] = arr;
    }
  });
  const volume = mergeDailyVolume(series.sse, series.szi).filter(p => p?.date && p.date < day);
  return JSON.stringify({ day, series, volume, rev: OVERVIEW_CACHE_REV });
}

async function backfillOverviewHistoryIfNeeded() {
  if (!isAfterCloseNow()) return;
  const day = latestTradingDay();
  if (lastDailyBackfillDay === day) return;
  const cacheFile = cacheJsonPath('overview-history', day);
  const cached = readJsonCache(cacheFile);
  if (cached) {
    try {
      const p = JSON.parse(cached);
      const last = lastDateInSeries(p?.series?.sse);
      if (p?.rev === OVERVIEW_CACHE_REV && last === day) {
        lastDailyBackfillDay = day;
        return;
      }
    } catch (e) {
      console.error(e);
    }
  }
  const payload = await buildOverviewHistoryPayload(day);
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
  const day = (new Date()).toISOString().split('T')[0];
  const file = path.join(__dirname, 'data', `archive-${day.replace(/-/g, '')}.jsonl`);
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
  const volumeSeriesYday = (() => {
    const yday = findPreviousTradingDay(day);
    if (yday) ensureVolumeFile(yday);
    return yday ? readVolumeSeries(yday) : [];
  })();
  const payload = {
    day,
    indices: {
      sse: { price: ssePrice ?? null, pct: ssePct ?? null, series: [] },
      szi: { price: sziPrice ?? null, pct: sziPct ?? null, series: [] },
      gem: { price: gemPrice ?? null, pct: gemPct ?? null, series: [] },
      star: { price: starPrice ?? null, pct: starPct ?? null, series: [] },
      hs300: { price: hs300Price ?? null, pct: hs300Pct ?? null, series: [] },
      csi2000: { price: csi2000Price ?? null, pct: csi2000Pct ?? null, series: [] },
      avg: { price: avgPrice ?? null, pct: avgPct ?? null, series: [] }
    },
    bonds: {
      gov: { pct: govPct ?? null, series: [] },
      tl2603: { price: tlPriceNorm ?? null, pct: tlPct ?? null, series: [] },
      t2603: { price: tPriceNorm ?? null, pct: tPct ?? null, series: [] },
      tl: { price: tlPriceNorm ?? null, pct: tlPct ?? null },
      t: { price: tPriceNorm ?? null, pct: tPct ?? null }
    },
    sectors: {
      bank: { pct: bankPct ?? null, series: [] },
      broker: { pct: brokerPct ?? null, series: [] },
      insure: { pct: insurePct ?? null, series: [] }
    },
    sentiment: {
      volume: volume || 0,
      volumeStr: volume ? (volume / 10000).toFixed(1) + '亿' : '-',
      upCount: upCount ?? '-',
      downCount: downCount ?? '-',
      volumeCmp,
      volumeSeries,
      volumeSeriesYday
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
  const [sse, szi, gem, star, hs300] = await Promise.all([
    fetchAshareMinute('sh000001'),
    fetchAshareMinute('sz399001'),
    fetchAshareMinute('sz399006'),
    fetchAshareMinute('sh000688'),
    fetchAshareMinute('sh000300')
  ]);

  const snaps = await fetchSnapshot('sh000001,sz399001,sz399006,sh000688,sh000300,sh000012,sz399106');
  const em = await fetchEastmoneySnapshot(['90.BK0475', '90.BK0473', '90.BK0474', '2.932000', '8.110130', '8.140130', '2.830000', '1.000012']);
  
  // Determine market date: prefer fresh API date, fallback to latest local file, then current trading day
  const todayTradingDay = latestTradingDay();
  let marketDate = sse.date;
  if (!marketDate) {
    const latestFile = findLatestMinuteFile('sse');
    if (latestFile) {
      marketDate = dayFromMinuteFile(latestFile);
    } else {
      marketDate = todayTradingDay;
    }
  }
  // Guard against stale upstream minute dates dragging snapshot back to old days.
  if (marketDate < todayTradingDay) {
    marketDate = todayTradingDay;
  }

  const [sseSeries, sziSeries, gemSeries, starSeries, hs300Series] = await Promise.all([
    (sse.date === marketDate && sse.data?.length) ? sse.data : loadMinuteSeries(marketDate, 'sse', '1.000001'),
    (szi.date === marketDate && szi.data?.length) ? szi.data : loadMinuteSeries(marketDate, 'szi', '0.399001'),
    (gem.date === marketDate && gem.data?.length) ? gem.data : loadMinuteSeries(marketDate, 'gem', '0.399006'),
    (star.date === marketDate && star.data?.length) ? star.data : loadMinuteSeries(marketDate, 'star', '1.000688'),
    (hs300.date === marketDate && hs300.data?.length) ? hs300.data : loadMinuteSeries(marketDate, 'hs300', '1.000300')
  ]);

  // Get previous trading day volume via Tencent API as fallback
  let prevVolume = null;
  try {
    const sseDaily = await fetchTencentDaily('sh000001', 5);
    if (sseDaily?.data?.length >= 2) {
      // Find the day before marketDate
      const prevData = sseDaily.data.filter(d => d.date < marketDate).sort((a, b) => b.date.localeCompare(a.date))[0];
      if (prevData?.amount) {
        prevVolume = prevData.amount;
      }
    }
  } catch (e) {
    console.error(e);
  }

  const tPrev = normalizeBondPrice(em['8.110130']?.prevClose ?? null);
  const tlPrev = normalizeBondPrice(em['8.140130']?.prevClose ?? null);
  
  // Use loadMinuteSeries for consistent fallback to local files
  const tSeries = await loadMinuteSeries(marketDate, 't', '8.110130');
  const tlSeries = await loadMinuteSeries(marketDate, 'tl', '8.140130');
  const avgSeries = await loadMinuteSeries(marketDate, 'avg', '2.830000');
  const csi2000Series = await loadMinuteSeries(marketDate, 'csi2000', '2.932000');

  const tDerived = deriveFromSeries(tSeries, tPrev);
  const tlDerived = deriveFromSeries(tlSeries, tlPrev);
  const tSnapPrice = normalizeBondPrice(em['8.110130']?.price ?? null);
  const tlSnapPrice = normalizeBondPrice(em['8.140130']?.price ?? null);
  const tSnapPct = em['8.110130']?.pct ?? null;
  const tlSnapPct = em['8.140130']?.pct ?? null;
  const tFinal = { price: tDerived.price ?? tSnapPrice ?? null, pct: tDerived.pct ?? tSnapPct ?? null };
  const tlFinal = { price: tlDerived.price ?? tlSnapPrice ?? null, pct: tlDerived.pct ?? tlSnapPct ?? null };
  const szAmount = pickNum(snaps['sz399001']?.amount, snaps['sz399106']?.amount);
  const amountList = [snaps['sh000001']?.amount, szAmount];
  const totalAmountRaw = amountList.reduce((sum, v) => sum + (isNum(v) ? v : 0), 0);
  let totalAmount = isNum(totalAmountRaw) ? totalAmountRaw : 0;
  if (!isNum(totalAmount) || totalAmount <= 0) {
    const fallback = pickNum(lastGoodSnapshot.payload?.sentiment?.volume, readLatestArchiveVolume(marketDate));
    if (isNum(fallback) && fallback > 0) totalAmount = fallback;
  }
  const avgPrice = em['2.830000']?.price ?? null;
  const avgPct = em['2.830000']?.pct ?? null;
  
  // Recalculate avg price/pct from series if snapshot is missing
  const avgDerived = deriveFromSeries(avgSeries, em['2.830000']?.prevClose ?? null);
  const avgPriceFinal = avgPrice ?? avgDerived.price ?? null;
  const avgPctFinal = avgPct ?? avgDerived.pct ?? null;
  
  const csi2000Derived = deriveFromSeries(csi2000Series, em['2.932000']?.prevClose ?? null);
  const csi2000PriceFinal = em['2.932000']?.price ?? csi2000Derived.price ?? null;
  const csi2000PctFinal = em['2.932000']?.pct ?? csi2000Derived.pct ?? null;

  const volumeSeries = readVolumeSeries(marketDate);
  const volumeSeriesYday = (() => {
    const yday = findPreviousTradingDay(marketDate);
    if (yday) ensureVolumeFile(yday);
    return yday ? readVolumeSeries(yday) : [];
  })();
  const breadth = await fetchBreadthRealtime();
  const upCount = isNum(breadth?.up) ? breadth.up : null;
  const downCount = isNum(breadth?.down) ? breadth.down : null;
  if (isAfterCloseNow() && volumeSeries.length) {
    const lastVol = volumeSeries[volumeSeries.length - 1]?.volume;
    if (isNum(lastVol) && lastVol > 0) totalAmount = lastVol;
  }
  const volumeCmp = buildVolumeCompare(marketDate, totalAmount, prevVolume);

  const bankSeries = await loadMinuteSeries(marketDate, 'bank', '90.BK0475');
  const brokerSeries = await loadMinuteSeries(marketDate, 'broker', '90.BK0473');
  const insureSeries = await loadMinuteSeries(marketDate, 'insure', '90.BK0474');
  const govSeries = await loadMinuteSeries(marketDate, 'gov', '1.000012');
  const bankDerived = deriveFromSeries(bankSeries, em['90.BK0475']?.prevClose ?? null);
  const brokerDerived = deriveFromSeries(brokerSeries, em['90.BK0473']?.prevClose ?? null);
  const insureDerived = deriveFromSeries(insureSeries, em['90.BK0474']?.prevClose ?? null);
  const govDerived = deriveFromSeries(govSeries, em['1.000012']?.prevClose ?? null);
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
      sse: { price: snaps['sh000001']?.price || sseSeries.at(-1)?.close, pct: snaps['sh000001']?.pct || pctOfDay(sseSeries), series: sseSeries },
      szi: { price: snaps['sz399001']?.price || sziSeries.at(-1)?.close, pct: snaps['sz399001']?.pct || pctOfDay(sziSeries), series: sziSeries },
      gem: { price: snaps['sz399006']?.price || gemSeries.at(-1)?.close, pct: snaps['sz399006']?.pct || pctOfDay(gemSeries), series: gemSeries },
      star: { price: snaps['sh000688']?.price || starSeries.at(-1)?.close, pct: snaps['sh000688']?.pct || pctOfDay(starSeries), series: starSeries },
      hs300: { price: snaps['sh000300']?.price || hs300Series.at(-1)?.close, pct: snaps['sh000300']?.pct || pctOfDay(hs300Series), series: hs300Series },
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
      volumeSeries,
      volumeSeriesYday,
      upCount: upCount ?? '-',
      downCount: downCount ?? '-'
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
        execFile('python3', ['fetch_sector_data.py', cmd], (err, stdout) => {
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
    const mapped = minuteCodeMap(code);
    const emMapped = minuteEmMap(code);
    if (!mapped) {
      res.writeHead(404);
      res.end('not found');
      return;
    }

    let data = { data: [], prevClose: null };
    try {
      if (emMapped) {
        data = await fetchEastmoneyMinute(emMapped);
      } else {
        data = await fetchAshareMinute(mapped);
      }
      
      if (emMapped && (!data?.data || !data.data.length)) {
        const alt = await fetchAshareMinute(mapped);
        if (alt?.data && alt.data.length) data = alt;
      }
    } catch (e) {
      console.error(`Error fetching minute data for ${code}:`, e.message);
    }

    let prevClose = data.prevClose ?? null;
    if (prevClose == null && emMapped) {
      try {
        const snap = await fetchEastmoneySnapshot([emMapped]);
        prevClose = snap[emMapped]?.prevClose ?? null;
      } catch (e) {
        console.error(e);
      }
    }
    const today = latestTradingDay();
    const marketOpen = isMarketOpenNow();
    let day = today;
    const dataFile = minuteFilePath(today, code);
    const runtimeFile = runtimeMinuteFilePath(today, code);
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
    const todayFiltered = merged.filter(p => p?.time && String(p.time).startsWith(today) && isTradingMinute(timeToMinuteKey(p?.time)));
    if (todayFiltered.length) {
      merged = todayFiltered;
    } else {
      if (!marketOpen) {
        const latestRuntime = findLatestRuntimeMinuteFile(code);
        if (latestRuntime) {
          const { arr: fallbackArr } = readMinuteFile(latestRuntime);
          if (fallbackArr.length) {
            merged = fallbackArr;
            day = dayFromMinuteFile(latestRuntime) || day;
          }
        }
        if (!merged.length) {
          const latestFile = findLatestMinuteFile(code);
          if (latestFile) {
            const { arr: fallbackArr } = readMinuteFile(latestFile);
            if (fallbackArr.length) {
              merged = fallbackArr;
              day = dayFromMinuteFile(latestFile) || day;
            }
          }
        }
      }
    }
    const last = merged.length ? (merged[merged.length - 1]?.close ?? merged[merged.length - 1]?.open) : null;
    if ((code === 't' || code === 'tl') && last != null) {
      prevClose = normalizeBondPrice(prevClose);
      if (prevClose != null && prevClose > 500 && last < 200) {
        prevClose = +((prevClose / 10).toFixed(2));
      }
    }
    if (!merged.length) {
      const cached = lastGoodMinute.get(code);
      if (cached?.series?.length && (!marketOpen || cached.day === today)) {
        merged = cached.series;
        day = cached.day;
        prevClose = cached.prevClose ?? prevClose;
      }
    } else {
      lastGoodMinute.set(code, { day, series: merged, prevClose });
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
    res.end(JSON.stringify({ day, series: merged, latest: merged[merged.length - 1] || null, prevClose }));
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
  if (url.pathname === '/api/snapshot') {
    const snap = await buildSnapshotPayload();
    warmupDay(snap.day || (new Date()).toISOString().split('T')[0]);
    const needAi = url.searchParams.get('ai') !== '0';
    snap.aiText = needAi ? await ensureAiText(snap) : (lastAiText || '');
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify(snap));
    return;
  }
  if (url.pathname === '/api/snapshot/latest') {
    let snap = readLatestArchivePayload();
    const missing = !snap || !isNum(snap.bonds?.gov?.pct) || !isNum(snap.sectors?.bank?.pct) || !isNum(snap.sectors?.broker?.pct) || !isNum(snap.sectors?.insure?.pct);
    const stale = !snap || !isNum(snap.ts) || (now() - snap.ts > CACHE_TTL_MS);
    if (stale || missing) {
      let fresh = null;
      try {
        fresh = await withTimeout(buildSnapshotPayload(), 6000);
      } catch (e) {
        fresh = null;
      }
      if (fresh) {
        warmupDay(fresh.day || (new Date()).toISOString().split('T')[0]);
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
        buildSnapshotPayload().then((v) => {
          if (!v) return;
          lastGoodSnapshot.payload = v;
          lastGoodSnapshot.ts = v.ts || now();
          archiveSnapshot(v);
        }).catch(() => {});
        return;
      }
    }
    snap = repairSnapshot(snap);
    if (snap?.sentiment) {
      const day = snap.day || (new Date()).toISOString().split('T')[0];
      warmupDay(day);
      snap.sentiment.volumeCmp = buildVolumeCompare(day, snap.sentiment.volume ?? null);
      ensureVolumeFile(day);
      snap.sentiment.volumeSeries = readVolumeSeries(day);
      const yday = findPreviousTradingDay(day);
      if (yday) ensureVolumeFile(yday);
      snap.sentiment.volumeSeriesYday = yday ? readVolumeSeries(yday) : [];
    }
    if (isNum(snap.bonds?.t2603?.price) && isNum(snap.bonds?.tl2603?.price)) {
      lastGoodSnapshot.payload = snap;
      lastGoodSnapshot.ts = snap.ts || now();
    }
    const needAi = url.searchParams.get('ai') !== '0';
    snap.aiText = needAi ? await ensureAiText(snap) : (lastAiText || '');
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify(snap));
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
    execFile('python3', ['fetch_sector_data.py', 'rank'], (err, stdout) => {
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
    const list = sectorsParam && sectorsParam.trim() ? sectorsParam.trim() : readWatchList().join(',');
    const day = latestTradingDay();
    const cacheFile = !realtime ? sectorCacheFile('sector-history', day, list, days) : null;
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
          if (latest && String(latest).localeCompare(day) >= 0) {
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(cached);
            return;
          }
          if (!realtime && isAfterCloseNow()) {
            staleCached = cached;
          } else {
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(cached);
            warmupSectorCache('history_dynamic', list, days, cacheFile);
            return;
          }
        } catch (e) {
          console.error(e);
        }
      }
    }
    const fallbackFile = findLatestCacheFile('sector-history');
    if (fallbackFile) {
      const cached = readJsonCache(fallbackFile);
      if (cached) {
        if (!realtime && isAfterCloseNow()) {
          staleCached = cached;
        } else {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(cached);
          if (cacheFile) warmupSectorCache('history_dynamic', list, days, cacheFile);
          return;
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
    execFile('python3', args, { timeout: 180000, maxBuffer: 20 * 1024 * 1024, cwd: __dirname }, (err, stdout) => {
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
    const days = Number.isFinite(Number(daysParam)) ? Math.max(10, Number(daysParam)) : 60;
    const list = sectorsParam && sectorsParam.trim() ? sectorsParam.trim() : readWatchList().join(',');
    const day = latestTradingDay();
    const historyCache = sectorCacheFile('sector-history', day, list, days);
    const lifecycleCache = sectorCacheFile('sector-lifecycle', day, list, days);
    const rotationCache = sectorCacheFile('sector-rotation', day, list, Math.max(90, days));
    const status = {
      history: warmupSectorCache('history_dynamic', list, days, historyCache),
      lifecycle: warmupSectorCache('lifecycle_dynamic', list, days, lifecycleCache),
      rotation: warmupSectorCache('rotation_dynamic', list, Math.max(90, days), rotationCache)
    };
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ day, status }));
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
  if (url.pathname === '/api/sector/lifecycle') {
    const realtime = url.searchParams.get('rt') === '1';
    const sectorsParam = url.searchParams.get('sectors');
    const daysParam = url.searchParams.get('days');
    const days = Number.isFinite(Number(daysParam)) ? Math.max(1, Number(daysParam)) : 60;
    const list = sectorsParam && sectorsParam.trim() ? sectorsParam.trim() : readWatchList().join(',');
    const day = latestTradingDay();
    const cacheFile = !realtime ? sectorCacheFile('sector-lifecycle', day, list, days) : null;
    if (cacheFile) {
      const cached = readJsonCache(cacheFile);
      if (cached) {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(cached);
        return;
      }
    }
    const useDynamic = list && list.trim();
    const args = ['fetch_sector_data.py', useDynamic ? 'lifecycle_dynamic' : 'lifecycle'];
    if (useDynamic) {
      args.push(list);
      args.push(String(days));
    } else {
      args.push(String(days));
    }
    execFile('python3', args, (err, stdout) => {
      if (err) {
        console.error(err);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: "Failed to fetch sector lifecycle" }));
        return;
      }
      const out = (stdout || '').trim();
      if (cacheFile && out && isJsonText(out)) writeJsonCache(cacheFile, out);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(out || '{}');
    });
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
    execFile('python3', args, (err, stdout) => {
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
        const invalid = Object.values(groups || {}).some((g) => g && !GROUP_OPTIONS.includes(String(g).trim()));
        if (invalid) {
          res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
          res.end(JSON.stringify({ error: 'invalid group' }));
          return;
        }
        const payload = writeSectorProfile(groups);
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
    const snap = readLatestArchivePayload();
    const snapUp = Number(snap?.sentiment?.upCount);
    const snapDown = Number(snap?.sentiment?.downCount);
    if (isNum(snapUp) && isNum(snapDown) && (snap?.day || day) === day) {
      const total = Number(snapUp || 0) + Number(snapDown || 0);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ up: snapUp, down: snapDown, flat: 0, total, day }));
      return;
    }
    if (isMarketOpenNow()) {
      const rt = await fetchBreadthRealtime();
      if (rt && isNum(rt.up) && isNum(rt.down)) {
        const total = Number(rt.total || (rt.up + rt.down + (rt.flat || 0)) || 0);
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ up: rt.up, down: rt.down, flat: rt.flat || 0, total, day }));
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
          res.end(JSON.stringify(obj));
          return;
        }
      } catch (e) {
        console.error(e);
      }
    }
    execFile('python3', ['fetch_sector_data.py', 'breadth'], { timeout: 5000 }, (err, stdout) => {
      if (!err) {
        const out = (stdout || '').trim();
        if (out && isJsonText(out)) {
          const obj = JSON.parse(out);
          if (isNum(obj?.up) && isNum(obj?.down)) {
            if (!obj.day && !obj.date) obj.day = day;
            if (!isNum(obj.total)) obj.total = Number(obj.up || 0) + Number(obj.down || 0) + Number(obj.flat || 0);
            const payload = JSON.stringify(obj);
            writeJsonCache(cacheFile, payload);
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(payload);
            return;
          }
        }
      } else {
        console.error(err);
      }
      const row = loadLatestBreadthRecord() || loadBreadthFromArchive(day);
      const rowDay = row?.day || row?.date || null;
      const up = Number(row?.up || 0);
      const down = Number(row?.down || 0);
      const flat = Number(row?.flat || 0);
      const total = Number(row?.total || (up + down + flat) || 0);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ up, down, flat, total, day: rowDay || day }));
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

server.listen(PORT, () => {
  console.log(`proxy server on http://localhost:${PORT} [Ashare+Tencent]`);
});

setTimeout(() => { backfillOverviewHistoryIfNeeded(); }, 3000);
setInterval(() => { backfillOverviewHistoryIfNeeded(); }, 60 * 1000);
