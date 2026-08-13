const { createApp, ref, computed, watch, onMounted } = Vue;
const API_BASE = window.location.origin;

const app = createApp({
  setup() {
    const currentMonth = ref('');
    const monthMacro = ref({ yearGz: '', monthGz: '', summary: '', indexTrend: [] });
    const indexNames = ref([]);       // [{ code, name, pillar }]
    const calendarDays = ref([]);     // 当月交易日格子
    const selectedDay = ref(null);    // 当前选中格子
    const dayDetail = ref(null);      // 选中日的深度推演
    const tagChecks = ref({});        // 因子标记的人工确认状态（date:type -> bool）

    // 命主八字
    const showBaziModal = ref(false);
    const userGender = ref(localStorage.getItem('astro_user_gender') || '');
    const userBirth = ref(localStorage.getItem('astro_user_birth') || '');
    const userPlace = ref(localStorage.getItem('astro_user_place') || '');
    const userPlaceCustom = ref(localStorage.getItem('astro_user_place_custom') || '');
    const userArea = ref(localStorage.getItem('astro_user_area') || '');
    const baziProfile = ref(null);
    const baziLoading = ref(false);
    const baziError = ref('');
    const userPillar = computed(() => (baziProfile.value && baziProfile.value.ok ? (baziProfile.value.bazi.day || '') : ''));

    // 省市数据（下拉框）
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

    const pad2 = (n) => String(n).padStart(2, '0');

    function beijingNowMonth() {
      const d = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }));
      return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}`;
    }

    function shiftMonth(month, delta) {
      const [y, m] = String(month).split('-').map(Number);
      const total = y * 12 + (m - 1) + delta;
      const ny = Math.floor(total / 12);
      const nm = (total % 12) + 1;
      return `${ny}-${pad2(nm)}`;
    }

    async function fetchMonth(month) {
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/astro_calendar_month?month=${encodeURIComponent(month)}&user_pillar=${encodeURIComponent(userPillar.value || '')}`);
        const json = await res.json();
        if (json && json.ok) {
          monthMacro.value = json.macro || { yearGz: '', monthGz: '', summary: '', indexTrend: [] };
          indexNames.value = json.indices || [];
          calendarDays.value = json.days || [];
          const stillValid = selectedDay.value && json.days.some(d => d.date === selectedDay.value.date);
          if (!stillValid) {
            const first = json.days.find(d => !d.disabled);
            if (first) await selectDay(first);
          }
        }
      } catch (e) { console.error('fetchMonth error', e); }
    }

    async function fetchDetail(date) {
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/astro_daily_detail?date=${encodeURIComponent(date)}&user_pillar=${encodeURIComponent(userPillar.value || '')}`);
        const json = await res.json();
        dayDetail.value = (json && json.ok) ? json : null;
      } catch (e) { dayDetail.value = null; }
    }

    async function selectDay(day) {
      if (!day || day.disabled) return;
      selectedDay.value = day;
      dayDetail.value = null;
      await fetchDetail(day.date);
    }

    function prevMonth() {
      currentMonth.value = shiftMonth(currentMonth.value, -1);
      selectedDay.value = null;
      dayDetail.value = null;
      fetchMonth(currentMonth.value);
    }

    function nextMonth() {
      currentMonth.value = shiftMonth(currentMonth.value, 1);
      selectedDay.value = null;
      dayDetail.value = null;
      fetchMonth(currentMonth.value);
    }

    function formatScore(v) {
      const n = Number(v);
      if (!Number.isFinite(n)) return '--';
      return (n > 0 ? '+' : '') + n.toFixed(1);
    }

    function trendClass(trend) {
      const t = String(trend || '');
      if (t === '偏强') return 'text-q-up bg-red-50/60';
      if (t === '偏弱') return 'text-q-down bg-green-50/60';
      return 'text-gray-500 bg-gray-50/60';
    }

    function toggleTag(date, type) {
      const key = `${date}:${type}`;
      tagChecks.value = { ...tagChecks.value, [key]: !tagChecks.value[key] };
    }
    function isTagChecked(date, type) {
      return !!tagChecks.value[`${date}:${type}`];
    }

    async function submitBazi() {
      const birth = String(userBirth.value || '').trim();
      const place = String(userPlaceText.value || '').trim();
      if (!birth) { baziError.value = '请填写出生年月日'; return; }
      if (!place) { baziError.value = '请选择出生地（省市）'; return; }
      baziLoading.value = true;
      baziError.value = '';
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/bazi`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ gender: userGender.value, birth, place, placeDetail: String(userArea.value || '').trim(), trueSolar: true })
        });
        const json = await res.json();
        if (json && json.ok) {
          baziProfile.value = json;
          localStorage.setItem('astro_bazi_profile', JSON.stringify(json));
          localStorage.setItem('astro_user_gender', userGender.value);
          localStorage.setItem('astro_user_birth', userBirth.value);
          localStorage.setItem('astro_user_place', userPlace.value);
          localStorage.setItem('astro_user_place_custom', userPlaceCustom.value);
          localStorage.setItem('astro_user_area', userArea.value);
          showBaziModal.value = false;
          await fetchMonth(currentMonth.value);
          if (selectedDay.value) await fetchDetail(selectedDay.value.date);
        } else {
          baziError.value = (json && json.error) ? String(json.error) : '生成失败';
        }
      } catch (e) {
        baziError.value = String(e.message || '').slice(0, 200);
      }
      baziLoading.value = false;
    }

    onMounted(() => {
      currentMonth.value = beijingNowMonth();
      loadPlaceGroups();
      // 先恢复八字缓存，再拉日历（确保 userPillar 有值，进财/克伐标记正确）
      const cached = localStorage.getItem('astro_bazi_profile');
      if (cached) {
        try { baziProfile.value = JSON.parse(cached); } catch (e) { void e; }
      }
      fetchMonth(currentMonth.value);
      // 无缓存但有出生信息时，自动重新计算（计算成功后内部会重新拉日历）
      if (!baziProfile.value && String(userBirth.value || '').trim() && String(userPlaceText.value || '').trim()) {
        submitBazi();
      }
    });

    return {
      currentMonth,
      monthMacro,
      indexNames,
      calendarDays,
      selectedDay,
      dayDetail,
      userPillar,
      showBaziModal,
      userGender,
      userBirth,
      userPlace,
      userPlaceCustom,
      userArea,
      placeGroups,
      placeAreas,
      placeLoading,
      baziProfile,
      baziLoading,
      baziError,
      tagChecks,
      toggleTag,
      isTagChecked,
      submitBazi,
      selectDay,
      prevMonth,
      nextMonth,
      formatScore,
      trendClass
    };
  }
});

app.mount('#app');
