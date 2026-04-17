const https = require('https');
https.get("https://push2.eastmoney.com/api/qt/stock/get?secid=0.399001&fields=f43,f170,f58,f60", (res) => {
  let data = '';
  res.on('data', c => data += c);
  res.on('end', () => console.log(data));
}).on('error', console.error);
