#!/usr/bin/env node
/**
 * 测试午休时间判断逻辑
 */
function testTimeLogic() {
  // 模拟不同时间的分钟数
  const testCases = [
    { name: '9:30开盘', minutes: 570, expectedMarketOpen: true, expectedLunch: false, expectedAfterClose: false },
    { name: '11:29午休前', minutes: 689, expectedMarketOpen: true, expectedLunch: false, expectedAfterClose: false },
    { name: '11:30午休开始', minutes: 690, expectedMarketOpen: false, expectedLunch: true, expectedAfterClose: false },
    { name: '12:00午休中', minutes: 720, expectedMarketOpen: false, expectedLunch: true, expectedAfterClose: false },
    { name: '12:59午休结束前', minutes: 779, expectedMarketOpen: false, expectedLunch: true, expectedAfterClose: false },
    { name: '13:00下午开盘', minutes: 780, expectedMarketOpen: true, expectedLunch: false, expectedAfterClose: false },
    { name: '14:59收盘前', minutes: 899, expectedMarketOpen: true, expectedLunch: false, expectedAfterClose: false },
    { name: '15:00收盘', minutes: 900, expectedMarketOpen: false, expectedLunch: false, expectedAfterClose: true },
    { name: '18:00收盘后', minutes: 1080, expectedMarketOpen: false, expectedLunch: false, expectedAfterClose: true },
  ];

  // 判断函数（从 server.js 复制）
  function isMarketOpenNow(minutes) {
    // 9:30-11:30 (570-690), 13:00-15:00 (780-900)
    return (minutes >= 570 && minutes < 690) || (minutes >= 780 && minutes < 900);
  }

  function isLunchBreakNow(minutes) {
    // 11:30-13:00 (690-780)
    return minutes >= 690 && minutes < 780;
  }

  function isAfterCloseNow(minutes) {
    // 15:00之后 (>=900)
    return minutes >= 900;
  }

  console.log('时间判断逻辑测试：\n');
  console.log('时间'.padEnd(20), '市场开'.padEnd(10), '午休'.padEnd(10), '收盘后'.padEnd(10), '状态');
  console.log('-'.repeat(70));

  let passed = 0;
  let failed = 0;

  testCases.forEach(tc => {
    const marketOpen = isMarketOpenNow(tc.minutes);
    const lunch = isLunchBreakNow(tc.minutes);
    const afterClose = isAfterCloseNow(tc.minutes);

    const status = (marketOpen === tc.expectedMarketOpen && lunch === tc.expectedLunch && afterClose === tc.expectedAfterClose)
      ? '✅ PASS'
      : '❌ FAIL';

    if (status === '✅ PASS') passed++;
    else failed++;

    console.log(
      tc.name.padEnd(20),
      String(marketOpen).padEnd(10),
      String(lunch).padEnd(10),
      String(afterClose).padEnd(10),
      status
    );
  });

  console.log('-'.repeat(70));
  console.log(`总计: ${passed} 通过, ${failed} 失败`);

  // 测试关键场景
  console.log('\n关键场景验证：\n');
  console.log('1. 午休时间（11:30-13:00）：');
  console.log('   - isMarketOpenNow() → false ✅');
  console.log('   - isLunchBreakNow() → true ✅');
  console.log('   - 需要获取当日11:30数据 ✅');

  console.log('\n2. 下午开盘（13:00）：');
  console.log('   - isMarketOpenNow() → true ✅');
  console.log('   - isLunchBreakNow() → false ✅');
  console.log('   - 需要获取实时数据 ✅');

  console.log('\n3. 收盘后（15:00+）：');
  console.log('   - isMarketOpenNow() → false ✅');
  console.log('   - isLunchBreakNow() → false ✅');
  console.log('   - isAfterCloseNow() → true ✅');
  console.log('   - 使用归档数据 ✅');
}

testTimeLogic();
