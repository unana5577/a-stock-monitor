const { createApp, ref, computed } = window.Vue;

createApp({
  setup() {
    const sparks = ref({});
    const dataTs = ref(0);
    const aiBrief = ref({ title:'规则版即将上线', detail: '将根据国债/行业/指数/情绪判定避险或上攻、风险与仓位' });
    const aiText = ref('');
    const promptText = ref('');
    const promptOutput = ref('');
    const promptLoading = ref(false);
    const promptError = ref('');
    const sectorPromptText = ref('');
    const sectorPromptOutput = ref('');
    const sectorPromptLoading = ref(false);
    const sectorPromptError = ref('');
    const sectorInput = ref(localStorage.getItem('sector_input') || '半导体,云计算,新能源,商业航天,创新药,有色金属,煤炭,电力,通讯设备');
    const watchList = ref([]);
    const watchIndicators = ref({});
    const activeTab = ref('overview');
    const marketAi = ref({ seesaw: '数据加载中', streak: '数据加载中' });
    const market = ref({ sse:{price:null,pct:null}, szi:{price:null,pct:null}, chinaext:{price:null,pct:null}, star:{price:null,pct:null} });
    const extra = ref({ avg:{price:null,pct:null}, hs300:{price:null,pct:null}, csi2000:{price:null,pct:null} });
    const bonds = ref({ gov:{pct:null,slope:null}, tl:{price:null,pct:null}, t:{price:null,pct:null} });
    const sectors = ref({ bank:null, broker:null, insure:null });
    const sentiment = ref({ volume:0, volumeStr:'-', upCount:'-', downCount:'-', volumeCmp:null });
    const overviewDailyReady = ref(false);
    const overviewHistoryDay = ref('');
    const overviewHistoryTs = ref(0);
    const minuteCache = {};
    const buildAiSections = (sourceText, brief) => {
      const map = {};
      const text = (sourceText || '').replace(/\r/g, '').trim();
      const detail = (brief?.detail || '').replace(/\r/g, '').trim();
      const title = (brief?.title || '').trim();
      const source = text || detail || title || '';
      if (source) {
        const raw = source.replace(/\s+/g, ' ');
        const pattern = /(走势判断|支撑依据|情绪结论|市场情绪|资金态度|资金风格|仓位建议|提示)\s*[：:]/g;
        let lastTitle = '';
        let lastIndex = 0;
        let match;
        while ((match = pattern.exec(raw))) {
          if (lastTitle) {
            const seg = raw.slice(lastIndex, match.index).trim();
            if (seg) map[lastTitle] = seg;
          }
          lastTitle = match[1];
          lastIndex = pattern.lastIndex;
        }
        if (lastTitle) {
          const seg = raw.slice(lastIndex).trim();
          if (seg) map[lastTitle] = seg;
        }
      }
      if (!map['走势判断'] && title) map['走势判断'] = title;
      if (!Object.keys(map).length && detail) map['走势判断'] = detail;
      const pick = (keys) => {
        for (const k of keys) {
          if (map[k]) return map[k];
        }
        return '';
      };
      const sections = [
        { title: '走势判断', content: pick(['走势判断']) },
        { title: '支撑依据', content: pick(['支撑依据', '依据']) },
        { title: '情绪结论', content: pick(['情绪结论', '市场情绪', '情绪']) },
        { title: '资金风格', content: pick(['资金风格', '资金态度', '资金']) },
        { title: '仓位建议', content: pick(['仓位建议', '仓位']) },
        { title: '提示', content: pick(['提示', '提醒']) }
      ];
      return sections.map(s => ({ title: s.title, content: s.content || '暂无' }));
    };
    const aiSections = computed(() => buildAiSections(aiText.value, aiBrief.value));
    const minuteMap = {
      'spark-sse': 'sse',
      'spark-szi': 'szi',
      'spark-gem': 'gem',
      'spark-star': 'star',
      'spark-hs300': 'hs300',
      'spark-csi2000': 'csi2000',
      'spark-avg': 'avg',
      'spark-tl': 'tl',
      'spark-t': 't',
      'spark-bank': 'bank',
      'spark-broker': 'broker',
      'spark-insure': 'insure'
    };
    const dailyMap = {
      'spark-sse': 'sse',
      'spark-szi': 'szi',
      'spark-gem': 'gem',
      'spark-star': 'star',
      'spark-hs300': 'hs300',
      'spark-csi2000': 'csi2000',
      'spark-avg': 'avg',
      'spark-tl': 'tl',
      'spark-t': 't',
      'spark-bank': 'bank',
      'spark-broker': 'broker',
      'spark-insure': 'insure'
    };
    const minuteTarget = {
      sse: (v) => market.value.sse = v,
      szi: (v) => market.value.szi = v,
      gem: (v) => market.value.chinaext = v,
      star: (v) => market.value.star = v,
      hs300: (v) => extra.value.hs300 = v,
      csi2000: (v) => extra.value.csi2000 = v,
      avg: (v) => extra.value.avg = v,
      tl: (v) => bonds.value.tl = v,
      t: (v) => bonds.value.t = v,
      bank: (v) => sectors.value.bank = { pct: v.pct },
      broker: (v) => sectors.value.broker = { pct: v.pct },
      insure: (v) => sectors.value.insure = { pct: v.pct }
    };

    const fmtTime = (ts) => {
      if (!ts) return '';
      const d = new Date(ts);
      const month = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      return `${month}-${day} ${d.toTimeString().slice(0, 8)}`;
    };

    const toHM = (t) => {
      if (!t) return '';
      if (t.includes(' ')) return t.split(' ')[1].slice(0,5);
      if (t.includes(':')) return t.slice(-5);
      if (t.length >= 4) return t.slice(-4).replace(/(\d{2})(\d{2})/, '$1:$2');
      return t;
    };

    const buildTradingAxis = () => {
      const axis = [];
      const push = (h, m) => axis.push(`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`);
      const toHM = (total) => {
        const h = Math.floor(total / 60);
        const m = total % 60;
        return { h, m };
      };
      for (let i = 0; i <= 120; i += 1) {
        const { h, m } = toHM(9 * 60 + 30 + i);
        push(h, m);
      }
      for (let i = 0; i <= 120; i += 1) {
        const { h, m } = toHM(13 * 60 + i);
        push(h, m);
      }
      return axis;
    };

    const pickPrice = (p) => {
      const c = p?.close;
      if (typeof c === 'number' && c > 0) return c;
      const o = p?.open;
      if (typeof o === 'number' && o > 0) return o;
      return null;
    };

    const renderSpark = (el, arr, prevClose) => {
      if (!arr || !arr.length) {
        if (sparks.value[el]) sparks.value[el].clear();
        return;
      }
      const base = (typeof prevClose === 'number' && prevClose > 0) ? prevClose : pickPrice(arr[0]);
      const axis = buildTradingAxis();
      const map = new Map();
      arr.forEach((p) => {
        const t = toHM(p.time);
        const v = pickPrice(p);
        if (!t || v == null || base == null) return;
        map.set(t, ((v - base) / base) * 100);
      });
      const valsRaw = axis.map(t => map.has(t) ? map.get(t) : null);
      const firstIdx = valsRaw.findIndex(v => v != null);
      const lastIdx = (() => {
        if (firstIdx === -1) return -1;
        for (let i = valsRaw.length - 1; i >= 0; i -= 1) {
          if (valsRaw[i] != null) return i;
        }
        return -1;
      })();
      let lastSeen = null;
      const vals = valsRaw.map((v, i) => {
        if (v != null) { lastSeen = v; return v; }
        if (firstIdx !== -1 && i > firstIdx && i < lastIdx) return lastSeen;
        return null;
      });
      const latest = [...vals].reverse().find(v => v != null) ?? 0;
      const color = latest >= 0 ? '#f87171' : '#4ade80';
      if (!sparks.value[el]) { sparks.value[el] = window.echarts.init(document.getElementById(el)); }
      sparks.value[el].setOption({
        grid:{left:0,right:0,top:0,bottom:0},
        xAxis:{type:'category',data:axis,show:false},
        yAxis:{type:'value',show:false, min:(v)=>Math.min(0, v.min), max:(v)=>Math.max(0, v.max)},
        tooltip: { trigger: 'axis', formatter: (params)=>{ const p = params.find(x => x && x.value != null) || params[0] || {}; const v = p.value; const n = Number(v); const s = Number.isFinite(n) ? n.toFixed(2) : v; return `${p.axisValue||''}<br/>${s}%`; } },
        markLine:{ silent:true, symbol:'none', lineStyle:{color:'#9ca3af',width:0.6}, data:[{ yAxis: 0 }]},
        series:[
          { type:'line', data:vals, smooth:true, symbol:'none', connectNulls:false, lineStyle:{width:1.2, color} }
        ]
      });
    };
    
    const renderVolumeSpark = (el, arr, ydayValue) => {
      const buildAxisFromSeries = (series) => {
        if (!series || !series.length) return [];
        const out = [];
        const seen = new Set();
        series.forEach((p) => {
          const t = toHM(p.time);
          if (!t || seen.has(t)) return;
          seen.add(t);
          out.push(t);
        });
        return out;
      };
      const buildVolumeVals = (series, axis) => {
        if (!series || !series.length || !axis.length) return [];
        const map = new Map();
        series.forEach((p) => {
          const t = toHM(p.time);
          const v = p.volume ?? p.value;
          if (!t || v == null || v === 0) return;
          map.set(t, v);
        });
        const valsRaw = axis.map(t => map.has(t) ? map.get(t) : null);
        const firstIdx = valsRaw.findIndex(v => v != null);
        const lastIdx = (() => {
          if (firstIdx === -1) return -1;
          for (let i = valsRaw.length - 1; i >= 0; i -= 1) {
            if (valsRaw[i] != null) return i;
          }
          return -1;
        })();
        let lastSeen = null;
        return valsRaw.map((v, i) => {
          if (v != null) { lastSeen = v; return v; }
          if (firstIdx !== -1 && i > firstIdx && i < lastIdx) return lastSeen;
          return null;
        });
      };
      let axis = buildTradingAxis();
      let vals = buildVolumeVals(arr, axis);
      const hasAny = vals.some(v => v != null);
      if (!hasAny) {
        axis = buildAxisFromSeries(arr);
        vals = buildVolumeVals(arr, axis);
      }
      if (!axis.length || !vals.length) {
        if (sparks.value[el]) sparks.value[el].clear();
        return;
      }
      const fmtVol = (v) => v==null ? '-' : `${(v / 10000).toFixed(1)}亿`;
      const series = [];
      const ydayNum = Number.isFinite(Number(ydayValue)) ? Number(ydayValue) : null;
      const markLine = (ydayNum != null)
        ? {
          silent:true,
          symbol:'none',
          lineStyle:{color:'#60a5fa',width:1},
          label:{show:true, formatter:`昨日 ${fmtVol(ydayNum)}`, color:'#60a5fa', fontSize:11, position:'end'},
          data:[{ yAxis: ydayNum }]
        }
        : undefined;
      if (vals.length) {
        const line = { name: '今日量能', type:'line', data:vals, smooth:true, symbol:'none', connectNulls:false, lineStyle:{width:1.2, color:'#f87171'} };
        if (markLine) line.markLine = markLine;
        series.push(line);
      }
      if (!sparks.value[el]) { sparks.value[el] = window.echarts.init(document.getElementById(el)); }
      sparks.value[el].setOption({
        grid:{left:0,right:0,top:0,bottom:0},
        xAxis:{type:'category',data:axis,show:false},
        yAxis:{type:'value',show:false, min:0, max:(v)=>Math.max(0, v.max, ydayNum ?? 0)},
        tooltip: { trigger: 'axis', formatter: (params)=>{ const items = (params || []).filter(x => x && x.value != null); if (!items.length) return ''; const time = items[0]?.axisValue || ''; const lines = items.map(p => { const n = Number(p.value); const s = Number.isFinite(n) ? n.toFixed(0) : p.value; return `${p.seriesName} ${s}`; }); return `${time}<br/>${lines.join('<br/>')}`; } },
        series
      });
    };

    const renderDailySpark = (el, series) => {
      if (!series || !series.length) {
        if (sparks.value[el]) sparks.value[el].clear();
        return;
      }
      const axis = series.map(p => p.date);
      const base = Number(series[0]?.close);
      const vals = series.map((p) => {
        const v = Number(p?.close);
        if (!Number.isFinite(v) || !Number.isFinite(base) || base === 0) return null;
        return ((v - base) / base) * 100;
      });
      const latest = [...vals].reverse().find(v => v != null) ?? 0;
      const color = latest >= 0 ? '#f87171' : '#4ade80';
      if (!sparks.value[el]) { sparks.value[el] = window.echarts.init(document.getElementById(el)); }
      sparks.value[el].setOption({
        grid:{left:0,right:0,top:0,bottom:0},
        xAxis:{type:'category',data:axis,show:false},
        yAxis:{type:'value',show:false, min:(v)=>Math.min(0, v.min), max:(v)=>Math.max(0, v.max)},
        tooltip: { trigger: 'axis', formatter: (params)=>{ const p = params.find(x => x && x.value != null) || params[0] || {}; const v = p.value; const n = Number(v); const s = Number.isFinite(n) ? n.toFixed(2) : v; return `${p.axisValue||''}<br/>${s}%`; } },
        markLine:{ silent:true, symbol:'none', lineStyle:{color:'#9ca3af',width:0.6}, data:[{ yAxis: 0 }]},
        series:[
          { type:'line', data:vals, smooth:true, symbol:'none', connectNulls:false, lineStyle:{width:1.2, color} }
        ]
      });
    };

    const renderDailyVolumeSpark = (el, series) => {
      if (!series || !series.length) {
        if (sparks.value[el]) sparks.value[el].clear();
        return;
      }
      const axis = series.map(p => p.date);
      const vals = series.map(p => {
        const v = Number(p?.amount);
        return Number.isFinite(v) ? v : null;
      });
      if (!sparks.value[el]) { sparks.value[el] = window.echarts.init(document.getElementById(el)); }
      sparks.value[el].setOption({
        grid:{left:0,right:0,top:0,bottom:0},
        xAxis:{type:'category',data:axis,show:false},
        yAxis:{type:'value',show:false, min:0, max:(v)=>Math.max(0, v.max)},
        tooltip: { trigger: 'axis', formatter: (params)=>{ const p = params.find(x => x && x.value != null) || params[0] || {}; const n = Number(p.value); const s = Number.isFinite(n) ? `${(n / 10000).toFixed(1)}亿` : p.value; return `${p.axisValue||''}<br/>${s}`; } },
        series:[{ name: '180日成交额', type:'line', data:vals, smooth:true, symbol:'none', connectNulls:false, lineStyle:{width:1.2, color:'#60a5fa'} }]
      });
    };
    
    const pctColor = (v) => v==null? 'text-gray-400' : (v>=0? 'text-red-400' : 'text-green-400');
    const fmtPct = (v) => v==null? '-' : (v>0? `+${v}%` : `${v}%`);
    const fmtVolume = (v) => v==null? '-' : `${(v / 10000).toFixed(1)}亿`;
    const fmtVolumeCmp = (cmp) => {
      if (!cmp) return '昨日缺失';
      if (cmp.pct == null || cmp.delta == null || !cmp.dir) return '昨日缺失';
      const pct = Math.abs(cmp.pct).toFixed(2);
      const delta = Math.abs(cmp.delta);
      return `${cmp.dir} ${pct}% / ${fmtVolume(delta)}`;
    };

    const corrOf = (a, b) => {
      const n = Math.min(a.length, b.length);
      if (n < 5) return null;
      let sumA = 0;
      let sumB = 0;
      for (let i = 0; i < n; i += 1) {
        sumA += a[i];
        sumB += b[i];
      }
      const meanA = sumA / n;
      const meanB = sumB / n;
      let num = 0;
      let denA = 0;
      let denB = 0;
      for (let i = 0; i < n; i += 1) {
        const da = a[i] - meanA;
        const db = b[i] - meanB;
        num += da * db;
        denA += da * da;
        denB += db * db;
      }
      const den = Math.sqrt(denA * denB);
      if (!den) return null;
      return num / den;
    };

    const buildSeesawAi = (histRes) => {
      const history = histRes?.history || {};
      const names = Object.keys(history).filter(n => (history[n] || []).length);
      if (!names.length) return '数据缺失';
      const seriesMap = {};
      names.forEach((n) => {
        const arr = (history[n] || []).map(h => Number(h.close)).filter(v => Number.isFinite(v));
        if (arr.length >= 5) seriesMap[n] = arr;
      });
      const keys = Object.keys(seriesMap);
      if (keys.length < 2) return '数据缺失';
      let bestNeg = null;
      let bestPos = null;
      for (let i = 0; i < keys.length; i += 1) {
        for (let j = i + 1; j < keys.length; j += 1) {
          const a = keys[i];
          const b = keys[j];
          const c = corrOf(seriesMap[a], seriesMap[b]);
          if (!Number.isFinite(c)) continue;
          if (bestNeg == null || c < bestNeg.val) bestNeg = { a, b, val: c };
          if (bestPos == null || c > bestPos.val) bestPos = { a, b, val: c };
        }
      }
      const parts = [];
      if (bestNeg && bestNeg.val <= -0.3) parts.push(`${bestNeg.a}与${bestNeg.b}负相关${bestNeg.val.toFixed(2)}，跷跷板特征明显`);
      else parts.push('未见明显跷跷板');
      if (bestPos && bestPos.val >= 0.5) parts.push(`${bestPos.a}与${bestPos.b}同涨同跌${bestPos.val.toFixed(2)}`);
      else parts.push('共振板块不明显');
      return `180天观察：${parts.join('；')}。`;
    };

    const buildStreakAi = (rankRes, histRes) => {
      const history = histRes?.history || {};
      if (!rankRes) return '数据缺失';
      const getStreak = (name, dir) => {
        const hist = history[name];
        if (!hist || !hist.length) return 0;
        let cnt = 0;
        for (let i = hist.length - 1; i >= 0; i -= 1) {
          const v = Number(hist[i]?.pct);
          if (!Number.isFinite(v)) break;
          if (dir === 'up' && v > 0) cnt += 1;
          else if (dir === 'down' && v < 0) cnt += 1;
          else break;
        }
        return cnt;
      };
      const upList = (rankRes.up || []).map(i => ({ name: i.name, streak: getStreak(i.name, 'up') })).sort((a, b) => b.streak - a.streak);
      const downList = (rankRes.down || []).map(i => ({ name: i.name, streak: getStreak(i.name, 'down') })).sort((a, b) => b.streak - a.streak);
      const topUp = upList[0] || { name: '', streak: 0 };
      const topDown = downList[0] || { name: '', streak: 0 };
      const upText = topUp.streak >= 3 ? `连涨：${topUp.name} ${topUp.streak}天` : '连涨持续性不强';
      const downText = topDown.streak >= 3 ? `连跌：${topDown.name} ${topDown.streak}天` : '连跌持续性不强';
      let trend = '趋势信号一般';
      if (topUp.streak >= 5 && topUp.streak > topDown.streak) trend = '主线可能形成';
      if (topDown.streak >= 5 && topDown.streak > topUp.streak) trend = '趋势走坏需防守';
      return `${upText}；${downText}；判断：${trend}。`;
    };
    
    const fetchSnapshot = async (withAi) => {
      try {
        const res = await fetch(`http://localhost:8787/api/snapshot/latest?ai=${withAi ? '1' : '0'}`);
        if (!res.ok) throw new Error('bad');
        const data = await res.json();
        if (data?.aiBrief) aiBrief.value = data.aiBrief;
        if (data?.aiText) aiText.value = data.aiText;
        if (data?.sentiment) sentiment.value = { ...sentiment.value, ...data.sentiment };
        if (data?.sentiment?.volumeCmp) sentiment.value.volumeCmp = data.sentiment.volumeCmp;
        const arrToday = data?.sentiment?.volumeSeries || [];
        const ydayValue = data?.sentiment?.volumeCmp?.yday ?? null;
        sentiment.value.volumeSeries = arrToday;
        sentiment.value.volumeSeriesYday = data?.sentiment?.volumeSeriesYday || [];
        if (!overviewDailyReady.value) renderVolumeSpark('spark-volume', arrToday, ydayValue);
        if (data?.bonds?.gov?.pct != null) bonds.value.gov = { ...bonds.value.gov, pct: data.bonds.gov.pct };
        if (data?.bonds?.tl) {
          const v = data.bonds.tl;
          bonds.value.tl = { price: v.price ?? bonds.value.tl.price, pct: v.pct ?? bonds.value.tl.pct };
        } else if (data?.bonds?.tl2603) {
          const v = data.bonds.tl2603;
          bonds.value.tl = { price: v.price ?? bonds.value.tl.price, pct: v.pct ?? bonds.value.tl.pct };
        }
        if (data?.bonds?.t) {
          const v = data.bonds.t;
          bonds.value.t = { price: v.price ?? bonds.value.t.price, pct: v.pct ?? bonds.value.t.pct };
        } else if (data?.bonds?.t2603) {
          const v = data.bonds.t2603;
          bonds.value.t = { price: v.price ?? bonds.value.t.price, pct: v.pct ?? bonds.value.t.pct };
        }
        if (data?.sectors?.bank?.pct != null) sectors.value.bank = { pct: data.sectors.bank.pct };
        if (data?.sectors?.broker?.pct != null) sectors.value.broker = { pct: data.sectors.broker.pct };
        if (data?.sectors?.insure?.pct != null) sectors.value.insure = { pct: data.sectors.insure.pct };
        if (data?.ts) dataTs.value = data.ts;
      } catch (e) { console.error(e); }
    };

    const fetchPrompt = async () => {
      try {
        const res = await fetch('http://localhost:8787/api/prompt/stock-daily');
        if (!res.ok) throw new Error('bad');
        const data = await res.json();
        if (data?.text) promptText.value = data.text;
      } catch (e) { console.error(e); }
    };

    const fetchSectorPrompt = async () => {
      try {
        const res = await fetch('http://localhost:8787/api/prompt/sector-analysis');
        if (!res.ok) throw new Error('bad');
        const data = await res.json();
        if (data?.text) sectorPromptText.value = data.text;
      } catch (e) { console.error(e); }
    };

    const runPromptDebug = async () => {
      promptLoading.value = true;
      promptError.value = '';
      promptOutput.value = '';
      try {
        const res = await fetch('http://localhost:8787/api/ai/debug', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: promptText.value })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data?.error || '调用失败');
        promptOutput.value = data?.text || '';
        aiText.value = data?.text || '';
      } catch (e) {
        promptError.value = String(e?.message || '调用失败');
      } finally {
        promptLoading.value = false;
      }
    };

    const runSectorPromptDebug = async () => {
      sectorPromptLoading.value = true;
      sectorPromptError.value = '';
      sectorPromptOutput.value = '';
      try {
        const res = await fetch('http://localhost:8787/api/ai/sector-debug', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: sectorPromptText.value })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data?.error || '调用失败');
        sectorPromptOutput.value = data?.text || '';
        const parsed = parseSectorAiText(data?.text || '');
        if (parsed.seesaw || parsed.streak) {
          marketAi.value = {
            seesaw: parsed.seesaw || marketAi.value.seesaw,
            streak: parsed.streak || marketAi.value.streak
          };
        }
      } catch (e) {
        sectorPromptError.value = String(e?.message || '调用失败');
      } finally {
        sectorPromptLoading.value = false;
      }
    };

    const deriveFromSeries = (series, prevClose) => {
      if (!series || !series.length) return { price: null, pct: null };
      const first = (typeof prevClose === 'number' && prevClose > 0) ? prevClose : pickPrice(series[0]);
      const last = pickPrice(series[series.length - 1]);
      const pct = first ? +(((last - first) / first) * 100).toFixed(2) : null;
      return { price: last ?? null, pct };
    };

    const deriveSlope = (series) => {
      if (!series || series.length < 2) return null;
      const first = pickPrice(series[0]);
      const last = pickPrice(series[series.length - 1]);
      if (!first || !last) return null;
      return (last - first) / first;
    };

    const fetchMinute = async (el, code) => {
      try {
        const res = await fetch(`http://localhost:8787/api/minute/${code}`);
        if (!res.ok) throw new Error('bad');
        const data = await res.json();
        const series = data?.series || [];
        const prevClose = data?.prevClose ?? null;
        minuteCache[el] = series;
        if (series.length) {
          if (!(overviewDailyReady.value && dailyMap[el])) renderSpark(el, series, prevClose);
          const v = deriveFromSeries(series, prevClose);
          const slope = deriveSlope(series);
          const setter = minuteTarget[code];
          if (setter) setter(v, slope);
          if (data?.latest?.time) {
            const t = Date.parse(data.latest.time.replace(' ', 'T'));
            if (!Number.isNaN(t)) dataTs.value = t;
          }
        }
      } catch(e) { console.error(e); }
    };

    const refreshMinuteAll = async () => {
      const tasks = Object.entries(minuteMap).map(([el, code]) => fetchMinute(el, code));
      await Promise.all(tasks);
    };

    const fetchBreadth = async () => {
      try {
        const res = await fetch('http://localhost:8787/api/market/breadth');
        if (!res.ok) return;
        const data = await res.json();
        if (!data) return;

        const container = document.getElementById('market-breadth');
        if (container) container.classList.remove('hidden');

        const { up, down } = data;
        const total = up + down;

        const upPct = (total ? (up / total * 100) : 50).toFixed(1) + '%';
        const downPct = (total ? (down / total * 100) : 50).toFixed(1) + '%';

        const elUp = document.getElementById('breadth-up');
        if (elUp) elUp.style.width = upPct;
        const elDown = document.getElementById('breadth-down');
        if (elDown) elDown.style.width = downPct;

        const elUpCount = document.getElementById('breadth-up-count');
        if (elUpCount) elUpCount.textContent = `涨 ${up}`;
        const elDownCount = document.getElementById('breadth-down-count');
        if (elDownCount) elDownCount.textContent = `跌 ${down}`;

        const ratio = document.getElementById('breadth-ratio');
        if (ratio) {
          if (up > down * 2) {
            ratio.textContent = "普涨 🔥";
            ratio.className = "text-red-600 font-bold";
          } else if (down > up * 2) {
            ratio.textContent = "普跌 ❄️";
            ratio.className = "text-green-600 font-bold";
          } else {
            ratio.textContent = "震荡 ⚖️";
            ratio.className = "text-gray-600 font-bold";
          }
        }
      } catch (e) { console.error(e); }
    };

    const parseSectorAiText = (text) => {
      const raw = (text || '').trim();
      if (!raw) return { seesaw: '', streak: '' };
      const pick = (title) => {
        const reg = new RegExp(`【${title}】([^【]+)`, 'm');
        const m = raw.match(reg);
        return m ? m[1].trim() : '';
      };
      const seesaw = [pick('跷跷板分析'), pick('共振分析')].filter(Boolean).join('；');
      const streak = [pick('轮动规律'), pick('主线趋势')].filter(Boolean).join('；');
      if (!seesaw && !streak) return { seesaw: raw, streak: raw };
      return { seesaw, streak };
    };

    const buildSectorQuery = () => {
      const list = (sectorInput.value || '').split(',').map(s => s.trim()).filter(Boolean);
      const uniq = Array.from(new Set(list));
      if (!uniq.length) return '';
      return 'sectors=' + encodeURIComponent(uniq.join(','));
    };

    const updateSectorWatch = async () => {
      const list = (sectorInput.value || '').split(',').map(s => s.trim()).filter(Boolean);
      const uniq = Array.from(new Set(list));
      const next = uniq.join(',');
      sectorInput.value = next;
      localStorage.setItem('sector_input', next);
      try {
        await fetch('http://localhost:8787/api/sector/watch-list', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ watch_list: uniq })
        });
      } catch (e) { console.error(e); }
      watchList.value = uniq;
      await fetchSectorData();
    };

    const fetchSectorData = async () => {
      try {
        const query = buildSectorQuery();
        const historyUrl = 'http://localhost:8787/api/sector/history?rt=1&days=20' + (query ? '&' + query : '');
        const [rankRes, histRes, aiRes] = await Promise.all([
          fetch('http://localhost:8787/api/sector/rank').then(r => r.json()),
          fetch(historyUrl).then(r => r.json()),
          fetch('http://localhost:8787/api/ai/sector-analysis').then(r => r.json()).catch(() => ({}))
        ]);
        
        renderSectorRank(rankRes);
        renderSectorHistory(histRes);
        if (histRes?.indicators) watchIndicators.value = histRes.indicators || {};
        if (Array.isArray(histRes?.watch)) watchList.value = histRes.watch;
        const fallback = {
          seesaw: buildSeesawAi(histRes),
          streak: buildStreakAi(rankRes, histRes)
        };
        const parsed = parseSectorAiText(aiRes?.text || '');
        marketAi.value = {
          seesaw: parsed.seesaw || fallback.seesaw,
          streak: parsed.streak || fallback.streak
        };
      } catch (e) {
        console.error("Sector module init failed", e);
        const container = document.getElementById('sector-analysis');
        if (container) container.innerHTML = "<p>数据加载失败</p>";
        marketAi.value = { seesaw: '数据加载失败', streak: '数据加载失败' };
      }
    };

    const fetchWatchList = async () => {
      try {
        const res = await fetch('http://localhost:8787/api/sector/watch-list');
        if (!res.ok) throw new Error('bad');
        const data = await res.json();
        const list = Array.isArray(data?.watch_list) ? data.watch_list : [];
        if (list.length) {
          const next = list.join(',');
          sectorInput.value = next;
          localStorage.setItem('sector_input', next);
          watchList.value = list;
        }
      } catch (e) { console.error(e); }
    };

    const lastIndicator = (name) => {
      const arr = watchIndicators.value[name] || [];
      return arr.length ? arr[arr.length - 1] : {};
    };

    const renderSectorRank = (data) => {
      if (!data) return;
      
      const toPct = (v) => {
        if (v == null) return null;
        if (typeof v === 'string') {
          const n = Number(v.replace('%', ''));
          return Number.isFinite(n) ? n : null;
        }
        const n = Number(v);
        return Number.isFinite(n) ? n : null;
      };

      const renderChart = (domId, list, color, align) => {
        const chartDom = document.getElementById(domId);
        if (!chartDom || !list || list.length === 0) return;
        
        const myChart = window.echarts.init(chartDom);
        const names = list.map(d => d.name);
        const rawPcts = list.map(d => toPct(d.pct));
        const barPcts = rawPcts.map(v => (Number.isFinite(v) ? Math.abs(+v.toFixed(1)) : 0));
        const maxVal = Math.max(1, ...barPcts);
        const labelFormatter = (params) => {
          const item = list[params.dataIndex] || {};
          const name = item.name || '';
          const v = toPct(item.pct);
          const pct = Number.isFinite(v) ? v.toFixed(1) : '-';
          return `${name} ${pct}%`;
        };
        
        const isLeft = align === 'left';
        const option = {
          tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
          grid: { left: 0, right: 0, top: 0, bottom: 0, containLabel: false },
          xAxis: {
            type: 'value',
            min: 0,
            max: maxVal,
            inverse: isLeft,
            boundaryGap: [0, 0],
            axisLabel: { show: false },
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { show: false }
          },
          yAxis: {
            type: 'category',
            data: names,
            inverse: true,
            axisLabel: { show: false },
            axisLine: { show: false },
            axisTick: { show: false }
          },
          series: [
            {
              type: 'bar',
              data: barPcts,
              itemStyle: { color: color },
              barWidth: 12,
              label: {
                show: true,
                position: isLeft ? 'insideLeft' : 'insideRight',
                align: isLeft ? 'left' : 'right',
                formatter: labelFormatter,
                distance: 0,
                fontSize: 10
              }
            }
          ]
        };
        myChart.setOption(option);
      };

      const downList = (data.down || []).slice().sort((a, b) => {
        const av = toPct(a?.pct);
        const bv = toPct(b?.pct);
        if (!Number.isFinite(av) && !Number.isFinite(bv)) return 0;
        if (!Number.isFinite(av)) return 1;
        if (!Number.isFinite(bv)) return -1;
        return av - bv;
      });
      const upList = (data.up || []).slice().sort((a, b) => {
        const av = toPct(a?.pct);
        const bv = toPct(b?.pct);
        if (!Number.isFinite(av) && !Number.isFinite(bv)) return 0;
        if (!Number.isFinite(av)) return 1;
        if (!Number.isFinite(bv)) return -1;
        return bv - av;
      });
      renderChart('sector-rank-down-chart', downList, '#4ade80', 'left');
      renderChart('sector-rank-up-chart', upList, '#eb5454', 'right');
    };

    const renderSectorHistory = (data) => {
      const chartDom = document.getElementById('sector-trend-chart');
      const infoDom = document.getElementById('sector-info');
      if (infoDom) {
        let infoHtml = '';
        if (data.watch && data.watch.length) {
          infoHtml += `<div class="text-xs text-gray-500 mb-1">关注：${data.watch.join(' / ')}</div>`;
        }
        if (data.correlations && data.correlations.length > 0) {
          const top = data.correlations[0];
          infoHtml += `
            <div class="bg-blue-50 border-l-4 border-blue-500 p-2 mb-2">
              <div class="text-xs font-bold text-blue-700">跷跷板效应发现</div>
              <div class="text-xs text-blue-600">
                <span class="font-bold text-red-500">${top.pair[0]}</span> 与 <span class="font-bold text-blue-500">${top.pair[1]}</span> 
                强负相关 (系数: ${top.val})。
              </div>
            </div>
          `;
        }
        const minute = data.minute || {};
        const items = Object.entries(minute).map(([name, item]) => {
          const v = deriveFromSeries(item?.series || [], item?.prevClose ?? null);
          if (v?.pct == null) return '';
          const cls = pctColor(v.pct);
          return `<span class="${cls}">${name} ${v.pct.toFixed(2)}%</span>`;
        }).filter(Boolean);
        if (items.length) {
          infoHtml += `<div class="text-xs text-gray-600 mb-2">实时：${items.join(' / ')}</div>`;
        }
        infoDom.innerHTML = infoHtml;
      }
      
      if (!chartDom || !data.history) return;
      
      const myChart = window.echarts.init(chartDom);
      const series = [];
      let dates = [];
      
      Object.keys(data.history).forEach(name => {
        const hist = data.history[name];
        if (!hist || hist.length === 0) return;
        
        if (dates.length === 0) dates = hist.map(h => h.date);
        
        const base = hist[0].close;
        const lineData = hist.map(h => ((h.close - base) / base * 100).toFixed(2));
        
        series.push({
          name: name,
          type: 'line',
          showSymbol: false,
          smooth: true,
          data: lineData,
          emphasis: { focus: 'series' }
        });
      });

      const option = {
        title: { text: '180天相对走势 (归一化)', left: 'center', textStyle: { fontSize: 12 } },
        tooltip: { 
          trigger: 'axis',
          formatter: function(params) {
            let res = params[0].axisValue + '<br/>';
            params.sort((a, b) => b.value - a.value);
            params.forEach(p => {
              const color = p.value > 0 ? 'red' : 'green';
              res += `<span style="display:inline-block;margin-right:5px;border-radius:10px;width:9px;height:9px;background-color:${p.color}"></span>`;
              res += `${p.seriesName}: <span style="color:${color}">${p.value}%</span><br/>`;
            });
            return res;
          }
        },
        legend: { 
          type: 'scroll', 
          bottom: 0, 
          textStyle: {fontSize: 10},
          selectedMode: 'multiple' // Allow toggling
        },
        grid: { left: '5%', right: '5%', bottom: '20%', top: '20%', containLabel: true },
        xAxis: { type: 'category', data: dates },
        yAxis: { type: 'value', name: '累计%' },
        series: series
      };
      myChart.setOption(option);
    };

    const fetchOverviewHistory = async (force) => {
      const nowTs = Date.now();
      if (!force && overviewHistoryTs.value && nowTs - overviewHistoryTs.value < 30 * 60 * 1000) return;
      try {
        const res = await fetch('http://localhost:8787/api/overview/history');
        if (!res.ok) throw new Error('bad');
        const data = await res.json();
        if (!data?.series) return;
        overviewHistoryTs.value = nowTs;
        overviewHistoryDay.value = data?.day || '';
        overviewDailyReady.value = true;
        Object.entries(dailyMap).forEach(([el, key]) => {
          renderDailySpark(el, data.series[key] || []);
        });
        renderDailyVolumeSpark('spark-volume', data.volume || []);
      } catch (e) { console.error(e); }
    };

    const refreshAll = async () => {
      await fetchSnapshot(false);
      await refreshMinuteAll();
      await fetchOverviewHistory(false);
      await fetchBreadth();
      await fetchSectorData();
    };

    const isMarketOpen = () => {
      const d = new Date();
      const day = d.getDay();
      if (day === 0 || day === 6) return false;
      const minutes = d.getHours() * 60 + d.getMinutes();
      const morning = minutes >= 570 && minutes <= 690;
      const afternoon = minutes >= 780 && minutes <= 900;
      return morning || afternoon;
    };

    const refreshAi = async (force) => {
      if (!force && !isMarketOpen()) return;
      await fetchSnapshot(true);
    };
    
    const init = async () => {
      fetchPrompt();
      fetchSectorPrompt();
      await fetchWatchList();
      await refreshAll();
      await refreshAi(false);
    };
    init();
    setInterval(refreshAll, 15000);
    setInterval(() => refreshAi(false), 30 * 60 * 1000);

    return { activeTab, aiBrief, aiSections, marketAi, promptText, promptOutput, promptLoading, promptError, runPromptDebug, sectorPromptText, sectorPromptOutput, sectorPromptLoading, sectorPromptError, runSectorPromptDebug, refreshAi, market, bonds, extra, sectors, sentiment, pctColor, fmtPct, fmtVolumeCmp, refreshAll, dataTs, fmtTime, sectorInput, updateSectorWatch, watchList, watchIndicators, lastIndicator };
  }
}).mount('#app');
