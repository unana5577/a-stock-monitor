const fs = require('fs');
const path = require('path');

const file = path.join(__dirname, 'data/volume-20260306.jsonl');
if (!fs.existsSync(file)) {
    console.log("File not found");
    process.exit(0);
}

const txt = fs.readFileSync(file, 'utf-8').trim();
const lines = txt.split('\n');
const newLines = [];

lines.forEach(line => {
    try {
        const row = JSON.parse(line);
        let vol = row[1];
        if (typeof vol === 'number') {
             if (vol < 1000000000) { 
                 vol = vol * 10000;
             }
        }
        newLines.push(JSON.stringify([row[0], vol]));
    } catch (e) { return; }
});

const map = new Map();
newLines.forEach(line => {
    const row = JSON.parse(line);
    map.set(row[0], row[1]);
});

const finalLines = Array.from(map.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(p => JSON.stringify(p));

fs.writeFileSync(file, finalLines.join('\n') + '\n');
console.log(`Repaired ${finalLines.length} lines.`);
