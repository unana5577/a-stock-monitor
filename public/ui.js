const { createApp, ref, computed } = window.Vue;

createApp({
  setup() {
    const sparks = ref({});
    const dataTs = ref(0);
    const aiBrief = ref({ title:'规则版即将上线', detail: '将根据国债/行业/指数/情绪判定避险或上攻、风险与仓位' });
    const aiText = ref('');
    const aiUpdatedAt = ref(0);
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
    const currentDays = ref(60);
    const lifecycleItems = ref([]);
    const sectorLoading = ref(false);
    const watchIndicators = ref({});
    const activeTab = ref('overview');
    const marketAi = ref({ seesaw: '数据加载中', streak: '数据加载中' });
    const market = ref({ sse:{price:null,pct:null}, szi:{price:null,pct:null}, chinaext:{price:null,pct:null}, star:{price:null,pct:null} });
    const extra = ref({ avg:{price:null,pct:null}, hs300:{price:null,pct:null}, csi2000:{price:null,pct:null} });
    const bonds = ref({ gov:{pct:null,slope:null}, tl:{price:null,pct:null}, t:{price:null,pct:null} });
    const sectors = ref({ bank:{price:null,pct:null}, broker:{price:null,pct:null}, insure:{price:null,pct:null} });
    const sentiment = ref({ volume:0, volumeStr:'-', upCount:'-', downCount:'-', volumeCmp:null });
    const overviewDailyReady = ref(false);
    const overviewHistoryDay = ref('');
    const overviewHistoryTs = ref(0);
    const minuteCache = {};
    const sectorTs = ref(0);
    const sectorCacheKey = 'sector_cache_v1';
    const sectorHistoryPayload = ref(null);
    const sectorLifecyclePayload = ref(null);
    const sectorRotationPayload = ref(null);
    const sectorIntradayPayload = ref(null);
    const intradayTs = ref(0);
    const intradayCacheMs = 2 * 60 * 1000;
    const intradayIdleCacheMs = 10 * 60 * 1000;
    const intradayView = ref('summary');
    const signalsMap = ref({});
    const panicPayload = ref(null);
    const showSectorManager = ref(false);
    const profileGroups = ref({});
    const profileUpdatedAt = ref('');
    const manageSectorName = ref('');
    const sectorGroupOptions = ['资源', '硬件', '软件'];
    const rotationSequencePayload = ref(null);
    const rotationSequenceDays = ref(60);
    const rotationSequenceTs = ref(0);
    const rotationSequenceLoading = ref(false);
    const rotationSequenceCacheMs = 10 * 60 * 1000;
    const warmupTs = ref(0);
    const warmupCacheMs = 10 * 60 * 1000;
    const rotationFilter = ref('全部');
    const rotationExpanded = ref({});
    const rotationMonthSpan = ref(Number(localStorage.getItem('rotation_month_span') || 2));
    const newsList = ref([]);
    const newsLoading = ref(false);
    const newsTs = ref(0);
    const apiBase = (() => {
      let q = '';
      try {
        const params = new URLSearchParams(location.search || '');
        q = (params.get('api') || '').trim();
        if (q) localStorage.setItem('api_base', q);
      } catch (e) { q = ''; }
      const stored = (localStorage.getItem('api_base') || '').trim();
      if (stored) return stored.replace(/\/+$/, '');
      if (location.protocol === 'file:' || location.origin === 'null') return 'http://localhost:8787';
      return location.origin;
    })();
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

    const pickLastPctFromMinute = (series, prevClose) => {
      if (!Array.isArray(series) || !series.length) return null;
      const last = series[series.length - 1];
      const lastPrice = pickPrice(last);
      const first = (typeof prevClose === 'number' && prevClose > 0) ? prevClose : pickPrice(series[0]);
      if (!first || !lastPrice) return null;
      return +(((lastPrice - first) / first) * 100).toFixed(2);
    };

    const toSignalAction = (sig, ydayPct, nowPct, isPanic) => {
      const y = Number(ydayPct);
      const n = Number(nowPct);
      const yOk = Number.isFinite(y);
      const nOk = Number.isFinite(n);
      if (isPanic) return { action: '风控', color: 'text-gray-600' };
      if (sig === 'false_kill') {
        if (yOk && nOk && y <= -0.5 && n <= -0.5) return { action: '错杀', color: 'text-orange-600' };
        return { action: '观望', color: 'text-gray-600' };
      }
      if (sig === 'long') {
        if (nOk && n >= 0.5) return { action: '建仓', color: 'text-red-600' };
        return { action: '观望', color: 'text-gray-600' };
      }
      return { action: '观望', color: 'text-gray-600' };
    };

    const watchIntradayRows = computed(() => {
      const hist = sectorHistoryPayload.value || {};
      const lifecycle = sectorLifecyclePayload.value || {};
      const mainline = sectorRotationPayload.value?.mainline || [];
      const topMap = new Map();
      (Array.isArray(mainline) ? mainline : []).slice(0, 3).forEach((m, idx) => {
        const name = String(m?.['板块名称'] || '').trim();
        if (name) topMap.set(name, idx + 1);
      });
      const items = Array.isArray(lifecycle?.items) ? lifecycle.items : [];
      const byName = new Map();
      items.forEach((it) => {
        const name = String(it?.['板块名称'] || '').trim();
        if (name) byName.set(name, it);
      });
      const list = Array.isArray(hist?.watch) && hist.watch.length ? hist.watch : (watchList.value || []);
      const out = list.map((name) => {
        const h = hist?.history?.[name] || [];
        const last = h.length ? h[h.length - 1] : null;
        const prev = h.length >= 2 ? h[h.length - 2] : null;
        const ydayPct = prev?.pct ?? null;
        const todayPct = last?.pct ?? null;
        const minute = hist?.minute?.[name] || {};
        const minutePct = pickLastPctFromMinute(minute?.series, minute?.prevClose);
        const nowPct = minutePct ?? todayPct;
        const it = byName.get(name) || {};
        const momentum = it?.['动能'] || '-';
        const behavior = it?.['资金行为'] || '-';
        const advice = it?.['操作建议'] || '-';
        const ch = it?.['指标数据']?.['Amount_Share_Change'];
        const chNum = Number(ch);
        const chOk = Number.isFinite(chNum);
        let tag = '';
        const y = Number(ydayPct);
        const n = Number(nowPct);
        const yOk = Number.isFinite(y);
        const nOk = Number.isFinite(n);
        if (yOk && nOk) {
          if (y <= -1 && n >= 0.5) tag = '修复转强';
          else if (y < 0 && n > 0) tag = '转强';
          else if (y > 0 && n < 0) tag = '转弱';
          else if (n >= 1) tag = '今日强势';
          else if (y < 0 && n < 0 && n > y) tag = '跌势收敛';
          else if (y < 0 && n < 0 && n < y) tag = '跌势加剧';
          else if (n <= -1) tag = '今日走弱';
        }
        const sig = signalsMap.value?.[name];
        const sigView = toSignalAction(sig, ydayPct, nowPct, !!panicPayload.value?.is_panic);
        const action = advice;
        const actionColor = getAdviceColor(action);
        const topRank = topMap.get(name) || null;
        return {
          name,
          ydayPct,
          nowPct,
          tag,
          momentum,
          behavior,
          action,
          actionColor,
          topRank,
          sigAction: sigView.action,
          sigColor: sigView.color,
          shareChange: chOk ? +chNum.toFixed(3) : null
        };
      });
      const score = (row) => {
        const tag = row.tag || '';
        if (tag.includes('启动')) return 3;
        if (tag.includes('走强')) return 2;
        if (tag.includes('回落')) return -2;
        if (tag.includes('走弱')) return -1;
        return 0;
      };
      out.sort((a, b) => {
        const ar = a.topRank || 99;
        const br = b.topRank || 99;
        if (ar !== br) return ar - br;
        return score(b) - score(a);
      });
      return out;
    });

    const rotationTopGroups = computed(() => {
      const groups = sectorRotationPayload.value?.groups || [];
      const rows = groups.filter((g) => g && g['组别'] && Number.isFinite(Number(g['均值得分'])));
      return rows.slice(0, 5);
    });

    const intradayBars = computed(() => {
      const bars = sectorIntradayPayload.value?.intraday?.bars || [];
      return Array.isArray(bars) ? bars : [];
    });

    const intradaySignal = computed(() => {
      return sectorIntradayPayload.value?.intraday?.signal || '';
    });

    const intradayReason = computed(() => {
      const reason = sectorIntradayPayload.value?.intraday?.reason || [];
      return Array.isArray(reason) ? reason : [];
    });

    const intradayMax = computed(() => {
      const vals = intradayBars.value.map(b => Math.abs(Number(b?.today_pct || 0))).filter(v => Number.isFinite(v));
      return vals.length ? Math.max(...vals, 0.1) : 1;
    });

    const riskSummary = computed(() => {
      const mainline = sectorRotationPayload.value?.mainline || [];
      const tags = [];
      const seen = new Set();
      let cap = 1.0;
      mainline.forEach((m) => {
        const newsTags = m?.news_view?.risk_tags || [];
        newsTags.forEach((t) => {
          const v = String(t || '').trim();
          if (!v || seen.has(v)) return;
          seen.add(v);
          tags.push(v);
        });
        const max = Number(m?.exec_view?.position?.max);
        if (Number.isFinite(max)) cap = Math.min(cap, max);
      });
      return { tags, cap: Number.isFinite(cap) ? cap : 1.0 };
    });
    const rotationFilters = computed(() => {
      const set = new Set(['全部', '资源', '硬件', '软件', '科技']);
      const groups = sectorRotationPayload.value?.groups || [];
      groups.forEach((g) => {
        const raw = String(g?.['组别'] || '').trim();
        if (!raw) return;
        const head = raw.split(':')[0];
        if (head) set.add(head);
      });
      return Array.from(set);
    });
    const rotationMainline = computed(() => {
      const list = sectorRotationPayload.value?.mainline || [];
      if (rotationFilter.value === '全部') return list;
      const key = rotationFilter.value;
      return list.filter((m) => {
        const groups = Array.isArray(m?.groups) ? m.groups : [];
        return groups.some((g) => {
          const name = String(g || '');
          if (!name) return false;
          const head = name.split(':')[0];
          return head === key || name.includes(key);
        });
      });
    });
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
    const lockIndexSparks = true;
    const indexSparkEls = new Set([
      'spark-sse','spark-szi','spark-gem','spark-star','spark-hs300','spark-csi2000','spark-avg',
      'spark-bank','spark-broker','spark-insure','spark-t','spark-tl'
    ]);
    const dailySeriesLen = {};
    const minDailyPoints = 5;
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
      bank: (v) => sectors.value.bank = { price: v.price ?? null, pct: v.pct },
      broker: (v) => sectors.value.broker = { price: v.price ?? null, pct: v.pct },
      insure: (v) => sectors.value.insure = { price: v.price ?? null, pct: v.pct }
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

    const extractDate = (t) => {
      if (!t) return '';
      const s = String(t);
      if (s.includes(' ')) return s.split(' ')[0];
      if (s.includes('T')) return s.split('T')[0];
      return '';
    };

    const normalizeMinuteSeries = (data) => {
      const series = Array.isArray(data?.series) ? data.series : [];
      const day = data?.day || extractDate(series[series.length - 1]?.time) || extractDate(series[0]?.time) || '';
      if (!day) return { series, day: data?.day || '' };
      const filtered = series.filter((p) => {
        const d = extractDate(p?.time);
        if (!d) return true;
        return d === day;
      });
      return { series: filtered, day };
    };

    const buildTs = (day, t) => {
      if (!t) return null;
      const s = String(t);
      if (s.includes(' ')) return s.replace(' ', 'T');
      if (s.includes('T')) return s;
      if (day && s.includes(':')) return `${day}T${s.length === 5 ? s : s.slice(0, 5)}:00`;
      return null;
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
    
    const renderVolumeSpark = (el, arr, ydayArr) => {
      const buildVolumeVals = (series, axis) => {
        if (!series || !series.length || !axis.length) return { vals: [], raw: [] };
        const map = new Map();
        series.forEach((p) => {
          const t = toHM(p.time);
          const v = p.volume ?? p.value;
          if (!t || v == null || v === 0) return;
          map.set(t, v);
        });
        const rawVals = axis.map(t => map.has(t) ? map.get(t) : null);
        const firstIdx = rawVals.findIndex(v => v != null);
        const lastIdx = (() => {
          if (firstIdx === -1) return -1;
          for (let i = rawVals.length - 1; i >= 0; i -= 1) {
            if (rawVals[i] != null) return i;
          }
          return -1;
        })();
        let lastSeen = null;
        const filled = rawVals.map((v, i) => {
          if (v != null) { lastSeen = v; return v; }
          if (firstIdx !== -1 && i > firstIdx && i < lastIdx) return lastSeen;
          return null;
        });
        const base = filled.find(v => v != null);
        const vals = base ? filled.map(v => (v == null ? null : +(((v - base) / base) * 100).toFixed(2))) : filled.map(() => null);
        return { vals, raw: filled };
      };
      const axis = buildTradingAxis();
      const today = buildVolumeVals(arr, axis);
      const yday = buildVolumeVals(ydayArr, axis);
      const hasAny = today.raw.some(v => v != null) || yday.raw.some(v => v != null);
      if (!axis.length || !hasAny) {
        if (sparks.value[el]) sparks.value[el].clear();
        return;
      }
      const series = [];
      if (today.vals.length) {
        const latest = [...today.vals].reverse().find(v => v != null) ?? 0;
        const color = latest >= 0 ? '#f87171' : '#4ade80';
        series.push({
          name: '今日量能',
          type:'line',
          data: today.vals.map((v, i) => v == null ? null : ({ value: v, raw: today.raw[i] })),
          smooth:true,
          symbol:'none',
          connectNulls:false,
          lineStyle:{width:1.2, color}
        });
      }
      if (yday.vals.length) {
        series.push({
          name: '昨日量能',
          type:'line',
          data: yday.vals.map((v, i) => v == null ? null : ({ value: v, raw: yday.raw[i] })),
          smooth:true,
          symbol:'none',
          connectNulls:false,
          lineStyle:{width:1, color:'#60a5fa', type:'dashed'}
        });
      }
      if (!sparks.value[el]) { sparks.value[el] = window.echarts.init(document.getElementById(el)); }
      sparks.value[el].setOption({
        grid:{left:0,right:0,top:0,bottom:0},
        xAxis:{type:'category',data:axis,show:false},
        yAxis:{type:'value',show:false, min:(v)=>Math.min(0, v.min), max:(v)=>Math.max(0, v.max)},
        tooltip: {
          trigger: 'axis',
          formatter: (params)=>{
            const items = (params || []).filter(x => x && x.value != null);
            if (!items.length) return '';
            const time = items[0]?.axisValue || '';
            const lines = items.map(p => {
              const raw = p?.data?.raw;
              const n = Number(raw);
              const s = Number.isFinite(n) ? `${(n / 10000).toFixed(1)}亿` : '-';
              return `${p.seriesName} ${s}`;
            });
            return `${time}<br/>${lines.join('<br/>')}`;
          }
        },
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
      const pctNum = Number(cmp.pct);
      const deltaNum = Number(cmp.delta);
      if (!Number.isFinite(pctNum) || !Number.isFinite(deltaNum)) return '昨日缺失';
      const dir = deltaNum >= 0 ? '增量' : '缩量';
      const pct = Math.abs(pctNum).toFixed(2);
      const delta = Math.abs(deltaNum);
      return `${dir} ${pct}% / ${fmtVolume(delta)}`;
    };

    const fmtHeatDelta = (raw) => {
      const n = Number(raw);
      if (!Number.isFinite(n)) return '-';
      const pct = Math.abs(n) < 1 ? n * 100 : n;
      const sign = pct > 0 ? '+' : '';
      return `${sign}${pct.toFixed(2)}%`;
    };

    const rotationMatrixAxisAll = computed(() => {
      const hist = sectorHistoryPayload.value || {};
      const history = hist.history || {};
      const dates = new Set();
      Object.values(history).forEach((arr) => {
        (Array.isArray(arr) ? arr : []).forEach((r) => {
          const d = r?.date;
          if (d) dates.add(String(d));
        });
      });
      return Array.from(dates).sort().slice(-180);
    });

    const rotationMatrixAxis = computed(() => {
      const axis = rotationMatrixAxisAll.value || [];
      if (!axis.length) return [];
      const span = Number(rotationMonthSpan.value) || 2;
      const last = axis[axis.length - 1];
      const lastMonth = String(last || '').slice(0, 7);
      if (!lastMonth) return axis.slice(-60);
      const months = [];
      for (let i = axis.length - 1; i >= 0; i -= 1) {
        const m = String(axis[i] || '').slice(0, 7);
        if (!m) continue;
        if (!months.includes(m)) months.push(m);
        if (months.length >= span) break;
      }
      const allow = new Set(months);
      const filtered = axis.filter(d => allow.has(String(d).slice(0, 7)));
      return filtered.length ? filtered : axis.slice(-60);
    });

    const rotationMatrixMonths = computed(() => {
      const axis = rotationMatrixAxis.value || [];
      const out = [];
      let cur = '';
      let start = 0;
      for (let i = 0; i < axis.length; i += 1) {
        const d = axis[i] || '';
        const m = d ? d.slice(0, 7) : '';
        if (!m) continue;
        if (!cur) {
          cur = m;
          start = i;
          continue;
        }
        if (m !== cur) {
          out.push({ label: cur, start, len: i - start });
          cur = m;
          start = i;
        }
      }
      if (cur) out.push({ label: cur, start, len: axis.length - start });
      return out;
    });

    const rotationMatrixRows = computed(() => {
      const hist = sectorHistoryPayload.value || {};
      const history = hist.history || {};
      const axis = rotationMatrixAxis.value || [];
      const groups = profileGroups.value || {};
      const list = Array.isArray(hist?.watch) && hist.watch.length ? hist.watch : (watchList.value || []);
      const MAINLINE_WINDOW = 20;
      const MAINLINE_MIN_UP_DAYS = 12;
      const MAINLINE_MIN_CUM_PCT = 6;
      const MAINLINE_MIN_STREAK = 4;
      const MAINLINE_MAX = 3;
      const base = (Array.isArray(list) ? list : []).map((name) => {
        const nm = String(name || '').trim();
        const g = String(groups?.[nm] || '未分类');
        const rows = Array.isArray(history?.[nm]) ? history[nm] : [];
        const byDate = new Map();
        rows.forEach((r) => {
          const d = r?.date;
          if (!d) return;
          byDate.set(String(d), Number(r?.pct));
        });
        const tail = rows.slice(-MAINLINE_WINDOW);
        let upDays = 0;
        let cumPct = 0;
        let streak = 0;
        let maxStreak = 0;
        tail.forEach((r) => {
          const v = Number(r?.pct);
          const ok = Number.isFinite(v);
          if (ok) cumPct += v;
          if (ok && v > 0) {
            upDays += 1;
            streak += 1;
            if (streak > maxStreak) maxStreak = streak;
          } else {
            streak = 0;
          }
        });
        const stats = {
          upDays,
          cumPct: +cumPct.toFixed(2),
          maxStreak
        };
        const segs = [];
        let start = null;
        let sum = 0;
        for (let i = 0; i < axis.length; i += 1) {
          const d = axis[i];
          const v = byDate.has(d) ? Number(byDate.get(d)) : null;
          const up = Number.isFinite(v) && v > 0;
          if (up) {
            if (start == null) {
              start = i;
              sum = 0;
            }
            sum += v;
          } else if (start != null) {
            const len = i - start;
            segs.push({ start, len, from: axis[start], to: axis[i - 1], sum: +sum.toFixed(2) });
            start = null;
            sum = 0;
          }
        }
        if (start != null) {
          const len = axis.length - start;
          segs.push({ start, len, from: axis[start], to: axis[axis.length - 1], sum: +sum.toFixed(2) });
        }
        return { name: nm, group: g, segments: segs, stats };
      }).filter(r => r.name);

      const mainlineCandidates = base.filter(r => r.stats.upDays >= MAINLINE_MIN_UP_DAYS && r.stats.cumPct >= MAINLINE_MIN_CUM_PCT && r.stats.maxStreak >= MAINLINE_MIN_STREAK);
      mainlineCandidates.sort((a, b) => (b.stats.cumPct - a.stats.cumPct));
      const mainlineSet = new Set(mainlineCandidates.slice(0, MAINLINE_MAX).map(r => r.name));
      return base.map((r) => ({ ...r, type: mainlineSet.has(r.name) ? '主线' : '题材' }));
    });

    const rotationMatrixGroups = computed(() => {
      const rows = rotationMatrixRows.value || [];
      const order = ['资源', '硬件', '软件', '科技', '医药', '新能源', '未分类'];
      const map = new Map();
      rows.forEach((r) => {
        const g = r.group || '未分类';
        if (!map.has(g)) map.set(g, []);
        map.get(g).push(r);
      });
      const keys = Array.from(map.keys()).sort((a, b) => {
        const ai = order.indexOf(a);
        const bi = order.indexOf(b);
        const av = ai === -1 ? 999 : ai;
        const bv = bi === -1 ? 999 : bi;
        if (av !== bv) return av - bv;
        return String(a).localeCompare(String(b));
      });
      return keys.map(k => ({ group: k, rows: map.get(k) || [] }));
    });

    const setRotationMonthSpan = (v) => {
      const n = Number(v);
      const next = Number.isFinite(n) ? n : 2;
      rotationMonthSpan.value = next;
      localStorage.setItem('rotation_month_span', String(next));
    };

    const renderIntradayWatchRank = (rows) => {
      const list = Array.isArray(rows) ? rows : [];
      const toPct = (v) => {
        if (v == null) return null;
        if (typeof v === 'string') {
          const n = Number(v.replace('%', ''));
          return Number.isFinite(n) ? n : null;
        }
        const n = Number(v);
        return Number.isFinite(n) ? n : null;
      };
      const renderChart = (domId, items, color, align) => {
        const chartDom = document.getElementById(domId);
        if (!chartDom) return;
        const myChart = window.echarts.init(chartDom);
        if (!items.length) {
          myChart.clear();
          return;
        }
        const names = items.map(d => d.name);
        const rawPcts = items.map(d => toPct(d.pct));
        const barPcts = rawPcts.map(v => (Number.isFinite(v) ? Math.abs(+v.toFixed(2)) : 0));
        const maxVal = Math.max(1, ...barPcts);
        const isLeft = align === 'left';
        const labelFormatter = (params) => {
          const item = items[params.dataIndex] || {};
          const name = item.name || '';
          const v = toPct(item.pct);
          const pct = Number.isFinite(v) ? v.toFixed(2) : '-';
          return `${name} ${pct}%`;
        };
        const option = {
          tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
          grid: { left: 0, right: 8, top: 4, bottom: 4, containLabel: false },
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
          dataZoom: [
            { type: 'inside', yAxisIndex: 0, filterMode: 'none' }
          ],
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
      const items = list
        .map((r) => ({ name: r?.name || '', pct: r?.nowPct }))
        .filter(x => x.name && Number.isFinite(Number(x.pct)));
      const downList = items.filter(i => Number(i.pct) < 0).sort((a, b) => Number(a.pct) - Number(b.pct));
      const upList = items.filter(i => Number(i.pct) > 0).sort((a, b) => Number(b.pct) - Number(a.pct));
      renderChart('intraday-watch-down-chart', downList, '#4ade80', 'left');
      renderChart('intraday-watch-up-chart', upList, '#eb5454', 'right');
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
        const res = await fetch(`${apiBase}/api/snapshot/latest?ai=${withAi ? '1' : '0'}`);
        if (!res.ok) throw new Error('bad');
        const data = await res.json();
        const aiChanged = !!(data?.aiBrief || data?.aiText);
        if (data?.aiBrief) aiBrief.value = data.aiBrief;
        if (data?.aiText) aiText.value = data.aiText;
        if (aiChanged && withAi) aiUpdatedAt.value = Date.now();
        if (data?.sentiment) sentiment.value = { ...sentiment.value, ...data.sentiment };
        if (data?.sentiment?.volumeCmp) sentiment.value.volumeCmp = data.sentiment.volumeCmp;
        const arrToday = data?.sentiment?.volumeSeries || [];
        const ydayArr = data?.sentiment?.volumeSeriesYday || [];
        sentiment.value.volumeSeries = arrToday;
        sentiment.value.volumeSeriesYday = ydayArr;
        if (!overviewDailyReady.value) renderVolumeSpark('spark-volume', arrToday, ydayArr);
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
        if (data?.sectors?.bank) sectors.value.bank = { price: data.sectors.bank.price ?? sectors.value.bank?.price ?? null, pct: data.sectors.bank.pct ?? sectors.value.bank?.pct };
        if (data?.sectors?.broker) sectors.value.broker = { price: data.sectors.broker.price ?? sectors.value.broker?.price ?? null, pct: data.sectors.broker.pct ?? sectors.value.broker?.pct };
        if (data?.sectors?.insure) sectors.value.insure = { price: data.sectors.insure.price ?? sectors.value.insure?.price ?? null, pct: data.sectors.insure.pct ?? sectors.value.insure?.pct };
        if (data?.ts) dataTs.value = data.ts;
      } catch (e) { console.error(e); }
    };

    const fetchPrompt = async () => {
      try {
        const res = await fetch(`${apiBase}/api/prompt/stock-daily`);
        if (!res.ok) throw new Error('bad');
        const data = await res.json();
        if (data?.text) promptText.value = data.text;
      } catch (e) { console.error(e); }
    };

    const fetchSectorPrompt = async () => {
      try {
        const res = await fetch(`${apiBase}/api/prompt/sector-analysis`);
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
        const res = await fetch(`${apiBase}/api/ai/debug`, {
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
        const res = await fetch(`${apiBase}/api/ai/sector-debug`, {
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
        const res = await fetch(`${apiBase}/api/minute/${code}`);
        if (!res.ok) throw new Error('bad');
        const data = await res.json();
        const normalized = normalizeMinuteSeries(data);
        const series = normalized.series || [];
        const prevClose = data?.prevClose ?? null;
        minuteCache[el] = { series, day: normalized.day };
        if (series.length) {
          renderSpark(el, series, prevClose);
          const v = deriveFromSeries(series, prevClose);
          const slope = deriveSlope(series);
          const setter = minuteTarget[code];
          if (setter) setter(v, slope);
          const lastTime = data?.latest?.time || series[series.length - 1]?.time;
          const tsRaw = buildTs(normalized.day, lastTime);
          if (tsRaw) {
            const t = Date.parse(tsRaw);
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
        const res = await fetch(`${apiBase}/api/market/breadth`);
        if (!res.ok) return;
        const data = await res.json();
        if (!data) return;

        const container = document.getElementById('market-breadth');
        if (container) container.classList.remove('hidden');

        const up = Number(data?.up || 0);
        const down = Number(data?.down || 0);
        const flat = Number(data?.flat || 0);
        const total = Number(data?.total || (up + down + flat) || 0);

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

    const getStageColor = (stage) => {
      if (!stage) return 'bg-gray-400';
      if (stage.includes('启动') || stage.includes('加速')) return 'bg-red-500';
      if (stage.includes('震荡')) return 'bg-yellow-500';
      if (stage.includes('潜伏')) return 'bg-blue-500';
      if (stage.includes('衰退') || stage.includes('背离')) return 'bg-green-500';
      return 'bg-gray-400';
    };

    const getAdviceColor = (advice) => {
      if (!advice) return 'text-gray-500';
      if (advice.includes('建仓') || advice.includes('试探') || advice.includes('低吸') || advice.includes('积极') || advice.includes('增持')) return 'text-red-600';
      if (advice.includes('持有') || advice.includes('埋伏') || advice.includes('观望')) return 'text-yellow-600';
      if (advice.includes('减仓') || advice.includes('止盈') || advice.includes('清仓')) return 'text-green-600';
      return 'text-gray-500';
    };

    const badgeClass = (kind, val) => {
      const v = String(val || '').trim();
      if (kind === 'resonance') {
        if (val === true || v === '是') return 'bg-green-50 text-green-700 border border-green-200';
        return 'bg-gray-50 text-gray-600 border border-gray-200';
      }
      if (kind === 'seesaw') {
        if (v === '科技强') return 'bg-red-50 text-red-700 border border-red-200';
        if (v === '资源强') return 'bg-yellow-50 text-yellow-700 border border-yellow-200';
        return 'bg-gray-50 text-gray-600 border border-gray-200';
      }
      if (kind === 'diffusion') {
        if (v === '硬件领先') return 'bg-blue-50 text-blue-700 border border-blue-200';
        if (v === '软件补涨') return 'bg-purple-50 text-purple-700 border border-purple-200';
        return 'bg-gray-50 text-gray-600 border border-gray-200';
      }
      if (kind === 'leader') {
        if (!v || v === '-') return 'bg-gray-50 text-gray-600 border border-gray-200';
        return 'bg-indigo-50 text-indigo-700 border border-indigo-200';
      }
      if (kind === 'risk') {
        if (v === '恐慌出逃' || v === '资金撤退' || v === '加速赶顶' || v === '向下') return 'bg-rose-50 text-rose-700 border border-rose-200';
        if (v === '放量') return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
        return 'bg-gray-50 text-gray-600 border border-gray-200';
      }
      return 'bg-gray-50 text-gray-600 border border-gray-200';
    };

    const fmtProb = (v) => {
      const n = Number(v);
      if (!Number.isFinite(n)) return '-';
      return `${Math.round(n)}%`;
    };

    const getImpact = (item) => {
      const tags = Array.isArray(item?.tags) ? item.tags : [];
      if (tags.includes('利好')) return '利好';
      if (tags.includes('利空')) return '利空';
      return '中性';
    };

    const getImpactClass = (impact) => {
      if (impact === '利好') return 'bg-red-50 text-red-600 border-red-200';
      if (impact === '利空') return 'bg-green-50 text-green-600 border-green-200';
      return 'bg-gray-50 text-gray-600 border-gray-200';
    };

    const importanceStars = (val) => {
      const n = Math.min(5, Math.max(1, Number(val) || 1));
      return '★'.repeat(n);
    };

    const buildMockNews = () => ([
      {
        news_id: '9a0d32b3f4a1',
        title: '政策加码算力基础设施，产业链订单释放',
        content: '多地发布算力基础设施规划，运营商与设备厂订单回暖。',
        summary: '政策驱动算力基建加速，产业链景气度提升。',
        source: '财联社',
        source_url: 'https://example.com/news/1',
        publish_time: '2026-02-23 15:30:00',
        crawl_time: '2026-02-23 23:24:00',
        importance: 5,
        tags: ['A股', '宏观', '政策', '利好', '云计算', '通信设备'],
        related_stocks: ['600050.SH', '000938.SZ'],
        status: 'new'
      },
      {
        news_id: '7c3e1a8b2f91',
        title: '新能源车补贴细则落地，部分车型门槛提高',
        content: '补贴标准更新，续航与能耗门槛提升，部分车型或受影响。',
        summary: '补贴细则收紧，短期销量存在波动。',
        source: '东方财富',
        source_url: 'https://example.com/news/2',
        publish_time: '2026-02-23 14:10:00',
        crawl_time: '2026-02-23 23:22:00',
        importance: 4,
        tags: ['A股', '宏观', '新能源', '利空'],
        related_stocks: ['300750.SZ', '002594.SZ'],
        status: 'new'
      },
      {
        news_id: '3f2b9c1d5e8a',
        title: '半导体设备国产替代提速，龙头扩产',
        content: '多家半导体设备厂商宣布扩产与产线升级。',
        summary: '国产替代进程加快，设备环节景气度抬升。',
        source: '财联社',
        source_url: 'https://example.com/news/3',
        publish_time: '2026-02-23 13:20:00',
        crawl_time: '2026-02-23 23:20:00',
        importance: 5,
        tags: ['A股', '关注行业', '半导体', '利好'],
        related_stocks: ['688981.SH', '300223.SZ'],
        status: 'new'
      },
      {
        news_id: '1d8f7a3c9b02',
        title: '有色金属价格波动加剧，库存回升',
        content: '部分金属价格震荡，库存小幅回升。',
        summary: '供需边际变化，短期价格弹性减弱。',
        source: '东方财富',
        source_url: 'https://example.com/news/4',
        publish_time: '2026-02-23 12:05:00',
        crawl_time: '2026-02-23 23:10:00',
        importance: 3,
        tags: ['A股', '关注行业', '有色金属', '中性'],
        related_stocks: ['600219.SH'],
        status: 'processed'
      },
      {
        news_id: '5a9c2e1b7d33',
        title: '地缘局势扰动国际油价，避险情绪升温',
        content: '中东局势变化引发油价波动，市场风险偏好下降。',
        summary: '地缘风险提升，能源与避险资产关注度上升。',
        source: '财联社',
        source_url: 'https://example.com/news/7',
        publish_time: '2026-02-23 11:10:00',
        crawl_time: '2026-02-23 22:40:00',
        importance: 4,
        tags: ['地缘', '海外', '利空', '能源'],
        related_stocks: ['600028.SH'],
        status: 'new'
      },
      {
        news_id: '8e6b1c2d0a55',
        title: '医药集采范围扩大，部分品种降价',
        content: '集采品种扩围，部分药品降价明显。',
        summary: '医药板块短期承压，需关注结构性机会。',
        source: '财联社',
        source_url: 'https://example.com/news/5',
        publish_time: '2026-02-23 11:40:00',
        crawl_time: '2026-02-23 23:00:00',
        importance: 4,
        tags: ['A股', '关注行业', '医药', '利空'],
        related_stocks: ['600276.SH'],
        status: 'new'
      },
      {
        news_id: '6b3a9e1f0c77',
        title: '电力需求高位运行，煤电长协价格稳定',
        content: '电力需求维持高位，煤电长协价格保持稳定。',
        summary: '供需平衡改善，电力盈利预期改善。',
        source: '东方财富',
        source_url: 'https://example.com/news/6',
        publish_time: '2026-02-23 10:15:00',
        crawl_time: '2026-02-23 22:50:00',
        importance: 3,
        tags: ['A股', '关注行业', '电力', '利好', '煤炭'],
        related_stocks: ['600900.SH', '601088.SH'],
        status: 'archived'
      }
    ]);

    const loadNews = async (force = false) => {
      const nowTs = Date.now();
      if (!force && newsTs.value && nowTs - newsTs.value < 5 * 60 * 1000) return;
      newsLoading.value = true;
      try {
        newsList.value = buildMockNews();
        newsTs.value = nowTs;
      } finally {
        newsLoading.value = false;
      }
    };

    const newsItems = computed(() => newsList.value || []);
    const heatmapItems = computed(() => {
      const base = watchList.value && watchList.value.length ? watchList.value : [];
      const map = new Map();
      base.forEach(s => map.set(s, 0));
      (newsList.value || []).forEach((item) => {
        const tags = Array.isArray(item?.tags) ? item.tags : [];
        tags.forEach((t) => {
          if (map.has(t)) map.set(t, map.get(t) + 1);
        });
      });
      return Array.from(map.entries())
        .map(([name, count]) => ({ name, count }))
        .sort((a, b) => b.count - a.count);
    });
    const heatmapMax = computed(() => {
      const vals = heatmapItems.value.map(i => i.count);
      return vals.length ? Math.max(...vals, 1) : 1;
    });
    const macroTags = ['宏观', '政策', '数据', '央行', '货币', '经济', '财政', '利率', '通胀'];
    const geoTags = ['地缘', '海外', '国际', '战争', '中东', '俄乌', '巴以', '美联储'];
    const hasAnyTag = (tags, list) => list.some(t => tags.includes(t));
    const classifyNews = (item) => {
      const tags = Array.isArray(item?.tags) ? item.tags : [];
      const focusTags = watchList.value && watchList.value.length ? watchList.value : [];
      if (focusTags.length && hasAnyTag(tags, focusTags)) return 'focus';
      if (hasAnyTag(tags, geoTags)) return 'geo';
      if (hasAnyTag(tags, macroTags)) return 'macro';
      return 'macro';
    };
    const sortNews = (arr) => arr.slice().sort((a, b) => {
      const ai = Number(a?.importance) || 1;
      const bi = Number(b?.importance) || 1;
      if (ai !== bi) return bi - ai;
      const at = a?.publish_time || '';
      const bt = b?.publish_time || '';
      return bt.localeCompare(at);
    });
    const macroNews = computed(() => sortNews(newsItems.value.filter(i => classifyNews(i) === 'macro')));
    const geoNews = computed(() => sortNews(newsItems.value.filter(i => classifyNews(i) === 'geo')));
    const focusNews = computed(() => sortNews(newsItems.value.filter(i => classifyNews(i) === 'focus')));

    const changeDays = (d) => {
      currentDays.value = d;
      const histRes = sectorHistoryPayload.value;
      if (histRes) {
        renderSectorHistory(histRes);
        if (histRes?.indicators) watchIndicators.value = histRes.indicators || {};
        if (Array.isArray(histRes?.watch)) watchList.value = histRes.watch;
      }
      if (sectorLifecyclePayload.value) renderSectorLifecycle(sectorLifecyclePayload.value);
    };

    const normalizeSectorList = (list) => {
      const out = [];
      const seen = new Set();
      (Array.isArray(list) ? list : []).forEach((s) => {
        const v = String(s || '').trim();
        if (!v || seen.has(v)) return;
        seen.add(v);
        out.push(v);
      });
      return out;
    };

    const buildSectorQuery = () => {
      const list = (sectorInput.value || '').split(',').map(s => s.trim()).filter(Boolean);
      const uniq = Array.from(new Set(list));
      if (!uniq.length) return '';
      return 'sectors=' + encodeURIComponent(uniq.join(','));
    };

    const updateSectorWatch = async () => {
      const list = (sectorInput.value || '').split(',').map(s => s.trim()).filter(Boolean);
      const uniq = normalizeSectorList(list);
      const next = uniq.join(',');
      sectorInput.value = next;
      localStorage.setItem('sector_input', next);
      try {
        await fetch(`${apiBase}/api/sector/watch-list`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ watch_list: uniq })
        });
      } catch (e) { console.error(e); }
      watchList.value = uniq;
      await fetchSectorData();
    };

    const fetchSectorProfile = async () => {
      try {
        const res = await fetch(`${apiBase}/api/sector/profile`);
        if (!res.ok) throw new Error('bad');
        const data = await res.json();
        profileGroups.value = data?.groups || {};
        profileUpdatedAt.value = data?.updated_at || '';
      } catch (e) { console.error(e); }
    };

    const saveSectorProfile = async () => {
      try {
        const res = await fetch(`${apiBase}/api/sector/profile`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ groups: profileGroups.value || {} })
        });
        if (!res.ok) throw new Error('bad');
        const data = await res.json();
        profileGroups.value = data?.groups || {};
        profileUpdatedAt.value = data?.updated_at || '';
      } catch (e) { console.error(e); }
    };

    const openSectorManager = async () => {
      showSectorManager.value = true;
      await fetchWatchList();
      await fetchSectorProfile();
    };

    const closeSectorManager = () => {
      showSectorManager.value = false;
      manageSectorName.value = '';
    };

    const addWatchSector = async () => {
      const name = String(manageSectorName.value || '').trim();
      if (!name) return;
      const list = normalizeSectorList([...(watchList.value || []), name]);
      try {
        const res = await fetch(`${apiBase}/api/sector/watch-list`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ watch_list: list })
        });
        if (!res.ok) throw new Error('bad');
        const data = await res.json();
        const next = normalizeSectorList(data?.watch_list || list);
        watchList.value = next;
        const joined = next.join(',');
        sectorInput.value = joined;
        localStorage.setItem('sector_input', joined);
      } catch (e) { console.error(e); }
      manageSectorName.value = '';
    };

    const fetchRotationSequence = async () => {
      const nowTs = Date.now();
      if (rotationSequenceLoading.value) return;
      if (rotationSequencePayload.value && rotationSequenceTs.value && nowTs - rotationSequenceTs.value < rotationSequenceCacheMs) return;
      rotationSequenceLoading.value = true;
      try {
        const query = buildSectorQuery();
        const url = `${apiBase}/api/sector/rotation/sequence?days=${rotationSequenceDays.value}${query ? '&' + query : ''}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error('bad');
        const data = await res.json();
        rotationSequencePayload.value = data || null;
        rotationSequenceTs.value = nowTs;
      } catch (e) { console.error(e); }
      rotationSequenceLoading.value = false;
    };

    const warmupSectorCaches = async () => {
      const nowTs = Date.now();
      if (warmupTs.value && nowTs - warmupTs.value < warmupCacheMs) return;
      warmupTs.value = nowTs;
      try {
        const query = buildSectorQuery();
        const days = Math.max(60, currentDays.value || 0);
        const url = `${apiBase}/api/sector/warmup?days=${days}${query ? '&' + query : ''}`;
        fetch(url).catch(() => {});
      } catch (e) { console.error(e); }
    };

    const removeWatchSector = async (name) => {
      const list = normalizeSectorList((watchList.value || []).filter((s) => s !== name));
      try {
        const res = await fetch(`${apiBase}/api/sector/watch-list`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ watch_list: list })
        });
        if (!res.ok) throw new Error('bad');
        const data = await res.json();
        const next = normalizeSectorList(data?.watch_list || list);
        watchList.value = next;
        const joined = next.join(',');
        sectorInput.value = joined;
        localStorage.setItem('sector_input', joined);
      } catch (e) { console.error(e); }
      const groups = { ...(profileGroups.value || {}) };
      if (groups[name]) {
        delete groups[name];
        profileGroups.value = groups;
        await saveSectorProfile();
      }
    };

    const fetchRotationIntraday = async () => {
      const nowTs = Date.now();
      const cacheMs = isMarketOpen() ? intradayCacheMs : intradayIdleCacheMs;
      if (sectorIntradayPayload.value && intradayTs.value && nowTs - intradayTs.value < cacheMs) return;
      try {
        const query = buildSectorQuery();
        const intradayUrl = `${apiBase}/api/sector/rotation/intraday?view=${intradayView.value === 'detail' ? 'detail' : 'summary'}${query ? '&' + query : ''}`;
        const res = await fetch(intradayUrl);
        if (!res.ok) throw new Error('bad');
        const intradayRes = await res.json();
        sectorIntradayPayload.value = intradayRes || null;
        intradayTs.value = nowTs;
        if (intradayView.value === 'detail') renderIntradayWatchRank(watchIntradayRows.value);
      } catch (e) {
        sectorIntradayPayload.value = null;
      }
    };

    const setIntradayView = async (v) => {
      intradayView.value = v === 'detail' ? 'detail' : 'summary';
      await fetchRotationIntraday();
      if (intradayView.value === 'detail') renderIntradayWatchRank(watchIntradayRows.value);
    };

    const fetchSectorData = async (force = false) => {
      const nowTs = Date.now();
      const refreshMs = isMarketOpen() ? 60 * 1000 : 5 * 60 * 1000;
      if (!force && sectorTs.value && nowTs - sectorTs.value < refreshMs) return;
      sectorLoading.value = true;
      try {
        warmupSectorCaches();
        const query = buildSectorQuery();
        const days = Math.max(60, currentDays.value || 0);
        const realtimeHist = isMarketOpen();
        const historyUrl = `${apiBase}/api/sector/history?rt=${realtimeHist ? 1 : 0}&days=${days}${query ? '&' + query : ''}`;
        const lifecycleUrl = `${apiBase}/api/sector/lifecycle?rt=0&days=${days}${query ? '&' + query : ''}`;
        const rotationUrl = `${apiBase}/api/sector/rotation?rt=0&days=${Math.max(90, days)}${query ? '&' + query : ''}`;
        const signalsReq = fetch(`${apiBase}/api/signals`)
          .then(r => r.json())
          .then((data) => {
            const rows = Array.isArray(data) ? data : (Array.isArray(data?.signals) ? data.signals : []);
            const map = {};
            (rows || []).forEach((it) => {
              const sector = String(it?.sector || '').trim();
              const signal = String(it?.signal || '').trim();
              if (sector && signal) map[sector] = signal;
            });
            signalsMap.value = map;
            return data;
          })
          .catch(() => ({}));
        const panicReq = fetch(`${apiBase}/api/panic`)
          .then(r => r.json())
          .then((data) => {
            panicPayload.value = data || null;
            return data;
          })
          .catch(() => null);
        const rankReq = fetch(`${apiBase}/api/sector/rank`)
          .then(r => r.json())
          .then((rankRes) => {
            renderSectorRank(rankRes);
            return rankRes;
          });
        const histReq = fetch(historyUrl)
          .then(r => r.json())
          .then((histRes) => {
            renderSectorHistory(histRes);
            if (histRes?.indicators) watchIndicators.value = histRes.indicators || {};
            if (Array.isArray(histRes?.watch)) watchList.value = histRes.watch;
            sectorHistoryPayload.value = histRes || null;
            return histRes;
          });
        const aiReq = fetch(`${apiBase}/api/ai/sector-analysis`)
          .then(r => r.json())
          .catch(() => ({}));
        const rotationReq = fetch(rotationUrl)
          .then(r => r.json())
          .then((rotRes) => {
            sectorRotationPayload.value = rotRes || null;
            return rotRes;
          })
          .catch(() => {
            sectorRotationPayload.value = null;
            return null;
          });
        let lifecyclePayload = null;
        const lifecycleReq = fetch(lifecycleUrl)
          .then(r => r.json())
          .then((lifecycleRes) => {
            lifecyclePayload = lifecycleRes || {};
            renderSectorLifecycle(lifecycleRes);
            sectorLifecyclePayload.value = lifecycleRes || null;
            return lifecycleRes;
          })
          .catch(() => ({}));
        const [rankRes, histRes, aiRes, rotationRes] = await Promise.all([rankReq, histReq, aiReq, rotationReq]);
        await Promise.all([signalsReq, panicReq]);
        await fetchRotationIntraday();
        fetchRotationSequence();
        const fallback = {
          seesaw: buildSeesawAi(histRes || {}),
          streak: buildStreakAi(rankRes || {}, histRes || {})
        };
        const parsed = parseSectorAiText(aiRes?.text || '');
        marketAi.value = {
          seesaw: parsed.seesaw || fallback.seesaw,
          streak: parsed.streak || fallback.streak
        };
        await lifecycleReq;
        localStorage.setItem(sectorCacheKey, JSON.stringify({
          ts: nowTs,
          rank: rankRes || {},
          history: histRes || {},
          lifecycle: lifecyclePayload || null,
          rotation: rotationRes || null,
          ai: aiRes || {}
        }));
        sectorTs.value = nowTs;
      } catch (e) {
        console.error("Sector module init failed", e);
        marketAi.value = { seesaw: '数据加载失败', streak: '数据加载失败' };
        sectorRotationPayload.value = null;
      } finally {
        sectorLoading.value = false;
      }
    };

    const fetchWatchList = async () => {
      try {
        const res = await fetch(`${apiBase}/api/sector/watch-list`);
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
      const days = currentDays.value || 60; // Frontend Slicing Limit
      
      Object.keys(data.history).forEach(name => {
        let hist = data.history[name];
        if (!hist || hist.length === 0) return;
        
        // Frontend Slicing Logic:
        // If backend returns more data than needed, slice it here to satisfy user request without backend changes.
        if (hist.length > days) {
          hist = hist.slice(-days);
        }
        
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
        title: { text: `${days}日相对走势 (归一化)`, left: 'center', textStyle: { fontSize: 12 } },
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

    const renderSectorLifecycle = (data) => {
      lifecycleItems.value = Array.isArray(data?.items) ? data.items : [];
    };

    const setRotationFilter = (v) => {
      rotationFilter.value = v || '全部';
    };

    const rotationKey = (m, idx) => {
      const name = String(m?.['板块名称'] || m?.name || '').trim();
      return name || `idx-${idx}`;
    };

    const isRotationExpanded = (m, idx) => {
      const key = rotationKey(m, idx);
      return !!rotationExpanded.value[key];
    };

    const toggleRotationExpand = (m, idx) => {
      const key = rotationKey(m, idx);
      rotationExpanded.value = {
        ...rotationExpanded.value,
        [key]: !rotationExpanded.value[key]
      };
    };

    const buildRotationMarkdown = () => {
      const data = sectorRotationPayload.value;
      if (!data) return '';
      const day = data.day || '';
      const rotation = data.rotation || {};
      const lines = [];
      lines.push(`# 主线&轮动盘后报告 ${day}`);
      lines.push('');
      lines.push(`- 领先：${rotation.leader || '-'}`);
      lines.push(`- 跷跷板：${rotation.seesaw || '-'}`);
      lines.push(`- 扩散：${rotation.diffusion || '-'}`);
      lines.push(`- 共振：${rotation.resonance ? '是' : '否'}`);
      lines.push('');
      lines.push('## 主线列表');
      const list = data.mainline || [];
      if (!list.length) {
        lines.push('- 暂无');
        return lines.join('\n');
      }
      list.forEach((m, idx) => {
        const name = m?.['板块名称'] || `主线${idx + 1}`;
        lines.push(`### ${idx + 1}. ${name}`);
        lines.push(`- 动能：${m?.['动能'] || '-'}`);
        lines.push(`- 资金行为：${m?.['资金行为'] || '-'}`);
        lines.push(`- 操作建议：${m?.['操作建议'] || '-'}`);
        if (Array.isArray(m?.groups) && m.groups.length) {
          lines.push(`- 组别：${m.groups.join(' / ')}`);
        }
        const p3 = m?.prob_view?.['3d'] || {};
        const p5 = m?.prob_view?.['5d'] || {};
        lines.push(`- 概率3日：涨${p3.up_prob ?? '-'} 震${p3.range_prob ?? '-'} 回撤${p3.drawdown_risk ?? '-'}`);
        lines.push(`- 概率5日：涨${p5.up_prob ?? '-'} 震${p5.range_prob ?? '-'} 回撤${p5.drawdown_risk ?? '-'}`);
        const exec = m?.exec_view || {};
        const pos = exec.position || {};
        lines.push(`- 执行：${exec.action || '-'} 仓位${pos.min ?? '-'}-${pos.max ?? '-'} 偏好${exec.horizon_prefer === '3d' ? '3日' : '5日'}`);
        const triggers = m?.triggers || {};
        lines.push(`- 确认：${triggers.confirm || '-'}`);
        lines.push(`- 否决：${triggers.invalidate || '-'}`);
        const news = m?.news_view || {};
        if (news?.risk_tags?.length) lines.push(`- 新闻风险：${news.risk_tags.join(' / ')}`);
        if (news?.top_titles?.length) lines.push(`- 相关新闻：${news.top_titles.join('；')}`);
        if (m?.['归因说明']) lines.push(`- 归因：${m['归因说明']}`);
        lines.push('');
      });
      return lines.join('\n');
    };

    const exportRotationJson = () => {
      const data = sectorRotationPayload.value;
      if (!data) return;
      const json = JSON.stringify(data, null, 2);
      const blob = new Blob([json], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `sector-rotation-${data.day || 'latest'}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 500);
    };

    const copyRotationMarkdown = async () => {
      const text = buildRotationMarkdown();
      if (!text) return;
      if (navigator?.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(text);
          return;
        } catch (e) {
          return;
        }
      }
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    };

    const fetchOverviewHistory = async (force) => {
      const nowTs = Date.now();
      if (!force && overviewHistoryTs.value && nowTs - overviewHistoryTs.value < 30 * 60 * 1000) return;
      try {
        const res = await fetch(`${apiBase}/api/overview/history`);
        if (!res.ok) throw new Error('bad');
        const data = await res.json();
        if (!data?.series) return;
        const seriesValues = Object.values(data.series || {});
        const hasDailySeries = seriesValues.some(arr => Array.isArray(arr) && arr.length);
        const hasDailyVolume = Array.isArray(data.volume) && data.volume.length;
        if (!hasDailySeries && !hasDailyVolume) return;
        overviewHistoryTs.value = nowTs;
        overviewHistoryDay.value = data?.day || '';
        overviewDailyReady.value = true;
        Object.entries(dailyMap).forEach(([el, key]) => {
          const arr = data.series[key] || [];
          const len = Array.isArray(arr) ? arr.length : 0;
          dailySeriesLen[key] = len;
          const cached = minuteCache[el];
          if (cached?.series?.length) return;
          if (lockIndexSparks && indexSparkEls.has(el)) return;
          if (len >= minDailyPoints) renderDailySpark(el, arr);
        });
        if (hasDailyVolume) renderDailyVolumeSpark('spark-volume', data.volume || []);
      } catch (e) { console.error(e); }
    };

    const refreshAll = async () => {
      await fetchSnapshot(false);
      await refreshMinuteAll();
      await fetchOverviewHistory(false);
      await fetchBreadth();
      if (activeTab.value === 'market') await fetchSectorData(false);
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
    
    const selectTab = async (tab) => {
      activeTab.value = tab;
      if (tab === 'market') await fetchSectorData(true);
      if (tab === 'news') await loadNews(false);
    };

    const init = async () => {
      try {
        const cached = localStorage.getItem(sectorCacheKey);
        if (cached) {
          const data = JSON.parse(cached);
          if (data?.rank) renderSectorRank(data.rank);
          if (data?.history) {
            renderSectorHistory(data.history);
            if (data.history?.indicators) watchIndicators.value = data.history.indicators || {};
            if (Array.isArray(data.history?.watch)) watchList.value = data.history.watch;
          }
          if (data?.lifecycle) renderSectorLifecycle(data.lifecycle);
          if (data?.rotation) sectorRotationPayload.value = data.rotation || null;
          if (data?.ai) {
            const parsed = parseSectorAiText(data.ai?.text || '');
            marketAi.value = {
              seesaw: parsed.seesaw || marketAi.value.seesaw,
              streak: parsed.streak || marketAi.value.streak
            };
          }
          if (Number.isFinite(data?.ts)) sectorTs.value = data.ts;
        }
      } catch (e) { console.error(e); }
      fetchPrompt();
      fetchSectorPrompt();
      await fetchWatchList();
      await loadNews(false);
      await refreshAll();
      await refreshAi(false);
    };
    init();
    setInterval(refreshAll, 15000);
    setInterval(() => refreshAi(false), 30 * 60 * 1000);

    return { activeTab, aiBrief, aiUpdatedAt, aiSections, marketAi, promptText, promptOutput, promptLoading, promptError, runPromptDebug, sectorPromptText, sectorPromptOutput, sectorPromptLoading, sectorPromptError, runSectorPromptDebug, refreshAi, market, bonds, extra, sectors, sentiment, pctColor, fmtPct, fmtVolumeCmp, fmtHeatDelta, rotationMonthSpan, setRotationMonthSpan, rotationMatrixAxis, rotationMatrixMonths, rotationMatrixGroups, refreshAll, dataTs, fmtTime, sectorInput, updateSectorWatch, watchList, watchIndicators, lastIndicator, currentDays, lifecycleItems, sectorRotationPayload, sectorIntradayPayload, sectorLoading, changeDays, getStageColor, getAdviceColor, badgeClass, fmtProb, selectTab, newsItems, newsLoading, heatmapItems, heatmapMax, getImpact, getImpactClass, importanceStars, loadNews, macroNews, geoNews, focusNews, rotationFilters, rotationFilter, rotationMainline, setRotationFilter, toggleRotationExpand, isRotationExpanded, exportRotationJson, copyRotationMarkdown, watchIntradayRows, rotationTopGroups, intradayBars, intradaySignal, intradayReason, intradayMax, intradayView, setIntradayView, rotationSequencePayload, rotationSequenceDays, fetchRotationSequence, riskSummary, panicPayload, showSectorManager, profileGroups, profileUpdatedAt, manageSectorName, sectorGroupOptions, openSectorManager, closeSectorManager, addWatchSector, removeWatchSector, saveSectorProfile };
  }
}).mount('#app');
