const https = require('https');

function testUrl(name, url) {
  return new Promise((resolve) => {
    const startTime = Date.now();
    console.log(`\n[${name}] 测试中...`);
    console.log(`URL: ${url}`);

    const req = https.get(url, {
      headers: { 'User-Agent': 'Mozilla/5.0' },
      timeout: 10000
    }, (res) => {
      let data = [];
      res.on('data', chunk => data.push(chunk));
      res.on('end', () => {
        const latency = Date.now() - startTime;
        const body = Buffer.concat(data).toString();
        try {
          const json = JSON.parse(body);
          console.log(`✓ 状态码: ${res.statusCode}`);
          console.log(`✓ 响应时间: ${latency}ms`);
          console.log(`✓ 数据预览: ${JSON.stringify(json).slice(0, 150)}...`);
          resolve({ name, url, status: res.statusCode, latency, success: true, data: json });
        } catch (e) {
          console.log(`✗ JSON解析失败: ${e.message}`);
          console.log(`✓ 响应内容: ${body.slice(0, 150)}...`);
          resolve({ name, url, status: res.statusCode, latency, success: false, error: 'JSON解析失败' });
        }
      });
    });

    req.on('error', (err) => {
      const latency = Date.now() - startTime;
      console.log(`✗ 请求失败: ${err.message} (code: ${err.code})`);
      resolve({ name, url, status: null, latency, success: false, error: err.message, code: err.code });
    });

    req.on('timeout', () => {
      req.destroy();
      const latency = Date.now() - startTime;
      console.log(`✗ 请求超时 (>10秒)`);
      resolve({ name, url, status: null, latency, success: false, error: 'timeout' });
    });
  });
}

async function main() {
  console.log('='.repeat(60));
  console.log('东财API连通性测试');
  console.log('='.repeat(60));

  const tests = [
    {
      name: 'Snapshot (快照数据)',
      url: 'https://push2.eastmoney.com/api/qt/stock/get?secid=1.000001&fields=f43,f170,f58,f60'
    },
    {
      name: 'Minute (分钟数据)',
      url: 'https://push2.eastmoney.com/api/qt/stock/kline/get?secid=1.000001&fields1=f1,f2&fields2=f51,f52,f53,f54,f55,f56&klt=1&fqt=1&end=20500101&lmt=10'
    },
    {
      name: 'Daily (日线数据)',
      url: 'https://push2.eastmoney.com/api/qt/stock/kline/get?secid=1.000001&fields1=f1,f2&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=1&end=20500101&lmt=10'
    },
    {
      name: 'Breadth (广度数据)',
      url: 'https://push2.eastmoney.com/api/qt/stock/get?secid=1.000001&fields=f104,f105,f106'
    }
  ];

  const results = [];
  for (const test of tests) {
    const result = await testUrl(test.name, test.url);
    results.push(result);
  }

  console.log('\n' + '='.repeat(60));
  console.log('测试总结');
  console.log('='.repeat(60));

  const successCount = results.filter(r => r.success).length;
  const failCount = results.length - successCount;

  console.log(`\n总计: ${results.length} 个测试`);
  console.log(`成功: ${successCount} 个`);
  console.log(`失败: ${failCount} 个`);

  if (failCount > 0) {
    console.log('\n失败的测试:');
    results.filter(r => !r.success).forEach(r => {
      console.log(`  - ${r.name}: ${r.error || '未知错误'}`);
      if (r.code) console.log(`    错误码: ${r.code}`);
    });
  }

  console.log('\n' + '='.repeat(60));

  if (failCount === 0) {
    console.log('✓ 所有API连通性测试通过！');
  } else if (failCount === results.length) {
    console.log('✗ 所有API测试失败，可能存在网络问题');
    console.log('\n可能原因:');
    console.log('  1. 网络连接问题（防火墙/代理）');
    console.log('  2. DNS解析问题');
    console.log('  3. 东财服务器限制');
  } else {
    console.log('⚠ 部分API测试失败，需要进一步调查');
  }
}

main().catch(console.error);
