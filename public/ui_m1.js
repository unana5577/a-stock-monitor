const { createApp, ref, onMounted, computed, nextTick, watch } = Vue;

const API_BASE = window.location.origin;

const app = createApp({
  setup() {
    // --- State ---
    const activeTab = ref('overview'); // overview, market
    const activeLifecycleTab = ref('after'); // 'intraday' or 'after'
    const lastUpdate = ref('---');
    const marketAmount = ref(null);
    const lifecycleItems = ref([]);
    const breadthData = ref({ up: 0, flat: 0, down: 0, total: 0 });
    const volumeHistory = ref([]);
    const warmupHistory = ref({});
    
    // Indices config
    const indexSymbols = ['sh000001', 'sz399001', 'sz399006', 'sh000688', 'sh000300', 'sh000852', 'sh511130', 'sh511260'];
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
    
    // Charting state
    const currentPrices = ref({});
    const chartsLoaded = ref({});
    const chartInstances = {};

    // Computed
    const etfLifecycleItems = computed(() => {
      const items = lifecycleItems.value || [];
      // 只保留 etfSymbols 里的 9 个核心 ETF
      return items.filter(item => item.symbol && etfSymbols.includes(item.symbol));
    });
    
    const etfLifecycleHold = computed(() => {
      const items = etfLifecycleItems.value || [];
      return items.filter(item => {
        const signal = item.阶段信号 || '';
        const advice = item.操作建议 || '';
        return signal.includes('建仓') || signal.includes('低吸') || signal.includes('潜伏期') || signal.includes('趋势确立') || signal.includes('主升浪') || advice.includes('持有') || advice.includes('持股');
      });
    });
    
    const etfLifecycleWait = computed(() => {
      const items = etfLifecycleItems.value || [];
      const holdIds = new Set(etfLifecycleHold.value.map(i => i.symbol));
      return items.filter(item => {
        if (holdIds.has(item.symbol)) return false; // 互斥，如果在持有池里，就不在震荡池
        const signal = item.阶段信号 || '';
        const advice = item.操作建议 || '';
        return signal.includes('观望') || signal.includes('震荡') || signal.includes('超跌反弹') || signal.includes('背离期') || signal.includes('筑底期') || advice.includes('观望');
      });
    });
    
    const etfLifecycleSell = computed(() => {
      const items = etfLifecycleItems.value || [];
      const holdIds = new Set(etfLifecycleHold.value.map(i => i.symbol));
      const waitIds = new Set(etfLifecycleWait.value.map(i => i.symbol));
      return items.filter(item => {
        if (holdIds.has(item.symbol) || waitIds.has(item.symbol)) return false;
        const signal = item.阶段信号 || '';
        const advice = item.操作建议 || '';
        return signal.includes('离场') || signal.includes('高位回调') || signal.includes('止盈') || signal.includes('止损') || signal.includes('减仓') || signal.includes('回避') || signal.includes('加速期') || signal.includes('衰退期') || signal.includes('杀跌期') || advice.includes('减仓');
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

    // --- Helpers ---
    const formatAmount = (val) => {
      if (!val) return '---';
      return (val / 1e8).toFixed(2) + '亿';
    };

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
    
    const getAdviceTextColor = (advice) => {
      if (!advice) return 'text-gray-500';
      if (advice.includes('建仓') || advice.includes('持') || advice.includes('低吸') || advice.includes('潜伏期') || advice.includes('趋势确立') || advice.includes('主升浪')) return 'text-red-500';
      if (advice.includes('止损') || advice.includes('回避') || advice.includes('离场') || advice.includes('止盈') || advice.includes('减仓') || advice.includes('加速期') || advice.includes('衰退期') || advice.includes('杀跌期')) return 'text-green-500';
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

    // --- Data Fetching ---
    
    const fetchOverview = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/m1/data/overview`);
        const data = await res.json();
        
        if (data.ok) {
          if (data.market_amount) marketAmount.value = data.market_amount;
          if (data.lifecycle && data.lifecycle.data) lifecycleItems.value = data.lifecycle.data;
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
          nextTick(() => renderVolumeChart());
        }
      } catch (err) { console.error('Failed to fetch volume history:', err); }
    };

    // --- Charts ---

    const renderVolumeChart = () => {
      const el = document.getElementById('chart-volume');
      if (!el || volumeHistory.value.length < 2) return;
      if (!chartInstances['volume']) chartInstances['volume'] = echarts.init(el);
      
      const chart = chartInstances['volume'];
      // Mock line data based on real market amount scale for UI testing
      const data = volumeHistory.value.slice(-60).map(d => d.market_amount / 1e8);
      const xAxis = volumeHistory.value.slice(-60).map(d => d.date);

      const option = {
        grid: { left: 30, right: 10, top: 5, bottom: 5 },
        xAxis: { type: 'category', data: xAxis, show: false },
        yAxis: { type: 'value', show: false, splitLine: { show: false } },
        series: [{
          data: data,
          type: 'line',
          smooth: true,
          lineStyle: { width: 2, color: '#2563EB' },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(37, 99, 235, 0.15)' },
              { offset: 1, color: 'rgba(37, 99, 235, 0)' }
            ])
          },
          symbol: 'none'
        }]
      };
      chart.setOption(option);
    };

    const renderCorrelationChart = () => {
      const el = document.getElementById('chart-correlation');
      if (!el || Object.keys(warmupHistory.value).length === 0) return;
      if (!chartInstances['correlation']) chartInstances['correlation'] = echarts.init(el);
      
      const chart = chartInstances['correlation'];
      
      // Pick a few symbols to draw (e.g., semiconductor, cloud, comms)
      const symbolsToDraw = ['sh512480', 'sh516510', 'sh515880', 'sh563530'];
      const seriesData = [];
      let xAxisData = [];

      symbolsToDraw.forEach((sym, idx) => {
        if (warmupHistory.value[sym]) {
          const hist = warmupHistory.value[sym];
          if (xAxisData.length === 0) xAxisData = hist.map(h => h.date);
          
          // Normalize to start at 0%
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

      const option = {
        tooltip: { trigger: 'axis', valueFormatter: (val) => val.toFixed(2) + '%' },
        legend: { top: 0, left: 'center', type: 'scroll', icon: 'circle', itemWidth: 8, itemHeight: 8 },
        grid: { left: 40, right: 20, top: 40, bottom: 20 },
        xAxis: { type: 'category', data: xAxisData, axisLine: { lineStyle: { color: '#E2E8F0' } }, axisLabel: { color: '#64748B' } },
        yAxis: { type: 'value', axisLabel: { formatter: '{value}%', color: '#64748B' }, splitLine: { lineStyle: { type: 'dashed', color: '#E2E8F0' } } },
        series: seriesData
      };
      
      chart.setOption(option);
    };

    const renderMinuteChart = (sym, dataPoints, preClose) => {
      if (!chartInstances[sym]) {
        const el = document.getElementById(`chart-minute-${sym}`);
        if (!el) return;
        chartInstances[sym] = echarts.init(el);
      }
      
      const chart = chartInstances[sym];
      
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
        dataPoints.forEach((pt, idx) => {
          if (idx < 240) {
            prices.push(pt.price);
            if (preClose) {
              const p = ((pt.price - preClose) / preClose) * 100;
              pcts.push(p);
              latestPct = p;
            }
            latestPrice = pt.price;
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
          min: preClose ? preClose * (1 - maxAbsPct/100) : 'dataMin',
          max: preClose ? preClose * (1 + maxAbsPct/100) : 'dataMax',
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
          },
          markLine: preClose ? {
            silent: true,
            symbol: 'none',
            lineStyle: { color: '#94A3B8', type: 'dashed', width: 1 },
            data: [{ yAxis: preClose }]
          } : undefined
        }]
      };
      
      chart.setOption(option);
      chartsLoaded.value[sym] = true;
    };

    const fetchMinuteData = async () => {
      const promises = indexSymbols.map(async (sym) => {
        try {
          const res = await fetch(`${API_BASE}/api/m1/data/minute?symbol=${sym}`);
          const data = await res.json();
          if (data.ok) {
            nextTick(() => renderMinuteChart(sym, data.data, data.pre_close));
          }
        } catch (err) { console.error(`Failed to fetch minute data for ${sym}:`, err); }
      });
      await Promise.all(promises);
    };

    // --- Lifecycle Hooks ---
    onMounted(() => {
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
      }, 60000);
    });

    watch(activeTab, (newVal) => {
      nextTick(() => {
        if (newVal === 'market') {
          if (chartInstances['correlation']) chartInstances['correlation'].resize();
        } else if (newVal === 'overview') {
          if (chartInstances['volume']) chartInstances['volume'].resize();
          indexSymbols.forEach((sym) => {
            if (chartInstances[sym]) chartInstances[sym].resize();
          });
        }
      });
    });

    return {
      activeTab,
      activeLifecycleTab,
      lastUpdate,
      marketAmount,
      breadthData,
      indexSymbols,
      etfSymbols,
      symbolNames,
      etfLifecycleItems,
      etfLifecycleHold,
      etfLifecycleWait,
      etfLifecycleSell,
      etfLifecycleOther,
      currentPrices,
      chartsLoaded,
      warmupHistory,
      formatAmount,
      getPriceColor,
      getAdviceBgClass,
      getAdviceTextColor,
      getMomentumTextColor,
      getGridItem,
      getProcessedGrid,
      getGridHeaders,
      fmtPct,
      fmtHeatDelta,
      getItemStats
    };
  }
});

app.mount('#app');
