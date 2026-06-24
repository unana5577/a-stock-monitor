const { createApp, ref, reactive, computed, watch, onMounted, onUnmounted } = Vue;

const STAGE_TARGET = { '主升': 0.80, '启动': 0.30, '震荡': 0.00, '下跌': 0.00, '防守': 0.00 };
const RETRACE_TARGET = { '主升': 0.80, '启动': 0.30, '震荡': 0.00, '下跌': 0.00, '防守': 0.00 };
const STAGE_STOP  = { '主升': 0.90, '震荡': 0.92, '启动': 0.95, '下跌': 0.92, '防守': 1.0 };

const SIM_KEY = 'm1_sim_account_v1';

const fmtCny = (val) => {
  const n = Number(val);
  if (!Number.isFinite(n)) return '-';
  const sign = n < 0 ? '-' : '';
  return sign + Math.abs(n).toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
};

const pad2 = (n) => String(n).padStart(2, '0');
const nowTs = () => {
  const d = new Date();
  return `${d.getFullYear()}-${pad2(d.getMonth()+1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
};

const fmtStopPrice = (stage, price, avgPrice) => {
  const st = stage || '震荡';
  const mult = STAGE_STOP[st] || 0.92;
  if (mult >= 1.0) return '—';
  const ref = avgPrice > 0 ? avgPrice : price;
  if (!ref) return '—';
  return '¥' + (ref * mult).toFixed(3);
};

const stageTriggers = (s) => {
  const stage = s.stage || '';
  const parts = [];
  if (stage === '防守') {
    parts.push('空头排列 MA20<MA60');
    if (s.vol_ratio != null && s.vol_ratio < 0.8) parts.push('缩量');
    else if (s.amount_trend && s.amount_trend !== '量能持平') parts.push(s.amount_trend);
  } else if (stage === '主升') {
    parts.push('多头排列');
    if (s.ma20_slope != null && s.ma20_slope > 0) parts.push('不创新低');
    if (s.amount_trend && s.amount_trend !== '量能持平') parts.push(s.amount_trend);
  } else if (stage === '启动') {
    parts.push('站上MA20 · 斜率转正');
    if (s.vol_ratio != null && s.vol_ratio > 1.2) parts.push('放量突破');
    else if (s.amount_trend) parts.push(s.amount_trend);
  } else if (stage === '下跌') {
    parts.push('跌破MA20 · 斜率转负');
    if (s.vol_ratio != null && s.vol_ratio < 0.8) parts.push('缩量');
  } else if (stage === '震荡') {
    if (s.ma20 && s.close) {
      const pct = ((s.close - s.ma20) / s.ma20 * 100);
      parts.push('横盘 MA20' + (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%');
    }
    if (s.ma20_slope != null && Math.abs(s.ma20_slope * 100) < 0.3) parts.push('斜率走平');
  }
  return parts.join(' · ') || '—';
};

createApp({
  setup() {

    const stageMap = ref({});
    const livePriceCache = ref({});

    const fetchLivePrices = async () => {
      const posSyms = Object.keys(simState.value.positions || {});
      const missing = posSyms.filter(s => !(stageMap.value || {})[s]?.minute_price);
      if (!missing.length) return;
      for (const sym of missing) {
        try {
          const r = await fetch(`/api/trade/quote?symbol=${sym}`);
          const d = await r.json();
          if (d.ok) {
            livePriceCache.value = { ...livePriceCache.value, [sym]: { price: d.price, pct: d.pct, name: d.name } };
            if (d.name && !symbolNames.value[sym]) {
              symbolNames.value = { ...symbolNames.value, [sym]: d.name };
            }
          }
        } catch (e) { /* ignore */ }
      }
    };
    const day = ref('--');
    const error = ref('');
    const autoRefresh = ref(true);
    const refreshSec = ref(30);
    let timer = null;

    const etfSymbols = ref([]);
    const symbolNames = ref({});
    const etfCategoryMap = ref({});

    const entryTiersMap = ref({});

    const syncMapsFromApi = (apiEtfs) => {
      const newSymbols = [];
      const newNames = {};
      const newCategory = {};
      Object.entries(apiEtfs).forEach(([key, info]) => {
        let code, name;
        if (info && info.code && /^(sh|sz)\d{6}$/i.test(info.code)) {
          // old format: {name: {code, category, ...}}
          code = info.code; name = key;
        } else if (info && /^(sh|sz)\d{6}$/i.test(key)) {
          // new format: {code: {api_name, category, ...}}
          code = key; name = info.api_name || key;
        } else {
          return;
        }
        if (info.hidden) return;
        newSymbols.push(code);
        newNames[code] = name;
        newCategory[code] = info.category;
      });
      if (newSymbols.length) {
        etfSymbols.value = newSymbols;
        symbolNames.value = newNames;
        etfCategoryMap.value = newCategory;
      }
    };

    const fetchEtfConfig = async () => {
      try {
        const res = await fetch('/api/sector/manage');
        const json = await res.json();
        if (json && json.ok && json.etfs) {
          syncMapsFromApi(json.etfs);
        }
      } catch (e) { /* 使用默认值 */ }
      fetchEntryTiers();
    };

    const fetchEntryTiers = async () => {
      try {
        const res = await fetch('/api/trade/entry_tiers');
        const json = await res.json();
        if (json && json.ok && json.tiers) {
          entryTiersMap.value = json.tiers;
        }
      } catch (e) { /* keep previous */ }
    };

    async function fetchStageState() {
      try {
        const r = await fetch('/api/trade/stage_snapshot');
        const json = await r.json();
        if (json.ok && json.data) {
          stageMap.value = json.data.stages || {};
          day.value = json.data.day;
          error.value = '';
          fetchLivePrices();
        } else {
          error.value = json.error || '加载失败';
        }
      } catch (e) {
        error.value = e.message;
      }
    }

    function toggleAutoRefresh() {
      autoRefresh.value = !autoRefresh.value;
      if (autoRefresh.value) {
        fetchStageState();
        timer = setInterval(fetchStageState, refreshSec.value * 1000);
      } else {
        clearInterval(timer);
        timer = null;
      }
    }

    const sortedStageEntries = computed(() => {
      const entries = Object.entries(stageMap.value || {});
      const order = { '主升': 0, '启动': 1, '震荡': 2, '下跌': 3, '防守': 4 };
      entries.sort((a, b) => (order[a[1].stage] || 9) - (order[b[1].stage] || 9));
      return entries.map(([sym, s]) => ({ sym, s }));
    });

    const hiddenEtfs = ref(new Set());
    try {
      const saved = JSON.parse(localStorage.getItem('trade_hidden_etfs') || '[]');
      if (Array.isArray(saved)) hiddenEtfs.value = new Set(saved);
    } catch (e) { /* ignore */ }

    const manageOpen = ref(false);
    const toggleManage = () => { manageOpen.value = !manageOpen.value; };
    const toggleEtfHidden = (code) => {
      if (hiddenEtfs.value.has(code)) {
        hiddenEtfs.value.delete(code);
      } else {
        hiddenEtfs.value.add(code);
      }
      hiddenEtfs.value = new Set(hiddenEtfs.value);
      localStorage.setItem('trade_hidden_etfs', JSON.stringify(Array.from(hiddenEtfs.value)));
    };
    const isEtfVisible = (code) => !hiddenEtfs.value.has(code);

    const simConfig = ref({
      initialCash: Number(localStorage.getItem('sim_initial_cash') || 100000)
    });

    const simState = ref({
      cash: 0,
      positions: {},
      trades: []
    });

    const suggestionOverrides = ref({});
    const selectedSuggestions = ref({});
    const tradeExecutedToday = ref({});
    const tradeConfirmOpen = ref(false);
    const tradeConfirmItems = ref([]);
    const tradeConfirmError = ref('');
    const tradeBottomTab = ref('positions');

    const backfillToast = reactive({ show: false, name: '', code: '', status: 'requesting' });

    const registerEtfViaApi = async (code) => {
      backfillToast.name = code;
      backfillToast.code = code;
      backfillToast.status = 'requesting';
      backfillToast.show = true;
      try {
        const res = await fetch('/api/sector/manage', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code, category: '科技', sub_category: '硬件' })
        });
        const json = await res.json();
        if (json && json.ok) {
          await fetchEtfConfig();
          backfillToast.name = symbolNames.value[code] || code;
          backfillToast.status = 'done';
          // 确保 symbolNames 已更新
          if (!symbolNames.value[code]) symbolNames.value = { ...symbolNames.value, [code]: backfillToast.name };
          fetchStageState();
        } else {
          backfillToast.status = 'failed';
        }
        return json;
      } catch (e) {
        backfillToast.status = 'failed';
        return { ok: false, error: e.message };
      } finally {
        setTimeout(() => { backfillToast.show = false; }, 4000);
      }
    };

    const closeBackfillToast = () => { backfillToast.show = false; };

    const capitalModalOpen = ref(false);
    const capitalModalValue = ref(0);
    const openCapitalModal = () => {
      capitalModalValue.value = Math.round(simMetrics.value.equity || simConfig.value.initialCash || 0);
      capitalModalOpen.value = true;
    };
    const closeCapitalModal = () => { capitalModalOpen.value = false; };
    const confirmCapitalModal = () => {
      const val = Math.max(0, Number(capitalModalValue.value || 0));
      if (!Number.isFinite(val)) return;
      simConfig.value.initialCash = val;
      simState.value.cash = Math.max(0, val - (simMetrics.value.positionsValue || 0));
      capitalModalOpen.value = false;
      saveSimLocal();
    };

    const posEditOpen = ref(false);
    const posEditIsAdd = ref(false);
    const posEditSym = ref('');
    const posEditShares = ref(0);
    const posEditPrice = ref(0);
    const posEditCode = ref('');
    const posEditName = ref('');
    const posEditNameLoading = ref(false);
    const onPosEditCodeInput = () => {
      let raw = posEditCode.value.trim();
      if (!raw) { posEditSym.value = ''; posEditName.value = ''; posEditNameLoading.value = false; return; }
      // 自动补 sh/sz 前缀
      if (/^\d{6}$/.test(raw)) {
        raw = raw[0] === '0' || raw[0] === '3' ? 'sz' + raw : 'sh' + raw;
        posEditCode.value = raw;
      }
      if (/^(sh|sz)\d{6}$/i.test(raw)) {
        const lc = raw.toLowerCase();
        posEditSym.value = lc;
        // 自动从行情接口拉中文名
        if (!symbolNames.value[lc]) {
          posEditNameLoading.value = true;
          fetch(`/api/trade/quote?symbol=${lc}`).then(r => r.json()).then(d => {
            if (d.ok && d.name) {
              posEditName.value = d.name;
              symbolNames.value = { ...symbolNames.value, [lc]: d.name };
            }
          }).catch(() => {}).finally(() => { posEditNameLoading.value = false; });
        } else {
          posEditName.value = symbolNames.value[lc] || lc;
        }
      } else {
        posEditSym.value = '';
      }
    };
    const addPosition = () => {
      posEditIsAdd.value = true;
      posEditSym.value = '';
      posEditCode.value = '';
      posEditName.value = '';
      posEditShares.value = 0;
      posEditPrice.value = 0;
      posEditOpen.value = true;
    };
    const editPosition = (sym) => {
      posEditIsAdd.value = false;
      const p = simState.value.positions?.[sym];
      posEditSym.value = sym;
      posEditCode.value = sym;
      posEditShares.value = Number(p?.shares || 0);
      posEditPrice.value = Number(p?.avgPrice || 0);
      posEditOpen.value = true;
    };
    const closePosEdit = () => { posEditOpen.value = false; };
    const confirmPosEdit = async () => {
      const sym = posEditSym.value || posEditCode.value;
      if (!sym) return;
      const sh = Math.floor(Number(posEditShares.value || 0) / 100) * 100;
      const px = Number(posEditPrice.value || 0);
      if (sh < 0 || !Number.isFinite(px) || px <= 0) return;
      if (sh === 0) {
        delete simState.value.positions[sym];
      } else {
        simState.value.positions[sym] = { shares: sh, avgPrice: px };
        // 自动注册未知 ETF
        if (posEditIsAdd.value && !etfSymbols.value.includes(sym)) {
          await registerEtfViaApi(sym);
        }
      }
      posEditOpen.value = false;
      saveSimLocal();
    };

    const getLastPrice = (sym) => {
      const s = (stageMap.value || {})[sym];
      if (s && Number.isFinite(s.minute_price) && s.minute_price > 0) return s.minute_price;
      if (s && Number.isFinite(s.close) && s.close > 0) return s.close;
      const l = (livePriceCache.value || {})[sym];
      if (l && Number.isFinite(l.price) && l.price > 0) return l.price;
      return null;
    };

    const simPositionsList = computed(() => {
      const pos = simState.value.positions || {};
      return Object.keys(pos).map((sym) => {
        const p = pos[sym];
        const shares = Number(p?.shares || 0);
        const avgPrice = Number(p?.avgPrice || 0);
        const lastPrice = getLastPrice(sym);
        const value = lastPrice ? shares * lastPrice : 0;
        const pnl = lastPrice ? (lastPrice - avgPrice) * shares : 0;
        return { symbol: sym, shares, avgPrice, lastPrice, value, pnl };
      }).sort((a, b) => (b.value || 0) - (a.value || 0));
    });

    const simMetrics = computed(() => {
      const positionsValue = simPositionsList.value.reduce((acc, p) => acc + (p.value || 0), 0);
      const cash = Number(simState.value.cash || 0);
      const equity = cash + positionsValue;
      const pnl = equity - Number(simConfig.value.initialCash || 0);
      const positionPct = equity > 0 ? positionsValue / equity : 0;
      return { cash, positionsValue, equity, pnl, positionPct };
    });

    const simTradesLatest = computed(() => {
      const arr = Array.isArray(simState.value.trades) ? [...simState.value.trades] : [];
      return arr.slice(-50).reverse();
    });

    const simCategoryExposure = computed(() => {
      const equity = simMetrics.value.equity || 0;
      if (equity <= 0) return {};
      const map = {};
      simPositionsList.value.forEach((p) => {
        const cat = etfCategoryMap.value[p.symbol] || '未分类';
        map[cat] = (map[cat] || 0) + (p.value || 0);
      });
      Object.keys(map).forEach((k) => { map[k] = map[k] / equity; });
      return map;
    });

    const simCategoryExposureList = computed(() => {
      const m = simCategoryExposure.value || {};
      return Object.keys(m).map((k) => ({ category: k, pct: Number(m[k] || 0) }))
        .sort((a, b) => (b.pct || 0) - (a.pct || 0));
    });

    const simMajorExposure = computed(() => {
      const m = simCategoryExposure.value || {};
      return {
        tech: Number(m['科技'] || 0),
        resource: Number(m['资源'] || 0)
      };
    });

    const simRiskAlerts = computed(() => {
      const alerts = [];
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
      const sm = stageMap.value || {};
      const syms = Object.keys(sm).filter(s => sm[s].stage);
      if (!syms.length) return [];

      // 只算有目标仓位的 ETF，按目标比例分配
      const getTarget = (s) => {
        if (s.was_uptrend) return RETRACE_TARGET[s.stage] || 0;
        return STAGE_TARGET[s.stage] || 0;
      };
      const totalTarget = syms.reduce((sum, sym) => sum + getTarget(sm[sym]), 0);
      const allocDenom = totalTarget > 0 ? totalTarget : syms.length;

      const suggestions = [];

      syms.forEach(sym => {
        const s = sm[sym];
        const cheapPrice = s.close || 0;
        if (!cheapPrice) return;
        const targetPct = getTarget(s);
        if (targetPct <= 0) return;
        const targetW = targetPct / allocDenom;
        const targetVal = targetW * equity;
        const pos = simState.value.positions?.[sym] || {};
        const curShares = Math.max(0, Number(pos.shares || 0));
        const curVal = curShares * cheapPrice;
        const curW = equity > 0 ? curVal / equity : 0;
        const delta = targetW - curW;
        if (Math.abs(delta) < 0.03) return;

        const action = delta > 0 ? 'BUY' : 'SELL';
        let notional = Math.abs(delta) * equity;
        if (action === 'BUY') notional = Math.min(notional, Math.max(0, Number(simState.value.cash || 0)));
        if (action === 'SELL') notional = Math.min(notional, curVal);
        if (notional <= 0) return;
        const tradeShares = Math.floor(notional / cheapPrice / 100) * 100;
        if (tradeShares <= 0) return;

        const stopPrice = fmtStopPrice(s.stage, cheapPrice, curShares > 0 ? Number(pos.avgPrice || 0) : 0);

        suggestions.push({
          symbol: sym, category: etfCategoryMap.value[sym] || '未分类', action,
          tradeShares, tradePrice: cheapPrice, targetPct, curShares, curVal,
          stopPrice, notional: Math.round(notional),
          reason: `${s.stage_icon} ${s.stage} → ${(targetPct*100).toFixed(0)}%仓位 · ${stageTriggers(s)}`
        });
      });

      suggestions.sort((a, b) => Math.abs(b.notional) - Math.abs(a.notional));
      if (window.TradeAllocator) TradeAllocator.applySectorCap(suggestions, equity);
      return suggestions;
    });

    const tradeSuggestionMap = computed(() => {
      const m = {};
      (tradeSuggestions.value || []).forEach((s) => { m[s.symbol] = s; });
      return m;
    });

    const stageInfo = (sym) => (stageMap.value || {})[sym] || {};

    function budgetPer() {
      const equity = simMetrics.value.equity || 0;
      const sm = stageMap.value || {};
      const syms = Object.keys(sm).filter(s => sm[s].stage);
      return syms.length ? equity / syms.length : 0;
    }

    const tradeTableRows = computed(() => {
      const equity = simMetrics.value.equity || 0;
      const execMap = tradeExecutedToday.value || {};
      return (etfSymbols.value || []).filter(isEtfVisible).map((sym) => {
        const s = stageInfo(sym);
        const sugg = tradeSuggestionMap.value?.[sym] || null;
        const stage = s.stage || '—';
        const price = s.close || 0;
        const pos = simState.value.positions?.[sym] || {};
        const curShares = Math.max(0, Number(pos.shares || 0));
        const curVal = curShares * price;
        const curW = equity > 0 ? curVal / equity : 0;
        const avgPrice = Number(pos.avgPrice || 0);

        const targetMap = s.was_uptrend ? RETRACE_TARGET : STAGE_TARGET;
        const targetPct = targetMap[stage] || 0;
        const targetShares = price > 0 ? Math.floor(budgetPer() * targetPct / price / 100) * 100 : 0;

        const executed = execMap[sym];
        const selectable = !!sugg && !executed;
        const isDefense = stage === '防守';
        const action = executed ? '已执行' : (sugg ? (sugg.action === 'BUY' ? '买入' : '卖出') : (isDefense ? '回避' : '不动'));
        const execLabel = executed ? ('✓ ' + executed.shares + '股@' + executed.price.toFixed(3)) : '';
        const stopPrice = sugg ? sugg.stopPrice : fmtStopPrice(stage, price, avgPrice);
        const tiers = entryTiersMap.value[sym] || null;

        return {
          symbol: sym, name: symbolNames.value[sym] || sym,
          category: etfCategoryMap.value[sym] || '未分类', _stage: stage,
          stage_icon: s.stage_icon || '', triggerDetail: (s.was_uptrend && stage === '启动' ? '🔥主线回调 · ' : '') + stageTriggers(s),
          curShares, curVal, curWeight: curW,
          targetPct, targetShares, targetVal: targetShares * price,
          action, tradeShares: sugg ? sugg.tradeShares : 0,
          tradePrice: sugg ? sugg.tradePrice : price,
          tradeNotional: sugg ? sugg.notional : 0,
          stopPrice, selectable, executed, execLabel,
          reason: sugg ? sugg.reason : (stage !== '—' ? `${s.stage_icon} ${stage}` : '等待阶段数据'),
          entryTiers: tiers,
        };
      }).sort((a, b) => {
        const order = { '主升': 0, '启动': 1, '震荡': 2, '下跌': 3, '防守': 4, '—': 5 };
        return (order[a._stage] || 9) - (order[b._stage] || 9);
      });
    });

    watch(tradeSuggestions, (items) => {
      const next = { ...suggestionOverrides.value };
      (items || []).forEach((s) => { if (next[s.symbol] == null) next[s.symbol] = s.notional; });
      Object.keys(next).forEach((k) => { if (!(items||[]).some(s=>s.symbol===k)) delete next[k]; });
      suggestionOverrides.value = next;
      const nextSel = { ...selectedSuggestions.value };
      Object.keys(nextSel).forEach((k) => { if (!(items||[]).some(s=>s.symbol===k)) delete nextSel[k]; });
      selectedSuggestions.value = nextSel;
    }, { immediate: true });

    const calcLotShares = ({ amount, price, lot }) => {
      const amt = Math.max(0, Number(amount||0));
      const p = Number(price||0);
      if (!Number.isFinite(amt) || !Number.isFinite(p) || p <= 0) return 0;
      const l = Math.max(1, Number(lot||100));
      return Math.floor(amt / p / l) * l;
    };

    const applySimTradeExact = ({ symbol, side, shares, price, reason }) => {
      const lot = 100;
      const p = Number(price||0);
      const sh = Math.floor(Number(shares||0)/lot)*lot;
      if (!symbol||!Number.isFinite(p)||p<=0) return {ok:false,error:'价格无效'};
      if (!Number.isFinite(sh)||sh<=0) return {ok:false,error:'份额无效'};
      const pos0 = simState.value.positions?.[symbol] || {shares:0,avgPrice:0};
      const curShares = Math.max(0,Number(pos0.shares||0));
      const curAvg = Number(pos0.avgPrice||0);
      const notional = sh * p;
      if (side==='BUY'){
        const cash = Math.max(0,Number(simState.value.cash||0));
        if (notional>cash) return {ok:false,error:'现金不足'};
        const ns = curShares+sh;
        simState.value.cash=cash-notional;
        simState.value.positions[symbol]={shares:ns,avgPrice:ns>0?((curShares*curAvg)+notional)/ns:0};
        simState.value.trades.push({id:`${Date.now()}_${symbol}_B`,ts:nowTs(),symbol,side:'BUY',shares:sh,price:p,notional,reason:reason||''});
        saveSimLocal();
        return {ok:true};
      }
      if (side==='SELL'){
        if (sh>curShares) return {ok:false,error:'份额超过持仓'};
        simState.value.cash = Math.max(0,Number(simState.value.cash||0))+notional;
        const ns = curShares-sh;
        if (ns<=0) delete simState.value.positions[symbol];
        else simState.value.positions[symbol]={shares:ns,avgPrice:curAvg};
        simState.value.trades.push({id:`${Date.now()}_${symbol}_S`,ts:nowTs(),symbol,side:'SELL',shares:sh,price:p,notional,reason:reason||''});
        saveSimLocal();
        return {ok:true};
      }
      return {ok:false,error:'方向无效'};
    };

    const openTradeConfirmForSymbols = (symbols) => {
      const syms = Array.isArray(symbols)?symbols:[];
      const items=[];
      const lot=100;
      syms.forEach((symbol)=>{
        const s = (tradeSuggestions.value||[]).find(x=>x.symbol===symbol);
        if (!s) return;
        const price = getLastPrice(symbol)||0;
        const amt = Number(suggestionOverrides.value?.[symbol]??s.notional);
        const held = Math.max(0,Number(simState.value.positions?.[symbol]?.shares||0));
        let shares=0;
        if (s.action==='BUY') shares=calcLotShares({amount:amt,price,lot});
        else if (s.action==='SELL') { const req=calcLotShares({amount:amt,price,lot}); shares=req>0?Math.min(held,req):held; }
        items.push({symbol,name:symbolNames.value[symbol]||symbol,side:s.action,price:Number(price||0),shares:Number(shares||0),lot,reason:s.reason||''});
      });
      tradeConfirmItems.value=items; tradeConfirmError.value=''; tradeConfirmOpen.value=true;
    };

    const closeTradeConfirm = () => { tradeConfirmOpen.value=false; tradeConfirmItems.value=[]; tradeConfirmError.value=''; };

    const confirmTradeConfirm = () => {
      tradeConfirmError.value='';
      const items = tradeConfirmItems.value||[];
      if (!items.length) { tradeConfirmError.value='没有可执行的建议'; return; }
      for (const it of items) {
        const p=Number(it.price||0),sh=Number(it.shares||0),lot=Number(it.lot||100);
        if(!Number.isFinite(p)||p<=0){tradeConfirmError.value=`${it.name} 价格无效`;return;}
        if(!Number.isFinite(sh)||sh<=0||sh%lot!==0){tradeConfirmError.value=`${it.name} 份额需为${lot}的整数倍`;return;}
        if(it.side==='SELL'){const held=Math.max(0,Number(simState.value.positions?.[it.symbol]?.shares||0));if(sh>held){tradeConfirmError.value=`${it.name} 卖出份额超过持仓`;return;}}
        else if(it.side==='BUY'){if(sh*p>Math.max(0,Number(simState.value.cash||0))){tradeConfirmError.value=`${it.name} 现金不足`;return;}}
      }
      const selectedMap={...selectedSuggestions.value}, execMap={...tradeExecutedToday.value};
      for(const it of items){
        const r=applySimTradeExact({symbol:it.symbol,side:it.side,shares:it.shares,price:it.price,reason:it.reason});
        if(!r.ok){tradeConfirmError.value=`${it.name} 执行失败：${r.error||'未知原因'}`;return;}
        if(selectedMap[it.symbol]) selectedMap[it.symbol]=false;
        execMap[it.symbol]={shares:it.shares,price:it.price,ts:Date.now()};
      }
      tradeExecutedToday.value=execMap; selectedSuggestions.value=selectedMap; closeTradeConfirm();
    };

    const executeSuggestion = (symbol) => openTradeConfirmForSymbols([symbol]);

    const tradeSelectedCount = computed(()=>{
      const m=selectedSuggestions.value||{};
      return Object.keys(m).filter(k=>!!m[k]).length;
    });

    const tradeAllSelected = computed(()=>{
      const syms=(tradeSuggestions.value||[]).map(s=>s.symbol);
      return syms.length>0&&syms.every(s=>!!selectedSuggestions.value?.[s]);
    });

    const toggleTradeSelectAll = ()=>{
      const syms=(tradeSuggestions.value||[]).map(s=>s.symbol);
      if(!syms.length) return;
      const next=!tradeAllSelected.value;
      const m={...selectedSuggestions.value};
      syms.forEach(s=>{m[s]=next;});
      selectedSuggestions.value=m;
    };

    const executeSelectedSuggestions = ()=>{
      const syms=(tradeSuggestions.value||[]).map(s=>s.symbol);
      const picked=syms.filter(s=>!!selectedSuggestions.value?.[s]);
      openTradeConfirmForSymbols(picked);
    };

    // --- localStorage ---
    const saveSimLocal = ()=>{
      localStorage.setItem('sim_initial_cash',String(simConfig.value.initialCash||0));
      localStorage.setItem(SIM_KEY,JSON.stringify({config:simConfig.value,state:simState.value}));
    };

    const loadSimLocal = ()=>{
      try{
        const raw=localStorage.getItem(SIM_KEY);
        if(!raw) return false;
        const parsed=JSON.parse(raw);
        if(parsed?.config) simConfig.value={initialCash:Number(parsed.config.initialCash??simConfig.value.initialCash)};
        if(parsed?.state) simState.value={...simState.value,...parsed.state};
        if(!Number.isFinite(Number(simState.value.cash))) simState.value.cash=Number(simConfig.value.initialCash)||0;
        if(!simState.value.positions||typeof simState.value.positions!=='object') simState.value.positions={};
        if(!Array.isArray(simState.value.trades)) simState.value.trades=[];
        return true;
      }catch(e){return false;}
    };

    const resetSimAccount = ()=>{
      const initial=Number(simConfig.value.initialCash)||0;
      simState.value={cash:initial,positions:{},trades:[]};
      suggestionOverrides.value={};
      tradeExecutedToday.value={};
      saveSimLocal();
    };

    const holdingsScreenshot = ref(localStorage.getItem('sim_holdings_screenshot')||'');

    const ocrLoading = ref(false);
    const ocrResultsOpen = ref(false);
    const ocrResults = ref([]);
    const ocrRawTexts = ref([]);
    const ocrError = ref('');
    const ocrUnmapped = ref([]);

    const onHoldingsScreenshot = async (ev)=>{
      try{
        const file=ev?.target?.files?.[0];
        if(!file) return;
        const reader=new FileReader();
        reader.onload=async ()=>{
          const dataUrl=String(reader.result||'');
          holdingsScreenshot.value=dataUrl;
          localStorage.setItem('sim_holdings_screenshot',dataUrl);

          ocrLoading.value = true;
          ocrError.value = '';
          try {
            const r = await fetch('/api/trade/ocr-positions', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({image: dataUrl})
            });
            const j = await r.json();
            if (j.ok && j.data && j.data.positions && j.data.positions.length > 0) {
              ocrResults.value = j.data.positions;
              ocrRawTexts.value = j.data.raw_texts || [];
              ocrResultsOpen.value = true;
            } else {
              const texts = j.data?.raw_texts || [];
              const detail = texts.length ? ' (检测到: '+texts.slice(0,10).join(', ')+')' : '';
              ocrError.value = '未识别到持仓数据，请用"＋ 添加"手动录入' + detail;
            }
          } catch (e) {
            ocrError.value = '识别失败：' + (e.message || '网络错误');
          }
          ocrLoading.value = false;
        };
        reader.readAsDataURL(file);
      }catch(e){void e;}
    };

    const closeOcrResults = () => { ocrResultsOpen.value = false; ocrResults.value = []; ocrRawTexts.value = []; };

    const clearScreenshot = () => {
      holdingsScreenshot.value = '';
      localStorage.removeItem('sim_holdings_screenshot');
    };

    const matchNameToCode = (ocrName) => {
      if (/^(sh|sz)\d{6}$/i.test(ocrName)) return ocrName.toLowerCase();
      return null;
    };

    const importOcrPositions = () => {
      if (!ocrResults.value.length) return;
      const unmapped = [];
      ocrResults.value.forEach((p) => {
        const code = p.code || matchNameToCode(p.name);
        if (!code) { unmapped.push(p); return; }
        if (p.shares > 0 && p.avgPrice > 0) {
          simState.value.positions[code] = { shares: p.shares, avgPrice: p.avgPrice };
        } else if (p.shares > 0) {
          const existing = simState.value.positions[code];
          const avg = existing ? Number(existing.avgPrice || 0) : Number(getLastPrice(code) || 0);
          simState.value.positions[code] = { shares: p.shares, avgPrice: avg };
        }
      });
      if (unmapped.length) {
        ocrUnmapped.value = unmapped;
        ocrError.value = `${unmapped.length} 个未识别,请在弹窗中选择对应代码`;
      } else {
        ocrResultsOpen.value = false;
        ocrResults.value = [];
      }
      saveSimLocal();
    };

    // --- init ---
    if(!loadSimLocal()) resetSimAccount();
    watch(simConfig, ()=>saveSimLocal(), {deep:true});

    // --- stage border class (reused from old page) ---
    const stageBorderClass = (stage)=>{
      const map={主升:'stage-uptrend',启动:'stage-startup',震荡:'stage-ranged',下跌:'stage-declining',防守:'stage-defense'};
      return map[stage]||'';
    };

    onMounted(()=>{
      fetchEtfConfig();
      fetchStageState();
      window.TradeAllocator?.fetchMarketState();
      if(autoRefresh.value) timer=setInterval(fetchStageState,refreshSec.value*1000);
    });
    onUnmounted(()=>{ if(timer) clearInterval(timer); });

    return {
      stageMap, day, error, autoRefresh, refreshSec, toggleAutoRefresh,
      sortedStageEntries,
      simConfig, simState, simMetrics, simPositionsList, simTradesLatest,
      simCategoryExposureList, simMajorExposure, simRiskAlerts,
      tradeSuggestions, tradeTableRows, suggestionOverrides, selectedSuggestions,
      tradeExecutedToday, tradeSelectedCount, tradeAllSelected, toggleTradeSelectAll,
      executeSelectedSuggestions, executeSuggestion,
      tradeConfirmOpen, tradeConfirmItems, tradeConfirmError,
      closeTradeConfirm, confirmTradeConfirm,
      capitalModalOpen, capitalModalValue, openCapitalModal, closeCapitalModal, confirmCapitalModal,
      posEditOpen, posEditIsAdd, posEditSym, posEditShares, posEditPrice, posEditCode,
      editPosition, addPosition, closePosEdit, confirmPosEdit, onPosEditCodeInput,
      resetSimAccount, holdingsScreenshot, onHoldingsScreenshot,
      ocrLoading, ocrResultsOpen, ocrResults, ocrRawTexts, ocrError, ocrUnmapped,
      closeOcrResults, clearScreenshot, importOcrPositions, matchNameToCode,
      backfillToast, closeBackfillToast, posEditName, posEditNameLoading,
      tradeBottomTab,
      symbolNames,
      hiddenEtfs, manageOpen, toggleManage, toggleEtfHidden, isEtfVisible,
      stageBorderClass, fmtCny
    };
  }
}).mount('#app');
