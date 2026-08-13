const ctx = require('../context');
ctx.install(global);

const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');

const ROOT = path.join(__dirname, '..', '..');

// ===== 纯 JS 计算中枢（读动态变量 + 天时缓存，不再调 Python 做生克/交割/风险） =====
let _calendarMap = null;       // { date: record }
let _dynamicVars = null;       // astro_dynamic_vars.json 解析结果
let _holidaySet = new Set();   // 节假日
let _deliveryCache = {};       // { year: [dates] }

function _pad2(n) { return String(n).padStart(2, '0'); }
function _fmtDate(d) { return `${d.getFullYear()}-${_pad2(d.getMonth() + 1)}-${_pad2(d.getDate())}`; }

function _loadCalendarMap() {
  if (_calendarMap) return _calendarMap;
  const map = {};
  const fp = path.join(ROOT, 'data', 'astro', 'astro_calendar.jsonl');
  if (fs.existsSync(fp)) {
    const text = fs.readFileSync(fp, 'utf8');
    for (const line of text.split('\n')) {
      const s = line.trim();
      if (!s) continue;
      try {
        const rec = JSON.parse(s);
        if (rec && rec.date) map[rec.date] = rec;
      } catch (e) { /* skip bad line */ }
    }
  }
  _calendarMap = map;
  return _calendarMap;
}

function _loadDynamicVars() {
  if (_dynamicVars) return _dynamicVars;
  const fp = path.join(ROOT, '八字', 'astro_dynamic_vars.json');
  if (fs.existsSync(fp)) {
    try { _dynamicVars = JSON.parse(fs.readFileSync(fp, 'utf8')); } catch (e) { _dynamicVars = null; }
  }
  if (!_dynamicVars) {
    // 兜底：配置文件缺失时用内置默认，避免整页崩溃
    _dynamicVars = {
      static: {
        tiangan_wuxing: {"甲":"木","乙":"木","丙":"火","丁":"火","戊":"土","己":"土","庚":"金","辛":"金","壬":"水","癸":"水"},
        dizhi_wuxing: {"子":"水","丑":"土","寅":"木","卯":"木","辰":"土","巳":"火","午":"火","未":"土","申":"金","酉":"金","戌":"土","亥":"水"},
        sheng: {"木":"火","火":"土","土":"金","金":"水","水":"木"},
        ke: {"木":"土","土":"水","水":"火","火":"金","金":"木"}
      },
      tunable: {
        indices: [],
        energy_weights: { year: 0.5, month: 0.3, day: 0.2 },
        score_map: { year: { same: 2, sheng: 1, ke: -2, xie: -1 }, month: { same: 1, sheng: 1, ke: -1, xie: -1 }, day: { same: 1, sheng: 1, ke: -1, xie: -1 } },
        verdict_thresholds: { strong_up: 1.5, strong_down: -1.5 },
        switch_rule: { window: 20, min_samples: 10, min_advantage: 0.15 }
      }
    };
  }
  return _dynamicVars;
}

function _loadHolidays() {
  if (_holidaySet.size > 0) return _holidaySet;
  const fp = path.join(ROOT, 'config', 'holidays.json');
  if (fs.existsSync(fp)) {
    try {
      const obj = JSON.parse(fs.readFileSync(fp, 'utf8'));
      const arr = Array.isArray(obj) ? obj : (obj.holidays || []);
      arr.forEach(d => _holidaySet.add(String(d)));
    } catch (e) { /* skip */ }
  }
  return _holidaySet;
}

// 特征胜率表（数据驱动预测基础）
let _featureStats = null;
function _loadFeatureStats() {
  if (_featureStats) return _featureStats;
  const fp = path.join(ROOT, '八字', 'feature_stats.json');
  if (fs.existsSync(fp)) {
    try { _featureStats = JSON.parse(fs.readFileSync(fp, 'utf8')); } catch (e) { _featureStats = null; }
  }
  if (!_featureStats) _featureStats = { indices: {} };
  return _featureStats;
}

// 生克关系标签（替代手工打分，返回关系类别）
function relationLabel(flowWx, pillarWx) {
  const s = _loadDynamicVars().static;
  if (!flowWx || !pillarWx) return null;
  if (flowWx === pillarWx) return '同气';
  if (s.sheng[flowWx] === pillarWx) return '被生';
  if (s.ke[flowWx] === pillarWx) return '被克';
  if (s.sheng[pillarWx] === flowWx) return '泄';
  return '柱克';
}

function phaseLabel(rec) {
  if (isFullMoonWindow(rec)) return '满月窗口';
  if (isNewMoonWindow(rec)) return '新月窗口';
  return '其他';
}

function riskLabels(rec) {
  const labels = [];
  if (rec.gzDay === '丙午') labels.push('丙午日');
  if (rec.tgWx === '土' && rec.dzWx === '土') labels.push('双土日');
  if (rec.gzMonth === '乙未') labels.push('乙未月');
  if (isDeliveryDay(rec.date)) labels.push('交割日');
  return labels;
}

// 加权胜率预测：查当天各特征历史胜率，样本数加权平均 → P(涨)
function predictIndex(rec, idx) {
  const stats = _loadFeatureStats();
  const idxStats = stats.indices && stats.indices[idx.code];
  const s = _loadDynamicVars().static;
  const pillarTg = String(idx.pillar || '').charAt(0);
  const pillarWx = s.tiangan_wuxing[pillarTg];
  const feats = idxStats ? idxStats.features : null;

  const contribs = [];
  const push = (stat) => { if (stat && stat.n >= 5) contribs.push(stat); };

  if (feats) {
    push(feats.year_rel && feats.year_rel[relationLabel(s.tiangan_wuxing[rec.ytg], pillarWx)]);
    push(feats.month_rel && feats.month_rel[relationLabel(s.tiangan_wuxing[rec.mtg], pillarWx)]);
    push(feats.day_rel && feats.day_rel[relationLabel(s.tiangan_wuxing[rec.tg], pillarWx)]);
    push(feats.phase && feats.phase[phaseLabel(rec)]);
    for (const r of riskLabels(rec)) push(feats.risk && feats.risk[r]);
  }

  if (!contribs.length) return { p_up: 0.5, direction: '平' };
  let num = 0, den = 0;
  for (const c of contribs) { num += c.n * c.win_rate; den += c.n; }
  const p_up = den > 0 ? num / den : 0.5;
  return { p_up, direction: p_up > 0.5 ? '涨' : (p_up < 0.5 ? '跌' : '平') };
}

// 交割日：每月第三个周五，遇节假日/周末顺延到下一交易日
function calcDeliveryDays(year) {
  if (_deliveryCache[year]) return _deliveryCache[year];
  const holidays = _loadHolidays();
  const out = [];
  for (let m = 0; m < 12; m++) {
    const first = new Date(year, m, 1);
    const firstDow = first.getDay(); // 0=周日
    const offsetToFri = (5 - firstDow + 7) % 7; // 到第一个周五的天数
    let d = new Date(year, m, 1 + offsetToFri + 14); // 第三个周五
    while (holidays.has(_fmtDate(d)) || d.getDay() === 0 || d.getDay() === 6) {
      d = new Date(d.getTime() + 86400000);
    }
    out.push(_fmtDate(d));
  }
  _deliveryCache[year] = out;
  return out;
}

function isDeliveryDay(dateStr) {
  const year = Number(String(dateStr).slice(0, 4));
  if (!year) return false;
  return calcDeliveryDays(year).includes(dateStr);
}

// 满月/新月窗口：各取 3 天（moonAge 峰值前后约 1.5 天）
function isFullMoonWindow(rec) {
  const a = Number(rec.moonAge);
  return Number.isFinite(a) && a >= 13 && a < 16.5;
}
function isNewMoonWindow(rec) {
  const a = Number(rec.moonAge);
  return Number.isFinite(a) && (a < 1.5 || a >= 28);
}

// 风险规则：数据驱动，规则定义在 八字/risk_rules.json
let _riskRules = null;
function _loadRiskRules() {
  if (_riskRules) return _riskRules;
  const fp = path.join(ROOT, '八字', 'risk_rules.json');
  if (fs.existsSync(fp)) {
    try { _riskRules = JSON.parse(fs.readFileSync(fp, 'utf8')); } catch (e) { _riskRules = null; }
  }
  if (!_riskRules) _riskRules = { rules: [] };
  return _riskRules;
}

function _matchRule(rec, rule) {
  switch (rule.type) {
    case 'moon_full': return isFullMoonWindow(rec);
    case 'moon_new': return isNewMoonWindow(rec);
    case 'gz_day': return rec.gzDay === rule.value;
    case 'gz_month': return rec.gzMonth === rule.value;
    case 'double_earth': return rec.tgWx === '土' && rec.dzWx === '土';
    default: return false;
  }
}

function checkRiskFactors(rec) {
  const rules = (_loadRiskRules().rules || []);
  let level = 0;
  let riskCount = 0;
  const marks = [];
  for (const rule of rules) {
    if (_matchRule(rec, rule)) {
      if (rule.level > 0) {
        level = Math.max(level, rule.level);
        riskCount += 1;
      }
      marks.push(rule.name);
    }
  }
  // 多个风险因子叠加，升级一级（封顶 L4）
  if (riskCount >= 2 && level > 0 && level < 4) level += 1;
  return { level, marks };
}

// 生成某月交易日历（只列周一~周五，节假日置 disabled）
function buildMonthDays(monthStr, userPillar) {
  const [y, m] = String(monthStr).split('-').map(Number);
  if (!y || !m) return [];
  const map = _loadCalendarMap();
  const holidays = _loadHolidays();
  const daysInMonth = new Date(y, m, 0).getDate();
  const days = [];
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${y}-${_pad2(m)}-${_pad2(d)}`;
    const dow = new Date(y, m - 1, d).getDay(); // 0=周日
    if (dow === 0 || dow === 6) continue; // 跳过周末（5列布局）
    const rec = map[dateStr];
    const isHoliday = holidays.has(dateStr);
    const risk = rec ? checkRiskFactors(rec) : { level: 0, marks: [] };
    const advice = rec && userPillar ? computePersonalAdvice(rec, userPillar) : null;
    days.push({
      date: dateStr,
      dayNum: d,
      disabled: isHoliday,
      lunar: rec ? rec.lunarDay : '',
      ganzhi: rec ? rec.gzDay : '',
      phase: rec ? (isFullMoonWindow(rec) ? 'full' : isNewMoonWindow(rec) ? 'new' : null) : null,
      isDelivery: isDeliveryDay(dateStr),
      riskLevel: risk.level,
      riskMarks: risk.marks,
      personal: (advice && advice.type !== 'neutral') ? advice.type : null
    });
  }
  return days;
}

// 指数历史日线缓存 + 准确率计算
let _indexPctMap = null;  // { code: { date: pct } }
function _loadIndexPctMap() {
  if (_indexPctMap) return _indexPctMap;
  _indexPctMap = {};
  const dir = path.join(ROOT, 'data', 'index', 'daily');
  if (!fs.existsSync(dir)) return _indexPctMap;
  for (const name of fs.readdirSync(dir)) {
    const fp = path.join(dir, name, 'daily.jsonl');
    if (!fs.existsSync(fp)) continue;
    const m = {};
    try {
      const text = fs.readFileSync(fp, 'utf8');
      for (const line of text.split('\n')) {
        const s = line.trim();
        if (!s) continue;
        try {
          const r = JSON.parse(s);
          if (r.date && r.pct != null) m[r.date] = Number(r.pct);
        } catch (e) { /* skip */ }
      }
    } catch (e) { /* skip */ }
    _indexPctMap[name] = m;
  }
  return _indexPctMap;
}

let _accuracyCache = {};  // { code: { hit_rate, samples, pillar } }
function calcIndexAccuracy(idx) {
  const cached = _accuracyCache[idx.code];
  if (cached && cached.pillar === idx.pillar) return cached;
  const pctMap = (_loadIndexPctMap() || {})[idx.code];
  const calendarMap = _loadCalendarMap();
  let hits = 0, total = 0;
  if (pctMap) {
    for (const date in pctMap) {
      const astro = calendarMap[date];
      if (!astro) continue;
      const pct = pctMap[date];
      if (pct === 0) continue;
      const pred = predictIndex(astro, idx);
      if (pred.direction === '平') continue;
      total++;
      if ((pred.direction === '涨') === (pct > 0)) hits++;
    }
  }
  const result = total > 0 ? { hit_rate: hits / total, samples: total, pillar: idx.pillar } : null;
  _accuracyCache[idx.code] = result;
  return result;
}

// 单个指数的深度解析（数据驱动：加权胜率 → P(涨) + 方向）
function buildIndexAnalysis(rec, idx) {
  const pred = predictIndex(rec, idx);
  return {
    code: idx.code,
    name: idx.name,
    pillar: idx.pillar,
    p_up: pred.p_up,
    direction: pred.direction,
    accuracy: calcIndexAccuracy(idx)
  };
}

// 命主操作建议：按命主日柱天干 vs 当日天干的生克，判定进财/克伐/平稳
function computePersonalAdvice(rec, userPillar) {
  const p = String(userPillar || '').trim();
  if (!p || p.length < 1) return null;
  const s = _loadDynamicVars().static;
  const pillarTg = p.charAt(0);
  const pillarWx = s.tiangan_wuxing[pillarTg];
  const dayWx = s.tiangan_wuxing[rec.tg];
  if (!pillarWx || !dayWx) return null;

  let type;
  if (s.sheng[dayWx] === pillarWx) type = 'money';      // 当日生我（印星）
  else if (s.ke[pillarWx] === dayWx) type = 'money';    // 我克当日（财星）
  else if (s.ke[dayWx] === pillarWx) type = 'danger';   // 当日克我（七杀）
  else type = 'neutral';                                 // 平稳

  const map = {
    money: { type: 'money', title: '今日财印当令，宜进攻', desc: '命主日柱得当日干支相生/相合，财气或助力较旺，适合主动寻找机会、分批布局。' },
    danger: { type: 'danger', title: '今日七杀克身，宜空仓', desc: '当日干支克制命主日柱，情绪与操作易失误，建议降低仓位、以防守为主。' },
    neutral: { type: 'neutral', title: '今日平稳，宜观望', desc: '当日干支与命主日柱无明显生克，适合观望、等待更明确的信号再行动。' }
  };
  return map[type];
}

module.exports = function() {
  const handleRoute = async function(req, res) {
    const url = new URL(req.url, `http://${req.headers.host}`);

  // 月度日历聚合（含主日柱得分 + 交割日 + 风险标记）
  if (url.pathname === '/api/m1/data/astro_calendar_month' && req.method === 'GET') {
    try {
      const month = String(url.searchParams.get('month') || '').trim();
      if (!month) {
        res.statusCode = 400;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'missing month' }));
        return true;
      }
      const days = buildMonthDays(month, String(url.searchParams.get('user_pillar') || '').trim());
      const map = _loadCalendarMap();
      const firstRec = days.length ? map[days[0].date] : null;
      const macro = {
        yearGz: firstRec ? firstRec.gzYear : '',
        monthGz: firstRec ? firstRec.gzMonth : '',
        summary: firstRec ? `流年${firstRec.gzYear}(${firstRec.ytgWx}${firstRec.ydzWx}) · 流月${firstRec.gzMonth}(${firstRec.mtgWx}${firstRec.mdzWx})` : ''
      };
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: true, month, macro, days }));
      return true;
    } catch (e) {
      res.statusCode = 500;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: e.message }));
      return true;
    }
  }

  // 单日深度推演（主日柱 + 备选日柱双结果）
  if (url.pathname === '/api/m1/data/astro_daily_detail' && req.method === 'GET') {
    try {
      const date = String(url.searchParams.get('date') || '').trim();
      if (!date) {
        res.statusCode = 400;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'missing date' }));
        return true;
      }
      const rec = _loadCalendarMap()[date];
      if (!rec) {
        res.statusCode = 404;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'no astro record for ' + date }));
        return true;
      }
      const risk = checkRiskFactors(rec);
      const riskAlerts = [];
      if (isDeliveryDay(date)) riskAlerts.push('股指期货交割日，历史上叠加下跌趋势极易发生大波动。');
      for (const rule of (_loadRiskRules().rules || [])) {
        if (_matchRule(rec, rule) && rule.alert) riskAlerts.push(rule.alert);
      }

      const userPillar = String(url.searchParams.get('user_pillar') || '').trim();
      // 交割日作为 level=1 因子纳入累积
      let riskLevelValue = risk.level;
      if (isDeliveryDay(date)) {
        if (risk.level > 0) riskLevelValue = Math.min(4, risk.level + 1);
        else riskLevelValue = 1;
      }
      const riskLabelMap = { 0: '安全', 1: '注意', 2: '谨慎', 3: '危险', 4: '高危' };
      const riskSummaryMap = {
        0: '今日无风险因子，可正常操作。',
        1: '命中低风险因子，注意仓位。',
        2: '命中中风险因子，建议降低仓位。',
        3: '多个风险因子叠加，建议谨慎防守。',
        4: '命中极高风险因子，建议空仓观望。'
      };
      const marketOutlook = {
        level: riskLevelValue,
        label: riskLabelMap[riskLevelValue] || '安全',
        summary: riskSummaryMap[riskLevelValue] || '今日无风险因子，可正常操作。'
      };

      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({
        ok: true,
        date,
        astro: {
          gzYear: rec.gzYear, gzMonth: rec.gzMonth, gzDay: rec.gzDay,
          lunarMonth: rec.lunarMonth, lunarDay: rec.lunarDay,
          phaseName: rec.phaseName, phaseIdx: rec.phaseIdx,
          weekday: rec.weekday
        },
        riskLevel: riskLevelValue,
        riskAlerts,
        marketOutlook,
        personalAdvice: computePersonalAdvice(rec, userPillar)
      }));
      return true;
    } catch (e) {
      res.statusCode = 500;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: e.message }));
      return true;
    }
  }

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

        const script = path.join(ROOT, 'treasolo', 'm1_bazi.py');
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

        execFile(pythonBin, args, { cwd: ROOT, timeout: 60000, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
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
    return true;
  }

  if (url.pathname === '/api/m1/config/bazi_prompts' && req.method === 'GET') {
    try {
      const fp = path.join(ROOT, '八字', 'prompts.json');
      if (!fs.existsSync(fp)) {
        res.statusCode = 404;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'prompts not found' }));
        return true;
      }
      const txt = fs.readFileSync(fp, 'utf8');
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.setHeader('Cache-Control', 'no-store');
      res.end(txt);
      return true;
    } catch (e) {
      res.statusCode = 500;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: e.message }));
      return true;
    }
  }

  if (url.pathname === '/api/m1/data/day_astro' && req.method === 'GET') {
    try {
      const day = String(url.searchParams.get('day') || '').trim();
      if (!day) {
        res.statusCode = 400;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'missing day' }));
        return true;
      }

      const script = path.join(ROOT, 'treasolo', 'm1_day_astro.py');
      if (!fs.existsSync(script)) {
        res.statusCode = 500;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'm1_day_astro.py not found' }));
        return true;
      }

      const pythonBin =
        process.env.PYTHON_BIN ||
        (fs.existsSync('/opt/homebrew/bin/python3') ? '/opt/homebrew/bin/python3' : 'python3');

      const args = [script, '--day', day];
      execFile(pythonBin, args, { cwd: ROOT, timeout: 60000, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
        const out = String(stdout || '').trim();
        if (err) {
          res.statusCode = 500;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: false, error: (stderr || err.message || '').trim(), stdout: out }));
          return true;
        }
        if (out && out.startsWith('{')) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(out);
          return true;
        }
        res.statusCode = 500;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'invalid day_astro output', stderr: (stderr || '').trim(), stdout: out }));
      });
      return true;
    } catch (e) {
      res.statusCode = 500;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: e.message }));
      return true;
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
        return true;
      }

      const script = path.join(ROOT, 'treasolo', 'm1_astro_calendar.py');
      if (!fs.existsSync(script)) {
        res.statusCode = 500;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'm1_astro_calendar.py not found' }));
        return true;
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

      execFile(pythonBin, args, { cwd: ROOT, timeout: 60000, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
        const out = String(stdout || '').trim();
        if (err) {
          res.statusCode = 500;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ ok: false, error: (stderr || err.message || '').trim(), stdout: out }));
          return true;
        }
        if (out && out.startsWith('{')) {
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(out);
          return true;
        }
        res.statusCode = 500;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(JSON.stringify({ ok: false, error: 'invalid astro_calendar output', stderr: (stderr || '').trim(), stdout: out }));
      });
      return true;
    } catch (e) {
      res.statusCode = 500;
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.end(JSON.stringify({ ok: false, error: e.message }));
      return true;
    }
  }

    return false;
  };
  return handleRoute;
};
