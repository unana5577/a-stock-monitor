const http = require('http');

const TARGET = process.env.TARGET || 'http://a-stock-v2:8788';
const PORT = process.env.PORT || 8787;

const server = http.createServer((clientReq, clientRes) => {
  const options = {
    hostname: new URL(TARGET).hostname,
    port: new URL(TARGET).port || 8788,
    path: clientReq.url,
    method: clientReq.method,
    headers: { ...clientReq.headers, host: new URL(TARGET).host },
  };

  const proxy = http.request(options, (proxyRes) => {
    clientRes.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(clientRes);
  });

  proxy.on('error', () => {
    clientRes.writeHead(502);
    clientRes.end('proxy error');
  });

  clientReq.pipe(proxy);
});

server.listen(PORT, () => console.log(`proxy ${PORT} → ${TARGET}`));
