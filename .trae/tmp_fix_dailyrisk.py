with open('public/ui_m1.js', 'r') as f:
    content = f.read()

old = '''      dailyRiskLoading.value = true;
      const sys = '你是A股交易风控助手，输出要简洁可执行，不要出现百分比概率，不要使用项目符号符号，只用换行分段。';
      const user = `请结合\u201c当日选中日期\u201d的信息，生成\u201c当日操作风险提示\u201d（3-5行）：\\n日期：${day}\\n月相：${astroSelectedPhase.value}\\n次日大盘倾向：${marketDirectionText('1')}\\n性别：${userGender.value}\\n出生：${userBirth.value}\\n出生地：${userPlaceText.value}\\n八字：${b}`;
      const txt = await callChat(sys, user);'''

new = '''      dailyRiskLoading.value = true;
      const p2 = baziPrompts.value;
      const du2 = baziProfile.value?.dayun;
      const duText2 = du2?.current && du2?.currentAgeRange ? `${du2.current}（${du2.currentAgeRange}）` : (du2?.current || '');
      const sys = p2?.dailyRisk?.system || '你是A股交易风控助手，输出要简洁可执行，不要出现百分比概率，不要使用项目符号符号，只用换行分段。';
      const user = replaceTemplate(p2?.dailyRisk?.userTemplate || '请结合\u201c当日选中日期\u201d的信息，生成\u201c当日操作风险提示\u201d（3-5行）：\\n日期：{{day}}\\n月相：{{phaseText}}\\n次日大盘倾向：{{marketBias}}\\n性别：{{gender}}\\n出生：{{birth}}\\n八字：{{baziText}}', {
        day, phaseText: astroSelectedPhase.value, marketBias: marketDirectionText('1'),
        gender: userGender.value, birth: userBirth.value, baziText: b, dayun: duText2,
        ganzhiYear: baziProfile.value?.bazi?.year || '',
        ganzhiMonth: astroMonthGanzhi.value || '',
        ganzhiDay: astroSelectedGanzhiDay.value || '',
        lunarMonth: '', lunarDay: astroSelectedLunarDay.value || ''
      });
      const txt = await callChat(sys, user);'''

if old in content:
    content = content.replace(old, new)
    with open('public/ui_m1.js', 'w') as f:
        f.write(content)
    print('OK')
else:
    print('NOT FOUND')
    idx = content.find('dailyRiskLoading')
    print(repr(content[idx:idx+400]))
