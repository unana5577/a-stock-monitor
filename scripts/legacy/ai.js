// AI Analysis Logic
// Currently rule-based, ready for LLM integration

function analyze(data) {
  // data: snapshot payload
  const idx = data.indices || {};
  const sent = data.sentiment || {};
  
  // Extract key indicators
  const ssePct = idx.sse?.pct || 0;
  const starPct = idx.star?.pct || 0;
  const vol = sent.volume || 0; // 10k
  
  let title = '市场扫描中...';
  let detail = '正在获取数据...';
  
  // 1. Risk vs Risk-on
  // Risk-off: Gov bond up, Stocks down
  // Risk-on: Stocks up (esp. Growth/Star50), Gov bond flat/down
  
  let state = '震荡';
  if (ssePct > 0.5 && starPct > 1.0) state = '进攻';
  else if (ssePct < -0.5) state = '防御';
  
  if (state === '进攻') {
    title = '资金情绪积极，成长风格占优';
    detail = '科创/创业板领涨，市场风险偏好提升。建议关注科技成长板块，持仓待涨。';
  } else if (state === '防御') {
    title = '避险情绪升温，注意风险控制';
    detail = '大盘走弱，国债/红利资产可能受捧。建议控制仓位，避免追高，关注防守型板块。';
  } else {
    title = '市场窄幅震荡，方向不明';
    detail = '指数涨跌互现，缺乏明确主线。建议多看少动，等待市场选择方向，保持灵活仓位。';
  }
  
  // Volume check
  if (vol > 100000000) { // 1 Trillion
    detail += ' 今日成交额有望破万亿，流动性充裕。';
  }
  
  return { title, detail };
}

module.exports = { analyze };
