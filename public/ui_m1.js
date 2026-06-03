const { createApp, ref, onMounted, computed, nextTick, watch } = Vue;

const resolveApiBase = () => {
  try {
    const { protocol, hostname, port } = window.location || {};
    const isLocal = hostname === 'localhost' || hostname === '127.0.0.1';
    if (isLocal && String(port || '') !== '8787') return `${protocol}//${hostname}:8787`;
  } catch (e) { void e; }
  return window.location.origin;
};

const API_BASE = resolveApiBase();

const app = createApp({
  setup() {
    // --- State ---
    const activeTab = ref('overview');
    const activeLifecycleTab = ref('after'); // 'intraday' or 'after'
    const lastUpdate = ref('---');
    const marketAmount = ref(null);
    const lifecycleItems = ref([]);
    const intradaySnapshotItems = ref([]);
    const breadthData = ref({ up: 0, flat: 0, down: 0, total: 0 });
    const volumeHistory = ref([]);
    const intradayVolume = ref([]);
    const intradayYdayVolume = ref([]);
    const volumeStats = ref({ current: 0, ydayTotal: 0, ydaySameTime: 0, forecast: 0, deltaPct: 0 });
    const warmupHistory = ref({});
    const corrDays = ref(parseInt(localStorage.getItem('corrDays')) || 1);
    watch(corrDays, (newVal) => {
      localStorage.setItem('corrDays', newVal);
    });
    const overviewAiText = ref('加载中...');
    const overviewAiUpdatedAt = ref('');
    const overviewAiLoading = ref(false);

    const etfAiText = ref('加载中...');
    const etfAiUpdatedAt = ref('');
    const etfAiLoading = ref(false);

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
      if (!c) {
        userPlace.value = p;
        return;
      }
      if (c === '其他') {
        userPlace.value = cc ? `${p}-${cc}` : p;
        return;
      }
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
          try {
            const res = await fetch(u);
            if (!res || !res.ok) continue;
            return await res.json();
          } catch (e) { void e; }
        }
        return null;
      };
      try {
        const provinces = await fetchJsonFrom([
          'https://unpkg.com/province-city-china@8.5.8/dist/province.json',
          'https://cdn.jsdelivr.net/npm/province-city-china@8.5.8/dist/province.json',
          'https://unpkg.com/province-city-china/dist/province.json',
          'https://cdn.jsdelivr.net/npm/province-city-china/dist/province.json'
        ]);
        const cities = await fetchJsonFrom([
          'https://unpkg.com/province-city-china@8.5.8/dist/city.json',
          'https://cdn.jsdelivr.net/npm/province-city-china@8.5.8/dist/city.json',
          'https://unpkg.com/province-city-china/dist/city.json',
          'https://cdn.jsdelivr.net/npm/province-city-china/dist/city.json'
        ]);
        const areas = await fetchJsonFrom([
          'https://unpkg.com/province-city-china@8.5.8/dist/area.json',
          'https://cdn.jsdelivr.net/npm/province-city-china@8.5.8/dist/area.json',
          'https://unpkg.com/province-city-china/dist/area.json',
          'https://cdn.jsdelivr.net/npm/province-city-china/dist/area.json'
        ]);
        if (!provinces || !cities || !areas) throw new Error('place list fetch failed');
        const pInfo = {};
        for (const p of (Array.isArray(provinces) ? provinces : [])) {
          const key = String(p.province || '').trim();
          if (!key) continue;
          const full = String(p.name || '').trim();
          if (!full) continue;
          pInfo[key] = { full, label: normalizeProvinceName(full) };
        }
        const gMap = {};
        const gSet = {};
        const cityKeyToValue = {};
        const pushOpt = (groupLabel, opt) => {
          if (!groupLabel || !opt || !opt.value) return;
          if (!gMap[groupLabel]) gMap[groupLabel] = [];
          if (!gSet[groupLabel]) gSet[groupLabel] = new Set();
          if (gSet[groupLabel].has(opt.value)) return;
          gSet[groupLabel].add(opt.value);
          gMap[groupLabel].push(opt);
        };
        for (const c of (Array.isArray(cities) ? cities : [])) {
          const pc = String(c.province || '').trim();
          const pi = pInfo[pc];
          if (!pi) continue;
          const cityName = String(c.name || '').trim();
          if (!cityName) continue;
          const cv = `${pi.label}-${cityName}`;
          pushOpt(pi.label, { value: cv, label: cityName });
          const cKey = `${pc}-${String(c.city || '').trim()}`;
          if (pc && cKey && !cityKeyToValue[cKey]) cityKeyToValue[cKey] = cv;
        }
        const groups = [];
        const order = (Array.isArray(provinces) ? provinces : []).map((p) => normalizeProvinceName(p && p.name));
        for (const label of order) {
          if (!label) continue;
          const opts = gMap[label];
          if (!opts || !opts.length) continue;
          groups.push({ label, options: opts });
        }
        for (const label of Object.keys(gMap)) {
          if (order.includes(label)) continue;
          groups.push({ label, options: gMap[label] });
        }
        const areaMap = {};
        const areaSet = {};
        const pushArea = (placeValue, areaName) => {
          const pv = String(placeValue || '').trim();
          const an = String(areaName || '').trim();
          if (!pv || !an) return;
          if (!areaMap[pv]) areaMap[pv] = [];
          if (!areaSet[pv]) areaSet[pv] = new Set();
          if (areaSet[pv].has(an)) return;
          areaSet[pv].add(an);
          areaMap[pv].push(an);
        };
        for (const a of (Array.isArray(areas) ? areas : [])) {
          const pc = String(a.province || '').trim();
          const cc = String(a.city || '').trim();
          const cKey = `${pc}-${cc}`;
          const pv = cityKeyToValue[cKey];
          if (!pv) continue;
          const an = String(a.name || '').trim();
          if (!an) continue;
          pushArea(pv, an);
        }
        placeGroups.value = groups;
        placeAreaMap.value = areaMap;
        try {
          localStorage.setItem(PLACE_DATA_CACHE_KEY, JSON.stringify({ ts: Date.now(), groups, areaMap }));
        } catch (e) { void e; }
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
      if (!arr.length) {
        userArea.value = '';
        return;
      }
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

    const fetchBaziProfile = async () => {
      const birth = String(userBirth.value || '').trim();
      if (!birth) return;
      baziLoading.value = true;
      baziError.value = '';
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/bazi`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            gender: userGender.value,
            birth,
            place: userPlaceText.value,
            placeDetail: String(userArea.value || '').trim(),
            trueSolar: true
          })
        });
        if (!res.ok) {
          const t = await res.text();
          throw new Error(t || `http_${res.status}`);
        }
        const json = await res.json();
        if (json && json.ok) {
          baziProfile.value = json;
        } else {
          baziProfile.value = null;
          baziError.value = json && json.error ? String(json.error) : '生成失败';
        }
      } catch (e) {
        baziProfile.value = null;
        baziError.value = (e && e.message) ? String(e.message).slice(0, 80) : '生成失败';
      } finally {
        baziLoading.value = false;
      }
    };

    const submitBazi = async () => {
      baziSubmitted.value = true;
      if (!baziReady.value) {
        baziError.value = '请先填写性别、出生年月日、出生地';
        return;
      }
      await fetchBaziProfile();
    };

    watch([userGender, userBirth, userPlace, userPlaceCustom, userArea], () => {
      if (!baziSubmitted.value) return;
      baziProfile.value = null;
      baziError.value = '';
      financeAuto.value = '';
      dailyRiskAuto.value = '';
    });

    const astroWeekStatus = ref('');
    const astroWeekTradingDays = computed(() => {
      const days = Array.isArray(astroWeekDays.value) ? astroWeekDays.value : [];
      return days.filter((x) => {
        if (!x || !x.date) return false;
        const dt = new Date(`${x.date}T12:00:00+08:00`);
        const wd = dt.getDay();
        return wd >= 1 && wd <= 5;
      });
    });
    const astroWeekMatrix = ref({});
    const astroPrevCache = {};
    const astroPredCache = {};
    const journalDay = ref('');
    const journalMood = ref(3);
    const journalNote = ref('');
    const journalSubmitting = ref(false);
    const journalStatus = ref('');

    const chatMessages = ref([]);
    const chatInput = ref('');
    const chatSending = ref(false);
    const chatError = ref('');

    const loadChat = () => {
      try {
        const raw = localStorage.getItem('m1_ai_chat_v1') || '';
        const arr = raw ? JSON.parse(raw) : [];
        chatMessages.value = Array.isArray(arr) ? arr : [];
      } catch (e) { void e; }
    };

    const saveChat = () => {
      try {
        localStorage.setItem('m1_ai_chat_v1', JSON.stringify(chatMessages.value || []));
      } catch (e) { void e; }
    };

    const clearChat = () => {
      chatMessages.value = [];
      chatError.value = '';
      saveChat();
    };

    const scrollChatToBottom = () => {
      try {
        const el = document.getElementById('chat-scroll');
        if (!el) return;
        el.scrollTop = el.scrollHeight;
      } catch (e) { void e; }
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
        const payload = {
          messages: chatMessages.value.map(m => ({ role: m.role, content: m.content })).slice(-20),
          context: {
            activeTab: activeTab.value,
            selectedDay: astroSelectedDay.value || '',
            monthGanzhi: astroMonthGanzhi.value || ''
          }
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
      } catch (e) {
        chatError.value = '发送失败';
      } finally {
        chatSending.value = false;
      }
    };

    const SIM_KEY = 'm1_sim_account_v1';
    const simConfig = ref({
      initialCash: Number(localStorage.getItem('sim_initial_cash') || 100000),
      rebalanceBandPct: Number(localStorage.getItem('sim_rebalance_band_pct') || 5),
      maxCategoryPct: Number(localStorage.getItem('sim_max_category_pct') || 30)
    });
    const simState = ref({
      cash: 0,
      positions: {},
      trades: []
    });
    const suggestionOverrides = ref({});
    const selectedSuggestions = ref({});
    const tradeConfirmOpen = ref(false);
    const tradeConfirmItems = ref([]);
    const tradeConfirmError = ref('');
    const tradeBottomTab = ref('positions');

    const holdingsScreenshot = ref(localStorage.getItem('sim_holdings_screenshot') || '');
    const holdingsScreenshotUpdatedAt = ref(localStorage.getItem('sim_holdings_screenshot_at') || '');

    const onHoldingsScreenshot = async (ev) => {
      try {
        const file = ev?.target?.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
          const dataUrl = String(reader.result || '');
          holdingsScreenshot.value = dataUrl;
          holdingsScreenshotUpdatedAt.value = String(Date.now());
          localStorage.setItem('sim_holdings_screenshot', dataUrl);
          localStorage.setItem('sim_holdings_screenshot_at', holdingsScreenshotUpdatedAt.value);
        };
        reader.readAsDataURL(file);
      } catch (e) { void e; }
    };
    
    // Indices config
    const indexSymbols = ['sh000001', 'sz399001', 'sz399006', 'sh000688', 'sh000300', 'sh000852', 'sh511130', 'sh511260', 'bank', 'broker', 'insure'];
    const etfSymbols = ['sh512400', 'sh512480', 'sh515120', 'sh515880', 'sh516010', 'sh516160', 'sh516510', 'sh562500', 'sh563530'];
    const symbolNames = {
      'sh000001': '上证指数',
      'sz399001': '深证成指',
      'sz399006': '创业板指',
      'sh000688': '科创50',
      'sh000300': '沪深300',
      'sh000852': '中证1000',
      'sh511130': '30年国债ETF',
      'sh511260': '10年国债ETF',
      'bank': '银行',
      'broker': '证券',
      'insure': '保险',
      'sh512400': '有色金属ETF',  
      'sh512480': '半导体ETF',
      'sh515120': '创新药ETF',
      'sh515880': '通信ETF',
      'sh516010': '游戏ETF',
      'sh516160': '新能源ETF',
      'sh516510': '云计算ETF',
      'sh562500': '机器人ETF',
      'sh563530': '商业航天ETF'
    };

    const etfCategoryMap = {
      'sh512480': '科技',
      'sh515880': '科技',
      'sh516510': '科技',
      'sh516010': '科技',
      'sh563530': '科技',
      'sh562500': '科技',
      'sh515120': '科技',
      'sh512400': '资源',
      'sh516160': '资源'
    };
    
    // Charting state
    const currentPrices = ref({});
    const minuteDataCache = ref({});
    const chartsLoaded = ref({});
    const chartInstances = {};

    // 解析AI返回的 Markdown 文本
    const parseAiSections = (txt) => {
      if (!txt) return [];
      if (txt === '加载中...' || txt === '等待接入...' || txt === '暂无今日 AI 解读数据' || txt === 'AI 板块解析加载中...') return [{ title: '', content: txt }];
      
      const lines = txt.split('\n');
      const sections = [];
      let currentTitle = '';
      let currentContent = [];
      
      for (const line of lines) {
        if (line.includes('===') || !line.trim()) continue;
        
        // 尝试匹配老版本的格式，如 **【走势判断】**
        let isOldFormat = false;
        const oldTitleMatch = line.match(/^(?:\*\*)?【([^】]+)】(?:\*\*)?\s*(.*)/);
        if (oldTitleMatch) {
            isOldFormat = true;
            if (currentTitle) {
              sections.push({ title: currentTitle, content: currentContent.join('\n').trim() });
            }
            currentTitle = oldTitleMatch[1].trim();
            currentContent = [];
            // 如果标题后面紧跟了正文，保留正文内容
            const rest = oldTitleMatch[2].trim();
            if (rest) {
              currentContent.push(rest);
            }
            continue;
        }
        
        // 匹配带有 ** 的标题，例如 **走势判断**： 或者直接 走势判断：
        // 允许标题中包含空格，并且处理可能的双角冒号
        const titleMatch = line.match(/^(?:\*\*)?\s*([^：:]+?)\s*(?:\*\*)?[：:](.*)/);
        
        if (!isOldFormat && titleMatch && ['走势判断', '情绪定性', '阵营轮动', '资金风格', '操作建议', '盘面核心特征', '异动与风向', '交易员应对策略', '主线追踪', '资金偏好', '主线与异动', '阵营跷跷板', '跷跷板效应', '异动解读', '轮动建议', '重点异动', '轮动分析', '行情研判', '赚钱效应', '跷跷板分析', '共振分析', '轮动规律', '主线趋势'].includes(titleMatch[1].trim())) {
          if (currentTitle) {
            sections.push({ title: currentTitle, content: currentContent.join('\n').trim().replace(/\*\*([^*]+)\*\*/g, '<strong class="text-q-primary">$1</strong>') });
          }
          currentTitle = titleMatch[1].trim();
          currentContent = [];
          
          // 把冒号后面的内容放进 content，保留 markdown 加粗标记交由前端解析
          const rest = titleMatch[2].trim();
          if (rest) currentContent.push(rest);
        } else {
          if (currentTitle) {
            // 保留内容里的 markdown 加粗标记
            currentContent.push(line.trim());
          } else {
            // 如果一开始就没有匹配到任何标题，就把所有内容放在一个默认区域里
            currentContent.push(line.trim());
          }
        }
      }
      
      if (currentTitle) {
        sections.push({ title: currentTitle, content: currentContent.join('\n').trim().replace(/\*\*([^*]+)\*\*/g, '<strong class="text-q-primary">$1</strong>') });
      } else if (currentContent.length > 0) {
        sections.push({ title: '', content: currentContent.join('\n').trim().replace(/\*\*([^*]+)\*\*/g, '<strong class="text-q-primary">$1</strong>') });
      }
      
      return sections.length > 0 ? sections.map(s => {
        // 如果是最后补上去的段落，且内部含有 markdown bold，顺手替换掉
        if (s.content && s.content.includes('**')) {
           s.content = s.content.replace(/\*\*([^*]+)\*\*/g, '<strong class="text-q-primary">$1</strong>');
        }
        return s;
      }) : [{ title: '原文', content: txt }];
    };

    const overviewAiSections = computed(() => parseAiSections(overviewAiText.value));
    const etfAiSections = computed(() => parseAiSections(etfAiText.value));

    // 解析仓位进度条 (例如提取 "2-4成" -> 30, "6-8成" -> 70, "5成" -> 50)
    const overviewAiPositionPct = computed(() => {
      const txt = overviewAiText.value || '';
      const match = txt.match(/(\d)(?:-(\d))?成仓位/);
      if (match) {
        if (match[2]) {
          return (parseInt(match[1]) + parseInt(match[2])) / 2 * 10;
        }
        return parseInt(match[1]) * 10;
      }
      // 兼容其他写法
      const match2 = txt.match(/建议(.*?)([2-8])/);
      if (match2) return parseInt(match2[2]) * 10;
      return 50; // 默认50
    });

    const refreshOverviewAi = async (force = false) => {
      if (overviewAiLoading.value) return;
      overviewAiLoading.value = true;
      try {
        const res = await fetch(`${API_BASE}/api/ai/report${force ? '?force=true' : ''}`);
        const d = await res.json();
        if (d.ok && d.data) {
          overviewAiText.value = d.data.content || '';
          overviewAiUpdatedAt.value = d.data.asOf || '';
        } else {
          overviewAiText.value = '暂无今日 AI 解读数据';
          overviewAiUpdatedAt.value = '';
        }
      } catch (e) {
        overviewAiText.value = 'AI 解读加载失败';
      } finally {
        overviewAiLoading.value = false;
      }
    };

    const refreshEtfAi = async () => {
      if (etfAiLoading.value) return;
      etfAiLoading.value = true;
      try {
        const res = await fetch(`${API_BASE}/api/ai/sector-analysis`);
        const d = await res.json();
        if (d.text) {
          etfAiText.value = d.text;
          etfAiUpdatedAt.value = d.asOf || '';
        } else {
          etfAiText.value = '暂无今日 AI 板块解析数据';
          etfAiUpdatedAt.value = '';
        }
      } catch (e) {
        etfAiText.value = 'AI 板块解析加载失败';
        etfAiUpdatedAt.value = '';
      } finally {
        etfAiLoading.value = false;
      }
    };

    // Computed
    const intradayItems = computed(() => {
      const items = intradaySnapshotItems.value || [];
      return items.filter(item => item.symbol && etfSymbols.includes(item.symbol));
    });

    const intradayHold = computed(() => {
      const items = intradayItems.value || [];
      return items.filter(item => item.category_pool === '趋势向上/风险可控' || item.category_pool === '持有池');
    });

    const intradayWait = computed(() => {
      const items = intradayItems.value || [];
      return items.filter(item => item.category_pool === '观望/回避' || item.category_pool === '观望池');
    });

    const intradaySell = computed(() => {
      const items = intradayItems.value || [];
      return items.filter(item => item.category_pool === '高位/高风险' || item.category_pool === '高位/风险池');
    });
    
    const etfLifecycleItems = computed(() => {
      const items = lifecycleItems.value || [];
      // 只保留 etfSymbols 里的 9 个核心 ETF
      return items.filter(item => item.symbol && etfSymbols.includes(item.symbol));
    });

    const getClose = (rec) => {
      if (!rec) return null;
      const v = rec.close ?? rec.Close ?? rec.price ?? rec.last ?? null;
      const n = Number(v);
      return Number.isFinite(n) ? n : null;
    };

    const calcBias20FromWarmup = (sym) => {
      const hist = warmupHistory.value?.[sym] || [];
      if (!Array.isArray(hist) || hist.length < 25) return { bias20: null, max: null, series: [] };
      const closes = hist.map(getClose);
      const series = [];
      for (let i = 0; i < closes.length; i++) {
        if (i < 19) {
          series.push(null);
          continue;
        }
        let sum = 0;
        let cnt = 0;
        for (let j = i - 19; j <= i; j++) {
          const c = closes[j];
          if (c == null) continue;
          sum += c;
          cnt++;
        }
        if (cnt < 15) {
          series.push(null);
          continue;
        }
        const ma20 = sum / cnt;
        if (!ma20) {
          series.push(null);
          continue;
        }
        const c0 = closes[i];
        if (c0 == null) {
          series.push(null);
          continue;
        }
        series.push(((c0 - ma20) / ma20) * 100);
      }
      const finite = series.filter(v => Number.isFinite(v));
      if (!finite.length) return { bias20: null, max: null, series };
      return { bias20: finite[finite.length - 1], max: Math.max(...finite), series };
    };

    const getBiasMetrics = (item) => {
      const ind = item?.指标数据 || {};
      const bias20 = Number(ind.Bias_20 ?? ind.bias_20 ?? null);
      const max = Number(ind.Bias_20_History_Max ?? ind.bias_20_history_max ?? null);
      if (Number.isFinite(bias20) && Number.isFinite(max) && max !== 0) return { bias20, max, series: [] };
      return calcBias20FromWarmup(item?.symbol);
    };

    const isUpTrend = (item) => {
      const m = item?.动能 || '';
      return m.includes('强势向上') || m.includes('偏强向上');
    };

    const isNearExtreme = (item) => {
      const { bias20, max } = getBiasMetrics(item);
      if (!Number.isFinite(bias20) || !Number.isFinite(max) || max === 0) return false;
      return bias20 >= 0.9 * max || bias20 > max;
    };

    const etfLifecycleSell = computed(() => {
      const items = etfLifecycleItems.value || [];
      return items.filter(item => {
        const m = item?.动能 || '';
        if (!m.includes('强势向上')) return false;
        return isNearExtreme(item);
      });
    });

    const etfLifecycleHold = computed(() => {
      const items = etfLifecycleItems.value || [];
      const sellIds = new Set(etfLifecycleSell.value.map(i => i.symbol));
      return items.filter(item => {
        if (sellIds.has(item.symbol)) return false; // 排除已经进入高风险极值池的
        return isUpTrend(item);
      });
    });

    const etfLifecycleWait = computed(() => {
      const items = etfLifecycleItems.value || [];
      const sellIds = new Set(etfLifecycleSell.value.map(i => i.symbol));
      const holdIds = new Set(etfLifecycleHold.value.map(i => i.symbol));
      return items.filter(item => {
        if (sellIds.has(item.symbol) || holdIds.has(item.symbol)) return false;
        return true;
      });
    });

    const etfLifecycleOther = computed(() => {
      const items = etfLifecycleItems.value || [];
      const holdIds = new Set(etfLifecycleHold.value.map(i => i.symbol));
      const waitIds = new Set(etfLifecycleWait.value.map(i => i.symbol));
      const sellIds = new Set(etfLifecycleSell.value.map(i => i.symbol));
      
      return items.filter(item => !holdIds.has(item.symbol) && !waitIds.has(item.symbol) && !sellIds.has(item.symbol));
    });

    // --- Format Helpers ---
    const fmtPct = (v) => {
      if (v == null || isNaN(v)) return '-';
      const num = Number(v).toFixed(2);
      return num > 0 ? `+${num}%` : `${num}%`;
    };

    const fmtHeatDelta = (v) => {
      if (v == null || isNaN(v)) return '-';
      const num = Number(v).toFixed(2);
      return num > 0 ? `+${num}%` : `${num}%`;
    };

    const getItemStats = (item) => {
      const ydayPct = item.昨日涨跌幅 ?? null;
      let nowPct = currentPrices.value[item.symbol]?.pct;
      if (nowPct == null) {
        nowPct = item.指标数据?.pct ?? item.指标数据?.Pct ?? null;
      }
      
      let tag = '-';
      if (ydayPct != null && nowPct != null) {
        const y = Number(ydayPct);
        const n = Number(nowPct);
        if (y <= -1 && n >= 0.5) tag = '修复转强';
        else if (y < 0 && n > 0) tag = '转强';
        else if (y > 0 && n < 0) tag = '转弱';
        else if (n >= 1) tag = '今日强势';
        else if (y < 0 && n < 0 && n > y) tag = '跌势收敛';
        else if (y < 0 && n < 0 && n < y) tag = '跌势加剧';
        else if (n <= -1) tag = '今日走弱';
      }

      let shareChange = item.指标数据?.Amount_Share_Change_Pct ?? item.指标数据?.Amount_Share_Change ?? null;

      return {
        ydayPct,
        nowPct,
        tag,
        shareChange
      };
    };

    const getLastPrice = (sym) => {
      const p = currentPrices.value?.[sym]?.price;
      if (Number.isFinite(p) && p > 0) return p;
      const hist = warmupHistory.value?.[sym];
      if (Array.isArray(hist) && hist.length > 0) {
        const c = getClose(hist[hist.length - 1]);
        if (Number.isFinite(c) && c > 0) return c;
      }
      return null;
    };

    const simPositionsList = computed(() => {
      const pos = simState.value.positions || {};
      const symbols = Object.keys(pos);
      const out = symbols.map((sym) => {
        const p = pos[sym];
        const shares = Number(p?.shares || 0);
        const avgPrice = Number(p?.avgPrice || 0);
        const lastPrice = getLastPrice(sym);
        const value = lastPrice ? shares * lastPrice : 0;
        const pnl = lastPrice ? (lastPrice - avgPrice) * shares : 0;
        return { symbol: sym, shares, avgPrice, lastPrice, value, pnl };
      });
      out.sort((a, b) => (b.value || 0) - (a.value || 0));
      return out;
    });

    const simMetrics = computed(() => {
      const positionsValue = simPositionsList.value.reduce((acc, p) => acc + (p.value || 0), 0);
      const cash = Number(simState.value.cash || 0);
      const equity = cash + positionsValue;
      const initial = Number(simConfig.value.initialCash || 0);
      const pnl = equity - initial;
      const positionPct = equity > 0 ? positionsValue / equity : 0;
      return { cash, positionsValue, equity, pnl, positionPct };
    });

    const simTradesLatest = computed(() => {
      const arr = Array.isArray(simState.value.trades) ? simState.value.trades : [];
      return [...arr].slice(-50).reverse();
    });

    const simInitialMissing = computed(() => {
      const v = Number(simConfig.value.initialCash || 0);
      return !(Number.isFinite(v) && v > 0);
    });

    const simCategoryExposure = computed(() => {
      const equity = simMetrics.value.equity || 0;
      if (equity <= 0) return {};
      const map = {};
      simPositionsList.value.forEach((p) => {
        const cat = etfCategoryMap[p.symbol] || '未分类';
        map[cat] = (map[cat] || 0) + (p.value || 0);
      });
      Object.keys(map).forEach((k) => {
        map[k] = map[k] / equity;
      });
      return map;
    });

    const simCategoryExposureList = computed(() => {
      const m = simCategoryExposure.value || {};
      const out = Object.keys(m).map((k) => ({ category: k, pct: Number(m[k] || 0) }));
      out.sort((a, b) => (b.pct || 0) - (a.pct || 0));
      return out;
    });

    const simMajorExposure = computed(() => {
      const m = simCategoryExposure.value || {};
      const tech = Number(m['科技'] || 0);
      const res = Number(m['资源'] || 0);
      const other = Object.keys(m).reduce((acc, k) => {
        if (k === '科技' || k === '资源') return acc;
        const v = Number(m[k] || 0);
        return acc + (Number.isFinite(v) ? v : 0);
      }, 0);
      return {
        tech: Number.isFinite(tech) ? tech : 0,
        resource: Number.isFinite(res) ? res : 0,
        other: Number.isFinite(other) ? other : 0
      };
    });

    const simRiskAlerts = computed(() => {
      const alerts = [];
      const maxPct = Number(simConfig.value.maxCategoryPct || 0) / 100;
      const exposure = simCategoryExposure.value || {};
      Object.keys(exposure).forEach((cat) => {
        const pct = exposure[cat];
        if (!Number.isFinite(pct)) return;
        if (pct > maxPct && maxPct > 0) {
          alerts.push({
            key: `cat:${cat}`,
            level: pct > maxPct * 1.15 ? 'high' : 'mid',
            title: `板块超配：${cat}`,
            value: `${(pct * 100).toFixed(1)}%`
          });
        }
      });
      if ((simMetrics.value.cash || 0) < 0) {
        alerts.push({ key: 'cash:neg', level: 'high', title: '现金为负', value: fmtCny(simMetrics.value.cash) });
      }
      return alerts;
    });

    const getPositionValue = (sym) => {
      const p = simState.value.positions?.[sym];
      if (!p) return 0;
      const shares = Number(p.shares || 0);
      const lastPrice = getLastPrice(sym);
      if (!lastPrice) return 0;
      return shares * lastPrice;
    };

    const tradeSuggestions = computed(() => {
      const equity = simMetrics.value.equity || 0;
      if (equity <= 0) return [];
      const band = Math.max(0, Number(simConfig.value.rebalanceBandPct || 0)) / 100;
      const holdSyms = (etfLifecycleHold.value || []).map(i => i.symbol);
      const sellSyms = (etfLifecycleSell.value || []).map(i => i.symbol);
      const holdSet = new Set(holdSyms);
      const sellSet = new Set(sellSyms);
      if (!holdSyms.length && !sellSyms.length) return [];

      const targets = {};
      if (holdSyms.length) {
        const w = 1 / holdSyms.length;
        holdSyms.forEach((s) => { targets[s] = w; });
      }
      sellSyms.forEach((s) => { targets[s] = 0; });

      const suggestions = [];
      Object.keys(targets).forEach((sym) => {
        const targetWeight = targets[sym];
        const curVal = getPositionValue(sym);
        const curW = equity > 0 ? curVal / equity : 0;
        const delta = targetWeight - curW;
        if (Math.abs(delta) < band) return;

        const action = delta > 0 ? 'BUY' : 'SELL';
        let notional = Math.abs(delta) * equity;
        if (action === 'BUY') notional = Math.min(notional, Math.max(0, Number(simState.value.cash || 0)));
        if (action === 'SELL') notional = Math.min(notional, curVal);
        if (notional <= 0) return;

        const cat = etfCategoryMap[sym] || '未分类';
        const item = (etfLifecycleItems.value || []).find(i => i.symbol === sym);
        let reason = sellSet.has(sym)
          ? `高风险极值：${item?.动能 || '高位风险'}，建议减仓至0%`
          : (holdSet.has(sym) ? `趋势向上：${item?.动能 || '趋势向上'}，等权目标配置` : '等待趋势信号');
        if (sym === 'sh512400') {
          if (sellSet.has(sym)) reason = `有色强势高位，偏离均线接近极值，先落袋减仓；动能：${item?.动能 || '高位风险'}`;
          else if (holdSet.has(sym)) reason = `有色趋势偏强，优先考虑回撤分批吸；动能：${item?.动能 || '趋势向上'}`;
          else reason = `有色暂无明确优势，先观望等待趋势确认`;
        }

        suggestions.push({
          symbol: sym,
          category: cat,
          action,
          targetWeight,
          currentWeight: curW,
          deltaWeight: delta,
          notional: Math.round(notional),
          reason
        });
      });

      suggestions.sort((a, b) => Math.abs(b.deltaWeight) - Math.abs(a.deltaWeight));
      return suggestions;
    });

    const tradeSuggestionMap = computed(() => {
      const m = {};
      (tradeSuggestions.value || []).forEach((s) => { m[s.symbol] = s; });
      return m;
    });

    const getLifecyclePool = (sym) => {
      const sell = (etfLifecycleSell.value || []).some(i => i.symbol === sym);
      if (sell) return '高风险';
      const hold = (etfLifecycleHold.value || []).some(i => i.symbol === sym);
      if (hold) return '趋势向上';
      return '观望';
    };

    const tradeTableRows = computed(() => {
      const equity = simMetrics.value.equity || 0;
      const holdCount = (etfLifecycleHold.value || []).length;
      const holdTarget = holdCount > 0 ? 1 / holdCount : 0;
      return (etfSymbols || []).map((sym) => {
        const sugg = tradeSuggestionMap.value?.[sym] || null;
        const val = getPositionValue(sym);
        const w = equity > 0 ? val / equity : 0;
        const pool = getLifecyclePool(sym);
        const action = sugg ? (sugg.action === 'BUY' ? '买入' : '卖出') : '不动';
        const targetWeight = sugg ? sugg.targetWeight : (pool === '趋势向上' ? holdTarget : 0);
        const amt = sugg ? Number(suggestionOverrides.value?.[sym] ?? sugg.notional) : 0;
        const selectable = !!sugg;
        const item = (etfLifecycleItems.value || []).find(i => i.symbol === sym);
        const momentum = item?.动能 || '';
        const reason = sugg ? sugg.reason : (momentum ? `趋势信号：${momentum}` : '等待趋势信号');
        return {
          symbol: sym,
          name: symbolNames[sym] || sym,
          category: etfCategoryMap[sym] || '未分类',
          pool,
          currentWeight: w,
          targetWeight,
          action,
          selectable,
          amount: amt,
          reason
        };
      }).sort((a, b) => {
        if (a.selectable !== b.selectable) return a.selectable ? -1 : 1;
        if (a.pool !== b.pool) return a.pool === '趋势向上' ? -1 : (b.pool === '趋势向上' ? 1 : (a.pool === '高风险' ? -1 : 1));
        return (b.currentWeight || 0) - (a.currentWeight || 0);
      });
    });

    watch(tradeSuggestions, (items) => {
      const next = { ...suggestionOverrides.value };
      (items || []).forEach((s) => {
        if (next[s.symbol] == null) next[s.symbol] = s.notional;
      });
      Object.keys(next).forEach((k) => {
        if (!(items || []).some(s => s.symbol === k)) delete next[k];
      });
      suggestionOverrides.value = next;

      const nextSel = { ...selectedSuggestions.value };
      Object.keys(nextSel).forEach((k) => {
        if (!(items || []).some(s => s.symbol === k)) delete nextSel[k];
      });
      selectedSuggestions.value = nextSel;
    }, { immediate: true });

    const calcLotShares = ({ amount, price, lot }) => {
      const amt = Math.max(0, Number(amount || 0));
      const p = Number(price || 0);
      if (!Number.isFinite(amt) || !Number.isFinite(p) || p <= 0) return 0;
      const l = Math.max(1, Number(lot || 100));
      return Math.floor(amt / p / l) * l;
    };

    const applySimTradeExact = ({ symbol, side, shares, price, reason }) => {
      const lot = 100;
      const p = Number(price || 0);
      const sh = Math.floor(Number(shares || 0) / lot) * lot;
      if (!symbol || !Number.isFinite(p) || p <= 0) return { ok: false, error: '价格无效' };
      if (!Number.isFinite(sh) || sh <= 0) return { ok: false, error: '份额无效' };

      const pos0 = simState.value.positions?.[symbol] || { shares: 0, avgPrice: 0 };
      const curShares = Math.max(0, Number(pos0.shares || 0));
      const curAvg = Number(pos0.avgPrice || 0);
      const notional = sh * p;

      if (side === 'BUY') {
        const cash = Math.max(0, Number(simState.value.cash || 0));
        if (notional > cash) return { ok: false, error: '现金不足' };
        const newShares = curShares + sh;
        const newAvg = newShares > 0 ? ((curShares * curAvg) + notional) / newShares : 0;
        simState.value.cash = cash - notional;
        simState.value.positions[symbol] = { shares: newShares, avgPrice: newAvg };
        simState.value.trades.push({
          id: `${Date.now()}_${symbol}_B`,
          ts: nowTs(),
          symbol,
          side: 'BUY',
          shares: sh,
          price: p,
          notional,
          reason: reason || ''
        });
        saveSimLocal();
        return { ok: true };
      }

      if (side === 'SELL') {
        if (sh > curShares) return { ok: false, error: '份额超过持仓' };
        const cash = Math.max(0, Number(simState.value.cash || 0));
        simState.value.cash = cash + notional;
        const newShares = curShares - sh;
        if (newShares <= 0) delete simState.value.positions[symbol];
        else simState.value.positions[symbol] = { shares: newShares, avgPrice: curAvg };
        simState.value.trades.push({
          id: `${Date.now()}_${symbol}_S`,
          ts: nowTs(),
          symbol,
          side: 'SELL',
          shares: sh,
          price: p,
          notional,
          reason: reason || ''
        });
        saveSimLocal();
        return { ok: true };
      }

      return { ok: false, error: '方向无效' };
    };

    const openTradeConfirmForSymbols = (symbols) => {
      const syms = Array.isArray(symbols) ? symbols : [];
      const items = [];
      const lot = 100;
      (syms || []).forEach((symbol) => {
        const s = (tradeSuggestions.value || []).find(x => x.symbol === symbol);
        if (!s) return;
        const price = getLastPrice(symbol) || 0;
        const amt = Number(suggestionOverrides.value?.[symbol] ?? s.notional);
        const held = Math.max(0, Number(simState.value.positions?.[symbol]?.shares || 0));
        let shares = 0;
        if (s.action === 'BUY') {
          shares = calcLotShares({ amount: amt, price, lot });
        } else if (s.action === 'SELL') {
          const req = calcLotShares({ amount: amt, price, lot });
          shares = req > 0 ? Math.min(held, req) : held;
        }
        items.push({
          symbol,
          name: symbolNames[symbol] || symbol,
          side: s.action,
          price: Number(price || 0),
          shares: Number(shares || 0),
          lot,
          reason: s.reason || ''
        });
      });
      tradeConfirmItems.value = items;
      tradeConfirmError.value = '';
      tradeConfirmOpen.value = true;
    };

    const closeTradeConfirm = () => {
      tradeConfirmOpen.value = false;
      tradeConfirmItems.value = [];
      tradeConfirmError.value = '';
    };

    const confirmTradeConfirm = () => {
      tradeConfirmError.value = '';
      const items = tradeConfirmItems.value || [];
      if (!items.length) {
        tradeConfirmError.value = '没有可执行的建议';
        return;
      }
      for (const it of items) {
        const p = Number(it.price || 0);
        const sh = Number(it.shares || 0);
        const lot = Number(it.lot || 100);
        if (!Number.isFinite(p) || p <= 0) {
          tradeConfirmError.value = `${it.name} 价格无效`;
          return;
        }
        if (!Number.isFinite(sh) || sh <= 0 || sh % lot !== 0) {
          tradeConfirmError.value = `${it.name} 份额需为 ${lot} 的整数倍`;
          return;
        }
        if (it.side === 'SELL') {
          const held = Math.max(0, Number(simState.value.positions?.[it.symbol]?.shares || 0));
          if (sh > held) {
            tradeConfirmError.value = `${it.name} 卖出份额超过持仓`;
            return;
          }
        } else if (it.side === 'BUY') {
          const cash = Math.max(0, Number(simState.value.cash || 0));
          if (sh * p > cash) {
            tradeConfirmError.value = `${it.name} 现金不足`;
            return;
          }
        }
      }

      const selectedMap = { ...selectedSuggestions.value };
      for (const it of items) {
        const r = applySimTradeExact({ symbol: it.symbol, side: it.side, shares: it.shares, price: it.price, reason: it.reason });
        if (!r.ok) {
          tradeConfirmError.value = `${it.name} 执行失败：${r.error || '未知原因'}`;
          return;
        }
        if (selectedMap[it.symbol]) selectedMap[it.symbol] = false;
      }
      selectedSuggestions.value = selectedMap;
      closeTradeConfirm();
    };

    const executeSuggestion = (symbol) => {
      openTradeConfirmForSymbols([symbol]);
    };

    const tradeSelectedCount = computed(() => {
      const m = selectedSuggestions.value || {};
      return Object.keys(m).filter((k) => !!m[k]).length;
    });

    const tradeSelectableSymbols = computed(() => (tradeSuggestions.value || []).map(s => s.symbol));

    const tradeAllSelected = computed(() => {
      const syms = tradeSelectableSymbols.value || [];
      if (!syms.length) return false;
      return syms.every((s) => !!selectedSuggestions.value?.[s]);
    });

    const toggleTradeSelectAll = () => {
      const syms = tradeSelectableSymbols.value || [];
      if (!syms.length) return;
      const next = !tradeAllSelected.value;
      const m = { ...selectedSuggestions.value };
      syms.forEach((s) => { m[s] = next; });
      selectedSuggestions.value = m;
    };

    const executeSelectedSuggestions = () => {
      const syms = tradeSelectableSymbols.value || [];
      const picked = syms.filter((s) => !!selectedSuggestions.value?.[s]);
      openTradeConfirmForSymbols(picked);
    };

    // --- Helpers ---
    const formatAmount = (val) => {
      if (!val) return '---';
      return (val / 1e8).toFixed(2) + '亿';
    };

    const fmtCny = (val) => {
      const n = Number(val);
      if (!Number.isFinite(n)) return '-';
      const sign = n < 0 ? '-' : '';
      const abs = Math.abs(n);
      return sign + abs.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    };

    const pad2 = (n) => String(n).padStart(2, '0');
    const nowTs = () => {
      const d = new Date();
      return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
    };

    const saveSimLocal = () => {
      localStorage.setItem('sim_initial_cash', String(simConfig.value.initialCash || 0));
      localStorage.setItem('sim_rebalance_band_pct', String(simConfig.value.rebalanceBandPct || 0));
      localStorage.setItem('sim_max_category_pct', String(simConfig.value.maxCategoryPct || 0));
      localStorage.removeItem('sim_commission_bps');
      localStorage.setItem(SIM_KEY, JSON.stringify({
        config: simConfig.value,
        state: simState.value
      }));
    };

    const loadSimLocal = () => {
      try {
        const raw = localStorage.getItem(SIM_KEY);
        if (!raw) return false;
        const parsed = JSON.parse(raw);
        if (parsed?.config) {
          const c = parsed.config || {};
          simConfig.value = {
            initialCash: Number(c.initialCash ?? simConfig.value.initialCash),
            rebalanceBandPct: Number(c.rebalanceBandPct ?? simConfig.value.rebalanceBandPct),
            maxCategoryPct: Number(c.maxCategoryPct ?? simConfig.value.maxCategoryPct)
          };
        }
        if (parsed?.state) simState.value = { ...simState.value, ...parsed.state };
        if (!Number.isFinite(Number(simState.value.cash))) simState.value.cash = Number(simConfig.value.initialCash) || 0;
        if (!simState.value.positions || typeof simState.value.positions !== 'object') simState.value.positions = {};
        if (!Array.isArray(simState.value.trades)) simState.value.trades = [];
        return true;
      } catch (e) {
        return false;
      }
    };

    const resetSimAccount = () => {
      const initial = Number(simConfig.value.initialCash) || 0;
      simState.value = { cash: initial, positions: {}, trades: [] };
      suggestionOverrides.value = {};
      saveSimLocal();
    };

    if (!loadSimLocal()) {
      resetSimAccount();
    }

    watch(simConfig, () => saveSimLocal(), { deep: true });

    const getPriceColor = (val) => {
      if (val === undefined || val === null) return 'text-quant-flat';
      return val > 0 ? 'text-quant-up' : (val < 0 ? 'text-quant-down' : 'text-quant-flat');
    };

    const getAdviceBgClass = (advice) => {
      if (!advice) return 'bg-gray-200';
      if (advice.includes('建仓') || advice.includes('持') || advice.includes('低吸') || advice.includes('潜伏期') || advice.includes('趋势确立') || advice.includes('主升浪')) return 'bg-red-500';
      if (advice.includes('止损') || advice.includes('回避') || advice.includes('离场') || advice.includes('止盈') || advice.includes('减仓') || advice.includes('加速期') || advice.includes('衰退期') || advice.includes('杀跌期')) return 'bg-green-500';
      return 'bg-yellow-400';
    };
    
    const getIntradayItem = (symbol) => {
      const items = intradayItems.value || [];
      return items.find(item => item.symbol === symbol) || null;
    };

    // --- Computed for Shared View ---
    const getAdviceTextColor = (advice) => {
      if (!advice) return 'text-gray-500';
      // 主线特权色（紫色/金色系，这里用紫色表示尊贵）
      if (advice.includes('主线')) return 'text-purple-600 font-bold';
      // 高风险（红色）：派发、赶顶、极值、止损、止盈、减仓等，新增冲高、放量（作为盘中资金行为时也需要红）
      if (advice.includes('止损') || advice.includes('回避') || advice.includes('离场') || advice.includes('止盈') || advice.includes('减仓') || advice.includes('加速期') || advice.includes('衰退期') || advice.includes('杀跌') || advice.includes('派发') || advice.includes('破位') || advice.includes('分歧') || advice.includes('高位滞涨') || advice.includes('涨速放缓') || advice.includes('警惕回落') || advice.includes('向下破位') || advice.includes('冲高') || advice.includes('赶顶') || advice.includes('放量')) return 'text-red-500';
      // 趋势向好（绿色）：建仓、持股、低吸、主升、洗盘等
      if (advice.includes('建仓') || advice.includes('持') || advice.includes('低吸') || advice.includes('潜伏期') || advice.includes('确立') || advice.includes('主升') || advice.includes('洗盘') || advice.includes('承接') || advice.includes('强势向上') || advice.includes('多头') || advice.includes('企稳')) return 'text-green-500';
      // 观望/弱势（黄色）：震荡、没方向等
      return 'text-yellow-500';
    };

    const getMomentumTextColor = (momentum) => {
      if (!momentum) return 'text-gray-500';
      if (momentum.includes('向上')) return 'text-quant-up';
      if (momentum.includes('向下')) return 'text-quant-down';
      if (momentum.includes('反弹')) return 'text-orange-500';
      return 'text-yellow-500';
    };

    const getGridItem = (sym, i) => {
      // i from 1 to 60 (1 is oldest we display, 60 is newest)
      const hist = warmupHistory.value[sym];
      if (!hist || hist.length === 0) return null;
      
      // Calculate offset. If hist has fewer than 60 days, pad left with null
      const maxDays = 60;
      const idx = hist.length - maxDays + (i - 1);
      
      if (idx < 0 || idx >= hist.length) return null;
      return hist[idx];
    };

    const getProcessedGrid = (sym) => {
      const hist = warmupHistory.value[sym];
      if (!hist || hist.length === 0) return Array(60).fill({ isUp: false });
      
      const maxDays = 60;
      const result = [];
      const slice = [];
      
      for (let i = 0; i < maxDays; i++) {
        const idx = hist.length - maxDays + i;
        slice.push(idx >= 0 && idx < hist.length ? hist[idx] : null);
      }
      
      let currentStreak = 0;
      for (let i = 0; i < maxDays; i++) {
        const item = slice[i];
        const isUp = item && item.pct > 0;
        
        if (isUp) {
          currentStreak++;
        } else {
          if (currentStreak > 0) {
            const mid = i - Math.floor(currentStreak / 2) - 1;
            if (result[mid]) result[mid].streakLabel = currentStreak;
          }
          currentStreak = 0;
        }
        
        result.push({
          item,
          isUp,
          isStart: false,
          isEnd: false,
          streakLabel: null
        });
      }
      
      if (currentStreak > 0) {
        const mid = maxDays - Math.floor(currentStreak / 2) - 1;
        if (result[mid]) result[mid].streakLabel = currentStreak;
      }
      
      for (let i = 0; i < maxDays; i++) {
        if (result[i].isUp) {
          result[i].isStart = i === 0 || !result[i-1].isUp;
          result[i].isEnd = i === maxDays - 1 || !result[i+1].isUp;
        }
      }
      
      return result;
    };

    const getGridHeaders = () => {
      const symbols = Object.keys(warmupHistory.value);
      if (symbols.length === 0) return Array(60).fill('');
      const hist = warmupHistory.value[symbols[0]];
      if (!hist || hist.length === 0) return Array(60).fill('');
      
      const maxDays = 60;
      const headers = [];
      for (let i = 0; i < maxDays; i++) {
        const idx = hist.length - maxDays + i;
        if (idx >= 0 && idx < hist.length) {
          headers.push(hist[idx].date);
        } else {
          headers.push('');
        }
      }
      return headers;
    };

    const sortedEtfCycleSymbols = computed(() => {
      const histMap = warmupHistory.value || {};
      const rows = etfSymbols.map((sym, idx) => {
        const hist = histMap[sym] || [];
        const last20 = hist.slice(-20);
        const upDays = last20.reduce((acc, it) => acc + (it && it.pct > 0 ? 1 : 0), 0);
        return { sym, upDays, idx };
      });
      rows.sort((a, b) => (b.upDays - a.upDays) || (a.idx - b.idx));
      return rows.map(r => r.sym);
    });

    // --- Data Fetching ---
    
    const fetchOverview = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/overview`);
        const data = await res.json();
        
        if (data.ok) {
          if (data.market_amount) marketAmount.value = data.market_amount;
          if (data.lifecycle && data.lifecycle.data) lifecycleItems.value = data.lifecycle.data;
          if (data.data && data.data.intraday_snapshot && data.data.intraday_snapshot.items) {
            intradaySnapshotItems.value = data.data.intraday_snapshot.items;
          } else if (data.intraday_snapshot && data.intraday_snapshot.items) {
            intradaySnapshotItems.value = data.intraday_snapshot.items;
          }
          if (data.warmup && data.warmup.history) warmupHistory.value = data.warmup.history;
          lastUpdate.value = new Date().toLocaleTimeString('zh-CN', { hour12: false });
          
          // Draw Correlation Chart once warmup is ready
          nextTick(() => {
            renderCorrelationChart();
          });}
      } catch (err) { console.error('Failed to fetch overview:', err); }
    };

    const fetchBreadth = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/breadth`);
        const json = await res.json();
        if (json.ok && json.data.length > 0) {
          const last = json.data[json.data.length - 1];
          breadthData.value = {
            up: last.up || 0,
            down: last.down || 0,
            flat: last.flat || 0,
            total: (last.up || 0) + (last.down || 0) + (last.flat || 0)
          };
        }
      } catch (err) { console.error('Failed to fetch breadth:', err); }
    };

    const fetchVolumeHistory = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/volume_history`);
        const json = await res.json();
        if (json.ok && json.data.length > 0) {
          volumeHistory.value = json.data;
          intradayVolume.value = json.minute || [];
          intradayYdayVolume.value = json.minuteYday || [];
          nextTick(() => renderVolumeChart());
        }
      } catch (err) { console.error('Failed to fetch volume history:', err); }
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
          if (!journalDay.value) journalDay.value = base;
        }
      } catch (err) {
        console.error('Failed to fetch astro predict:', err);
      } finally {
        astroLoading.value = false;
      }
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
          const k = astroMonthGanzhi.value ? `astro_month_outlook_${astroMonthGanzhi.value}` : 'astro_month_outlook';
          if (!monthOutlook.value) monthOutlook.value = localStorage.getItem(k) || '';
          nextTick(() => scrollAstroPhaseToDay(astroSelectedDay.value || (json.days[0] && json.days[0].date) || ''));
        }
      } catch (err) {
        console.error('Failed to fetch astro calendar month:', err);
      }
    };

    const fetchAstroCalendarRange = async (start, end) => {
      if (!start || !end) return [];
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/astro_calendar?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`);
        const json = await res.json();
        if (json && json.ok && Array.isArray(json.days)) return json.days;
      } catch (err) {
        console.error('Failed to fetch astro calendar range:', err);
      }
      return [];
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
      } catch (err) {
        console.error('Failed to fetch astro review:', err);
      }
    };

    const fetchTradingPrev = async (day) => {
      if (!day) return null;
      if (Object.prototype.hasOwnProperty.call(astroPrevCache, day)) return astroPrevCache[day];
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/trading_prev?day=${encodeURIComponent(day)}`);
        const json = await res.json();
        if (json && json.ok) {
          astroPrevCache[day] = json.prev || null;
          return astroPrevCache[day];
        }
      } catch (err) {
        console.error('Failed to fetch trading prev:', err);
      }
      astroPrevCache[day] = null;
      return null;
    };

    const fetchAstroPredictRaw = async (day) => {
      if (!day) return null;
      if (Object.prototype.hasOwnProperty.call(astroPredCache, day)) return astroPredCache[day];
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/astro_predict?day=${encodeURIComponent(day)}`);
        const json = await res.json();
        if (json && json.ok) {
          astroPredCache[day] = json;
          return json;
        }
      } catch (err) {
        console.error('Failed to fetch astro predict raw:', err);
      }
      astroPredCache[day] = null;
      return null;
    };

    const astroTagFromProb = (v) => {
      const p = Number(v);
      if (!Number.isFinite(p)) return '--';
      if (p >= 0.65) return '强多';
      if (p >= 0.55) return '偏多';
      if (p > 0.45) return '中性';
      if (p > 0.35) return '偏空';
      return '强空';
    };

    const astroTagClassFromTag = (tag) => {
      if (tag === '强多') return 'border-red-200 bg-red-50 text-red-700';
      if (tag === '偏多') return 'border-red-100 bg-red-50/60 text-red-600';
      if (tag === '偏空') return 'border-emerald-100 bg-emerald-50/60 text-emerald-600';
      if (tag === '强空') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
      if (tag === '中性') return 'border-gray-200 bg-gray-50 text-gray-600';
      return 'border-gray-200 bg-white text-gray-400';
    };

    const buildAstroWeekMatrix = async () => {
      const days = astroWeekTradingDays.value.map(x => x.date).filter(Boolean);
      if (days.length === 0) {
        astroWeekMatrix.value = {};
        return;
      }
      astroWeekStatus.value = '加载中...';
      const matrix = {};
      try {
        for (const targetDay of days) {
          const prev = await fetchTradingPrev(targetDay);
          if (!prev) continue;
          const pred = await fetchAstroPredictRaw(prev);
          if (!pred) continue;
          matrix[targetDay] = {};
          const marketProb = pred.market && pred.market.probs ? pred.market.probs['1'] : null;
          matrix[targetDay]['__market__'] = {
            probUp: Number(marketProb),
            tag: astroTagFromProb(marketProb),
            prev
          };
          for (const sym of etfSymbols) {
            const p = pred.predictions && pred.predictions[sym] && pred.predictions[sym].probs ? pred.predictions[sym].probs['1'] : null;
            matrix[targetDay][sym] = {
              probUp: Number(p),
              tag: astroTagFromProb(p),
              prev
            };
          }
        }
        astroWeekMatrix.value = matrix;
        astroWeekStatus.value = '';
      } catch (e) {
        void e;
        astroWeekStatus.value = '加载失败';
      }
    };

    const beijingDateFrom = (d) => {
      const dt = new Date(`${d}T00:00:00+08:00`);
      const y = dt.getFullYear();
      const m = String(dt.getMonth() + 1).padStart(2, '0');
      const day = String(dt.getDate()).padStart(2, '0');
      return `${y}-${m}-${day}`;
    };

    const shiftDate = (d, deltaDays) => {
      const dt = new Date(`${d}T00:00:00+08:00`);
      dt.setDate(dt.getDate() + deltaDays);
      return beijingDateFrom(dt.toISOString().slice(0, 10));
    };

    const weekRangeFor = (d) => {
      const dt = new Date(`${d}T12:00:00+08:00`);
      const weekday = dt.getDay();
      const mondayDelta = weekday === 0 ? -6 : (1 - weekday);
      const start = shiftDate(d, mondayDelta);
      const end = shiftDate(start, 6);
      return { start, end };
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

    const astroWeekRangeText = computed(() => {
      if (!astroWeekDays.value || astroWeekDays.value.length === 0) return '-';
      const start = astroWeekDays.value[0].date;
      const end = astroWeekDays.value[astroWeekDays.value.length - 1].date;
      return `${start} ~ ${end}`;
    });

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

    const astroProbTag = (sym, h) => {
      const p = astroPredict.value && astroPredict.value.predictions && astroPredict.value.predictions[sym];
      const v = p && p.probs ? Number(p.probs[h]) : NaN;
      if (!Number.isFinite(v)) return '--';
      if (v >= 0.65) return '强多';
      if (v >= 0.55) return '偏多';
      if (v > 0.45) return '中性';
      if (v > 0.35) return '偏空';
      return '强空';
    };

    const astroProbTagClass = (sym, h) => {
      const tag = astroProbTag(sym, h);
      if (tag === '强多') return 'border-red-200 bg-red-50 text-red-700';
      if (tag === '偏多') return 'border-red-100 bg-red-50/60 text-red-600';
      if (tag === '偏空') return 'border-emerald-100 bg-emerald-50/60 text-emerald-600';
      if (tag === '强空') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
      if (tag === '中性') return 'border-gray-200 bg-gray-50 text-gray-600';
      return 'border-gray-200 bg-white text-gray-400';
    };

    const astroPhaseSvg = (d) => {
      const idx = Number(d && d.phaseIndex);
      const i = Number.isFinite(idx) ? Math.max(0, Math.min(7, idx)) : 0;
      const cut = [1.0, 0.82, 0.62, 0.38, 0.0, -0.38, -0.62, -0.82][i];
      const g = d && d.waxingWaning === '盈' ? 1 : 0;
      const side = g ? 1 : -1;
      const cx = 14 + side * cut * 10;
      const r = 12;
      const clip = `<clipPath id="mc"><circle cx="14" cy="14" r="${r}"/></clipPath>`;
      const grad = `<radialGradient id="gl" cx="30%" cy="30%"><stop offset="0%" stop-color="#FFFFFF"/><stop offset="55%" stop-color="#F2F4F8"/><stop offset="100%" stop-color="#D9DEE8"/></radialGradient>`;
      const bg = `<circle cx="14" cy="14" r="${r}" fill="#0B1220"/>`;
      const disc = `<circle cx="14" cy="14" r="${r}" fill="url(#gl)"/>`;
      const shade = i === 4 ? '' : `<circle cx="${cx}" cy="14" r="${r}" fill="#0B1220"/>`;
      const ring = `<circle cx="14" cy="14" r="${r}" fill="none" stroke="rgba(17,24,39,0.08)" stroke-width="1"/>`;
      const sparkle = `<circle cx="9" cy="9" r="1.2" fill="rgba(255,255,255,0.35)"/><circle cx="19" cy="7" r="0.9" fill="rgba(255,255,255,0.25)"/>`;
      return `<svg viewBox="0 0 28 28" width="28" height="28" xmlns="http://www.w3.org/2000/svg">${grad}${clip}<g clip-path="url(#mc)">${bg}${disc}${shade}${sparkle}</g>${ring}</svg>`;
    };

    const astroPhaseRiskText = (idx) => {
      const i = Number(idx);
      if (!Number.isFinite(i)) return '';
      if (i === 4) return '满月';
      if (i === 0) return '新月';
      if (i === 2) return '上弦月';
      if (i === 6) return '下弦月';
      return '';
    };

    const astroPhaseRiskClass = (idx) => {
      const t = astroPhaseRiskText(idx);
      if (!t) return 'text-gray-300';
      if (t === '满月') return 'text-gray-700';
      if (t === '新月') return 'text-gray-700';
      return 'text-gray-500';
    };

    const astroSelectedGanzhiDay = computed(() => {
      const d = astroSelectedDay.value;
      if (!d) return '';
      const hit = astroMonthDays.value.find(x => x.date === d) || astroWeekDays.value.find(x => x.date === d);
      return hit ? hit.sixtyCycleDay : (astroPredict.value?.astro?.asOf?.sixtyCycleDay || '');
    });

    const astroSelectedPhase = computed(() => {
      const d = astroSelectedDay.value;
      if (!d) return '';
      const hit = astroMonthDays.value.find(x => x.date === d) || astroWeekDays.value.find(x => x.date === d);
      return hit ? `${astroPhaseRiskText(hit.phaseIndex)} ${hit.waxingWaning}`.trim() : '';
    });

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
      if (tag === '中性') return '观望';
      return '未知';
    };

    const marketDirectionText = (h) => directionTextFromTag(marketTag(h));

    const astroDirectionText = (sym, h) => directionTextFromTag(astroProbTag(sym, h));

    const callChat = async (systemPrompt, userPrompt) => {
      const messages = [];
      if (systemPrompt) messages.push({ role: 'system', content: String(systemPrompt) });
      messages.push({ role: 'user', content: String(userPrompt || '') });
      try {
        const res = await fetch(`${API_BASE}/api/ai/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ messages })
        });
        const json = await res.json();
        if (json && json.ok && json.reply) return String(json.reply || '').trim();
      } catch (e) { void e; }
      return '';
    };

    const financeFallback = () => {
      const b = baziProfile.value?.bazi?.text ? `八字：${baziProfile.value.bazi.text}` : '';
      const s = [
        b,
        '资金纪律：分层仓位、单笔止损、连续亏损停手。',
        '行为禁忌：追高、频繁还手、无计划加仓。',
        '执行：先定计划（入场/止损/止盈）再下单。'
      ].filter(Boolean);
      return s.join('\n');
    };

    const dailyRiskFallback = () => {
      const day = astroSelectedDay.value || '';
      const phase = (astroSelectedPhase.value || '').split(' ')[0] || '';
      const bias = marketDirectionText('1');
      const head = [day, phase].filter(Boolean).join(' ');
      const lines = [
        head ? `${head}：${bias}` : `今日：${bias}`,
        phase === '满月' ? '满月窗口：优先防守，避免追高与满仓。' : '',
        phase === '新月' ? '新月窗口：更适合试错与观察，先小仓位。' : '',
        '若出现系统性风险信号（放量下跌/题材退潮），优先降仓与减少交易频次。'
      ].filter(Boolean);
      return lines.join('\n');
    };

    const ensureFinanceAuto = async (force = false) => {
      const key = baziProfile.value?.bazi?.text ? `astro_finance_auto_${baziProfile.value.bazi.text}` : '';
      if (!force && key) {
        const cached = localStorage.getItem(key) || '';
        if (cached) {
          financeAuto.value = cached;
          return;
        }
      }
      financeLoading.value = true;
      const sys = '你是A股交易资金管理教练，输出要简洁可执行，不要出现百分比概率，不要使用项目符号符号，只用换行分段。';
      const user = `请根据以下信息生成“八字财务分析”（3-5行）：\n性别：${userGender.value}\n出生：${userBirth.value}\n出生地：${userPlaceText.value}\n八字：${baziProfile.value?.bazi?.text || ''}`;
      const txt = await callChat(sys, user);
      financeAuto.value = txt || financeFallback();
      if (key) localStorage.setItem(key, financeAuto.value);
      financeLoading.value = false;
    };

    const ensureDailyRiskAuto = async (force = false) => {
      const day = astroSelectedDay.value || '';
      const b = baziProfile.value?.bazi?.text || '';
      const key = (day && b) ? `astro_daily_risk_auto_${day}_${b}` : '';
      if (!force && key) {
        const cached = localStorage.getItem(key) || '';
        if (cached) {
          dailyRiskAuto.value = cached;
          return;
        }
      }
      dailyRiskLoading.value = true;
      const sys = '你是A股交易风控助手，输出要简洁可执行，不要出现百分比概率，不要使用项目符号符号，只用换行分段。';
      const user = `请结合“当日选中日期”的信息，生成“当日操作风险提示”（3-5行）：\n日期：${day}\n月相：${astroSelectedPhase.value}\n次日大盘倾向：${marketDirectionText('1')}\n性别：${userGender.value}\n出生：${userBirth.value}\n出生地：${userPlaceText.value}\n八字：${b}`;
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

    const astroWeekCell = (day, sym) => {
      if (!day || !sym) return null;
      const row = astroWeekMatrix.value && astroWeekMatrix.value[day];
      return row ? row[sym] : null;
    };

    const astroWeekCellTag = (day, sym) => {
      const c = astroWeekCell(day, sym);
      return c ? c.tag : '--';
    };

    const astroWeekCellClass = (day, sym) => {
      const c = astroWeekCell(day, sym);
      return astroTagClassFromTag(c ? c.tag : '--');
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
      astroHistorySymbols.value = Array.from(cur);
      localStorage.setItem('astro_history_symbols', astroHistorySymbols.value.join(','));
      nextTick(() => renderAstroHistoryChart());
    };

    const renderAstroHistoryChart = () => {
      const el = document.getElementById('chart-astro-history');
      if (!el) return;
      if (!chartInstances['astroHistory']) chartInstances['astroHistory'] = echarts.init(el);
      const chart = chartInstances['astroHistory'];
      const symbols = (astroHistorySymbols.value && astroHistorySymbols.value.length) ? astroHistorySymbols.value : ['sh512480', 'sh516510', 'sh515880', 'sh563530'];
      const day = astroSelectedDay.value;
      if (!day || !warmupHistory.value || Object.keys(warmupHistory.value).length === 0) return;

      const series = [];
      let xAxis = [];

      symbols.forEach((sym) => {
        const hist = warmupHistory.value[sym] || [];
        if (!hist || hist.length === 0) return;
        let endIdx = hist.findIndex(x => x && x.date === day);
        if (endIdx < 0) endIdx = hist.length - 1;
        const win = Number(astroHistoryWindow.value) || 15;
        const startIdx = Math.max(0, endIdx - win + 1);
        const slice = hist.slice(startIdx, endIdx + 1);
        if (slice.length < 2) return;
        const base = Number(slice[0].close || 0);
        if (!Number.isFinite(base) || base <= 0) return;
        if (xAxis.length === 0) xAxis = slice.map(x => x.date);
        const data = slice.map(x => {
          const c = Number(x.close || 0);
          if (!Number.isFinite(c) || c <= 0) return null;
          return ((c / base) - 1) * 100;
        });
        series.push({
          name: (symbolNames[sym] || sym).replace('ETF', ''),
          type: 'line',
          data,
          smooth: true,
          symbol: 'none',
          connectNulls: true,
          lineStyle: { width: 2 }
        });
      });

      const option = {
        tooltip: { trigger: 'axis', valueFormatter: (val) => (val == null ? '-' : `${val.toFixed(2)}%`) },
        legend: { top: 0, left: 'center', type: 'scroll', icon: 'circle', itemWidth: 8, itemHeight: 8 },
        grid: { left: 40, right: 20, top: 36, bottom: 22 },
        xAxis: { type: 'category', data: xAxis, axisLabel: { color: '#64748B' }, axisLine: { lineStyle: { color: '#E2E8F0' } } },
        yAxis: { type: 'value', axisLabel: { formatter: '{value}%', color: '#64748B' }, splitLine: { lineStyle: { type: 'dashed', color: '#E2E8F0' } } },
        series
      };
      chart.setOption(option, true);
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
          journalStatus.value = '已保存，更新预测中...';
          await runAstroPredict(journalDay.value);
          journalStatus.value = '完成';
        } else {
          journalStatus.value = json && json.error ? json.error : '提交失败';
        }
      } catch (err) {
        console.error('Failed to submit journal:', err);
        journalStatus.value = '提交失败';
      } finally {
        journalSubmitting.value = false;
      }
    };

    // --- Charts ---

    const renderVolumeChart = () => {
      const el = document.getElementById('chart-volume');
      if (!el || volumeHistory.value.length === 0) return;
      if (!chartInstances['volume']) chartInstances['volume'] = echarts.init(el);
      
      const chart = chartInstances['volume'];
      
      // Calculate yesterday's average volume per minute (the dashed reference line)
      let ydayTotalAmount = 0;
      const todayStr = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Shanghai' })).toISOString().split('T')[0];
      
      // Find the most recent day before today
      let lastDaily = null;
      for (let i = volumeHistory.value.length - 1; i >= 0; i--) {
        const row = volumeHistory.value[i];
        if (row && row.date < todayStr) {
          lastDaily = row;
          break;
        }
      }
      
      if (lastDaily) {
        ydayTotalAmount = lastDaily.market_amount / 100000000; // in hundred millions (亿)
      }
      const avgPerMinute = ydayTotalAmount / 240;

      // Construct standard 240-minute trading axis
      const xAxisData = [];
      let d = new Date();
      d.setHours(9, 30, 0, 0);
      for(let i=0; i<120; i++) { xAxisData.push(d.toTimeString().substring(0,5)); d.setMinutes(d.getMinutes()+1); }
      d.setHours(13, 0, 0, 0);
      for(let i=0; i<120; i++) { xAxisData.push(d.toTimeString().substring(0,5)); d.setMinutes(d.getMinutes()+1); }

      // Construct today's real minute-by-minute volume curve
      const todayData = new Array(240).fill(null);
      let currentTradedMinutes = 0;
      let finalCumulative = 0;
      
      // Extract yesterday's cumulative volume mapping with forward-fill to handle data gaps
      const ydayCumulativeMap = new Map();
      let lastYdayVol = 0;
      let ydayIdx = 0;
      xAxisData.forEach(timeStr => {
        while (ydayIdx < intradayYdayVolume.value.length && intradayYdayVolume.value[ydayIdx].asOf <= timeStr) {
          lastYdayVol = intradayYdayVolume.value[ydayIdx].market_amount / 100000000;
          ydayIdx++;
        }
        if (lastYdayVol > 0) {
          ydayCumulativeMap.set(timeStr, lastYdayVol);
        }
      });

      if (intradayVolume.value.length > 0) {
        let prevCumulative = 0;
        let prevAxisIdx = -1;

        intradayVolume.value.forEach((pt, i) => {
          const timeStr = pt.asOf;
          const axisIdx = xAxisData.indexOf(timeStr);
          if (axisIdx === -1) return; // ignore invalid times
          if (prevAxisIdx !== -1 && axisIdx < prevAxisIdx) return;
          
          currentTradedMinutes = axisIdx + 1;
          const currentCumulative = pt.market_amount / 100000000;
          finalCumulative = currentCumulative;
          
          const spanMinutes = i === 0 ? (axisIdx + 1) : Math.max(1, axisIdx - prevAxisIdx);
          let segmentVolume = i === 0 ? currentCumulative : (currentCumulative - prevCumulative);
          if (segmentVolume < 0) segmentVolume = 0;
          const perMinuteVolume = segmentVolume / spanMinutes;

          const startFill = i === 0 ? 0 : (prevAxisIdx + 1);
          for (let m = startFill; m <= axisIdx; m++) {
            todayData[m] = perMinuteVolume;
          }

          prevCumulative = currentCumulative;
          prevAxisIdx = axisIdx;
        });
        
        const lastAsOf = intradayVolume.value[intradayVolume.value.length - 1].asOf;
        const ydaySameTimeCumulative = ydayCumulativeMap.get(lastAsOf) ?? (avgPerMinute * currentTradedMinutes);

        let forecastTotal = finalCumulative;
        if (currentTradedMinutes > 0 && currentTradedMinutes < 240) {
          const remainingMinutes = 240 - currentTradedMinutes;
          let lastMinuteVol = 0;
          
          if (intradayVolume.value.length > 1) {
            const currentVol = intradayVolume.value[intradayVolume.value.length - 1].market_amount / 100000000;
            const prevVol = intradayVolume.value[intradayVolume.value.length - 2].market_amount / 100000000;
            lastMinuteVol = currentVol - prevVol;
          } else if (intradayVolume.value.length === 1) {
            lastMinuteVol = intradayVolume.value[0].market_amount / 100000000;
          }
          
          if (!Number.isFinite(lastMinuteVol) || lastMinuteVol < 0) lastMinuteVol = 0;
          forecastTotal = finalCumulative + (lastMinuteVol * remainingMinutes);
        }

        volumeStats.value = {
          current: finalCumulative,
          ydayTotal: ydayTotalAmount,
          ydaySameTime: ydaySameTimeCumulative,
          forecast: forecastTotal,
          deltaPct: ydayTotalAmount > 0 ? ((forecastTotal - ydayTotalAmount) / ydayTotalAmount) * 100 : 0
        };
      }
      
      // Construct the baseline array for yesterday's average
      const ydayAvgData = new Array(240).fill(avgPerMinute);

      const option = {
        tooltip: { 
          trigger: 'axis', 
          valueFormatter: (val) => val != null ? val.toFixed(2) + '亿' : '-'
        },
        grid: { left: 40, right: 10, top: 10, bottom: 20 },
        xAxis: { 
          type: 'category', 
          data: xAxisData, 
          axisLabel: {
            color: '#9CA3AF',
            interval: (index, value) => {
              return ['09:30', '10:30', '11:30', '13:00', '14:00', '15:00'].includes(value);
            }
          },
          axisTick: { alignWithLabel: true }
        },
        yAxis: { 
          type: 'value', 
          axisLabel: { formatter: '{value}', color: '#9CA3AF' },
          splitLine: { lineStyle: { type: 'dashed', color: '#F3F4F6' } }
        },
        series: [
          {
            name: '今日量能(分钟)',
            data: todayData,
            type: 'line',
            smooth: true,
            symbol: 'none',
            connectNulls: true,
            lineStyle: { color: '#3B82F6', width: 2 },
            areaStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: 'rgba(59, 130, 246, 0.3)' },
                { offset: 1, color: 'rgba(59, 130, 246, 0.05)' }
              ])
            }
          },
          {
            name: '昨日均量',
            data: ydayAvgData,
            type: 'line',
            smooth: false,
            symbol: 'none',
            lineStyle: { color: '#9CA3AF', width: 1, type: 'dashed' }
          }
        ]
      };
      chart.setOption(option);
    };

    const renderCorrelationChart = () => {
      const el = document.getElementById('chart-correlation');
      if (!el) return;
      if (!chartInstances['correlation']) chartInstances['correlation'] = echarts.init(el);
      
      const chart = chartInstances['correlation'];
      const symbolsToDraw = etfSymbols;
      const labelToSym = {};
      symbolsToDraw.forEach((sym) => {
        labelToSym[symbolNames[sym] || sym] = sym;
      });
      const seriesData = [];
      let xAxisData = [];

      if (corrDays.value === 1) {
        const times = [];
        let d = new Date();
        d.setHours(9, 30, 0, 0);
        for(let i=0; i<120; i++) { times.push(d.toTimeString().substring(0,5)); d.setMinutes(d.getMinutes()+1); }
        d.setHours(13, 0, 0, 0);
        for(let i=0; i<120; i++) { times.push(d.toTimeString().substring(0,5)); d.setMinutes(d.getMinutes()+1); }
        xAxisData = times;

        symbolsToDraw.forEach((sym) => {
          const mData = minuteDataCache.value[sym];
          if (mData && mData.data) {
            const pcts = [];
            mData.data.forEach((pt, idx) => {
              if (idx < 240) {
                const ptPct = pt.pct !== undefined ? pt.pct : (mData.pre_close ? ((pt.price - mData.pre_close) / mData.pre_close) * 100 : 0);
                pcts.push(ptPct);
              }
            });
            seriesData.push({
              name: symbolNames[sym] || sym,
              type: 'line',
              data: pcts,
              smooth: true,
              symbol: 'none',
              lineStyle: { width: 2 }
            });
          }
        });
      } else {
        if (Object.keys(warmupHistory.value).length === 0) return;
        symbolsToDraw.forEach((sym) => {
          if (warmupHistory.value[sym]) {
            let hist = warmupHistory.value[sym];
            if (hist.length > corrDays.value) {
              hist = hist.slice(-corrDays.value);
            }
            if (xAxisData.length === 0) xAxisData = hist.map(h => h.date);
            
            const basePrice = hist[0].close;
            const pcts = hist.map(h => ((h.close - basePrice) / basePrice) * 100);
            
            seriesData.push({
              name: symbolNames[sym] || sym,
              type: 'line',
              data: pcts,
              smooth: true,
              symbol: 'none',
              lineStyle: { width: 2 }
            });
          }
        });
      }

      const option = {
        tooltip: { trigger: 'axis', valueFormatter: (val) => val.toFixed(2) + '%' },
        legend: { 
          top: 0, 
          left: 'center', 
          type: 'scroll', 
          icon: 'circle', 
          itemWidth: 8, 
          itemHeight: 8,
          formatter: (name) => {
            const sym = labelToSym[name];
            const pct = sym ? currentPrices.value[sym]?.pct : null;
            if (pct == null || isNaN(pct)) return name;
            const num = Number(pct).toFixed(2);
            const sign = Number(pct) > 0 ? '+' : '';
            return `${name} ${sign}${num}%`;
          }
        },
        grid: { left: 40, right: 20, top: 40, bottom: 20 },
        xAxis: { type: 'category', data: xAxisData, axisLine: { lineStyle: { color: '#E2E8F0' } }, axisLabel: { color: '#64748B' } },
        yAxis: { type: 'value', axisLabel: { formatter: '{value}%', color: '#64748B' }, splitLine: { lineStyle: { type: 'dashed', color: '#E2E8F0' } } },
        series: seriesData
      };
      
      chart.setOption(option, true);
    };

    const renderMinuteChart = (sym, dataPoints, preClose) => {
      const el = document.getElementById(`chart-minute-${sym}`);
      if (!el) return;
      
      let chart = echarts.getInstanceByDom(el);
      if (!chart) {
        chart = echarts.init(el);
        chartInstances[sym] = chart;
      }
      
      const times = [];
      let d = new Date();
      d.setHours(9, 30, 0, 0);
      for(let i=0; i<120; i++) { times.push(d.toTimeString().substring(0,5)); d.setMinutes(d.getMinutes()+1); }
      d.setHours(13, 0, 0, 0);
      for(let i=0; i<120; i++) { times.push(d.toTimeString().substring(0,5)); d.setMinutes(d.getMinutes()+1); }
      
      const prices = [];
      const pcts = [];
      let latestPrice = preClose;
      let latestPct = 0;
      
      if (dataPoints && dataPoints.length > 0) {
        // 创建一个映射表以便快速按时间填充数据
        const pointMap = {};
        dataPoints.forEach(pt => {
          if (pt.price > 0 && pt.asOf >= "09:30") { // 严格过滤 0.0 数据和盘前数据
            pointMap[pt.asOf] = pt;
          }
        });

        // 严格按照 X 轴的时间槽位（times）来对齐填入数据
        times.forEach((t) => {
          const pt = pointMap[t];
          if (pt) {
            prices.push(pt.price);
            const ptPct = pt.pct !== undefined ? pt.pct : (preClose ? ((pt.price - preClose) / preClose) * 100 : 0);
            pcts.push(ptPct);
            latestPct = ptPct;
            latestPrice = pt.price;
          } else if (prices.length > 0 && t <= dataPoints[dataPoints.length - 1].asOf) {
             // 交易时间内的缺失分钟，使用前一分钟的价格补齐以保持曲线连续性
             const prevPrice = prices[prices.length - 1];
             const prevPct = pcts[pcts.length - 1];
             prices.push(prevPrice);
             pcts.push(prevPct);
          } else {
             prices.push(null);
             pcts.push(null);
          }
        });
      }
      
      currentPrices.value[sym] = { price: latestPrice, pct: latestPct };
      
      let maxAbsPct = 0.5;
      pcts.forEach(p => { if (Math.abs(p) > maxAbsPct) maxAbsPct = Math.abs(p); });
      maxAbsPct = Math.ceil(maxAbsPct * 10) / 10;

      const option = {
        animation: false,
        grid: { left: 0, right: 0, top: 10, bottom: 0 },
        xAxis: { type: 'category', data: times, show: false },
        yAxis: [{
          type: 'value',
          min: 'dataMin',
          max: 'dataMax',
          show: false
        }],
        series: [{
          data: prices,
          type: 'line',
          symbol: 'none',
          lineStyle: { width: 1.5, color: latestPct >= 0 ? '#EF4444' : '#10B981' },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: latestPct >= 0 ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.15)' },
              { offset: 1, color: latestPct >= 0 ? 'rgba(239, 68, 68, 0)' : 'rgba(16, 185, 129, 0)' }
            ])
          }
        }]
      };
      
      chart.setOption(option);
      chartsLoaded.value[sym] = true;
    };

    const fetchMinuteData = async () => {
      const allSymbols = [...new Set([...indexSymbols, ...etfSymbols])];
      const promises = allSymbols.map(async (sym) => {
        try {
          const res = await fetch(`${API_BASE}/api/m1/data/minute?symbol=${sym}`);
          const data = await res.json();
          if (data.ok) {
            const pre_close = data.pre_close;
            const dataPoints = data.data;
            
            let latestPrice = 0;
            let latestPct = 0;
            
            if (dataPoints && dataPoints.length > 0) {
              const lastPt = dataPoints[dataPoints.length - 1];
              latestPrice = lastPt.price;
              latestPct = lastPt.pct !== undefined ? lastPt.pct : (pre_close ? ((lastPt.price - pre_close) / pre_close) * 100 : 0);
            }
            
            minuteDataCache.value[sym] = { pre_close, data: dataPoints || [] };
            currentPrices.value[sym] = { price: latestPrice, pct: latestPct };
            nextTick(() => {
              renderMinuteChart(sym, dataPoints, pre_close);
              if (sym === 'sh512480' || sym === 'sh516510' || sym === 'sh515880' || sym === 'sh563530') {
                if (typeof corrDays !== 'undefined') {
                  if (corrDays.value === 1) renderCorrelationChart();
                } else {
                  renderCorrelationChart();
                }
              }
            });
          }
        } catch (err) { console.error(`Failed to fetch minute data for ${sym}:`, err); }
      });
      await Promise.all(promises);
      if (chartInstances['correlation']) {
        nextTick(() => renderCorrelationChart());
      }
    };

    // --- Lifecycle Hooks ---
    onMounted(() => {
      loadChat();
      loadPlaceGroups();
      refreshOverviewAi();
      refreshEtfAi();
      fetchOverview();
      fetchMinuteData();
      fetchBreadth();
      fetchVolumeHistory();
      fetchAstroPredict().then(() => {
        const d = astroSelectedDay.value || (astroPredict.value ? astroPredict.value.asOfDay : '');
        if (d) selectAstroDay(d);
      });

      window.addEventListener('resize', () => {
        Object.values(chartInstances).forEach(chart => chart.resize());
      });
      
      setInterval(() => {
        fetchOverview();
        fetchMinuteData();
        fetchBreadth();
      }, 60000);
    });

    watch(activeTab, (newVal) => {
      nextTick(() => {
        if (newVal === 'market') {
          if (chartInstances['correlation']) chartInstances['correlation'].resize();
          etfSymbols.forEach((sym) => {
            if (chartInstances[sym]) chartInstances[sym].resize();
          });
        } else if (newVal === 'astro') {
          if (chartInstances['astroHistory']) chartInstances['astroHistory'].resize();
        } else if (newVal === 'overview') {
          if (chartInstances['volume']) chartInstances['volume'].resize();
          indexSymbols.forEach((sym) => {
            if (chartInstances[sym]) chartInstances[sym].resize();
          });
        }
      });
    });

    watch(activeLifecycleTab, (newVal) => {
      if (newVal === 'after') {
        nextTick(() => {
          etfSymbols.forEach(sym => {
            const mData = minuteDataCache.value[sym];
            if (mData) renderMinuteChart(sym, mData.data, mData.pre_close);
          });
        });
      }
    });

    return {
      overviewAiText,
      overviewAiUpdatedAt,
      overviewAiLoading,
      overviewAiSections,
      overviewAiPositionPct,
      etfAiText,
      etfAiUpdatedAt,
      etfAiLoading,
      etfAiSections,
      refreshOverviewAi,
      refreshEtfAi,
      activeTab,
      activeLifecycleTab,
      lastUpdate,
      marketAmount,
      breadthData,
      indexSymbols,
      etfSymbols,
      symbolNames,
      etfCategoryMap,
      sortedEtfCycleSymbols,
      etfLifecycleItems,
      etfLifecycleHold,
      etfLifecycleWait,
      etfLifecycleSell,
      etfLifecycleOther,
      intradaySnapshotItems,
      intradayItems,
      intradayHold,
      intradayWait,
      intradaySell,
      currentPrices,
      chartsLoaded,
      warmupHistory,
      volumeHistory,
      volumeStats,
      corrDays,
      renderCorrelationChart,
      formatAmount,
      getPriceColor,
      getAdviceBgClass,
      getIntradayItem,
      getAdviceTextColor,
      getMomentumTextColor,
      getGridItem,
      getProcessedGrid,
      getGridHeaders,
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
      astroSelectedPhase,
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
      runAstroPredict,
      astroProbTag,
      astroProbTagClass,
      astroPhaseSvg,
      astroPhaseRiskText,
      astroPhaseRiskClass,
      selectAstroDay,
      astroReviewItems,
      astroReviewText,
      marketDirectionText,
      astroDirectionText,
      astroWeekCellTag,
      astroWeekCellClass,
      astroWeekCellTextClass,
      astroHistoryWindow,
      astroHistorySymbols,
      toggleAstroHistorySymbol,
      renderAstroHistoryChart,
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
      fmtPct,
      fmtHeatDelta,
      getItemStats,
      simConfig,
      simState,
      simMetrics,
      simPositionsList,
      simTradesLatest,
      tradeSuggestions,
      tradeTableRows,
      suggestionOverrides,
      selectedSuggestions,
      tradeSelectedCount,
      tradeAllSelected,
      toggleTradeSelectAll,
      executeSelectedSuggestions,
      executeSuggestion,
      resetSimAccount,
      onHoldingsScreenshot,
      holdingsScreenshot,
      holdingsScreenshotUpdatedAt,
      fmtCny,
      simRiskAlerts,
      simInitialMissing,
      simCategoryExposureList,
      simMajorExposure,
      tradeConfirmOpen,
      tradeConfirmItems,
      tradeConfirmError,
      closeTradeConfirm,
      confirmTradeConfirm,
      tradeBottomTab
    };
  }
});

app.mount('#app');
