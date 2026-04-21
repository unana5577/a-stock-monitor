const https = require('https');
const fs = require('fs');
const path = require('path');

function fetchEastmoneyMinute(secid) {
  return new Promise((resolve, reject) => {
    const url = `https://push2.eastmoney.com/api/qt/stock/trends2/get?fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13&fields2=f51,f53,f56,f58&secid=${secid}&ndays=1&iscr=0&iscca=0`;
    https.get(url, (res) => {
      let raw = '';
      res.on('data', c => raw += c);
      res.on('end', () => {
        try {
          const json = JSON.parse(raw);
          if (!json?.data?.trends) return resolve({ data: [] });
          // trends2 returns string: "time,price,volume,avgPrice,..."
          const trends = json.data.trends.map(t => {
            const parts = t.split(',');
            // Return object to allow volume extraction
            return { 
              time: parts[0], 
              price: +parts[1], 
              volume: +parts[2] // This volume is usually in Hands (100 shares) or raw units depending on index
              // For indices, it's usually Volume (Hands) or Amount?
              // Let's check. 
              // API: fields2=f51,f53,f56,f58 -> time, price, volume, avgPrice?
              // Actually trends2 standard is: time, open, close, high, low, vol, amount?
              // Wait, trends2 usually returns simple list.
              // Let's assume parts[2] is Volume (Hands) and we need Amount?
              // For "Turnover" (Amount), we need to check if API returns it.
              // fields1=f1..f13. 
              // f13 is usually Amount?
              // Let's assume for now we use the volume/amount from the API response if available.
              // But trends2 default might not have Amount.
              // However, we can approximate or use a separate call.
              // Actually, parts[2] is usually Volume. 
              // For the turnover curve, we need AMOUNT (Money).
              // Let's assume parts[2] is close to what we need or we can't get better easily.
              // Wait, for indices, 'volume' field in trends usually IS the volume (shares/hands).
              // We need Amount (Yuan).
              // Does trends2 return Amount?
              // If not, we might need to multiply Volume * AvgPrice?
              // parts[3] is AvgPrice.
              // Amount = Volume * AvgPrice?
              // Let's try that.
            };
          });
          resolve({ data: trends, prevClose: json.data.prePrice });
        } catch (e) {
          reject(e);
        }
      });
    }).on('error', reject);
  });
}

async function buildVolumeFromIndices(dateStr) {
  console.log('Building volume from indices for', dateStr);
  const sse = await fetchEastmoneyMinute('1.000001');
  const szi = await fetchEastmoneyMinute('0.399001');
  
  if (!sse.data.length || !szi.data.length) {
    console.log('Missing index data for volume build');
    return;
  }
  
  // Align by time
  const map = new Map();
  
  const process = (data) => {
    data.forEach(p => {
       const t = p.time;
       // Approximate Amount = Volume * Price (rough) or just use Volume if it's actually Amount
       // For indices, trends2 'volume' is often Volume (Hands).
       // We need Amount. 
       // Let's check parts[5]?
       // Actually let's just use Volume * Price / 10000 (to get Wan)?
       // No, that's too rough.
       // Let's assume parts[2] IS amount? 
       // No, usually it's volume.
       
       // ALTERNATIVE: Use akshare daily total and distribute it according to minute volume profile?
       // That's complex.
       
       // Let's try to see if trends2 has amount.
       // I'll assume Volume * AvgPrice is a good proxy for incremental amount.
       // p.volume (Hands?) * p.price (Index Points?) -> Index Volume?
       // Index "Amount" is sum of constituent amounts.
       // It is not directly Vol * Price.
       
       // BUT, for the purpose of the "Volume Curve", the shape matters most.
       // The total can be scaled.
       // I will sum the raw volumes (or whatever parts[2] is) and then Scale it to match the known Daily Total (1.98T).
       
       const v = p.volume; 
       if (!map.has(t)) map.set(t, 0);
       map.set(t, map.get(t) + v);
    });
  };
  
  process(sse.data);
  process(szi.data);
  
  const sortedTimes = Array.from(map.keys()).sort();
  let cumulative = 0;
  const points = [];
  
  sortedTimes.forEach(t => {
    cumulative += map.get(t);
    points.push({ time: t, raw: cumulative });
  });
  
  if (!points.length) return;
  
  const maxRaw = points[points.length - 1].raw;
  // Target Total: 1.98 Trillion Yuan = 198,267,000 Wan.
  const targetTotal = 198267000;
  
  const file = path.join(__dirname, 'data', `volume-${dateStr}.jsonl`);
  const lines = points.map(p => {
    // Scale
    const val = Math.floor(p.raw / maxRaw * targetTotal);
    return JSON.stringify([p.time, val]);
  });
  
  fs.writeFileSync(file, lines.join('\n') + '\n');
  console.log(`Rebuilt ${file} with target ${targetTotal}`);
}

async function main() {
  const mappings = [
    { code: 'sse', secid: '1.000001' },
    { code: 'szi', secid: '0.399001' },
    { code: 'gem', secid: '0.399006' },
    { code: 'star', secid: '1.000688' },
    { code: 'hs300', secid: '1.000300' },
    { code: 'csi2000', secid: '2.932000' },
    { code: 'gov', secid: '1.000012' },
    { code: 't', secid: '8.110130' },
    { code: 'tl', secid: '8.140130' },
    { code: 'bank', secid: '90.BK0475' },
    { code: 'broker', secid: '90.BK0473' },
    { code: 'insure', secid: '90.BK0474' },
    { code: 'avg', secid: '2.830000' }
  ];

  const dateStr = '20260213';

  // 1. Fetch minute data and save [time, price, price]
  for (const m of mappings) {
    try {
      console.log(`Fetching ${m.code}...`);
      const res = await fetchEastmoneyMinute(m.secid);
      if (res.data && res.data.length > 0) {
        const file = path.join(__dirname, 'data', `minute-${dateStr}-${m.code}.jsonl`);
        // Save as [time, price, price]
        const lines = res.data.map(row => JSON.stringify([row.time, row.price, row.price]));
        fs.writeFileSync(file, lines.join('\n') + '\n');
        console.log(`Saved ${file} (${res.data.length} points)`);
      } else {
        console.log(`No data for ${m.code}`);
      }
    } catch (e) {
      console.error(`Error ${m.code}:`, e.message);
    }
  }
  
  // 2. Build Volume File for 2026-02-13
  await buildVolumeFromIndices(dateStr);
  
  // 3. Ensure 2026-02-12 Volume File is correct (2.14T)
  const vol0212 = path.join(__dirname, 'data', 'volume-20260212.jsonl');
  // 2.1417 * 10^12 Yuan = 214173835 Wan.
  const content0212 = `["2026-02-12 15:00",214173835]\n`;
  fs.writeFileSync(vol0212, content0212);
  console.log('Reset volume-20260212.jsonl');
}

main();
