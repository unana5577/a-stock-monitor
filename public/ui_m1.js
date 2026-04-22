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
    const intradaySnapshotItems = ref([]);
    const breadthData = ref({ up: 0, flat: 0, down: 0, total: 0 });
    const volumeHistory = ref([]);
    const intradayVolume = ref([]);
    const intradayYdayVolume = ref([]);
    const volumeStats = ref({ current: 0, ydayTotal: 0, ydaySameTime: 0, forecast: 0, deltaPct: 0 });
    const marketTotal = ref(0);
    const warmupHistory = ref({});
    const corrDays = ref(60);
    const aiText = ref('加载中...');
    const aiUpdatedAt = ref('');
    const aiLoading = ref(false);
    
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
    
    // Charting state
    const currentPrices = ref({});
    const minuteDataCache = ref({});
    const chartsLoaded = ref({});
    const chartInstances = {};

    // 解析AI返回的 Markdown 文本
    const aiSections = computed(() => {
      const txt = aiText.value || '';
      if (txt === '加载中...' || txt === '等待接入...' || txt === '暂无今日 AI 解读数据') return [{ title: '', content: txt }];
      
      const lines = txt.split('\n');
      const sections = [];
      let currentTitle = '';
      let currentContent = [];
      
      for (const line of lines) {
        if (line.includes('===') || !line.trim()) continue;
        
        // 尝试匹配老版本的格式，如 **【走势判断】**
        let isOldFormat = false;
        const oldTitleMatch = line.match(/^(?:\*\*)?【([^】]+)】(?:\*\*)?/);
        if (oldTitleMatch) {
            isOldFormat = true;
            if (currentTitle) {
              sections.push({ title: currentTitle, content: currentContent.join('\n').trim() });
            }
            currentTitle = oldTitleMatch[1].trim();
            currentContent = [];
            continue; // 老格式标题行通常没有正文
        }
        
        // 匹配带有 ** 的标题，例如 **走势判断**： 或者直接 走势判断：
        // 允许标题中包含空格，并且处理可能的双角冒号
        const titleMatch = line.match(/^(?:\*\*)?\s*([^：:]+?)\s*(?:\*\*)?[：:](.*)/);
        
        if (!isOldFormat && titleMatch && ['走势判断', '情绪定性', '阵营轮动', '资金风格', '操作建议', '盘面核心特征', '异动与风向', '交易员应对策略'].includes(titleMatch[1].trim())) {
          if (currentTitle) {
            sections.push({ title: currentTitle, content: currentContent.join('\n').trim() });
          }
          currentTitle = titleMatch[1].trim();
          currentContent = [];
          
          // 把冒号后面的内容放进 content，并清理可能残留的 markdown 粗体标记
          const rest = titleMatch[2].trim();
          if (rest) currentContent.push(rest.replace(/\*\*/g, ''));
        } else {
          if (currentTitle) {
            // 清理内容里的 markdown 粗体标记
            currentContent.push(line.replace(/\*\*/g, '').trim());
          }
        }
      }
      
      if (currentTitle) {
        sections.push({ title: currentTitle, content: currentContent.join('\n').trim() });
      }
      
      return sections.length > 0 ? sections : [{ title: '原文', content: txt }];
    });

    // 解析仓位进度条 (例如提取 "2-4成" -> 30, "6-8成" -> 70, "5成" -> 50)
    const aiPositionPct = computed(() => {
      const txt = aiText.value || '';
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

    const refreshAi = async (force = false) => {
      if (aiLoading.value) return;
      aiLoading.value = true;
      try {
        const res = await fetch(`${API_BASE}/api/ai/report${force ? '?force=true' : ''}`);
        const d = await res.json();
        if (d.ok && d.data) {
          aiText.value = d.data.content || '';
          aiUpdatedAt.value = d.data.asOf || '';
        } else {
          aiText.value = '暂无今日 AI 解读数据';
          aiUpdatedAt.value = '';
        }
      } catch (e) {
        aiText.value = 'AI 解读加载失败';
      } finally {
        aiLoading.value = false;
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
    
    const getIntradayItem = (symbol) => {
      const items = intradayItems.value || [];
      return items.find(item => item.symbol === symbol) || null;
    };

    // --- Computed for Shared View ---
    const getAdviceTextColor = (advice) => {
      if (!advice) return 'text-gray-500';
      if (advice.includes('建仓') || advice.includes('持') || advice.includes('低吸') || advice.includes('潜伏期') || advice.includes('趋势确立') || advice.includes('主升浪') || advice.includes('洗盘') || advice.includes('承接')) return 'text-red-500';
      if (advice.includes('止损') || advice.includes('回避') || advice.includes('离场') || advice.includes('止盈') || advice.includes('减仓') || advice.includes('加速期') || advice.includes('衰退期') || advice.includes('杀跌期') || advice.includes('派发') || advice.includes('破位') || advice.includes('分歧') || advice.includes('高位滞涨') || advice.includes('警惕回落')) return 'text-green-500';
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
      let today3MinData = new Array(240).fill(null); // Initialize here for global scope within function
      let currentTradedMinutes = 0;
      let finalCumulative = 0;
      
      // Extract yesterday's cumulative volume mapping
      const ydayCumulativeMap = new Map();
      intradayYdayVolume.value.forEach(pt => {
        ydayCumulativeMap.set(pt.asOf, pt.market_amount / 100000000);
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
        
        // Remove the 3-minute aggregation logic and use todayData directly for the curve
        // today3MinData is no longer needed

        let forecastTotal = finalCumulative;
        if (currentTradedMinutes > 0 && currentTradedMinutes < 240) {
          if (ydaySameTimeCumulative > 0 && ydayTotalAmount > 0) {
            // Use relative pace compared to yesterday to forecast, which naturally accounts for the U-shaped volume curve
            forecastTotal = (finalCumulative / ydaySameTimeCumulative) * ydayTotalAmount;
          } else {
            // Fallback if yesterday's data is missing
            const remainingMinutes = 240 - currentTradedMinutes;
            const avgSoFar = finalCumulative / currentTradedMinutes;
            forecastTotal = finalCumulative + avgSoFar * remainingMinutes;
          }
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
      refreshAi();
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
          etfSymbols.forEach((sym) => {
            if (chartInstances[sym]) chartInstances[sym].resize();
          });
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
      aiText,
      aiUpdatedAt,
      aiLoading,
      aiSections,
      aiPositionPct,
      refreshAi,
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
      fmtPct,
      fmtHeatDelta,
      getItemStats
    };
  }
});

app.mount('#app');
