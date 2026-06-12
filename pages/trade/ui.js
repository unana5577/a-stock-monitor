const { createApp, ref, onMounted, onUnmounted } = Vue
const STAGE_POSITION = {
  '主升': '80%仓位 · 趋势持有',
  '启动': '30%试探 → 70%突破加仓',
  '震荡': '70%底仓 · 网格波段',
  '下跌': '30%仓位 · 等待修复',
  '防守': '0%仓位 · 空仓等待',
}

createApp({
  setup() {
    const stages = ref([])
    const day = ref('--')
    const error = ref('')
    const autoRefresh = ref(true)
    const refreshSec = ref(30)
    let timer = null

    async function fetchData() {
      try {
        const r = await fetch('/api/m1/stage_state')
        const json = await r.json()
        if (json.ok && json.data) {
          stages.value = Object.values(json.data.stages)
          day.value = json.data.day
          error.value = ''
        } else {
          error.value = json.error || '加载失败'
        }
      } catch (e) {
        error.value = e.message
      }
    }

    function toggleAutoRefresh() {
      autoRefresh.value = !autoRefresh.value
      if (autoRefresh.value) {
        fetchData()
        timer = setInterval(fetchData, refreshSec.value * 1000)
      } else {
        clearInterval(timer)
        timer = null
      }
    }

    onMounted(() => {
      fetchData()
      if (autoRefresh.value) {
        timer = setInterval(fetchData, refreshSec.value * 1000)
      }
    })

    onUnmounted(() => {
      if (timer) clearInterval(timer)
    })

    function stageBorderClass(stage) {
      const map = { '主升':'stage-uptrend','启动':'stage-startup','震荡':'stage-ranged','下跌':'stage-declining','防守':'stage-defense' }
      return map[stage] || ''
    }
    function stageBadgeClass(stage) {
      const map = { '主升':'badge-uptrend','启动':'badge-startup','震荡':'badge-ranged','下跌':'badge-declining','防守':'badge-defense' }
      return map[stage] || ''
    }
    function fmtSlope(v) {
      if (v == null) return '--'
      return (v * 100).toFixed(2) + '%'
    }
    function rangePct(s) {
      if (!s.high_90d || !s.low_90d || s.high_90d === s.low_90d) return 0
      return ((s.close - s.low_90d) / (s.high_90d - s.low_90d) * 100).toFixed(1)
    }
    function rangeColor(s) {
      const p = parseFloat(rangePct(s))
      if (p > 60) return '#10B981'
      if (p > 30) return '#F59E0B'
      return '#EF4444'
    }
    function positionHint(s) {
      return STAGE_POSITION[s.stage] || ''
    }

    return { stages, day, error, autoRefresh, refreshSec, toggleAutoRefresh, stageBorderClass, stageBadgeClass, fmtSlope, rangePct, rangeColor, positionHint }
  }
}).mount('#app')
