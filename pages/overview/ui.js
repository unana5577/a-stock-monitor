const { createApp, ref, onMounted, computed, nextTick } = Vue;

const resolveApiBase = () => {
  try {
    const { protocol, hostname, port } = window.location || {};
    const isLocal = hostname === 'localhost' || hostname === '127.0.0.1';
    if (isLocal && String(port || '') !== '8787') return `${protocol}//${hostname}:8787`;
  } catch (e) { void e; }
  return window.location.origin;
};

const API_BASE = resolveApiBase();

createApp({
  setup() {
    const lastUpdate = ref('---');
    const marketAmount = ref(null);
    const breadthData = ref({ up: 0, flat: 0, down: 0, total: 0 });
    const volumeHistory = ref([]);
    const intradayVolume = ref([]);
    const intradayYdayVolume = ref([]);
    const volumeStats = ref({ current: 0, ydayTotal: 0, ydaySameTime: 0, forecast: 0, deltaPct: 0 });
    const overviewAiText = ref('加载中...');
    const overviewAiUpdatedAt = ref('');
    const overviewAiLoading = ref(false);

    const indexSymbols = ['sh000001', 'sz399001', 'sz399006', 'sh000688', 'sh000300', 'sh000852', 'sh511130', 'sh511260', 'sh562590', 'bank', 'broker', 'insure'];
    const symbolNames = ref({
      'sh000001': '上证指数',
      'sz399001': '深证成指',
      'sz399006': '创业板指',
      'sh000688': '科创50',
      'sh000300': '沪深300',
      'sh000852': '中证1000',
      'bank': '银行',
      'broker': '证券',
      'insure': '保险'
    });
    const etfSymbolNames = ref({});

    const currentPrices = ref({});
    const minuteDataCache = ref({});
    const chartsLoaded = ref({});
    const chartInstances = {};

    const formatAmount = (val) => {
      if (!val) return '---';
      return (val / 1e8).toFixed(2) + '亿';
    };

    const getPriceColor = (val) => {
      if (val === undefined || val === null) return 'text-q-flat';
      return val > 0 ? 'text-q-up' : (val < 0 ? 'text-q-down' : 'text-q-flat');
    };

    const getBeijingToday = () => {
      const d = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }));
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      return `${y}-${m}-${dd}`;
    };

    const parseAiSections = (txt) => {
      if (!txt) return [];
      if (txt === '加载中...' || txt === '等待接入...' || txt === '暂无今日 AI 解读数据' || txt === 'AI 板块解析加载中...') return [{ title: '', content: txt }];
      const lines = txt.split('\n');
      const sections = [];
      let currentTitle = '';
      let currentContent = [];
      const validTitles = ['走势判断', '情绪定性', '阵营轮动', '资金风格', '操作建议', '盘面核心特征', '异动与风向', '交易员应对策略', '主线追踪', '资金偏好', '主线与异动', '阵营跷跷板', '跷跷板效应', '异动解读', '轮动建议', '重点异动', '轮动分析', '行情研判', '赚钱效应', '跷跷板分析', '共振分析', '轮动规律', '主线趋势'];
      for (const line of lines) {
        if (line.includes('===') || !line.trim()) continue;
        let isOldFormat = false;
        const oldTitleMatch = line.match(/^(?:\*\*)?【([^】]+)】(?:\*\*)?\s*(.*)/);
        if (oldTitleMatch) {
          isOldFormat = true;
          if (currentTitle) { sections.push({ title: currentTitle, content: currentContent.join('\n').trim() }); }
          currentTitle = oldTitleMatch[1].trim();
          currentContent = [];
          const rest = oldTitleMatch[2].trim();
          if (rest) { currentContent.push(rest); }
          continue;
        }
        const titleMatch = line.match(/^(?:\*\*)?\s*([^：:]+?)\s*(?:\*\*)?[：:](.*)/);
        if (!isOldFormat && titleMatch && validTitles.includes(titleMatch[1].trim())) {
          if (currentTitle) { sections.push({ title: currentTitle, content: currentContent.join('\n').trim().replace(/\*\*([^*]+)\*\*/g, '<strong class="text-q-primary">$1</strong>') }); }
          currentTitle = titleMatch[1].trim();
          currentContent = [];
          const rest = titleMatch[2].trim();
          if (rest) currentContent.push(rest);
        } else {
          if (currentTitle) { currentContent.push(line.trim()); } else { currentContent.push(line.trim()); }
        }
      }
      if (currentTitle) {
        let cnt = currentContent.join('\n').trim().replace(/\*\*([^*]+)\*\*/g, '<strong class="text-q-primary">$1</strong>');
        sections.push({ title: currentTitle, content: cnt });
      } else if (currentContent.length > 0) {
        sections.push({ title: '', content: currentContent.join('\n').trim() });
      }
      return sections.map(s => {
        if (s.title) return s;
        return s;
      });
    };

    const overviewAiSections = computed(() => parseAiSections(overviewAiText.value));

    const overviewAiPositionPct = computed(() => {
      const txt = overviewAiText.value || '';
      const match = txt.match(/(\d)(?:-(\d))?成仓位/);
      if (match) {
        if (match[2]) { return (parseInt(match[1]) + parseInt(match[2])) / 2 * 10; }
        return parseInt(match[1]) * 10;
      }
      const match2 = txt.match(/建议(.*?)([2-8])/);
      if (match2) return parseInt(match2[2]) * 10;
      return 50;
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

    const fetchOverview = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/overview`);
        const data = await res.json();
        if (data.ok) {
          if (data.market_amount) marketAmount.value = data.market_amount;
          lastUpdate.value = new Date().toLocaleTimeString('zh-CN', { hour12: false });
        }
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

    const renderVolumeChart = () => {
      const el = document.getElementById('chart-volume');
      if (!el || volumeHistory.value.length === 0) return;
      if (!chartInstances['volume']) chartInstances['volume'] = echarts.init(el);
      const chart = chartInstances['volume'];
      let ydayTotalAmount = 0;
      const todayStr = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Shanghai' })).toISOString().split('T')[0];
      let lastDaily = null;
      for (let i = volumeHistory.value.length - 1; i >= 0; i--) {
        const row = volumeHistory.value[i];
        if (row && row.date < todayStr) { lastDaily = row; break; }
      }
      if (lastDaily) { ydayTotalAmount = lastDaily.market_amount / 100000000; }
      const avgPerMinute = ydayTotalAmount / 240;
      const xAxisData = [];
      let d = new Date();
      d.setHours(9, 30, 0, 0);
      for (let i = 0; i < 120; i++) { xAxisData.push(d.toTimeString().substring(0, 5)); d.setMinutes(d.getMinutes() + 1); }
      d.setHours(13, 0, 0, 0);
      for (let i = 0; i < 120; i++) { xAxisData.push(d.toTimeString().substring(0, 5)); d.setMinutes(d.getMinutes() + 1); }
      const todayData = new Array(240).fill(null);
      let currentTradedMinutes = 0;
      let finalCumulative = 0;
      const ydayCumulativeMap = new Map();
      let lastYdayVol = 0;
      let ydayIdx = 0;
      xAxisData.forEach(timeStr => {
        while (ydayIdx < intradayYdayVolume.value.length && intradayYdayVolume.value[ydayIdx].asOf <= timeStr) {
          lastYdayVol = intradayYdayVolume.value[ydayIdx].market_amount / 100000000;
          ydayIdx++;
        }
        if (lastYdayVol > 0) { ydayCumulativeMap.set(timeStr, lastYdayVol); }
      });
      if (intradayVolume.value.length > 0) {
        let prevCumulative = 0;
        let prevAxisIdx = -1;
        intradayVolume.value.forEach((pt, i) => {
          const timeStr = pt.asOf;
          const axisIdx = xAxisData.indexOf(timeStr);
          if (axisIdx === -1) return;
          if (prevAxisIdx !== -1 && axisIdx < prevAxisIdx) return;
          currentTradedMinutes = axisIdx + 1;
          const currentCumulative = pt.market_amount / 100000000;
          finalCumulative = currentCumulative;
          const spanMinutes = i === 0 ? (axisIdx + 1) : Math.max(1, axisIdx - prevAxisIdx);
          let segmentVolume = i === 0 ? currentCumulative : (currentCumulative - prevCumulative);
          if (segmentVolume < 0) segmentVolume = 0;
          const perMinuteVolume = segmentVolume / spanMinutes;
          const startFill = i === 0 ? 0 : (prevAxisIdx + 1);
          for (let m = startFill; m <= axisIdx; m++) { todayData[m] = perMinuteVolume; }
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
            interval: (index, value) => ['09:30','10:30','11:30','13:00','14:00','15:00'].includes(value)
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
      chart.setOption(option, true);
    };

    const renderMinuteChart = (sym, dataPoints, preClose) => {
      const el = document.getElementById(`chart-minute-${sym}`);
      if (!el) return;
      let chart = echarts.getInstanceByDom(el);
      if (!chart) { chart = echarts.init(el); chartInstances[sym] = chart; }
      const times = [];
      let d = new Date();
      d.setHours(9, 30, 0, 0);
      for (let i = 0; i < 120; i++) { times.push(d.toTimeString().substring(0, 5)); d.setMinutes(d.getMinutes() + 1); }
      d.setHours(13, 0, 0, 0);
      for (let i = 0; i < 120; i++) { times.push(d.toTimeString().substring(0, 5)); d.setMinutes(d.getMinutes() + 1); }
      const prices = [];
      let latestPrice = preClose;
      let latestPct = 0;
      if (dataPoints && dataPoints.length > 0) {
        const pointMap = {};
        dataPoints.forEach(pt => { if (pt.price > 0 && pt.asOf >= "09:30") { pointMap[pt.asOf] = pt; } });
        times.forEach((t) => {
          const pt = pointMap[t];
          if (pt) {
            prices.push(pt.price);
            const ptPct = pt.pct !== undefined ? pt.pct : (preClose ? ((pt.price - preClose) / preClose) * 100 : 0);
            latestPct = ptPct;
            latestPrice = pt.price;
          } else if (prices.length > 0 && dataPoints.length > 0 && t <= dataPoints[dataPoints.length - 1].asOf) {
            const prevPrice = prices[prices.length - 1];
            prices.push(prevPrice);
          } else {
            prices.push(null);
          }
        });
      }
      currentPrices.value[sym] = { price: latestPrice, pct: latestPct };
      chartsLoaded.value[sym] = true;
      const option = {
        animation: false,
        grid: { left: 0, right: 0, top: 10, bottom: 0 },
        xAxis: { type: 'category', data: times, show: false },
        yAxis: [{ type: 'value', min: 'dataMin', max: 'dataMax', show: false }],
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
    };

    const fetchMinuteData = async () => {
      const etfCodes = Object.keys(etfSymbolNames.value || {});
      const allSymbols = [...new Set([...indexSymbols, ...etfCodes])];
      allSymbols.map(async (sym) => {
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
            nextTick(() => { renderMinuteChart(sym, dataPoints, pre_close); });
          }
        } catch (err) { console.error(`Failed to fetch minute for ${sym}:`, err); }
      });
    };

    const fetchEtfNames = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/sector/manage`);
        const json = await res.json();
        if (json && json.ok && json.etfs) {
          const names = { ...symbolNames.value };
          Object.entries(json.etfs).forEach(([code, info]) => {
            names[code] = info.api_name || code;
          });
          symbolNames.value = names;
          etfSymbolNames.value = names;
        }
      } catch (e) { console.warn('ETF名称加载失败'); }
    };

    onMounted(() => {
      fetchEtfNames();
      refreshOverviewAi();
      fetchOverview();
      fetchMinuteData();
      fetchBreadth();
      fetchVolumeHistory();
      window.addEventListener('resize', () => {
        Object.values(chartInstances).forEach(chart => chart.resize());
      });
      setInterval(() => {
        fetchOverview();
        fetchMinuteData();
        fetchBreadth();
        refreshOverviewAi();
      }, 60000);
    });

    return {
      lastUpdate,
      marketAmount,
      breadthData,
      volumeStats,
      overviewAiSections,
      overviewAiPositionPct,
      overviewAiUpdatedAt,
      indexSymbols,
      symbolNames,
      currentPrices,
      chartsLoaded,
      formatAmount,
      getPriceColor
    };
  }
}).mount('#app');
