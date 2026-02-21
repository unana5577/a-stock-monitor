const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');

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

const cache = new Map();
const now = () => Date.now();
let lastAiText = '';
const lastGoodSnapshot = { payload: null, ts: 0 };
const lastGoodMinute = new Map();
let lastWarmupDay = '';

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
    const today = (new Date()).toISOString().split('T')[0];
    const arr = rawArr.filter(p => p?.time && String(p.time).startsWith(today));
    const day = today;
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
          amount: parseFloat(vals[37])
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

function volumeFilePath(day) {
  const d = day.replace(/-/g, '');
  const dir = path.join(__dirname, 'data');
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, `volume-${d}.jsonl`);
}

function latestTradingDay() {
  const d = new Date();
  const day = d.getDay();
  if (day === 0) d.setDate(d.getDate() - 2);
  if (day === 6) d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
}

function cacheJsonPath(prefix, day) {
  const d = day.replace(/-/g, '');
  const dir = path.join(__dirname, 'data');
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, `${prefix}-${d}.json`);
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

function isJsonText(text) {
  try {
    JSON.parse(text);
    return true;
  } catch (e) {
    return false;
  }
}

const WATCH_FILE = path.join(__dirname, 'data', 'sector-watch.json');
const DEFAULT_WATCH_LIST = ['云计算', '半导体', '有色金属'];

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
    const key = minuteKey(new Date(ts));
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
  const series = readVolumeFile(file);
  const arch = readArchiveVolumeSeries(day);
  if (!arch.length) return series;
  const map = new Map();
  arch.forEach((p) => {
    if (p?.time && isNum(p.volume)) map.set(p.time, p.volume);
  });
  series.forEach((p) => {
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

function prevDay(day) {
  const d = new Date(day);
  if (Number.isNaN(d.getTime())) return null;
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
}

function hasTradingPoint(arr) {
  if (!arr || !arr.length) return false;
  for (const p of arr) {
    const t = minuteToNumber(p.time);
    if (t == null) continue;
    if ((t >= 570 && t <= 690) || (t >= 780 && t <= 900)) return true;
  }
  return false;
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

function buildVolumeCompare(day, volume) {
  const nowTime = minuteKey(new Date());
  if (day) appendVolumePoint(volumeFilePath(day), nowTime, volume);
  const yday = day ? prevDay(day) : null;
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
  const file = minuteFilePath(day, code);
  let series = readMinuteFile(file).arr;
  if (!series.length && secid) {
    const emMinute = await fetchEastmoneyMinute(secid);
    if (emMinute?.data?.length) {
      series = emMinute.data;
      writeMinuteFile(file, series);
    }
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
      const v = map.get(p.date) || 0;
      map.set(p.date, v + p.amount);
    });
  };
  add(sse);
  add(szi);
  return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0])).map(([date, amount]) => ({ date, amount }));
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
    const yday = prevDay(day);
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
  const marketDate = sse.date || (new Date()).toISOString().split('T')[0];
  const tPrev = normalizeBondPrice(em['8.110130']?.prevClose ?? null);
  const tlPrev = normalizeBondPrice(em['8.140130']?.prevClose ?? null);
  const tSeries = readMinuteFile(minuteFilePath(marketDate, 't')).arr;
  const tlSeries = readMinuteFile(minuteFilePath(marketDate, 'tl')).arr;
  const tDerived = deriveFromSeries(tSeries, tPrev);
  const tlDerived = deriveFromSeries(tlSeries, tlPrev);
  const tSnapPrice = normalizeBondPrice(em['8.110130']?.price ?? null);
  const tlSnapPrice = normalizeBondPrice(em['8.140130']?.price ?? null);
  const tSnapPct = em['8.110130']?.pct ?? null;
  const tlSnapPct = em['8.140130']?.pct ?? null;
  const tFinal = { price: tDerived.price ?? tSnapPrice ?? null, pct: tDerived.pct ?? tSnapPct ?? null };
  const tlFinal = { price: tlDerived.price ?? tlSnapPrice ?? null, pct: tlDerived.pct ?? tlSnapPct ?? null };
  const amountList = [snaps['sh000001']?.amount, snaps['sz399106']?.amount];
  const totalAmountRaw = amountList.reduce((sum, v) => sum + (isNum(v) ? v : 0), 0);
  let totalAmount = isNum(totalAmountRaw) ? totalAmountRaw : 0;
  if (!isNum(totalAmount) || totalAmount <= 0) {
    const fallback = pickNum(lastGoodSnapshot.payload?.sentiment?.volume, readLatestArchiveVolume(marketDate));
    if (isNum(fallback) && fallback > 0) totalAmount = fallback;
  }
  const avgPrice = em['2.830000']?.price ?? null;
  const avgPct = em['2.830000']?.pct ?? null;

  const volumeCmp = buildVolumeCompare(marketDate, totalAmount);
  const volumeSeries = readVolumeSeries(marketDate);
  const volumeSeriesYday = (() => {
    const yday = prevDay(marketDate);
    if (yday) ensureVolumeFile(yday);
    return yday ? readVolumeSeries(yday) : [];
  })();

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
  const govPctFinal = pickNum(snaps['sh000012']?.pct, govDerived.pct);
  const payload = {
    day: marketDate,
    indices: {
      sse: { price: snaps['sh000001']?.price || sse.data.at(-1)?.close, pct: snaps['sh000001']?.pct || pctOfDay(sse.data), series: sse.data },
      szi: { price: snaps['sz399001']?.price || szi.data.at(-1)?.close, pct: snaps['sz399001']?.pct || pctOfDay(szi.data), series: szi.data },
      gem: { price: snaps['sz399006']?.price || gem.data.at(-1)?.close, pct: snaps['sz399006']?.pct || pctOfDay(gem.data), series: gem.data },
      star: { price: snaps['sh000688']?.price || star.data.at(-1)?.close, pct: snaps['sh000688']?.pct || pctOfDay(star.data), series: star.data },
      hs300: { price: snaps['sh000300']?.price || hs300.data.at(-1)?.close, pct: snaps['sh000300']?.pct || pctOfDay(hs300.data), series: hs300.data },
      csi2000: { price: em['2.932000']?.price ?? null, pct: em['2.932000']?.pct ?? null, series: [] },
      avg: { price: avgPrice ?? null, pct: avgPct ?? null, series: [] }
    },
    bonds: {
      gov: { pct: govPctFinal, series: [] },
      tl2603: { price: tlFinal.price, pct: tlFinal.pct, series: [] },
      t2603: { price: tFinal.price, pct: tFinal.pct, series: [] },
      tl: { price: tlFinal.price, pct: tlFinal.pct },
      t: { price: tFinal.price, pct: tFinal.pct }
    },
    sectors: {
      bank: { pct: bankPctFinal, series: [] },
      broker: { pct: brokerPctFinal, series: [] },
      insure: { pct: insurePctFinal, series: [] }
    },
    sentiment: {
      volume: totalAmount || 0,
      volumeStr: totalAmount ? (totalAmount / 10000).toFixed(1) + '亿' : '-',
      volumeCmp,
      volumeSeries,
      volumeSeriesYday
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
    let data = emMapped ? await fetchEastmoneyMinute(emMapped) : await fetchAshareMinute(mapped);
    if (emMapped && (!data?.data || !data.data.length)) {
      const alt = await fetchAshareMinute(mapped);
      if (alt?.data && alt.data.length) data = alt;
    }
    let prevClose = data.prevClose ?? null;
    if (prevClose == null && emMapped) {
      const snap = await fetchEastmoneySnapshot([emMapped]);
      prevClose = snap[emMapped]?.prevClose ?? null;
    }
    const today = (new Date()).toISOString().split('T')[0];
    let day = today;
    const file = minuteFilePath(today, code);
    const { arr, lastTime } = readMinuteFile(file);
    let merged = arr;
    if (data.data && data.data.length) {
      if (!arr.length || (arr[0]?.time && data.data[0]?.time && data.data[0].time < arr[0].time)) {
        writeMinuteFile(file, data.data);
        merged = data.data;
      } else {
        appendMinuteFile(file, data.data, lastTime);
        merged = arr.concat((data.data || []).filter(p => !lastTime || p.time > lastTime));
      }
    }
    if (!merged.length && fs.existsSync(file)) {
      merged = readMinuteFile(file).arr;
    }
    const todayFiltered = merged.filter(p => p?.time && String(p.time).startsWith(today));
    if (todayFiltered.length) {
      merged = todayFiltered;
    } else {
      const latestFile = findLatestMinuteFile(code);
      if (latestFile) {
        const { arr: fallbackArr } = readMinuteFile(latestFile);
        if (fallbackArr.length) {
          merged = fallbackArr;
          day = dayFromMinuteFile(latestFile) || day;
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
      if (cached?.series?.length) {
        merged = cached.series;
        day = cached.day;
        prevClose = cached.prevClose ?? prevClose;
      }
    } else {
      lastGoodMinute.set(code, { day, series: merged, prevClose });
    }
    merged.sort((a, b) => (a.time || '').localeCompare(b.time || ''));
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ day, series: merged, latest: merged[merged.length - 1] || null, prevClose }));
    return;
  }
  if (url.pathname === '/api/overview/history') {
    const day = latestTradingDay();
    const cacheFile = cacheJsonPath('overview-history', day);
    const cached = readJsonCache(cacheFile);
    if (cached) {
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(cached);
      return;
    }
    const keys = ['sse', 'szi', 'gem', 'star', 'hs300', 'csi2000', 'avg', 't', 'tl', 'bank', 'broker', 'insure'];
    const pairs = await Promise.all(keys.map(async (k) => {
      const secid = minuteEmMap(k);
      if (!secid) return [k, []];
      const daily = await fetchEastmoneyDaily(secid, 180);
      return [k, daily?.data || []];
    }));
    const series = {};
    pairs.forEach(([k, v]) => { series[k] = v || []; });
    const volume = mergeDailyVolume(series.sse, series.szi);
    const payload = JSON.stringify({ day, series, volume });
    writeJsonCache(cacheFile, payload);
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(payload);
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
      const fresh = await buildSnapshotPayload();
      warmupDay(fresh.day || (new Date()).toISOString().split('T')[0]);
      const needAi = url.searchParams.get('ai') !== '0';
      fresh.aiText = needAi ? await ensureAiText(fresh) : (lastAiText || '');
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify(fresh));
      return;
    }
    snap = repairSnapshot(snap);
    if (snap?.sentiment) {
      const day = snap.day || (new Date()).toISOString().split('T')[0];
      warmupDay(day);
      snap.sentiment.volumeCmp = buildVolumeCompare(day, snap.sentiment.volume ?? null);
      ensureVolumeFile(day);
      snap.sentiment.volumeSeries = readVolumeFile(volumeFilePath(day));
      const yday = prevDay(day);
      if (yday) ensureVolumeFile(yday);
      snap.sentiment.volumeSeriesYday = yday ? readVolumeFile(volumeFilePath(yday)) : [];
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
    const useDynamic = list && list.trim();
    const args = ['fetch_sector_data.py', useDynamic ? 'history_dynamic' : 'history'];
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
        res.end(JSON.stringify({ error: "Failed to fetch sector history" }));
        return;
      }
      const out = (stdout || '').trim();
      if (!realtime && out && isJsonText(out)) writeJsonCache(cacheJsonPath('sector-history', latestTradingDay()), out);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(out || '{}');
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
    const cacheFile = cacheJsonPath('market-breadth', day);
    const cached = readJsonCache(cacheFile);
    if (cached) {
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(cached);
      return;
    }
    execFile('python3', ['fetch_sector_data.py', 'breadth'], (err, stdout) => {
      if (err) {
        console.error(err);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: "Failed to fetch market breadth" }));
        return;
      }
      const out = (stdout || '').trim();
      if (out && isJsonText(out)) writeJsonCache(cacheFile, out);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(out || '{}');
    });
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
