const fs = require('fs');
const path = require('path');

function readVolumeFile(file) {
  if (!fs.existsSync(file)) return [];
  const txt = fs.readFileSync(file, 'utf-8').trim();
  if (!txt) return [];
  return txt.split('\n').map((line) => {
    try {
        const row = JSON.parse(line);
        return { time: row[0], volume: row[1] };
    } catch (e) { return null; }
  }).filter(x => x);
}

const day = '2026-03-06';
const file = path.join(__dirname, 'data', `volume-${day.replace(/-/g, '')}.jsonl`);
console.log(`Reading file: ${file}`);
const series = readVolumeFile(file);
console.log(`Read ${series.length} points.`);
if (series.length > 0) {
    console.log('First 5:', series.slice(0, 5));
}
