const { createApp, ref, onMounted, computed, nextTick, watch } = Vue;

const API_BASE = window.location.origin;

const app = createApp({
  setup() {
    const astroPredict = ref(null);
    const astroLoading = ref(false);
    const astroSelectedDay = ref('');
    const astroMonthStr = ref('');
    const astroMonthGanzhi = ref('');
    const astroMonthDays = ref([]);
    const astroWeekDays = ref([]);
    const astroReviewItems = ref([]);
    const astroReviewText = ref('');
    const userGender = ref(localStorage.getItem('astro_user_gender') || '');
    watch(userGender, (v) => localStorage.setItem('astro_user_gender', String(v || '')));
    const userBirth = ref(localStorage.getItem('astro_user_birth') || '');
    watch(userBirth, (v) => localStorage.setItem('astro_user_birth', String(v || '')));
    const userPlace = ref(localStorage.getItem('astro_user_place') || '');
    watch(userPlace, (v) => localStorage.setItem('astro_user_place', String(v || '')));
    const userPlaceCustom = ref(localStorage.getItem('astro_user_place_custom') || '');
    watch(userPlaceCustom, (v) => localStorage.setItem('astro_user_place_custom', String(v || '')));
    const userArea = ref(localStorage.getItem('astro_user_area') || '');
    watch(userArea, (v) => localStorage.setItem('astro_user_area', String(v || '')));

    const migrateOldPlace = () => {
      if (String(userPlace.value || '').trim()) return;
      const p = String(localStorage.getItem('astro_user_province') || '').trim();
      const c = String(localStorage.getItem('astro_user_city') || '').trim();
      const cc = String(localStorage.getItem('astro_user_city_custom') || '').trim();
      if (!p) return;
      if (!c) { userPlace.value = p; return; }
      if (c === '其他') { userPlace.value = cc ? `${p}-${cc}` : p; return; }
      userPlace.value = `${p}-${c}`;
    };
    migrateOldPlace();

    const placeGroups = ref([]);
    const placeAreaMap = ref({});
    const placeLoading = ref(false);
    const PLACE_DATA_CACHE_KEY = 'm1_place_data_v3';

    const normalizeProvinceName = (s) => {
      let v = String(s || '');
      v = v.replace('特别行政区', '');
      v = v.replace('维吾尔自治区', '');
      v = v.replace('壮族自治区', '');
      v = v.replace('回族自治区', '');
      v = v.replace('自治区', '');
      v = v.replace('省', '');
      v = v.replace('市', '');
      return v;
    };

    const loadPlaceGroups = async () => {
      if (placeGroups.value && placeGroups.value.length) return;
      try {
        const raw = localStorage.getItem(PLACE_DATA_CACHE_KEY) || '';
        const cached = raw ? JSON.parse(raw) : null;
        if (cached && Array.isArray(cached.groups) && cached.groups.length && (Date.now() - Number(cached.ts || 0) < 30 * 86400 * 1000)) {
          placeGroups.value = cached.groups;
          if (cached.areaMap && typeof cached.areaMap === 'object') placeAreaMap.value = cached.areaMap;
          return;
        }
      } catch (e) { void e; }
      placeLoading.value = true;
      const fetchJsonFrom = async (urls) => {
        for (const u of (Array.isArray(urls) ? urls : [])) {
          try { const res = await fetch(u); if (!res || !res.ok) continue; return await res.json(); } catch (e) { void e; }
        }
        return null;
      };
      try {
        const provinces = await fetchJsonFrom(['https://unpkg.com/province-city-china@8.5.8/dist/province.json', 'https://cdn.jsdelivr.net/npm/province-city-china@8.5.8/dist/province.json']);
        const cities = await fetchJsonFrom(['https://unpkg.com/province-city-china@8.5.8/dist/city.json', 'https://cdn.jsdelivr.net/npm/province-city-china@8.5.8/dist/city.json']);
        const areas = await fetchJsonFrom(['https://unpkg.com/province-city-china@8.5.8/dist/area.json', 'https://cdn.jsdelivr.net/npm/province-city-china@8.5.8/dist/area.json']);
        if (!provinces || !cities || !areas) throw new Error('place list fetch failed');
        const pInfo = {};
        for (const p of (Array.isArray(provinces) ? provinces : [])) {
          const key = String(p.province || '').trim();
          if (!key) continue;
          const full = String(p.name || '').trim();
          if (!full) continue;
          pInfo[key] = { full, label: normalizeProvinceName(full) };
        }
        const gMap = {}; const gSet = {};
        const pushOpt = (groupLabel, opt) => {
          if (!groupLabel || !opt || !opt.value) return;
          if (!gMap[groupLabel]) gMap[groupLabel] = [];
          if (!gSet[groupLabel]) gSet[groupLabel] = new Set();
          if (gSet[groupLabel].has(opt.value)) return;
          gSet[groupLabel].add(opt.value);
          gMap[groupLabel].push(opt);
        };
        for (const c of (Array.isArray(cities) ? cities : [])) {
          const pi = pInfo[String(c.province || '').trim()];
          if (!pi) continue;
          const cityName = String(c.name || '').trim();
          if (!cityName) continue;
          pushOpt(pi.label, { value: `${pi.label}-${cityName}`, label: cityName });
        }
        const groups = [];
        const order = (Array.isArray(provinces) ? provinces : []).map((p) => normalizeProvinceName(p && p.name));
        for (const label of order) { if (label && gMap[label] && gMap[label].length) groups.push({ label, options: gMap[label] }); }
        for (const label of Object.keys(gMap)) { if (!order.includes(label)) groups.push({ label, options: gMap[label] }); }
        const areaMap = {}; const areaSet = {};
        for (const a of (Array.isArray(areas) ? areas : [])) {
          const pc = String(a.province || '').trim();
          const ac = String(a.city || '').trim();
          const pi = pInfo[pc];
          if (!pi) continue;
          const cv = `${pi.label}-${String((cities || []).find(x => String(x.province || '').trim() === pc && String(x.city || '').trim() === ac)?.name || '').trim()}`;
          const an = String(a.name || '').trim();
          if (!cv || !an) continue;
          if (!areaMap[cv]) areaMap[cv] = [];
          if (!areaSet[cv]) areaSet[cv] = new Set();
          if (areaSet[cv].has(an)) continue;
          areaSet[cv].add(an);
          areaMap[cv].push(an);
        }
        placeGroups.value = groups;
        placeAreaMap.value = areaMap;
        try { localStorage.setItem(PLACE_DATA_CACHE_KEY, JSON.stringify({ ts: Date.now(), groups, areaMap })); } catch (e) { void e; }
      } catch (e) { void e; }
      placeLoading.value = false;
    };

    const placeAreas = computed(() => {
      const pv = String(userPlace.value || '').trim();
      if (!pv || pv === '其他') return [];
      const m = placeAreaMap.value || {};
      const arr = m[pv];
      return Array.isArray(arr) ? arr : [];
    });

    watch([userPlace, placeAreaMap], () => {
      const arr = placeAreas.value || [];
      if (!arr.length) { userArea.value = ''; return; }
      if (userArea.value && arr.includes(userArea.value)) return;
      userArea.value = '';
    });

    const userPlaceText = computed(() => {
      const v = String(userPlace.value || '').trim();
      const cc = String(userPlaceCustom.value || '').trim();
      if (v === '其他') return cc;
      return v;
    });

    const baziProfile = ref(null);
    const baziPrompts = ref(null);

    const loadBaziPrompts = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/m1/config/bazi_prompts`);
        const json = await res.json();
        if (json && json.rev) baziPrompts.value = json;
      } catch (e) { void e; }
    };

    const replaceTemplate = (tmpl, vars) => {
      let s = String(tmpl || '');
      Object.entries(vars || {}).forEach(([k, v]) => {
        s = s.replaceAll(`{{${k}}}`, String(v ?? ''));
      });
      return s;
    };

    const baziLoading = ref(false);
    const baziError = ref('');
    const financeAuto = ref('');
    const financeLoading = ref(false);
    const dailyRiskAuto = ref('');
    const dailyRiskLoading = ref(false);
    const monthOutlook = ref('');
    const editMonthOutlook = ref(false);
    const astroHistoryWindow = ref(15);
    const astroHistorySymbols = ref((localStorage.getItem('astro_history_symbols') || '').split(',').filter(Boolean));

    watch(monthOutlook, (v) => {
      const k = astroMonthGanzhi.value ? `astro_month_outlook_${astroMonthGanzhi.value}` : 'astro_month_outlook';
      localStorage.setItem(k, String(v || ''));
    });
    watch(astroMonthGanzhi, (v) => {
      const k = v ? `astro_month_outlook_${v}` : 'astro_month_outlook';
      monthOutlook.value = localStorage.getItem(k) || '';
    });

    const baziReady = computed(() => !!(userGender.value && userBirth.value && userPlaceText.value));
    const baziSubmitted = ref(false);
    const BAZI_CACHE_KEY = 'astro_bazi_profile_v1';

    const restoreBaziCache = () => {
      try {
        const raw = localStorage.getItem(BAZI_CACHE_KEY) || '';
        const obj = raw ? JSON.parse(raw) : null;
        if (!obj || !obj.ok) return;
        const birth = String(userBirth.value || '').trim();
        const place = String(userPlaceText.value || '').trim();
        const placeDetail = String(userArea.value || '').trim();
        const gender = String(userGender.value || '').trim();
        if (String(obj.birth || '').trim() !== birth) return;
        if (String(obj.place || '').trim() !== place) return;
        if (String(obj.placeDetail || '').trim() !== placeDetail) return;
        if (String(obj.gender || '').trim() !== gender) return;
        baziProfile.value = obj;
        baziSubmitted.value = true;
      } catch (e) { void e; }
    };
    restoreBaziCache();

    const fetchBaziProfile = async () => {
      const birth = String(userBirth.value || '').trim();
      if (!birth) return;
      baziLoading.value = true;
      baziError.value = '';
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/bazi`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ gender: userGender.value, birth, place: userPlaceText.value, placeDetail: String(userArea.value || '').trim(), trueSolar: true })
        });
        if (!res.ok) { const t = await res.text(); throw new Error(t || `http_${res.status}`); }
        const json = await res.json();
        if (json && json.ok) {
          baziProfile.value = json;
          try { localStorage.setItem(BAZI_CACHE_KEY, JSON.stringify(json)); } catch (e) { void e; }
        } else {
          baziProfile.value = null;
          baziError.value = json && json.error ? String(json.error) : '生成失败';
        }
      } catch (e) {
        baziProfile.value = null;
        baziError.value = String(e.message || '').slice(0, 200);
      }
      baziLoading.value = false;
    };

    const submitBazi = async () => {
      baziSubmitted.value = true;
      const birth = String(userBirth.value || '').trim();
      if (!birth) { baziError.value = '请填写出生年月日'; return; }
      baziError.value = '';
      await fetchBaziProfile();
    };

    watch([userGender, userBirth, userPlace, userPlaceCustom, userArea], () => {
      baziProfile.value = null;
      baziError.value = '';
      if (baziSubmitted.value) submitBazi();
    });

    const astroWeekStatus = ref('');
    const astroWeekTradingDays = computed(() => {
      const days = astroWeekDays.value || [];
      return days.filter(d => {
        const dw = new Date(d.date + 'T00:00:00+08:00').getDay();
        return dw >= 1 && dw <= 5;
      });
    });

    const astroWeekRangeText = computed(() => {
      const days = astroWeekDays.value || [];
      if (!days.length) return '';
      const first = days[0].date;
      const last = days[days.length - 1].date;
      return `${first} ~ ${last}`;
    });

    const astroWeekMatrix = ref({});
    const astroPrevCache = {};
    const astroPredCache = {};

    const pad2 = (n) => String(n).padStart(2, '0');

    const nowTs = () => {
      const d = new Date();
      return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
    };

    const chartInstances = {};

    const callChat = async (system, user) => {
      try {
        const res = await fetch(`${API_BASE}/api/ai/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages: [
              { role: 'system', content: String(system || '') },
              { role: 'user', content: String(user || '') }
            ]
          })
        });
        const json = await res.json();
        if (json && json.ok && json.reply) return String(json.reply || '');
        return '';
      } catch (e) { return ''; }
    };

    const formatAmount = (val) => {
      if (!val) return '---';
      return (val / 1e8).toFixed(2) + '亿';
    };

    const getBeijingToday = () => {
      const d = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }));
      const m = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      return `${d.getFullYear()}-${m}-${dd}`;
    };

    const shiftDate = (d, n) => {
      const dt = new Date(d + 'T00:00:00+08:00');
      dt.setDate(dt.getDate() + n);
      const y = dt.getFullYear();
      const m = String(dt.getMonth() + 1).padStart(2, '0');
      const dd = String(dt.getDate()).padStart(2, '0');
      return `${y}-${m}-${dd}`;
    };

    const weekRangeFor = (day) => {
      const dt = new Date(day + 'T00:00:00+08:00');
      const dw = dt.getDay();
      const mondayOffset = dw === 0 ? -6 : 1 - dw;
      const monday = shiftDate(day, mondayOffset);
      const sunday = shiftDate(day, mondayOffset + 6);
      return { start: monday, end: sunday };
    };

    const fetchAstroPredictRaw = async (day = '') => {
      if (!day) return null;
      if (Object.prototype.hasOwnProperty.call(astroPredCache, day)) return astroPredCache[day];
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/astro_predict?day=${encodeURIComponent(day)}`);
        const json = await res.json();
        if (json && json.ok) {
          astroPredCache[day] = json;
          return json;
        }
      } catch (e) { void e; }
      astroPredCache[day] = null;
      return null;
    };

    const fetchAstroPredict = async (day = '') => {
      astroLoading.value = true;
      try {
        const q = day ? `?day=${encodeURIComponent(day)}` : '';
        const res = await fetch(`${API_BASE}/api/m1/data/astro_predict${q}`);
        const json = await res.json();
        if (json && json.ok) {
          astroPredict.value = json;
          const base = day || json.asOfDay || '';
          if (!astroSelectedDay.value && base) astroSelectedDay.value = base;
        }
      } catch (err) { console.error('Failed to fetch astro predict:', err); }
      astroLoading.value = false;
    };

    const fetchAstroReview = async (day) => {
      if (!day) return;
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/astro_review?day=${encodeURIComponent(day)}`);
        const json = await res.json();
        if (json && json.ok) {
          astroReviewItems.value = Array.isArray(json.items) ? json.items : [];
          if (json.prev && json.summary && json.summary.total) {
            astroReviewText.value = `prev=${json.prev} 命中 ${json.summary.hit}/${json.summary.total}`;
          } else {
            astroReviewText.value = '暂无可复盘数据';
          }
        }
      } catch (err) { console.error('Failed to fetch astro review:', err); }
    };

    const fetchTradingPrev = async (day) => {
      if (!day) return null;
      if (Object.prototype.hasOwnProperty.call(astroPrevCache, day)) return astroPrevCache[day];
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/trading_prev?day=${encodeURIComponent(day)}`);
        const json = await res.json();
        if (json && json.ok) { astroPrevCache[day] = json.prev || null; return astroPrevCache[day]; }
      } catch (err) { void err; }
      astroPrevCache[day] = null;
      return null;
    };

    const fetchAstroCalendarMonth = async (monthStr) => {
      if (!monthStr) return;
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/astro_calendar?month=${encodeURIComponent(monthStr)}`);
        const json = await res.json();
        if (json && json.ok && Array.isArray(json.days)) {
          astroMonthDays.value = json.days;
          astroMonthStr.value = monthStr;
          const pick = astroSelectedDay.value ? json.days.find(x => x.date === astroSelectedDay.value) : null;
          astroMonthGanzhi.value = (pick && pick.sixtyCycleMonth) ? pick.sixtyCycleMonth : (json.days[0]?.sixtyCycleMonth || '');
          nextTick(() => scrollAstroPhaseToDay(astroSelectedDay.value || (json.days[0] && json.days[0].date) || ''));
        }
      } catch (err) { console.error('Failed to fetch astro calendar month:', err); }
    };

    const fetchAstroCalendarRange = async (start, end) => {
      if (!start || !end) return [];
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/astro_calendar?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`);
        const json = await res.json();
        if (json && json.ok && Array.isArray(json.days)) return json.days;
      } catch (err) { console.error('Failed to fetch astro calendar range:', err); }
      return [];
    };

    const scrollAstroPhaseToDay = (day) => {
      if (!day) return;
      try {
        const wrap = document.getElementById('astro-phase-scroll');
        if (!wrap) return;
        const btn = wrap.querySelector(`button[data-date="${day}"]`);
        if (!btn) return;
        btn.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'auto' });
      } catch (e) { void e; }
    };

    const buildAstroWeekMatrix = async () => {
      const days = astroWeekDays.value || [];
      const matrix = {};
      for (const d of days) {
        const pred = await fetchAstroPredictRaw(d.date);
        if (!pred) continue;
        const marketProb = pred.market && pred.market.probs ? pred.market.probs['1'] : null;
        matrix[d.date] = { __market__: { prob: marketProb, tag: marketProb != null ? probToTag(marketProb) : '--' } };
        const etfs = pred.predictions || {};
        const syms = Object.keys(etfs);
        for (const sym of syms) {
          const p = etfs[sym] && etfs[sym].probs ? etfs[sym].probs['1'] : null;
          matrix[d.date][sym] = { prob: p, tag: p != null ? probToTag(p) : '--' };
        }
      }
      astroWeekMatrix.value = matrix;
      astroWeekStatus.value = '';
    };

    const probToTag = (v) => {
      const n = Number(v);
      if (!Number.isFinite(n)) return '--';
      if (n >= 0.65) return '强多';
      if (n >= 0.55) return '偏多';
      if (n > 0.45) return '中性';
      if (n > 0.35) return '偏空';
      return '强空';
    };

    const selectAstroDay = async (day) => {
      if (!day) return;
      astroSelectedDay.value = day;
      if (!journalDay.value) journalDay.value = day;
      await fetchAstroPredict(day);
      await fetchAstroReview(day);
      const monthStr = day.slice(0, 7);
      if (astroMonthStr.value !== monthStr) {
        await fetchAstroCalendarMonth(monthStr);
      } else {
        const pick = astroMonthDays.value.find(x => x.date === day);
        if (pick && pick.sixtyCycleMonth) astroMonthGanzhi.value = pick.sixtyCycleMonth;
      }
      nextTick(() => scrollAstroPhaseToDay(day));
      const { start, end } = weekRangeFor(day);
      astroWeekDays.value = await fetchAstroCalendarRange(start, end);
      await buildAstroWeekMatrix();
      nextTick(() => renderAstroHistoryChart());
      if (baziReady.value && baziProfile.value && baziProfile.value.ok) {
        ensureDailyRiskAuto(false);
      }
    };

    const runAstroPredict = async (day = '') => {
      astroLoading.value = true;
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/astro_predict/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ day: day || '' })
        });
        const json = await res.json();
        if (json && json.ok) {
          await fetchAstroPredict(day);
          if (day) await fetchAstroReview(day);
          nextTick(() => renderAstroHistoryChart());
        }
      } catch (err) {
        console.error('Failed to run astro predict:', err);
      } finally {
        astroLoading.value = false;
      }
    };

    const etfSymbols = ['sh512400', 'sh512480', 'sh515120', 'sh515880', 'sh516010', 'sh516160', 'sh516510', 'sh562500', 'sh563530'];
    const symbolNames = {
      'sh512400': '有色金属ETF', 'sh512480': '半导体ETF', 'sh515120': '创新药ETF',
      'sh515880': '通信ETF', 'sh516010': '游戏ETF', 'sh516160': '新能源ETF',
      'sh516510': '云计算ETF', 'sh562500': '机器人ETF', 'sh563530': '商业航天ETF'
    };

    const astroProbTag = (sym, horizon) => {
      const p = astroPredict.value && astroPredict.value.predictions;
      const v = p && p[sym] && p[sym].probs ? Number(p[sym].probs[horizon]) : NaN;
      if (!Number.isFinite(v)) return '--';
      if (v >= 0.65) return '强多';
      if (v >= 0.55) return '偏多';
      if (v > 0.45) return '中性';
      if (v > 0.35) return '偏空';
      return '强空';
    };

    const astroProbTagClass = (sym, horizon) => {
      const tag = astroProbTag(sym, horizon);
      if (tag === '强多') return 'border-red-200 bg-red-50 text-red-700';
      if (tag === '偏多') return 'border-red-100 bg-red-50/60 text-red-600';
      if (tag === '偏空') return 'border-emerald-100 bg-emerald-50/60 text-emerald-600';
      if (tag === '强空') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
      if (tag === '中性') return 'border-gray-200 bg-gray-50 text-gray-600';
      return 'border-gray-200 bg-white text-gray-400';
    };

    const marketTag = (h) => {
      const p = astroPredict.value && astroPredict.value.market;
      const v = p && p.probs ? Number(p.probs[h]) : NaN;
      if (!Number.isFinite(v)) return '--';
      if (v >= 0.65) return '强多';
      if (v >= 0.55) return '偏多';
      if (v > 0.45) return '中性';
      if (v > 0.35) return '偏空';
      return '强空';
    };

    const directionTextFromTag = (tag) => {
      if (tag === '强多' || tag === '偏多') return '倾向上涨';
      if (tag === '强空' || tag === '偏空') return '倾向下跌';
      return '观望';
    };

    const marketDirectionText = (h) => directionTextFromTag(marketTag(h));
    const astroDirectionText = (sym, h) => directionTextFromTag(astroProbTag(sym, h));

    const astroPhaseRiskText = (d) => {
      const i = Number(d && d.phaseIndex);
      if (!Number.isFinite(i)) return '';
      const name = String(d && d.phaseName || '').trim();
      if (name) return name;
      const map = ['新月', '娥眉月', '上弦月', '盈凸月', '满月', '亏凸月', '下弦月', '残月'];
      return map[i] || '';
    };

    const astroPhaseRiskClass = (idx) => {
      const i = Number(idx);
      const t = Number.isFinite(i) ? i : -1;
      if (t < 0) return 'text-gray-300';
      if (t === 4 || t === 0) return 'text-gray-700';
      if (t === 2 || t === 6) return 'text-gray-600';
      return 'text-gray-500';
    };

    const astroSelectedGanzhiDay = computed(() => {
      const d = astroSelectedDay.value;
      if (!d) return '';
      const hit = astroMonthDays.value.find(x => x.date === d) || astroWeekDays.value.find(x => x.date === d);
      return hit ? hit.sixtyCycleDay : (astroPredict.value?.astro?.asOf?.sixtyCycleDay || '');
    });

    const astroSelectedLunarDay = computed(() => {
      const d = astroSelectedDay.value;
      if (!d) return '';
      const hit = astroMonthDays.value.find(x => x.date === d) || astroWeekDays.value.find(x => x.date === d);
      if (hit && hit.lunarMonth && hit.lunarDay) return `${hit.lunarMonth}${hit.lunarDay}`;
      return '';
    });

    const astroSelectedPhase = computed(() => {
      const d = astroSelectedDay.value;
      if (!d) return '';
      const hit = astroMonthDays.value.find(x => x.date === d) || astroWeekDays.value.find(x => x.date === d);
      return hit ? `${astroPhaseRiskText(hit)}`.trim() : '';
    });

    const astroWeekCell = (day, sym) => {
      if (!day || !sym) return null;
      const row = astroWeekMatrix.value && astroWeekMatrix.value[day];
      return row ? row[sym] : null;
    };

    const astroWeekCellTag = (day, sym) => {
      const c = astroWeekCell(day, sym);
      return c ? c.tag : '--';
    };

    const astroWeekCellTextClass = (day, sym) => {
      const tag = astroWeekCellTag(day, sym);
      if (tag === '强多') return 'text-red-700 font-semibold';
      if (tag === '偏多') return 'text-red-600 font-semibold';
      if (tag === '强空') return 'text-gray-800';
      if (tag === '偏空') return 'text-emerald-600 font-semibold';
      if (tag === '中性') return 'text-gray-600 font-semibold';
      return 'text-gray-400';
    };

    const toggleAstroHistorySymbol = (sym) => {
      const cur = new Set(astroHistorySymbols.value);
      if (cur.has(sym)) cur.delete(sym);
      else cur.add(sym);
      astroHistorySymbols.value = [...cur];
      localStorage.setItem('astro_history_symbols', astroHistorySymbols.value.join(','));
      renderAstroHistoryChart();
    };

    const fetchIntradayDataMultiple = async (syms, day) => {
      const results = {};
      const promises = syms.map(async (sym) => {
        try {
          const qs = day ? `?symbol=${encodeURIComponent(sym)}&day=${encodeURIComponent(day)}` : `?symbol=${encodeURIComponent(sym)}`;
          const res = await fetch(`${API_BASE}/api/m1/data/minute${qs}`);
          const json = await res.json();
          if (json && json.ok && Array.isArray(json.data) && json.data.length > 0) {
            results[sym] = { data: json.data, pre_close: json.pre_close };
          }
        } catch (err) { void err; }
      });
      await Promise.all(promises);
      return results;
    };

    const renderAstroHistoryChart = () => {
      const el = document.getElementById('chart-astro-history');
      if (!el) return;
      if (!chartInstances['astroHistory']) chartInstances['astroHistory'] = echarts.init(el);
      const chart = chartInstances['astroHistory'];
      const syms = astroHistorySymbols.value.filter(s => etfSymbols.includes(s));
      if (!syms.length) return;
      const days = astroWeekDays.value || [];
      const dayLabels = days.map(d => d.date);
      const series = [];
      const colors = ['#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899', '#06B6D4', '#84CC16', '#F97316'];
      syms.forEach((sym, idx) => {
        const data = days.map(d => {
          const cell = astroWeekCell(d.date, sym);
          const prob = cell && cell.prob != null ? Number(cell.prob) : null;
          if (prob == null) return null;
          return Math.round((prob - 0.5) * 200);
        });
        series.push({
          name: (symbolNames[sym] || sym).replace('ETF', ''),
          type: 'line',
          data,
          smooth: true,
          symbol: 'circle',
          symbolSize: 5,
          lineStyle: { width: 2, color: colors[idx % colors.length] },
          itemStyle: { color: colors[idx % colors.length] }
        });
      });
      chart.setOption({
        tooltip: { trigger: 'axis' },
        legend: { bottom: 0, textStyle: { fontSize: 11 } },
        grid: { left: 50, right: 20, top: 10, bottom: 30 },
        xAxis: { type: 'category', data: dayLabels, axisLabel: { fontSize: 10, rotate: 30 } },
        yAxis: { type: 'value', axisLabel: { fontSize: 10, formatter: (v) => (v > 0 ? '+' : '') + v + 'bp' }, splitLine: { lineStyle: { type: 'dashed' } } },
        series
      }, true);
    };

    const submitJournal = async () => {
      if (!journalDay.value) return;
      journalSubmitting.value = true;
      journalStatus.value = '提交中...';
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/journal`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            day: journalDay.value,
            mood: journalMood.value,
            note: journalNote.value
          })
        });
        const json = await res.json();
        if (json && json.ok) {
          journalStatus.value = '已保存';
          await runAstroPredict(journalDay.value);
        }
      } catch (err) { journalStatus.value = '保存失败'; }
      journalSubmitting.value = false;
    };

    const financeFallback = () => {
      const b = baziProfile.value?.bazi?.text ? `八字：${baziProfile.value.bazi.text}` : '';
      const s = [b, '资金纪律：分层仓位、单笔止损、连续亏损停手。', '行为禁忌：追高、频繁还手、无计划加仓。', '执行：先定计划（入场/止损/止盈）再下单。'].filter(Boolean);
      return s.join('\n');
    };

    const dailyRiskFallback = () => {
      const day = astroSelectedDay.value || '';
      const phase = (astroSelectedPhase.value || '').split(' ')[0] || '';
      const bias = marketDirectionText('1');
      const head = [day, phase].filter(Boolean).join(' ');
      const lines = [head ? `${head}：${bias}` : `今日：${bias}`, phase === '满月' ? '满月窗口：优先防守，避免追高与满仓。' : '', phase === '新月' ? '新月窗口：更适合试错与观察，先小仓位。' : '', '若出现系统性风险信号（放量下跌/题材退潮），优先降仓与减少交易频次。'].filter(Boolean);
      return lines.join('\n');
    };

    const ensureFinanceAuto = async (force = false) => {
      const rev = baziPrompts.value?.rev || 'v0';
      const key = baziProfile.value?.bazi?.text ? `astro_finance_auto_${baziProfile.value.bazi.text}_${rev}` : '';
      if (!force && key) {
        const cached = localStorage.getItem(key) || '';
        if (cached) { financeAuto.value = cached; return; }
      }
      financeLoading.value = true;
      const p = baziPrompts.value;
      const du = baziProfile.value?.dayun;
      const duText = du?.current && du?.currentAgeRange ? `${du.current}（${du.currentAgeRange}）` : (du?.current || '');
      const sys = p?.finance?.system || '你是A股交易资金管理教练，输出要简洁可执行，不要出现百分比概率，不要使用项目符号符号，只用换行分段。';
      const user = replaceTemplate(p?.finance?.userTemplate || '请根据以下信息生成"八字财务分析"（3-5行）：\n性别：{{gender}}\n出生：{{birth}}\n出生地：{{place}}\n八字：{{baziText}}', {
        gender: userGender.value, birth: userBirth.value, place: userPlaceText.value,
        baziText: baziProfile.value?.bazi?.text || '', dayun: duText,
        ganzhiYear: baziProfile.value?.bazi?.year || ''
      });
      const txt = await callChat(sys, user);
      financeAuto.value = txt || financeFallback();
      if (key) localStorage.setItem(key, financeAuto.value);
      financeLoading.value = false;
    };

    const ensureDailyRiskAuto = async (force = false) => {
      const day = astroSelectedDay.value || '';
      const b = baziProfile.value?.bazi?.text || '';
      const rev = baziPrompts.value?.rev || 'v0';
      const key = (day && b) ? `astro_daily_risk_auto_${day}_${b}_${rev}` : '';
      if (!force && key) {
        const cached = localStorage.getItem(key) || '';
        if (cached) { dailyRiskAuto.value = cached; return; }
      }
      dailyRiskLoading.value = true;
      const p2 = baziPrompts.value;
      const du2 = baziProfile.value?.dayun;
      const duText2 = du2?.current && du2?.currentAgeRange ? `${du2.current}（${du2.currentAgeRange}）` : (du2?.current || '');
      const sys = p2?.dailyRisk?.system || '你是A股交易风控助手，输出要简洁可执行，不要出现百分比概率，不要使用项目符号符号，只用换行分段。';
      const user = replaceTemplate(p2?.dailyRisk?.userTemplate || '请结合"当日选中日期"的信息，生成"当日操作风险提示"（3-5行）：\n日期：{{day}}\n月相：{{phaseText}}\n次日大盘倾向：{{marketBias}}\n性别：{{gender}}\n出生：{{birth}}\n八字：{{baziText}}', {
        day, phaseText: astroSelectedPhase.value, marketBias: marketDirectionText('1'),
        gender: userGender.value, birth: userBirth.value, baziText: b, dayun: duText2,
        ganzhiYear: baziProfile.value?.bazi?.year || '',
        ganzhiMonth: astroMonthGanzhi.value || '',
        ganzhiDay: astroSelectedGanzhiDay.value || '',
        lunarMonth: '', lunarDay: astroSelectedLunarDay.value || ''
      });
      const txt = await callChat(sys, user);
      dailyRiskAuto.value = txt || dailyRiskFallback();
      if (key) localStorage.setItem(key, dailyRiskAuto.value);
      dailyRiskLoading.value = false;
    };

    watch(baziProfile, () => {
      if (baziReady.value && baziProfile.value && baziProfile.value.ok) {
        ensureFinanceAuto(false);
        ensureDailyRiskAuto(false);
      }
    });

    const astroPhaseSvg = (d) => {
      const idx = Number(d && d.phaseIndex);
      const i = Number.isFinite(idx) ? Math.max(0, Math.min(7, idx)) : 0;

      const paths = [
        "",
        "M 14 2 A 12 12 0 0 1 14 26 A 5 12 0 0 0 14 2",
        "M 14 2 A 12 12 0 0 1 14 26 L 14 2",
        "M 14 2 A 12 12 0 0 1 14 26 A 5 12 0 0 1 14 2",
        "FULL",
        "M 14 2 A 12 12 0 0 0 14 26 A 5 12 0 0 0 14 2",
        "M 14 2 A 12 12 0 0 0 14 26 L 14 2",
        "M 14 2 A 12 12 0 0 0 14 26 A 5 12 0 0 1 14 2"
      ];

      const litPath = paths[i];
      const isFull = litPath === "FULL";
      const isNew = litPath === "";

      const craters = `
        <circle cx="10" cy="12" r="1.5" fill="rgba(0,0,0,0.1)" />
        <circle cx="18" cy="18" r="2.2" fill="rgba(0,0,0,0.08)" />
        <circle cx="15" cy="8" r="1.2" fill="rgba(0,0,0,0.08)" />
        <circle cx="21" cy="12" r="1.8" fill="rgba(0,0,0,0.06)" />
        <circle cx="9" cy="19" r="1.4" fill="rgba(0,0,0,0.08)" />
      `;

      return `
        <svg viewBox="0 0 28 28" width="28" height="28" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <radialGradient id="moonGrad" cx="35%" cy="35%" r="65%">
              <stop offset="0%" stop-color="#FFF9C4"/>
              <stop offset="60%" stop-color="#FDD835"/>
              <stop offset="100%" stop-color="#FBC02D"/>
            </radialGradient>
            <filter id="softTerminator" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur in="SourceGraphic" stdDeviation="0.4" />
            </filter>
            <clipPath id="moonCircle">
              <circle cx="14" cy="14" r="12" />
            </clipPath>
          </defs>
          <circle cx="14" cy="14" r="12" fill="rgba(0,0,0,0.5)" />
          <g filter="url(#softTerminator)">
            ${isFull ?
              `<circle cx="14" cy="14" r="12" fill="url(#moonGrad)" />` :
              (isNew ? '' : `<path d="${litPath}" fill="url(#moonGrad)" />`)
            }
          </g>
          <g clip-path="url(#moonCircle)" style="mix-blend-mode: multiply">
            ${craters}
          </g>
          <circle cx="14" cy="14" r="12" fill="none" stroke="rgba(0,0,0,0.05)" stroke-width="0.5" />
        </svg>
      `;
    };

    const chatMessages = ref([]);
    const chatInput = ref('');
    const chatSending = ref(false);
    const chatError = ref('');

    const journalDay = ref('');
    const journalMood = ref(3);
    const journalNote = ref('');
    const journalSubmitting = ref(false);
    const journalStatus = ref('');

    const loadChat = () => {
      try {
        const raw = localStorage.getItem('m1_astro_chat_v1') || '';
        const arr = raw ? JSON.parse(raw) : null;
        if (Array.isArray(arr)) chatMessages.value = arr.slice(-50);
      } catch (e) { void e; }
    };

    const saveChat = () => {
      try { localStorage.setItem('m1_astro_chat_v1', JSON.stringify(chatMessages.value.slice(-50))); } catch (e) { void e; }
    };

    const clearChat = () => {
      chatMessages.value = [];
      saveChat();
    };

    const scrollChatToBottom = () => {
      nextTick(() => {
        const el = document.getElementById('chat-scroll');
        if (el) el.scrollTop = el.scrollHeight;
      });
    };

    const sendChat = async () => {
      const txt = String(chatInput.value || '').trim();
      if (!txt || chatSending.value) return;
      chatInput.value = '';
      chatError.value = '';
      chatMessages.value.push({ role: 'user', content: txt, ts: Date.now() });
      saveChat();
      nextTick(() => scrollChatToBottom());
      chatSending.value = true;
      try {
        const ctx = {
          selectedDay: astroSelectedDay.value || '',
          monthGanzhi: astroMonthGanzhi.value || '',
          bazi: (baziProfile.value?.ok ? {
            year: baziProfile.value.bazi?.year || '',
            month: baziProfile.value.bazi?.month || '',
            day: baziProfile.value.bazi?.day || '',
            hour: baziProfile.value.bazi?.hour || '',
            text: baziProfile.value.bazi?.text || '',
            dayun: (baziProfile.value.dayun?.current ? {
              current: baziProfile.value.dayun.current,
              currentAgeRange: baziProfile.value.dayun.currentAgeRange || '',
              startAge: baziProfile.value.dayun.startAge,
              all: baziProfile.value.dayun.all || []
            } : undefined)
          } : undefined),
          dayAstro: (astroSelectedDay.value ? {
            ganzhiYear: baziProfile.value?.bazi?.year || '',
            ganzhiMonth: astroMonthGanzhi.value || '',
            ganzhiDay: astroSelectedGanzhiDay.value || '',
            lunarDay: astroSelectedLunarDay.value || '',
            phaseText: astroSelectedPhase.value || ''
          } : undefined)
        };
        const payload = {
          messages: chatMessages.value.map(m => ({ role: m.role, content: m.content })).slice(-20),
          context: ctx
        };
        const res = await fetch(`${API_BASE}/api/ai/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const json = await res.json();
        if (json && json.ok && json.reply) {
          chatMessages.value.push({ role: 'assistant', content: String(json.reply || ''), ts: Date.now() });
          saveChat();
          nextTick(() => scrollChatToBottom());
        } else {
          chatError.value = (json && (json.error || json.msg)) ? String(json.error || json.msg) : '发送失败';
        }
      } catch (e) { chatError.value = '发送失败'; }
      chatSending.value = false;
    };

    onMounted(() => {
      loadChat();
      loadBaziPrompts();
      loadPlaceGroups();
      const d = astroSelectedDay.value || getBeijingToday();
      astroSelectedDay.value = d;
      selectAstroDay(d);
      window.addEventListener('resize', () => {
        Object.values(chartInstances).forEach(chart => chart.resize());
      });
    });

    return {
      astroPredict,
      astroLoading,
      astroSelectedDay,
      astroMonthStr,
      astroMonthGanzhi,
      astroMonthDays,
      astroWeekDays,
      astroWeekRangeText,
      astroWeekTradingDays,
      astroWeekStatus,
      astroSelectedGanzhiDay,
      astroSelectedLunarDay,
      astroSelectedPhase,
      astroPhaseSvg,
      astroPhaseRiskText,
      astroPhaseRiskClass,
      marketTag,
      marketDirectionText,
      astroDirectionText,
      astroProbTag,
      astroProbTagClass,
      astroWeekCellTag,
      astroWeekCellTextClass,
      astroHistoryWindow,
      astroHistorySymbols,
      toggleAstroHistorySymbol,
      renderAstroHistoryChart,
      astroReviewItems,
      astroReviewText,
      selectAstroDay,
      runAstroPredict,
      etfSymbols,
      symbolNames,
      userGender,
      userBirth,
      userPlace,
      userPlaceCustom,
      userArea,
      placeGroups,
      placeAreas,
      placeLoading,
      baziReady,
      baziSubmitted,
      baziProfile,
      baziLoading,
      baziError,
      submitBazi,
      financeAuto,
      financeLoading,
      dailyRiskAuto,
      dailyRiskLoading,
      ensureFinanceAuto,
      ensureDailyRiskAuto,
      monthOutlook,
      editMonthOutlook,
      journalDay,
      journalMood,
      journalNote,
      journalSubmitting,
      journalStatus,
      submitJournal,
      chatMessages,
      chatInput,
      chatSending,
      chatError,
      sendChat,
      clearChat,
      formatAmount
    };
  }
});

app.mount('#app');
