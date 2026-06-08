## 提示词文件

文件：prompts.json

你可以直接改里面的 system / userTemplate。改完后建议顺手改一下 rev，用来让前端缓存自动失效（否则可能继续读旧的生成结果）。

## 占位符

finance.userTemplate：
- {{gender}}：性别
- {{birth}}：出生时间（北京时间输入）
- {{place}}：出生地（省-市/州）
- {{baziText}}：八字四柱文本（年 月 日 时）

dailyRisk.userTemplate：
- {{day}}：当日选中日期（YYYY-MM-DD，北京时间自然日）
- {{ganzhiYear}} / {{ganzhiMonth}} / {{ganzhiDay}}：当日流年/流月/流日干支
- {{lunarMonth}} / {{lunarDay}}：农历月份与初几
- {{phaseText}}：月相（由 phaseIndex + 盈/亏 映射为 新月/上弦月/满月/下弦月 + 盈/亏）
- {{marketBias}}：次日大盘倾向（来自现有预测模块的标签映射）
- {{gender}} / {{birth}} / {{place}} / {{baziText}}：同上
