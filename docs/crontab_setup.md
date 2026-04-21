# 定时任务配置说明

## Cron任务配置

### 1. 日线数据更新（每个交易日 15:30）
```bash
# 编辑crontab
crontab -e

# 添加以下行
30 15 * * 1-5 cd /Users/una5577/Documents/trae_projects/a-stock-monitor && python3 data_maintenance.py >> /Users/una5577/Documents/trae_projects/a-stock-monitor/logs/cron.log 2>&1
```

### 2. 分时数据更新（交易时间内每30分钟）
```bash
# 添加以下行（9:30-15:00 每30分钟）
30 9,10,11,12,13,14,15 * * 1-5 cd /Users/una5577/Documents/trae_projects/a-stock-monitor && python3 -c "from data_maintenance import update_minute_data; update_minute_data()" >> /Users/una5577/Documents/trae_projects/a-stock-monitor/logs/minute_cron.log 2>&1
```

### 3. 验证cron任务
```bash
# 查看当前cron任务
crontab -l

# 查看cron日志
tail -f /Users/una5577/Documents/trae_projects/a-stock-monitor/logs/cron.log
```

## 当前已配置任务

### 会话级定时任务（自动创建）
- **任务ID**: 1eb60444
- **时间**: 每周一至周五 15:30
- **命令**: `python3 data_maintenance.py`
- **状态**: 会话级（3天后自动过期）
- **持久化**: 需要手动添加到系统crontab

## 手动执行命令

### 立即更新所有数据
```bash
cd /Users/una5577/Documents/trae_projects/a-stock-monitor
python3 data_maintenance.py
```

### 仅更新分时数据
```bash
cd /Users/una5577/Documents/trae_projects/a-stock-monitor
python3 -c "from data_maintenance import update_minute_data; update_minute_data()"
```

### 仅更新日线数据
```bash
cd /Users/una5577/Documents/trae_projects/a-stock-monitor
python3 -c "from data_maintenance import update_all_index_data, update_all_etf_data; update_all_index_data(); update_all_etf_data()"
```

## 日志文件位置

- **主任务日志**: `logs/cron.log`
- **分时数据日志**: `logs/minute_cron.log`
- **数据文件**:
  - 指数日线: `data/index_daily/index_*.jsonl`
  - ETF日线: `data/etf_daily/etf_*.jsonl`
  - 分时数据: `data/minute_data/minute_*_YYYY-MM-DD.jsonl`

## 数据验证

### 检查最新数据日期
```bash
# 查看上证指数最新数据
tail -1 data/index_daily/index_000001.jsonl

# 查看半导体ETF最新数据
tail -1 data/etf_daily/etf_512480.jsonl

# 查看今日分时数据
ls -la data/minute_data/
```

## 故障排查

### 1. cron任务未执行
```bash
# 检查cron服务状态（Linux）
sudo systemctl status cron

# macOS使用launchd，无需检查
```

### 2. 权限问题
```bash
# 确保脚本有执行权限
chmod +x data_maintenance.py
```

### 3. Python路径问题
```bash
# 使用完整Python路径
which python3

# 在crontab中使用绝对路径
/usr/bin/python3 data_maintenance.py
```

## 注意事项

1. **交易日判断**: 脚本会自动判断是否为交易日（排除周末和节假日）
2. **数据去重**: 自动检测最新日期，只追加新数据
3. **错误重试**: 网络错误会自动重试3次
4. **文件格式**: 所有数据使用JSONL格式，每行一个JSON对象
5. **ETF代码**: 必须保留sh/sz前缀（如sh512480）
