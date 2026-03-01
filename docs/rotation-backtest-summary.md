# 主线&轮动回放与校准总览（2026-02-26）

## 回放统计
- 样本数：358
- 3日：胜率 64.25%，均值 1.07%，最佳 14.951%，最差 -10.681%
- 5日：胜率 67.04%，均值 1.784%，最佳 18.079%，最差 -11.555%
- 换手率：0.5686
- 最大回撤：3日 -19.72%，5日 -31.68%

## 校准口径
- 分桶：bin_size 1.0
- 得分区间：[-10.0, 5.91]
- 阈值：up=2.0，down=2.0

## 失败样本 Top3
- 3日：2026-01-28 有色金属 score 3.5299 回报 -10.681%
- 3日：2026-01-29 有色金属 score 4.0174 回报 -9.09%
- 3日：2026-01-15 云计算 score 4.8665 回报 -4.312%
- 5日：2026-01-29 有色金属 score 4.0174 回报 -11.555%
- 5日：2026-01-28 有色金属 score 3.5299 回报 -8.392%
- 5日：2026-01-27 有色金属 score 5.728 回报 -4.336%

## 产出文件
- data/rotation-calibration.json
- data/rotation-backtest-report.json
- data/sector-rotation-YYYYMMDD.json

## 验收要点
- 回放与校准：python3 fetch_sector_data.py rotation_calibrate 240 1.0
- Rotation 输出：python3 fetch_sector_data.py rotation_dynamic 20
- 盘后快照：bash scripts/fetch_rotation_job.sh
