const { createApp, ref, onMounted, computed, nextTick, watch, reactive } = Vue;

const API_BASE = window.location.origin;

createApp({
  setup() {
    const activeLifecycleTab = ref('after');
    const lastUpdate = ref('---');
    const lifecycleItems = ref([]);
    const intradaySnapshotItems = ref([]);
    const warmupHistory = ref({});
    const corrDays = ref(parseInt(localStorage.getItem('corrDays')) || 1);
    watch(corrDays, (v) => localStorage.setItem('corrDays', v));

    const etfAiText = ref('加载中...');
    const etfAiUpdatedAt = ref('');
    const etfAiLoading = ref(false);

    const etfSymbols = ref(['sh512400', 'sh512480', 'sh515120', 'sh515880', 'sh516010', 'sh516160', 'sh516510', 'sh562500', 'sh563530']);
    const symbolNames = {
      'sh512400': '有色金属ETF', 'sh512480': '半导体ETF', 'sh515120': '创新药ETF',
      'sh515880': '通信ETF', 'sh516010': '游戏ETF', 'sh516160': '新能源ETF',
      'sh516510': '云计算ETF', 'sh562500': '机器人ETF', 'sh563530': '商业航天ETF'
    };
    const etfCategoryMap = {
      'sh512480': '科技', 'sh515880': '科技', 'sh516510': '科技', 'sh516010': '科技',
      'sh563530': '科技', 'sh562500': '科技', 'sh515120': '科技',
      'sh512400': '资源', 'sh516160': '资源'
    };
    const etfSubCategoryMap = {
      'sh512480': '硬件', 'sh515880': '硬件', 'sh516510': '软件', 'sh516010': '软件',
      'sh563530': '新质生产力', 'sh562500': '新质生产力', 'sh515120': '生物科技',
      'sh512400': '大宗周期', 'sh516160': '泛能源'
    };

    const currentPrices = ref({});
    const minuteDataCache = ref({});
    const chartInstances = {};
    const hiddenSymbols = reactive({});
    const backfillOpen = ref(false);
    const backfillStatus = reactive({});
    const backfillToast = reactive({ show: false, name: '', code: '', status: 'requesting' });

    const visibleEtfSymbols = computed(() => etfSymbols.value.filter(s => !hiddenSymbols[s]));

    const parseAiSections = (txt) => {
      if (!txt) return [];
      if (txt === '加载中...' || txt === '等待接入...' || txt === '暂无今日 AI 解读数据' || txt === 'AI 板块解析加载中...') return [{ title: '', content: txt }];
      const lines = txt.split('\n');
      const sections = [];
      let currentTitle = '';
      let currentContent = [];
      const knownTitles = ['走势判断', '情绪定性', '阵营轮动', '资金风格', '操作建议', '盘面核心特征', '异动与风向', '交易员应对策略', '主线追踪', '资金偏好', '主线与异动', '阵营跷跷板', '跷跷板效应', '异动解读', '轮动建议', '重点异动', '轮动分析', '行情研判', '赚钱效应', '跷跷板分析', '共振分析', '轮动规律', '主线趋势'];
      for (const line of lines) {
        if (line.includes('===') || !line.trim()) continue;
        const oldTitleMatch = line.match(/^(?:\*\*)?【([^】]+)】(?:\*\*)?\s*(.*)/);
        if (oldTitleMatch) {
          if (currentTitle) sections.push({ title: currentTitle, content: currentContent.join('\n').trim() });
          currentTitle = oldTitleMatch[1].trim();
          currentContent = [];
          const rest = oldTitleMatch[2].trim();
          if (rest) currentContent.push(rest);
          continue;
        }
        const titleMatch = line.match(/^(?:\*\*)?\s*([^：:]+?)\s*(?:\*\*)?[：:](.*)/);
        if (titleMatch && knownTitles.includes(titleMatch[1].trim())) {
          if (currentTitle) sections.push({ title: currentTitle, content: currentContent.join('\n').trim().replace(/\*\*([^*]+)\*\*/g, '<strong class="text-q-primary">$1</strong>') });
          currentTitle = titleMatch[1].trim();
          currentContent = [];
          const rest = titleMatch[2].trim();
          if (rest) currentContent.push(rest);
        } else {
          if (currentTitle) currentContent.push(line.trim());
          else currentContent.push(line.trim());
        }
      }
      if (currentTitle) sections.push({ title: currentTitle, content: currentContent.join('\n').trim() });
      else if (currentContent.length) sections.push({ title: '', content: currentContent.join('\n').trim() });
      return sections;
    };

    const etfAiSections = computed(() => parseAiSections(etfAiText.value));

    const getPriceColor = (val) => {
      if (val == null || isNaN(val)) return 'text-q-flat';
      if (val > 0) return 'text-q-up';
      if (val < 0) return 'text-q-down';
      return 'text-q-flat';
    };

    const getAdviceTextColor = (advice) => {
      if (!advice) return 'text-gray-500';
      if (advice.includes('主线')) return 'text-purple-600 font-bold';
      if (advice.includes('止损') || advice.includes('回避') || advice.includes('离场') || advice.includes('止盈') || advice.includes('减仓') || advice.includes('加速期') || advice.includes('衰退期') || advice.includes('杀跌') || advice.includes('派发') || advice.includes('破位') || advice.includes('分歧') || advice.includes('高位滞涨') || advice.includes('涨速放缓') || advice.includes('警惕回落') || advice.includes('向下破位') || advice.includes('冲高') || advice.includes('赶顶') || advice.includes('放量')) return 'text-red-500';
      if (advice.includes('建仓') || advice.includes('持') || advice.includes('低吸') || advice.includes('潜伏期') || advice.includes('确立') || advice.includes('主升') || advice.includes('洗盘') || advice.includes('承接') || advice.includes('强势向上') || advice.includes('多头') || advice.includes('企稳')) return 'text-green-500';
      return 'text-yellow-500';
    };

    const intradayItems = computed(() => {
      const items = intradaySnapshotItems.value || [];
      return items.filter(item => item.symbol && visibleEtfSymbols.value.includes(item.symbol));
    });

    const getIntradayItem = (symbol) => {
      const items = intradayItems.value || [];
      return items.find(item => item.symbol === symbol) || null;
    };

    const etfLifecycleItems = computed(() => {
      const items = lifecycleItems.value || [];
      return items.filter(item => item.symbol && visibleEtfSymbols.value.includes(item.symbol));
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
        if (i < 19) { series.push(null); continue; }
        let sum = 0; let cnt = 0;
        for (let j = i - 19; j <= i; j++) { const c = closes[j]; if (c == null) continue; sum += c; cnt++; }
        if (cnt < 15) { series.push(null); continue; }
        const ma20 = sum / cnt;
        if (!ma20) { series.push(null); continue; }
        const c0 = closes[i];
        if (c0 == null) { series.push(null); continue; }
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
      return items.filter(item => { const m = item?.动能 || ''; if (!m.includes('强势向上')) return false; return isNearExtreme(item); });
    });

    const etfLifecycleHold = computed(() => {
      const items = etfLifecycleItems.value || [];
      const sellIds = new Set(etfLifecycleSell.value.map(i => i.symbol));
      return items.filter(item => { if (sellIds.has(item.symbol)) return false; return isUpTrend(item); });
    });

    const etfLifecycleWait = computed(() => {
      const items = etfLifecycleItems.value || [];
      const sellIds = new Set(etfLifecycleSell.value.map(i => i.symbol));
      const holdIds = new Set(etfLifecycleHold.value.map(i => i.symbol));
      return items.filter(item => { if (sellIds.has(item.symbol) || holdIds.has(item.symbol)) return false; return true; });
    });

    const sortedEtfCycleSymbols = computed(() => {
      const syms = [...visibleEtfSymbols.value];
      syms.sort((a, b) => {
        const ha = warmupHistory.value[a];
        const hb = warmupHistory.value[b];
        const countUp = (hist) => {
          if (!hist || hist.length === 0) return 0;
          const recent = hist.slice(-20);
          return recent.filter(x => x.pct > 0).length;
        };
        return countUp(hb) - countUp(ha);
      });
      return syms;
    });

    const getProcessedGrid = (sym) => {
      const hist = warmupHistory.value[sym];
      if (!hist || hist.length === 0) return Array(60).fill({ isUp: false });
      const maxDays = 60;
      const result = [];
      const slice = [];
      for (let i = 0; i < maxDays; i++) { const idx = hist.length - maxDays + i; slice.push(idx >= 0 && idx < hist.length ? hist[idx] : null); }
      let currentStreak = 0;
      for (let i = 0; i < maxDays; i++) {
        const item = slice[i];
        const isUp = item && item.pct > 0;
        if (isUp) { currentStreak++; } else {
          if (currentStreak > 0) { const mid = i - Math.floor(currentStreak / 2) - 1; if (result[mid]) result[mid].streakLabel = currentStreak; }
          currentStreak = 0;
        }
        result.push({ item, isUp, isStart: false, isEnd: false, streakLabel: null });
      }
      if (currentStreak > 0) { const mid = maxDays - Math.floor(currentStreak / 2) - 1; if (result[mid]) result[mid].streakLabel = currentStreak; }
      for (let i = 0; i < maxDays; i++) { if (result[i].isUp) { result[i].isStart = i === 0 || !result[i-1].isUp; result[i].isEnd = i === maxDays - 1 || !result[i+1].isUp; } }
      return result;
    };

    const getGridHeaders = () => {
      const symbols = Object.keys(warmupHistory.value);
      if (symbols.length === 0) return Array(60).fill('');
      const hist = warmupHistory.value[symbols[0]];
      if (!hist || hist.length === 0) return Array(60).fill('');
      const maxDays = 60;
      const headers = [];
      for (let i = 0; i < maxDays; i++) { const idx = hist.length - maxDays + i; headers.push(idx >= 0 && idx < hist.length ? (hist[idx].date || '') : ''); }
      return headers;
    };

    const renderCorrelationChart = () => {
      const el = document.getElementById('chart-correlation');
      if (!el) return;
      if (!chartInstances['correlation']) chartInstances['correlation'] = echarts.init(el);
      const chart = chartInstances['correlation'];
      const symbolsToDraw = visibleEtfSymbols.value;
      const labelToSym = {};
      symbolsToDraw.forEach(sym => { labelToSym[symbolNames[sym] || sym] = sym; });
      const seriesData = [];
      let xAxisData = [];
      if (corrDays.value === 1) {
        const times = [];
        let d = new Date(); d.setHours(9, 30, 0, 0);
        for (let i = 0; i < 120; i++) { times.push(d.toTimeString().substring(0, 5)); d.setMinutes(d.getMinutes() + 1); }
        d.setHours(13, 0, 0, 0);
        for (let i = 0; i < 120; i++) { times.push(d.toTimeString().substring(0, 5)); d.setMinutes(d.getMinutes() + 1); }
        xAxisData = times;
        symbolsToDraw.forEach(sym => {
          const mData = minuteDataCache.value[sym];
          if (mData && mData.data) {
            const pcts = [];
            mData.data.forEach((pt, idx) => {
              if (idx < 240) { const ptPct = pt.pct !== undefined ? pt.pct : (mData.pre_close ? ((pt.price - mData.pre_close) / mData.pre_close) * 100 : 0); pcts.push(ptPct); }
            });
            seriesData.push({ name: symbolNames[sym] || sym, type: 'line', data: pcts, smooth: true, symbol: 'none', lineStyle: { width: 2 } });
          }
        });
      } else {
        if (Object.keys(warmupHistory.value).length === 0) return;
        symbolsToDraw.forEach(sym => {
          if (warmupHistory.value[sym]) {
            let hist = warmupHistory.value[sym];
            if (hist.length > corrDays.value) hist = hist.slice(-corrDays.value);
            if (xAxisData.length === 0) xAxisData = hist.map(h => h.date);
            const basePrice = hist[0].close;
            const pcts = hist.map(h => ((h.close - basePrice) / basePrice) * 100);
            seriesData.push({ name: symbolNames[sym] || sym, type: 'line', data: pcts, smooth: true, symbol: 'none', lineStyle: { width: 2 } });
          }
        });
      }
      chart.setOption({
        tooltip: { trigger: 'axis', valueFormatter: (val) => val.toFixed(2) + '%' },
        legend: { top: 0, left: 'center', type: 'scroll', icon: 'circle', itemWidth: 8, itemHeight: 8, formatter: (name) => { const sym = labelToSym[name]; const pct = sym ? currentPrices.value[sym]?.pct : null; if (pct == null || isNaN(pct)) return name; return name + ' ' + (Number(pct) > 0 ? '+' : '') + Number(pct).toFixed(2) + '%'; } },
        grid: { left: 40, right: 20, top: 40, bottom: 20 },
        xAxis: { type: 'category', data: xAxisData, axisLine: { lineStyle: { color: '#E2E8F0' } }, axisLabel: { color: '#64748B' } },
        yAxis: { type: 'value', axisLabel: { formatter: '{value}%', color: '#64748B' }, splitLine: { lineStyle: { type: 'dashed', color: '#E2E8F0' } } },
        series: seriesData
      }, true);
    };

    const fetchOverview = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/overview`);
        const data = await res.json();
        if (data.ok) {
          if (data.lifecycle && data.lifecycle.data) lifecycleItems.value = data.lifecycle.data;
          if (data.data && data.data.intraday_snapshot && data.data.intraday_snapshot.items) intradaySnapshotItems.value = data.data.intraday_snapshot.items;
          else if (data.intraday_snapshot && data.intraday_snapshot.items) intradaySnapshotItems.value = data.intraday_snapshot.items;
          if (data.warmup && data.warmup.history) warmupHistory.value = data.warmup.history;
          lastUpdate.value = new Date().toLocaleTimeString('zh-CN', { hour12: false });
          nextTick(() => renderCorrelationChart());
        }
      } catch (err) { console.error('Failed to fetch overview:', err); }
    };

    const getTotalAmount = (pts) => {
      if (!pts || pts.length === 0) return 0;
      const isIncremental = pts.some(p => p.source === 'tencent_backfill' || p.amountMode === 'incremental');
      if (!isIncremental && pts.length > 1) {
        let nonDec = 0;
        for (let i = 1; i < pts.length; i++) {
          if ((pts[i].amount || 0) >= (pts[i-1].amount || 0)) nonDec++;
        }
        if (nonDec / (pts.length - 1) < 0.9) return pts.reduce((s, p) => s + (p.amount || 0), 0);
      }
      if (isIncremental) return pts.reduce((s, p) => s + (p.amount || 0), 0);
      return pts[pts.length - 1].amount || 0;
    };

    const fetchMinuteData = async () => {
      const promises = visibleEtfSymbols.value.map(async (sym) => {
        try {
          const res = await fetch(`${API_BASE}/api/m1/data/minute?symbol=${sym}`);
          const data = await res.json();
          if (data.ok) {
            const pre_close = data.pre_close;
            const dataPoints = data.data;
            let latestPrice = 0, latestPct = 0;
            if (dataPoints && dataPoints.length > 0) {
              const lastPt = dataPoints[dataPoints.length - 1];
              latestPrice = lastPt.price;
              latestPct = lastPt.pct !== undefined ? lastPt.pct : (pre_close ? ((lastPt.price - pre_close) / pre_close) * 100 : 0);
            }
            minuteDataCache.value[sym] = { pre_close, data: dataPoints || [] };
            currentPrices.value[sym] = { price: latestPrice, pct: latestPct, amount: getTotalAmount(dataPoints || []) };
          }
        } catch (err) { console.error(`Failed to fetch minute data for ${sym}:`, err); }
      });
      await Promise.all(promises);
      nextTick(() => { renderCategoryBar(); renderEtfPctBar(); });
      if (chartInstances['correlation']) nextTick(() => renderCorrelationChart());
    };

    const refreshEtfAi = async () => {
      if (etfAiLoading.value) return;
      etfAiLoading.value = true;
      try {
        const res = await fetch(`${API_BASE}/api/ai/sector-analysis`);
        const d = await res.json();
        if (d.text) { etfAiText.value = d.text; etfAiUpdatedAt.value = d.asOf || ''; }
        else { etfAiText.value = '暂无今日 AI 板块解析数据'; etfAiUpdatedAt.value = ''; }
      } catch (e) { etfAiText.value = 'AI 板块解析加载失败'; etfAiUpdatedAt.value = ''; }
      finally { etfAiLoading.value = false; }
    };

    const etfManagerOpen = ref(false);
    const etfFormOpen = ref(false);
    const etfFormMode = ref('add');
    const etfFormEditingCode = ref(null);
    const etfForm = reactive({ name: '', code: '', category: '科技', sub_category: '硬件', error: '' });

    const buildEtfManagerRows = () => {
      const rows = [];
      etfSymbols.value.forEach(code => {
        const name = symbolNames[code] || code;
        rows.push({ name, code, category: etfCategoryMap[code] || '科技', sub_category: etfSubCategoryMap[code] || '硬件', hidden: !!hiddenSymbols[code] });
      });
      return rows;
    };
    const etfManagerRows = ref(buildEtfManagerRows());

    const refreshEtfManagerRows = () => { etfManagerRows.value = buildEtfManagerRows(); };

    const openEtfForm = (mode, row) => {
      etfFormMode.value = mode;
      etfForm.error = '';
      if (mode === 'add') {
        etfForm.name = ''; etfForm.code = ''; etfForm.category = '科技'; etfForm.sub_category = '硬件'; etfFormEditingCode.value = null;
      } else if (row) {
        etfForm.name = row.name; etfForm.code = row.code; etfForm.category = row.category; etfForm.sub_category = row.sub_category; etfFormEditingCode.value = row.code;
      }
      etfFormOpen.value = true;
    };

    const syncMapsFromApi = (apiEtfs) => {
      const newSymbols = [];
      Object.keys(symbolNames).forEach(k => delete symbolNames[k]);
      Object.keys(etfCategoryMap).forEach(k => delete etfCategoryMap[k]);
      Object.keys(etfSubCategoryMap).forEach(k => delete etfSubCategoryMap[k]);
      Object.keys(hiddenSymbols).forEach(k => delete hiddenSymbols[k]);
      Object.entries(apiEtfs).forEach(([name, info]) => {
        newSymbols.push(info.code);
        symbolNames[info.code] = name;
        etfCategoryMap[info.code] = info.category;
        etfSubCategoryMap[info.code] = info.sub_category;
        if (info.hidden) hiddenSymbols[info.code] = true;
      });
      etfSymbols.value = newSymbols;
    };

    const toggleHidden = async (code) => {
      const name = symbolNames[code] || code;
      const meta = { name, code, category: etfCategoryMap[code] || '科技', sub_category: etfSubCategoryMap[code] || '硬件', hidden: !hiddenSymbols[code] };
      try {
        await fetch(`${API_BASE}/api/sector/manage`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(meta) });
        if (hiddenSymbols[code]) delete hiddenSymbols[code]; else hiddenSymbols[code] = true;
        refreshEtfManagerRows();
        nextTick(() => { renderCategoryBar(); renderEtfPctBar(); renderCorrelationChart(); });
      } catch (e) { console.warn('toggleHidden failed', e); }
    };

    const fetchEtfConfig = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/sector/manage`);
        const json = await res.json();
        if (json && json.ok && json.etfs) {
          syncMapsFromApi(json.etfs);
          refreshEtfManagerRows();
          nextTick(() => { renderCategoryBar(); renderEtfPctBar(); });
        }
      } catch (e) { console.warn('ETF配置加载失败，使用硬编码默认值'); }
    };

    const triggerBackfill = async (code, name) => {
      backfillStatus[code] = 'requesting';
      backfillToast.name = name || symbolNames[code] || code;
      backfillToast.code = code;
      backfillToast.status = 'requesting';
      backfillToast.show = true;
      try {
        await fetch(`${API_BASE}/api/m1/run`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ script: 'm1_backfill.py', symbol: code, applyFix: true })
        });
      } catch (e) { console.warn('回补触发失败', e); }
      try {
        await fetch(`${API_BASE}/api/m1/run`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ script: 'm1_minute_fetch_etf.py', symbols: code, force: true })
        });
      } catch (e) { console.warn('分时拉取触发失败', e); }
      setTimeout(async () => {
        try {
          const res = await fetch(`${API_BASE}/api/m1/data/minute?symbol=${code}`);
          const d = await res.json();
          const minuteOk = d.ok && d.data && d.data.length > 0;
          backfillStatus[code] = minuteOk ? 'done' : 'failed';
          backfillToast.status = minuteOk ? 'done' : 'failed';
        } catch (e) {
          backfillStatus[code] = 'failed';
          backfillToast.status = 'failed';
        }
        fetchOverview(); fetchMinuteData();
        setTimeout(() => { backfillToast.show = false; }, 3000);
      }, 15000);
    };

    const closeBackfillToast = () => { backfillToast.show = false; };

    const triggerBackfillRow = (code) => {
      const name = symbolNames[code] || code;
      triggerBackfill(code, name);
    };

    const submitEtfForm = async () => {
      if (!etfForm.name.trim()) { etfForm.error = '名称不能为空'; return; }
      let code = etfForm.code.trim();
      if (!code) { etfForm.error = '代码不能为空'; return; }
      if (/^\d{6}$/.test(code)) {
        code = (code.startsWith('5') ? 'sh' : code.startsWith('1') ? 'sz' : 'sh') + code;
      }
      if (!/^(sh|sz)\d{6}$/.test(code)) { etfForm.error = '代码格式错误，应为 sh/sz + 6位数字（或纯6位数字自动补前缀）'; return; }
      if (etfFormMode.value === 'add' && etfManagerRows.value.find(r => r.code === code)) { etfForm.error = '该代码已存在'; return; }
      try {
        const body = { name: etfForm.name.trim(), code, category: etfForm.category, sub_category: etfForm.sub_category };
        const res = await fetch(`${API_BASE}/api/sector/manage`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        const json = await res.json();
        if (json && json.ok && json.etfs) {
          syncMapsFromApi(json.etfs);
          refreshEtfManagerRows();
          nextTick(() => { renderCategoryBar(); renderEtfPctBar(); });
          etfFormOpen.value = false;
          etfManagerOpen.value = false;
          triggerBackfill(code, etfForm.name.trim());
        } else { etfForm.error = json?.error || '保存失败'; }
      } catch (e) { etfForm.error = '网络错误'; }
    };

    const deleteEtfRow = async (code) => {
      const name = symbolNames[code] || code;
      if (!confirm(`确认删除 "${name}" 吗？`)) return;
      try {
        const res = await fetch(`${API_BASE}/api/sector/manage?name=${encodeURIComponent(name)}`, { method: 'DELETE' });
        const json = await res.json();
        if (json && json.ok && json.etfs) {
          syncMapsFromApi(json.etfs);
          refreshEtfManagerRows();
          nextTick(() => { renderCategoryBar(); renderEtfPctBar(); });
        }
      } catch (e) { console.error('删除失败', e); }
    };

    const categoryPctData = computed(() => {
      const groups = {};
      visibleEtfSymbols.value.forEach(code => {
        const cat = etfCategoryMap[code] || '其他';
        const amt = currentPrices.value[code]?.amount;
        if (!groups[cat]) groups[cat] = 0;
        if (amt != null && isFinite(amt) && amt > 0) groups[cat] += amt;
      });
      return groups;
    });

    const etfPctBarData = computed(() => {
      return visibleEtfSymbols.value
        .map(code => ({
          name: symbolNames[code] || code,
          code,
          amount: currentPrices.value[code]?.amount ?? 0,
          category: etfCategoryMap[code] || '其他'
        }))
        .filter(d => d.amount > 0)
        .sort((a, b) => b.amount - a.amount);
    });

    const fmtAmount = (v) => {
      if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿';
      if (v >= 1e4) return (v / 1e4).toFixed(2) + '万';
      return v.toFixed(0);
    };

    const getBarColor = (v) => v > 0 ? '#3B82F6' : '#A1A1AA';

    const renderCategoryBar = () => {
      const el = document.getElementById('chart-category-bar');
      if (!el) return;
      if (!chartInstances['categoryBar']) chartInstances['categoryBar'] = echarts.init(el);
      const chart = chartInstances['categoryBar'];
      const data = categoryPctData.value;
      const cats = Object.keys(data);
      const vals = cats.map(c => data[c]);
      const maxVal = Math.max(...vals, 1);
      chart.setOption({
        tooltip: { trigger: 'axis', valueFormatter: (v) => v >= 1e8 ? (v / 1e8).toFixed(2) + '亿' : (v / 1e4).toFixed(2) + '万' },
        grid: { left: 85, right: 20, top: 30, bottom: 24 },
        xAxis: { type: 'category', data: cats, axisLabel: { fontSize: 12, color: '#52525B', fontWeight: 'bold' }, axisLine: { lineStyle: { color: '#E4E4E7' } } },
        yAxis: { type: 'value', max: maxVal * 1.2, axisLabel: { fontSize: 9, color: '#71717A', formatter: (v) => v >= 1e8 ? (v / 1e8).toFixed(1) + '亿' : (v / 1e4).toFixed(0) + '万' }, splitLine: { lineStyle: { type: 'dashed', color: '#E4E4E7' } } },
        series: [{ type: 'bar', data: vals.map((v, i) => ({ value: v, itemStyle: { color: cats[i] === '科技' ? '#3B82F6' : '#10B981', borderRadius: [4, 4, 0, 0] } })), barWidth: Math.max(16, Math.min(32, 240 / cats.length)), label: { show: true, position: 'top', fontSize: 11, fontWeight: 'bold', color: '#18181B', formatter: (p) => fmtAmount(p.value) } }]
      }, true);
    };

    const renderEtfPctBar = () => {
      const el = document.getElementById('chart-etf-pct-bar');
      if (!el) return;
      if (!chartInstances['etfPctBar']) chartInstances['etfPctBar'] = echarts.init(el);
      const chart = chartInstances['etfPctBar'];
      const data = etfPctBarData.value;
      const names = data.map(d => d.name);
      const vals = data.map(d => d.amount);
      const cats = data.map(d => d.category);
      const bw = Math.max(6, Math.min(14, 180 / data.length));
      const maxVal = Math.max(...vals, 1);
      chart.setOption({
        tooltip: { trigger: 'axis', valueFormatter: (v) => v >= 1e8 ? (v / 1e8).toFixed(2) + '亿' : (v / 1e4).toFixed(2) + '万' },
        grid: { left: 85, right: 20, top: 30, bottom: 50 },
        xAxis: { type: 'category', data: names, axisLabel: { fontSize: 9, color: '#52525B', rotate: names.length > 8 ? 35 : 0 }, axisLine: { lineStyle: { color: '#E4E4E7' } } },
        yAxis: { type: 'value', max: maxVal * 1.2, axisLabel: { fontSize: 9, color: '#71717A', formatter: (v) => v >= 1e8 ? (v / 1e8).toFixed(1) + '亿' : (v / 1e4).toFixed(0) + '万' }, splitLine: { lineStyle: { type: 'dashed', color: '#E4E4E7' } } },
        series: [{ type: 'bar', data: vals.map((v, i) => ({ value: v, itemStyle: { color: cats[i] === '科技' ? '#3B82F6' : '#10B981', borderRadius: [4, 4, 0, 0] } })), barWidth: bw, label: { show: true, position: 'top', fontSize: 10, fontWeight: 'bold', color: '#18181B', formatter: (p) => fmtAmount(p.value) } }]
      }, true);
    };

    onMounted(() => {
      fetchEtfConfig();
      refreshEtfAi();
      fetchOverview();
      fetchMinuteData();
      nextTick(() => { renderCategoryBar(); renderEtfPctBar(); });
      window.addEventListener('resize', () => { Object.values(chartInstances).forEach(c => c.resize()); });
      setInterval(() => { fetchOverview(); fetchMinuteData(); nextTick(() => { renderCategoryBar(); renderEtfPctBar(); }); }, 600000);
    });

    return {
      activeLifecycleTab, lastUpdate, corrDays,
      etfAiText, etfAiUpdatedAt, etfAiSections,
      etfSymbols, symbolNames, etfCategoryMap,
      etfLifecycleSell, etfLifecycleHold, etfLifecycleWait,
      sortedEtfCycleSymbols, getProcessedGrid, getGridHeaders,
      getPriceColor, getAdviceTextColor, getIntradayItem,
      renderCorrelationChart, renderCategoryBar, renderEtfPctBar,
      etfManagerOpen, etfManagerRows, etfFormOpen, etfFormMode, etfForm,
      openEtfForm, submitEtfForm, deleteEtfRow, toggleHidden, backfillOpen, backfillStatus, backfillToast, closeBackfillToast, triggerBackfillRow
    };
  }
}).mount('#app');
